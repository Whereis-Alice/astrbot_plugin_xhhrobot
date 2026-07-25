from __future__ import annotations

import asyncio
import copy
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any

from .models import Mention


STATE_VERSION = 1


class StateStore:
    def __init__(
        self,
        *,
        load_value: Callable[[str, Any], Awaitable[Any]],
        save_value: Callable[[str, Any], Awaitable[None]],
        key: str = "runtime_state_v1",
        max_queue: int = 500,
        max_recent: int = 200,
        max_dead: int = 200,
    ) -> None:
        self._load_value = load_value
        self._save_value = save_value
        self._key = key
        self._max_queue = max(20, max_queue)
        self._max_recent = max(20, max_recent)
        self._max_dead = max(20, max_dead)
        self._lock = asyncio.Lock()
        self._state = self._default_state()

    async def initialize(self) -> None:
        raw = await self._load_value(self._key, None)
        async with self._lock:
            self._state = self._normalise(raw)
            recovered = self._recover_sending_locked()
            if recovered:
                await self._save_locked()

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return copy.deepcopy(self._state)

    async def set_paused(self, paused: bool) -> None:
        async with self._lock:
            self._state["paused"] = bool(paused)
            await self._save_locked()

    async def set_initial_cursor(self, newest_message_id: int) -> None:
        async with self._lock:
            self._state["initialized"] = True
            self._state["last_message_id"] = max(0, int(newest_message_id))
            self._state["stats"]["baseline_skipped"] += 1
            await self._save_locked()

    async def ingest(
        self,
        *,
        newest_message_id: int,
        queued: Iterable[Mention],
        ignored: Iterable[tuple[Mention, str]],
    ) -> tuple[int, int]:
        queued_count = 0
        ignored_count = 0
        now = time.time()
        async with self._lock:
            queue = self._state["queue"]
            dead = self._state["dead"]
            recent_ids = {str(item.get("message_id") or "") for item in self._state["recent"]}
            for mention in queued:
                key = str(mention.message_id)
                if key in queue or key in dead or key in recent_ids:
                    continue
                if len(queue) >= self._max_queue:
                    self._append_dead_locked(mention, "queue_overflow", "待处理队列已满。", now)
                    continue
                queue[key] = {
                    **mention.to_dict(),
                    "status": "pending",
                    "attempts": 0,
                    "next_attempt_at": 0.0,
                    "last_error": "",
                    "created_at": now,
                    "updated_at": now,
                }
                queued_count += 1
            for mention, reason in ignored:
                key = str(mention.message_id)
                if key in queue or key in dead or key in recent_ids:
                    continue
                self._append_recent_locked(mention, "ignored", reason, "", now)
                ignored_count += 1
            self._state["initialized"] = True
            self._state["last_message_id"] = max(
                int(self._state.get("last_message_id") or 0),
                int(newest_message_id or 0),
            )
            self._state["stats"]["seen"] += queued_count + ignored_count
            self._state["stats"]["queued"] += queued_count
            self._state["stats"]["ignored"] += ignored_count
            await self._save_locked()
        return queued_count, ignored_count

    async def due_items(self, *, limit: int, now: float | None = None) -> list[Mention]:
        current = time.time() if now is None else now
        async with self._lock:
            items = [
                value
                for value in self._state["queue"].values()
                if value.get("status") == "pending" and float(value.get("next_attempt_at") or 0) <= current
            ]
            items.sort(key=lambda item: (float(item.get("created_at") or 0), int(item.get("message_id") or 0)))
            return [Mention.from_dict(item) for item in items[: max(0, limit)]]

    async def mark_sending(self, message_id: int) -> None:
        async with self._lock:
            item = self._state["queue"].get(str(message_id))
            if item is None:
                return
            item["status"] = "sending"
            item["updated_at"] = time.time()
            await self._save_locked()

    async def mark_retry(
        self,
        message_id: int,
        error: str,
        *,
        max_attempts: int,
        delay_seconds: float,
    ) -> bool:
        async with self._lock:
            key = str(message_id)
            item = self._state["queue"].get(key)
            if item is None:
                return False
            attempts = int(item.get("attempts") or 0) + 1
            item.update(
                {
                    "status": "pending",
                    "attempts": attempts,
                    "last_error": error[:1000],
                    "next_attempt_at": time.time() + max(0.0, delay_seconds),
                    "updated_at": time.time(),
                }
            )
            self._state["stats"]["failed_attempts"] += 1
            if attempts >= max(1, max_attempts):
                mention = Mention.from_dict(item)
                self._state["queue"].pop(key, None)
                self._append_dead_locked(mention, "retry_exhausted", error, time.time(), attempts=attempts)
                self._state["stats"]["dead"] += 1
                await self._save_locked()
                return False
            await self._save_locked()
            return True

    async def defer(self, message_id: int, error: str, *, delay_seconds: float) -> None:
        async with self._lock:
            item = self._state["queue"].get(str(message_id))
            if item is None:
                return
            item.update(
                {
                    "status": "pending",
                    "last_error": error[:1000],
                    "next_attempt_at": time.time() + max(0.0, delay_seconds),
                    "updated_at": time.time(),
                }
            )
            await self._save_locked()

    async def mark_uncertain(self, message_id: int, error: str) -> None:
        async with self._lock:
            key = str(message_id)
            item = self._state["queue"].pop(key, None)
            if item is None:
                return
            mention = Mention.from_dict(item)
            self._append_dead_locked(
                mention,
                "uncertain_delivery",
                error,
                time.time(),
                attempts=int(item.get("attempts") or 0),
            )
            self._state["stats"]["dead"] += 1
            await self._save_locked()

    async def mark_done(self, message_id: int, reply_text: str) -> None:
        async with self._lock:
            key = str(message_id)
            item = self._state["queue"].pop(key, None)
            if item is None:
                return
            self._append_recent_locked(Mention.from_dict(item), "replied", "", reply_text, time.time())
            self._state["stats"]["replied"] += 1
            await self._save_locked()

    async def mark_skipped(self, message_id: int, reason: str) -> None:
        async with self._lock:
            key = str(message_id)
            item = self._state["queue"].pop(key, None)
            if item is None:
                return
            self._append_recent_locked(Mention.from_dict(item), "skipped", reason, "", time.time())
            self._state["stats"]["skipped"] += 1
            await self._save_locked()

    async def retry_dead(self, *, include_uncertain: bool = True) -> int:
        async with self._lock:
            moved = 0
            now = time.time()
            for key, item in list(self._state["dead"].items()):
                if len(self._state["queue"]) >= self._max_queue:
                    break
                if item.get("reason") == "uncertain_delivery" and not include_uncertain:
                    continue
                mention = Mention.from_dict(item)
                self._state["queue"][key] = {
                    **mention.to_dict(),
                    "status": "pending",
                    "attempts": 0,
                    "next_attempt_at": 0.0,
                    "last_error": "",
                    "created_at": now,
                    "updated_at": now,
                }
                self._state["dead"].pop(key, None)
                moved += 1
            if moved:
                await self._save_locked()
            return moved

    async def conversation_history(self, *, link_id: int, user_id: int, turns: int) -> list[dict[str, str]]:
        if turns <= 0:
            return []
        async with self._lock:
            matched = [
                item
                for item in self._state["recent"]
                if item.get("status") == "replied"
                and int(item.get("link_id") or 0) == link_id
                and int(item.get("user_id") or 0) == user_id
            ]
            matched = matched[-turns:]
            return [
                {
                    "user": str(item.get("comment_text") or ""),
                    "assistant": str(item.get("reply_text") or ""),
                }
                for item in matched
            ]

    def _recover_sending_locked(self) -> int:
        recovered = 0
        now = time.time()
        for key, item in list(self._state["queue"].items()):
            if item.get("status") != "sending":
                continue
            self._state["queue"].pop(key, None)
            self._append_dead_locked(
                Mention.from_dict(item),
                "uncertain_delivery",
                "AstrBot 在回帖发送过程中重启，无法确认是否已发布。",
                now,
                attempts=int(item.get("attempts") or 0),
            )
            recovered += 1
        if recovered:
            self._state["stats"]["dead"] += recovered
        return recovered

    def _append_recent_locked(
        self,
        mention: Mention,
        status: str,
        reason: str,
        reply_text: str,
        now: float,
    ) -> None:
        self._state["recent"].append(
            {
                **mention.to_dict(),
                "status": status,
                "reason": reason[:500],
                "reply_text": reply_text[:5000],
                "completed_at": now,
            }
        )
        self._state["recent"] = self._state["recent"][-self._max_recent :]

    def _append_dead_locked(
        self,
        mention: Mention,
        reason: str,
        error: str,
        now: float,
        *,
        attempts: int = 0,
    ) -> None:
        self._state["dead"][str(mention.message_id)] = {
            **mention.to_dict(),
            "reason": reason,
            "last_error": error[:1000],
            "attempts": attempts,
            "failed_at": now,
        }
        if len(self._state["dead"]) > self._max_dead:
            oldest = min(
                self._state["dead"],
                key=lambda key: float(self._state["dead"][key].get("failed_at") or 0),
            )
            self._state["dead"].pop(oldest, None)

    async def _save_locked(self) -> None:
        await self._save_value(self._key, self._state)

    @classmethod
    def _normalise(cls, raw: Any) -> dict[str, Any]:
        state = cls._default_state()
        if not isinstance(raw, Mapping):
            return state
        state["initialized"] = bool(raw.get("initialized", False))
        try:
            state["last_message_id"] = int(raw.get("last_message_id") or 0)
        except (TypeError, ValueError):
            state["last_message_id"] = 0
        state["paused"] = bool(raw.get("paused", False))
        for key in ("queue", "dead"):
            value = raw.get(key)
            if isinstance(value, Mapping):
                state[key] = {
                    str(item_key): dict(item)
                    for item_key, item in value.items()
                    if isinstance(item, Mapping)
                }
        recent = raw.get("recent")
        if isinstance(recent, list):
            state["recent"] = [dict(item) for item in recent if isinstance(item, Mapping)]
        stats = raw.get("stats")
        if isinstance(stats, Mapping):
            for key in state["stats"]:
                try:
                    state["stats"][key] = int(stats.get(key) or 0)
                except (TypeError, ValueError):
                    pass
        return state

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "initialized": False,
            "last_message_id": 0,
            "paused": False,
            "queue": {},
            "dead": {},
            "recent": [],
            "stats": {
                "seen": 0,
                "queued": 0,
                "ignored": 0,
                "replied": 0,
                "skipped": 0,
                "failed_attempts": 0,
                "dead": 0,
                "baseline_skipped": 0,
            },
        }
