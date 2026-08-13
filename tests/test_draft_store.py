from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from astrbot_plugin_xhhrobot.draft_store import DraftStore


class DraftStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_list_get_update_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DraftStore(Path(temp_dir) / "post_drafts.sqlite3")
            created = await store.save(
                title="第一版标题",
                body="第一版正文\n第二行",
                description="摘要",
                topic_ids=["7214"],
                hashtags=["AstrBot"],
                image_urls=["https://example.com/image.png"],
                content_blocks=[
                    {"type": "html", "text": "<p><strong>重点</strong></p>"},
                    {"type": "image", "url": "https://example.com/image.png"},
                ],
            )
            draft_id = created["draft"]["draft_id"]
            summary = await store.list()
            fetched = await store.get(draft_id)
            updated = await store.save(draft_id=draft_id, title="第二版标题")
            overview = await store.overview()
            deleted = await store.delete(draft_id)

        self.assertTrue(created["created"])
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["drafts"][0]["body_preview"], "第一版正文 第二行")
        self.assertEqual(
            fetched["draft"]["image_urls"], ["https://example.com/image.png"]
        )
        self.assertEqual(
            fetched["draft"]["content_blocks"],
            [
                {"type": "html", "text": "<p><strong>重点</strong></p>"},
                {"type": "image", "url": "https://example.com/image.png"},
            ],
        )
        self.assertEqual(summary["drafts"][0]["content_block_count"], 2)
        self.assertFalse(updated["created"])
        self.assertEqual(updated["draft"]["title"], "第二版标题")
        self.assertEqual(updated["draft"]["body"], "第一版正文\n第二行")
        self.assertEqual(overview["total"], 1)
        self.assertTrue(deleted["deleted"])

    async def test_empty_draft_and_missing_draft_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DraftStore(Path(temp_dir) / "post_drafts.sqlite3")
            with self.assertRaisesRegex(ValueError, "不能同时为空"):
                await store.save(title="", body="")
            with self.assertRaisesRegex(ValueError, "不存在"):
                await store.get("draft_missing")

    async def test_existing_database_is_migrated_for_content_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "post_drafts.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE post_drafts (
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
                INSERT INTO post_drafts VALUES (
                    'draft_old', '旧草稿', '旧正文', '', '[]', '[]', '[]', 1, 1
                );
                """
            )
            connection.commit()
            connection.close()

            store = DraftStore(path)
            before = await store.get("draft_old")
            updated = await store.save(
                draft_id="draft_old",
                content_blocks=[{"type": "text", "text": "新的内容块"}],
            )

        self.assertEqual(before["draft"]["content_blocks"], [])
        self.assertEqual(
            updated["draft"]["content_blocks"],
            [{"type": "text", "text": "新的内容块"}],
        )


if __name__ == "__main__":
    unittest.main()
