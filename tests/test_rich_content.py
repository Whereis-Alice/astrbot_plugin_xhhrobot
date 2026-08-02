from __future__ import annotations

import unittest

from astrbot_plugin_xhhrobot.rich_content import (
    RichContentError,
    content_blocks_plain_text,
    normalize_plain_text,
    normalize_rich_content_blocks,
    parse_inbound_content_blocks,
)


class RichContentTests(unittest.TestCase):
    def test_plain_text_converts_common_model_break_tags(self) -> None:
        self.assertEqual(
            normalize_plain_text("第一行<br>第二行<br />第三行"),
            "第一行\n第二行\n第三行",
        )
        self.assertEqual(normalize_plain_text("第一行 <tag> 第二行"), "第一行 <tag> 第二行")

    def test_normalizes_safe_blocks_without_losing_order(self) -> None:
        blocks = normalize_rich_content_blocks(
            [
                {"type": "text", "text": "第一段\n第二行"},
                {
                    "type": "html",
                    "html": '<p><strong>重点</strong> <a href="https://example.com/x">链接</a></p>',
                },
                {"type": "image", "url": "https://images.example/pic.png"},
            ],
            max_text_chars=1000,
        )

        self.assertEqual(blocks[0], {"type": "text", "text": "第一段\n第二行"})
        self.assertEqual(
            blocks[1],
            {
                "type": "html",
                "text": '<p><strong>重点</strong> <a href="https://example.com/x">链接</a></p>',
            },
        )
        self.assertEqual(
            blocks[2],
            {"type": "image", "url": "https://images.example/pic.png"},
        )
        self.assertEqual(content_blocks_plain_text(blocks), "第一段\n第二行\n重点 链接")

    def test_rejects_unsafe_or_unsupported_html(self) -> None:
        values = (
            '<script>alert("x")</script>',
            '<p onclick="alert(1)">内容</p>',
            '<a href="javascript:alert(1)">内容</a>',
            '<a href="http://127.0.0.1/private">内容</a>',
            '<img src="https://images.example/pic.png">',
        )
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(RichContentError):
                    normalize_rich_content_blocks(
                        [{"type": "html", "html": value}],
                        max_text_chars=1000,
                    )

    def test_inbound_blocks_keep_safe_formatting_and_plain_text(self) -> None:
        blocks = parse_inbound_content_blocks(
            '[{"type":"text","text":"<p>正文<br><strong>重点</strong><script>bad</script></p>"},'
            '{"type":"img","url":"//cdn.example/image.png"}]'
        )

        self.assertEqual(blocks[0]["type"], "html")
        self.assertEqual(blocks[0]["text"], "<p>正文<br><strong>重点</strong></p>")
        self.assertEqual(blocks[1], {"type": "image", "url": "https://cdn.example/image.png"})
        self.assertEqual(content_blocks_plain_text(blocks), "正文\n重点")


if __name__ == "__main__":
    unittest.main()
