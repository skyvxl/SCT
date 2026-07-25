from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sct.application import build_main_window, main
from sct.game.runtime import GameSnapshot
from sct.localization import TranslationCatalogError, TranslationService
from sct.settings import SettingsStore
from sct.steam import SteamService
from tests.qt_helpers import get_qapplication


class FakeGameRuntime:
    def __init__(self) -> None:
        self.closed = False

    def poll(self) -> GameSnapshot:
        return GameSnapshot((), ())

    def set_runes(self, value: int) -> GameSnapshot:
        return GameSnapshot((), ())

    def set_cheat(self, cheat: object, enabled: bool) -> None:
        return None

    def enabled_cheats(self) -> frozenset[object]:
        return frozenset()

    def close(self) -> None:
        self.closed = True


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    @patch("sct.application.configure_logging")
    @patch("sct.application.QMessageBox.critical")
    @patch(
        "sct.application.TranslationService",
        side_effect=TranslationCatalogError("broken ru.json"),
    )
    def test_catalog_failure_returns_nonzero_before_event_loop(
        self,
        _translator: object,
        critical: object,
        _logging: object,
    ) -> None:
        with self.assertLogs("sct.application", level="ERROR") as logs:
            result = main([])
        self.assertEqual(result, 1)
        critical.assert_called_once()
        self.assertEqual(critical.call_args.args[1], "Localization error")
        self.assertTrue(any("Unable to initialize localization" in entry for entry in logs.output))

    @patch("sct.application.configure_logging")
    @patch("sct.application.QMessageBox.critical")
    @patch("sct.application.SettingsStore")
    @patch("sct.application.build_main_window", side_effect=RuntimeError("broken window"))
    def test_unhandled_startup_failure_is_reported_without_event_loop(
        self,
        _window: object,
        _settings_store: object,
        critical: object,
        _logging: object,
    ) -> None:
        with self.assertLogs("sct.application", level="ERROR") as logs:
            result = main([])
        self.assertEqual(result, 1)
        critical.assert_called_once()
        self.assertNotIn("broken window", critical.call_args.args[2])
        self.assertTrue(any("Unable to build application window" in entry for entry in logs.output))

    def test_game_runtime_is_injected_and_closed_with_main_window(self) -> None:
        runtime = FakeGameRuntime()
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsStore(Path(directory) / "settings.ini")
            settings.ensure_exists()
            window = build_main_window(
                TranslationService(),
                settings,
                SteamService(),
                runtime,
            )

            current_page = window.page_stack.widget(2)
            self.assertIs(current_page.runtime, runtime)
            window.close()

        self.assertTrue(runtime.closed)


if __name__ == "__main__":
    unittest.main()
