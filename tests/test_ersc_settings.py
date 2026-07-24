from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from scmm.ersc_settings import ErscSettings, ErscSettingsStore


class ErscSettingsStoreTests(unittest.TestCase):
    def test_reads_current_gameplay_options_including_new_ersc_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ersc_settings.ini"
            path.write_text(
                "[GAMEPLAY]\n"
                "allow_invaders = 1\n"
                "append_steam_id_to_players = 1\n"
                "always_spectate_on_death = 1\n"
                "default_boot_master_volume = 7\n"
                "\n[PASSWORD]\n"
                "cooppassword = test123\n",
                encoding="utf-8",
            )

            settings = ErscSettingsStore(path).load()

            self.assertTrue(settings.allow_invaders)
            self.assertTrue(settings.append_steam_id_to_players)
            self.assertTrue(settings.always_spectate_on_death)
            self.assertEqual(settings.default_boot_master_volume, 7)
            self.assertEqual(settings.cooppassword, "test123")

    def test_save_preserves_comments_unknown_options_and_file_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ersc_settings.ini"
            path.write_text(
                "; keep this documentation\n"
                "[GAMEPLAY]\n"
                "allow_invaders = 0\n"
                "future_gameplay_option = 42\n"
                "\n[PASSWORD]\n"
                "cooppassword = old\n",
                encoding="utf-8",
            )
            store = ErscSettingsStore(path)

            store.save(
                replace(
                    ErscSettings(),
                    allow_invaders=True,
                    append_steam_id_to_players=True,
                    always_spectate_on_death=True,
                    cooppassword="12345",
                )
            )

            saved = path.read_text(encoding="utf-8")
            self.assertIn("; keep this documentation", saved)
            self.assertIn("future_gameplay_option = 42", saved)
            self.assertIn("allow_invaders = 1", saved)
            self.assertIn("append_steam_id_to_players = 1", saved)
            self.assertIn("always_spectate_on_death = 1", saved)
            self.assertIn("cooppassword = 12345", saved)

    def test_store_resolves_file_from_game_directory(self) -> None:
        game_directory = Path(r"C:\Games\ELDEN RING\Game")
        store = ErscSettingsStore.from_game_directory(game_directory)

        self.assertEqual(
            store.path,
            game_directory / "SeamlessCoop" / "ersc_settings.ini",
        )

    def test_missing_options_are_not_joined_to_file_without_final_newline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ersc_settings.ini"
            path.write_text("[GAMEPLAY]\nallow_invaders = 0", encoding="utf-8")

            ErscSettingsStore(path).save(ErscSettings())

            saved = path.read_text(encoding="utf-8")
            self.assertIn("allow_invaders = 1\n", saved)
            self.assertIn("death_debuffs = 1\n", saved)


if __name__ == "__main__":
    unittest.main()
