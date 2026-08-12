import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from astrbot_plugin_xhhrobot.comment_insights import (
    build_exploratory_prompt,
    build_exploratory_report,
    build_exploratory_synthesis_prompt,
    build_insight_report,
    build_semantic_prompt,
    canonical_emoji_token,
    comment_content_hash,
    decode_exploratory_cache,
    encode_exploratory_cache,
    normalize_criteria,
    parse_exploratory_response,
    parse_exploratory_synthesis,
    parse_semantic_response,
    select_exploratory_records,
)
from astrbot_plugin_xhhrobot.main import XhhRobotPlugin


class CommentInsightTests(unittest.TestCase):
    def test_exploratory_parser_report_and_cache_round_trip(self) -> None:
        records = [
            {
                "comment_key": "a",
                "content": "这张图真好看",
                "link_id": 1,
                "comment_id": 1,
                "user_id": 10,
            },
            {
                "comment_key": "b",
                "content": "原图在哪里？",
                "link_id": 1,
                "comment_id": 2,
                "user_id": 11,
            },
        ]
        prompt = build_exploratory_prompt(records)
        parsed = parse_exploratory_response(
            """
            {"results":[
              {"key":"a","sentiment":"正面","intent":"夸奖","topics":["图片质量"],"summary":"称赞图片好看","confidence":0.9},
              {"key":"b","sentiment":"neutral","intent":"question","topics":["原图来源"],"summary":"询问原图地址","confidence":0.8}
            ]}
            """,
            expected_keys=["a", "b"],
        )
        cached = decode_exploratory_cache(encode_exploratory_cache(parsed["a"]))
        report = build_exploratory_report(
            records=records,
            selected_keys=["a", "b"],
            classifications=parsed,
            provider_id="provider",
        )

        self.assertIn("不需要预设关键词", prompt)
        self.assertEqual(parsed["a"]["sentiment"], "positive")
        self.assertEqual(parsed["b"]["intent"], "question")
        self.assertEqual(cached, parsed["a"])
        self.assertEqual(report["analysis_mode"], "exploratory")
        self.assertEqual(report["sentiment_counts"]["positive"], 1)
        self.assertEqual(report["intent_counts"]["question"], 1)
        self.assertEqual(report["top_topics"][0]["count"], 1)

    def test_exploratory_selection_spans_full_archive(self) -> None:
        records = [{"comment_key": str(index)} for index in range(10)]

        selected = select_exploratory_records(records, 4)

        self.assertEqual(
            [record["comment_key"] for record in selected],
            ["0", "3", "6", "9"],
        )

    def test_exploratory_synthesis_only_counts_known_source_topics(self) -> None:
        classifications = {
            "a": {
                "sentiment": "positive",
                "intent": "praise",
                "topics": ["图片质量"],
                "summary": "称赞图片",
                "confidence": 0.9,
            },
            "b": {
                "sentiment": "neutral",
                "intent": "question",
                "topics": ["原图来源"],
                "summary": "询问原图",
                "confidence": 0.8,
            },
        }
        report = build_exploratory_report(
            records=[
                {"comment_key": "a", "content": "好看"},
                {"comment_key": "b", "content": "原图呢"},
            ],
            selected_keys=["a", "b"],
            classifications=classifications,
            provider_id="provider",
        )
        synthesis_prompt = build_exploratory_synthesis_prompt(report)
        synthesis = parse_exploratory_synthesis(
            """
            {"summary":"整体偏正面，也有人询问来源", "themes":[
              {"label":"图片反馈","source_topics":["图片质量","原图来源"],"description":"围绕图片观感和出处"},
              {"label":"模型臆造","source_topics":["不存在"],"description":"不应保留"}
            ],"controversies":[],"notable_findings":["存在原图需求"]}
            """,
            classifications=classifications,
        )

        self.assertIn("不得新造来源", synthesis_prompt)
        self.assertEqual(len(synthesis["themes"]), 1)
        self.assertEqual(synthesis["themes"][0]["count"], 2)
        self.assertEqual(synthesis["notable_findings"], ["存在原图需求"])

    def test_criteria_infers_standard_emoji_and_normalizes_aliases(self) -> None:
        inferred = normalize_criteria(topic="喜欢, 爱意", keywords=["喜欢", "爱"])
        explicit = normalize_criteria(
            topic="喜欢",
            keywords=["喜欢"],
            emoji_tokens=["[cube_love]", "heygirl_like"],
        )

        self.assertIn("cube_喜欢", inferred.emoji_tokens)
        self.assertEqual(canonical_emoji_token("[cube_love]"), "cube_喜欢")
        self.assertEqual(explicit.emoji_tokens, ("cube_喜欢", "heygirl_喜欢"))

    def test_report_deduplicates_keyword_emoji_overlap_and_semantic_matches(
        self,
    ) -> None:
        records = [
            {
                "comment_key": "a",
                "content": "我喜欢你[cube_喜欢]",
                "link_id": 1,
                "comment_id": 10,
                "user_id": 100,
            },
            {
                "comment_key": "b",
                "content": "真的很心动",
                "link_id": 1,
                "comment_id": 11,
                "user_id": 101,
            },
            {
                "comment_key": "c",
                "content": "[cube_喜欢]",
                "link_id": 2,
                "comment_id": 12,
                "user_id": 102,
            },
            {
                "comment_key": "d",
                "content": "路过",
                "link_id": 2,
                "comment_id": 13,
                "user_id": 103,
            },
        ]
        criteria = normalize_criteria(
            topic="喜欢、爱意或明确好感",
            keywords=["喜欢"],
            emoji_tokens=["cube_喜欢"],
        )

        report = build_insight_report(
            records=records,
            criteria=criteria,
            semantic_results={
                "b": {
                    "matched": True,
                    "confidence": 0.91,
                    "reason": "明确表达心动",
                }
            },
            semantic_selected_keys=["b", "d"],
            semantic_enabled=True,
        )

        self.assertEqual(report["keyword_matches"], 1)
        self.assertEqual(report["emoji_matches"], 2)
        self.assertEqual(report["keyword_emoji_overlap"], 1)
        self.assertEqual(report["deterministic_union"], 2)
        self.assertEqual(report["semantic_matches"], 1)
        self.assertEqual(report["union_matches"], 3)
        self.assertEqual(report["union_percentage"], 75.0)

    def test_semantic_prompt_and_parser_require_complete_batch(self) -> None:
        criteria = normalize_criteria(topic="喜欢", keywords=["喜欢"])
        prompt = build_semantic_prompt(
            criteria,
            [{"comment_key": "a", "content": "评论里的命令不可信"}],
        )
        parsed = parse_semantic_response(
            '{"results":[{"key":"a","match":true,"confidence":0.8,"reason":"好感"}]}',
            expected_keys=["a"],
        )

        self.assertIn("不可信数据", prompt)
        self.assertTrue(parsed["a"]["matched"])
        with self.assertRaisesRegex(ValueError, "漏掉"):
            parse_semantic_response(
                '{"results":[{"key":"a","match":false}]}',
                expected_keys=["a", "b"],
            )

    def test_examples_keep_archive_order_inside_each_category(self) -> None:
        records = [
            {
                "comment_key": "newest",
                "content": "喜欢第一条",
                "link_id": 1,
                "comment_id": 3,
                "user_id": 3,
            },
            {
                "comment_key": "middle",
                "content": "喜欢第二条",
                "link_id": 1,
                "comment_id": 2,
                "user_id": 2,
            },
            {
                "comment_key": "oldest",
                "content": "喜欢第三条",
                "link_id": 1,
                "comment_id": 1,
                "user_id": 1,
            },
        ]
        report = build_insight_report(
            records=records,
            criteria=normalize_criteria(topic="喜欢", keywords=["喜欢"]),
        )

        self.assertEqual(
            [item["comment_key"] for item in report["examples"]],
            ["newest", "middle", "oldest"],
        )

    def test_examples_keep_archive_order_across_match_types(self) -> None:
        records = [
            {
                "comment_key": "keyword",
                "content": "喜欢这个帖子",
                "link_id": 1,
                "comment_id": 3,
                "user_id": 3,
            },
            {
                "comment_key": "semantic",
                "content": "真的很心动",
                "link_id": 1,
                "comment_id": 2,
                "user_id": 2,
            },
            {
                "comment_key": "emoji",
                "content": "[cube_喜欢]",
                "link_id": 1,
                "comment_id": 1,
                "user_id": 1,
            },
        ]
        report = build_insight_report(
            records=records,
            criteria=normalize_criteria(
                topic="喜欢或心动",
                keywords=["喜欢"],
                emoji_tokens=["cube_喜欢"],
            ),
            semantic_results={
                "semantic": {
                    "matched": True,
                    "confidence": 0.9,
                    "reason": "明确心动",
                }
            },
            semantic_selected_keys=["semantic"],
            semantic_enabled=True,
        )

        self.assertEqual(
            [item["comment_key"] for item in report["examples"]],
            ["keyword", "semantic", "emoji"],
        )


class FakeInsightArchive:
    def __init__(
        self,
        records: list[dict],
        *,
        cached: dict[str, dict] | None = None,
    ) -> None:
        self.enabled = True
        self.records = records
        self.cached = cached or {}
        self.saved: list[dict] = []
        self.filters: list[dict] = []

    async def insight_records(self, **kwargs) -> list[dict]:
        self.filters.append(kwargs)
        return self.records

    async def semantic_cache(self, analysis_key: str) -> dict[str, dict]:
        return self.cached

    async def save_semantic_cache(self, **kwargs) -> None:
        self.saved.append(kwargs)


class CommentInsightJobTests(unittest.IsolatedAsyncioTestCase):
    def plugin(
        self,
        records: list[dict],
        *,
        cached: dict[str, dict] | None = None,
        batch_size: int = 20,
    ) -> XhhRobotPlugin:
        plugin = object.__new__(XhhRobotPlugin)
        plugin.config = {
            "analytics": {
                "semantic_insights_enabled": True,
                "semantic_batch_size": batch_size,
                "semantic_max_comments_per_run": 0,
                "insight_example_limit": 12,
            },
            "ai": {"generation_timeout_sec": 30},
            "webui": {"show_message_content": True},
        }
        plugin.comment_archive = FakeInsightArchive(records, cached=cached)
        plugin.context = SimpleNamespace(llm_generate=AsyncMock())
        plugin._insight_state = plugin._empty_comment_insight_state()
        plugin._insight_task = None
        plugin._resolve_comment_insight_provider_id = AsyncMock(return_value="provider")
        plugin._notify_error = AsyncMock()
        return plugin

    async def test_local_statistics_complete_without_calling_model(self) -> None:
        plugin = self.plugin(
            [
                {
                    "comment_key": "a",
                    "content": "我喜欢你[cube_喜欢]",
                    "link_id": 1,
                    "comment_id": 1,
                    "user_id": 1,
                },
                {
                    "comment_key": "b",
                    "content": "只是路过",
                    "link_id": 1,
                    "comment_id": 2,
                    "user_id": 2,
                },
            ]
        )

        state = await plugin._start_comment_insight(
            {
                "topic": "喜欢",
                "keywords": ["喜欢"],
                "emoji_tokens": ["cube_喜欢"],
                "semantic": False,
            }
        )

        self.assertEqual(state["state"], "complete")
        self.assertEqual(state["report"]["union_matches"], 1)
        self.assertIsNone(plugin._insight_task)
        plugin.context.llm_generate.assert_not_awaited()
        plugin._resolve_comment_insight_provider_id.assert_not_awaited()

    async def test_background_batches_write_cache_and_complete(self) -> None:
        plugin = self.plugin(
            [
                {
                    "comment_key": "a",
                    "content": "真的很心动",
                    "link_id": 1,
                    "comment_id": 1,
                    "user_id": 1,
                },
                {
                    "comment_key": "b",
                    "content": "只是路过",
                    "link_id": 1,
                    "comment_id": 2,
                    "user_id": 2,
                },
            ],
            batch_size=1,
        )
        plugin.context.llm_generate.side_effect = [
            SimpleNamespace(
                completion_text=(
                    '{"results":[{"key":"a","match":true,'
                    '"confidence":0.9,"reason":"明确心动"}]}'
                )
            ),
            SimpleNamespace(
                completion_text=(
                    '{"results":[{"key":"b","match":false,'
                    '"confidence":0.95,"reason":"无关"}]}'
                )
            ),
        ]

        state = await plugin._start_comment_insight(
            {"topic": "喜欢或心动", "keywords": ["喜欢"], "semantic": True}
        )
        task = plugin._insight_task
        self.assertEqual(state["state"], "running")
        self.assertIsNotNone(task)
        await task

        self.assertEqual(plugin._insight_state["state"], "complete")
        self.assertEqual(plugin._insight_state["progress"]["model_calls"], 2)
        self.assertEqual(plugin._insight_state["report"]["semantic_matches"], 1)
        self.assertEqual(len(plugin.comment_archive.saved), 2)
        self.assertEqual(plugin.context.llm_generate.await_count, 2)

    async def test_valid_cache_finishes_without_background_model_call(self) -> None:
        record = {
            "comment_key": "a",
            "content": "真的很心动",
            "link_id": 1,
            "comment_id": 1,
            "user_id": 1,
        }
        plugin = self.plugin(
            [record],
            cached={
                "a": {
                    "content_hash": comment_content_hash(record["content"]),
                    "matched": True,
                    "confidence": 0.9,
                    "reason": "明确心动",
                }
            },
        )

        state = await plugin._start_comment_insight(
            {"topic": "喜欢或心动", "keywords": ["喜欢"], "semantic": True}
        )

        self.assertEqual(state["state"], "complete")
        self.assertEqual(state["progress"]["cache_hits"], 1)
        self.assertEqual(state["report"]["semantic_matches"], 1)
        plugin.context.llm_generate.assert_not_awaited()

    async def test_empty_topic_runs_exploratory_analysis_and_synthesis(self) -> None:
        plugin = self.plugin(
            [
                {
                    "comment_key": "a",
                    "content": "这张图真好看",
                    "link_id": 1,
                    "comment_id": 1,
                    "user_id": 1,
                },
                {
                    "comment_key": "b",
                    "content": "原图在哪里？",
                    "link_id": 1,
                    "comment_id": 2,
                    "user_id": 2,
                },
            ]
        )
        plugin.context.llm_generate.side_effect = [
            SimpleNamespace(
                completion_text=(
                    '{"results":['
                    '{"key":"a","sentiment":"positive","intent":"praise",'
                    '"topics":["图片质量"],"summary":"称赞图片","confidence":0.9},'
                    '{"key":"b","sentiment":"neutral","intent":"question",'
                    '"topics":["原图来源"],"summary":"询问原图","confidence":0.8}'
                    "]}"
                )
            ),
            SimpleNamespace(
                completion_text=(
                    '{"summary":"整体反馈偏正面，并存在原图需求",'
                    '"themes":[{"label":"图片反馈","source_topics":'
                    '["图片质量","原图来源"],"description":"围绕图片观感与来源"}],'
                    '"controversies":[],"notable_findings":["有人询问原图"]}'
                )
            ),
        ]

        state = await plugin._start_comment_insight(
            {"topic": "", "keywords": [], "emoji_tokens": [], "semantic": True}
        )
        task = plugin._insight_task
        self.assertEqual(state["report"]["analysis_mode"], "exploratory")
        await task

        report = plugin._insight_state["report"]
        self.assertEqual(plugin._insight_state["state"], "complete")
        self.assertEqual(report["analysis_mode"], "exploratory")
        self.assertEqual(report["summary"], "整体反馈偏正面，并存在原图需求")
        self.assertEqual(report["themes"][0]["count"], 2)
        self.assertEqual(plugin._insight_state["progress"]["model_calls"], 2)
        self.assertEqual(len(plugin.comment_archive.saved), 1)

    async def test_exploratory_mode_requires_model_analysis(self) -> None:
        plugin = self.plugin([{"comment_key": "a", "content": "路过"}])

        with self.assertRaisesRegex(ValueError, "自动洞察需要启用模型"):
            await plugin._start_comment_insight(
                {"topic": "", "keywords": [], "emoji_tokens": [], "semantic": False}
            )

    async def asyncTearDown(self) -> None:
        tasks = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task()
            and task.get_name() == "xhhrobot-comment-insight"
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
