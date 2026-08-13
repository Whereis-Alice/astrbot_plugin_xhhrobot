from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Any

from .media import extract_image_urls
from .rich_content import content_blocks_plain_text

_HTML_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_HTML_SKIPPED_TAGS = frozenset({"script", "style"})


class _HtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        tag = tag.lower()
        if tag in _HTML_SKIPPED_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0 and (tag == "br" or tag in _HTML_BLOCK_TAGS):
            self._append_break()

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in _HTML_SKIPPED_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _HTML_SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif self._skip_depth == 0 and tag in _HTML_BLOCK_TAGS:
            self._append_break()

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)

    def _append_break(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")


def _html_to_plain_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    parser = _HtmlTextParser()
    parser.feed(text)
    parser.close()
    text = "".join(parser.parts)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _first_deep(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        for key in keys:
            candidate = value.get(key)
            if candidate not in (None, ""):
                return candidate
        for child in value.values():
            candidate = _first_deep(child, keys)
            if candidate not in (None, ""):
                return candidate
    elif isinstance(value, (list, tuple)):
        for child in value:
            candidate = _first_deep(child, keys)
            if candidate not in (None, ""):
                return candidate
    return None


_COMMENT_IMAGE_KEYS = (
    "comment_img",
    "comment_imgs",
    "comment_image",
    "comment_images",
    "comment_img_url",
    "comment_img_urls",
    "comment_image_url",
    "comment_image_urls",
    "comment_a_img",
    "comment_a_imgs",
    "comment_a_image",
    "comment_a_images",
    "comment_a_img_url",
    "comment_a_img_urls",
    "comment_a_image_url",
    "comment_a_image_urls",
    "comment_b_img",
    "comment_b_imgs",
    "comment_b_image",
    "comment_b_images",
    "comment_b_img_url",
    "comment_b_img_urls",
    "comment_b_image_url",
    "comment_b_image_urls",
    "reply_img",
    "reply_imgs",
    "reply_image",
    "reply_images",
    "reply_img_url",
    "reply_img_urls",
    "reply_image_url",
    "reply_image_urls",
    "img",
    "imgs",
    "image",
    "images",
    "img_url",
    "img_urls",
    "image_url",
    "image_urls",
    "image_list",
    "img_list",
    "picture",
    "pictures",
    "attachments",
    "attachment",
    "media",
    "media_list",
)
_COMMENT_TEXT_KEYS = (
    "comment_a_text",
    "comment_text",
    "comment_content",
    "reply_content",
    "replyContent",
    "text",
    "content",
    "html",
)
_COMMENT_NESTED_KEYS = (
    "comment_a",
    "comment_b",
    "comment",
    "reply",
    "body",
    "data",
    "payload",
)
def extract_comment_image_urls(value: Any) -> tuple[str, ...]:
    """Extract images from a comment-shaped value without walking post data.

    The message-center response uses generic ``img``/``imgs``/``images``
    fields for the related post.  This helper only follows fields that belong
    to a comment, so a nested author/link object cannot leak its thumbnail into
    the comment image list.
    """

    urls: list[str] = []

    def visit(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, Mapping):
            for key in (*_COMMENT_IMAGE_KEYS, *_COMMENT_TEXT_KEYS):
                if key in item:
                    value = item.get(key)
                    urls.extend(extract_image_urls(value))
            for key in _COMMENT_NESTED_KEYS:
                if key in item:
                    visit(item.get(key))
            return
        if isinstance(item, (list, tuple, set)):
            for child in item:
                visit(child)
            return
        urls.extend(extract_image_urls(item))

    visit(value)
    return tuple(dict.fromkeys(urls))


def _extract_current_comment_image_urls(value: Mapping[str, Any]) -> tuple[str, ...]:
    """Read only fields whose meaning is the current notification comment."""

    scoped: dict[str, Any] = {}
    for key in (
        "comment_img",
        "comment_imgs",
        "comment_image",
        "comment_images",
        "comment_img_url",
        "comment_img_urls",
        "comment_image_url",
        "comment_image_urls",
        "comment_a_img",
        "comment_a_imgs",
        "comment_a_image",
        "comment_a_images",
        "comment_a_img_url",
        "comment_a_img_urls",
        "comment_a_image_url",
        "comment_a_image_urls",
        "comment_a",
        "comment_a_text",
        "comment_text",
        "comment_content",
        "reply_content",
        "replyContent",
    ):
        if key in value:
            scoped[key] = value.get(key)
    return extract_comment_image_urls(scoped)


def _extract_replied_comment_image_urls(value: Mapping[str, Any]) -> tuple[str, ...]:
    scoped: dict[str, Any] = {}
    for key in (
        "comment_b_img",
        "comment_b_imgs",
        "comment_b_image",
        "comment_b_images",
        "comment_b_img_url",
        "comment_b_img_urls",
        "comment_b_image_url",
        "comment_b_image_urls",
        "reply_img",
        "reply_imgs",
        "reply_image",
        "reply_images",
        "reply_img_url",
        "reply_img_urls",
        "reply_image_url",
        "reply_image_urls",
        "comment_b",
        "reply",
        "comment_b_text",
        "reply_to_text",
        "target_comment_text",
    ):
        if key in value:
            scoped[key] = value.get(key)
    return extract_comment_image_urls(scoped)


@dataclass(frozen=True, slots=True)
class Mention:
    message_id: int
    comment_id: int
    root_comment_id: int
    link_id: int
    user_id: int
    comment_text: str
    source: str = "mention"
    user_name: str = ""
    message_time: int = 0
    link_title: str = ""
    replied_text: str = ""
    image_urls: tuple[str, ...] = ()
    replied_image_urls: tuple[str, ...] = ()

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        source: str = "mention",
    ) -> "Mention":
        link = value.get("link")
        link = link if isinstance(link, Mapping) else {}
        target = value.get("target")
        target = target if isinstance(target, Mapping) else {}
        user = value.get("user_a")
        user = user if isinstance(user, Mapping) else {}
        comment_id = _as_int(
            _first_deep(
                value,
                (
                    "comment_a_id",
                    "comment_id",
                    "commentid",
                    "commentId",
                    "reply_id",
                    "replyid",
                    "cid",
                ),
            )
        )
        root_comment_id = _as_int(
            _first_deep(
                value,
                ("root_comment_id", "root_id", "rootCommentId", "root_commentid"),
            )
        )
        return cls(
            message_id=_as_int(value.get("message_id")),
            comment_id=comment_id,
            root_comment_id=root_comment_id or comment_id,
            link_id=_as_int(
                value.get("linkid")
                or value.get("link_id")
                or link.get("linkid")
                or link.get("link_id")
                or target.get("linkid")
                or target.get("link_id")
            ),
            user_id=_as_int(
                value.get("userid_a")
                or value.get("user_id")
                or user.get("heybox_id")
                or user.get("user_heybox_id")
                or user.get("userid")
                or user.get("user_id")
                or user.get("uid")
                or user.get("id")
            ),
            comment_text=_html_to_plain_text(
                value.get("comment_a_text")
                or value.get("comment_text")
                or value.get("content")
                or value.get("text")
            ),
            source=str(source or "mention"),
            user_name=str(
                user.get("username") or user.get("nickname") or user.get("name") or ""
            ).strip(),
            message_time=_timestamp(
                value.get("timestamp") or value.get("time") or value.get("create_time")
            ),
            link_title=str(link.get("title") or value.get("link_title") or "").strip(),
            replied_text=_html_to_plain_text(value.get("comment_b_text")),
            image_urls=_extract_current_comment_image_urls(value),
            replied_image_urls=_extract_replied_comment_image_urls(value),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Mention":
        return cls(
            message_id=_as_int(value.get("message_id")),
            comment_id=_as_int(value.get("comment_id")),
            root_comment_id=_as_int(value.get("root_comment_id")),
            link_id=_as_int(value.get("link_id")),
            user_id=_as_int(value.get("user_id")),
            comment_text=_html_to_plain_text(value.get("comment_text")),
            source=str(value.get("source") or "mention"),
            user_name=str(value.get("user_name") or "").strip(),
            message_time=_as_int(value.get("message_time")),
            link_title=str(value.get("link_title") or "").strip(),
            replied_text=_html_to_plain_text(value.get("replied_text")),
            image_urls=_string_tuple(value.get("image_urls")),
            replied_image_urls=_string_tuple(value.get("replied_image_urls")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_actionable(self) -> bool:
        return self.message_id > 0 and self.comment_id > 0 and self.link_id > 0

    @property
    def target_key(self) -> tuple[int, int]:
        return self.link_id, self.comment_id


@dataclass(frozen=True, slots=True)
class DirectConversation:
    user_id: str
    user_name: str = ""
    source: str = "direct_message"
    marker: str = ""

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        source: str,
    ) -> "DirectConversation | None":
        user = _mapping(
            value.get("user_a")
            or value.get("user")
            or value.get("recipient_info")
            or value.get("sender_info")
        )
        user_id = _first_text(
            _user_id(user),
            value.get("to_user_id"),
            value.get("target_user_id"),
            value.get("user_id"),
            value.get("userid"),
            value.get("message_id")
            if str(value.get("entry") or "") == "message"
            else "",
        )
        if not user_id:
            return None
        marker_source = {
            "message_id": value.get("last_message_id") or value.get("message_id"),
            "seq": value.get("seq") or value.get("msg_seq"),
            "time": value.get("update_time")
            or value.get("timestamp")
            or value.get("time"),
            "text": value.get("content") or value.get("msg") or value.get("text"),
            "img": value.get("img") or value.get("imgs"),
        }
        marker = hashlib.sha256(
            json.dumps(
                marker_source, ensure_ascii=False, sort_keys=True, default=str
            ).encode("utf-8")
        ).hexdigest()[:24]
        return cls(
            user_id=user_id,
            user_name=_first_text(
                user.get("username"),
                user.get("nickname"),
                user.get("name"),
                user_id,
            ),
            source=str(source or "direct_message"),
            marker=marker,
        )


@dataclass(frozen=True, slots=True)
class DirectMessage:
    event_key: str
    message_id: str
    user_id: str
    user_name: str
    text: str
    image_urls: tuple[str, ...]
    timestamp: int
    source: str = "direct_message"

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        conversation: DirectConversation,
        self_user_id: str,
    ) -> "DirectMessage | None":
        sender = _mapping(
            value.get("sender")
            or value.get("sender_info")
            or value.get("user")
            or value.get("user_a")
        )
        sender_id = _first_text(
            value.get("sender_id"),
            value.get("from_user_id"),
            value.get("from_uid"),
            _user_id(sender),
        )
        outgoing = bool(
            value.get("is_self")
            or value.get("is_mine")
            or value.get("from_self")
            or str(value.get("direction") or "").casefold()
            in {"out", "outgoing", "send", "sent"}
        )
        if outgoing or (sender_id and self_user_id and sender_id == self_user_id):
            return None

        text = str(
            value.get("content")
            or value.get("msg")
            or value.get("text")
            or value.get("message")
            or ""
        ).strip()
        image_urls = tuple(
            extract_image_urls(
                [
                    value.get("img"),
                    value.get("imgs"),
                    value.get("image"),
                    value.get("images"),
                    value.get("content"),
                ]
            )
        )
        if not text and not image_urls:
            return None

        message_id = _first_text(
            value.get("msg_id"),
            value.get("message_id"),
            value.get("id"),
            value.get("_id"),
            value.get("seq"),
            value.get("msg_seq"),
            value.get("sequence"),
        )
        if not message_id:
            digest_source = {
                "sender": sender_id or conversation.user_id,
                "time": _timestamp(
                    value.get("send_time")
                    or value.get("timestamp")
                    or value.get("time")
                ),
                "text": text,
                "images": image_urls,
            }
            message_id = hashlib.sha256(
                json.dumps(
                    digest_source,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ).encode("utf-8")
            ).hexdigest()[:20]
        event_key = f"{conversation.source}:{conversation.user_id}:{message_id}"
        return cls(
            event_key=event_key,
            message_id=message_id,
            user_id=conversation.user_id,
            user_name=_first_text(
                sender.get("username"),
                sender.get("nickname"),
                sender.get("name"),
                conversation.user_name,
                conversation.user_id,
            ),
            text=text,
            image_urls=image_urls,
            timestamp=_timestamp(
                value.get("send_time")
                or value.get("timestamp")
                or value.get("time")
                or value.get("update_time")
                or value.get("created_at")
                or value.get("create_time")
            ),
            source=conversation.source,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DirectMessage":
        return cls(
            event_key=str(value.get("event_key") or ""),
            message_id=str(value.get("message_id") or ""),
            user_id=str(value.get("user_id") or ""),
            user_name=str(value.get("user_name") or ""),
            text=str(value.get("text") or ""),
            image_urls=_string_tuple(value.get("image_urls")),
            timestamp=_as_int(value.get("timestamp")),
            source=str(value.get("source") or "direct_message"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NotificationPage:
    items: tuple[Mention, ...] = ()
    message_ids: tuple[int, ...] = ()
    raw_count: int = 0

    @property
    def newest_message_id(self) -> int:
        return max(self.message_ids, default=0)

    def reaches(self, cursor: int) -> bool:
        return cursor > 0 and any(
            message_id <= cursor for message_id in self.message_ids
        )


@dataclass(frozen=True, slots=True)
class PostContext:
    title: str = ""
    author_id: str = ""
    author_name: str = ""
    text_parts: tuple[str, ...] = ()
    image_urls: tuple[str, ...] = ()
    content_blocks: tuple[dict[str, str], ...] = ()
    topics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    comment_image_urls_by_id: tuple[tuple[int, tuple[str, ...]], ...] = ()

    def comment_images_for(self, comment_id: int) -> tuple[str, ...]:
        try:
            target_id = int(comment_id)
        except (TypeError, ValueError):
            return ()
        for stored_id, image_urls in self.comment_image_urls_by_id:
            if stored_id == target_id:
                return image_urls
        return ()

    @property
    def body_text(self) -> str:
        body = "\n".join(
            part.strip() for part in self.text_parts if part.strip()
        ).strip()
        return body or content_blocks_plain_text(self.content_blocks)


@dataclass(frozen=True, slots=True)
class FeedPost:
    link_id: int
    title: str = ""
    description: str = ""
    author_id: str = ""
    author_name: str = ""
    created_at: int = 0
    likes: int = 0
    comments: int = 0
    topics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _user_id(value: Mapping[str, Any]) -> str:
    return _first_text(
        value.get("heybox_id"),
        value.get("user_heybox_id"),
        value.get("userid"),
        value.get("user_id"),
        value.get("uid"),
        value.get("id"),
    )


def _timestamp(value: Any) -> int:
    try:
        timestamp = int(float(value or 0))
    except (TypeError, ValueError):
        timestamp = 0
    if timestamp > 100_000_000_000:
        timestamp //= 1000
    return timestamp if timestamp > 0 else int(time.time())


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    return tuple(
        dict.fromkeys(
            str(item or "").strip() for item in values if str(item or "").strip()
        )
    )


@dataclass(frozen=True, slots=True)
class AuthInfo:
    cookie: str
    heybox_id: str
    nickname: str = ""
    login_at: int = 0
    avatar: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "AuthInfo | None":
        if not isinstance(value, Mapping):
            return None
        cookie = str(value.get("cookie") or "").strip()
        if not cookie:
            return None
        return cls(
            cookie=cookie,
            heybox_id=str(
                value.get("heybox_id") or value.get("heyboxId") or ""
            ).strip(),
            nickname=str(value.get("nickname") or "").strip(),
            avatar=str(value.get("avatar") or "").strip(),
            login_at=_as_int(value.get("login_at") or value.get("time")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QrChallenge:
    qr_url: str
    state_params: dict[str, str] = field(default_factory=dict)
    expires_in: int = 120


@dataclass(frozen=True, slots=True)
class QrPollResult:
    state: str
    message: str = ""
    auth: AuthInfo | None = None

    @property
    def complete(self) -> bool:
        return self.state in {"success", "expired", "failed"}


@dataclass(frozen=True, slots=True)
class ReplyReceipt:
    status: str
    message: str = ""
