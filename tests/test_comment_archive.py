from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from astrbot_plugin_xhhrobot.comment_archive import CommentArchive, extract_comment_id
from astrbot_plugin_xhhrobot.models import Mention


class CommentArchiveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.archive = CommentArchive(
            Path(self.temp_dir.name) / "comments.sqlite3",
            retention_days=0,
            max_records=10_000,
            query_max_results=3,
        )
        await self.archive.initialize()

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def mention(
        message_id: int,
        comment_id: int,
        *,
        text: str,
        link_id: int = 10,
        root_id: int | None = None,
        user_id: int = 1,
        source: str = "mention",
    ) -> Mention:
        return Mention(
            message_id=message_id,
            comment_id=comment_id,
            root_comment_id=root_id or comment_id,
            link_id=link_id,
            user_id=user_id,
            comment_text=text,
            source=source,
        )

    async def test_deduplicates_comments_but_preserves_raw_observations(self) -> None:
        duplicate_a = self.mention(1, 100, text="转人妻", root_id=100)
        duplicate_b = self.mention(2, 100, text="转人妻", root_id=100)
        exact = self.mention(3, 200, text="转人妻", root_id=200, user_id=2)
        variant = self.mention(
            4,
            300,
            text="@ATRI 转人妻[cube_喜欢]",
            link_id=20,
            root_id=300,
        )
        unrelated = self.mention(5, 400, text="其他评论", link_id=20)

        await self.archive.record_received(
            [
                (duplicate_a, "queued", ""),
                (duplicate_b, "queued", ""),
                (exact, "replied", ""),
                (variant, "ignored", ""),
                (unrelated, "queued", ""),
            ]
        )
        await self.archive.update_received_status(duplicate_a, "replied")
        await self.archive.record_bot_comment(
            kind="auto_reply",
            content="转人妻，我看到了",
            link_id=10,
            target_comment_id=100,
            event_key="auto_reply:10:100",
        )
        await self.archive.record_bot_comment(
            kind="llm_tool",
            content="转人妻",
            link_id=20,
        )

        stats = await self.archive.statistics(keyword="转人妻")

        self.assertEqual(stats["received"]["raw_observations"], 4)
        self.assertEqual(stats["received"]["unique_comments"], 3)
        self.assertEqual(stats["received"]["duplicate_observations"], 1)
        self.assertEqual(stats["received"]["exact_text_matches"], 2)
        self.assertEqual(stats["received"]["text_variant_matches"], 1)
        self.assertEqual(stats["received"]["unique_users"], 2)
        self.assertEqual(stats["received"]["unique_posts"], 2)
        self.assertEqual(stats["received"]["unique_root_threads"], 3)
        self.assertEqual(stats["bot"]["comment_records"], 2)
        self.assertEqual(stats["bot"]["confirmed_sent"], 2)
        self.assertEqual(stats["bot"]["delivery_uncertain"], 0)
        self.assertEqual(stats["bot"]["kind_counts"]["auto_reply"], 1)
        self.assertEqual(stats["bot"]["kind_counts"]["llm_tool"], 1)

        overview = await self.archive.overview()
        self.assertEqual(overview["received_observations"], 5)
        self.assertEqual(overview["received_comments"], 4)
        self.assertEqual(overview["bot_comments"], 2)

    async def test_source_filter_counts_only_matching_observations(self) -> None:
        mention = self.mention(10, 500, text="同一条评论")
        comment_stream = self.mention(
            11,
            500,
            text="同一条评论",
            source="own_post_comment",
        )
        await self.archive.record_received(
            [(mention, "queued", ""), (comment_stream, "queued", "")]
        )

        all_stats = await self.archive.statistics()
        mention_stats = await self.archive.statistics(source="mention")
        comment_stats = await self.archive.statistics(source="own_post_comment")

        self.assertEqual(all_stats["received"]["raw_observations"], 2)
        self.assertEqual(all_stats["received"]["unique_comments"], 1)
        self.assertEqual(mention_stats["received"]["raw_observations"], 1)
        self.assertEqual(comment_stats["received"]["raw_observations"], 1)

    async def test_search_returns_ids_status_and_enforces_query_limit(self) -> None:
        records = [
            (
                self.mention(
                    message_id=index,
                    comment_id=1_000 + index,
                    text=f"评论 {index}",
                    link_id=99,
                    user_id=77,
                    source="own_post_comment",
                ),
                "queued",
                "",
            )
            for index in range(1, 6)
        ]
        await self.archive.record_received(records)

        result = await self.archive.search(
            direction="received",
            link_id=99,
            source="own_post_comment",
            limit=99,
        )

        self.assertEqual(result["matched_count"], 5)
        self.assertEqual(result["returned_count"], 3)
        self.assertEqual(result["records"][0]["comment_id"], 1005)
        self.assertEqual(result["records"][0]["message_ids"], [5])
        self.assertEqual(result["records"][0]["status"], "queued")

        second_page = await self.archive.search(
            direction="received",
            link_id=99,
            source="own_post_comment",
            limit=2,
            offset=2,
        )
        self.assertEqual(second_page["matched_count"], 5)
        self.assertEqual(second_page["returned_count"], 2)
        self.assertEqual(second_page["offset"], 2)
        self.assertEqual(second_page["records"][0]["comment_id"], 1003)
        self.assertEqual(second_page["records"][1]["comment_id"], 1002)

    async def test_bot_event_key_updates_uncertain_record_without_duplication(
        self,
    ) -> None:
        await self.archive.record_bot_comment(
            kind="auto_browse",
            content="准备发送的评论",
            link_id=123,
            status="uncertain",
            event_key="auto_browse:123",
        )
        await self.archive.record_bot_comment(
            kind="auto_browse",
            content="准备发送的评论",
            link_id=123,
            status="sent",
            comment_id=456,
            event_key="auto_browse:123",
        )

        result = await self.archive.search(direction="bot")

        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["records"][0]["status"], "sent")
        self.assertEqual(result["records"][0]["comment_id"], 456)

    async def test_record_cap_limits_observations_and_removes_orphans(self) -> None:
        capped = CommentArchive(
            Path(self.temp_dir.name) / "capped.sqlite3",
            retention_days=0,
            max_records=1_000,
            query_max_results=5,
        )
        await capped.initialize()
        await capped.record_received(
            [
                (
                    self.mention(
                        message_id=index + 1,
                        comment_id=10_000 + index,
                        text=f"容量评论 {index}",
                    ),
                    "queued",
                    "",
                )
                for index in range(1_005)
            ]
        )

        overview = await capped.overview()
        deleted = await capped.search(keyword="容量评论 0", direction="received")
        retained = await capped.search(keyword="容量评论 1004", direction="received")

        self.assertEqual(overview["received_observations"], 1_000)
        self.assertEqual(overview["received_comments"], 1_000)
        self.assertEqual(deleted["matched_count"], 0)
        self.assertEqual(retained["matched_count"], 1)

    async def test_invalid_time_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "start_time"):
            await self.archive.statistics(
                start_time="2026-07-27T00:00:00+08:00",
                end_time="2026-07-26T00:00:00+08:00",
            )

    def test_extract_comment_id_reads_nested_response(self) -> None:
        self.assertEqual(
            extract_comment_id({"status": "ok", "result": {"comment_id": "987"}}),
            987,
        )


if __name__ == "__main__":
    unittest.main()
