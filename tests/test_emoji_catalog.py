from __future__ import annotations

import re
import unittest
from pathlib import Path

from astrbot_plugin_xhhrobot.emoji_catalog import (
    XHH_EMOJI_ALIAS_GROUPS,
    XHH_EMOJI_FALLBACK_NAMES,
    XHH_EMOJI_STANDARD_SNAPSHOT_NAMES,
)


class EmojiCatalogTests(unittest.TestCase):
    def test_standard_snapshot_contains_all_recorded_packs(self) -> None:
        names = XHH_EMOJI_STANDARD_SNAPSHOT_NAMES

        self.assertEqual(len(names), 156)
        self.assertEqual(sum(name.startswith("cube_") for name in names), 100)
        self.assertEqual(sum(name.startswith("heygirl_") for name in names), 24)
        self.assertEqual(sum(name.startswith("bigemoji_") for name in names), 16)
        self.assertEqual(sum(name.startswith("grandemoji_") for name in names), 16)

    def test_every_standard_identifier_has_a_compatibility_group(self) -> None:
        grouped = {name for group in XHH_EMOJI_ALIAS_GROUPS for name in group}

        self.assertTrue(XHH_EMOJI_STANDARD_SNAPSHOT_NAMES <= grouped)
        self.assertTrue({"cube_剑星涂鸦", "heygirl_耶嘿"} <= XHH_EMOJI_FALLBACK_NAMES)
        self.assertFalse(
            {"cube_剑星涂鸦", "heygirl_耶嘿"}
            & XHH_EMOJI_STANDARD_SNAPSHOT_NAMES
        )

    def test_reference_table_lists_every_standard_identifier(self) -> None:
        reference = (
            Path(__file__).resolve().parents[1] / "emoji_reference.md"
        ).read_text(encoding="utf-8")
        documented = set(re.findall(r"\[([A-Za-z][A-Za-z0-9-]*_[^\]\r\n]+)\]", reference))

        self.assertTrue(XHH_EMOJI_STANDARD_SNAPSHOT_NAMES <= documented)


if __name__ == "__main__":
    unittest.main()
