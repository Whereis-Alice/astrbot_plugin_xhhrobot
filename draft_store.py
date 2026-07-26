from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any


class DraftStore:
    """Small SQLite-backed local draft box for LLM-authored posts."""

    def __init__(self, path: Path, *, max_records: int = 500) -> None:
        self.path = Path(path)
        self.max_records = max(10, int(max_records))
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._initialize_sync)
            self._initialized = True

    async def overview(self) -> dict[str, int]:
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._overview_sync)

    async def list(self, *, limit: int = 20) -> dict[str, Any]:
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(
                self._list_sync, max(1, min(100, int(limit)))
            )

    async def get(self, draft_id: str) -> dict[str, Any]:
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._get_sync, draft_id)

    async def save(
        self,
        *,
        draft_id: str = "",
        title: str | None = None,
        body: str | None = None,
        description: str | None = None,
        topic_ids: Sequence[str] | None = None,
        hashtags: Sequence[str] | None = None,
        image_urls: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        await self.initialize()
        values = {
            "title": title,
            "body": body,
            "description": description,
            "topic_ids": list(topic_ids) if topic_ids is not None else None,
            "hashtags": list(hashtags) if hashtags is not None else None,
            "image_urls": list(image_urls) if image_urls is not None else None,
        }
        async with self._lock:
            return await asyncio.to_thread(self._save_sync, draft_id, values)

    async def delete(self, draft_id: str) -> dict[str, Any]:
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(self._delete_sync, draft_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
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
                CREATE TABLE IF NOT EXISTS post_drafts (
                    draft_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    topic_ids TEXT NOT NULL DEFAULT '[]',
                    hashtags TEXT NOT NULL DEFAULT '[]',
                    image_urls TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_post_drafts_updated_at
                    ON post_drafts(updated_at DESC);
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _overview_sync(self) -> dict[str, int]:
        connection = self._connect()
        try:
            count = connection.execute("SELECT COUNT(*) FROM post_drafts").fetchone()[0]
            return {"total": int(count or 0)}
        finally:
            connection.close()

    def _list_sync(self, limit: int) -> dict[str, Any]:
        connection = self._connect()
        try:
            total = connection.execute("SELECT COUNT(*) FROM post_drafts").fetchone()[0]
            rows = connection.execute(
                """
                SELECT draft_id, title, body, topic_ids, hashtags, image_urls, created_at, updated_at
                FROM post_drafts
                ORDER BY updated_at DESC, draft_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return {
                "total": int(total or 0),
                "drafts": [self._summary_from_row(row) for row in rows],
            }
        finally:
            connection.close()

    def _get_sync(self, draft_id: str) -> dict[str, Any]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM post_drafts WHERE draft_id = ?", (draft_id,)
            ).fetchone()
            if row is None:
                raise ValueError("草稿不存在或已删除。")
            return {"draft": self._record_from_row(row)}
        finally:
            connection.close()

    def _save_sync(self, draft_id: str, values: dict[str, Any]) -> dict[str, Any]:
        connection = self._connect()
        try:
            draft_id = str(draft_id or "").strip()
            row = None
            if draft_id:
                row = connection.execute(
                    "SELECT * FROM post_drafts WHERE draft_id = ?", (draft_id,)
                ).fetchone()
            else:
                draft_id = self._new_draft_id(connection)

            record = (
                self._record_from_row(row)
                if row is not None
                else self._empty_record(draft_id)
            )
            for key, value in values.items():
                if value is not None:
                    record[key] = value
            if not (
                record["title"].strip()
                or record["body"].strip()
                or record["image_urls"]
            ):
                raise ValueError("草稿标题、正文和图片不能同时为空。")

            now = time.time()
            record["updated_at"] = now
            if row is None:
                record["created_at"] = now
                connection.execute(
                    """
                    INSERT INTO post_drafts (
                        draft_id, title, body, description, topic_ids, hashtags, image_urls,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._record_values(record),
                )
            else:
                connection.execute(
                    """
                    UPDATE post_drafts
                    SET title = ?, body = ?, description = ?, topic_ids = ?, hashtags = ?,
                        image_urls = ?, updated_at = ?
                    WHERE draft_id = ?
                    """,
                    (
                        record["title"],
                        record["body"],
                        record["description"],
                        json.dumps(
                            record["topic_ids"],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        json.dumps(
                            record["hashtags"],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        json.dumps(
                            record["image_urls"],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        record["updated_at"],
                        draft_id,
                    ),
                )
            self._prune_sync(connection)
            connection.commit()
            return {"created": row is None, "draft": record}
        finally:
            connection.close()

    def _delete_sync(self, draft_id: str) -> dict[str, Any]:
        connection = self._connect()
        try:
            result = connection.execute(
                "DELETE FROM post_drafts WHERE draft_id = ?", (draft_id,)
            )
            if result.rowcount <= 0:
                raise ValueError("草稿不存在或已删除。")
            connection.commit()
            return {"draft_id": draft_id, "deleted": True}
        finally:
            connection.close()

    def _prune_sync(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM post_drafts
            WHERE draft_id NOT IN (
                SELECT draft_id
                FROM post_drafts
                ORDER BY updated_at DESC, draft_id ASC
                LIMIT ?
            )
            """,
            (self.max_records,),
        )

    @staticmethod
    def _new_draft_id(connection: sqlite3.Connection) -> str:
        while True:
            draft_id = "draft_" + uuid.uuid4().hex[:16]
            row = connection.execute(
                "SELECT 1 FROM post_drafts WHERE draft_id = ?", (draft_id,)
            ).fetchone()
            if row is None:
                return draft_id

    @staticmethod
    def _empty_record(draft_id: str) -> dict[str, Any]:
        return {
            "draft_id": draft_id,
            "title": "",
            "body": "",
            "description": "",
            "topic_ids": [],
            "hashtags": [],
            "image_urls": [],
            "created_at": 0.0,
            "updated_at": 0.0,
        }

    @staticmethod
    def _record_values(record: dict[str, Any]) -> tuple[Any, ...]:
        return (
            record["draft_id"],
            record["title"],
            record["body"],
            record["description"],
            json.dumps(record["topic_ids"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(record["hashtags"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(record["image_urls"], ensure_ascii=False, separators=(",", ":")),
            record["created_at"],
            record["updated_at"],
        )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "draft_id": str(row["draft_id"]),
            "title": str(row["title"] or ""),
            "body": str(row["body"] or ""),
            "description": str(row["description"] or ""),
            "topic_ids": _json_list(row["topic_ids"]),
            "hashtags": _json_list(row["hashtags"]),
            "image_urls": _json_list(row["image_urls"]),
            "created_at": float(row["created_at"] or 0),
            "updated_at": float(row["updated_at"] or 0),
        }

    @staticmethod
    def _summary_from_row(row: sqlite3.Row) -> dict[str, Any]:
        body = str(row["body"] or "").strip().replace("\n", " ")
        image_urls = _json_list(row["image_urls"])
        return {
            "draft_id": str(row["draft_id"]),
            "title": str(row["title"] or ""),
            "body_preview": body[:160],
            "topic_ids": _json_list(row["topic_ids"]),
            "hashtags": _json_list(row["hashtags"]),
            "image_count": len(image_urls),
            "created_at": float(row["created_at"] or 0),
            "updated_at": float(row["updated_at"] or 0),
        }


def _json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]
