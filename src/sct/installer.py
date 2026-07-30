from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sct.downloads import download_file, safe_extract_zip
from sct.errors import LocalizedError
from sct.ersc_settings import ErscSettingsStore
from sct.installer_settings import merge_ersc_settings
from sct.modengine import ModEngineConfig
from sct.releases import GitHubReleaseClient, ReleaseAsset
from sct.runtime_config import RuntimeConfig

MODENGINE2_URL = (
    "https://github.com/soulsmods/ModEngine2/releases/download/"
    "release-2.1.0/ModEngine-2.1.0.0-win64.zip"
)
MODENGINE_ROOT_NAME = "ModEngine-2.1.0.0-win64"
MODENGINE_ITEMS = (
    "modengine2",
    "mod",
    "modengine2_launcher.exe",
    "launchmod_eldenring.bat",
)
ProgressCallback = Callable[[str, int], None]


class InstallerError(LocalizedError):
    pass


@dataclass(frozen=True, slots=True)
class InstallResult:
    ersc_version: str
    game_directory: Path
    launcher_path: Path
    mod_directory: Path


class FileTransaction:
    def __init__(self, root: Path, backup_root: Path) -> None:
        self.root = root.resolve()
        self.backup_root = backup_root
        self._prepared: set[Path] = set()
        self._created_files: set[Path] = set()
        self._created_directories: set[Path] = set()
        self._backups: dict[Path, Path] = {}

    def copy_file(self, source: Path, destination: Path) -> None:
        self._prepare_file(destination)
        self._ensure_directory(destination.parent)
        shutil.copy2(source, destination)

    def copy_tree(self, source: Path, destination: Path) -> None:
        self._ensure_directory(destination)
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            target = destination / relative
            if item.is_symlink():
                raise InstallerError(
                    "installer_archive_symlink",
                    f"Installer archive contains a link: {relative}",
                    params={"path": str(relative)},
                )
            if item.is_dir():
                self._ensure_directory(target)
            elif item.is_file():
                self.copy_file(item, target)

    def prepare_existing_file(self, path: Path) -> None:
        self._prepare_file(path)

    def rollback(self) -> None:
        for path in sorted(self._created_files, key=lambda value: len(value.parts), reverse=True):
            path.unlink(missing_ok=True)
        for destination, backup in self._backups.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, destination)
        created_roots = [
            directory
            for directory in self._created_directories
            if not any(
                parent in self._created_directories
                for parent in directory.parents
                if parent != self.root
            )
        ]
        for directory in created_roots:
            if directory.exists():
                shutil.rmtree(directory)

    def _relative(self, path: Path) -> Path:
        try:
            return path.resolve(strict=False).relative_to(self.root)
        except ValueError as error:
            raise InstallerError(
                "installer_path_outside_game",
                f"Attempted write outside the game directory: {path}",
            ) from error

    def _prepare_file(self, path: Path) -> None:
        relative = self._relative(path)
        if relative in self._prepared:
            return
        self._prepared.add(relative)
        if path.is_symlink() or path.is_dir():
            raise InstallerError(
                "installer_target_invalid",
                f"Unable to replace installation target: {path}",
                params={"path": str(path)},
            )
        if path.exists():
            backup = self.backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            self._backups[path] = backup
        else:
            self._created_files.add(path)

    def _ensure_directory(self, path: Path) -> None:
        requested_directory_was_missing = not path.exists()
        relative = self._relative(path)
        current = self.root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise InstallerError(
                    "installer_directory_symlink",
                    f"Installation directory is a symbolic link: {current}",
                    params={"path": str(current)},
                )
            if current.exists():
                if not current.is_dir():
                    raise InstallerError(
                        "installer_directory_expected",
                        f"Expected an installation directory: {current}",
                        params={"path": str(current)},
                    )
                continue
            current.mkdir()
            self._created_directories.add(current)
        if requested_directory_was_missing:
            self._created_directories.add(path)


class ModInstaller:
    def __init__(
            self,
            config: RuntimeConfig,
            *,
            release_client: GitHubReleaseClient | None = None,
            modengine_url: str = MODENGINE2_URL,
    ) -> None:
        self.config = config
        self.release_client = release_client or GitHubReleaseClient()
        self.modengine_url = modengine_url

    def install(
            self,
            game_directory: Path | str,
            password: str,
            *,
            progress: ProgressCallback | None = None,
    ) -> InstallResult:
        game = Path(game_directory).expanduser().resolve()
        if not (game / "eldenring.exe").is_file():
            raise InstallerError(
                "installer_game_exe_missing",
                f"eldenring.exe is missing from the selected directory: {game}",
            )
        if not password:
            raise InstallerError(
                "installer_password_required",
                "A co-op password is required",
            )

        def emit(phase: str, percent: int) -> None:
            if progress is not None:
                progress(phase, max(0, min(percent, 100)))

        transaction: FileTransaction | None = None
        try:
            emit("release", 0)
            release = self.release_client.latest_asset(self.config.ersc_release_api_url)
            with tempfile.TemporaryDirectory(prefix="sct-install-") as temporary:
                workspace = Path(temporary)
                me2_archive = workspace / "modengine2.zip"
                ersc_archive = workspace / release.name
                download_file(
                    self.modengine_url,
                    me2_archive,
                    progress=self._download_progress(emit, "download_modengine", 5, 30),
                )
                download_file(
                    release.download_url,
                    ersc_archive,
                    expected_digest=release.sha256,
                    expected_size=release.size,
                    progress=self._download_progress(emit, "download_ersc", 35, 30),
                )
                emit("extract", 68)
                me2_extract = safe_extract_zip(me2_archive, workspace / "me2")
                ersc_extract = safe_extract_zip(ersc_archive, workspace / "ersc")
                me2_root = self._validate_modengine_staging(me2_extract)
                self._validate_ersc_staging(ersc_extract)

                staged_settings = ersc_extract / "SeamlessCoop" / "ersc_settings.ini"
                existing_settings = game / "SeamlessCoop" / "ersc_settings.ini"
                merge_ersc_settings(
                    staged_settings,
                    existing_settings if existing_settings.is_file() else None,
                    staged_settings,
                    password,
                )

                transaction = FileTransaction(game, workspace / "rollback")
                try:
                    emit("install", 76)
                    for name in MODENGINE_ITEMS:
                        source = me2_root / name
                        destination = game / name
                        if source.is_dir():
                            transaction.copy_tree(source, destination)
                        else:
                            transaction.copy_file(source, destination)

                    config_path = game / "config_eldenring.toml"
                    if not config_path.exists():
                        transaction.copy_file(me2_root / "config_eldenring.toml", config_path)
                    transaction.copy_file(
                        ersc_extract / "ersc_launcher.exe",
                        game / "ersc_launcher.exe",
                    )
                    transaction.copy_tree(
                        ersc_extract / "SeamlessCoop",
                        game / "SeamlessCoop",
                    )

                    emit("configure", 94)
                    transaction.prepare_existing_file(config_path)
                    ModEngineConfig(config_path).ensure_ersc()
                    emit("complete", 100)
                    return InstallResult(
                        ersc_version=release.tag_name,
                        game_directory=game,
                        launcher_path=game / "ersc_launcher.exe",
                        mod_directory=game / "mod",
                    )
                except Exception as error:
                    try:
                        transaction.rollback()
                    except OSError as rollback_error:
                        transaction = None
                        raise InstallerError(
                            "installer_rollback_failed",
                            f"Installation rollback failed: {rollback_error}",
                        ) from error
                    transaction = None
                    raise
        except Exception as error:
            if transaction is not None:
                try:
                    transaction.rollback()
                except OSError as rollback_error:
                    raise InstallerError(
                        "installer_rollback_failed",
                        f"Installation rollback failed: {rollback_error}",
                    ) from error
            if isinstance(error, InstallerError):
                raise
            if isinstance(error, LocalizedError):
                raise InstallerError(
                    error.code,
                    f"Installation failed: {error}",
                    params=error.params,
                ) from error
            raise InstallerError(
                "installer_unexpected",
                f"Unexpected installation failure: {error}",
            ) from error

    def update_ersc(
            self,
            game_directory: Path | str,
            release: ReleaseAsset,
            *,
            progress: ProgressCallback | None = None,
    ) -> InstallResult:
        game = Path(game_directory).expanduser().resolve()
        if not (game / "eldenring.exe").is_file():
            raise InstallerError(
                "installer_game_exe_missing",
                f"eldenring.exe is missing from the selected directory: {game}",
            )

        def emit(phase: str, percent: int) -> None:
            if progress is not None:
                progress(phase, max(0, min(percent, 100)))

        transaction: FileTransaction | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="sct-ersc-update-") as temporary:
                workspace = Path(temporary)
                archive = workspace / release.name
                emit("download_ersc", 0)
                download_file(
                    release.download_url,
                    archive,
                    expected_digest=release.sha256,
                    expected_size=release.size,
                    progress=self._download_progress(emit, "download_ersc", 0, 65),
                )
                emit("extract", 68)
                extracted = safe_extract_zip(archive, workspace / "ersc")
                self._validate_ersc_staging(extracted)

                staged_settings = extracted / "SeamlessCoop" / "ersc_settings.ini"
                existing_settings = game / "SeamlessCoop" / "ersc_settings.ini"
                password = ErscSettingsStore(existing_settings).load().cooppassword
                merge_ersc_settings(
                    staged_settings,
                    existing_settings if existing_settings.is_file() else None,
                    staged_settings,
                    password,
                )

                transaction = FileTransaction(game, workspace / "rollback")
                try:
                    emit("install", 76)
                    transaction.copy_file(
                        extracted / "ersc_launcher.exe",
                        game / "ersc_launcher.exe",
                    )
                    transaction.copy_tree(
                        extracted / "SeamlessCoop",
                        game / "SeamlessCoop",
                    )
                    emit("complete", 100)
                    return InstallResult(
                        ersc_version=release.tag_name,
                        game_directory=game,
                        launcher_path=game / "ersc_launcher.exe",
                        mod_directory=game / "mod",
                    )
                except Exception:
                    transaction.rollback()
                    transaction = None
                    raise
        except Exception as error:
            if transaction is not None:
                try:
                    transaction.rollback()
                except OSError as rollback_error:
                    raise InstallerError(
                        "installer_rollback_failed",
                        f"Installation rollback failed: {rollback_error}",
                    ) from error
            if isinstance(error, InstallerError):
                raise
            if isinstance(error, LocalizedError):
                raise InstallerError(
                    error.code,
                    f"Installation failed: {error}",
                    params=error.params,
                ) from error
            raise InstallerError(
                "installer_unexpected",
                f"Unexpected installation failure: {error}",
            ) from error

    @staticmethod
    def _download_progress(
            emit: ProgressCallback,
            phase: str,
            base: int,
            span: int,
    ) -> Callable[[int, int | None], None]:
        def report(received: int, total: int | None) -> None:
            completed = int((received / total) * span) if total else 0
            emit(phase, base + min(completed, span))

        return report

    @staticmethod
    def _validate_modengine_staging(extracted: Path) -> Path:
        expected = extracted / MODENGINE_ROOT_NAME
        candidates = (expected, extracted)
        for candidate in candidates:
            required = (*MODENGINE_ITEMS, "config_eldenring.toml")
            if all((candidate / name).exists() for name in required):
                return candidate
        raise InstallerError(
            "installer_modengine_structure",
            "ModEngine2 archive has an unexpected structure",
        )

    @staticmethod
    def _validate_ersc_staging(extracted: Path) -> None:
        required = (
            extracted / "ersc_launcher.exe",
            extracted / "SeamlessCoop" / "ersc.dll",
            extracted / "SeamlessCoop" / "ersc_settings.ini",
        )
        if not all(path.is_file() for path in required):
            raise InstallerError(
                "installer_ersc_structure",
                "Seamless Co-op archive has an unexpected structure",
            )
