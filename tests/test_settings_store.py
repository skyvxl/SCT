from __future__ import annotations

import configparser
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sct.settings import AppSettings, SettingsStore, default_settings_path


class SettingsStoreTests(unittest.TestCase):
    def test_default_path_uses_new_non_conflicting_roaming_folder(self) -> None:
        with patch.dict("os.environ", {"APPDATA": r"C:\Users\Test\AppData\Roaming"}):
            path = default_settings_path()

        self.assertEqual(
            path,
            Path(r"C:\Users\Test\AppData\Roaming") / "SeamlessCoopToolkit" / "settings.ini",
        )

    def test_ensure_exists_creates_complete_default_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SeamlessCoopToolkit" / "settings.ini"
            store = SettingsStore(path)

            settings = store.ensure_exists()

            self.assertEqual(settings, AppSettings())
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(path, encoding="utf-8")
            self.assertEqual(parser["Settings"]["preferred_language"], "en")
            self.assertEqual(parser["Settings"]["save_file_type"], "ER0000.co2")
            self.assertEqual(parser["Settings"]["run_steam_silently"], "0")
            self.assertEqual(parser["Settings"]["fps_target"], "60")
            self.assertEqual(parser["Settings"]["default_mod_loader"], "")
            self.assertIn("sleep_between_saves", parser["Settings"])

    def test_round_trip_preserves_values_and_unknown_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            path.write_text(
                "[Settings]\nunknown_future_option = keep-me\n\n[Plugin]\nenabled = yes\n",
                encoding="utf-8",
            )
            store = SettingsStore(path)

            updated = store.update(
                mod_path=r"C:\Games\ELDEN RING\Game",
                run_steam_silently=True,
                steam_id="76561198000000000",
                fps_target=144,
                default_mod_loader="me3",
                save_backup_key="100663379",
            )

            self.assertEqual(updated.fps_target, 144)
            self.assertEqual(store.load().default_mod_loader, "me3")
            self.assertTrue(store.load().run_steam_silently)
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(path, encoding="utf-8")
            self.assertEqual(parser["Settings"]["unknown_future_option"], "keep-me")
            self.assertEqual(parser["Plugin"]["enabled"], "yes")

    def test_invalid_existing_values_fall_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            path.write_text(
                "[Settings]\nbackup_method = invalid\nenable_sounds = maybe\nsound_volume = loud\n",
                encoding="utf-8",
            )

            settings = SettingsStore(path).load()

            self.assertEqual(settings.backup_method, AppSettings().backup_method)
            self.assertEqual(settings.enable_sounds, AppSettings().enable_sounds)
            self.assertEqual(settings.sound_volume, AppSettings().sound_volume)


if __name__ == "__main__":
    unittest.main()
