from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from scmm.installer import InstallerError, ModInstaller
from scmm.releases import ReleaseAsset
from scmm.runtime_config import RuntimeConfig


class FakeReleaseClient:
    def __init__(self, asset: ReleaseAsset) -> None:
        self.asset = asset
        self.requested_url = ""

    def latest_asset(self, api_url: str) -> ReleaseAsset:
        self.requested_url = api_url
        return self.asset


def write_modengine_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        root = "ModEngine-2.1.0.0-win64/"
        archive.writestr(f"{root}modengine2/bin/loader.dll", "loader")
        archive.writestr(f"{root}mod/default.txt", "default mod")
        archive.writestr(f"{root}modengine2_launcher.exe", "launcher")
        archive.writestr(f"{root}launchmod_eldenring.bat", "launch")
        archive.writestr(
            f"{root}config_eldenring.toml",
            "[modengine]\nexternal_dlls = []\n",
        )
        archive.writestr(f"{root}README.txt", "must not be installed")


def write_ersc_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ersc_launcher.exe", "ersc launcher")
        archive.writestr("SeamlessCoop/ersc.dll", "ersc")
        archive.writestr(
            "SeamlessCoop/ersc_settings.ini",
            "# new release comments\n"
            "[GAMEPLAY]\n"
            "allow_invaders = 1\n"
            "new_option = 9\n"
            "[PASSWORD]\n"
            "cooppassword = template\n",
        )


class ModInstallerTests(unittest.TestCase):
    def test_installs_selected_files_and_preserves_user_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            (game / "eldenring.exe").write_text("game")
            (game / "mod").mkdir()
            (game / "mod" / "user-mod.txt").write_text("keep")
            (game / "config_eldenring.toml").write_text(
                "[modengine]\n"
                "external_dlls = []\n"
                "# preserve me\n",
                encoding="utf-8",
            )
            old_settings = game / "SeamlessCoop" / "ersc_settings.ini"
            old_settings.parent.mkdir()
            old_settings.write_text(
                "[GAMEPLAY]\nallow_invaders = 0\n[PASSWORD]\ncooppassword = old\n",
                encoding="utf-8",
            )
            me2_archive = root / "me2.zip"
            ersc_archive = root / "ersc.zip"
            write_modengine_archive(me2_archive)
            write_ersc_archive(ersc_archive)
            ersc_digest = hashlib.sha256(ersc_archive.read_bytes()).hexdigest()
            release_client = FakeReleaseClient(
                ReleaseAsset(
                    tag_name="v1.9.8",
                    name=ersc_archive.name,
                    download_url=ersc_archive.as_uri(),
                    size=ersc_archive.stat().st_size,
                    sha256=ersc_digest,
                )
            )
            progress: list[tuple[str, int]] = []
            installer = ModInstaller(
                RuntimeConfig("https://example.invalid/releases/latest"),
                release_client=release_client,
                modengine_url=me2_archive.as_uri(),
            )

            result = installer.install(
                game,
                "wizard-password",
                progress=lambda phase, percent: progress.append((phase, percent)),
            )

            self.assertEqual(result.ersc_version, "v1.9.8")
            self.assertEqual(
                release_client.requested_url,
                "https://example.invalid/releases/latest",
            )
            self.assertTrue((game / "modengine2" / "bin" / "loader.dll").is_file())
            self.assertTrue((game / "mod" / "user-mod.txt").is_file())
            self.assertTrue((game / "mod" / "default.txt").is_file())
            self.assertTrue((game / "ersc_launcher.exe").is_file())
            self.assertFalse((game / "README.txt").exists())
            installed_settings = old_settings.read_text(encoding="utf-8")
            self.assertIn("# new release comments", installed_settings)
            self.assertIn("allow_invaders = 0", installed_settings)
            self.assertIn("new_option = 9", installed_settings)
            self.assertIn("cooppassword = wizard-password", installed_settings)
            config = (game / "config_eldenring.toml").read_text(encoding="utf-8")
            self.assertIn("# preserve me", config)
            self.assertIn('"SeamlessCoop\\\\ersc.dll"', config)
            self.assertEqual(progress[-1], ("complete", 100))

    def test_rolls_back_files_when_configuration_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            (game / "eldenring.exe").write_text("game")
            broken_config = game / "config_eldenring.toml"
            broken_config.write_text(
                "[modengine]\nexternal_dlls = [\n",
                encoding="utf-8",
            )
            me2_archive = root / "me2.zip"
            ersc_archive = root / "ersc.zip"
            write_modengine_archive(me2_archive)
            write_ersc_archive(ersc_archive)
            client = FakeReleaseClient(
                ReleaseAsset(
                    "v1",
                    ersc_archive.name,
                    ersc_archive.as_uri(),
                    ersc_archive.stat().st_size,
                    hashlib.sha256(ersc_archive.read_bytes()).hexdigest(),
                )
            )
            installer = ModInstaller(
                RuntimeConfig("https://example.invalid/latest"),
                release_client=client,
                modengine_url=me2_archive.as_uri(),
            )

            with self.assertRaises(InstallerError):
                installer.install(game, "password")

            self.assertEqual(
                broken_config.read_text(encoding="utf-8"),
                "[modengine]\nexternal_dlls = [\n",
            )
            self.assertFalse((game / "modengine2_launcher.exe").exists())
            self.assertFalse(
                (game / "SeamlessCoop").exists(),
                list((game / "SeamlessCoop").rglob("*")),
            )

    def test_rejects_directory_without_eldenring_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            installer = ModInstaller(
                RuntimeConfig("https://example.invalid/latest"),
                release_client=FakeReleaseClient(
                    ReleaseAsset("v1", "ersc.zip", "https://example.invalid/ersc.zip")
                ),
            )

            with self.assertRaisesRegex(InstallerError, "eldenring.exe"):
                installer.install(Path(directory), "password")


if __name__ == "__main__":
    unittest.main()
