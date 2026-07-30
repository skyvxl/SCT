from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QLineEdit

from sct.installer import InstallResult
from sct.localization import TranslationService
from sct.settings import SettingsStore
from sct.ui.dialogs.auto_setup import AutoSetupDialog
from tests.qt_helpers import get_qapplication


class AutoSetupDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_loads_game_path_and_persists_successful_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            settings = SettingsStore(root / "settings.ini")
            settings.ensure_exists()
            settings.update(mod_path=str(game))
            dialog = AutoSetupDialog(
                TranslationService(),
                settings,
                installer_factory=lambda: object(),
            )
            completed: list[InstallResult] = []
            dialog.installation_completed.connect(completed.append)
            result = InstallResult(
                "v1.9.8",
                game,
                game / "ersc_launcher.exe",
                game / "mod",
            )

            with patch("sct.ui.dialogs.auto_setup.QMessageBox.information"):
                dialog._handle_success(result)

            persisted = settings.load()
            self.assertEqual(dialog.game_path_edit.text(), "")
            self.assertIn("ELDEN RING", dialog.game_path_edit.placeholderText())
            self.assertEqual(
                dialog.password_edit.echoMode(),
                QLineEdit.EchoMode.Normal,
            )
            self.assertEqual(persisted.mod_path, str(game))
            self.assertEqual(persisted.game_exe_path, str(game / "ersc_launcher.exe"))
            self.assertEqual(completed, [result])

    def test_shows_github_mirror_warning_before_installation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = SettingsStore(root / "settings.ini")
            settings.ensure_exists()
            dialog = AutoSetupDialog(
                TranslationService(locale="en"),
                settings,
                installer_factory=lambda: object(),
            )

            self.assertTrue(dialog.github_nexus_warning.isVisibleTo(dialog))
            self.assertIn("GitHub", dialog.github_nexus_warning.text())
            self.assertIn("Nexus", dialog.github_nexus_warning.text())

    def test_success_waits_for_worker_thread_before_closing_dialog(self) -> None:
        class RunningThread:
            @staticmethod
            def isRunning() -> bool:
                return True

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            settings = SettingsStore(root / "settings.ini")
            settings.ensure_exists()
            dialog = AutoSetupDialog(
                TranslationService(),
                settings,
                installer_factory=lambda: object(),
            )
            dialog._thread = RunningThread()
            result = InstallResult("v1", game, game / "ersc_launcher.exe", game / "mod")

            with (
                patch("sct.ui.dialogs.auto_setup.QMessageBox.information"),
                patch.object(dialog, "accept") as accept,
            ):
                dialog._handle_success(result)
                accept.assert_not_called()
                dialog._clear_worker()
                accept.assert_called_once()


if __name__ == "__main__":
    unittest.main()
