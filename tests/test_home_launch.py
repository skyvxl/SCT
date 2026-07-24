from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.settings import AppSettings
from sct.ui.pages.home import LaunchConfigurationError, resolve_launch_target


class LaunchTargetTests(unittest.TestCase):
    def test_prefers_modengine_batch_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory) / "Game"
            game.mkdir()
            launcher = game / "ersc_launcher.exe"
            launcher.touch()
            batch = game / "launchmod_eldenring.bat"
            batch.touch()
            settings = AppSettings(
                mod_path=str(game),
                game_exe_path=str(launcher),
            )

            target = resolve_launch_target(settings)

        self.assertEqual(target, batch)

    def test_uses_selected_executable_when_batch_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory) / "Game"
            game.mkdir()
            launcher = game / "ersc_launcher.exe"
            launcher.touch()

            target = resolve_launch_target(
                AppSettings(mod_path=str(game), game_exe_path=str(launcher))
            )

        self.assertEqual(target, launcher)

    def test_allows_eldenring_executable_as_selected_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory) / "Game"
            game.mkdir()
            executable = game / "eldenring.exe"
            executable.touch()

            target = resolve_launch_target(
                AppSettings(mod_path=str(game), game_exe_path=str(executable))
            )

        self.assertEqual(target, executable)

    def test_missing_game_directory_or_executable_is_reported(self) -> None:
        invalid_settings = (
            AppSettings(),
            AppSettings(mod_path=r"C:\Missing\Game"),
            AppSettings(
                mod_path=r"C:\Missing\Game",
                game_exe_path=r"C:\Missing\Game\ersc_launcher.exe",
            ),
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings):
                with self.assertRaises(LaunchConfigurationError):
                    resolve_launch_target(settings)


if __name__ == "__main__":
    unittest.main()
