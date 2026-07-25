from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


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


@dataclass(frozen=True, slots=True)
class Mention:
    message_id: int
    comment_id: int
    root_comment_id: int
    link_id: int
    user_id: int
    comment_text: str
    source: str = "mention"

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
            comment_text=str(
                value.get("comment_a_text")
                or value.get("comment_text")
                or value.get("content")
                or value.get("text")
                or ""
            ).strip(),
            source=str(source or "mention"),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Mention":
        return cls(
            message_id=_as_int(value.get("message_id")),
            comment_id=_as_int(value.get("comment_id")),
            root_comment_id=_as_int(value.get("root_comment_id")),
            link_id=_as_int(value.get("link_id")),
            user_id=_as_int(value.get("user_id")),
            comment_text=str(value.get("comment_text") or "").strip(),
            source=str(value.get("source") or "mention"),
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
    topics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    @property
    def body_text(self) -> str:
        return "\n".join(
            part.strip() for part in self.text_parts if part.strip()
        ).strip()


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


@dataclass(frozen=True, slots=True)
class AuthInfo:
    cookie: str
    heybox_id: str
    nickname: str = ""
    login_at: int = 0

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
