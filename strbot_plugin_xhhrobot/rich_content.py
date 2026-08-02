from __future__ import annotations

import html
import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse


class RichContentError(ValueError):
    pass


_ALLOWED_TAGS = frozenset(
    {
        "a",
        "b",
        "blockquote",
        "br",
        "code",
        "del",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "s",
        "strong",
        "u",
        "ul",
    }
)
_VOID_TAGS = frozenset({"br"})
_SKIPPED_TAGS = frozenset({"script", "style", "iframe", "object", "embed"})
_BLOCK_TAGS = frozenset(
    {"blockquote", "h1", "h2", "h3", "h4", "li", "ol", "p", "pre", "ul"}
)
_OUTBOUND_TYPES = frozenset({"text", "html", "image"})
_PLAIN_TEXT_BREAK_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_PLAIN_TEXT_BLOCK_RE = re.compile(
    r"</?\s*(?:p|div)\b[^>]*>",
    re.IGNORECASE,
)
_PLAIN_TEXT_ESCAPED_BREAK_RE = re.compile(r"\\(?:r\\n|n|r)")


class _HtmlSanitizer(HTMLParser):
    def __init__(self, *, strict: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.strict = strict
        self.parts: list[str] = []
        self._stack: list[str] = []
        self._skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.lower()
        if tag in _SKIPPED_TAGS:
            if self.strict:
                raise RichContentError(f"富文本不允许 <{tag}> 标签。")
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in _ALLOWED_TAGS:
            if self.strict:
                raise RichContentError(f"富文本不支持 <{tag}> 标签。")
            return

        rendered_attrs = self._render_attrs(tag, attrs)
        self.parts.append(f"<{tag}{rendered_attrs}>")
        if tag not in _VOID_TAGS:
            self._stack.append(tag)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIPPED_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            elif self.strict:
                raise RichContentError(f"富文本包含未匹配的 </{tag}> 标签。")
            return
        if self._skip_depth:
            return
        if tag not in _ALLOWED_TAGS:
            if self.strict:
                raise RichContentError(f"富文本不支持 </{tag}> 标签。")
            return
        if tag in _VOID_TAGS:
            return
        if not self._stack or self._stack[-1] != tag:
            if self.strict:
                raise RichContentError(f"富文本包含未匹配的 </{tag}> 标签。")
            return
        self._stack.pop()
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(html.escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        del data
        if self.strict:
            raise RichContentError("富文本不允许 HTML 注释。")

    def close_and_render(self) -> str:
        self.close()
        if self._skip_depth and self.strict:
            raise RichContentError("富文本包含未关闭的危险标签。")
        if self._stack:
            if self.strict:
                raise RichContentError("富文本包含未关闭的标签。")
            while self._stack:
                self.parts.append(f"</{self._stack.pop()}>")
        return "".join(self.parts).strip()

    def _render_attrs(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> str:
        if not attrs:
            return ""
        if tag != "a":
            if self.strict:
                raise RichContentError(f"<{tag}> 标签不支持属性。")
            return ""

        href = ""
        for name, value in attrs:
            normalized_name = str(name or "").lower()
            if normalized_name.startswith("on"):
                if self.strict:
                    raise RichContentError("富文本不允许事件属性。")
                continue
            if normalized_name != "href":
                if self.strict:
                    raise RichContentError("链接仅允许 href 属性。")
                continue
            try:
                href = _normalize_href(value or "")
            except RichContentError:
                if self.strict:
                    raise
                href = ""
        return f' href="{html.escape(href, quote=True)}"' if href else ""


class _HtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.lower() == "br" or tag.lower() in _BLOCK_TAGS:
            self._append_break()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self._append_break()

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def _append_break(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")


def sanitize_rich_html(value: Any) -> str:
    text = _require_text(value, "html")
    parser = _HtmlSanitizer(strict=True)
    parser.feed(text)
    sanitized = parser.close_and_render()
    if not html_to_plain_text(sanitized):
        raise RichContentError("富文本内容不能为空。")
    return sanitized


def sanitize_inbound_html(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    parser = _HtmlSanitizer(strict=False)
    parser.feed(text)
    return parser.close_and_render()


def html_to_plain_text(value: Any) -> str:
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


def normalize_plain_text(value: Any) -> str:
    """Convert common model HTML line breaks in a plain text field."""

    text = str(value or "")
    if not text:
        return ""
    text = _PLAIN_TEXT_BREAK_RE.sub("\n", text)
    text = _PLAIN_TEXT_BLOCK_RE.sub("\n", text)
    text = _PLAIN_TEXT_ESCAPED_BREAK_RE.sub("\n", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_rich_content_blocks(
    value: Any,
    *,
    max_text_chars: int,
    max_blocks: int = 40,
) -> list[dict[str, str]]:
    """Validate LLM-supplied blocks without handling image uploads."""

    if value in (None, ""):
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RichContentError("content_blocks 必须是内容块数组。")
    if len(value) > max_blocks:
        raise RichContentError(f"content_blocks 最多允许 {max_blocks} 项。")

    blocks: list[dict[str, str]] = []
    text_length = 0
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, Mapping):
            raise RichContentError(f"第 {index} 个内容块必须是对象。")
        item_type = str(raw.get("type") or "").strip().lower()
        if item_type not in _OUTBOUND_TYPES:
            raise RichContentError(
                f"第 {index} 个内容块 type 只能是 text、html 或 image。"
            )

        if item_type == "image":
            _reject_unknown_keys(raw, {"type", "url", "image_url"}, index)
            source = raw.get("url")
            if source is None:
                source = raw.get("image_url")
            blocks.append({"type": "image", "url": _require_text(source, "图片地址")})
            continue

        _reject_unknown_keys(raw, {"type", "text", "html", "content"}, index)
        source = raw.get("text")
        if source is None:
            source = raw.get("html") if item_type == "html" else raw.get("content")
        if source is None:
            source = raw.get("content")
        if item_type == "html":
            text = sanitize_rich_html(source)
            visible_text = html_to_plain_text(text)
        else:
            text = _require_text(source, "文本")
            visible_text = text.strip()
            if not visible_text:
                raise RichContentError(f"第 {index} 个文本内容块不能为空。")
        text_length += len(visible_text)
        if text_length > max_text_chars:
            raise RichContentError(f"内容块文字总长度不能超过 {max_text_chars} 字符。")
        blocks.append({"type": item_type, "text": text})
    return blocks


def parse_inbound_content_blocks(value: Any) -> tuple[dict[str, str], ...]:
    """Convert Xiaoheihe's variable post payload into safe ordered blocks."""

    items: Any = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        items = parsed if parsed is not None else [{"type": "text", "text": value}]
    if isinstance(items, Mapping):
        items = [items]
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        return ()

    blocks: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            text = str(item or "").strip()
            if text:
                blocks.append({"type": "text", "text": text})
            continue
        item_type = str(item.get("type") or "text").strip().lower()
        url = str(item.get("url") or item.get("src") or "").strip()
        if item_type in {"img", "image"} or (url and not item.get("text")):
            if url:
                blocks.append({"type": "image", "url": _normalize_protocol_url(url)})
            continue
        text = item.get("text")
        if text is None:
            text = item.get("content")
        if text is None:
            text = item.get("html")
        text = str(text or "").strip()
        if not text:
            continue
        if item_type == "html" or re.search(r"<[A-Za-z!/][^>]*>", text):
            sanitized = sanitize_inbound_html(text)
            if sanitized:
                blocks.append({"type": "html", "text": sanitized})
        else:
            blocks.append({"type": "text", "text": text})
    return tuple(blocks)


def content_blocks_plain_text(blocks: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        item_type = str(block.get("type") or "").lower()
        if item_type == "image":
            continue
        text = str(block.get("text") or "")
        if item_type == "html":
            text = html_to_plain_text(text)
        if text.strip():
            parts.append(text.strip())
    return "\n".join(parts).strip()


def content_blocks_image_sources(blocks: Sequence[Mapping[str, Any]]) -> list[str]:
    return [
        str(block.get("url") or "").strip()
        for block in blocks
        if str(block.get("type") or "").lower() == "image"
        and str(block.get("url") or "").strip()
    ]


def platform_html_for_block(block: Mapping[str, Any]) -> str:
    item_type = str(block.get("type") or "").lower()
    text = str(block.get("text") or "")
    if item_type == "html":
        return sanitize_rich_html(text)
    if item_type == "text":
        return html.escape(text)
    raise RichContentError("只有文本内容块可以转换为帖子正文。")


def _normalize_href(value: str) -> str:
    href = str(value or "").strip()
    if not href or len(href) > 2048:
        raise RichContentError("链接地址无效或过长。")
    parsed = urlparse(href)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise RichContentError("链接只允许公开 HTTP(S) 地址。")
    if parsed.username or parsed.password:
        raise RichContentError("链接地址不能包含用户名或密码。")
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise RichContentError("链接不能指向本机或内部网络主机。")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return href
    if not address.is_global:
        raise RichContentError("链接不能指向私有、回环或保留 IP 地址。")
    return href


def _normalize_protocol_url(value: str) -> str:
    return "https:" + value if value.startswith("//") else value


def _reject_unknown_keys(
    value: Mapping[str, Any],
    allowed: set[str],
    index: int,
) -> None:
    unknown = {str(key) for key in value} - allowed
    if unknown:
        names = "、".join(sorted(unknown))
        raise RichContentError(f"第 {index} 个内容块包含不支持的字段：{names}。")


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise RichContentError(f"{field_name} 必须是非空字符串。")
    if not value.strip():
        raise RichContentError(f"{field_name} 不能为空。")
    return value
