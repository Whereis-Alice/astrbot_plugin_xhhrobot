from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jsonschema

from astrbot_plugin_xhhrobot.draft_store import DraftStore
from astrbot_plugin_xhhrobot.insight_card import InsightCardResult
from astrbot_plugin_xhhrobot.main import XhhRobotPlugin
from astrbot_plugin_xhhrobot.tools import WRITE_ACTIONS, XhhToolRuntime, tool_specs


class FakeEvent:
    def __init__(
        self,
        *,
        admin: bool = False,
        sender_id: str = "user-1",
        umo: str = "test:FriendMessage:session",
        message: str = "",
        platform: str = "test",
    ) -> None:
        self._admin = admin
        self._sender_id = sender_id
        self.unified_msg_origin = umo
        self.message_str = message
        self.platform = platform
        self.sent: list[Any] = []

    def is_admin(self) -> bool:
        return self._admin

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_message_str(self) -> str:
        return self.message_str

    def get_platform_name(self) -> str:
        return self.platform

    def image_result(self, source: str) -> dict[str, str]:
        return {"image": source}

    async def send(self, result: Any) -> None:
        self.sent.append(result)


class FakeClient:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.notifications_calls: list[dict[str, Any]] = []
        self.favorites_calls: list[dict[str, Any]] = []
        self.remote_drafts_calls = 0
        self.search_payload: dict[str, Any] = {"status": "ok", "result": {"items": []}}

    async def publish_post(self, **kwargs: Any) -> dict[str, Any]:
        self.published.append(kwargs)
        return {"status": "ok", "result": {"link_id": 123}}

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return self.search_payload

    async def create_comment(self, **kwargs: Any) -> dict[str, Any]:
        self.comments.append(kwargs)
        return {"status": "ok", "result": {"comment_id": 456}}

    async def fetch_notifications(self, **kwargs: Any) -> dict[str, Any]:
        self.notifications_calls.append(kwargs)
        return {"items": [{"message_id": 1, "source": "mention"}]}

    async def fetch_my_favorites(self, **kwargs: Any) -> dict[str, Any]:
        self.favorites_calls.append(kwargs)
        return {"items": [{"link_id": "88", "title": "收藏帖子"}]}

    async def fetch_remote_drafts(self) -> dict[str, Any]:
        self.remote_drafts_calls += 1
        return {"drafts": [{"link_id": "99", "title": "服务端草稿"}]}


class FakePlugin:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.client = FakeClient()
        self.auth = SimpleNamespace(
            heybox_id="42", nickname="tester", cookie="cookie-value"
        )
        self.recorded_bot_comments: list[dict[str, Any]] = []
        self.local_roots: list[Path] = []
        self.insight_started: list[dict[str, Any]] = []
        self.insight_cancelled = False
        self.insight_card_calls: list[dict[str, Any]] = []
        self.status_refresh_account: bool | None = None
        self.insight_wait_calls: list[str] = []
        self.insight_wait_result: dict[str, Any] | None = None

    async def _status_text(self, *, refresh_account: bool = False) -> str:
        self.status_refresh_account = refresh_account
        return "登录：已配置"

    async def _record_bot_comment(self, **kwargs: Any) -> None:
        self.recorded_bot_comments.append(kwargs)

    def _allowed_local_upload_roots(self) -> list[Path]:
        return self.local_roots

    @staticmethod
    def _max_local_image_bytes() -> int:
        return 20 * 1024 * 1024

    async def _start_comment_insight(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.insight_started.append(payload)
        return {"state": "running", "report": {"total_comments": 10}}

    def _comment_insight_snapshot(self) -> dict[str, Any]:
        return {"state": "complete", "report": {"union_matches": 3}}

    async def _cancel_comment_insight(self) -> bool:
        self.insight_cancelled = True
        return True

    async def _wait_for_comment_insight_completion(self, job_id: str) -> dict[str, Any]:
        self.insight_wait_calls.append(job_id)
        return self.insight_wait_result or {
            "state": "running",
            "job_id": job_id,
            "conversation_wait": {"timed_out": True},
        }

    async def _render_comment_insight_card(
        self,
        *,
        theme: str = "",
        resolution: str = "",
        include_examples: bool = True,
    ) -> InsightCardResult:
        self.insight_card_calls.append(
            {
                "theme": theme,
                "resolution": resolution,
                "include_examples": include_examples,
            }
        )
        return InsightCardResult(
            image_url="https://render.example/insight.png",
            theme=theme or "terminal",
            theme_label="小黑盒终端",
            mode="exploratory",
            resolution=resolution or "high",
        )


class FakeArchive:
    def __init__(self) -> None:
        self.stats_calls: list[dict[str, Any]] = []
        self.search_calls: list[dict[str, Any]] = []

    async def statistics(self, **kwargs: Any) -> dict[str, Any]:
        self.stats_calls.append(kwargs)
        return {"received": {"unique_comments": 7}, "bot": {"comment_records": 2}}

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        self.search_calls.append(kwargs)
        return {"matched_count": 1, "records": [{"direction": "received"}]}


class FakeToolManager:
    def __init__(self) -> None:
        self.removed: list[str] = []

    def remove_func(self, name: str) -> None:
        self.removed.append(name)


class FakeContext:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.manager = FakeToolManager()

    def add_llm_tools(self, *tools: Any) -> None:
        self.added.extend(tools)

    def get_llm_tool_manager(self) -> FakeToolManager:
        return self.manager


class XhhToolTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def config(**overrides: Any) -> dict[str, Any]:
        tools = {
            "enabled": True,
            "enable_write_tools": True,
            "write_admin_only": True,
            "private_tools_admin_only": True,
            "require_explicit_confirmation": True,
            "confirmation_keywords": ["确认执行小黑盒操作"],
            "write_cooldown_sec": 0,
            "duplicate_guard_sec": 120,
        }
        tools.update(overrides)
        return {"tools": tools}

    async def test_build_tools_disables_write_tools_by_default(self) -> None:
        plugin = FakePlugin({"tools": {"enabled": True}})
        tools = XhhToolRuntime(plugin).build_tools()
        by_name = {tool.name: tool for tool in tools}

        self.assertEqual(len(tools), 27)
        self.assertTrue(by_name["xhh_search"].active)
        self.assertFalse(by_name["xhh_publish_post"].active)
        self.assertNotIn("xhh_get_drafts", by_name)

    async def test_draft_tools_are_registered_only_when_enabled(self) -> None:
        disabled = XhhToolRuntime(FakePlugin(self.config()))
        disabled_result = json.loads(
            await disabled.execute("drafts", FakeEvent(admin=True), {})
        )
        self.assertFalse(disabled_result["ok"])
        self.assertIn("草稿箱", disabled_result["error"])

        enabled = XhhToolRuntime(FakePlugin(self.config(enable_draft_tools=True)))
        by_name = {tool.name: tool for tool in enabled.build_tools()}

        self.assertEqual(len(by_name), 30)
        self.assertTrue(by_name["xhh_get_drafts"].active)
        self.assertTrue(by_name["xhh_save_draft"].active)
        self.assertTrue(by_name["xhh_delete_draft"].active)

    async def test_draft_tools_keep_write_permissions_and_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin = FakePlugin(self.config(enable_draft_tools=True))
            plugin.draft_store = DraftStore(Path(temp_dir) / "post_drafts.sqlite3")
            runtime = XhhToolRuntime(plugin)
            confirmed = FakeEvent(admin=True, message="确认执行小黑盒操作")

            saved = json.loads(
                await runtime.execute(
                    "save_draft",
                    confirmed,
                    {
                        "title": "草稿标题",
                        "body": "草稿正文",
                        "topic_ids": ["7214"],
                        "confirm": True,
                    },
                )
            )
            draft_id = saved["data"]["draft"]["draft_id"]
            listed = json.loads(
                await runtime.execute("drafts", FakeEvent(admin=True), {})
            )
            denied_delete = json.loads(
                await runtime.execute(
                    "delete_draft",
                    FakeEvent(admin=True, message="删除草稿"),
                    {"draft_id": draft_id, "confirm": True},
                )
            )
            deleted = json.loads(
                await runtime.execute(
                    "delete_draft",
                    confirmed,
                    {"draft_id": draft_id, "confirm": True},
                )
            )

        self.assertTrue(saved["ok"])
        self.assertEqual(saved["source"], "local_draft_box")
        self.assertEqual(listed["data"]["total"], 1)
        self.assertEqual(listed["data"]["drafts"][0]["draft_id"], draft_id)
        self.assertEqual(listed["source"], "local_draft_box")
        self.assertIn("本地草稿箱", listed["notice"])
        self.assertFalse(denied_delete["ok"])
        self.assertIn("确认", denied_delete["error"])
        self.assertTrue(deleted["ok"])

    async def test_current_account_convenience_tools_use_signed_in_account(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)
        event = FakeEvent(admin=True)

        status = json.loads(await runtime.execute("status", event, {}))
        notifications = json.loads(
            await runtime.execute(
                "notifications",
                event,
                {"kind": "comment", "offset": 2, "limit": 5},
            )
        )
        favorites = json.loads(
            await runtime.execute("my_favorites", event, {"offset": 3, "limit": 4})
        )
        remote_drafts = json.loads(
            await runtime.execute("remote_drafts", event, {})
        )

        self.assertEqual(status["data"]["account"]["heybox_id"], "42")
        self.assertTrue(status["data"]["account"]["logged_in"])
        self.assertTrue(plugin.status_refresh_account)
        self.assertTrue(notifications["ok"])
        self.assertEqual(
            plugin.client.notifications_calls,
            [{"kind": "comment", "offset": 2, "limit": 5}],
        )
        self.assertEqual(plugin.client.favorites_calls, [{"offset": 3, "limit": 4}])
        self.assertEqual(favorites["data"]["items"][0]["link_id"], "88")
        self.assertEqual(remote_drafts["data"]["drafts"][0]["link_id"], "99")
        self.assertEqual(plugin.client.remote_drafts_calls, 1)

    async def test_build_tools_keep_confirmation_schema_stable(self) -> None:
        required_runtime = XhhToolRuntime(FakePlugin(self.config()))
        required_tools = [
            tool
            for tool in required_runtime.build_tools()
            if tool.action in WRITE_ACTIONS
        ]
        self.assertEqual(len(required_tools), 7)
        for tool in required_tools:
            self.assertNotIn("confirm", tool.parameters["properties"])
            self.assertNotIn("confirm", tool.parameters.get("required", []))
            self.assertIn("用户明确要求执行时直接调用", tool.description)

        direct_runtime = XhhToolRuntime(
            FakePlugin(self.config(require_explicit_confirmation=False))
        )
        direct_tools = [
            tool
            for tool in direct_runtime.build_tools()
            if tool.action in WRITE_ACTIONS
        ]
        self.assertEqual(len(direct_tools), 7)
        for tool in direct_tools:
            self.assertNotIn("confirm", tool.parameters["properties"])
            self.assertNotIn("confirm", tool.parameters.get("required", []))
            self.assertEqual(
                tool.description,
                next(
                    required.description
                    for required in required_tools
                    if required.action == tool.action
                ),
            )

    async def test_confirmation_switch_is_read_after_tools_are_built(self) -> None:
        config = self.config()
        plugin = FakePlugin(config)
        runtime = XhhToolRuntime(plugin)
        runtime.build_tools()
        config["tools"]["require_explicit_confirmation"] = False

        result = json.loads(
            await runtime.execute(
                "publish_post",
                FakeEvent(admin=True, message="直接发布这篇帖子"),
                {"title": "标题", "body": "正文"},
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(plugin.client.published), 1)
        self.assertTrue(plugin.client.published[0]["preserve_remote_image_bytes"])

    async def test_write_tools_pass_remote_image_strategy_from_configuration(self) -> None:
        config = self.config(require_explicit_confirmation=False)
        config["media"] = {"preserve_remote_image_bytes": False}
        plugin = FakePlugin(config)
        runtime = XhhToolRuntime(plugin)

        result = json.loads(
            await runtime.execute(
                "publish_post",
                FakeEvent(admin=True, message="直接发布这篇帖子"),
                {"title": "标题", "body": "正文"},
            )
        )

        self.assertTrue(result["ok"])
        self.assertFalse(plugin.client.published[0]["preserve_remote_image_bytes"])

    async def test_enabling_confirmation_after_tools_are_built_blocks_write(
        self,
    ) -> None:
        config = self.config(require_explicit_confirmation=False)
        plugin = FakePlugin(config)
        runtime = XhhToolRuntime(plugin)
        runtime.build_tools()
        config["tools"]["require_explicit_confirmation"] = True

        result = json.loads(
            await runtime.execute(
                "publish_post",
                FakeEvent(admin=True, message="直接发布这篇帖子"),
                {"title": "标题", "body": "正文"},
            )
        )

        self.assertFalse(result["ok"])
        self.assertIn("写操作尚未确认", result["error"])
        self.assertEqual(plugin.client.published, [])

    async def test_publish_post_schema_accepts_numeric_topic_ids(self) -> None:
        runtime = XhhToolRuntime(
            FakePlugin(self.config(require_explicit_confirmation=False))
        )
        tool = next(
            tool for tool in runtime.build_tools() if tool.name == "xhh_publish_post"
        )

        jsonschema.validate(
            {
                "title": "标题",
                "body": "正文",
                "topic_ids": [7214],
            },
            tool.parameters,
        )

    async def test_write_can_run_directly_when_confirmation_is_disabled(self) -> None:
        plugin = FakePlugin(self.config(require_explicit_confirmation=False))
        runtime = XhhToolRuntime(plugin)

        result = json.loads(
            await runtime.execute(
                "publish_post",
                FakeEvent(admin=True, message="直接发布这篇帖子"),
                {"title": "标题", "body": "正文"},
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(plugin.client.published), 1)

    async def test_xhh_originated_event_cannot_call_account_tools(self) -> None:
        plugin = FakePlugin(self.config(require_explicit_confirmation=False))
        runtime = XhhToolRuntime(plugin)

        result = json.loads(
            await runtime.execute(
                "search",
                FakeEvent(admin=True, platform="xhhrobot"),
                {"query": "AstrBot"},
            )
        )

        self.assertFalse(result["ok"])
        self.assertIn("外部消息不能调用", result["error"])

    async def test_admin_write_tool_accepts_image_from_allowed_local_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "reply.png"
            image.write_bytes(b"image")
            config = self.config(require_explicit_confirmation=False)
            config["media"] = {"allow_local_tool_uploads": True}
            plugin = FakePlugin(config)
            plugin.local_roots = [root]
            runtime = XhhToolRuntime(plugin)

            result = json.loads(
                await runtime.execute(
                    "publish_post",
                    FakeEvent(admin=True, message="发布帖子"),
                    {
                        "title": "标题",
                        "body": "正文",
                        "image_urls": [str(image)],
                    },
                )
            )

        self.assertTrue(result["ok"])
        self.assertEqual(plugin.client.published[0]["image_urls"], [str(image)])

    async def test_admin_write_tool_preserves_data_url_as_one_image(self) -> None:
        config = self.config(require_explicit_confirmation=False)
        config["media"] = {"allow_local_tool_uploads": True}
        plugin = FakePlugin(config)
        runtime = XhhToolRuntime(plugin)
        data_url = "data:image/png;base64,aGVsbG8="

        result = json.loads(
            await runtime.execute(
                "publish_post",
                FakeEvent(admin=True, message="发布帖子"),
                {"title": "标题", "body": "正文", "image_urls": data_url},
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(plugin.client.published[0]["image_urls"], [data_url])

    async def test_write_requires_phrase_in_original_user_message(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)
        event = FakeEvent(admin=True, message="帮我发帖")

        result = json.loads(
            await runtime.execute(
                "publish_post",
                event,
                {"title": "标题", "body": "正文"},
            )
        )

        self.assertFalse(result["ok"])
        self.assertIn("用户", result["error"])
        self.assertEqual(plugin.client.published, [])

    async def test_admin_can_publish_after_explicit_confirmation(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)
        event = FakeEvent(admin=True, message="确认执行小黑盒操作，按刚才内容发布")

        result = json.loads(
            await runtime.execute(
                "publish_post",
                event,
                {
                    "title": "标题",
                    "body": "正文",
                    "topic_ids": ["7214"],
                    "hashtags": ["AstrBot"],
                },
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["result"]["link_id"], 123)
        self.assertEqual(plugin.client.published[0]["topic_ids"], ["7214"])

    async def test_publish_post_accepts_safe_ordered_rich_content_blocks(self) -> None:
        plugin = FakePlugin(self.config(require_explicit_confirmation=False))
        runtime = XhhToolRuntime(plugin)

        result = json.loads(
            await runtime.execute(
                "publish_post",
                FakeEvent(admin=True, message="发布带格式的帖子"),
                {
                    "title": "富文本标题",
                    "content_blocks": [
                        {"type": "text", "text": "第一段"},
                        {"type": "html", "html": "<p><strong>重点</strong></p>"},
                        {"type": "image", "url": "https://images.example/a.png"},
                    ],
                },
            )
        )
        rejected = json.loads(
            await runtime.execute(
                "publish_post",
                FakeEvent(admin=True, message="发布危险格式帖子"),
                {
                    "title": "富文本标题",
                    "content_blocks": [
                        {"type": "html", "html": "<script>alert(1)</script>"}
                    ],
                },
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            plugin.client.published[0]["content_blocks"],
            [
                {"type": "text", "text": "第一段"},
                {"type": "html", "text": "<p><strong>重点</strong></p>"},
                {"type": "image", "url": "https://images.example/a.png"},
            ],
        )
        self.assertFalse(rejected["ok"])
        self.assertIn("script", rejected["error"])

    async def test_comment_tool_archives_successful_bot_comment(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)

        result = json.loads(
            await runtime.execute(
                "create_comment",
                FakeEvent(admin=True, message="确认执行小黑盒操作"),
                {
                    "link_id": "123",
                    "text": "工具发布的评论",
                    "reply_id": "50",
                    "root_id": "40",
                    "confirm": True,
                },
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(plugin.recorded_bot_comments), 1)
        archived = plugin.recorded_bot_comments[0]
        self.assertEqual(archived["kind"], "llm_tool")
        self.assertEqual(archived["link_id"], 123)
        self.assertEqual(archived["comment_id"], 456)
        self.assertEqual(archived["target_comment_id"], 50)
        self.assertEqual(archived["root_comment_id"], 40)

    async def test_allowlisted_non_admin_can_write_when_admin_only_is_off(self) -> None:
        plugin = FakePlugin(
            self.config(
                write_admin_only=False, allowed_astrbot_user_ids=["allowed-user"]
            )
        )
        runtime = XhhToolRuntime(plugin)
        event = FakeEvent(
            admin=False,
            sender_id="allowed-user",
            message="确认执行小黑盒操作",
        )

        result = json.loads(
            await runtime.execute(
                "publish_post",
                event,
                {"title": "标题", "body": "正文", "confirm": True},
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(plugin.client.published), 1)

    async def test_non_allowlisted_non_admin_is_denied(self) -> None:
        plugin = FakePlugin(
            self.config(
                write_admin_only=False, allowed_astrbot_user_ids=["someone-else"]
            )
        )
        runtime = XhhToolRuntime(plugin)
        event = FakeEvent(admin=False, message="确认执行小黑盒操作")

        result = json.loads(
            await runtime.execute(
                "publish_post",
                event,
                {"title": "标题", "body": "正文", "confirm": True},
            )
        )

        self.assertFalse(result["ok"])
        self.assertIn("允许列表", result["error"])

    async def test_duplicate_write_from_same_message_is_blocked(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)
        event = FakeEvent(admin=True, message="确认执行小黑盒操作")
        arguments = {"title": "标题", "body": "正文", "confirm": True}

        first = json.loads(await runtime.execute("publish_post", event, arguments))
        second = json.loads(await runtime.execute("publish_post", event, arguments))

        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertIn("重复", second["error"])
        self.assertEqual(len(plugin.client.published), 1)

    async def test_private_image_url_is_rejected(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)
        event = FakeEvent(admin=True, message="确认执行小黑盒操作")

        result = json.loads(
            await runtime.execute(
                "publish_post",
                event,
                {
                    "title": "标题",
                    "body": "正文",
                    "image_urls": ["http://127.0.0.1/private.png"],
                    "confirm": True,
                },
            )
        )

        self.assertFalse(result["ok"])
        self.assertIn("私有", result["error"])
        self.assertEqual(plugin.client.published, [])

    async def test_external_output_is_valid_json_and_truncated(self) -> None:
        plugin = FakePlugin(self.config(max_tool_output_chars=1000))
        plugin.client.search_payload = {
            "status": "ok",
            "result": {"items": [{"title": "x" * 4000}]},
        }
        runtime = XhhToolRuntime(plugin)

        raw = await runtime.execute(
            "search",
            FakeEvent(),
            {"query": "AstrBot", "search_type": "link"},
        )
        result = json.loads(raw)

        self.assertLessEqual(len(raw), 1000)
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertIn("不可信外部内容", result["notice"])

    async def test_completed_comment_insight_preserves_summary_under_tool_limit(self) -> None:
        plugin = FakePlugin(self.config(max_tool_output_chars=1000))
        plugin.insight_wait_result = {
            "state": "complete",
            "job_id": "job-1",
            "report": {
                "analysis_mode": "exploratory",
                "total_comments": 800,
                "summary": "用户集中希望得到原图。",
                "notable_findings": ["原图需求最集中"],
                "themes": [{"label": "图片反馈", "count": 700}],
                "examples": [
                    {"content": "x" * 500, "summary": "询问原图"}
                    for _ in range(12)
                ],
            },
        }

        raw = await XhhToolRuntime(plugin).execute(
            "comment_insights", FakeEvent(admin=True), {"mode": "run"}
        )
        result = json.loads(raw)

        self.assertLessEqual(len(raw), 1000)
        self.assertNotIn("truncated", result)
        self.assertEqual(result["data"]["report"]["summary"], "用户集中希望得到原图。")
        self.assertNotIn("examples", result["data"]["report"])

    async def test_private_tool_requires_admin_by_default(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)

        result = json.loads(await runtime.execute("status", FakeEvent(admin=False), {}))

        self.assertFalse(result["ok"])
        self.assertIn("管理员", result["error"])

    async def test_comment_archive_tools_require_admin_and_forward_filters(
        self,
    ) -> None:
        plugin = FakePlugin(self.config())
        plugin.comment_archive = FakeArchive()
        runtime = XhhToolRuntime(plugin)

        denied = json.loads(
            await runtime.execute(
                "comment_stats",
                FakeEvent(admin=False),
                {"keyword": "AstrBot"},
            )
        )
        stats = json.loads(
            await runtime.execute(
                "comment_stats",
                FakeEvent(admin=True),
                {"keyword": "AstrBot", "link_id": "123", "source": "mention"},
            )
        )
        search = json.loads(
            await runtime.execute(
                "search_comment_archive",
                FakeEvent(admin=True),
                {"direction": "bot", "bot_kind": "auto_reply", "limit": 9},
            )
        )

        self.assertFalse(denied["ok"])
        self.assertTrue(stats["ok"])
        self.assertTrue(search["ok"])
        self.assertEqual(plugin.comment_archive.stats_calls[0]["link_id"], 123)
        self.assertEqual(plugin.comment_archive.stats_calls[0]["source"], "mention")
        self.assertEqual(plugin.comment_archive.search_calls[0]["direction"], "bot")
        self.assertEqual(
            plugin.comment_archive.search_calls[0]["bot_kind"], "auto_reply"
        )
        self.assertEqual(plugin.comment_archive.search_calls[0]["limit"], 9)

    async def test_comment_insight_tool_waits_for_report_and_hands_it_to_agent(self) -> None:
        plugin = FakePlugin(self.config())
        plugin.insight_wait_result = {
            "state": "complete",
            "job_id": "job-1",
            "report": {"union_matches": 3},
        }
        runtime = XhhToolRuntime(plugin)

        started = json.loads(
            await runtime.execute(
                "comment_insights",
                FakeEvent(admin=True),
                {
                    "mode": "run",
                    "topic": "喜欢、爱意或好感",
                    "keywords": ["喜欢", "爱"],
                    "emoji_tokens": ["[cube_喜欢]"],
                    "semantic": True,
                    "link_id": "123",
                },
            )
        )
        status = json.loads(
            await runtime.execute(
                "comment_insights", FakeEvent(admin=True), {"mode": "status"}
            )
        )
        cancelled = json.loads(
            await runtime.execute(
                "comment_insights", FakeEvent(admin=True), {"mode": "cancel"}
            )
        )

        self.assertTrue(started["ok"])
        self.assertEqual(
            started["agent_handoff"]["final_response_owner"],
            "current_astrbot_agent",
        )
        self.assertTrue(started["agent_handoff"]["preserve_current_persona"])
        self.assertTrue(started["agent_handoff"]["preserve_request_hooks"])
        self.assertIn("已完成", started["agent_handoff"]["instruction"])
        self.assertEqual(plugin.insight_started[0]["link_id"], 123)
        self.assertEqual(plugin.insight_started[0]["keywords"], ["喜欢", "爱"])
        self.assertEqual(plugin.insight_wait_calls, [""])
        self.assertEqual(started["data"]["state"], "complete")
        self.assertEqual(status["data"]["report"]["union_matches"], 3)
        self.assertTrue(cancelled["data"]["cancelled"])

    async def test_comment_insight_tool_keeps_background_job_after_wait_timeout(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)

        result = json.loads(
            await runtime.execute(
                "comment_insights",
                FakeEvent(admin=True),
                {"mode": "run", "link_id": "123"},
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["state"], "running")
        self.assertTrue(result["data"]["conversation_wait"]["timed_out"])
        self.assertIn("仍在后台运行", result["agent_handoff"]["instruction"])

    async def test_comment_insight_tool_allows_automatic_analysis_without_topic(
        self,
    ) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)

        result = json.loads(
            await runtime.execute(
                "comment_insights",
                FakeEvent(admin=True),
                {"mode": "run", "link_id": "123"},
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(plugin.insight_started[0]["topic"], "")
        self.assertEqual(plugin.insight_started[0]["link_id"], 123)

    def test_comment_insight_tool_description_supports_natural_language_intents(
        self,
    ) -> None:
        spec = next(item for item in tool_specs() if item.name == "xhh_comment_insights")

        self.assertIn("多少人在夸我", spec.description)
        self.assertIn("吐槽价格", spec.description)
        self.assertIn("不要反问用户提供关键词", spec.description)
        self.assertIn("status", spec.description)
        self.assertIn("仅管理员", spec.description)
        self.assertIn("当前人格", spec.description)
        self.assertIn("请求钩子", spec.description)
        self.assertIn("不要原样输出 JSON", spec.description)
        self.assertIn("自动探索", spec.parameters["properties"]["topic"]["description"])

    async def test_comment_insight_card_tool_sends_rendered_image(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)
        event = FakeEvent(admin=True)

        result = json.loads(
            await runtime.execute(
                "render_comment_insight_card",
                event,
                {"theme": "cyberpunk", "resolution": "ultra"},
            )
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["sent_to_current_session"])
        self.assertEqual(result["data"]["theme"], "cyberpunk")
        self.assertEqual(result["data"]["resolution"], "ultra")
        self.assertEqual(event.sent, [{"image": "https://render.example/insight.png"}])
        self.assertEqual(
            plugin.insight_card_calls,
            [
                {
                    "theme": "cyberpunk",
                    "resolution": "ultra",
                    "include_examples": True,
                }
            ],
        )

    async def test_comment_insight_card_tool_remains_admin_protected(self) -> None:
        plugin = FakePlugin(self.config())
        result = json.loads(
            await XhhToolRuntime(plugin).execute(
                "render_comment_insight_card",
                FakeEvent(admin=False),
                {"theme": "terminal"},
            )
        )

        self.assertFalse(result["ok"])
        self.assertEqual(plugin.insight_card_calls, [])

    async def test_tool_call_reads_event_from_astrbot_context_wrapper(self) -> None:
        plugin = FakePlugin(self.config())
        runtime = XhhToolRuntime(plugin)
        tool = next(tool for tool in runtime.build_tools() if tool.name == "xhh_search")
        context = SimpleNamespace(context=SimpleNamespace(event=FakeEvent()))

        result = json.loads(
            await tool.call(context, query="AstrBot", search_type="link")
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["untrusted_external_content"])

    async def test_plugin_registers_and_removes_all_tools(self) -> None:
        plugin = object.__new__(XhhRobotPlugin)
        plugin.config = {"tools": {"enabled": True, "enable_write_tools": False}}
        plugin.context = FakeContext()
        plugin._tool_runtime = XhhToolRuntime(plugin)
        plugin._registered_tool_names = []

        plugin._register_llm_tools()
        self.assertEqual(len(plugin.context.added), 27)
        self.assertEqual(len(plugin._registered_tool_names), 27)

        plugin._unregister_llm_tools()
        self.assertEqual(len(plugin.context.manager.removed), 27)
        self.assertEqual(plugin._registered_tool_names, [])


if __name__ == "__main__":
    unittest.main()
