from __future__ import annotations

import asyncio
import copy
import unittest

from astrbot_plugin_xhhrobot.models import Mention
from astrbot_plugin_xhhrobot.state_store import StateStore


class MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    async def load(self, key: str, default: object) -> object:
        return copy.deepcopy(self.values.get(key, default))

    async def save(self, key: str, value: object) -> None:
        self.values[key] = copy.deepcopy(value)


class StateStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.backend = MemoryBackend()
        self.store = StateStore(
            load_value=self.backend.load, save_value=self.backend.save
        )
        await self.store.initialize()
        self.mention = Mention(
            message_id=101,
            comment_id=202,
            root_comment_id=200,
            link_id=303,
            user_id=404,
            comment_text="@bot 你好",
        )

    async def test_ingest_deduplicates_and_completes(self) -> None:
        counts = await self.store.ingest(
            newest_message_id=101, queued=[self.mention], ignored=[]
        )
        self.assertEqual(counts, (1, 0, []))
        counts = await self.store.ingest(
            newest_message_id=101, queued=[self.mention], ignored=[]
        )
        self.assertEqual(counts, (0, 0, []))

        due = await self.store.due_items(limit=10)
        self.assertEqual(due, [self.mention])
        await self.store.mark_done(101, "你好呀")

        snapshot = await self.store.snapshot()
        self.assertEqual(snapshot["queue"], {})
        self.assertEqual(snapshot["stats"]["replied"], 1)
        history = await self.store.conversation_history(
            link_id=303, user_id=404, turns=3
        )
        self.assertEqual(history, [{"user": "@bot 你好", "assistant": "你好呀"}])

    async def test_sending_record_recovers_as_uncertain(self) -> None:
        await self.store.ingest(
            newest_message_id=101, queued=[self.mention], ignored=[]
        )
        await self.store.mark_sending(101)

        recovered = StateStore(
            load_value=self.backend.load, save_value=self.backend.save
        )
        await recovered.initialize()
        snapshot = await recovered.snapshot()
        self.assertEqual(snapshot["queue"], {})
        self.assertEqual(snapshot["dead"]["101"]["reason"], "uncertain_delivery")

        self.assertEqual(await recovered.retry_dead(include_uncertain=False), 0)
        self.assertEqual(await recovered.retry_dead(include_uncertain=True), 1)
        self.assertEqual(len(await recovered.due_items(limit=10)), 1)

    async def test_dispatch_and_delivery_claims_are_atomic(self) -> None:
        await self.store.ingest(
            newest_message_id=101, queued=[self.mention], ignored=[]
        )

        claims = await asyncio.gather(
            self.store.mark_dispatched(101),
            self.store.mark_dispatched(101),
        )

        self.assertEqual(sum(claims), 1)
        self.assertEqual(await self.store.item_status(101), "dispatched")
        self.assertTrue(await self.store.mark_sending(101))
        self.assertFalse(await self.store.mark_sending(101))

    async def test_retry_exhaustion_moves_to_dead_queue(self) -> None:
        await self.store.ingest(
            newest_message_id=101, queued=[self.mention], ignored=[]
        )
        pending = await self.store.mark_retry(
            101, "failure", max_attempts=1, delay_seconds=0
        )
        self.assertFalse(pending)
        snapshot = await self.store.snapshot()
        self.assertEqual(snapshot["dead"]["101"]["reason"], "retry_exhausted")

    async def test_overlapping_comment_notification_is_promoted_to_mention(
        self,
    ) -> None:
        ordinary = Mention(
            message_id=102,
            comment_id=self.mention.comment_id,
            root_comment_id=self.mention.root_comment_id,
            link_id=self.mention.link_id,
            user_id=self.mention.user_id,
            comment_text="普通评论入口",
            source="own_post_comment",
        )
        await self.store.ingest(
            newest_message_id=102,
            queued=[ordinary],
            ignored=[],
            source="own_post_comment",
        )
        counts = await self.store.ingest(
            newest_message_id=101,
            queued=[self.mention],
            ignored=[],
            source="mention",
        )

        self.assertEqual(counts, (0, 0, []))
        due = await self.store.due_items(limit=10)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].message_id, 102)
        self.assertEqual(due[0].source, "mention")
        self.assertEqual(due[0].comment_text, self.mention.comment_text)

    async def test_replied_target_blocks_duplicate_message_id(self) -> None:
        await self.store.ingest(
            newest_message_id=101, queued=[self.mention], ignored=[]
        )
        await self.store.mark_done(101, "已回复")
        duplicate = Mention(
            message_id=999,
            comment_id=self.mention.comment_id,
            root_comment_id=self.mention.root_comment_id,
            link_id=self.mention.link_id,
            user_id=self.mention.user_id,
            comment_text="同一条评论的另一条通知",
            source="own_post_comment",
        )

        counts = await self.store.ingest(
            newest_message_id=999,
            queued=[duplicate],
            ignored=[],
            source="own_post_comment",
        )

        self.assertEqual(counts, (0, 0, []))
        self.assertEqual(await self.store.due_items(limit=10), [])

    async def test_own_post_observation_applies_limit_to_queued_mention(self) -> None:
        await self.store.seed_own_post_reply_counts({self.mention.link_id: 1})
        await self.store.ingest(
            newest_message_id=self.mention.message_id,
            queued=[self.mention],
            ignored=[],
            source="mention",
            max_own_post_replies_per_post=1,
        )
        ordinary = Mention(
            message_id=102,
            comment_id=self.mention.comment_id,
            root_comment_id=self.mention.root_comment_id,
            link_id=self.mention.link_id,
            user_id=self.mention.user_id,
            comment_text="同一评论的自己帖子通知",
            source="own_post_comment",
        )

        queued, ignored, skipped = await self.store.ingest(
            newest_message_id=102,
            queued=[ordinary],
            ignored=[],
            source="own_post_comment",
            max_own_post_replies_per_post=1,
        )

        self.assertEqual((queued, ignored), (0, 0))
        self.assertEqual([item.message_id for item in skipped], [102])
        self.assertEqual(await self.store.due_items(limit=10), [])

    async def test_own_post_reply_limit_reserves_and_persists_capacity(self) -> None:
        comments = [
            Mention(
                message_id=200 + index,
                comment_id=300 + index,
                root_comment_id=300 + index,
                link_id=500,
                user_id=600 + index,
                comment_text=f"评论 {index}",
                source="own_post_comment",
            )
            for index in range(3)
        ]

        queued, ignored, skipped = await self.store.ingest(
            newest_message_id=202,
            queued=comments,
            ignored=[],
            source="own_post_comment",
            max_own_post_replies_per_post=2,
        )

        self.assertEqual((queued, ignored), (2, 0))
        self.assertEqual([item.message_id for item in skipped], [202])
        self.assertEqual(len(await self.store.due_items(limit=10)), 2)
        await self.store.mark_sending(
            200,
            max_own_post_replies_per_post=2,
        )
        await self.store.mark_done(200, "回复 0")
        snapshot = await self.store.snapshot()
        self.assertEqual(snapshot["own_post_reply_counts"], {"500": 1})

        fourth = Mention(
            message_id=203,
            comment_id=303,
            root_comment_id=303,
            link_id=500,
            user_id=603,
            comment_text="评论 3",
            source="own_post_comment",
        )
        queued, ignored, skipped = await self.store.ingest(
            newest_message_id=203,
            queued=[fourth],
            ignored=[],
            source="own_post_comment",
            max_own_post_replies_per_post=2,
        )
        self.assertEqual((queued, ignored), (0, 0))
        self.assertEqual([item.message_id for item in skipped], [203])

    async def test_limit_enforcement_cancels_excess_but_preserves_sending(self) -> None:
        comments = [
            Mention(
                message_id=300 + index,
                comment_id=400 + index,
                root_comment_id=400 + index,
                link_id=700,
                user_id=800 + index,
                comment_text=f"积压 {index}",
                source="own_post_comment",
            )
            for index in range(3)
        ]
        await self.store.ingest(
            newest_message_id=302,
            queued=comments,
            ignored=[],
            source="own_post_comment",
        )
        await self.store.mark_sending(300)
        skipped = await self.store.enforce_own_post_reply_limit(1)

        self.assertEqual({item.message_id for item in skipped}, {301, 302})
        snapshot = await self.store.snapshot()
        self.assertEqual(set(snapshot["queue"]), {"300"})
        self.assertEqual(snapshot["queue"]["300"]["status"], "sending")

    async def test_cancel_queue_can_target_one_post_and_preserves_sending(self) -> None:
        first = Mention(
            message_id=401,
            comment_id=501,
            root_comment_id=501,
            link_id=801,
            user_id=901,
            comment_text="帖子一待处理",
            source="own_post_comment",
        )
        sending = Mention(
            message_id=402,
            comment_id=502,
            root_comment_id=502,
            link_id=801,
            user_id=902,
            comment_text="帖子一发送中",
            source="own_post_comment",
        )
        other = Mention(
            message_id=403,
            comment_id=503,
            root_comment_id=503,
            link_id=802,
            user_id=903,
            comment_text="帖子二",
            source="own_post_comment",
        )
        await self.store.ingest(
            newest_message_id=403,
            queued=[first, sending, other],
            ignored=[],
            source="own_post_comment",
        )
        await self.store.mark_sending(402)

        cancelled, result = await self.store.cancel_queue(link_id=801)

        self.assertEqual([item.message_id for item in cancelled], [401])
        self.assertEqual(result["cancelled_total"], 1)
        self.assertEqual(result["sending_preserved"], 1)
        snapshot = await self.store.snapshot()
        self.assertEqual(set(snapshot["queue"]), {"402", "403"})
        self.assertEqual(snapshot["last_comment_message_id"], 403)

    async def test_old_state_starts_comment_stream_uninitialized(self) -> None:
        self.backend.values["runtime_state_v1"] = {
            "version": 2,
            "initialized": True,
            "last_message_id": 88,
        }
        migrated = StateStore(
            load_value=self.backend.load, save_value=self.backend.save
        )
        await migrated.initialize()

        snapshot = await migrated.snapshot()
        self.assertTrue(snapshot["initialized"])
        self.assertEqual(snapshot["last_message_id"], 88)
        self.assertFalse(snapshot["comments_initialized"])
        self.assertEqual(snapshot["last_comment_message_id"], 0)

    async def test_browse_sending_record_recovers_as_uncertain(self) -> None:
        await self.store.record_browse(
            link_id=501,
            title="发送中的帖子",
            author_id="123",
            status="sending",
            comment_text="可能已经发出的评论",
        )

        recovered = StateStore(
            load_value=self.backend.load, save_value=self.backend.save
        )
        await recovered.initialize()
        snapshot = await recovered.snapshot()

        self.assertEqual(
            snapshot["auto_browse"]["records"]["501"]["status"], "uncertain"
        )
        self.assertEqual(snapshot["auto_browse"]["stats"]["uncertain"], 1)


if __name__ == "__main__":
    unittest.main()
