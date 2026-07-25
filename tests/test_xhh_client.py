from __future__ import annotations

import json
import unittest
from collections import deque
from http.cookies import SimpleCookie
from typing import Any

from astrbot_plugin_xhhrobot.models import AuthInfo, QrChallenge
from astrbot_plugin_xhhrobot.xhh_client import XhhClient


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._raw = json.dumps(payload, ensure_ascii=False)
        self.status = status
        self.cookies: dict[str, Any] = {}
        self.headers: dict[str, str] = {}

    async def text(self, errors: str = "replace") -> str:
        return self._raw


class FakeRequestContext:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = deque(responses)
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.closed = False
        self.cookie_jar: list[Any] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeRequestContext:
        self.requests.append((method, url, kwargs))
        return FakeRequestContext(self.responses.popleft())


class XhhClientTests(unittest.IsolatedAsyncioTestCase):
    def make_client(
        self, responses: list[FakeResponse]
    ) -> tuple[XhhClient, FakeSession]:
        session = FakeSession(responses)
        client = XhhClient(
            api_base_url="https://api.xiaoheihe.cn",
            reply_base_url="https://workshopapi.xiaoheihe.cn",
            version="999.0.4",
            web_version="2.5",
            device_id="device",
            auth=AuthInfo(cookie="user_heybox_id=42; token=value", heybox_id="42"),
            session=session,  # type: ignore[arg-type]
        )
        return client, session

    async def test_fetch_mentions_parses_upstream_fields(self) -> None:
        client, session = self.make_client(
            [
                FakeResponse(
                    {
                        "stat": "ok",
                        "result": {
                            "messages": [
                                {
                                    "message_id": 11,
                                    "comment_a_id": 12,
                                    "root_comment_id": 10,
                                    "linkid": 13,
                                    "userid_a": 14,
                                    "comment_a_text": "@bot hello",
                                }
                            ]
                        },
                    }
                )
            ]
        )
        mentions = await client.fetch_mentions(offset=0, limit=20)
        self.assertEqual(mentions[0].message_id, 11)
        self.assertEqual(mentions[0].comment_text, "@bot hello")
        params = session.requests[0][2]["params"]
        self.assertEqual(params["message_type"], "16")
        self.assertIn("hkey", params)
        self.assertEqual(
            session.requests[0][2]["headers"]["Cookie"],
            "user_heybox_id=42; token=value",
        )

    async def test_fetch_comment_messages_filters_mixed_page_but_keeps_raw_count(
        self,
    ) -> None:
        client, session = self.make_client(
            [
                FakeResponse(
                    {
                        "status": "ok",
                        "result": {
                            "messages": [
                                {
                                    "message_id": 31,
                                    "message_type": 1,
                                    "comment_a_id": 41,
                                    "comment_a_text": "普通评论",
                                    "link": {"linkid": 51},
                                    "user_a": {"userid": 61},
                                },
                                {"message_id": 30, "message_type": 4},
                                {
                                    "message_id": 29,
                                    "message_type": "2",
                                    "comment_id": 39,
                                    "content": "回复评论",
                                    "link": {"link_id": 49},
                                    "user_a": {"heybox_id": 59},
                                },
                            ]
                        },
                    }
                )
            ]
        )

        page = await client.fetch_comment_messages_page(offset=0, limit=20)

        self.assertEqual(page.raw_count, 3)
        self.assertEqual(page.message_ids, (31, 30, 29))
        self.assertEqual([item.message_id for item in page.items], [31, 29])
        self.assertEqual(page.items[0].source, "own_post_comment")
        self.assertEqual(page.items[0].link_id, 51)
        self.assertEqual(page.items[0].user_id, 61)
        self.assertEqual(page.items[0].root_comment_id, 41)
        params = session.requests[0][2]["params"]
        self.assertNotIn("message_type", params)
        self.assertEqual(params["no_more"], "false")

    def test_feed_parser_handles_nested_links_and_deduplicates(self) -> None:
        payload = {
            "result": {
                "feeds": [
                    {
                        "link": {
                            "linkid": "701",
                            "title": "第一帖",
                            "description": "摘要",
                            "user": {"userid": "81", "username": "甲"},
                            "topics": [{"name": "硬件"}],
                            "hashtags": [{"name": "测试"}],
                            "up": 9,
                            "comment_num": 4,
                        }
                    },
                    {"link": {"linkid": 701, "title": "重复项"}},
                    {"link_id": 702, "title": "第二帖"},
                ]
            }
        }

        posts = XhhClient.parse_feed_posts(payload, limit=20)

        self.assertEqual([post.link_id for post in posts], [701, 702])
        self.assertEqual(posts[0].author_id, "81")
        self.assertEqual(posts[0].author_name, "甲")
        self.assertEqual(posts[0].topics, ("硬件",))
        self.assertEqual(posts[0].tags, ("测试",))
        self.assertEqual(posts[0].likes, 9)
        self.assertEqual(posts[0].comments, 4)

    async def test_fetch_post_extracts_text_images_topics_and_tags(self) -> None:
        content = json.dumps(
            [
                {"type": "text", "text": "正文"},
                {"type": "image", "url": "//cdn.example/image.jpg"},
            ],
            ensure_ascii=False,
        )
        client, _ = self.make_client(
            [
                FakeResponse(
                    {
                        "status": "ok",
                        "result": {
                            "link": {
                                "title": "标题",
                                "user": {"userid": "42", "username": "机器人"},
                                "text": content,
                                "topics": [{"name": "游戏"}],
                                "hashtags": [{"name": "测试"}],
                            }
                        },
                    }
                )
            ]
        )
        post = await client.fetch_post_context(99)
        self.assertEqual(post.title, "标题")
        self.assertEqual(post.author_id, "42")
        self.assertEqual(post.author_name, "机器人")
        self.assertEqual(post.body_text, "正文")
        self.assertEqual(post.image_urls, ("https://cdn.example/image.jpg",))
        self.assertEqual(post.topics, ("游戏",))
        self.assertEqual(post.tags, ("测试",))

    async def test_send_reply_uses_workshop_api_and_form_fields(self) -> None:
        client, session = self.make_client(
            [FakeResponse({"status": "ok", "msg": "done"})]
        )
        receipt = await client.send_reply(text="回复", link_id=1, reply_id=2, root_id=3)
        self.assertEqual(receipt.status, "ok")
        method, url, kwargs = session.requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://workshopapi.xiaoheihe.cn/bbs/app/comment/create")
        self.assertEqual(kwargs["data"]["text"], "回复")
        self.assertEqual(kwargs["data"]["reply_id"], "2")

    async def test_qr_login_does_not_send_old_auth_and_builds_new_auth(self) -> None:
        client, session = self.make_client(
            [
                FakeResponse(
                    {
                        "status": "ok",
                        "result": {
                            "qr_url": "https://api.xiaoheihe.cn/account/qr_login/?app=xhh&qr=state",
                            "expire": 120,
                        },
                    }
                ),
                FakeResponse(
                    {
                        "status": "ok",
                        "result": {"error": "ok", "nickname": "tester"},
                    }
                ),
            ]
        )
        challenge = await client.begin_qr_login()
        first_request = session.requests[0][2]
        self.assertNotIn("Cookie", first_request["headers"])
        self.assertNotIn("heybox_id", first_request["params"])
        self.assertEqual(challenge.state_params, {"app": "xhh", "qr": "state"})

        cookies = SimpleCookie()
        cookies.load("user_heybox_id=88; session=abc")
        session.cookie_jar = list(cookies.values())
        result = await client.poll_qr_login(
            QrChallenge(challenge.qr_url, challenge.state_params, 120)
        )
        self.assertEqual(result.state, "success")
        self.assertIsNotNone(result.auth)
        assert result.auth is not None
        self.assertEqual(result.auth.heybox_id, "88")
        self.assertEqual(result.auth.nickname, "tester")
        self.assertIn("x_xhh_tokenid=", result.auth.cookie)

    async def test_publish_post_copies_images_and_uses_verified_form(self) -> None:
        client, session = self.make_client(
            [
                FakeResponse(
                    {
                        "status": "ok",
                        "result": {"url": "https://cdn.xiaoheihe.cn/copied.jpg"},
                    }
                ),
                FakeResponse({"status": "ok", "result": {"link_id": 321}}),
            ]
        )

        payload = await client.publish_post(
            title="测试标题",
            body="第一行 <tag>\n第二行",
            description="测试摘要",
            topic_ids=["7214", "18745"],
            hashtags=["AstrBot", "测试"],
            image_urls=["https://images.example/source.jpg"],
        )

        self.assertEqual(payload["result"]["link_id"], 321)
        copy_method, copy_url, copy_kwargs = session.requests[0]
        self.assertEqual(copy_method, "GET")
        self.assertEqual(
            copy_url,
            "https://api.xiaoheihe.cn/bbs/app/api/qcloud/cos/copy/image/by/url",
        )
        self.assertEqual(
            copy_kwargs["params"]["target_url"], "https://images.example/source.jpg"
        )

        method, url, kwargs = session.requests[1]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.xiaoheihe.cn/bbs/app/api/link/post")
        self.assertEqual(kwargs["data"]["post_type"], "1")
        self.assertEqual(kwargs["data"]["topic_ids"], "7214,18745")
        self.assertEqual(json.loads(kwargs["data"]["hashtags"]), ["AstrBot", "测试"])
        content = json.loads(kwargs["data"]["text"])
        self.assertEqual(content[0]["type"], "html")
        self.assertEqual(content[0]["text"], "第一行 &lt;tag&gt;<br>第二行")
        self.assertEqual(
            content[1],
            {"type": "img", "url": "https://cdn.xiaoheihe.cn/copied.jpg"},
        )

    async def test_search_profile_and_sub_comments_use_expected_parameters(
        self,
    ) -> None:
        client, session = self.make_client(
            [
                FakeResponse({"status": "ok", "result": {"items": []}}),
                FakeResponse({"status": "ok", "result": {"account_detail": {}}}),
                FakeResponse({"status": "ok", "result": {"comments": []}}),
            ]
        )

        await client.search("AstrBot", search_type="link", offset=10, limit=5)
        await client.fetch_user_profile("88")
        await client.fetch_sub_comments(123, last_value=456)

        self.assertEqual(
            session.requests[0][1],
            "https://api.xiaoheihe.cn/bbs/app/api/general/search/v1",
        )
        self.assertEqual(session.requests[0][2]["params"]["search_type"], "link")
        self.assertEqual(session.requests[0][2]["params"]["offset"], "10")
        self.assertEqual(session.requests[1][2]["params"]["userid"], "88")
        self.assertEqual(session.requests[2][2]["params"]["root_comment_id"], "123")
        self.assertEqual(session.requests[2][2]["params"]["lastval"], "456")

    async def test_direct_message_uses_ack_and_copied_image(self) -> None:
        client, session = self.make_client(
            [
                FakeResponse(
                    {
                        "status": "ok",
                        "result": {"preview_url": "https://cdn.xiaoheihe.cn/dm.png"},
                    }
                ),
                FakeResponse({"status": "ok", "result": {"msg_id": "message-1"}}),
            ]
        )

        await client.send_direct_message(
            user_id="99",
            text="你好",
            image_url="https://images.example/dm.png",
        )

        method, url, kwargs = session.requests[1]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.xiaoheihe.cn/chatroom/v2/msg/user")
        self.assertEqual(kwargs["params"]["to_user_id"], "99")
        self.assertEqual(kwargs["data"]["msg"], "你好")
        self.assertEqual(kwargs["data"]["msg_type"], "6")
        self.assertEqual(kwargs["data"]["img"], "https://cdn.xiaoheihe.cn/dm.png")
        self.assertTrue(kwargs["data"]["heybox_ack_id"])


if __name__ == "__main__":
    unittest.main()
