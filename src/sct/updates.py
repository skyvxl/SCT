from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sct.component_versions import compare_versions, detect_ersc_version
from sct.errors import LocalizedError
from sct.installer import InstallResult, ModInstaller, ProgressCallback
from sct.releases import GitHubReleaseClient, ReleaseAsset
from sct.runtime_config import RuntimeConfig
from sct.version import DISPLAY_VERSION

TOOLKIT_RELEASE_API_URL = "https://api.github.com/repos/skyvxl/SCT/releases/latest"


class UpdateError(LocalizedError):
    pass


class UpdateState(Enum):
    AVAILABLE = "available"
    CURRENT = "current"
    AHEAD = "ahead"
    NOT_INSTALLED = "not_installed"


@dataclass(frozen=True, slots=True)
class UpdateCheck:
    installed_version: str | None
    latest_version: str
    state: UpdateState
    release_url: str | None = None
    asset: ReleaseAsset | None = None


InstallerFactory = Callable[[], ModInstaller]


class UpdateService:
    def __init__(
            self,
            config: RuntimeConfig,
            *,
            release_client: GitHubReleaseClient | None = None,
            installer_factory: InstallerFactory | None = None,
            toolkit_version: str = DISPLAY_VERSION,
    ) -> None:
        self.config = config
        self.release_client = release_client or GitHubReleaseClient()
        self.installer_factory = installer_factory or (
            lambda: ModInstaller(config, release_client=self.release_client)
        )
        self.toolkit_version = toolkit_version

    def check_toolkit(self) -> UpdateCheck:
        release = self.release_client.latest_release(TOOLKIT_RELEASE_API_URL)
        return self._build_check(
            self.toolkit_version,
            release.tag_name,
            release_url=release.html_url,
        )

    def check_ersc(self, game_directory: Path | str) -> UpdateCheck:
        asset = self.release_client.latest_asset(self.config.ersc_release_api_url)
        return self._build_check(
            detect_ersc_version(game_directory),
            asset.tag_name,
            asset=asset,
        )

    def install_ersc_update(
            self,
            game_directory: Path | str,
            asset: ReleaseAsset,
            *,
            progress: ProgressCallback | None = None,
    ) -> InstallResult:
        return self.installer_factory().update_ersc(
            game_directory,
            asset,
            progress=progress,
        )

    @staticmethod
    def _build_check(
            installed_version: str | None,
            latest_version: str,
            *,
            release_url: str | None = None,
            asset: ReleaseAsset | None = None,
    ) -> UpdateCheck:
        if installed_version is None:
            state = UpdateState.NOT_INSTALLED
        else:
            try:
                comparison = compare_versions(installed_version, latest_version)
            except ValueError as error:
                raise UpdateError(
                    "update_version_invalid",
                    f"Unable to compare versions: {installed_version}, {latest_version}",
                ) from error
            if comparison < 0:
                state = UpdateState.AVAILABLE
            elif comparison > 0:
                state = UpdateState.AHEAD
            else:
                state = UpdateState.CURRENT
        return UpdateCheck(
            installed_version=installed_version,
            latest_version=latest_version,
            state=state,
            release_url=release_url,
            asset=asset,
        )
