from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.mod_loaders import LoaderChoiceRequired, LoaderKind, ModLoaderManager
from sct.settings import AppSettings
from sct.ui.pages.home import LaunchConfigurationError, resolve_launch_command


def install_fake_me3(runtime: Path) -> None:
    (runtime / "bin").mkdir(parents=True)
    for name in ("me3.exe", "me3-launcher.exe", "me3_mod_host.dll"):
        (runtime / "bin" / name).write_text(name, encoding="utf-8")


def install_fake_me2(game: Path) -> None:
    (game / "modengine2").mkdir()
    (game / "modengine2_launcher.exe").write_text("launcher", encoding="utf-8")
    (game / "launchmod_eldenring.bat").write_text("launch", encoding="utf-8")


class LaunchCommandTests(unittest.TestCase):
    def test_configured_default_loader_is_used_when_both_are_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            executable = game / "ersc_launcher.exe"
            executable.touch()
            (game / "eldenring.exe").touch()
            install_fake_me2(game)
            install_fake_me3(root / "runtime")
            manager = ModLoaderManager(root / "runtime", root / "profiles")
            settings = AppSettings(
                mod_path=str(game),
                game_exe_path=str(executable),
                default_mod_loader="me3",
            )

            command = resolve_launch_command(settings, manager)

        self.assertEqual(command.executable, root / "runtime" / "bin" / "me3.exe")
        self.assertIn("--profile", command.arguments)

    def test_both_loaders_without_default_require_choice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            executable = game / "ersc_launcher.exe"
            executable.touch()
            (game / "eldenring.exe").touch()
            install_fake_me2(game)
            install_fake_me3(root / "runtime")
            manager = ModLoaderManager(root / "runtime", root / "profiles")

            with self.assertRaises(LoaderChoiceRequired):
                resolve_launch_command(
                    AppSettings(mod_path=str(game), game_exe_path=str(executable)),
                    manager,
                )

    def test_single_installed_loader_is_used_without_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            executable = game / "ersc_launcher.exe"
            executable.touch()
            install_fake_me2(game)
            manager = ModLoaderManager(root / "runtime", root / "profiles")

            command = resolve_launch_command(
                AppSettings(mod_path=str(game), game_exe_path=str(executable)),
                manager,
            )

        self.assertEqual(command.executable, game / "launchmod_eldenring.bat")
        self.assertEqual(command.arguments, ())

    def test_selected_executable_is_used_when_no_loader_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            executable = game / "ersc_launcher.exe"
            executable.touch()
            manager = ModLoaderManager(root / "runtime", root / "profiles")

            command = resolve_launch_command(
                AppSettings(mod_path=str(game), game_exe_path=str(executable)),
                manager,
            )

        self.assertEqual(command.executable, executable)
        self.assertEqual(command.working_directory, game)

    def test_explicit_one_time_choice_does_not_need_a_saved_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            executable = game / "ersc_launcher.exe"
            executable.touch()
            install_fake_me2(game)
            install_fake_me3(root / "runtime")
            manager = ModLoaderManager(root / "runtime", root / "profiles")

            command = resolve_launch_command(
                AppSettings(mod_path=str(game), game_exe_path=str(executable)),
                manager,
                selected_loader=LoaderKind.MODENGINE2,
            )

        self.assertEqual(command.executable, game / "launchmod_eldenring.bat")

    def test_missing_game_directory_or_executable_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = ModLoaderManager(
                Path(directory) / "runtime",
                Path(directory) / "profiles",
            )
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
                        resolve_launch_command(settings, manager)


if __name__ == "__main__":
    unittest.main()
