from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from sct.installer import InstallerError, ModInstaller
from sct.mod_loaders import LoaderKind, ModLoaderManager
from sct.releases import ReleaseAsset
from sct.runtime_config import RuntimeConfig


class FakeReleaseClient:
    def __init__(
            self,
            asset: ReleaseAsset,
            named_asset: ReleaseAsset | None = None,
    ) -> None:
        self.asset = asset
        self.named_asset = named_asset
        self.requested_url = ""
        self.requested_named_asset: tuple[str, str] | None = None

    def latest_asset(self, api_url: str) -> ReleaseAsset:
        self.requested_url = api_url
        return self.asset

    def latest_named_asset(self, api_url: str, asset_name: str) -> ReleaseAsset:
        self.requested_named_asset = (api_url, asset_name)
        if self.named_asset is None:
            raise AssertionError("No named release asset was configured")
        return self.named_asset


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


def write_me3_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("bin/me3.exe", "me3")
        archive.writestr("bin/me3-launcher.exe", "launcher")
        archive.writestr("bin/me3_mod_host.dll", "host")
        archive.writestr("eldenring-default.me3", 'profileVersion = "v1"\n')


class ModInstallerTests(unittest.TestCase):
    def test_installs_and_reinstalls_modengine3_without_reinstalling_ersc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            (game / "eldenring.exe").write_text("game", encoding="utf-8")
            me3_archive = root / "me3-windows-amd64.zip"
            write_me3_archive(me3_archive)
            client = FakeReleaseClient(
                ReleaseAsset("unused", "unused.zip", "https://example.invalid/unused"),
                ReleaseAsset("v0.12.1", me3_archive.name, me3_archive.as_uri()),
            )
            manager = ModLoaderManager(root / "runtime", root / "profiles")
            installer = ModInstaller(
                RuntimeConfig(
                    "https://example.invalid/ersc/latest",
                    "https://example.invalid/me3/latest",
                ),
                release_client=client,
                loader_manager=manager,
            )

            state = installer.install_loader(game, LoaderKind.MODENGINE3)

            self.assertTrue(state.installed)
            self.assertEqual(state.version, "v0.12.1")
            self.assertFalse((game / "SeamlessCoop").exists())
            self.assertTrue((root / "profiles" / "eldenring-sct.me3").is_file())

    def test_installs_legacy_modengine2_without_replacing_user_mod_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            (game / "eldenring.exe").write_text("game", encoding="utf-8")
            (game / "mod").mkdir()
            (game / "mod" / "user.txt").write_text("keep", encoding="utf-8")
            me2_archive = root / "me2.zip"
            write_modengine_archive(me2_archive)
            installer = ModInstaller(
                RuntimeConfig("https://example.invalid/ersc/latest"),
                modengine_url=me2_archive.as_uri(),
            )

            state = installer.install_loader(game, LoaderKind.MODENGINE2)

            self.assertTrue(state.installed)
            self.assertTrue((game / "mod" / "user.txt").is_file())
            self.assertTrue((game / "mod" / "default.txt").is_file())
            self.assertTrue((game / "config_eldenring.toml").is_file())

    def test_automatic_install_uses_modengine3_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            (game / "eldenring.exe").write_text("game", encoding="utf-8")
            ersc_archive = root / "ersc.zip"
            me3_archive = root / "me3-windows-amd64.zip"
            write_ersc_archive(ersc_archive)
            write_me3_archive(me3_archive)
            client = FakeReleaseClient(
                ReleaseAsset("v1.9.9", ersc_archive.name, ersc_archive.as_uri()),
                ReleaseAsset("v0.12.1", me3_archive.name, me3_archive.as_uri()),
            )
            manager = ModLoaderManager(root / "runtime", root / "profiles")
            installer = ModInstaller(
                RuntimeConfig(
                    "https://example.invalid/ersc/latest",
                    "https://example.invalid/me3/latest",
                ),
                release_client=client,
                loader_manager=manager,
            )

            result = installer.install(game, "password")

            self.assertEqual(result.loader, LoaderKind.MODENGINE3)
            self.assertTrue((root / "runtime" / "bin" / "me3.exe").is_file())
            self.assertTrue((root / "profiles" / "eldenring-sct.me3").is_file())
            self.assertTrue((game / "SeamlessCoop" / "ersc.dll").is_file())
            self.assertTrue((game / "mod").is_dir())
            self.assertFalse((game / "modengine2_launcher.exe").exists())
            self.assertEqual(
                client.requested_named_asset,
                (
                    "https://example.invalid/me3/latest",
                    "me3-windows-amd64.zip",
                ),
            )

    def test_updates_only_ersc_and_preserves_existing_settings_and_user_mods(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "Game"
            game.mkdir()
            (game / "eldenring.exe").write_text("game")
            (game / "ersc_launcher.exe").write_text("old launcher")
            (game / "mod").mkdir()
            (game / "mod" / "user-mod.txt").write_text("keep")
            config = game / "config_eldenring.toml"
            config.write_text(
                "[modengine]\n"
                'external_dlls = ["SeamlessCoop\\\\ersc.dll"]\n'
                "# preserve me\n",
                encoding="utf-8",
            )
            settings = game / "SeamlessCoop" / "ersc_settings.ini"
            settings.parent.mkdir()
            settings.write_text(
                "[GAMEPLAY]\n"
                "allow_invaders = 0\n"
                "[PASSWORD]\n"
                "cooppassword = existing-password\n",
                encoding="utf-8",
            )
            (settings.parent / "ersc.dll").write_text("old dll")
            ersc_archive = root / "ersc-update.zip"
            write_ersc_archive(ersc_archive)
            release = ReleaseAsset(
                tag_name="v1.9.9",
                name=ersc_archive.name,
                download_url=ersc_archive.as_uri(),
                size=ersc_archive.stat().st_size,
                sha256=hashlib.sha256(ersc_archive.read_bytes()).hexdigest(),
            )
            installer = ModInstaller(
                RuntimeConfig("https://example.invalid/latest"),
            )

            result = installer.update_ersc(game, release)

            self.assertEqual(result.ersc_version, "v1.9.9")
            self.assertEqual((game / "ersc_launcher.exe").read_text(), "ersc launcher")
            self.assertEqual((settings.parent / "ersc.dll").read_text(), "ersc")
            updated_settings = settings.read_text(encoding="utf-8")
            self.assertIn("allow_invaders = 0", updated_settings)
            self.assertIn("new_option = 9", updated_settings)
            self.assertIn("cooppassword = existing-password", updated_settings)
            self.assertEqual((game / "mod" / "user-mod.txt").read_text(), "keep")
            self.assertEqual(
                config.read_text(encoding="utf-8"),
                "[modengine]\n"
                'external_dlls = ["SeamlessCoop\\\\ersc.dll"]\n'
                "# preserve me\n",
            )

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
                loader=LoaderKind.MODENGINE2,
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
                installer.install(game, "password", loader=LoaderKind.MODENGINE2)

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

            with self.assertRaises(InstallerError) as caught:
                installer.install(Path(directory), "password")
            self.assertEqual(caught.exception.code, "installer_game_exe_missing")


if __name__ == "__main__":
    unittest.main()
