from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Mention


class CommentArchive:
    """SQLite-backed archive for received comments and comments sent by the bot."""

    def __init__(
        self,
        path: Path,
        *,
        enabled: bool = True,
        retention_days: int = 365,
        max_records: int = 100_000,
        query_max_results: int = 50,
    ) -> None:
        self.path = Path(path)
        self.enabled = bool(enabled)
        self.retention_days = max(0, int(retention_days))
        self.max_records = max(1_000, int(max_records))
        self.query_max_results = max(1, min(200, int(query_max_results)))
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        if not self.enabled or self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._initialize_sync)
            self._initialized = True

    async def record_received(
        self,
        records: Sequence[tuple[Mention, str, str]],
    ) -> None:
        if not self.enabled or not records:
            return
        await self.initialize()
        async with self._lock:
            await asyncio.to_thread(self._record_received_sync, records)

    async def update_received_status(
        self,
        mention: Mention,
        status: str,
        reason: str = "",
    ) -> None:
        await self.record_received(((mention, status, reason),))

    async def record_bot_comment(
        self,
        *,
        kind: str,
        content: str,
        link_id: int,
        status: str = "sent",
        reason: str = "",
        comment_id: int = 0,
        root_comment_id: int = 0,
        target_comment_id: int = 0,
        target_user_id: int | str = 0,
        source_message_id: int = 0,
        event_key: str = "",
    ) -> None:
        if not self.enabled:
            return
        await self.initialize()
        record = {
            "kind": str(kind or "unknown").strip()[:64],
            "content": str(content or "").strip(),
            "link_id": _as_int(link_id),
            "status": str(status or "sent").strip()[:64],
            "reason": str(reason or "").strip()[:2_000],
            "comment_id": _as_int(comment_id),
            "root_comment_id": _as_int(root_comment_id),
            "target_comment_id": _as_int(target_comment_id),
            "target_user_id": _as_int(target_user_id),
            "source_message_id": _as_int(source_message_id),
            "event_key": str(event_key or "").strip()[:300] or None,
        }
        async with self._lock:
            await asyncio.to_thread(self._record_bot_comment_sync, record)

    async def overview(self) -> dict[str, int | bool]:
        if not self.enabled:
            return {
                "enabled": False,
                "received_comments": 0,
                "received_observations": 0,
                "bot_comments": 0,
                "semantic_cache_records": 0,
            }
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._overview_sync)

    async def own_post_reply_counts(self) -> dict[int, int]:
        """Count sent or uncertain auto replies to comments on the bot's posts."""

        if not self.enabled:
            return {}
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._own_post_reply_counts_sync)

    async def statistics(
        self,
        *,
        keyword: str = "",
        start_time: str | float | None = None,
        end_time: str | float | None = None,
        link_id: int = 0,
        user_id: int = 0,
        root_comment_id: int = 0,
        source: str = "",
        status: str = "",
        bot_kind: str = "",
    ) -> dict[str, Any]:
        self._require_enabled()
        start_at, end_at = _time_range(start_time, end_time)
        filters = {
            "keyword": str(keyword or "").strip(),
            "start_at": start_at,
            "end_at": end_at,
            "link_id": _as_int(link_id),
            "user_id": _as_int(user_id),
            "root_comment_id": _as_int(root_comment_id),
            "source": str(source or "").strip(),
            "status": str(status or "").strip(),
            "bot_kind": str(bot_kind or "").strip(),
        }
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._statistics_sync, filters)

    async def search(
        self,
        *,
        keyword: str = "",
        direction: str = "all",
        start_time: str | float | None = None,
        end_time: str | float | None = None,
        link_id: int = 0,
        user_id: int = 0,
        root_comment_id: int = 0,
        source: str = "",
        status: str = "",
        bot_kind: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        self._require_enabled()
        direction = str(direction or "all").strip().lower()
        if direction not in {"all", "received", "bot"}:
            raise ValueError("direction 必须是 all、received 或 bot。")
        start_at, end_at = _time_range(start_time, end_time)
        filters = {
            "keyword": str(keyword or "").strip(),
            "direction": direction,
            "start_at": start_at,
            "end_at": end_at,
            "link_id": _as_int(link_id),
            "user_id": _as_int(user_id),
            "root_comment_id": _as_int(root_comment_id),
            "source": str(source or "").strip(),
            "status": str(status or "").strip(),
            "bot_kind": str(bot_kind or "").strip(),
            "limit": max(1, min(self.query_max_results, int(limit or 20))),
            "offset": max(0, int(offset or 0)),
        }
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._search_sync, filters)

    async def insight_records(
        self,
        *,
        start_time: str | float | None = None,
        end_time: str | float | None = None,
        link_id: int = 0,
        user_id: int = 0,
        source: str = "",
        status: str = "",
    ) -> list[dict[str, Any]]:
        self._require_enabled()
        start_at, end_at = _time_range(start_time, end_time)
        filters = {
            "keyword": "",
            "start_at": start_at,
            "end_at": end_at,
            "link_id": _as_int(link_id),
            "user_id": _as_int(user_id),
            "root_comment_id": 0,
            "source": str(source or "").strip(),
            "status": str(status or "").strip(),
            "bot_kind": "",
        }
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._insight_records_sync, filters)

    async def semantic_cache(self, analysis_key: str) -> dict[str, dict[str, Any]]:
        self._require_enabled()
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(
                self._semantic_cache_sync,
                str(analysis_key or "").strip(),
            )

    async def save_semantic_cache(
        self,
        *,
        analysis_key: str,
        provider_id: str,
        records: Sequence[Mapping[str, Any]],
    ) -> None:
        self._require_enabled()
        if not records:
            return
        await self.initialize()
        async with self._lock:
            await asyncio.to_thread(
                self._save_semantic_cache_sync,
                str(analysis_key or "").strip(),
                str(provider_id or "").strip(),
                records,
            )

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ValueError("评论归档已关闭，请由管理员开启 analytics.enabled。")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize_sync(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS received_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    link_id INTEGER NOT NULL DEFAULT 0,
                    comment_id INTEGER NOT NULL DEFAULT 0,
                    root_comment_id INTEGER NOT NULL DEFAULT 0,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'received',
                    status_reason TEXT NOT NULL DEFAULT '',
                    seen_count INTEGER NOT NULL DEFAULT 0,
                    first_seen_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS received_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_id INTEGER NOT NULL,
                    observation_key TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message_id INTEGER NOT NULL DEFAULT 0,
                    observed_at REAL NOT NULL,
                    UNIQUE(received_id, observation_key),
                    FOREIGN KEY(received_id) REFERENCES received_comments(id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS bot_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT UNIQUE,
                    kind TEXT NOT NULL,
                    link_id INTEGER NOT NULL DEFAULT 0,
                    comment_id INTEGER NOT NULL DEFAULT 0,
                    root_comment_id INTEGER NOT NULL DEFAULT 0,
                    target_comment_id INTEGER NOT NULL DEFAULT 0,
                    target_user_id INTEGER NOT NULL DEFAULT 0,
                    source_message_id INTEGER NOT NULL DEFAULT 0,
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'sent',
                    status_reason TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_received_link
                    ON received_comments(link_id);
                CREATE INDEX IF NOT EXISTS idx_received_user
                    ON received_comments(user_id);
                CREATE INDEX IF NOT EXISTS idx_received_root
                    ON received_comments(root_comment_id);
                CREATE INDEX IF NOT EXISTS idx_received_status
                    ON received_comments(status);
                CREATE INDEX IF NOT EXISTS idx_observations_received
                    ON received_observations(received_id);
                CREATE INDEX IF NOT EXISTS idx_observations_time
                    ON received_observations(observed_at);
                CREATE INDEX IF NOT EXISTS idx_observations_source
                    ON received_observations(source);
                CREATE INDEX IF NOT EXISTS idx_bot_link
                    ON bot_comments(link_id);
                CREATE INDEX IF NOT EXISTS idx_bot_time
                    ON bot_comments(created_at);
                CREATE INDEX IF NOT EXISTS idx_bot_kind
                    ON bot_comments(kind);

                CREATE TABLE IF NOT EXISTS semantic_comment_cache (
                    analysis_key TEXT NOT NULL,
                    comment_key TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    matched INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT '',
                    provider_id TEXT NOT NULL DEFAULT '',
                    analyzed_at REAL NOT NULL,
                    PRIMARY KEY (analysis_key, comment_key)
                );

                CREATE INDEX IF NOT EXISTS idx_semantic_cache_time
                    ON semantic_comment_cache(analyzed_at);
                CREATE INDEX IF NOT EXISTS idx_semantic_cache_comment
                    ON semantic_comment_cache(comment_key);
                """
            )
            connection.execute("PRAGMA user_version = 2")
            self._cleanup(connection, time.time())
            connection.commit()
        finally:
            connection.close()

    def _record_received_sync(
        self,
        records: Sequence[tuple[Mention, str, str]],
    ) -> None:
        now = time.time()
        connection = self._connect()
        try:
            with connection:
                for mention, status, reason in records:
                    self._upsert_received(
                        connection,
                        mention,
                        str(status or "received").strip()[:64],
                        str(reason or "").strip()[:2_000],
                        now,
                    )
                self._cleanup(connection, now)
        finally:
            connection.close()

    def _upsert_received(
        self,
        connection: sqlite3.Connection,
        mention: Mention,
        status: str,
        reason: str,
        now: float,
    ) -> None:
        dedupe_key = _received_key(mention)
        row = connection.execute(
            "SELECT id FROM received_comments WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if row is None:
            cursor = connection.execute(
                """
                INSERT INTO received_comments (
                    dedupe_key, link_id, comment_id, root_comment_id, user_id,
                    content, status, status_reason, seen_count,
                    first_seen_at, last_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    dedupe_key,
                    mention.link_id,
                    mention.comment_id,
                    mention.root_comment_id,
                    mention.user_id,
                    mention.comment_text,
                    status,
                    reason,
                    now,
                    now,
                    now,
                ),
            )
            received_id = int(cursor.lastrowid)
        else:
            received_id = int(row["id"])
            connection.execute(
                """
                UPDATE received_comments
                SET link_id = CASE WHEN ? > 0 THEN ? ELSE link_id END,
                    comment_id = CASE WHEN ? > 0 THEN ? ELSE comment_id END,
                    root_comment_id = CASE WHEN ? > 0 THEN ? ELSE root_comment_id END,
                    user_id = CASE WHEN ? > 0 THEN ? ELSE user_id END,
                    content = CASE WHEN ? <> '' THEN ? ELSE content END,
                    status = ?, status_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    mention.link_id,
                    mention.link_id,
                    mention.comment_id,
                    mention.comment_id,
                    mention.root_comment_id,
                    mention.root_comment_id,
                    mention.user_id,
                    mention.user_id,
                    mention.comment_text,
                    mention.comment_text,
                    status,
                    reason,
                    now,
                    received_id,
                ),
            )

        observation_key = _observation_key(mention, dedupe_key)
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO received_observations (
                received_id, observation_key, source, message_id, observed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                received_id,
                observation_key,
                str(mention.source or "mention").strip()[:64],
                mention.message_id,
                now,
            ),
        )
        if cursor.rowcount:
            connection.execute(
                """
                UPDATE received_comments
                SET seen_count = seen_count + 1, last_seen_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, received_id),
            )

    def _record_bot_comment_sync(self, record: Mapping[str, Any]) -> None:
        now = time.time()
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO bot_comments (
                        event_key, kind, link_id, comment_id, root_comment_id,
                        target_comment_id, target_user_id, source_message_id,
                        content, status, status_reason, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_key) DO UPDATE SET
                        comment_id = CASE
                            WHEN excluded.comment_id > 0 THEN excluded.comment_id
                            ELSE bot_comments.comment_id
                        END,
                        content = excluded.content,
                        status = excluded.status,
                        status_reason = excluded.status_reason,
                        updated_at = excluded.updated_at
                    """,
                    (
                        record["event_key"],
                        record["kind"],
                        record["link_id"],
                        record["comment_id"],
                        record["root_comment_id"],
                        record["target_comment_id"],
                        record["target_user_id"],
                        record["source_message_id"],
                        record["content"],
                        record["status"],
                        record["reason"],
                        now,
                        now,
                    ),
                )
                self._cleanup(connection, now)
        finally:
            connection.close()

    def _cleanup(self, connection: sqlite3.Connection, now: float) -> None:
        if self.retention_days > 0:
            cutoff = now - self.retention_days * 86_400
            connection.execute(
                "DELETE FROM received_observations WHERE observed_at < ?",
                (cutoff,),
            )
            connection.execute(
                "DELETE FROM received_comments WHERE NOT EXISTS ("
                "SELECT 1 FROM received_observations ro WHERE ro.received_id = received_comments.id"
                ")"
            )
            connection.execute(
                "DELETE FROM bot_comments WHERE created_at < ?", (cutoff,)
            )

        connection.execute(
            """
            DELETE FROM received_observations
            WHERE id IN (
                SELECT id FROM received_observations
                ORDER BY observed_at DESC, id DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self.max_records,),
        )
        connection.execute(
            "DELETE FROM received_comments WHERE NOT EXISTS ("
            "SELECT 1 FROM received_observations ro WHERE ro.received_id = received_comments.id"
            ")"
        )
        connection.execute(
            """
            DELETE FROM received_comments
            WHERE id IN (
                SELECT id FROM received_comments
                ORDER BY last_seen_at DESC, id DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self.max_records,),
        )
        connection.execute(
            """
            DELETE FROM bot_comments
            WHERE id IN (
                SELECT id FROM bot_comments
                ORDER BY created_at DESC, id DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self.max_records,),
        )
        connection.execute(
            "DELETE FROM semantic_comment_cache WHERE comment_key NOT IN "
            "(SELECT dedupe_key FROM received_comments)"
        )
        connection.execute(
            """
            DELETE FROM semantic_comment_cache
            WHERE rowid IN (
                SELECT rowid FROM semantic_comment_cache
                ORDER BY analyzed_at DESC, rowid DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self.max_records * 5,),
        )

    def _overview_sync(self) -> dict[str, int | bool]:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM received_comments) AS received_comments,
                    (SELECT COUNT(*) FROM received_observations) AS received_observations,
                    (SELECT COUNT(*) FROM bot_comments) AS bot_comments,
                    (SELECT COUNT(*) FROM semantic_comment_cache) AS semantic_cache_records
                """
            ).fetchone()
            return {
                "enabled": True,
                "received_comments": int(row["received_comments"]),
                "received_observations": int(row["received_observations"]),
                "bot_comments": int(row["bot_comments"]),
                "semantic_cache_records": int(row["semantic_cache_records"]),
            }
        finally:
            connection.close()

    def _own_post_reply_counts_sync(self) -> dict[int, int]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT bc.link_id, COUNT(*) AS reply_count
                FROM bot_comments bc
                WHERE bc.kind = 'auto_reply'
                  AND bc.status IN ('sent', 'uncertain')
                  AND bc.link_id > 0
                  AND bc.target_comment_id > 0
                  AND EXISTS (
                      SELECT 1
                      FROM received_comments rc
                      JOIN received_observations ro
                        ON ro.received_id = rc.id
                      WHERE rc.link_id = bc.link_id
                        AND rc.comment_id = bc.target_comment_id
                        AND ro.source = 'own_post_comment'
                  )
                GROUP BY bc.link_id
                """
            ).fetchall()
            return {
                int(row["link_id"]): int(row["reply_count"])
                for row in rows
                if int(row["link_id"] or 0) > 0
            }
        finally:
            connection.close()

    def _statistics_sync(self, filters: Mapping[str, Any]) -> dict[str, Any]:
        connection = self._connect()
        try:
            received = self._received_rows(connection, filters)
            bot = self._bot_rows(connection, filters)
            needle = str(filters["keyword"]).casefold()
            if needle:
                received = [
                    row for row in received if needle in str(row["content"]).casefold()
                ]
                bot = [row for row in bot if needle in str(row["content"]).casefold()]

            exact = (
                sum(
                    str(row["content"]).strip().casefold() == needle for row in received
                )
                if needle
                else 0
            )
            raw_count = sum(int(row["observation_count"]) for row in received)
            unique_count = len(received)
            source_counts: Counter[str] = Counter()
            for row in received:
                source_counts.update(_split_group(row["sources"]))

            received_statuses = Counter(str(row["status"]) for row in received)
            bot_statuses = Counter(str(row["status"]) for row in bot)
            bot_kinds = Counter(str(row["kind"]) for row in bot)
            root_keys = {
                (
                    int(row["link_id"]),
                    int(row["root_comment_id"] or row["comment_id"]),
                )
                for row in received
                if int(row["root_comment_id"] or row["comment_id"]) > 0
            }
            all_times = [
                float(row["filtered_first_seen_at"])
                for row in received
                if row["filtered_first_seen_at"] is not None
            ] + [float(row["created_at"]) for row in bot]
            all_last_times = [
                float(row["filtered_last_seen_at"])
                for row in received
                if row["filtered_last_seen_at"] is not None
            ] + [float(row["updated_at"]) for row in bot]

            return {
                "filters": _public_filters(filters),
                "received": {
                    "raw_observations": raw_count,
                    "unique_comments": unique_count,
                    "duplicate_observations": max(0, raw_count - unique_count),
                    "keyword_matches": unique_count if needle else None,
                    "exact_text_matches": exact if needle else None,
                    "text_variant_matches": unique_count - exact if needle else None,
                    "unique_users": len(
                        {
                            int(row["user_id"])
                            for row in received
                            if int(row["user_id"]) > 0
                        }
                    ),
                    "unique_posts": len(
                        {
                            int(row["link_id"])
                            for row in received
                            if int(row["link_id"]) > 0
                        }
                    ),
                    "unique_root_threads": len(root_keys),
                    "source_unique_comment_counts": dict(sorted(source_counts.items())),
                    "status_counts": dict(sorted(received_statuses.items())),
                },
                "bot": {
                    "comment_records": len(bot),
                    "confirmed_sent": bot_statuses.get("sent", 0),
                    "delivery_uncertain": bot_statuses.get("uncertain", 0),
                    "kind_counts": dict(sorted(bot_kinds.items())),
                    "status_counts": dict(sorted(bot_statuses.items())),
                },
                "range": {
                    "first_record_at": _iso_time(min(all_times)) if all_times else None,
                    "last_record_at": _iso_time(max(all_last_times))
                    if all_last_times
                    else None,
                },
                "counting_note": (
                    "received 统计外部用户评论；bot 单独统计本账号发出的评论，不混入 received。"
                    "raw_observations 是平台通知原始观察数，unique_comments 按帖子 ID + 评论 ID 去重。"
                    "source 只筛选 received，bot_kind 只筛选 bot；bot 的 uncertain 记录不等同于确认发布。"
                ),
            }
        finally:
            connection.close()

    def _search_sync(self, filters: Mapping[str, Any]) -> dict[str, Any]:
        connection = self._connect()
        try:
            records: list[dict[str, Any]] = []
            needle = str(filters["keyword"]).casefold()
            if filters["direction"] in {"all", "received"}:
                for row in self._received_rows(connection, filters):
                    content = str(row["content"])
                    if needle and needle not in content.casefold():
                        continue
                    records.append(
                        {
                            "direction": "received",
                            "sources": _split_group(row["sources"]),
                            "message_ids": [
                                _as_int(value)
                                for value in _split_group(row["message_ids"])
                            ],
                            "link_id": int(row["link_id"]),
                            "comment_id": int(row["comment_id"]),
                            "root_comment_id": int(row["root_comment_id"]),
                            "user_id": int(row["user_id"]),
                            "content": content,
                            "status": str(row["status"]),
                            "status_reason": str(row["status_reason"]),
                            "seen_count": int(row["observation_count"]),
                            "total_seen_count": int(row["seen_count"]),
                            "first_seen_at": _iso_time(row["filtered_first_seen_at"]),
                            "last_seen_at": _iso_time(row["filtered_last_seen_at"]),
                            "_sort_at": float(row["filtered_last_seen_at"]),
                            "_sort_id": int(row["id"]),
                        }
                    )
            if filters["direction"] in {"all", "bot"}:
                for row in self._bot_rows(connection, filters):
                    content = str(row["content"])
                    if needle and needle not in content.casefold():
                        continue
                    records.append(
                        {
                            "direction": "bot",
                            "kind": str(row["kind"]),
                            "link_id": int(row["link_id"]),
                            "comment_id": int(row["comment_id"]),
                            "root_comment_id": int(row["root_comment_id"]),
                            "target_comment_id": int(row["target_comment_id"]),
                            "target_user_id": int(row["target_user_id"]),
                            "source_message_id": int(row["source_message_id"]),
                            "content": content,
                            "status": str(row["status"]),
                            "status_reason": str(row["status_reason"]),
                            "created_at": _iso_time(row["created_at"]),
                            "updated_at": _iso_time(row["updated_at"]),
                            "_sort_at": float(row["updated_at"]),
                            "_sort_id": int(row["id"]),
                        }
                    )

            matched_count = len(records)
            records.sort(
                key=lambda item: (float(item["_sort_at"]), int(item["_sort_id"])),
                reverse=True,
            )
            offset = int(filters["offset"])
            limit = int(filters["limit"])
            records = records[offset : offset + limit]
            for record in records:
                record.pop("_sort_at", None)
                record.pop("_sort_id", None)
            return {
                "filters": _public_filters(filters),
                "matched_count": matched_count,
                "returned_count": len(records),
                "limit": limit,
                "offset": offset,
                "records": records,
                "counting_note": "received 与 bot 分开标记；received 的 seen_count 是当前筛选范围内的平台观察数。",
            }
        finally:
            connection.close()

    def _insight_records_sync(
        self,
        filters: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            records = [
                {
                    "comment_key": str(row["dedupe_key"]),
                    "link_id": int(row["link_id"]),
                    "comment_id": int(row["comment_id"]),
                    "root_comment_id": int(row["root_comment_id"]),
                    "user_id": int(row["user_id"]),
                    "content": str(row["content"]),
                    "status": str(row["status"]),
                    "sources": _split_group(row["sources"]),
                    "seen_count": int(row["observation_count"]),
                    "first_seen_at": _iso_time(row["filtered_first_seen_at"]),
                    "last_seen_at": _iso_time(row["filtered_last_seen_at"]),
                    "_sort_at": float(row["filtered_last_seen_at"] or 0.0),
                }
                for row in self._received_rows(connection, filters)
            ]
            records.sort(key=lambda item: float(item["_sort_at"]), reverse=True)
            for record in records:
                record.pop("_sort_at", None)
            return records
        finally:
            connection.close()

    def _semantic_cache_sync(self, analysis_key: str) -> dict[str, dict[str, Any]]:
        if not analysis_key:
            return {}
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM semantic_comment_cache WHERE analysis_key = ?",
                (analysis_key,),
            ).fetchall()
            return {
                str(row["comment_key"]): {
                    "content_hash": str(row["content_hash"]),
                    "matched": bool(row["matched"]),
                    "confidence": float(row["confidence"]),
                    "reason": str(row["reason"]),
                    "provider_id": str(row["provider_id"]),
                    "analyzed_at": _iso_time(row["analyzed_at"]),
                }
                for row in rows
            }
        finally:
            connection.close()

    def _save_semantic_cache_sync(
        self,
        analysis_key: str,
        provider_id: str,
        records: Sequence[Mapping[str, Any]],
    ) -> None:
        if not analysis_key or not records:
            return
        now = time.time()
        connection = self._connect()
        try:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO semantic_comment_cache (
                        analysis_key, comment_key, content_hash, matched,
                        confidence, reason, provider_id, analyzed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(analysis_key, comment_key) DO UPDATE SET
                        content_hash = excluded.content_hash,
                        matched = excluded.matched,
                        confidence = excluded.confidence,
                        reason = excluded.reason,
                        provider_id = excluded.provider_id,
                        analyzed_at = excluded.analyzed_at
                    """,
                    [
                        (
                            analysis_key,
                            str(record.get("comment_key") or ""),
                            str(record.get("content_hash") or ""),
                            1 if bool(record.get("matched")) else 0,
                            float(record.get("confidence") or 0.0),
                            str(record.get("reason") or "")[:500],
                            provider_id,
                            now,
                        )
                        for record in records
                        if str(record.get("comment_key") or "")
                    ],
                )
                self._cleanup(connection, now)
        finally:
            connection.close()

    @staticmethod
    def _received_rows(
        connection: sqlite3.Connection,
        filters: Mapping[str, Any],
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[Any] = []
        if filters.get("link_id"):
            clauses.append("rc.link_id = ?")
            params.append(filters["link_id"])
        if filters.get("user_id"):
            clauses.append("rc.user_id = ?")
            params.append(filters["user_id"])
        if filters.get("root_comment_id"):
            clauses.append("rc.root_comment_id = ?")
            params.append(filters["root_comment_id"])
        if filters.get("status"):
            clauses.append("rc.status = ?")
            params.append(filters["status"])
        if filters.get("source"):
            clauses.append("ro.source = ?")
            params.append(filters["source"])
        if filters.get("start_at") is not None:
            clauses.append("ro.observed_at >= ?")
            params.append(filters["start_at"])
        if filters.get("end_at") is not None:
            clauses.append("ro.observed_at <= ?")
            params.append(filters["end_at"])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return connection.execute(
            """
            SELECT rc.*,
                   COUNT(ro.id) AS observation_count,
                   GROUP_CONCAT(DISTINCT ro.source) AS sources,
                   GROUP_CONCAT(DISTINCT ro.message_id) AS message_ids,
                   MIN(ro.observed_at) AS filtered_first_seen_at,
                   MAX(ro.observed_at) AS filtered_last_seen_at
            FROM received_comments rc
            JOIN received_observations ro ON ro.received_id = rc.id
            """
            + where
            + " GROUP BY rc.id",
            params,
        ).fetchall()

    @staticmethod
    def _bot_rows(
        connection: sqlite3.Connection,
        filters: Mapping[str, Any],
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[Any] = []
        if filters.get("link_id"):
            clauses.append("link_id = ?")
            params.append(filters["link_id"])
        if filters.get("user_id"):
            clauses.append("target_user_id = ?")
            params.append(filters["user_id"])
        if filters.get("root_comment_id"):
            clauses.append("root_comment_id = ?")
            params.append(filters["root_comment_id"])
        if filters.get("status"):
            clauses.append("status = ?")
            params.append(filters["status"])
        if filters.get("bot_kind"):
            clauses.append("kind = ?")
            params.append(filters["bot_kind"])
        if filters.get("start_at") is not None:
            clauses.append("created_at >= ?")
            params.append(filters["start_at"])
        if filters.get("end_at") is not None:
            clauses.append("created_at <= ?")
            params.append(filters["end_at"])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return connection.execute(
            "SELECT * FROM bot_comments" + where, params
        ).fetchall()


def extract_comment_id(value: Any) -> int:
    if isinstance(value, Mapping):
        for key in ("comment_id", "commentid", "commentId", "comment_a_id"):
            candidate = _as_int(value.get(key))
            if candidate > 0:
                return candidate
        for child in value.values():
            candidate = extract_comment_id(child)
            if candidate > 0:
                return candidate
    elif isinstance(value, (list, tuple)):
        for child in value:
            candidate = extract_comment_id(child)
            if candidate > 0:
                return candidate
    return 0


def _received_key(mention: Mention) -> str:
    if mention.link_id > 0 and mention.comment_id > 0:
        return f"comment:{mention.link_id}:{mention.comment_id}"
    if mention.message_id > 0:
        return f"message:{mention.source}:{mention.message_id}"
    raw = json.dumps(mention.to_dict(), ensure_ascii=False, sort_keys=True)
    return "fallback:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _observation_key(mention: Mention, dedupe_key: str) -> str:
    if mention.message_id > 0:
        return f"{mention.source}:{mention.message_id}"
    return f"{mention.source}:{dedupe_key}"


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _time_range(
    start_time: str | float | None,
    end_time: str | float | None,
) -> tuple[float | None, float | None]:
    start_at = _parse_time(start_time, "start_time")
    end_at = _parse_time(end_time, "end_time")
    if start_at is not None and end_at is not None and start_at > end_at:
        raise ValueError("start_time 不能晚于 end_time。")
    return start_at, end_at


def _parse_time(value: str | float | None, field: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"{field} 必须是 Unix 秒时间戳或 ISO 8601 时间，例如 2026-07-26T00:00:00+08:00。"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _iso_time(value: Any) -> str | None:
    if value is None:
        return None
    return (
        datetime.fromtimestamp(float(value), tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _split_group(value: Any) -> list[str]:
    return [item for item in str(value or "").split(",") if item]


def _public_filters(filters: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (
            _iso_time(value)
            if key in {"start_at", "end_at"} and value is not None
            else value
        )
        for key, value in filters.items()
        if key != "limit" or value is not None
    }
