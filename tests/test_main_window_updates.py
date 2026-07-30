from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QWidget

from sct.localization import TranslationService
from sct.settings import SettingsStore
from sct.ui.main_window import MainWindow
from sct.ui.page_spec import PageSpec
from tests.qt_helpers import get_qapplication


class FakeSignal:
    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def connect(self, callback: object) -> None:
        self.callbacks.append(callback)


class FakeUpdateController:
    def __init__(self) -> None:
        self.ersc_updated = FakeSignal()
        self.auto_setup_requested = FakeSignal()
        self.toolkit_checks = 0
        self.ersc_checks = 0

    def check_toolkit(self, _parent: QWidget) -> None:
        self.toolkit_checks += 1

    def check_ersc(self, _parent: QWidget) -> None:
        self.ersc_checks += 1

    def shutdown(self) -> None:
        return None


def page_specs() -> tuple[PageSpec, ...]:
    return tuple(
        PageSpec("nav.home", "missing.png", QWidget())
        for _index in range(6)
    )


class MainWindowUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_update_menu_actions_dispatch_to_their_existing_components(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsStore(Path(directory) / "settings.ini")
            settings.ensure_exists()
            controller = FakeUpdateController()
            window = MainWindow(
                TranslationService(locale="en"),
                page_specs(),
                settings,
                installer_factory=lambda: object(),
                update_service_factory=lambda: object(),
                update_controller_factory=lambda *_args: controller,
            )

            window.help_actions[1].trigger()
            window.help_actions[2].trigger()

            self.assertEqual(controller.toolkit_checks, 1)
            self.assertEqual(controller.ersc_checks, 1)
            window.close()

    def test_footer_displays_version_detected_from_selected_game_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            dll = game / "SeamlessCoop" / "ersc.dll"
            dll.parent.mkdir(parents=True)
            dll.write_bytes(b"SteamMatchMaking009\0" b"1.9.9\0")
            settings = SettingsStore(root / "settings.ini")
            settings.ensure_exists()
            settings.update(mod_path=str(game))
            controller = FakeUpdateController()
            window = MainWindow(
                TranslationService(locale="en"),
                page_specs(),
                settings,
                installer_factory=lambda: object(),
                update_service_factory=lambda: object(),
                update_controller_factory=lambda *_args: controller,
            )

            self.assertIn("1.9.9", window.mod_version_label.text())
            window.close()


if __name__ == "__main__":
    unittest.main()
