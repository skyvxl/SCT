from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.localization import TranslationService
from sct.modengine import ModEngineConfig
from sct.settings import SettingsStore
from sct.ui.pages.settings import SettingsPage
from tests.qt_helpers import get_qapplication


class FakeSteamService:
    def is_running(self) -> bool:
        return False

    def profiles(self, _executable: str) -> tuple[object, ...]:
        return ()


class ModEngineSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_folder_button_and_dll_badges_reflect_real_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            (game / "mod").mkdir(parents=True)
            (game / "config_eldenring.toml").write_text(
                "[modengine]\n"
                "external_dlls = [\n"
                '    "SeamlessCoop\\\\ersc.dll",\n'
                '    # "mods\\\\optional.dll"\n'
                "]\n",
                encoding="utf-8",
            )
            store = SettingsStore(root / "settings.ini")
            store.ensure_exists()
            store.update(mod_path=str(game))

            page = SettingsPage(
                TranslationService(),
                store,
                FakeSteamService(),
            )
            page.steam_status_timer.stop()

            self.assertTrue(page.open_mod_folder_button.isEnabled())
            self.assertEqual(
                [button.text() for button in page.modengine_badges],
                ["ersc.dll", "optional.dll"],
            )
            self.assertEqual(page.modengine_badges[0].property("locked"), True)
            self.assertEqual(page.modengine_badges[0].property("active"), True)
            self.assertEqual(page.modengine_badges[1].property("active"), False)

            page.modengine_badges[1].click()

            dlls = ModEngineConfig.from_game_directory(game).list_dlls()
            self.assertTrue(dlls[1].enabled)


if __name__ == "__main__":
    unittest.main()
