from __future__ import annotations

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
        self.store = StateStore(load_value=self.backend.load, save_value=self.backend.save)
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
        counts = await self.store.ingest(newest_message_id=101, queued=[self.mention], ignored=[])
        self.assertEqual(counts, (1, 0))
        counts = await self.store.ingest(newest_message_id=101, queued=[self.mention], ignored=[])
        self.assertEqual(counts, (0, 0))

        due = await self.store.due_items(limit=10)
        self.assertEqual(due, [self.mention])
        await self.store.mark_done(101, "你好呀")

        snapshot = await self.store.snapshot()
        self.assertEqual(snapshot["queue"], {})
        self.assertEqual(snapshot["stats"]["replied"], 1)
        history = await self.store.conversation_history(link_id=303, user_id=404, turns=3)
        self.assertEqual(history, [{"user": "@bot 你好", "assistant": "你好呀"}])

    async def test_sending_record_recovers_as_uncertain(self) -> None:
        await self.store.ingest(newest_message_id=101, queued=[self.mention], ignored=[])
        await self.store.mark_sending(101)

        recovered = StateStore(load_value=self.backend.load, save_value=self.backend.save)
        await recovered.initialize()
        snapshot = await recovered.snapshot()
        self.assertEqual(snapshot["queue"], {})
        self.assertEqual(snapshot["dead"]["101"]["reason"], "uncertain_delivery")

        self.assertEqual(await recovered.retry_dead(include_uncertain=False), 0)
        self.assertEqual(await recovered.retry_dead(include_uncertain=True), 1)
        self.assertEqual(len(await recovered.due_items(limit=10)), 1)

    async def test_retry_exhaustion_moves_to_dead_queue(self) -> None:
        await self.store.ingest(newest_message_id=101, queued=[self.mention], ignored=[])
        pending = await self.store.mark_retry(101, "failure", max_attempts=1, delay_seconds=0)
        self.assertFalse(pending)
        snapshot = await self.store.snapshot()
        self.assertEqual(snapshot["dead"]["101"]["reason"], "retry_exhausted")


if __name__ == "__main__":
    unittest.main()

