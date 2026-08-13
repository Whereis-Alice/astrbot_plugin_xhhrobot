from __future__ import annotations

import asyncio
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import astrbot_plugin_xhhrobot.main as main_module
from astrbot_plugin_xhhrobot.insight_card import InsightCardResult
from astrbot_plugin_xhhrobot.main import PLUGIN_ID, XhhRobotPlugin
from astrbot_plugin_xhhrobot.media import ImagePayload
from astrbot_plugin_xhhrobot.models import AuthInfo, Mention
from astrbot_plugin_xhhrobot.xhh_client import XhhError


class FakeArchive:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.search_calls: list[dict] = []

    async def statistics(self) -> dict:
        return {
            "received": {"unique_comments": 2, "status_counts": {"replied": 1}},
            "bot": {"comment_records": 1, "status_counts": {"sent": 1}},
        }

    async def search(self, **kwargs) -> dict:
        self.search_calls.append(kwargs)
        return {
            "matched_count": 1,
            "returned_count": 1,
            "records": [
                {
                    "direction": "received",
                    "content": "不应显示的评论正文",
                    "status": "replied",
                }
            ],
        }


class FakeDmStore:
    def __init__(self) -> None:
        self.search_calls: list[dict] = []

    async def statistics(self) -> dict:
        return {
            "total": 3,
            "unique_users": 2,
            "with_images": 1,
            "status_counts": {"sent": 2},
        }

    async def search(self, **kwargs) -> dict:
        self.search_calls.append(kwargs)
        return {"total": 0, "records": []}


class WebUiTests(unittest.IsolatedAsyncioTestCase):
    def plugin(self, config: dict | None = None) -> XhhRobotPlugin:
        plugin = object.__new__(XhhRobotPlugin)
        plugin.config = config or {"webui": {"enabled": True}}
        plugin.comment_archive = FakeArchive()
        plugin.dm_store = FakeDmStore()
        return plugin

    async def test_summary_combines_comment_and_direct_message_databases(self) -> None:
        plugin = self.plugin()
        with patch.object(main_module, "jsonify", side_effect=lambda value: value):
            result = await plugin.web_analytics_summary()

        self.assertTrue(result["ok"])
        self.assertTrue(result["comments"]["enabled"])
        self.assertEqual(result["comments"]["received"]["unique_comments"], 2)
        self.assertEqual(result["direct_messages"]["total"], 3)

    async def test_comment_query_forwards_filters_pagination_and_hides_content(
        self,
    ) -> None:
        plugin = self.plugin(
            {
                "webui": {
                    "enabled": True,
                    "show_message_content": False,
                    "max_page_size": 100,
                }
            }
        )
        args = {
            "dataset": "comments",
            "keyword": "测试",
            "direction": "received",
            "source": "mention",
            "status": "replied",
            "link_id": "186",
            "user_id": "270",
            "limit": "30",
            "offset": "60",
        }
        with (
            patch.object(main_module, "request", SimpleNamespace(args=args)),
            patch.object(main_module, "jsonify", side_effect=lambda value: value),
        ):
            result = await plugin.web_analytics_messages()

        call = plugin.comment_archive.search_calls[0]
        self.assertEqual(call["link_id"], 186)
        self.assertEqual(call["user_id"], 270)
        self.assertEqual(call["limit"], 30)
        self.assertEqual(call["offset"], 60)
        self.assertEqual(result["records"][0]["content"], "[内容已在 WebUI 配置中隐藏]")
        self.assertEqual(result["records"][0]["dataset"], "comments")

    async def test_direct_message_query_uses_store_redaction(self) -> None:
        plugin = self.plugin(
            {"webui": {"enabled": True, "show_message_content": False}}
        )
        args = {"dataset": "direct_messages", "user_id": "99"}
        with (
            patch.object(main_module, "request", SimpleNamespace(args=args)),
            patch.object(main_module, "jsonify", side_effect=lambda value: value),
        ):
            result = await plugin.web_analytics_messages()

        self.assertTrue(result["ok"])
        self.assertFalse(plugin.dm_store.search_calls[0]["include_content"])
        self.assertEqual(plugin.dm_store.search_calls[0]["user_id"], "99")

    def test_comment_insight_snapshot_hides_representative_comments(self) -> None:
        plugin = self.plugin(
            {"webui": {"enabled": True, "show_message_content": False}}
        )
        plugin._insight_state = {
            **plugin._empty_comment_insight_state(),
            "state": "complete",
            "report": {
                "union_matches": 1,
                "examples": [{"content": "不应显示的评论正文"}],
            },
        }

        payload = plugin._web_comment_insight_snapshot()

        self.assertEqual(payload["report"]["examples"], [])
        self.assertTrue(payload["report"]["examples_hidden"])

    async def test_comment_insight_card_web_api_renders_selected_theme(self) -> None:
        plugin = self.plugin()
        plugin._render_comment_insight_card = AsyncMock(
            return_value=InsightCardResult(
                image_url="https://render.example/card.png",
                theme="editorial",
                theme_label="编辑部报告",
                mode="exploratory",
                resolution="high",
            )
        )
        fake_request = SimpleNamespace(
            get_json=AsyncMock(return_value={"theme": "editorial"})
        )

        with (
            patch.object(main_module, "request", fake_request),
            patch.object(main_module, "jsonify", side_effect=lambda value: value),
        ):
            result = await plugin.web_comment_insight_render()

        self.assertTrue(result["ok"])
        self.assertEqual(result["theme_label"], "编辑部报告")
        plugin._render_comment_insight_card.assert_awaited_once_with(
            theme="editorial",
            resolution=None,
            include_examples=True,
        )

    async def test_comment_insight_card_web_api_hides_examples_with_webui_setting(
        self,
    ) -> None:
        plugin = self.plugin(
            {"webui": {"enabled": True, "show_message_content": False}}
        )
        plugin._render_comment_insight_card = AsyncMock(
            return_value=InsightCardResult(
                image_url="https://render.example/card.png",
                theme="terminal",
                theme_label="小黑盒终端",
                mode="directed",
                resolution="high",
            )
        )
        fake_request = SimpleNamespace(get_json=AsyncMock(return_value={}))

        with (
            patch.object(main_module, "request", fake_request),
            patch.object(main_module, "jsonify", side_effect=lambda value: value),
        ):
            result = await plugin.web_comment_insight_render()

        self.assertTrue(result["ok"])
        plugin._render_comment_insight_card.assert_awaited_once_with(
            theme=None,
            resolution=None,
            include_examples=False,
        )

    async def test_status_reports_real_own_post_reply_setting(self) -> None:
        plugin = self.plugin(
            {
                "webui": {"enabled": True},
                "filters": {"reply_to_own_post_comments": False},
            }
        )
        plugin.store = SimpleNamespace(
            snapshot=AsyncMock(
                return_value={
                    "queue": {},
                    "dead": {},
                    "paused": False,
                    "last_message_id": 0,
                    "last_comment_message_id": 0,
                    "stats": {},
                }
            )
        )
        plugin._archive_overview = AsyncMock(
            return_value={
                "enabled": True,
                "received_comments": 0,
                "received_observations": 0,
                "bot_comments": 0,
            }
        )
        plugin._event_tasks = {}
        plugin._worker_task = None
        plugin._started_at = time.time()
        plugin._last_poll_at = 0
        plugin._last_success_at = 0
        plugin._last_error = ""
        plugin._consecutive_errors = 0
        plugin._suspended_until = 0
        plugin._last_dm_poll_at = 0
        plugin._last_dm_error = ""
        plugin._dm_sending_blocked_reason = "小黑盒已禁止当前账号发送私信"
        plugin._dm_sending_blocked_at = 123.0
        plugin._dm_sending_blocked_until = time.time() + 60
        plugin.auth = None
        plugin._auth_invalid = False
        plugin._auth_source = "none"

        result = await plugin._web_status_payload()

        self.assertFalse(result["features"]["reply_to_own_post_comments"])
        self.assertTrue(result["direct_messages"]["sending_blocked"])
        self.assertEqual(
            result["direct_messages"]["sending_blocked_reason"],
            "小黑盒已禁止当前账号发送私信",
        )
        self.assertGreater(
            result["direct_messages"]["sending_blocked_until"], time.time()
        )

    def test_registers_page_routes_with_plugin_prefix(self) -> None:
        routes: list[tuple] = []
        plugin = self.plugin()
        plugin.context = SimpleNamespace(
            register_web_api=lambda *args: routes.append(args)
        )

        plugin._register_web_apis()

        self.assertEqual(len(routes), 15)
        self.assertTrue(all(route[0].startswith(f"/{PLUGIN_ID}/") for route in routes))
        self.assertIn(f"/{PLUGIN_ID}/account/avatar", {route[0] for route in routes})
        suffixes = {route[0].rsplit("/", 1)[-1] for route in routes}
        self.assertIn("start", suffixes)
        self.assertIn("stop", suffixes)
        self.assertIn("clear", suffixes)

    def test_dashboard_exposes_terminal_network_and_comment_insight_workspace(
        self,
    ) -> None:
        page = (
            Path(__file__).parents[1] / "pages" / "dashboard" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('id="networkCanvas"', page)
        self.assertIn("function initializeNetworkBackground()", page)
        self.assertIn('data-tab="insights"', page)
        self.assertIn('id="insightForm"', page)
        self.assertIn("分析主题（可选）", page)
        self.assertIn('id="insightOverview"', page)
        self.assertIn('id="insightEvidenceSection"', page)
        self.assertIn('id="insightEvidence"', page)
        self.assertIn("function renderInsightEvidence(report)", page)
        self.assertIn('report.analysis_mode === "exploratory"', page)
        self.assertIn(".terminal-empty[hidden]", page)
        self.assertIn('postApi("analytics/insights/run", insightPayload())', page)
        self.assertIn('postApi("analytics/insights/cancel", {})', page)
        self.assertIn('postApi("analytics/insights/render", {', page)
        self.assertIn('id="insightCardTheme"', page)
        self.assertIn('id="insightCardResolution"', page)
        self.assertIn('id="renderInsightCardButton"', page)
        self.assertIn('id="insightCardDialog"', page)
        self.assertIn('getApi("analytics/insights/status")', page)
        self.assertIn("prefers-reduced-motion", page)

    def test_dashboard_prioritizes_messages_and_reduces_terminal_prefixes(self) -> None:
        page = (
            Path(__file__).parents[1] / "pages" / "dashboard" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('class="database-commandbar"', page)
        self.assertIn('class="database-details"', page)
        self.assertIn('id="toggleFiltersButton"', page)
        self.assertIn('.filters[data-expanded="true"]', page)
        self.assertIn('#databasePanel td:nth-child(4)', page)
        self.assertLess(page.index('id="filterForm"'), page.index('class="table-wrap"'))
        self.assertLess(page.index('class="table-wrap"'), page.index('id="commentDistribution"'))
        self.assertNotIn('content: "./"', page)
        self.assertNotIn('content: "> "', page)
        self.assertNotIn('content: ":: "', page)
        self.assertNotIn('content: "["', page)
        self.assertIn('class="runtime-overview"', page)
        self.assertIn('class="metrics runtime-metrics"', page)
        self.assertIn("#statusPanel .runtime-metrics .metric", page)

    async def test_account_profile_refresh_updates_cached_nickname_and_fields(
        self,
    ) -> None:
        plugin = self.plugin()
        plugin.auth = AuthInfo(
            cookie="cookie=value", heybox_id="102013423", nickname="旧名字"
        )
        plugin._auth_source = "qr"
        plugin._account_profile = {}
        plugin._account_profile_updated_at = 0.0
        plugin._account_profile_error = ""
        plugin._account_profile_lock = asyncio.Lock()
        plugin.client = SimpleNamespace(
            fetch_user_profile=AsyncMock(
                return_value={
                    "status": "ok",
                    "result": {
                        "account_detail": {
                            "userid": "102013423",
                            "username": "爱丽丝新名字",
                            "avatar": "https://example.com/avatar.jpg",
                            "level_info": {"level": 42},
                            "bbs_info": {
                                "follow_num": 88,
                                "fan_num": 520,
                                "post_link_num": 31,
                            },
                            "signature": "正在小黑盒营业",
                            "ip_location": "上海",
                        }
                    },
                }
            ),
            set_auth=lambda auth: None,
        )
        plugin.put_kv_data = AsyncMock()

        profile = await plugin._refresh_account_profile(force=True)

        self.assertEqual(profile["nickname"], "爱丽丝新名字")
        self.assertEqual(profile["level"], "42")
        self.assertEqual(profile["following_count"], 88)
        self.assertEqual(profile["follower_count"], 520)
        self.assertEqual(profile["post_count"], 31)
        self.assertEqual(plugin.auth.nickname, "爱丽丝新名字")
        plugin.put_kv_data.assert_awaited_once()

    async def test_account_profile_accepts_avatar_object_and_cookie_fallback(
        self,
    ) -> None:
        object_profile = XhhRobotPlugin._summarize_account_profile(
            {
                "result": {
                    "account_detail": {
                        "avatar": {
                            "small": "//imgheybox.max-c.com/small.jpg",
                            "original": "//imgheybox.max-c.com/original.jpg",
                        }
                    }
                }
            },
            "102013423",
        )
        self.assertEqual(
            object_profile["avatar"],
            "https://imgheybox.max-c.com/original.jpg",
        )
        root_profile = XhhRobotPlugin._summarize_account_profile(
            {
                "result": {
                    "avatar": "https://imgheybox.max-c.com/root-avatar.jpg",
                    "account_detail": {"username": "爱丽丝"},
                }
            },
            "102013423",
        )
        self.assertEqual(
            root_profile["avatar"],
            "https://imgheybox.max-c.com/root-avatar.jpg",
        )

        plugin = self.plugin()
        plugin.auth = AuthInfo(
            cookie=(
                "user_heybox_id=102013423; "
                "avatar=https%253A%252F%252Fimgheybox.max-c.com%252Fcookie.jpg"
            ),
            heybox_id="102013423",
        )
        plugin._auth_source = "qr"
        plugin._account_profile = {}
        plugin._account_profile_updated_at = 0.0
        plugin._account_profile_error = ""
        plugin._account_profile_lock = asyncio.Lock()
        plugin._account_avatar_source = ""
        plugin._account_avatar_data_url = ""
        plugin._account_avatar_updated_at = 0.0
        plugin._account_avatar_error = ""
        plugin.client = SimpleNamespace(
            fetch_user_profile=AsyncMock(
                return_value={
                    "status": "ok",
                    "result": {"account_detail": {"username": "爱丽丝"}},
                }
            ),
            set_auth=lambda auth: None,
        )
        plugin.put_kv_data = AsyncMock()

        cookie_profile = await plugin._refresh_account_profile(force=True)

        self.assertEqual(
            cookie_profile["avatar"],
            "https://imgheybox.max-c.com/cookie.jpg",
        )

    async def test_account_avatar_is_downloaded_once_and_cached(self) -> None:
        plugin = self.plugin()
        plugin._account_profile = {
            "avatar": "https://imgheybox.max-c.com/avatar.png"
        }
        plugin._account_avatar_source = ""
        plugin._account_avatar_data_url = ""
        plugin._account_avatar_updated_at = 0.0
        plugin._account_avatar_error = ""
        plugin._account_avatar_lock = asyncio.Lock()
        plugin.client = SimpleNamespace(
            fetch_image_payload=AsyncMock(
                return_value=ImagePayload(
                    name="avatar.png",
                    mimetype="image/png",
                    data=b"avatar-bytes",
                    width=30,
                    height=30,
                )
            )
        )

        first = await plugin._refresh_account_avatar()
        second = await plugin._refresh_account_avatar()

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("data:image/png;base64,"))
        plugin.client.fetch_image_payload.assert_awaited_once_with(
            "https://imgheybox.max-c.com/avatar.png",
            max_bytes=main_module.ACCOUNT_AVATAR_MAX_BYTES,
        )

    async def test_account_avatar_falls_back_to_login_cookie(self) -> None:
        plugin = self.plugin()
        plugin.auth = AuthInfo(
            cookie=(
                "user_heybox_id=102013423; "
                "avatar=https%253A%252F%252Fimgheybox.max-c.com%252Fcookie.jpg"
            ),
            heybox_id="102013423",
        )
        plugin._account_profile = {"nickname": "爱丽丝"}
        plugin._account_profile_updated_at = time.time()
        plugin._account_avatar_source = ""
        plugin._account_avatar_data_url = ""
        plugin._account_avatar_updated_at = 0.0
        plugin._account_avatar_error = ""
        plugin._account_avatar_lock = asyncio.Lock()
        plugin.client = SimpleNamespace(
            fetch_image_payload=AsyncMock(
                return_value=ImagePayload(
                    name="avatar.jpg",
                    mimetype="image/jpeg",
                    data=b"avatar-bytes",
                    width=30,
                    height=30,
                )
            )
        )

        data_url = await plugin._refresh_account_avatar()

        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        plugin.client.fetch_image_payload.assert_awaited_once_with(
            "https://imgheybox.max-c.com/cookie.jpg",
            max_bytes=main_module.ACCOUNT_AVATAR_MAX_BYTES,
        )

    async def test_account_avatar_rejects_tiny_placeholder(self) -> None:
        plugin = self.plugin()
        plugin._account_profile = {
            "avatar": "https://imgheybox.max-c.com/avatar.png"
        }
        plugin._account_avatar_source = ""
        plugin._account_avatar_data_url = ""
        plugin._account_avatar_updated_at = 0.0
        plugin._account_avatar_error = ""
        plugin._account_avatar_lock = asyncio.Lock()
        plugin.client = SimpleNamespace(
            fetch_image_payload=AsyncMock(
                return_value=ImagePayload(
                    name="avatar.png",
                    mimetype="image/png",
                    data=b"placeholder",
                    width=1,
                    height=1,
                )
            )
        )

        with self.assertRaisesRegex(XhhError, "异常小"):
            await plugin._refresh_account_avatar()

    async def test_account_avatar_tries_next_candidate_after_tiny_image(self) -> None:
        plugin = self.plugin()
        plugin.auth = AuthInfo(
            cookie=(
                "user_heybox_id=102013423; "
                "avatar=https%253A%252F%252Fimgheybox.max-c.com%252Fcookie.jpg"
            ),
            heybox_id="102013423",
        )
        plugin._account_profile = {
            "avatar": "https://imgheybox.max-c.com/tiny.png"
        }
        plugin._account_avatar_source = ""
        plugin._account_avatar_data_url = ""
        plugin._account_avatar_updated_at = 0.0
        plugin._account_avatar_error = ""
        plugin._account_avatar_lock = asyncio.Lock()
        plugin.client = SimpleNamespace(
            fetch_image_payload=AsyncMock(
                side_effect=[
                    ImagePayload(
                        name="tiny.png",
                        mimetype="image/png",
                        data=b"tiny",
                        width=1,
                        height=1,
                    ),
                    ImagePayload(
                        name="avatar.jpg",
                        mimetype="image/jpeg",
                        data=b"avatar",
                        width=64,
                        height=64,
                    ),
                ]
            )
        )

        data_url = await plugin._refresh_account_avatar()

        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        self.assertEqual(plugin.client.fetch_image_payload.await_count, 2)
        self.assertEqual(
            plugin._account_avatar_source,
            "https://imgheybox.max-c.com/cookie.jpg",
        )

    async def test_web_account_avatar_returns_cached_data_url(self) -> None:
        plugin = self.plugin()
        plugin.auth = AuthInfo(cookie="cookie=value", heybox_id="102013423")
        plugin._auth_invalid = False
        plugin._account_avatar_updated_at = 123.0
        plugin._refresh_account_avatar = AsyncMock(
            return_value="data:image/png;base64,YXZhdGFy"
        )
        fake_request = SimpleNamespace(args={"refresh": "1"})

        with (
            patch.object(main_module, "request", fake_request),
            patch.object(main_module, "jsonify", side_effect=lambda value: value),
        ):
            result = await plugin.web_account_avatar()

        self.assertTrue(result["ok"])
        self.assertEqual(result["data_url"], "data:image/png;base64,YXZhdGFy")
        plugin._refresh_account_avatar.assert_awaited_once_with(force=True)

    async def test_account_profile_normalizes_level_and_clears_stale_error(
        self,
    ) -> None:
        plugin = self.plugin()
        plugin.auth = AuthInfo(cookie="cookie=value", heybox_id="102013423")
        plugin._account_profile = {"nickname": "旧名字"}
        plugin._account_profile_updated_at = 0.0
        plugin._account_profile_error = "上次读取失败"
        plugin._account_profile_lock = asyncio.Lock()
        plugin.client = SimpleNamespace(
            fetch_user_profile=AsyncMock(
                return_value={
                    "status": "ok",
                    "result": {"account_detail": {"level": "Lv.42"}},
                }
            ),
            set_auth=lambda auth: None,
        )

        profile = await plugin._refresh_account_profile(force=True)

        self.assertEqual(profile["level"], "42")
        self.assertEqual(plugin._account_profile_error, "")

    async def test_account_profile_empty_success_clears_stale_error(self) -> None:
        plugin = self.plugin()
        plugin.auth = AuthInfo(cookie="cookie=value", heybox_id="102013423")
        plugin._account_profile = {"nickname": "保留名字"}
        plugin._account_profile_updated_at = 0.0
        plugin._account_profile_error = "上次读取失败"
        plugin._account_profile_lock = asyncio.Lock()
        plugin.client = SimpleNamespace(
            fetch_user_profile=AsyncMock(return_value={"status": "ok", "result": {}}),
            set_auth=lambda auth: None,
        )

        profile = await plugin._refresh_account_profile(force=True)

        self.assertEqual(profile["nickname"], "保留名字")
        self.assertEqual(plugin._account_profile_error, "")

    async def test_status_command_forces_account_profile_refresh(self) -> None:
        plugin = self.plugin()
        plugin._status_text = AsyncMock(return_value="状态")
        event = SimpleNamespace(plain_result=lambda value: value)

        results = [item async for item in plugin.xhh_status(event)]

        self.assertEqual(results, ["状态"])
        plugin._status_text.assert_awaited_once_with(refresh_account=True)

    async def test_web_status_can_force_account_refresh(self) -> None:
        plugin = self.plugin()
        plugin._web_status_payload = AsyncMock(return_value={"ok": True})
        fake_request = SimpleNamespace(args={"refresh_account": "1"})

        with (
            patch.object(main_module, "request", fake_request),
            patch.object(main_module, "jsonify", side_effect=lambda value: value),
        ):
            result = await plugin.web_status()

        self.assertTrue(result["ok"])
        plugin._web_status_payload.assert_awaited_once_with(refresh_account=True)

    def test_dashboard_loads_account_avatar_through_plugin_api(self) -> None:
        page = (
            Path(__file__).parents[1] / "pages" / "dashboard" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('class="account-avatar-shell"', page)
        self.assertIn('getApi("account/avatar"', page)
        self.assertIn("function applyAccountAvatar", page)
        self.assertIn("account-avatar-fallback", page)
        self.assertIn('shell.dataset.loaded = "true"', page)
        self.assertIn('image.naturalWidth < 8', page)
        self.assertIn('.account-avatar-shell[data-loaded="true"]', page)
        self.assertIn(
            'avatar || `account:${account.heybox_id || account.nickname || "authenticated"}`',
            page,
        )
        self.assertIn('const avatarSlot = account.state === "authenticated"', page)
        self.assertNotIn('referrerpolicy="no-referrer" onerror="this.remove()"', page)

    def test_dashboard_loads_bridge_before_inline_application(self) -> None:
        page = (
            Path(__file__).parents[1] / "pages" / "dashboard" / "index.html"
        ).read_text(encoding="utf-8")
        bridge_tag = '<script src="/api/plugin/page/bridge-sdk.js"></script>'
        application_marker = "<script>\n      let bridge = null;"

        self.assertIn(bridge_tag, page)
        self.assertIn(application_marker, page)
        self.assertLess(page.index(bridge_tag), page.index(application_marker))
        self.assertIn("const pageBridge = await getBridge();", page)
        self.assertNotIn("const bridge = window.AstrBotPluginPage;", page)

    def test_qr_code_uses_valid_canvas_matrix(self) -> None:
        payload = XhhRobotPlugin._qr_matrix_payload(
            "https://api.xiaoheihe.cn/account/qr_login/?app=web&qr=state"
        )

        size = payload["size"]
        rows = payload["rows"]
        self.assertGreaterEqual(size, 21)
        self.assertEqual(len(rows), size)
        self.assertTrue(all(len(row) == size for row in rows))
        self.assertTrue(all(set(row) <= {"0", "1"} for row in rows))
        self.assertEqual(set(rows[0]), {"0"})

    def test_dashboard_renders_qr_as_canvas_instead_of_data_image(self) -> None:
        page = (
            Path(__file__).parents[1] / "pages" / "dashboard" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("function renderQrMatrix(qrPayload)", page)
        self.assertIn("payload.qr_matrix", page)
        self.assertIn('document.createElement("canvas")', page)
        self.assertNotIn("payload.qr_image", page)

    async def test_login_payload_can_restore_qr_and_keeps_expiry_on_poll(
        self,
    ) -> None:
        plugin = self.plugin()
        plugin._login_task = SimpleNamespace(done=lambda: False)
        plugin._web_login_challenge = SimpleNamespace(
            qr_url="https://api.xiaoheihe.cn/account/qr_login/?app=web&qr=state",
            expires_in=120,
        )
        plugin._web_login_started_at = 1000.0
        plugin.auth = None
        plugin._auth_source = "none"

        initial = await plugin._web_login_payload(include_qr=True)
        polled = await plugin._web_login_payload(include_qr=False)

        self.assertIn("qr_matrix", initial)
        self.assertNotIn("qr_matrix", polled)
        self.assertEqual(initial["expires_at"], 1120.0)
        self.assertEqual(polled["expires_at"], 1120.0)

    async def test_login_session_requests_qr_for_page_refresh(self) -> None:
        plugin = self.plugin()
        plugin._worker_task = None
        plugin._web_login_payload = AsyncMock(return_value={"ok": True})

        with patch.object(main_module, "jsonify", side_effect=lambda value: value):
            result = await plugin.web_login_session()

        plugin._web_login_payload.assert_awaited_once_with(include_qr=True)
        self.assertFalse(result["worker_running"])

    def test_clear_login_uses_in_page_confirmation_dialog(self) -> None:
        page = (
            Path(__file__).parents[1] / "pages" / "dashboard" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('id="clearLoginDialog"', page)
        self.assertIn('id="confirmClearLoginButton"', page)
        self.assertNotIn("window.confirm(", page)
        self.assertIn(
            'byId("clearLoginButton").addEventListener("click", openClearLoginDialog);',
            page,
        )
        self.assertIn(
            'byId("confirmClearLoginButton").addEventListener("click", clearLogin);',
            page,
        )

    def test_dashboard_exposes_runtime_and_queue_emergency_controls(self) -> None:
        page = (
            Path(__file__).parents[1] / "pages" / "dashboard" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('id="startRuntimeButton"', page)
        self.assertIn('id="stopRuntimeButton"', page)
        self.assertIn('id="clearQueueButton"', page)
        self.assertIn('id="clearQueueDialog"', page)
        self.assertIn('id="clearQueueLinkId"', page)
        self.assertIn('postApi("runtime/start", {})', page)
        self.assertIn('postApi("runtime/stop", {})', page)
        self.assertIn('postApi("queue/clear", {', page)
        self.assertIn("消息游标、失败记录、SQLite 归档、统计和登录信息不会删除", page)
        self.assertNotIn("window.confirm(", page)

    def test_dashboard_pagination_shows_current_and_total_pages(self) -> None:
        page = (
            Path(__file__).parents[1] / "pages" / "dashboard" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("function paginationSummary(", page)
        self.assertIn("Math.ceil(safeTotal / safeLimit)", page)
        self.assertIn(
            "第 ${fmtNumber(currentPage)} / ${fmtNumber(totalPages)} 页", page
        )
        self.assertIn('id="paginationText">0 条记录，共 0 页', page)
        self.assertIn(
            'byId("paginationText").textContent = paginationSummary(',
            page,
        )

    async def test_web_login_clear_returns_updated_state_and_cookie_warning(
        self,
    ) -> None:
        plugin = self.plugin(
            {
                "webui": {"enabled": True},
                "account": {"cookie": "user_pkey=manual"},
            }
        )
        plugin._clear_login_credentials = AsyncMock()

        with patch.object(main_module, "jsonify", side_effect=lambda value: value):
            result = await plugin.web_login_clear()

        plugin._clear_login_credentials.assert_awaited_once()
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "logged_out")
        self.assertIn("手动 Cookie", result["message"])

    async def test_queue_clear_api_requires_confirmation_and_returns_counts(
        self,
    ) -> None:
        plugin = self.plugin()
        mention = Mention(
            message_id=1,
            comment_id=2,
            root_comment_id=2,
            link_id=3,
            user_id=4,
            comment_text="积压评论",
            source="own_post_comment",
        )
        plugin.store = SimpleNamespace(
            cancel_queue=AsyncMock(
                side_effect=[
                    (
                        [mention],
                        {
                            "cancelled_total": 1,
                            "cancelled_pending": 1,
                            "cancelled_dispatched": 0,
                            "sending_preserved": 1,
                            "queue_remaining": 1,
                        },
                    ),
                    (
                        [],
                        {
                            "cancelled_total": 0,
                            "cancelled_pending": 0,
                            "cancelled_dispatched": 0,
                            "sending_preserved": 1,
                            "queue_remaining": 1,
                        },
                    ),
                ]
            )
        )
        plugin._cycle_lock = asyncio.Lock()
        plugin._archive_received = AsyncMock()
        plugin._web_status_payload = AsyncMock(return_value={"ok": True})
        fake_request = SimpleNamespace(
            get_json=AsyncMock(return_value={"confirm": True, "link_id": 3})
        )

        with (
            patch.object(main_module, "request", fake_request),
            patch.object(main_module, "jsonify", side_effect=lambda value: value),
        ):
            result = await plugin.web_queue_clear()

        self.assertTrue(result["ok"])
        self.assertEqual(result["cancelled_total"], 1)
        self.assertEqual(result["sending_preserved"], 1)
        self.assertEqual(plugin.store.cancel_queue.await_count, 2)
        plugin._archive_received.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
