from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.fps_patcher import EldenRingFpsPatcher
from sct.localization import TranslationService
from sct.mod_loaders import LoaderKind, ModLoaderManager
from sct.modengine import ModEngineConfig
from sct.settings import SettingsStore
from sct.ui.pages.settings import SettingsPage
from tests.qt_helpers import get_qapplication

ORIGINAL_FPS_SIGNATURE = bytes.fromhex(
    "C7 43 1C 89 88 88 3C EB 6D 89 73 18 EB C7 89 73 18"
)


def supported_executable_bytes() -> bytes:
    return b"MZ" + (b"\x00" * 16) + ORIGINAL_FPS_SIGNATURE + (b"\xFF" * 32)


class FakeSteamService:
    def is_running(self) -> bool:
        return False

    def profiles(self, _executable: str) -> tuple[object, ...]:
        return ()


class ModEngineSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_me3_installation_shows_locked_ersc_badge_without_me2_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            (game / "mod").mkdir(parents=True)
            seamless = game / "SeamlessCoop"
            seamless.mkdir()
            (seamless / "ersc.dll").write_text("ersc", encoding="utf-8")
            runtime = root / "runtime" / "bin"
            runtime.mkdir(parents=True)
            for name in ("me3.exe", "me3-launcher.exe", "me3_mod_host.dll"):
                (runtime / name).write_text(name, encoding="utf-8")
            store = SettingsStore(root / "settings.ini")
            store.ensure_exists()
            store.update(mod_path=str(game))

            page = SettingsPage(
                TranslationService(),
                store,
                FakeSteamService(),
                loader_manager=ModLoaderManager(root / "runtime", root / "profiles"),
            )
            page.steam_status_timer.stop()

            self.assertEqual([badge.text() for badge in page.modengine_badges], ["ersc.dll"])
            self.assertTrue(page.modengine_badges[0].property("locked"))
            self.assertTrue(page.modengine_badges[0].property("active"))

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

    def test_default_loader_selection_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SettingsStore(root / "settings.ini")
            store.ensure_exists()
            store.update(default_mod_loader="me2")
            page = SettingsPage(
                TranslationService(),
                store,
                FakeSteamService(),
                loader_manager=ModLoaderManager(root / "runtime", root / "profiles"),
            )
            page.steam_status_timer.stop()

            self.assertEqual(page.default_loader_combo.currentData(), "me2")
            page.default_loader_combo.setCurrentIndex(
                page.default_loader_combo.findData(LoaderKind.MODENGINE3.value)
            )

            self.assertEqual(store.load().default_mod_loader, "me3")

    def test_current_fps_comes_from_active_executable_not_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            (game / "eldenring.exe").write_bytes(supported_executable_bytes())
            EldenRingFpsPatcher(game).patch(144)
            store = SettingsStore(root / "settings.ini")
            store.ensure_exists()
            store.update(mod_path=str(game), fps_target=240)
            translator = TranslationService()

            page = SettingsPage(translator, store, FakeSteamService())
            page.steam_status_timer.stop()

            self.assertEqual(
                page.current_fps_label.text(),
                translator.translate("settings.fps.current", value="144.0"),
            )

    def test_unsupported_executable_displays_unknown_current_fps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            (game / "eldenring.exe").write_bytes(b"MZ unsupported")
            store = SettingsStore(root / "settings.ini")
            store.ensure_exists()
            store.update(mod_path=str(game), fps_target=240)
            translator = TranslationService()

            page = SettingsPage(translator, store, FakeSteamService())
            page.steam_status_timer.stop()

            self.assertEqual(
                page.current_fps_label.text(),
                translator.translate("settings.fps.current_unknown"),
            )


if __name__ == "__main__":
    unittest.main()
