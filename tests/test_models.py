from __future__ import annotations

import unittest

from astrbot_plugin_xhhrobot.models import Mention


class MentionParsingTests(unittest.TestCase):
    def test_comment_html_is_converted_to_plain_text(self) -> None:
        mention = Mention.from_mapping(
            {
                "message_id": 1,
                "comment_a_id": 2,
                "linkid": 3,
                "userid_a": 4,
                "comment_a_text": (
                    '<a data-user-id="102013423" href="heybox://user">'
                    "@战网逃兵爱丽丝</a>"
                ),
            }
        )

        self.assertEqual(mention.comment_text, "@战网逃兵爱丽丝")

    def test_comment_html_preserves_breaks_and_decodes_entities(self) -> None:
        mention = Mention.from_mapping(
            {
                "message_id": 1,
                "comment_a_id": 2,
                "linkid": 3,
                "userid_a": 4,
                "comment_a_text": "第一行<br>第二行&nbsp;&amp;&nbsp;第三段",
                "comment_b_text": "<p>原回复</p><div>&lt;收到&gt;</div>",
            }
        )

        self.assertEqual(mention.comment_text, "第一行\n第二行 & 第三段")
        self.assertEqual(mention.replied_text, "原回复\n<收到>")

    def test_persisted_mentions_are_cleaned_when_loaded(self) -> None:
        mention = Mention.from_dict(
            {
                "comment_text": '<a href="#">@Alice</a>',
                "replied_text": "回复&nbsp;内容",
            }
        )

        self.assertEqual(mention.comment_text, "@Alice")
        self.assertEqual(mention.replied_text, "回复 内容")

    def test_nested_comment_image_groups_are_extracted(self) -> None:
        mention = Mention.from_mapping(
            {
                "message_id": 1,
                "comment_a_id": 2,
                "linkid": 3,
                "userid_a": 4,
                "comment_a": {
                    "images": [
                        {"url": "https://cdn.example/current.jpg"},
                        {"url": "https://cdn.example/shared.jpg"},
                    ]
                },
                "comment_b": {
                    "imgs": [
                        {"url": "https://cdn.example/quoted.jpg"},
                        {"url": "https://cdn.example/shared.jpg"},
                    ]
                },
            }
        )

        self.assertEqual(
            mention.image_urls,
            (
                "https://cdn.example/current.jpg",
                "https://cdn.example/shared.jpg",
            ),
        )
        self.assertEqual(
            mention.replied_image_urls,
            (
                "https://cdn.example/quoted.jpg",
                "https://cdn.example/shared.jpg",
            ),
        )


if __name__ == "__main__":
    unittest.main()
