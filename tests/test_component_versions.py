from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.component_versions import compare_versions, detect_ersc_version


class ComponentVersionTests(unittest.TestCase):
    def test_detects_ersc_version_next_to_steam_matchmaking_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            dll = game / "SeamlessCoop" / "ersc.dll"
            dll.parent.mkdir()
            dll.write_bytes(
                b"unrelated 9.9.9\0"
                b"SteamMatchMaking009\0"
                b"1.9.9\0"
                b"trailing data"
            )

            self.assertEqual(detect_ersc_version(game), "1.9.9")

    def test_missing_supported_marker_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            dll = game / "SeamlessCoop" / "ersc.dll"
            dll.parent.mkdir()
            dll.write_bytes(b"some library with version 1.9.9")

            self.assertIsNone(detect_ersc_version(game))

    def test_missing_dll_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(detect_ersc_version(directory))

    def test_compare_versions_handles_release_prefix_and_numeric_order(self) -> None:
        self.assertEqual(compare_versions("v1.9.9", "1.9.9"), 0)
        self.assertLess(compare_versions("1.9.8", "v1.9.9"), 0)
        self.assertGreater(compare_versions("1.10.0", "1.9.9"), 0)

    def test_compare_versions_rejects_values_without_semantic_version(self) -> None:
        with self.assertRaises(ValueError):
            compare_versions("unknown", "1.9.9")


if __name__ == "__main__":
    unittest.main()
