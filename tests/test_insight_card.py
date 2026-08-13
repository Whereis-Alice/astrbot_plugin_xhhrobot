from __future__ import annotations

import json
import unittest

from jinja2 import Environment

from astrbot_plugin_xhhrobot.insight_card import (
    INSIGHT_CARD_TEMPLATE,
    THEMES,
    InsightCardRenderer,
    available_insight_card_themes,
    build_insight_card_payload,
    normalize_insight_card_resolution,
    normalize_insight_card_theme,
)


class FakeRendererPlugin:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def html_render(
        self,
        template: str,
        data: dict,
        *,
        return_url: bool,
        options: dict,
    ) -> str:
        self.calls.append(
            {
                "template": template,
                "data": data,
                "return_url": return_url,
                "options": options,
            }
        )
        return "https://render.example/card.png"


def exploratory_snapshot() -> dict:
    return {
        "state": "complete",
        "job_id": "job-123",
        "filters": {"link_id": 187917301, "source": "own_post_comment"},
        "report": {
            "analysis_mode": "exploratory",
            "provider_id": "provider/model",
            "total_comments": 800,
            "selected_comments": 500,
            "analyzed_comments": 500,
            "coverage_percent": 62.5,
            "unique_users": 612,
            "unique_posts": 1,
            "sentiment_counts": {
                "positive": 300,
                "neutral": 130,
                "negative": 50,
                "mixed": 20,
            },
            "sentiment_percentages": {
                "positive": 60,
                "neutral": 26,
                "negative": 10,
                "mixed": 4,
            },
            "intent_counts": {"praise": 230, "question": 90, "joke": 80},
            "summary": "整体偏正面，原图需求集中。",
            "themes": [
                {
                    "label": "角色反馈",
                    "count": 260,
                    "percentage": 52,
                    "description": "多数评论喜欢角色表现。",
                }
            ],
            "top_questions": [
                {"label": "原图来源", "count": 70, "percentage": 14}
            ],
            "top_suggestions": [
                {"label": "发布原图", "count": 34, "percentage": 6.8}
            ],
            "controversies": ["少量用户认为压缩明显"],
            "notable_findings": ["原图请求是最集中的需求"],
            "evidence": {
                "scope": {
                    "archived": 800,
                    "selected": 500,
                    "analyzed": 500,
                    "coverage_percent": 62.5,
                },
                "topics": [
                    {
                        "label": "角色反馈",
                        "count": 260,
                        "percentage": 52,
                        "description": "多数评论喜欢角色表现。",
                    }
                ],
            },
            "examples": [
                {
                    "content": "<script>alert('x')</script> 这张很好看",
                    "link_id": 187917301,
                    "comment_id": 930158150,
                    "sentiment": "positive",
                    "intent": "praise",
                    "summary": "称赞图片",
                }
            ],
            "counting_note": "样本统计说明。",
        },
    }


class InsightCardTests(unittest.IsolatedAsyncioTestCase):
    def test_theme_aliases_and_public_theme_list(self) -> None:
        self.assertEqual(normalize_insight_card_theme("赛博朋克"), "cyberpunk")
        self.assertEqual(normalize_insight_card_theme("信号海报"), "command")
        self.assertEqual(normalize_insight_card_theme("信号作战室"), "command")
        self.assertEqual(normalize_insight_card_theme("", "editorial"), "editorial")
        self.assertEqual(len(available_insight_card_themes()), 4)
        self.assertEqual(THEMES["command"].label, "信号海报")
        with self.assertRaisesRegex(ValueError, "未知洞察卡片主题"):
            normalize_insight_card_theme("unknown")

    def test_resolution_aliases(self) -> None:
        self.assertEqual(normalize_insight_card_resolution("高清（推荐）"), "high")
        self.assertEqual(normalize_insight_card_resolution("超清"), "ultra")
        self.assertEqual(normalize_insight_card_resolution("", "standard"), "standard")
        with self.assertRaisesRegex(ValueError, "未知洞察卡片清晰度"):
            normalize_insight_card_resolution("unknown")

    def test_exploratory_payload_is_bounded_and_keeps_text_as_data(self) -> None:
        snapshot = exploratory_snapshot()
        snapshot["report"]["examples"] *= 10

        payload = build_insight_card_payload(
            snapshot,
            THEMES["terminal"],
            example_limit=3,
        )

        self.assertEqual(payload["mode"], "exploratory")
        self.assertEqual(payload["primary_value"], 500)
        self.assertEqual(len(payload["examples"]), 3)
        self.assertIn("<script>", payload["examples"][0]["content"])
        self.assertIn("{{ item.content | e }}", INSIGHT_CARD_TEMPLATE)
        self.assertIn("evidence", payload)
        self.assertNotIn("job_id", payload)
        self.assertNotIn("counting_note", payload)
        self.assertNotIn("provider_id", payload)
        self.assertNotIn("{{ job_id", INSIGHT_CARD_TEMPLATE)
        self.assertNotIn("{{ counting_note", INSIGHT_CARD_TEMPLATE)
        json.dumps(payload, ensure_ascii=False)

    def test_redesigned_card_is_mobile_readable_and_has_distinct_themes(
        self,
    ) -> None:
        snapshot = exploratory_snapshot()
        rendered = {
            key: Environment(autoescape=True)
            .from_string(INSIGHT_CARD_TEMPLATE)
            .render(
                **build_insight_card_payload(snapshot, theme, example_limit=2)
            )
            for key, theme in THEMES.items()
        }

        self.assertEqual(
            build_insight_card_payload(snapshot, THEMES["terminal"])["headline"],
            "",
        )
        self.assertNotIn("评论区正在形成怎样的共识", INSIGHT_CARD_TEMPLATE)
        self.assertIn("width: 720px", INSIGHT_CARD_TEMPLATE)
        self.assertIn("width: 680px", INSIGHT_CARD_TEMPLATE)
        self.assertIn("font-size: 30px", INSIGHT_CARD_TEMPLATE)
        self.assertIn("font-size: 27px", INSIGHT_CARD_TEMPLATE)
        self.assertIn("title_family | safe", INSIGHT_CARD_TEMPLATE)
        for key, html in rendered.items():
            self.assertIn('id="insight-card"', html)
            self.assertIn(f"theme-{key}", html)
            self.assertIn("mode-exploratory", html)
            self.assertNotIn("provider/model", html)
        self.assertIn(
            "font: 800 30px/1.3 Consolas, 'Microsoft YaHei UI', monospace",
            rendered["terminal"],
        )
        self.assertIn("[ ONLINE ]  XHHBOT ANALYTICS", rendered["terminal"])
        self.assertIn("explicit console grid", INSIGHT_CARD_TEMPLATE)
        self.assertIn("translucent fluorescent gradients", INSIGHT_CARD_TEMPLATE)
        self.assertIn("serif hierarchy", INSIGHT_CARD_TEMPLATE)
        self.assertIn("Signal poster", INSIGHT_CARD_TEMPLATE)
        self.assertIn("background-size: 32px 32px", rendered["terminal"])
        self.assertIn("rgba(255, 79, 154, .24)", rendered["cyberpunk"])
        self.assertNotIn(
            '<section class="section evidence-section">', rendered["editorial"]
        )
        self.assertIn(
            '<section class="section evidence-section">', rendered["terminal"]
        )

    def test_directed_payload_uses_match_statistics(self) -> None:
        snapshot = {
            "state": "complete",
            "filters": {},
            "report": {
                "criteria": {
                    "topic": "吐槽价格",
                    "keywords": ["贵"],
                    "emoji_tokens": [],
                },
                "total_comments": 100,
                "unique_users": 80,
                "unique_posts": 2,
                "keyword_matches": 12,
                "emoji_matches": 0,
                "semantic_matches": 8,
                "deterministic_union": 12,
                "union_matches": 20,
                "union_percentage": 20,
                "semantic_coverage_percent": 100,
                "semantic_complete": True,
                "examples": [],
            },
        }

        payload = build_insight_card_payload(snapshot, THEMES["command"])

        self.assertEqual(payload["mode"], "directed")
        self.assertEqual(payload["headline"], "吐槽价格")
        self.assertEqual(payload["primary_value"], 20)
        self.assertEqual(payload["criteria"][1]["value"], "1 个")
        self.assertTrue(payload["show_evidence"])
        rendered = (
            Environment(autoescape=True)
            .from_string(INSIGHT_CARD_TEMPLATE)
            .render(**payload)
        )
        self.assertIn("mode-directed", rendered)
        self.assertIn('<section class="section evidence-section">', rendered)

    async def test_renderer_calls_astrbot_html_render_with_png_selector(self) -> None:
        plugin = FakeRendererPlugin()

        result = await InsightCardRenderer().render(
            plugin,
            exploratory_snapshot(),
            theme="cyberpunk",
            example_limit=4,
        )

        self.assertEqual(result.theme, "cyberpunk")
        self.assertEqual(result.image_url, "https://render.example/card.png")
        self.assertTrue(plugin.calls[0]["return_url"])
        options = plugin.calls[0]["options"]
        self.assertEqual(options["selector"], "#insight-card")
        self.assertEqual(options["type"], "png")
        self.assertEqual(options["viewport_width"], 720)
        self.assertEqual(options["viewport_height"], 720)
        self.assertTrue(options["full_page"])
        self.assertEqual(options["scale"], "device")
        self.assertEqual(options["device_scale_factor_level"], "high")
        self.assertEqual(options["wait_until"], "load")
        self.assertNotIn("viewport", options)

    async def test_renderer_uses_requested_resolution(self) -> None:
        plugin = FakeRendererPlugin()

        result = await InsightCardRenderer().render(
            plugin,
            exploratory_snapshot(),
            resolution="超清",
        )

        self.assertEqual(result.resolution, "ultra")
        self.assertEqual(plugin.calls[0]["options"]["device_scale_factor_level"], "ultra")

    async def test_renderer_requires_completed_report(self) -> None:
        with self.assertRaisesRegex(ValueError, "尚未完成"):
            await InsightCardRenderer().render(
                FakeRendererPlugin(),
                {"state": "running", "report": {}},
            )


if __name__ == "__main__":
    unittest.main()
