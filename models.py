from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True, slots=True)
class Mention:
    message_id: int
    comment_id: int
    root_comment_id: int
    link_id: int
    user_id: int
    comment_text: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Mention":
        return cls(
            message_id=_as_int(value.get("message_id")),
            comment_id=_as_int(value.get("comment_a_id")),
            root_comment_id=_as_int(value.get("root_comment_id")),
            link_id=_as_int(value.get("linkid") or value.get("link_id")),
            user_id=_as_int(value.get("userid_a") or value.get("user_id")),
            comment_text=str(value.get("comment_a_text") or value.get("comment_text") or "").strip(),
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
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_actionable(self) -> bool:
        return self.message_id > 0 and self.comment_id > 0 and self.link_id > 0


@dataclass(frozen=True, slots=True)
class PostContext:
    title: str = ""
    text_parts: tuple[str, ...] = ()
    image_urls: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    @property
    def body_text(self) -> str:
        return "\n".join(part.strip() for part in self.text_parts if part.strip()).strip()


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
            heybox_id=str(value.get("heybox_id") or value.get("heyboxId") or "").strip(),
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

