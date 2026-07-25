from __future__ import annotations

import asyncio
import copy
import time
import unittest

from astrbot_plugin_xhhrobot.auto_browse import (
    CommentDecision,
    parse_comment_decision,
    parse_selection,
)
from astrbot_plugin_xhhrobot.main import XhhRobotPlugin
from astrbot_plugin_xhhrobot.models import AuthInfo, FeedPost, PostContext
from astrbot_plugin_xhhrobot.state_store import StateStore


class MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    async def load(self, key: str, default: object) -> object:
        return copy.deepcopy(self.values.get(key, default))

    async def save(self, key: str, value: object) -> None:
        self.values[key] = copy.deepcopy(value)


class BrowseClient:
    def __init__(self, *, block_send: bool = False) -> None:
        self.feed_calls = 0
        self.comments: list[dict[str, object]] = []
        self.send_started = asyncio.Event()
        self.block_send = block_send
        self.posts = [
            FeedPost(
                link_id=501,
                title="值得讨论的帖子",
                description="一段有实际内容的摘要",
                author_id="123",
                author_name="作者",
            )
        ]

    async def fetch_feed_posts(self, **kwargs: object) -> list[FeedPost]:
        self.feed_calls += 1
        return list(self.posts)

    async def fetch_post_context(self, link_id: int) -> PostContext:
        return PostContext(
            title="值得讨论的帖子",
            author_id="123",
            author_name="作者",
            text_parts=("这里是一段足够长、可以形成具体观点的帖子正文。",),
        )

    async def create_comment(self, **kwargs: object) -> None:
        self.comments.append(dict(kwargs))
        self.send_started.set()
        if self.block_send:
            await asyncio.Event().wait()


class AutoBrowseTests(unittest.IsolatedAsyncioTestCase):
    async def make_plugin(
        self,
        *,
        dry_run: bool = False,
        block_send: bool = False,
        daily_limit: int = 3,
    ) -> tuple[XhhRobotPlugin, BrowseClient, StateStore]:
        backend = MemoryBackend()
        store = StateStore(load_value=backend.load, save_value=backend.save)
        await store.initialize()
        client = BrowseClient(block_send=block_send)
        plugin = object.__new__(XhhRobotPlugin)
        plugin.config = {
            "ai": {"include_post_images": False},
            "auto_browse": {
                "dry_run": dry_run,
                "candidate_limit": 10,
                "max_evaluations_per_run": 3,
                "max_comments_per_run": 1,
                "max_comments_per_24h": daily_limit,
                "min_post_chars": 10,
                "max_post_chars": 20000,
                "min_comment_chars": 8,
                "max_comment_chars": 300,
                "notify_on_comment": False,
            },
        }
        plugin.store = store
        plugin.client = client
        plugin.auth = AuthInfo(cookie="cookie=value", heybox_id="999")
        plugin._auth_invalid = False
        plugin._cycle_lock = asyncio.Lock()
        plugin._stop_event = asyncio.Event()

        async def select_post(candidates: list[FeedPost]) -> tuple[int, str]:
            return candidates[0].link_id, "符合人设兴趣"

        async def decide_comment(*args: object, **kwargs: object) -> CommentDecision:
            return CommentDecision(
                action="comment",
                comment="这个切入点很具体，正文里的取舍也值得继续聊。",
                reason="可以针对正文交流",
            )

        plugin._select_browse_post = select_post  # type: ignore[method-assign]
        plugin._decide_browse_comment = decide_comment  # type: ignore[method-assign]
        return plugin, client, store

    async def test_selects_post_and_publishes_comment(self) -> None:
        plugin, client, store = await self.make_plugin()

        result = await plugin._run_auto_browse()

        self.assertEqual(result.commented, 1)
        self.assertEqual(len(client.comments), 1)
        self.assertEqual(client.comments[0]["link_id"], 501)
        snapshot = await store.snapshot()
        self.assertEqual(
            snapshot["auto_browse"]["records"]["501"]["status"], "commented"
        )

    async def test_preview_generates_but_never_sends(self) -> None:
        plugin, client, store = await self.make_plugin(dry_run=True)

        result = await plugin._run_auto_browse()

        self.assertEqual(result.dry_run, 1)
        self.assertEqual(client.comments, [])
        snapshot = await store.snapshot()
        self.assertEqual(snapshot["auto_browse"]["records"]["501"]["status"], "dry_run")

    async def test_daily_limit_blocks_before_feed_fetch(self) -> None:
        plugin, client, store = await self.make_plugin(daily_limit=1)
        await store.record_browse(
            link_id=400,
            title="已评论",
            author_id="111",
            status="commented",
            comment_text="之前的评论",
            now=time.time(),
        )

        result = await plugin._run_auto_browse()

        self.assertEqual(result.commented, 0)
        self.assertEqual(client.feed_calls, 0)
        self.assertIn("额度已满", result.notes[0])

    async def test_cancellation_during_send_records_uncertain(self) -> None:
        plugin, client, store = await self.make_plugin(block_send=True)
        task = asyncio.create_task(plugin._run_auto_browse())
        await client.send_started.wait()

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        snapshot = await store.snapshot()
        record = snapshot["auto_browse"]["records"]["501"]
        self.assertEqual(record["status"], "uncertain")
        self.assertEqual(snapshot["auto_browse"]["stats"]["uncertain"], 1)

    def test_model_json_parsers_reject_out_of_contract_values(self) -> None:
        with self.assertRaises(ValueError):
            parse_selection('{"link_id":999,"reason":"越界"}', {501})
        with self.assertRaises(ValueError):
            parse_comment_decision('{"action":"publish","comment":"内容"}')
        with self.assertRaises(ValueError):
            parse_comment_decision('{"action":"comment","comment":""}')


if __name__ == "__main__":
    unittest.main()
