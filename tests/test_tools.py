from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from astrbot_plugin_xhhrobot.main import XhhRobotPlugin
from astrbot_plugin_xhhrobot.tools import WRITE_ACTIONS, XhhToolRuntime


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

    def is_admin(self) -> bool:
        return self._admin

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_message_str(self) -> str:
        return self.message_str

    def get_platform_name(self) -> str:
        return self.platform


class FakeClient:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.search_payload: dict[str, Any] = {"status": "ok", "result": {"items": []}}

    async def publish_post(self, **kwargs: Any) -> dict[str, Any]:
        self.published.append(kwargs)
        return {"status": "ok", "result": {"link_id": 123}}

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return self.search_payload

    async def create_comment(self, **kwargs: Any) -> dict[str, Any]:
        self.comments.append(kwargs)
        return {"status": "ok", "result": {"comment_id": 456}}


class FakePlugin:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.client = FakeClient()
        self.recorded_bot_comments: list[dict[str, Any]] = []
        self.local_roots: list[Path] = []

    async def _status_text(self) -> str:
        return "登录：已配置"

    async def _record_bot_comment(self, **kwargs: Any) -> None:
        self.recorded_bot_comments.append(kwargs)

    def _allowed_local_upload_roots(self) -> list[Path]:
        return self.local_roots

    @staticmethod
    def _max_local_image_bytes() -> int:
        return 20 * 1024 * 1024


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

        self.assertEqual(len(tools), 22)
        self.assertTrue(by_name["xhh_search"].active)
        self.assertFalse(by_name["xhh_publish_post"].active)

    async def test_build_tools_adapts_confirmation_schema(self) -> None:
        required_runtime = XhhToolRuntime(FakePlugin(self.config()))
        required_tools = [
            tool
            for tool in required_runtime.build_tools()
            if tool.action in WRITE_ACTIONS
        ]
        self.assertEqual(len(required_tools), 7)
        for tool in required_tools:
            self.assertIn("confirm", tool.parameters["properties"])
            self.assertIn("confirm", tool.parameters["required"])

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
            self.assertNotIn("confirm", tool.parameters["required"])
            self.assertIn("不要求额外确认", tool.description)

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
                {"title": "标题", "body": "正文", "confirm": True},
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
                    "confirm": True,
                },
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["result"]["link_id"], 123)
        self.assertEqual(plugin.client.published[0]["topic_ids"], ["7214"])

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
        self.assertEqual(len(plugin.context.added), 22)
        self.assertEqual(len(plugin._registered_tool_names), 22)

        plugin._unregister_llm_tools()
        self.assertEqual(len(plugin.context.manager.removed), 22)
        self.assertEqual(plugin._registered_tool_names, [])


if __name__ == "__main__":
    unittest.main()
