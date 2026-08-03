from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sct.mod_loaders import (
    LoaderChoiceRequired,
    LoaderKind,
    ModLoaderManager,
)


def install_fake_me3(runtime: Path, version: str = "v0.12.1") -> None:
    (runtime / "bin").mkdir(parents=True)
    for name in ("me3.exe", "me3-launcher.exe", "me3_mod_host.dll"):
        (runtime / "bin" / name).write_text(name, encoding="utf-8")
    (runtime / "runtime.json").write_text(
        json.dumps({"version": version}),
        encoding="utf-8",
    )


def install_fake_me2(game: Path) -> None:
    (game / "modengine2").mkdir()
    (game / "modengine2_launcher.exe").write_text("launcher", encoding="utf-8")
    (game / "launchmod_eldenring.bat").write_text("launch", encoding="utf-8")


class ModLoaderManagerTests(unittest.TestCase):
    def test_installing_me3_replaces_runtime_and_records_release_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            install_fake_me3(runtime, "old")
            (runtime / "obsolete.txt").write_text("old", encoding="utf-8")
            extracted = root / "extracted"
            install_fake_me3(extracted, "archive-value")
            (extracted / "runtime.json").unlink()
            manager = ModLoaderManager(runtime, root / "profiles")

            manager.install_me3(extracted, "v0.12.1")

            self.assertFalse((runtime / "obsolete.txt").exists())
            self.assertEqual(
                manager.state(root / "Game", LoaderKind.MODENGINE3).version,
                "v0.12.1",
            )

    def test_invalid_me3_staging_keeps_existing_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            install_fake_me3(runtime, "old")
            extracted = root / "invalid"
            extracted.mkdir()
            manager = ModLoaderManager(runtime, root / "profiles")

            with self.assertRaises(ValueError):
                manager.install_me3(extracted, "v0.12.1")

            self.assertEqual(manager.state(root / "Game", LoaderKind.MODENGINE3).version, "old")

    def test_default_loader_is_used_without_choice_when_both_are_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            install_fake_me2(game)
            install_fake_me3(root / "runtime")
            manager = ModLoaderManager(root / "runtime", root / "profiles")

            selected = manager.select_loader(game, "me3")

        self.assertEqual(selected, LoaderKind.MODENGINE3)

    def test_both_loaders_without_default_require_a_one_time_choice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            install_fake_me2(game)
            install_fake_me3(root / "runtime")
            manager = ModLoaderManager(root / "runtime", root / "profiles")

            with self.assertRaises(LoaderChoiceRequired) as caught:
                manager.select_loader(game, "")

        self.assertEqual(
            caught.exception.loaders,
            (LoaderKind.MODENGINE3, LoaderKind.MODENGINE2),
        )

    def test_single_installed_loader_is_selected_and_no_loader_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            manager = ModLoaderManager(root / "runtime", root / "profiles")

            self.assertIsNone(manager.select_loader(game, "me3"))
            install_fake_me2(game)
            self.assertEqual(manager.select_loader(game, "me3"), LoaderKind.MODENGINE2)

    def test_me3_profile_and_command_reference_existing_game_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "ELDEN RING" / "Game"
            game.mkdir(parents=True)
            (game / "eldenring.exe").write_text("game", encoding="utf-8")
            install_fake_me3(root / "runtime")
            manager = ModLoaderManager(root / "runtime", root / "profiles")

            profile = manager.write_me3_profile(game)
            command = manager.launch_command(game, LoaderKind.MODENGINE3)

            profile_text = profile.read_text(encoding="utf-8")
            self.assertIn('game = "eldenring"', profile_text)
            self.assertIn(f'path = "{(game / "mod").as_posix()}"', profile_text)
            self.assertIn(
                f'path = "{(game / "SeamlessCoop" / "ersc.dll").as_posix()}"',
                profile_text,
            )
            self.assertEqual(command.executable, root / "runtime" / "bin" / "me3.exe")
            self.assertEqual(
                command.arguments,
                (
                    "launch",
                    "--profile",
                    str(profile),
                    "--exe",
                    str(game / "eldenring.exe"),
                ),
            )
            self.assertEqual(command.working_directory, root / "runtime")

    def test_removing_me2_preserves_user_mods_ersc_and_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            install_fake_me2(game)
            (game / "mod" / "user").mkdir(parents=True)
            (game / "SeamlessCoop").mkdir()
            (game / "SeamlessCoop" / "ersc.dll").write_text("ersc", encoding="utf-8")
            config = game / "config_eldenring.toml"
            config.write_text("keep", encoding="utf-8")
            manager = ModLoaderManager(root / "runtime", root / "profiles")

            manager.remove(game, LoaderKind.MODENGINE2)

            self.assertFalse((game / "modengine2").exists())
            self.assertFalse((game / "modengine2_launcher.exe").exists())
            self.assertFalse((game / "launchmod_eldenring.bat").exists())
            self.assertTrue((game / "mod" / "user").is_dir())
            self.assertTrue((game / "SeamlessCoop" / "ersc.dll").is_file())
            self.assertEqual(config.read_text(encoding="utf-8"), "keep")

    def test_removing_me3_deletes_only_managed_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            install_fake_me3(root / "runtime")
            profiles = root / "profiles"
            manager = ModLoaderManager(root / "runtime", profiles)
            profile = manager.write_me3_profile(game)

            manager.remove(game, LoaderKind.MODENGINE3)

            self.assertFalse((root / "runtime").exists())
            self.assertTrue(profile.is_file())


if __name__ == "__main__":
    unittest.main()
