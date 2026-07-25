from __future__ import annotations

import base64
import unittest

from astrbot_plugin_xhhrobot.signing import build_hkey, generate_xhh_token


class SigningTests(unittest.TestCase):
    def test_fixed_hkey_vector(self) -> None:
        self.assertEqual(
            build_hkey(
                "/bbs/app/user/message",
                1_700_000_000,
                "0123456789ABCDEF0123456789ABCDEF",
            ),
            "YT27P47",
        )

    def test_generated_token_has_expected_binary_shape(self) -> None:
        token = generate_xhh_token(1_700_000_000)
        decoded = base64.b64decode(token)
        self.assertEqual(len(decoded), 65)
        self.assertEqual(decoded[-1], 0)


if __name__ == "__main__":
    unittest.main()

