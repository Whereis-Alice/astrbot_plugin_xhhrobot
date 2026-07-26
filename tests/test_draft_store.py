from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
