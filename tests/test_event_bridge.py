from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import MessageType

from astrbot_plugin_xhhrobot.event_bridge import (
    EventTarget,
    XhhMessageEvent,
    build_comment_message,
    build_direct_message,
)


class EventBridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.image_path = self.root / "reply.png"
        self.image_path.write_bytes(b"test")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_inbound_messages_use_namespaced_users_and_image_chains(self) -> None:
        comment = build_comment_message(
            self_user_id="42",
            session_id="post!100",
            message_id="7",
            sender_id="99",
            sender_name="Alice",
            message_text="评论正文",
            image_urls=("https://example.com/a.png",),
            link_id=100,
            link_title="帖子标题",
            timestamp=123,
            raw_message={},
        )
        direct = build_direct_message(
            self_user_id="42",
            session_id="dm!99",
            message_id="8",
            sender_id="99",
            sender_name="Alice",
            message_text="私信正文",
            image_urls=("https://example.com/b.png",),
            timestamp=124,
            raw_message={},
        )

        self.assertEqual(comment.type, MessageType.GROUP_MESSAGE)
        self.assertEqual(comment.sender.user_id, "xhh:99")
        self.assertEqual(comment.self_id, "xhh:42")
        self.assertEqual(comment.session_id, "post!100")
        self.assertEqual(sum(isinstance(item, Image) for item in comment.message), 1)
        self.assertEqual(direct.type, MessageType.FRIEND_MESSAGE)
        self.assertEqual(direct.session_id, "dm!99")
        self.assertIsNone(direct.group)

    async def test_outbound_comment_preserves_text_and_full_image_chain(self) -> None:
        message_obj = build_comment_message(
            self_user_id="42",
            session_id="post!100",
            message_id="7",
            sender_id="99",
            sender_name="Alice",
            message_text="评论正文",
            image_urls=(),
            link_id=100,
            link_title="帖子标题",
            timestamp=123,
            raw_message={},
        )
        client = AsyncMock()
        callbacks = {
            "start": AsyncMock(),
            "sent": AsyncMock(),
            "error": AsyncMock(),
            "empty": AsyncMock(),
        }
        event = XhhMessageEvent(
            message_obj=message_obj,
            target=EventTarget(
                kind="comment",
                source="mention",
                event_key="comment:100:7",
                raw_user_id="99",
                link_id=100,
                comment_id=7,
                root_comment_id=7,
            ),
            client=client,
            max_reply_chars=5,
            max_outgoing_images=2,
            max_local_image_bytes=1024,
            allowed_local_roots=(self.root,),
            direct_message_cooldown_seconds=0,
            clean_text=lambda value: value.strip(),
            on_send_start=callbacks["start"],
            on_sent=callbacks["sent"],
            on_send_error=callbacks["error"],
            on_empty=callbacks["empty"],
        )
        chain = MessageChain(
            [
                Plain(" 123456 "),
                Image.fromURL("https://example.com/reply.png"),
                Image(file=str(self.image_path)),
            ]
        )

        with patch.object(AstrMessageEvent, "send", new=AsyncMock()):
            await event.send(chain)

        client.send_reply.assert_awaited_once_with(
            text="12345",
            link_id=100,
            reply_id=7,
            root_id=7,
            image_sources=["https://example.com/reply.png", str(self.image_path)],
            allowed_local_roots=(self.root,),
            max_local_image_bytes=1024,
        )
        callbacks["start"].assert_awaited_once()
        callbacks["sent"].assert_awaited_once()
        callbacks["error"].assert_not_awaited()
        self.assertEqual(event.delivery_future.result().status, "sent")

    async def test_outbound_direct_message_uses_chain_sender(self) -> None:
        message_obj = build_direct_message(
            self_user_id="42",
            session_id="dm!99",
            message_id="8",
            sender_id="99",
            sender_name="Alice",
            message_text="私信正文",
            image_urls=(),
            timestamp=124,
            raw_message={},
        )
        client = AsyncMock()
        event = XhhMessageEvent(
            message_obj=message_obj,
            target=EventTarget(
                kind="direct_message",
                source="direct_message",
                event_key="dm:99:8",
                raw_user_id="99",
            ),
            client=client,
            max_reply_chars=100,
            max_outgoing_images=1,
            max_local_image_bytes=1024,
            allowed_local_roots=(self.root,),
            direct_message_cooldown_seconds=3,
            clean_text=lambda value: value,
            on_send_start=AsyncMock(),
            on_sent=AsyncMock(),
            on_send_error=AsyncMock(),
            on_empty=AsyncMock(),
        )

        with patch.object(AstrMessageEvent, "send", new=AsyncMock()):
            await event.send(
                MessageChain(
                    [Plain("收到"), Image.fromURL("https://example.com/a.png")]
                )
            )

        client.send_direct_message_chain.assert_awaited_once_with(
            user_id="99",
            text="收到",
            image_sources=["https://example.com/a.png"],
            allowed_local_roots=(self.root,),
            max_local_image_bytes=1024,
            cooldown_seconds=3,
        )


if __name__ == "__main__":
    unittest.main()
