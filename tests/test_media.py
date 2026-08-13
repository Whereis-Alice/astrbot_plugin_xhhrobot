from __future__ import annotations

import base64
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image as PillowImage

from astrbot_plugin_xhhrobot.media import (
    ImagePayload,
    extract_image_urls,
    gif_to_png_payload,
    image_payload_to_data_url,
    load_image_payload,
    local_path_from_source,
    normalize_http_image_url,
    strip_xhh_image_transform_query,
)
from astrbot_plugin_xhhrobot.models import AuthInfo
from astrbot_plugin_xhhrobot.xhh_client import XhhClient, XhhError

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class MediaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.image_path = self.root / "image.png"
        self.image_path.write_bytes(PNG_1X1)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def client(self) -> XhhClient:
        return XhhClient(
            api_base_url="https://api.example.test",
            reply_base_url="https://reply.example.test",
            version="1",
            web_version="1",
            device_id="device",
            auth=AuthInfo(cookie="a=b", heybox_id="123"),
        )

    def test_local_image_is_validated_and_restricted_to_roots(self) -> None:
        payload = load_image_payload(
            self.image_path,
            max_bytes=1024 * 1024,
            allowed_roots=(self.root,),
        )
        self.assertEqual(payload.mimetype, "image/png")
        self.assertEqual((payload.width, payload.height), (1, 1))

        other_root = self.root / "other"
        other_root.mkdir()
        with self.assertRaisesRegex(ValueError, "允许上传"):
            load_image_payload(
                self.image_path,
                max_bytes=1024 * 1024,
                allowed_roots=(other_root,),
            )

    def test_base64_image_and_windows_paths_are_supported(self) -> None:
        encoded = "base64://" + base64.b64encode(PNG_1X1).decode("ascii")
        payload = load_image_payload(encoded, max_bytes=1024 * 1024)
        self.assertEqual(payload.mimetype, "image/png")
        self.assertEqual(
            local_path_from_source(r"C:\images\a.png"), Path(r"C:\images\a.png")
        )
        self.assertEqual(
            local_path_from_source(r"\\server\share\a.png"),
            Path(r"\\server\share\a.png"),
        )

    def test_private_network_image_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "私有"):
            normalize_http_image_url("http://127.0.0.1/image.png")

    def test_xhh_thumbnail_queries_are_removed_without_dropping_signatures(self) -> None:
        self.assertEqual(
            strip_xhh_image_transform_query(
                "https://imgheybox1.max-c.com/web/a.jpg?"
                "imageMogr2/auto-orient/ignore-error/1/thumbnail/850x1450%3E"
            ),
            "https://imgheybox1.max-c.com/web/a.jpg",
        )
        self.assertEqual(
            strip_xhh_image_transform_query(
                "https://imgheybox.max-c.com/web/a.jpg?sign=abc&imageView2/2/w/300"
            ),
            "https://imgheybox.max-c.com/web/a.jpg?sign=abc",
        )
        self.assertEqual(
            strip_xhh_image_transform_query(
                "https://images.example/a.jpg?imageMogr2/thumbnail/300x300"
            ),
            "https://images.example/a.jpg?imageMogr2/thumbnail/300x300",
        )

    def test_image_url_trailing_backslash_is_removed(self) -> None:
        self.assertEqual(
            normalize_http_image_url(
                "https://imgheybox.max-c.com/web/thumb.jpeg\\"
            ),
            "https://imgheybox.max-c.com/web/thumb.jpeg",
        )
        self.assertEqual(
            extract_image_urls(
                "https://imgheybox.max-c.com/web/thumb.png\\"
            ),
            ["https://imgheybox.max-c.com/web/thumb.png"],
        )

    def test_image_url_lists_and_nested_img_fields_are_supported(self) -> None:
        self.assertEqual(
            extract_image_urls(
                {
                    "comment_a": {
                        "img": "https://cdn.example/a.jpg;https://cdn.example/b.jpg"
                    }
                }
            ),
            [
                "https://cdn.example/a.jpg",
                "https://cdn.example/b.jpg",
            ],
        )

    def test_gif_first_frame_is_converted_to_png(self) -> None:
        first = PillowImage.new("RGBA", (2, 2), (255, 0, 0, 255))
        second = PillowImage.new("RGBA", (2, 2), (0, 0, 255, 255))
        encoded = BytesIO()
        first.save(
            encoded,
            format="GIF",
            save_all=True,
            append_images=[second],
            duration=100,
            loop=0,
        )
        payload = gif_to_png_payload(
            ImagePayload("reaction.gif", "image/gif", encoded.getvalue(), 2, 2)
        )

        self.assertEqual(payload.mimetype, "image/png")
        self.assertEqual((payload.width, payload.height), (2, 2))
        with PillowImage.open(BytesIO(payload.data)) as image:
            self.assertEqual(image.getpixel((0, 0))[:3], (255, 0, 0))
        self.assertTrue(image_payload_to_data_url(payload).startswith("data:image/png;base64,"))

    def test_gif_falls_back_to_truncated_frame_decode(self) -> None:
        first = PillowImage.new("RGBA", (2, 2), (255, 0, 0, 255))
        encoded = BytesIO()
        first.save(encoded, format="GIF")
        original_open = PillowImage.open
        calls = 0

        def fail_once(*args: object, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("truncated GIF frame")
            return original_open(*args, **kwargs)

        with patch("PIL.Image.open", side_effect=fail_once):
            payload = gif_to_png_payload(
                ImagePayload("truncated.gif", "image/gif", encoded.getvalue(), 2, 2)
            )

        self.assertEqual(payload.mimetype, "image/png")
        self.assertGreaterEqual(calls, 2)

    async def test_llm_gif_source_becomes_png_data_url(self) -> None:
        client = self.client()
        first = PillowImage.new("RGBA", (2, 2), (255, 0, 0, 255))
        encoded = BytesIO()
        first.save(encoded, format="GIF")
        gif = ImagePayload(
            "reaction.gif",
            "image/gif",
            encoded.getvalue(),
            2,
            2,
        )
        client.fetch_image_payload = AsyncMock(return_value=gif)  # type: ignore[method-assign]

        result = await client.prepare_llm_image_source("https://cdn.example/reaction.gif")

        self.assertTrue(result.startswith("data:image/png;base64,"))
        client.fetch_image_payload.assert_awaited_once()

    async def test_llm_static_image_is_validated_and_embedded(self) -> None:
        client = self.client()
        client.fetch_image_payload = AsyncMock(
            return_value=ImagePayload("photo.jpg", "image/jpeg", PNG_1X1, 1, 1)
        )

        result = await client.prepare_llm_image_source(
            "https://imgheybox.max-c.com/web/photo.jpg\\"
        )

        self.assertTrue(result.startswith("data:image/jpeg;base64,"))
        client.fetch_image_payload.assert_awaited_once_with(
            "https://imgheybox.max-c.com/web/photo.jpg\\",
            max_bytes=20 * 1024 * 1024,
        )

    async def test_prepare_sources_uploads_original_network_bytes_and_local_images(
        self,
    ) -> None:
        client = self.client()
        client.fetch_image_payload = AsyncMock(
            return_value=ImagePayload("remote.png", "image/png", PNG_1X1, 1, 1)
        )
        client.copy_image_by_url = AsyncMock()
        client.upload_image_payload_to_cos = AsyncMock(
            side_effect=[
                "https://cdn.example/remote.png",
                "https://cdn.example/local.png",
            ]
        )

        result = await client.prepare_image_sources(
            ["https://example.com/a.png", str(self.image_path)],
            allowed_local_roots=(self.root,),
        )

        self.assertEqual(
            result,
            ["https://cdn.example/remote.png", "https://cdn.example/local.png"],
        )
        client.fetch_image_payload.assert_awaited_once_with(
            "https://example.com/a.png", max_bytes=20 * 1024 * 1024
        )
        client.copy_image_by_url.assert_not_awaited()
        uploaded = [call.args[0] for call in client.upload_image_payload_to_cos.await_args_list]
        self.assertEqual([item.data for item in uploaded], [PNG_1X1, PNG_1X1])

    async def test_prepare_sources_falls_back_to_url_copy_after_remote_upload_error(
        self,
    ) -> None:
        client = self.client()
        client.fetch_image_payload = AsyncMock(
            side_effect=XhhError("图片下载失败（HTTP 403）。", retryable=False)
        )
        client.copy_image_by_url = AsyncMock(return_value="https://cdn.example/copied.png")

        result = await client.prepare_image_sources(["https://example.com/a.png"])

        self.assertEqual(result, ["https://cdn.example/copied.png"])
        client.copy_image_by_url.assert_awaited_once_with("https://example.com/a.png")

    async def test_cos_upload_runs_info_token_put_and_callback_sequence(self) -> None:
        client = self.client()
        client._request_cos_upload_info = AsyncMock(
            return_value={"keys": ["bbs/a.png"], "bucket": "bucket-123"}
        )
        client._request_cos_upload_token = AsyncMock(return_value={"credentials": {}})
        client._put_cos_object = AsyncMock()
        client._finish_cos_upload = AsyncMock(return_value="https://cdn.example/a.png")
        image = ImagePayload("a.png", "image/png", PNG_1X1, 1, 1)

        result = await client.upload_image_payload_to_cos(image)

        self.assertEqual(result, "https://cdn.example/a.png")
        client._request_cos_upload_token.assert_awaited_once_with(
            bucket="bucket-123",
            keys=["bbs/a.png"],
            mimetypes=["image/png"],
        )
        client._put_cos_object.assert_awaited_once()
        client._finish_cos_upload.assert_awaited_once_with(["bbs/a.png"])


if __name__ == "__main__":
    unittest.main()
