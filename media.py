from __future__ import annotations

import base64
import hashlib
import hmac
import html
import ipaddress
import json
import mimetypes
import re
import struct
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
XHH_IMAGE_HOST_SUFFIXES = ("max-c.com", "myqcloud.com", "xiaoheihe.cn")
_GIF_DECODE_LOCK = threading.Lock()

# COS signing logic is adapted from advent259141/astrbot_plugin_xiaoheihe_adapter
# under Apache-2.0. See THIRD_PARTY_NOTICES.md for the modification notice.


@dataclass(frozen=True, slots=True)
class ImagePayload:
    name: str
    mimetype: str
    data: bytes
    width: int = 0
    height: int = 0
    duration: int = 0


def unique_strings(values: Iterable[Any]) -> list[str]:
    return list(
        dict.fromkeys(
            str(value or "").strip() for value in values if str(value or "").strip()
        )
    )


def normalize_http_image_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("//"):
        text = "https:" + text
    if len(text) > 4096:
        raise ValueError("图片 URL 过长。")
    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("图片地址必须是完整 HTTP(S) URL。")
    if parsed.username or parsed.password:
        raise ValueError("图片 URL 不能包含用户名或密码。")
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith(
        (".localhost", ".local", ".internal")
    ):
        raise ValueError("图片 URL 不能指向本机或内部网络主机。")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("图片 URL 不能指向私有、回环或保留 IP 地址。")
    return text


def is_http_url(value: Any) -> bool:
    text = str(value or "").strip()
    return text.startswith(("http://", "https://", "//"))


def is_xhh_image_url(value: Any) -> bool:
    try:
        parsed = urlparse(normalize_http_image_url(value))
    except ValueError:
        return False
    host = (parsed.hostname or "").casefold()
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in XHH_IMAGE_HOST_SUFFIXES
    )


def is_gif_source(value: Any) -> bool:
    """Return whether an image source is explicitly marked as a GIF."""

    text = str(value or "").strip()
    if text.casefold().startswith("data:image/gif"):
        return True
    if text.startswith("base64://"):
        return False
    try:
        return Path(urlparse(text).path).suffix.casefold() == ".gif"
    except (TypeError, ValueError, OSError):
        return False


def gif_to_png_payload(
    image: ImagePayload,
    *,
    max_pixels: int = 16_000_000,
) -> ImagePayload:
    """Decode the first GIF frame into a PNG payload for vision providers."""

    if image.mimetype != "image/gif":
        return image
    try:
        from PIL import Image as PillowImage
    except ImportError as exc:
        raise ValueError("GIF 视觉兼容需要 Pillow 依赖。") from exc

    def render_first_frame() -> tuple[bytes, int, int]:
        with PillowImage.open(BytesIO(image.data)) as source:
            width, height = source.size
            if width <= 0 or height <= 0:
                raise ValueError("GIF 图片尺寸无效。")
            if width * height > max(1, int(max_pixels)):
                raise ValueError("GIF 图片分辨率超过视觉输入上限。")
            source.seek(0)
            frame = source.convert("RGBA")
            output = BytesIO()
            frame.save(output, format="PNG", optimize=True)
            return output.getvalue(), width, height

    try:
        data, width, height = render_first_frame()
    except ValueError:
        raise
    except Exception:
        # CDN responses can occasionally end mid-frame. Pillow exposes its
        # truncated-image switch globally, so guard this fallback with a
        # lock and always restore the previous process-wide value.
        try:
            from PIL import ImageFile

            with _GIF_DECODE_LOCK:
                previous = ImageFile.LOAD_TRUNCATED_IMAGES
                ImageFile.LOAD_TRUNCATED_IMAGES = True
                try:
                    data, width, height = render_first_frame()
                finally:
                    ImageFile.LOAD_TRUNCATED_IMAGES = previous
        except ValueError:
            raise
        except Exception as fallback_error:
            raise ValueError("GIF 图片无法解码为 PNG。") from fallback_error

    if not data:
        raise ValueError("GIF 图片转换后为空。")
    return ImagePayload(
        name=Path(image.name).stem + ".png",
        mimetype="image/png",
        data=data,
        width=width,
        height=height,
        duration=0,
    )


def image_payload_to_data_url(image: ImagePayload) -> str:
    """Convert an image payload to the data URL AstrBot accepts as vision input."""

    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:{image.mimetype};base64,{encoded}"


def extract_image_urls(value: Any) -> list[str]:
    urls: list[str] = []

    def visit(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, str):
            text = _decode_htmlish_text(item)
            if is_http_url(text):
                try:
                    urls.append(normalize_http_image_url(text))
                except ValueError:
                    pass
            pattern = re.compile(
                r"<img\b[^>]*\b(?:data-original|data-src|src)=([\"'])(.*?)\1",
                flags=re.IGNORECASE,
            )
            for match in pattern.finditer(text):
                try:
                    urls.append(normalize_http_image_url(match.group(2)))
                except ValueError:
                    pass
            stripped = text.strip()
            if stripped[:1] in {"[", "{"}:
                try:
                    visit(json.loads(stripped))
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            return
        if isinstance(item, (list, tuple, set)):
            for child in item:
                visit(child)
            return
        if isinstance(item, dict):
            for key in (
                "url",
                "thumb",
                "src",
                "image",
                "image_url",
                "img_url",
                "original",
                "data_original",
                "data-src",
                "data-original",
            ):
                candidate = item.get(key)
                if is_http_url(candidate):
                    try:
                        urls.append(normalize_http_image_url(candidate))
                    except ValueError:
                        pass
            for key in (
                "text",
                "content",
                "html",
                "value",
                "children",
                "items",
                "segments",
                "spans",
                "blocks",
                "imgs",
                "images",
            ):
                if key in item:
                    visit(item.get(key))

    visit(value)
    return unique_strings(urls)


def local_path_from_source(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text or is_http_url(text) or text.startswith(("base64://", "data:image/")):
        return None
    if re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith("\\\\"):
        try:
            return Path(text).expanduser()
        except OSError:
            return Path(text)
    parsed = urlparse(text)
    if parsed.scheme.lower() == "file":
        raw_path = unquote(parsed.path or "")
        if parsed.netloc and raw_path:
            raw_path = f"//{parsed.netloc}{raw_path}"
        elif parsed.netloc:
            raw_path = parsed.netloc
        if re.match(r"^/[A-Za-z]:/", raw_path):
            raw_path = raw_path[1:]
        if not raw_path:
            return None
        path = Path(raw_path)
    elif parsed.scheme:
        return None
    else:
        path = Path(text)
    try:
        return path.expanduser()
    except OSError:
        return path


def load_image_payload(
    source: Any,
    *,
    max_bytes: int,
    allowed_roots: Iterable[Path] = (),
) -> ImagePayload:
    text = str(source or "").strip()
    if text.startswith(("base64://", "data:image/")):
        return _decode_base64_payload(text, max_bytes=max_bytes)

    path = local_path_from_source(text)
    if path is None:
        raise ValueError(f"不支持的本地图片地址：{text!r}")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"本地图片不存在：{path}") from exc
    except OSError as exc:
        raise ValueError(f"无法读取本地图片路径：{path}") from exc
    if not resolved.is_file():
        raise ValueError(f"本地图片不是文件：{resolved}")

    roots = []
    for root in allowed_roots:
        try:
            roots.append(Path(root).expanduser().resolve(strict=False))
        except OSError:
            continue
    if roots and not any(
        resolved == root or resolved.is_relative_to(root) for root in roots
    ):
        raise ValueError("本地图片不在允许上传的目录中。")

    size = resolved.stat().st_size
    if size <= 0:
        raise ValueError("本地图片为空。")
    if size > max_bytes:
        raise ValueError(f"本地图片超过上传上限（{max_bytes // (1024 * 1024)} MiB）。")
    try:
        data = resolved.read_bytes()
    except OSError as exc:
        raise ValueError(f"读取本地图片失败：{resolved}") from exc
    mimetype, extension, width, height = detect_image(data, resolved.name)
    name = _safe_image_name(resolved.stem, extension)
    return ImagePayload(
        name=name,
        mimetype=mimetype,
        data=data,
        width=width,
        height=height,
    )


def detect_image(data: bytes, name: str = "image") -> tuple[str, str, int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        width, height = _read_png_dimensions(data)
        return "image/png", ".png", width, height
    if data.startswith(b"\xff\xd8"):
        width, height = _read_jpeg_dimensions(data)
        return "image/jpeg", ".jpg", width, height
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        width, height = _read_gif_dimensions(data)
        return "image/gif", ".gif", width, height
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        width, height = _read_webp_dimensions(data)
        return "image/webp", ".webp", width, height
    if data.startswith(b"BM"):
        width, height = _read_bmp_dimensions(data)
        return "image/bmp", ".bmp", width, height

    guessed = mimetypes.guess_type(name)[0] or ""
    if (
        guessed.startswith("image/")
        and Path(name).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ):
        raise ValueError("图片扩展名与文件内容不匹配。")
    raise ValueError("不支持的图片格式；仅支持 PNG、JPG、GIF、WebP 和 BMP。")


def cos_quote(value: str) -> str:
    return quote(value, safe="/-_.~")


def cos_authorization(
    *,
    secret_id: str,
    secret_key: str,
    method: str,
    path: str,
    headers: dict[str, str],
    start_time: int,
    end_time: int,
) -> str:
    key_time = f"{start_time};{end_time}"
    header_items = {
        key.lower(): " ".join(str(value).strip().split())
        for key, value in headers.items()
        if str(value).strip()
    }
    signed_headers = ";".join(sorted(header_items))
    http_headers = "&".join(
        f"{quote(key, safe='-_.~')}={quote(header_items[key], safe='-_.~')}"
        for key in sorted(header_items)
    )
    http_string = "\n".join([method.lower(), cos_quote(path), "", http_headers, ""])
    sign_key = _hmac_sha1(secret_key.encode("utf-8"), key_time)
    string_to_sign = "\n".join(
        [
            "sha1",
            key_time,
            hashlib.sha1(http_string.encode("utf-8")).hexdigest(),
            "",
        ]
    )
    signature = _hmac_sha1(sign_key.encode("utf-8"), string_to_sign)
    return (
        "q-sign-algorithm=sha1&"
        f"q-ak={secret_id}&"
        f"q-sign-time={key_time}&"
        f"q-key-time={key_time}&"
        f"q-header-list={signed_headers}&"
        "q-url-param-list=&"
        f"q-signature={signature}"
    )


def _decode_base64_payload(value: str, *, max_bytes: int) -> ImagePayload:
    if value.startswith("base64://"):
        encoded = value.removeprefix("base64://")
    else:
        header, separator, encoded = value.partition(",")
        if not separator or ";base64" not in header.casefold():
            raise ValueError("图片 data URL 不是 Base64 编码。")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("图片 Base64 数据无效。") from exc
    if not data:
        raise ValueError("图片 Base64 数据为空。")
    if len(data) > max_bytes:
        raise ValueError(f"图片超过上传上限（{max_bytes // (1024 * 1024)} MiB）。")
    mimetype, extension, width, height = detect_image(data)
    return ImagePayload(
        name="astrbot-image" + extension,
        mimetype=mimetype,
        data=data,
        width=width,
        height=height,
    )


def _safe_image_name(stem: str, extension: str) -> str:
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "image"
    return safe_stem[:80] + extension


def _decode_htmlish_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\\u003c", "<").replace("\\u003C", "<")
    text = text.replace("\\u003e", ">").replace("\\u003E", ">")
    text = text.replace("\\u0026", "&")
    return html.unescape(text)


def _read_png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    return 0, 0


def _read_gif_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    return 0, 0


def _read_bmp_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) >= 26:
        width = struct.unpack("<I", data[18:22])[0]
        height = abs(struct.unpack("<i", data[22:26])[0])
        return width, height
    return 0, 0


def _read_webp_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 30:
        return 0, 0
    chunk = data[12:16]
    if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        return (
            struct.unpack("<H", data[26:28])[0] & 0x3FFF,
            struct.unpack("<H", data[28:30])[0] & 0x3FFF,
        )
    if chunk == b"VP8L" and len(data) >= 25:
        b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
        width = 1 + (((b1 & 0x3F) << 8) | b0)
        height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return width, height
    if chunk == b"VP8X":
        return (
            1 + int.from_bytes(data[24:27], "little"),
            1 + int.from_bytes(data[27:30], "little"),
        )
    return 0, 0


def _read_jpeg_dimensions(data: bytes) -> tuple[int, int]:
    index = 2
    while index + 9 <= len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            break
        marker = data[index]
        index += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            break
        segment_length = struct.unpack(">H", data[index : index + 2])[0]
        if segment_length < 2 or index + segment_length > len(data):
            break
        if (
            marker
            in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }
            and segment_length >= 7
        ):
            height = struct.unpack(">H", data[index + 3 : index + 5])[0]
            width = struct.unpack(">H", data[index + 5 : index + 7])[0]
            return width, height
        index += segment_length
    return 0, 0


def _hmac_sha1(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha1).hexdigest()
