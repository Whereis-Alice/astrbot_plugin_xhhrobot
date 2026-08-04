from __future__ import annotations

import asyncio
import copy
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any

from .models import Mention

STATE_VERSION = 5


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
        max_browse_records: int = 500,
    ) -> None:
        self._load_value = load_value
        self._save_value = save_value
        self._key = key
        self._max_queue = max(20, max_queue)
        self._max_recent = max(20, max_recent)
        self._max_dead = max(20, max_dead)
        self._max_browse_records = max(100, max_browse_records)
        self._lock = asyncio.Lock()
        self._state = self._default_state()

    async def initialize(self) -> None:
        raw = await self._load_value(self._key, None)
        async with self._lock:
            self._state = self._normalise(raw)
            recovered = self._recover_sending_locked()
            browse_recovered = self._recover_browse_sending_locked()
            self._prune_browse_records_locked()
            if recovered or browse_recovered:
                await self._save_locked()

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return copy.deepcopy(self._state)

    async def set_paused(self, paused: bool) -> None:
        async with self._lock:
            self._state["paused"] = bool(paused)
            await self._save_locked()

    async def set_initial_cursor(
        self,
        newest_message_id: int,
        *,
        source: str = "mention",
    ) -> None:
        async with self._lock:
            initialized_key, cursor_key = self._cursor_keys(source)
            self._state[initialized_key] = True
            self._state[cursor_key] = max(0, int(newest_message_id))
            self._state["stats"]["baseline_skipped"] += 1
            await self._save_locked()

    async def ingest(
        self,
        *,
        newest_message_id: int,
        queued: Iterable[Mention],
        ignored: Iterable[tuple[Mention, str]],
        source: str = "mention",
        max_own_post_replies_per_post: int = 0,
    ) -> tuple[int, int, list[Mention]]:
        queued_count = 0
        ignored_count = 0
        limit_skipped: list[Mention] = []
        own_post_limit = max(0, int(max_own_post_replies_per_post))
        now = time.time()
        async with self._lock:
            queue = self._state["queue"]
            dead = self._state["dead"]
            own_post_usage = self._own_post_reply_usage_locked()
            recent_ids = {
                str(item.get("message_id") or "") for item in self._state["recent"]
            }
            for mention in queued:
                key = str(mention.message_id)
                if key in queue or key in dead or key in recent_ids:
                    continue
                duplicate = self._find_active_target_locked(mention)
                if duplicate is not None:
                    duplicate_key, duplicate_item = duplicate
                    if (
                        duplicate_key in queue
                        and mention.source == "own_post_comment"
                        and not self._counts_toward_own_post_limit(duplicate_item)
                    ):
                        link_key = str(max(0, int(mention.link_id)))
                        duplicate_status = str(
                            duplicate_item.get("status") or "pending"
                        )
                        if (
                            own_post_limit > 0
                            and link_key != "0"
                            and own_post_usage.get(link_key, 0) >= own_post_limit
                            and duplicate_status in {"pending", "dispatched"}
                        ):
                            queue.pop(duplicate_key, None)
                            skipped_mention = Mention.from_dict(duplicate_item)
                            self._append_recent_locked(
                                skipped_mention,
                                "skipped",
                                self._own_post_limit_reason(own_post_limit),
                                "",
                                now,
                            )
                            self._state["stats"]["skipped"] += 1
                            limit_skipped.append(mention)
                            continue
                        duplicate_item["counts_toward_own_post_limit"] = True
                        if link_key != "0":
                            own_post_usage[link_key] = (
                                own_post_usage.get(link_key, 0) + 1
                            )
                    if (
                        duplicate_key in queue
                        and mention.source == "mention"
                        and duplicate_item.get("source") != "mention"
                    ):
                        duplicate_item.update(
                            {
                                "source": "mention",
                                "user_id": mention.user_id,
                                "comment_text": mention.comment_text,
                                "root_comment_id": mention.root_comment_id,
                                "updated_at": now,
                            }
                        )
                        queue[duplicate_key] = duplicate_item
                    continue
                if mention.source == "own_post_comment" and mention.link_id > 0:
                    link_key = str(mention.link_id)
                    if (
                        own_post_limit > 0
                        and own_post_usage.get(link_key, 0) >= own_post_limit
                    ):
                        self._append_recent_locked(
                            mention,
                            "skipped",
                            self._own_post_limit_reason(own_post_limit),
                            "",
                            now,
                        )
                        self._state["stats"]["skipped"] += 1
                        limit_skipped.append(mention)
                        continue
                if len(queue) >= self._max_queue:
                    self._append_dead_locked(
                        mention, "queue_overflow", "待处理队列已满。", now
                    )
                    continue
                queue[key] = {
                    **mention.to_dict(),
                    "status": "pending",
                    "attempts": 0,
                    "next_attempt_at": 0.0,
                    "last_error": "",
                    "created_at": now,
                    "updated_at": now,
                    "counts_toward_own_post_limit": (
                        mention.source == "own_post_comment"
                    ),
                }
                queued_count += 1
                if mention.source == "own_post_comment" and mention.link_id > 0:
                    link_key = str(mention.link_id)
                    own_post_usage[link_key] = own_post_usage.get(link_key, 0) + 1
            for mention, reason in ignored:
                key = str(mention.message_id)
                if key in queue or key in dead or key in recent_ids:
                    continue
                if self._find_active_target_locked(mention) is not None:
                    continue
                self._append_recent_locked(mention, "ignored", reason, "", now)
                ignored_count += 1
            initialized_key, cursor_key = self._cursor_keys(source)
            self._state[initialized_key] = True
            self._state[cursor_key] = max(
                int(self._state.get(cursor_key) or 0),
                int(newest_message_id or 0),
            )
            self._state["stats"]["seen"] += (
                queued_count + ignored_count + len(limit_skipped)
            )
            self._state["stats"]["queued"] += queued_count
            self._state["stats"]["ignored"] += ignored_count
            await self._save_locked()
        return queued_count, ignored_count, limit_skipped

    async def seed_own_post_reply_counts(
        self,
        counts: Mapping[int | str, int],
    ) -> None:
        """Merge durable per-post reply counts recovered from SQLite."""

        async with self._lock:
            changed = False
            stored = self._state["own_post_reply_counts"]
            for raw_link_id, raw_count in counts.items():
                try:
                    link_id = int(raw_link_id)
                    count = max(0, int(raw_count))
                except (TypeError, ValueError):
                    continue
                if link_id <= 0 or count <= int(stored.get(str(link_id)) or 0):
                    continue
                stored[str(link_id)] = count
                changed = True
            if changed:
                await self._save_locked()

    async def enforce_own_post_reply_limit(self, limit: int) -> list[Mention]:
        """Remove queued own-post replies that no longer fit the configured cap."""

        maximum = max(0, int(limit))
        if maximum <= 0:
            return []
        async with self._lock:
            usage = {
                str(key): max(0, int(value or 0))
                for key, value in self._state["own_post_reply_counts"].items()
            }
            entries = [
                (str(key), item)
                for key, item in self._state["queue"].items()
                if self._counts_toward_own_post_limit(item)
                and int(item.get("link_id") or 0) > 0
            ]
            priority = {"sending": 0, "dispatched": 1, "pending": 2}
            entries.sort(
                key=lambda pair: (
                    priority.get(str(pair[1].get("status") or "pending"), 3),
                    float(pair[1].get("created_at") or 0),
                    int(pair[1].get("message_id") or 0),
                )
            )
            skipped: list[Mention] = []
            now = time.time()
            for key, item in entries:
                link_key = str(int(item.get("link_id") or 0))
                status = str(item.get("status") or "pending")
                if status == "sending":
                    usage[link_key] = usage.get(link_key, 0) + 1
                    continue
                if status not in {"pending", "dispatched"}:
                    continue
                if usage.get(link_key, 0) < maximum:
                    usage[link_key] = usage.get(link_key, 0) + 1
                    continue
                self._state["queue"].pop(key, None)
                mention = Mention.from_dict(item)
                self._append_recent_locked(
                    mention,
                    "skipped",
                    self._own_post_limit_reason(maximum),
                    "",
                    now,
                )
                self._state["stats"]["skipped"] += 1
                skipped.append(mention)
            if skipped:
                await self._save_locked()
            return skipped

    async def cancel_queue(
        self,
        *,
        link_id: int = 0,
        reason: str = "管理员取消待处理队列",
    ) -> tuple[list[Mention], dict[str, int]]:
        """Cancel pending/dispatched comments while preserving active sends."""

        target_link_id = max(0, int(link_id))
        async with self._lock:
            cancelled: list[Mention] = []
            counts = {
                "cancelled_total": 0,
                "cancelled_pending": 0,
                "cancelled_dispatched": 0,
                "sending_preserved": 0,
                "queue_remaining": 0,
            }
            now = time.time()
            for key, item in list(self._state["queue"].items()):
                item_link_id = int(item.get("link_id") or 0)
                if target_link_id and item_link_id != target_link_id:
                    continue
                status = str(item.get("status") or "pending")
                if status == "sending":
                    counts["sending_preserved"] += 1
                    continue
                if status not in {"pending", "dispatched"}:
                    continue
                self._state["queue"].pop(key, None)
                mention = Mention.from_dict(item)
                self._append_recent_locked(mention, "skipped", reason, "", now)
                self._state["stats"]["skipped"] += 1
                counts[f"cancelled_{status}"] += 1
                counts["cancelled_total"] += 1
                cancelled.append(mention)
            counts["queue_remaining"] = len(self._state["queue"])
            if cancelled:
                await self._save_locked()
            return cancelled, counts

    async def due_items(self, *, limit: int, now: float | None = None) -> list[Mention]:
        current = time.time() if now is None else now
        async with self._lock:
            items = [
                value
                for value in self._state["queue"].values()
                if value.get("status") == "pending"
                and float(value.get("next_attempt_at") or 0) <= current
            ]
            items.sort(
                key=lambda item: (
                    float(item.get("created_at") or 0),
                    int(item.get("message_id") or 0),
                )
            )
            return [Mention.from_dict(item) for item in items[: max(0, limit)]]

    async def mark_sending(
        self,
        message_id: int,
        *,
        max_own_post_replies_per_post: int = 0,
    ) -> bool:
        """Atomically claim the one allowed outbound reply for a comment.

        A notification can arrive through both the mention stream and the
        own-post-comment stream.  The queue normally merges those records, but
        this final gate also protects against stale or concurrently dispatched
        events before a request reaches Xiaoheihe.
        """

        async with self._lock:
            key = str(message_id)
            item = self._state["queue"].get(key)
            if item is None:
                return False
            if item.get("status") not in {"pending", "dispatched"}:
                return False

            if self._target_already_claimed_locked(key, item):
                self._skip_duplicate_locked(key, item)
                await self._save_locked()
                return False

            own_post_limit = max(0, int(max_own_post_replies_per_post))
            if (
                own_post_limit > 0
                and self._counts_toward_own_post_limit(item)
                and int(item.get("link_id") or 0) > 0
            ):
                link_key = str(int(item.get("link_id") or 0))
                claimed = int(
                    self._state["own_post_reply_counts"].get(link_key) or 0
                )
                claimed += sum(
                    1
                    for other_key, other in self._state["queue"].items()
                    if other_key != key
                    and str(other.get("status") or "") == "sending"
                    and self._counts_toward_own_post_limit(other)
                    and int(other.get("link_id") or 0) == int(link_key)
                )
                if claimed >= own_post_limit:
                    self._state["queue"].pop(key, None)
                    self._append_recent_locked(
                        Mention.from_dict(item),
                        "skipped",
                        self._own_post_limit_reason(own_post_limit),
                        "",
                        time.time(),
                    )
                    self._state["stats"]["skipped"] += 1
                    await self._save_locked()
                    return False

            item["status"] = "sending"
            item["updated_at"] = time.time()
            await self._save_locked()
            return True

    async def mark_dispatched(self, message_id: int) -> bool:
        """Claim a pending item before building its standard AstrBot event."""

        async with self._lock:
            key = str(message_id)
            item = self._state["queue"].get(key)
            if item is None or item.get("status") != "pending":
                return False
            if self._target_already_claimed_locked(key, item):
                self._skip_duplicate_locked(key, item)
                await self._save_locked()
                return False
            item["status"] = "dispatched"
            item["updated_at"] = time.time()
            await self._save_locked()
            return True

    async def item_status(self, message_id: int) -> str:
        status, _ = await self.item_outcome(message_id)
        return status

    async def item_outcome(self, message_id: int) -> tuple[str, str]:
        async with self._lock:
            item = self._state["queue"].get(str(message_id))
            if item is not None:
                return str(item.get("status") or ""), str(
                    item.get("last_error") or ""
                )
            dead = self._state["dead"].get(str(message_id))
            if dead is not None:
                return str(dead.get("reason") or "dead"), str(
                    dead.get("last_error") or ""
                )
            for recent in reversed(self._state["recent"]):
                if int(recent.get("message_id") or 0) == int(message_id):
                    return str(recent.get("status") or ""), str(
                        recent.get("reason") or ""
                    )
            return "", ""

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
                self._append_dead_locked(
                    mention, "retry_exhausted", error, time.time(), attempts=attempts
                )
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
            self._increment_own_post_reply_count_locked(item)
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
            self._increment_own_post_reply_count_locked(item)
            self._append_recent_locked(
                Mention.from_dict(item), "replied", "", reply_text, time.time()
            )
            self._state["stats"]["replied"] += 1
            await self._save_locked()

    async def mark_skipped(self, message_id: int, reason: str) -> bool:
        async with self._lock:
            key = str(message_id)
            item = self._state["queue"].pop(key, None)
            if item is None:
                return False
            self._append_recent_locked(
                Mention.from_dict(item), "skipped", reason, "", time.time()
            )
            self._state["stats"]["skipped"] += 1
            await self._save_locked()
            return True

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
                    "counts_toward_own_post_limit": (
                        mention.source == "own_post_comment"
                    ),
                }
                self._state["dead"].pop(key, None)
                moved += 1
            if moved:
                await self._save_locked()
            return moved

    async def conversation_history(
        self, *, link_id: int, user_id: int, turns: int
    ) -> list[dict[str, str]]:
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

    async def begin_browse_run(self, *, now: float, next_run_at: float) -> None:
        async with self._lock:
            browse = self._state["auto_browse"]
            browse["last_run_at"] = max(0.0, float(now))
            browse["next_run_at"] = max(0.0, float(next_run_at))
            browse["last_error"] = ""
            browse["stats"]["runs"] += 1
            await self._save_locked()

    async def schedule_browse(self, next_run_at: float) -> None:
        async with self._lock:
            self._state["auto_browse"]["next_run_at"] = max(0.0, float(next_run_at))
            await self._save_locked()

    async def note_browse_feed(self, count: int) -> None:
        async with self._lock:
            self._state["auto_browse"]["stats"]["seen"] += max(0, int(count))
            await self._save_locked()

    async def finish_browse_run(self, error: str = "") -> None:
        async with self._lock:
            browse = self._state["auto_browse"]
            if error:
                browse["last_error"] = str(error)[:1000]
                browse["stats"]["failed_runs"] += 1
            else:
                browse["last_error"] = ""
                browse["last_success_at"] = time.time()
            await self._save_locked()

    async def record_browse(
        self,
        *,
        link_id: int,
        title: str,
        author_id: str,
        status: str,
        reason: str = "",
        comment_text: str = "",
        evaluated: bool = False,
        now: float | None = None,
    ) -> None:
        current = time.time() if now is None else float(now)
        key = str(max(0, int(link_id)))
        if key == "0":
            return
        async with self._lock:
            browse = self._state["auto_browse"]
            previous = browse["records"].get(key, {})
            record = {
                "link_id": int(link_id),
                "title": str(title)[:500],
                "author_id": str(author_id)[:100],
                "status": str(status),
                "reason": str(reason)[:1000],
                "comment_text": str(comment_text)[:5000],
                "attempted_at": (
                    current
                    if status == "sending"
                    else float(previous.get("attempted_at") or current)
                ),
                "completed_at": 0.0 if status == "sending" else current,
            }
            browse["records"][key] = record

            if status != "sending":
                if evaluated:
                    browse["stats"]["evaluated"] += 1
                counter = {
                    "commented": "commented",
                    "skipped": "skipped",
                    "dry_run": "dry_runs",
                    "failed": "failed",
                    "uncertain": "uncertain",
                }.get(status)
                if counter:
                    browse["stats"][counter] += 1
            self._prune_browse_records_locked()
            await self._save_locked()

    def _recover_sending_locked(self) -> int:
        recovered = 0
        uncertain_recovered = 0
        now = time.time()
        for key, item in list(self._state["queue"].items()):
            if item.get("status") == "dispatched":
                item["status"] = "pending"
                item["last_error"] = "AstrBot 重启前事件尚未开始发送，已重新排队。"
                item["next_attempt_at"] = 0.0
                item["updated_at"] = now
                recovered += 1
                continue
            if item.get("status") != "sending":
                continue
            self._state["queue"].pop(key, None)
            self._increment_own_post_reply_count_locked(item)
            self._append_dead_locked(
                Mention.from_dict(item),
                "uncertain_delivery",
                "AstrBot 在回帖发送过程中重启，无法确认是否已发布。",
                now,
                attempts=int(item.get("attempts") or 0),
            )
            recovered += 1
            uncertain_recovered += 1
        if uncertain_recovered:
            self._state["stats"]["dead"] += uncertain_recovered
        return recovered

    def _recover_browse_sending_locked(self) -> int:
        recovered = 0
        now = time.time()
        browse = self._state["auto_browse"]
        for item in browse["records"].values():
            if item.get("status") != "sending":
                continue
            item["status"] = "uncertain"
            item["reason"] = "AstrBot 在自动评论发送过程中重启，无法确认是否已发布。"
            item["completed_at"] = now
            recovered += 1
        if recovered:
            browse["stats"]["uncertain"] += recovered
        return recovered

    def _prune_browse_records_locked(self) -> None:
        records = self._state["auto_browse"]["records"]
        if len(records) <= self._max_browse_records:
            return
        ordered = sorted(
            records,
            key=lambda key: float(
                records[key].get("completed_at")
                or records[key].get("attempted_at")
                or 0
            ),
        )
        for key in ordered[: len(records) - self._max_browse_records]:
            records.pop(key, None)

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

    def _find_active_target_locked(
        self,
        mention: Mention,
    ) -> tuple[str, dict[str, Any]] | None:
        if mention.link_id <= 0 or mention.comment_id <= 0:
            return None
        target = mention.target_key
        for key, item in self._state["queue"].items():
            if self._item_target(item) == target:
                return str(key), item
        for collection in (self._state["dead"],):
            for key, item in collection.items():
                if self._item_target(item) == target:
                    return str(key), item
        for item in self._state["recent"]:
            if item.get("status") == "replied" and self._item_target(item) == target:
                return str(item.get("message_id") or ""), item
        return None

    def _target_already_claimed_locked(
        self,
        key: str,
        item: Mapping[str, Any],
    ) -> bool:
        target = self._item_target(item)
        if target == (0, 0):
            return False
        for other_key, other in self._state["queue"].items():
            if other_key == key or self._item_target(other) != target:
                continue
            if other.get("status") in {"dispatched", "sending"}:
                return True
        return any(
            recent.get("status") == "replied"
            and self._item_target(recent) == target
            for recent in self._state["recent"]
        )

    def _skip_duplicate_locked(self, key: str, item: Mapping[str, Any]) -> None:
        self._state["queue"].pop(key, None)
        self._append_recent_locked(
            Mention.from_dict(item),
            "skipped",
            "同一条评论已经在发送或已完成回复",
            "",
            time.time(),
        )
        self._state["stats"]["skipped"] += 1

    def _own_post_reply_usage_locked(self) -> dict[str, int]:
        usage = {
            str(key): max(0, int(value or 0))
            for key, value in self._state["own_post_reply_counts"].items()
        }
        for item in self._state["queue"].values():
            if not self._counts_toward_own_post_limit(item):
                continue
            if str(item.get("status") or "pending") not in {
                "pending",
                "dispatched",
                "sending",
            }:
                continue
            link_id = int(item.get("link_id") or 0)
            if link_id > 0:
                link_key = str(link_id)
                usage[link_key] = usage.get(link_key, 0) + 1
        return usage

    def _increment_own_post_reply_count_locked(
        self,
        item: Mapping[str, Any],
    ) -> None:
        if not self._counts_toward_own_post_limit(item):
            return
        link_id = int(item.get("link_id") or 0)
        if link_id <= 0:
            return
        key = str(link_id)
        counts = self._state["own_post_reply_counts"]
        counts[key] = int(counts.get(key) or 0) + 1

    @staticmethod
    def _counts_toward_own_post_limit(item: Mapping[str, Any]) -> bool:
        marker = item.get("counts_toward_own_post_limit")
        if marker is not None:
            return bool(marker)
        return str(item.get("source") or "") == "own_post_comment"

    @staticmethod
    def _own_post_limit_reason(limit: int) -> str:
        return f"该帖子已达到自动回复总上限（{max(0, int(limit))} 条）"

    @staticmethod
    def _item_target(item: Mapping[str, Any]) -> tuple[int, int]:
        try:
            return int(item.get("link_id") or 0), int(item.get("comment_id") or 0)
        except (TypeError, ValueError):
            return 0, 0

    @staticmethod
    def _cursor_keys(source: str) -> tuple[str, str]:
        if source == "own_post_comment":
            return "comments_initialized", "last_comment_message_id"
        return "initialized", "last_message_id"

    async def _save_locked(self) -> None:
        await self._save_value(self._key, self._state)

    @classmethod
    def _normalise(cls, raw: Any) -> dict[str, Any]:
        state = cls._default_state()
        if not isinstance(raw, Mapping):
            return state
        state["initialized"] = bool(raw.get("initialized", False))
        state["comments_initialized"] = bool(raw.get("comments_initialized", False))
        try:
            state["last_message_id"] = int(raw.get("last_message_id") or 0)
        except (TypeError, ValueError):
            state["last_message_id"] = 0
        try:
            state["last_comment_message_id"] = int(
                raw.get("last_comment_message_id") or 0
            )
        except (TypeError, ValueError):
            state["last_comment_message_id"] = 0
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
            state["recent"] = [
                dict(item) for item in recent if isinstance(item, Mapping)
            ]
        reply_counts = raw.get("own_post_reply_counts")
        if isinstance(reply_counts, Mapping):
            for raw_link_id, raw_count in reply_counts.items():
                try:
                    link_id = int(raw_link_id)
                    count = max(0, int(raw_count))
                except (TypeError, ValueError):
                    continue
                if link_id > 0 and count > 0:
                    state["own_post_reply_counts"][str(link_id)] = count
        stats = raw.get("stats")
        if isinstance(stats, Mapping):
            for key in state["stats"]:
                try:
                    state["stats"][key] = int(stats.get(key) or 0)
                except (TypeError, ValueError):
                    pass
        browse = raw.get("auto_browse")
        if isinstance(browse, Mapping):
            for key in ("next_run_at", "last_run_at", "last_success_at"):
                try:
                    state["auto_browse"][key] = max(0.0, float(browse.get(key) or 0))
                except (TypeError, ValueError):
                    pass
            state["auto_browse"]["last_error"] = str(browse.get("last_error") or "")[
                :1000
            ]
            records = browse.get("records")
            if isinstance(records, Mapping):
                state["auto_browse"]["records"] = {
                    str(item_key): dict(item)
                    for item_key, item in records.items()
                    if isinstance(item, Mapping)
                }
            browse_stats = browse.get("stats")
            if isinstance(browse_stats, Mapping):
                for key in state["auto_browse"]["stats"]:
                    try:
                        state["auto_browse"]["stats"][key] = int(
                            browse_stats.get(key) or 0
                        )
                    except (TypeError, ValueError):
                        pass
        return state

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "initialized": False,
            "last_message_id": 0,
            "comments_initialized": False,
            "last_comment_message_id": 0,
            "paused": False,
            "queue": {},
            "dead": {},
            "recent": [],
            "own_post_reply_counts": {},
            "auto_browse": {
                "next_run_at": 0.0,
                "last_run_at": 0.0,
                "last_success_at": 0.0,
                "last_error": "",
                "records": {},
                "stats": {
                    "runs": 0,
                    "seen": 0,
                    "evaluated": 0,
                    "commented": 0,
                    "skipped": 0,
                    "dry_runs": 0,
                    "failed": 0,
                    "uncertain": 0,
                    "failed_runs": 0,
                },
            },
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
