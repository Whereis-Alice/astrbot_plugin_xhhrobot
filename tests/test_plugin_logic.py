from __future__ import annotations

import asyncio
import copy
import unittest

from astrbot_plugin_xhhrobot.main import XhhRobotPlugin
from astrbot_plugin_xhhrobot.models import (
    AuthInfo,
    Mention,
    NotificationPage,
    PostContext,
)
from astrbot_plugin_xhhrobot.state_store import StateStore
from astrbot_plugin_xhhrobot.xhh_client import XhhError


class MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    async def load(self, key: str, default: object) -> object:
        return copy.deepcopy(self.values.get(key, default))

    async def save(self, key: str, value: object) -> None:
        self.values[key] = copy.deepcopy(value)


class FakeClient:
    def __init__(
        self,
        pages: list[list[Mention]],
        comment_pages: list[NotificationPage] | None = None,
    ) -> None:
        self.pages = pages
        self.comment_pages = comment_pages or []

    async def fetch_mentions(self, *, offset: int, limit: int) -> list[Mention]:
        page = offset // limit
        return self.pages[page] if page < len(self.pages) else []

    async def fetch_mentions_page(self, *, offset: int, limit: int) -> NotificationPage:
        items = await self.fetch_mentions(offset=offset, limit=limit)
        return NotificationPage(
            items=tuple(items),
            message_ids=tuple(item.message_id for item in items),
            raw_count=len(items),
        )

    async def fetch_comment_messages_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> NotificationPage:
        page = offset // limit
        if page < len(self.comment_pages):
            return self.comment_pages[page]
        return NotificationPage()


class BlockingReplyClient:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def send_reply(self, **kwargs: object) -> None:
        self.started.set()
        await asyncio.Event().wait()


class RecordingReplyClient:
    def __init__(self, post: PostContext) -> None:
        self.post = post
        self.sent: list[dict[str, object]] = []

    async def fetch_post_context(self, link_id: int) -> PostContext:
        return self.post

    async def send_reply(self, **kwargs: object) -> None:
        self.sent.append(dict(kwargs))


class RecordingNotificationContext:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, umo: str, chain: object) -> None:
        self.sent.append((umo, chain.get_plain_text()))


class PluginPollingTests(unittest.IsolatedAsyncioTestCase):
    async def make_plugin(
        self, config: dict, pages: list[list[Mention]]
    ) -> XhhRobotPlugin:
        backend = MemoryBackend()
        store = StateStore(load_value=backend.load, save_value=backend.save)
        await store.initialize()
        plugin = object.__new__(XhhRobotPlugin)
        plugin.config = config
        plugin.store = store
        plugin.client = FakeClient(pages)
        plugin.auth = AuthInfo(cookie="cookie=value", heybox_id="999")
        return plugin

    @staticmethod
    def mention(message_id: int, user_id: int) -> Mention:
        return Mention(
            message_id=message_id,
            comment_id=message_id + 100,
            root_comment_id=message_id + 90,
            link_id=500,
            user_id=user_id,
            comment_text="hello",
        )

    async def test_first_poll_only_sets_baseline_by_default(self) -> None:
        plugin = await self.make_plugin(
            {
                "polling": {"page_size": 20, "max_pages_per_poll": 10},
                "filters": {"allow_all_users": True},
            },
            [[self.mention(12, 1), self.mention(11, 1)]],
        )
        result = await plugin._poll_mentions()
        snapshot = await plugin.store.snapshot()
        self.assertEqual(result.queued, 0)
        self.assertEqual(snapshot["last_message_id"], 12)
        self.assertEqual(snapshot["queue"], {})

    async def test_later_poll_applies_allow_and_block_lists(self) -> None:
        plugin = await self.make_plugin(
            {
                "polling": {"page_size": 20, "max_pages_per_poll": 10},
                "filters": {
                    "allow_all_users": False,
                    "allowed_user_ids": ["1", "2"],
                    "blocked_user_ids": ["2"],
                },
            },
            [[self.mention(12, 1), self.mention(11, 2), self.mention(10, 1)]],
        )
        await plugin.store.set_initial_cursor(10)
        result = await plugin._poll_mentions()
        due = await plugin.store.due_items(limit=10)
        self.assertEqual(result.queued, 1)
        self.assertEqual(result.ignored, 1)
        self.assertEqual([item.message_id for item in due], [12])

    async def test_page_limit_does_not_advance_cursor_or_drop_backlog(self) -> None:
        plugin = await self.make_plugin(
            {
                "polling": {"page_size": 2, "max_pages_per_poll": 1},
                "filters": {"allow_all_users": True},
            },
            [[self.mention(14, 1), self.mention(13, 1)]],
        )
        await plugin.store.set_initial_cursor(10)
        with self.assertRaises(XhhError):
            await plugin._poll_mentions()
        snapshot = await plugin.store.snapshot()
        self.assertEqual(snapshot["last_message_id"], 10)
        self.assertEqual(snapshot["queue"], {})

    async def test_page_limit_is_safe_when_initial_cursor_is_zero(self) -> None:
        plugin = await self.make_plugin(
            {
                "polling": {"page_size": 2, "max_pages_per_poll": 1},
                "filters": {"allow_all_users": True},
            },
            [[self.mention(2, 1), self.mention(1, 1)]],
        )
        await plugin.store.set_initial_cursor(0)
        with self.assertRaises(XhhError):
            await plugin._poll_mentions()
        snapshot = await plugin.store.snapshot()
        self.assertEqual(snapshot["last_message_id"], 0)
        self.assertEqual(snapshot["queue"], {})

    async def test_cancellation_during_send_moves_item_to_uncertain(self) -> None:
        backend = MemoryBackend()
        store = StateStore(load_value=backend.load, save_value=backend.save)
        await store.initialize()
        mention = self.mention(12, 1)
        await store.ingest(newest_message_id=12, queued=[mention], ignored=[])

        client = BlockingReplyClient()
        plugin = object.__new__(XhhRobotPlugin)
        plugin.config = {
            "ai": {"include_post_context": False, "history_turns": 0},
            "filters": {"allow_all_users": True},
            "notifications": {"notify_on_reply": False},
        }
        plugin.store = store
        plugin.client = client
        plugin.auth = AuthInfo(cookie="cookie=value", heybox_id="999")

        async def generate_reply(*args: object) -> str:
            return "reply"

        plugin._generate_reply = generate_reply  # type: ignore[method-assign]
        task = asyncio.create_task(plugin._process_mention(mention))
        await client.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        snapshot = await store.snapshot()
        self.assertEqual(snapshot["queue"], {})
        self.assertEqual(snapshot["dead"]["12"]["reason"], "uncertain_delivery")

    async def test_ordinary_comment_on_own_post_replies_without_mention(self) -> None:
        backend = MemoryBackend()
        store = StateStore(load_value=backend.load, save_value=backend.save)
        await store.initialize()
        comment = Mention(
            message_id=21,
            comment_id=121,
            root_comment_id=121,
            link_id=500,
            user_id=1,
            comment_text="普通评论",
            source="own_post_comment",
        )
        await store.ingest(
            newest_message_id=21,
            queued=[comment],
            ignored=[],
            source="own_post_comment",
        )
        client = RecordingReplyClient(PostContext(title="帖子", author_id="999"))
        plugin = object.__new__(XhhRobotPlugin)
        plugin.config = {
            "ai": {"include_post_context": False, "history_turns": 0},
            "filters": {
                "allow_all_users": True,
                "reply_to_own_post_comments": True,
            },
            "notifications": {
                "umo": "test:FriendMessage:notify",
                "notify_on_reply": True,
            },
        }
        plugin.store = store
        plugin.client = client
        plugin.auth = AuthInfo(cookie="cookie=value", heybox_id="999")
        plugin.context = RecordingNotificationContext()

        async def generate_reply(*args: object) -> str:
            return "自动回复"

        plugin._generate_reply = generate_reply  # type: ignore[method-assign]
        outcome = await plugin._process_mention(comment)

        self.assertEqual(outcome, "replied")
        self.assertEqual(len(client.sent), 1)
        self.assertEqual(client.sent[0]["reply_id"], 121)
        self.assertEqual(len(plugin.context.sent), 1)
        umo, notification = plugin.context.sent[0]
        self.assertEqual(umo, "test:FriendMessage:notify")
        self.assertTrue(notification.startswith("小黑盒自动回复成功"))
        self.assertIn("类型：自己帖子下的普通评论", notification)
        self.assertIn("对方评论：\n普通评论", notification)
        self.assertIn("Bot 回复：\n自动回复", notification)
        self.assertIn("消息 ID：21", notification)
        self.assertIn("帖子 ID：500", notification)
        self.assertIn("评论 ID：121", notification)
        self.assertIn("根评论 ID：121", notification)
        self.assertIn("用户 ID：1", notification)
        self.assertNotIn("[小黑盒机器人]", notification)

    async def test_ordinary_comment_on_someone_elses_post_is_skipped(self) -> None:
        backend = MemoryBackend()
        store = StateStore(load_value=backend.load, save_value=backend.save)
        await store.initialize()
        comment = Mention(
            message_id=22,
            comment_id=122,
            root_comment_id=122,
            link_id=500,
            user_id=1,
            comment_text="普通评论",
            source="own_post_comment",
        )
        await store.ingest(
            newest_message_id=22,
            queued=[comment],
            ignored=[],
            source="own_post_comment",
        )
        client = RecordingReplyClient(PostContext(title="帖子", author_id="888"))
        plugin = object.__new__(XhhRobotPlugin)
        plugin.config = {
            "ai": {"include_post_context": False, "history_turns": 0},
            "filters": {
                "allow_all_users": True,
                "reply_to_own_post_comments": True,
            },
        }
        plugin.store = store
        plugin.client = client
        plugin.auth = AuthInfo(cookie="cookie=value", heybox_id="999")

        outcome = await plugin._process_mention(comment)

        self.assertEqual(outcome, "skipped")
        self.assertEqual(client.sent, [])
        snapshot = await store.snapshot()
        self.assertEqual(
            snapshot["recent"][-1]["reason"],
            "普通评论不在机器人自己的帖子下",
        )

    async def test_comment_stream_uses_independent_cursor(self) -> None:
        comment = Mention(
            message_id=12,
            comment_id=112,
            root_comment_id=112,
            link_id=500,
            user_id=1,
            comment_text="没有 @",
            source="own_post_comment",
        )
        page = NotificationPage(items=(comment,), message_ids=(12, 11), raw_count=2)
        plugin = await self.make_plugin(
            {
                "polling": {"page_size": 20, "max_pages_per_poll": 10},
                "filters": {
                    "allow_all_users": True,
                    "reply_to_own_post_comments": True,
                },
            },
            [],
        )
        plugin.client = FakeClient([], [page])
        await plugin.store.set_initial_cursor(10, source="own_post_comment")

        result = await plugin._poll_own_post_comments()
        snapshot = await plugin.store.snapshot()

        self.assertEqual(result.queued, 1)
        self.assertEqual(snapshot["last_message_id"], 0)
        self.assertEqual(snapshot["last_comment_message_id"], 12)


if __name__ == "__main__":
    unittest.main()
