from __future__ import annotations

import asyncio
import copy
import unittest

from astrbot_plugin_xhhrobot.main import XhhRobotPlugin
from astrbot_plugin_xhhrobot.models import AuthInfo, Mention
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
    def __init__(self, pages: list[list[Mention]]) -> None:
        self.pages = pages

    async def fetch_mentions(self, *, offset: int, limit: int) -> list[Mention]:
        page = offset // limit
        return self.pages[page] if page < len(self.pages) else []


class BlockingReplyClient:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def send_reply(self, **kwargs: object) -> None:
        self.started.set()
        await asyncio.Event().wait()


class PluginPollingTests(unittest.IsolatedAsyncioTestCase):
    async def make_plugin(self, config: dict, pages: list[list[Mention]]) -> XhhRobotPlugin:
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
            "notifications": {"notify_on_reply": False},
        }
        plugin.store = store
        plugin.client = client

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


if __name__ == "__main__":
    unittest.main()
