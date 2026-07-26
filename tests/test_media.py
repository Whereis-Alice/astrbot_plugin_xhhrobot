from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from astrbot_plugin_xhhrobot.media import (
    ImagePayload,
    load_image_payload,
    local_path_from_source,
    normalize_http_image_url,
)
from astrbot_plugin_xhhrobot.models import AuthInfo
from astrbot_plugin_xhhrobot.xhh_client import XhhClient

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

    async def test_prepare_sources_copies_network_and_uploads_local_images(
        self,
    ) -> None:
        client = self.client()
        client.copy_image_by_url = AsyncMock(return_value="https://cdn.example/a.png")
        client.upload_image_payload_to_cos = AsyncMock(
            return_value="https://cdn.example/local.png"
        )

        result = await client.prepare_image_sources(
            ["https://example.com/a.png", str(self.image_path)],
            allowed_local_roots=(self.root,),
        )

        self.assertEqual(
            result,
            ["https://cdn.example/a.png", "https://cdn.example/local.png"],
        )
        uploaded = client.upload_image_payload_to_cos.await_args.args[0]
        self.assertIsInstance(uploaded, ImagePayload)
        self.assertEqual(uploaded.data, PNG_1X1)

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
