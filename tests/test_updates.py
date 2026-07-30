from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.releases import ReleaseAsset, ReleaseInfo
from sct.runtime_config import RuntimeConfig
from sct.updates import UpdateService, UpdateState


class FakeReleaseClient:
    def __init__(self, *, toolkit_version: str, ersc_version: str) -> None:
        self.toolkit_release = ReleaseInfo(
            toolkit_version,
            f"https://example.invalid/toolkit/{toolkit_version}",
        )
        self.ersc_asset = ReleaseAsset(
            ersc_version,
            "ersc.zip",
            "https://example.invalid/ersc.zip",
        )

    def latest_release(self, _api_url: str) -> ReleaseInfo:
        return self.toolkit_release

    def latest_asset(self, _api_url: str) -> ReleaseAsset:
        return self.ersc_asset


def write_ersc_version(game: Path, version: str) -> None:
    dll = game / "SeamlessCoop" / "ersc.dll"
    dll.parent.mkdir(parents=True)
    dll.write_bytes(f"SteamMatchMaking009\0{version}\0".encode("ascii"))


class UpdateServiceTests(unittest.TestCase):
    def test_toolkit_check_reports_newer_release_and_page(self) -> None:
        service = UpdateService(
            RuntimeConfig("https://example.invalid/ersc"),
            release_client=FakeReleaseClient(
                toolkit_version="v0.3.0",
                ersc_version="v1.9.9",
            ),
            toolkit_version="0.2.0",
        )

        result = service.check_toolkit()

        self.assertEqual(result.state, UpdateState.AVAILABLE)
        self.assertEqual(result.installed_version, "0.2.0")
        self.assertEqual(result.latest_version, "v0.3.0")
        self.assertEqual(
            result.release_url,
            "https://example.invalid/toolkit/v0.3.0",
        )

    def test_ersc_check_reports_current_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            write_ersc_version(game, "1.9.9")
            service = self._service("v1.9.9")

            result = service.check_ersc(game)

        self.assertEqual(result.state, UpdateState.CURRENT)
        self.assertIs(result.asset, service.release_client.ersc_asset)

    def test_ersc_check_reports_available_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            write_ersc_version(game, "1.9.8")

            result = self._service("v1.9.9").check_ersc(game)

        self.assertEqual(result.state, UpdateState.AVAILABLE)

    def test_ersc_check_never_marks_older_github_release_as_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            write_ersc_version(game, "1.9.9")

            result = self._service("v1.9.8").check_ersc(game)

        self.assertEqual(result.state, UpdateState.AHEAD)

    def test_ersc_check_reports_missing_local_installation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self._service("v1.9.9").check_ersc(directory)

        self.assertEqual(result.state, UpdateState.NOT_INSTALLED)
        self.assertIsNone(result.installed_version)

    @staticmethod
    def _service(ersc_version: str) -> UpdateService:
        return UpdateService(
            RuntimeConfig("https://example.invalid/ersc"),
            release_client=FakeReleaseClient(
                toolkit_version="v0.2.0",
                ersc_version=ersc_version,
            ),
            toolkit_version="0.2.0",
        )


if __name__ == "__main__":
    unittest.main()
