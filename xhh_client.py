from __future__ import annotations

import asyncio
import html
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qsl, unquote, urlparse

import aiohttp

from .models import (
    AuthInfo,
    Mention,
    PostContext,
    QrChallenge,
    QrPollResult,
    ReplyReceipt,
)
from .signing import generate_xhh_token, get_request_keys


class XhhError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        terminal: bool = False,
        auth_required: bool = False,
        delivery_uncertain: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.terminal = terminal
        self.auth_required = auth_required
        self.delivery_uncertain = delivery_uncertain
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class _JsonResponse:
    payload: dict[str, Any]
    cookies: dict[str, str]


class XhhClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        reply_base_url: str,
        version: str,
        web_version: str,
        device_id: str,
        timeout_seconds: int = 20,
        auth: AuthInfo | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.reply_base_url = reply_base_url.rstrip("/")
        self.version = version
        self.web_version = web_version
        self.device_id = device_id
        self.timeout_seconds = max(5, timeout_seconds)
        self.auth = auth
        self._session = session
        self._owns_session = session is None
        self._direct_message_ack_id = int(time.time() * 1000) % 1_000_000_000

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout, cookie_jar=aiohttp.CookieJar())
            self._owns_session = True

    async def close(self) -> None:
        if self._session is not None and self._owns_session and not self._session.closed:
            await self._session.close()

    def set_auth(self, auth: AuthInfo | None) -> None:
        self.auth = auth

    async def begin_qr_login(self) -> QrChallenge:
        response = await self._request_json(
            "GET",
            "/account/get_qrcode_url/",
            auth_required=False,
            allow_api_failure=False,
        )
        result = self._result_mapping(response.payload)
        qr_url = str(result.get("qr_url") or "").strip()
        if not qr_url:
            raise XhhError("小黑盒没有返回登录二维码地址。", retryable=False)
        query = dict(parse_qsl(urlparse(qr_url).query, keep_blank_values=True))
        expires_in = self._to_int(result.get("expire"), 120)
        return QrChallenge(qr_url=qr_url, state_params=query, expires_in=max(30, expires_in))

    async def poll_qr_login(self, challenge: QrChallenge) -> QrPollResult:
        response = await self._request_json(
            "GET",
            "/account/qr_state/",
            params=challenge.state_params,
            auth_required=False,
            allow_api_failure=True,
        )
        result = self._result_mapping(response.payload)
        state = str(result.get("error") or "").strip().lower()
        message = str(result.get("error_msg") or response.payload.get("msg") or "").strip()

        if state == "ok":
            cookies = self._all_session_cookies()
            cookies.update(response.cookies)
            cookies.setdefault("x_xhh_tokenid", generate_xhh_token())
            heybox_id = str(cookies.get("user_heybox_id") or "").strip()
            cookie_header = self._format_cookie_header(cookies)
            if not cookie_header:
                return QrPollResult("failed", "登录成功但没有取得 Cookie。")
            auth = AuthInfo(
                cookie=cookie_header,
                heybox_id=heybox_id,
                nickname=str(result.get("nickname") or "").strip(),
                login_at=int(time.time()),
            )
            self.set_auth(auth)
            return QrPollResult("success", message or "登录成功。", auth)

        combined = f"{state} {message}".lower()
        if any(word in combined for word in ("expire", "expired", "过期", "失效")):
            return QrPollResult("expired", message or "二维码已过期。")
        if any(word in combined for word in ("cancel", "拒绝", "取消")):
            return QrPollResult("failed", message or "登录已取消。")
        return QrPollResult("pending", message or "等待扫码确认。")

    async def fetch_mentions(self, *, offset: int = 0, limit: int = 20) -> list[Mention]:
        payload = await self.fetch_messages(
            message_type="16",
            offset=offset,
            limit=limit,
        )
        response = _JsonResponse(payload=payload, cookies={})
        result = self._result_mapping(response.payload)
        raw_messages = result.get("messages")
        if not isinstance(raw_messages, list):
            return []
        mentions = [Mention.from_mapping(item) for item in raw_messages if isinstance(item, Mapping)]
        return [mention for mention in mentions if mention.message_id > 0]

    async def fetch_post_context(self, link_id: int) -> PostContext:
        response = await self._request_json(
            "GET",
            "/bbs/app/link/tree",
            params={"h_src": "", "link_id": str(link_id)},
            auth_required=True,
        )
        result = self._result_mapping(response.payload)
        link = result.get("link")
        if not isinstance(link, Mapping):
            raise XhhError("帖子详情响应中缺少 link 数据。", terminal=True, retryable=False)

        text_parts: list[str] = []
        image_urls: list[str] = []
        raw_content = link.get("text")
        content_items: Any = raw_content
        if isinstance(raw_content, str):
            try:
                content_items = json.loads(raw_content)
            except json.JSONDecodeError:
                content_items = [{"type": "text", "text": raw_content}]
        if isinstance(content_items, Mapping):
            content_items = [content_items]
        if isinstance(content_items, list):
            for item in content_items:
                if not isinstance(item, Mapping):
                    if str(item).strip():
                        text_parts.append(str(item).strip())
                    continue
                item_type = str(item.get("type") or "text").lower()
                text = str(item.get("text") or "").strip()
                url = self._normalise_media_url(str(item.get("url") or item.get("src") or "").strip())
                if item_type in {"text", "html"} and text:
                    text_parts.append(text)
                elif url:
                    image_urls.append(url)
                elif text:
                    text_parts.append(text)

        return PostContext(
            title=str(link.get("title") or "").strip(),
            text_parts=tuple(text_parts),
            image_urls=tuple(dict.fromkeys(image_urls)),
            topics=tuple(self._extract_names(link.get("topics"))),
            tags=tuple(self._extract_names(link.get("hashtags"))),
        )

    async def fetch_messages(
        self,
        *,
        message_type: str = "16",
        list_type: str = "0",
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        params = {
            "list_type": str(list_type or "0"),
            "offset": str(max(0, offset)),
            "limit": str(max(1, min(50, limit))),
            "no_more": "false",
        }
        if message_type:
            params["message_type"] = str(message_type)
        response = await self._request_json(
            "GET",
            "/bbs/app/user/message",
            params=params,
            auth_required=True,
        )
        return response.payload

    async def fetch_feed(self, *, offset: int = 0, pull: bool = False) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/app/feeds",
            params={
                "offset": str(max(0, offset)),
                "pull": "1" if pull else "0",
                "use_history": "0" if pull else "1",
                "is_first": "1" if offset <= 0 else "0",
            },
            auth_required=True,
        )
        return response.payload

    async def search(
        self,
        query: str,
        *,
        search_type: str = "link",
        offset: int = 0,
        limit: int = 10,
        time_range: str = "",
        filter_tag: str = "",
    ) -> dict[str, Any]:
        allowed_types = {"general", "link", "game", "user", "hashtag", "mall"}
        normalized_type = search_type if search_type in allowed_types else "link"
        params = {
            "q": query,
            "search_type": normalized_type,
            "offset": str(max(0, offset)),
            "limit": str(max(1, min(30, limit))),
            "is_pull_down": "0",
            "dw": "628",
        }
        if time_range:
            params["time_range"] = time_range
        if filter_tag:
            params["filter_tag"] = filter_tag
        response = await self._request_json(
            "GET",
            "/bbs/app/api/general/search/v1",
            params=params,
            auth_required=True,
        )
        return response.payload

    async def fetch_post(
        self,
        link_id: int,
        *,
        page: int = 1,
        limit: int = 20,
        sort_filter: str = "hot",
        owner_only: bool = False,
    ) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/app/link/tree",
            params={
                "h_src": "",
                "link_id": str(link_id),
                "is_first": "1" if page <= 1 else "0",
                "page": str(max(1, page)),
                "index": str(max(1, page)),
                "limit": str(max(1, min(50, limit))),
                "owner_only": "1" if owner_only else "0",
                "sort_filter": sort_filter if sort_filter in {"hot", "time"} else "hot",
            },
            auth_required=True,
        )
        return response.payload

    async def fetch_sub_comments(
        self,
        root_comment_id: int,
        *,
        last_value: int = 0,
    ) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/app/comment/sub/comments",
            params={
                "root_comment_id": str(root_comment_id),
                "lastval": str(max(0, last_value)),
            },
            auth_required=True,
        )
        return response.payload

    async def fetch_user_profile(self, user_id: str) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/app/profile/user/profile",
            params={"userid": user_id},
            auth_required=True,
        )
        return response.payload

    async def fetch_user_posts(
        self,
        user_id: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/web/profile/post/links",
            params={
                "userid": user_id,
                "offset": str(max(0, offset)),
                "limit": str(max(1, min(50, limit))),
                "post_type": "1",
            },
            auth_required=True,
        )
        return response.payload

    async def fetch_user_comments(
        self,
        user_id: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/web/profile/post/comments",
            params={
                "userid": user_id,
                "offset": str(max(0, offset)),
                "limit": str(max(1, min(50, limit))),
            },
            auth_required=True,
        )
        return response.payload

    async def fetch_user_events(
        self,
        user_id: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/app/profile/events",
            params={
                "userid": user_id,
                "list_type": "moment",
                "offset": str(max(0, offset)),
                "limit": str(max(1, min(50, limit))),
            },
            auth_required=True,
        )
        return response.payload

    async def fetch_user_relations(
        self,
        user_id: str,
        *,
        relation: str,
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        path = (
            "/bbs/app/profile/follower/list"
            if relation == "followers"
            else "/bbs/app/profile/following/list"
        )
        response = await self._request_json(
            "GET",
            path,
            params={
                "userid": user_id,
                "offset": str(max(0, offset)),
                "limit": str(max(1, min(50, limit))),
            },
            auth_required=True,
        )
        return response.payload

    async def fetch_topics(self) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/app/api/topic/index/",
            params={"type": "list", "is_post": "1", "post_tab": "1"},
            auth_required=True,
        )
        return response.payload

    async def search_topics(self, query: str) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/app/api/post_editor/topic_selection/search",
            params={"q": query},
            auth_required=True,
        )
        return response.payload

    async def fetch_favorite_folders(self) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/app/profile/fav/folders",
            auth_required=True,
        )
        return response.payload

    async def fetch_emojis(self) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "/bbs/app/api/emojis/list",
            auth_required=True,
        )
        return response.payload

    async def fetch_direct_message_entries(
        self,
        *,
        limit: int = 20,
        strangers: bool = False,
    ) -> dict[str, Any]:
        if strangers:
            path = "/chat/stranger_messages/"
            params = {
                "offset": "0",
                "limit": str(max(1, min(50, limit))),
            }
        else:
            path = "/bbs/app/user/message"
            params = {
                "list_type": "2",
                "offset": "0",
                "limit": str(max(1, min(50, limit))),
            }
        response = await self._request_json(
            "GET",
            path,
            params=params,
            auth_required=True,
        )
        return response.payload

    async def fetch_direct_messages(
        self,
        user_id: str,
        *,
        limit: int = 30,
        sequence: str = "",
    ) -> dict[str, Any]:
        params = {
            "to_user_id": user_id,
            "offset": "0",
            "limit": str(max(1, min(50, limit))),
        }
        if sequence:
            params["seq"] = sequence
        response = await self._request_json(
            "GET",
            "/chatroom/v2/msg/user",
            params=params,
            auth_required=True,
        )
        return response.payload

    async def copy_image_by_url(self, image_url: str) -> str:
        response = await self._request_json(
            "GET",
            "/bbs/app/api/qcloud/cos/copy/image/by/url",
            params={"target_url": image_url, "watermark": "false"},
            auth_required=True,
        )
        result = self._result_mapping(response.payload)
        copied = str(result.get("url") or result.get("preview_url") or "").strip()
        if not copied:
            raise XhhError("小黑盒图片转存响应中缺少 URL。", retryable=False)
        return self._normalise_media_url(copied)

    async def publish_post(
        self,
        *,
        title: str,
        body: str,
        description: str = "",
        topic_ids: list[str] | None = None,
        hashtags: list[str] | None = None,
        image_urls: list[str] | None = None,
    ) -> dict[str, Any]:
        copied_images = [await self.copy_image_by_url(url) for url in image_urls or []]
        content: list[dict[str, str]] = []
        if body:
            escaped_body = html.escape(body).replace("\n", "<br>")
            content.append({"type": "html", "text": escaped_body})
        content.extend({"type": "img", "url": url} for url in copied_images)
        payload = await self._write_json(
            "/bbs/app/api/link/post",
            data={
                "title": title,
                "desc": (description or body)[:100],
                "post_type": "1",
                "words_count": str(len(body)),
                "topic_ids": ",".join(topic_ids or []),
                "hashtags": json.dumps(hashtags or [], ensure_ascii=False, separators=(",", ":")),
                "text": json.dumps(content, ensure_ascii=False, separators=(",", ":")),
                "link_tag": "11",
            },
        )
        result = self._result_mapping(payload)
        link_id = payload.get("link_id") or result.get("link_id")
        if not str(link_id or "").strip():
            raise XhhError("小黑盒发帖响应中缺少 link_id，无法确认帖子已发布。", retryable=False)
        return payload

    async def create_comment(
        self,
        *,
        text: str,
        link_id: int,
        reply_id: int = -1,
        root_id: int = -1,
        image_urls: list[str] | None = None,
    ) -> dict[str, Any]:
        copied_images = [await self.copy_image_by_url(url) for url in image_urls or []]
        data = {
            "is_cy": "0",
            "link_id": str(link_id),
            "reply_id": str(reply_id),
            "root_id": str(root_id),
            "text": text,
        }
        if copied_images:
            data["imgs"] = ";".join(copied_images)
        return await self._write_json(
            "/bbs/app/comment/create",
            data=data,
            use_reply_api=True,
        )

    async def set_favorite(
        self,
        *,
        link_id: int,
        favorite: bool,
        folder_id: str = "",
    ) -> dict[str, Any]:
        if self.auth is None or not self.auth.heybox_id:
            raise XhhError("登录凭据中缺少 heybox_id。", auth_required=True, retryable=False)
        data = {
            "link_id": str(link_id),
            "userid": self.auth.heybox_id,
            "favour_type": "1" if favorite else "2",
        }
        if folder_id:
            data["folder_id"] = folder_id
        return await self._write_json(
            "/bbs/app/link/favour",
            data=data,
            use_reply_api=True,
        )

    async def set_post_like(self, *, link_id: int, liked: bool) -> dict[str, Any]:
        return await self._write_json(
            "/bbs/app/profile/award/link",
            data={"link_id": str(link_id), "award_type": "1" if liked else "0"},
            use_reply_api=True,
        )

    async def set_comment_like(self, *, comment_id: int, liked: bool) -> dict[str, Any]:
        return await self._write_json(
            "/bbs/app/comment/support",
            data={"comment_id": str(comment_id), "support_type": "1" if liked else "2"},
            use_reply_api=True,
        )

    async def set_follow(
        self,
        *,
        user_id: str,
        followed: bool,
        link_id: int = 0,
    ) -> dict[str, Any]:
        path = "/bbs/app/profile/follow/user" if followed else "/bbs/app/profile/follow/user/cancel"
        data = {"following_id": user_id}
        if link_id > 0:
            data["link_id"] = str(link_id)
        return await self._write_json(path, data=data)

    async def delete_post(self, *, link_id: int) -> dict[str, Any]:
        return await self._write_json(
            "/bbs/app/link/delete",
            data={"link_id": str(link_id)},
        )

    async def send_direct_message(
        self,
        *,
        user_id: str,
        text: str,
        image_url: str = "",
    ) -> dict[str, Any]:
        copied_image = await self.copy_image_by_url(image_url) if image_url else ""
        self._direct_message_ack_id += 1
        payload = await self._write_json(
            "/chatroom/v2/msg/user",
            params={"to_user_id": user_id},
            data={
                "heybox_ack_id": str(self._direct_message_ack_id),
                "img": copied_image,
                "msg": text,
                "msg_type": "6",
            },
        )
        result = self._result_mapping(payload)
        acknowledged = any(
            str(result.get(key) or "").strip()
            for key in ("heychat_ack_id", "msg_id", "msg_seq")
        )
        if not acknowledged:
            protocol = unquote(
                str(result.get("heybox__protocol__execute__directly") or "")
            ).lower()
            if "web_auth" in protocol or "name_verify" in protocol:
                message = "小黑盒要求安全认证或实名认证，请先在 App 中完成后再发送私信。"
            else:
                message = "小黑盒私信响应中缺少消息 ID，无法确认私信已发送。"
            raise XhhError(message, retryable=False)
        return payload

    async def send_reply(self, *, text: str, link_id: int, reply_id: int, root_id: int) -> ReplyReceipt:
        response = await self._request_json(
            "POST",
            "/bbs/app/comment/create",
            data={
                "is_cy": "",
                "link_id": str(link_id),
                "reply_id": str(reply_id),
                "root_id": str(root_id),
                "text": text,
            },
            use_reply_api=True,
            auth_required=True,
            allow_api_failure=True,
            write_request=True,
        )
        status = self._api_status(response.payload)
        message = str(response.payload.get("msg") or "").strip()
        if status in {"ok", "success"}:
            return ReplyReceipt(status=status, message=message)

        combined = f"{status} {message}".lower()
        if self._looks_like_auth_error(combined):
            raise XhhError(message or "小黑盒登录已失效。", auth_required=True, retryable=False)
        if any(word in combined for word in ("评论已被删除", "帖子已删除", "无法评论", "不存在", "not found")):
            raise XhhError(message or "目标评论无法回复。", terminal=True, retryable=False)
        if self._looks_like_rate_limit(combined):
            raise XhhError(message or "小黑盒请求过于频繁。", retryable=True, retry_after=60)
        if status == "failed":
            raise XhhError(message or "目标评论当前无法回复。", terminal=True, retryable=False)
        raise XhhError(message or f"小黑盒回帖失败：{status or 'unknown'}", retryable=True)

    async def _write_json(
        self,
        path: str,
        *,
        data: Mapping[str, str],
        params: Mapping[str, str] | None = None,
        use_reply_api: bool = False,
    ) -> dict[str, Any]:
        response = await self._request_json(
            "POST",
            path,
            params=params,
            data=data,
            use_reply_api=use_reply_api,
            auth_required=True,
            allow_api_failure=True,
            write_request=True,
        )
        status = self._api_status(response.payload)
        if status not in {"ok", "success"}:
            if status:
                self._raise_for_api_failure(response.payload)
            raise XhhError(
                str(response.payload.get("msg") or "小黑盒写入接口没有返回成功状态。"),
                retryable=False,
            )
        return response.payload

    async def validate_auth(self) -> bool:
        await self.fetch_mentions(offset=0, limit=1)
        return True

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        use_reply_api: bool = False,
        auth_required: bool,
        allow_api_failure: bool = False,
        write_request: bool = False,
    ) -> _JsonResponse:
        await self.start()
        if auth_required and (self.auth is None or not self.auth.cookie):
            raise XhhError("尚未登录小黑盒。", auth_required=True, retryable=False)

        hkey, nonce, request_time = get_request_keys(path)
        query: dict[str, str] = dict(params or {})
        query.update(
            {
                "os_type": "web",
                "app": "web",
                "client_type": "web",
                "version": self.version,
                "web_version": self.web_version,
                "x_client_type": "web",
                "x_app": "heybox_website",
                "x_os_type": "Windows",
                "device_info": "Chrome",
                "device_id": self.device_id,
                "hkey": hkey,
                "_time": str(request_time),
                "nonce": nonce,
                "_notip": "true",
            }
        )
        if auth_required and self.auth is not None and self.auth.heybox_id:
            query["heybox_id"] = self.auth.heybox_id

        headers = {
            "Referer": "https://www.xiaoheihe.cn/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
        if auth_required and self.auth is not None and self.auth.cookie:
            headers["Cookie"] = self.auth.cookie
        if method.upper() == "POST":
            headers["Origin"] = "https://www.xiaoheihe.cn"

        base_url = self.reply_base_url if use_reply_api else self.api_base_url
        url = f"{base_url}{path}"
        assert self._session is not None
        try:
            async with self._session.request(method, url, params=query, data=data, headers=headers) as response:
                raw = await response.text(errors="replace")
                cookies = {name: morsel.value for name, morsel in response.cookies.items()}
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise XhhError(
                        f"小黑盒返回了非 JSON 响应（HTTP {response.status}）：{raw[:200]}",
                        retryable=response.status == 429 or response.status >= 500,
                        auth_required=response.status in {401, 403},
                        delivery_uncertain=write_request and response.status >= 500,
                        retry_after=self._retry_after(response.headers.get("Retry-After")),
                    ) from exc

                if not isinstance(payload, dict):
                    raise XhhError("小黑盒返回的 JSON 不是对象。", retryable=True)
                if response.status < 200 or response.status >= 300:
                    retry_after = self._retry_after(response.headers.get("Retry-After"))
                    raise XhhError(
                        f"小黑盒 HTTP {response.status}：{str(payload.get('msg') or raw)[:200]}",
                        retryable=response.status == 429 or response.status >= 500,
                        auth_required=response.status in {401, 403},
                        delivery_uncertain=write_request and response.status >= 500,
                        retry_after=retry_after,
                    )
                if not allow_api_failure:
                    self._raise_for_api_failure(payload)
                return _JsonResponse(payload=payload, cookies=cookies)
        except XhhError:
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            raise XhhError(
                f"请求小黑盒失败：{exc}",
                retryable=True,
                delivery_uncertain=write_request,
            ) from exc

    def _raise_for_api_failure(self, payload: Mapping[str, Any]) -> None:
        status = self._api_status(payload)
        if not status or status in {"ok", "success"}:
            return
        message = str(payload.get("msg") or "").strip()
        combined = f"{status} {message}".lower()
        if self._looks_like_auth_error(combined):
            raise XhhError(message or "小黑盒登录已失效。", auth_required=True, retryable=False)
        if self._looks_like_rate_limit(combined):
            raise XhhError(message or "小黑盒请求过于频繁。", retryable=True, retry_after=60)
        terminal = status == "failed" and any(
            word in combined for word in ("删除", "不存在", "不可见", "not found")
        )
        raise XhhError(message or f"小黑盒接口返回 {status}。", retryable=not terminal, terminal=terminal)

    def _all_session_cookies(self) -> dict[str, str]:
        if self._session is None:
            return {}
        return {morsel.key: morsel.value for morsel in self._session.cookie_jar}

    @staticmethod
    def parse_cookie_header(header: str) -> dict[str, str]:
        parsed = SimpleCookie()
        try:
            parsed.load(header)
        except Exception:
            return {}
        return {name: morsel.value for name, morsel in parsed.items()}

    @staticmethod
    def _format_cookie_header(cookies: Mapping[str, str]) -> str:
        return "; ".join(f"{name}={value}" for name, value in cookies.items() if name and value)

    @staticmethod
    def _result_mapping(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        result = payload.get("result")
        return result if isinstance(result, Mapping) else {}

    @staticmethod
    def _api_status(payload: Mapping[str, Any]) -> str:
        return str(payload.get("status") or payload.get("stat") or "").strip().lower()

    @staticmethod
    def _looks_like_auth_error(value: str) -> bool:
        return any(word in value for word in ("未登录", "登录失效", "请登录", "unauthorized", "forbidden", "cookie"))

    @staticmethod
    def _looks_like_rate_limit(value: str) -> bool:
        return any(word in value for word in ("频繁", "稍后", "rate limit", "too many"))

    @staticmethod
    def _normalise_media_url(value: str) -> str:
        if value.startswith("//"):
            return "https:" + value
        return value

    @classmethod
    def _extract_names(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        names: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                name = next(
                    (
                        str(item.get(key) or "").strip()
                        for key in ("name", "title", "text", "topic_name", "hashtag")
                        if str(item.get(key) or "").strip()
                    ),
                    "",
                )
            else:
                name = str(item).strip()
            if name:
                names.append(name)
        return list(dict.fromkeys(names))

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return None

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
