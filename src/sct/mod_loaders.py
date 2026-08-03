from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sct.settings import DIRECTORY_NAME, default_settings_path

ME3_MANIFEST_NAME = "runtime.json"
ME3_REQUIRED_FILES = (
    Path("bin/me3.exe"),
    Path("bin/me3-launcher.exe"),
    Path("bin/me3_mod_host.dll"),
)
ME2_OWNED_PATHS = (
    Path("modengine2"),
    Path("modengine2_launcher.exe"),
    Path("launchmod_eldenring.bat"),
)


class LoaderKind(StrEnum):
    MODENGINE3 = "me3"
    MODENGINE2 = "me2"


class LoaderChoiceRequired(RuntimeError):
    def __init__(self, loaders: tuple[LoaderKind, ...]) -> None:
        super().__init__("A mod loader must be selected for this launch")
        self.loaders = loaders


@dataclass(frozen=True, slots=True)
class LoaderState:
    kind: LoaderKind
    installed: bool
    version: str | None = None


@dataclass(frozen=True, slots=True)
class LaunchCommand:
    executable: Path
    arguments: tuple[str, ...] = ()
    working_directory: Path | None = None


def default_me3_runtime_directory() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / DIRECTORY_NAME / "runtimes" / "me3"


def default_me3_profiles_directory() -> Path:
    return default_settings_path().parent / "profiles"


class ModLoaderManager:
    def __init__(
            self,
            me3_runtime_directory: Path | str | None = None,
            profiles_directory: Path | str | None = None,
    ) -> None:
        self.me3_runtime_directory = Path(
            me3_runtime_directory or default_me3_runtime_directory()
        )
        self.profiles_directory = Path(
            profiles_directory or default_me3_profiles_directory()
        )

    @property
    def me3_profile_path(self) -> Path:
        return self.profiles_directory / "eldenring-sct.me3"

    def state(self, game_directory: Path | str, kind: LoaderKind) -> LoaderState:
        game = Path(game_directory)
        if kind is LoaderKind.MODENGINE3:
            installed = all(
                (self.me3_runtime_directory / relative).is_file()
                for relative in ME3_REQUIRED_FILES
            )
            return LoaderState(kind, installed, self._me3_version() if installed else None)
        installed = (
                (game / "modengine2").is_dir()
                and (game / "modengine2_launcher.exe").is_file()
                and (game / "launchmod_eldenring.bat").is_file()
        )
        return LoaderState(kind, installed, "2.1.0" if installed else None)

    def installed_loaders(self, game_directory: Path | str) -> tuple[LoaderKind, ...]:
        return tuple(
            kind
            for kind in (LoaderKind.MODENGINE3, LoaderKind.MODENGINE2)
            if self.state(game_directory, kind).installed
        )

    def select_loader(
            self,
            game_directory: Path | str,
            preferred: str | LoaderKind,
    ) -> LoaderKind | None:
        installed = self.installed_loaders(game_directory)
        try:
            preferred_kind = LoaderKind(preferred) if preferred else None
        except ValueError:
            preferred_kind = None
        if preferred_kind in installed:
            return preferred_kind
        if len(installed) == 1:
            return installed[0]
        if len(installed) > 1:
            raise LoaderChoiceRequired(installed)
        return None

    def write_me3_profile(self, game_directory: Path | str) -> Path:
        game = Path(game_directory).expanduser().resolve()
        profile = self.me3_profile_path
        if profile.is_file():
            return profile
        profile.parent.mkdir(parents=True, exist_ok=True)
        mod_path = (game / "mod").as_posix()
        ersc_path = (game / "SeamlessCoop" / "ersc.dll").as_posix()
        contents = (
            'profileVersion = "v1"\n\n'
            "[[supports]]\n"
            'game = "eldenring"\n\n'
            "[[packages]]\n"
            'id = "sct-mods"\n'
            f'path = "{mod_path}"\n\n'
            "[[natives]]\n"
            f'path = "{ersc_path}"\n'
        )
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    newline="\n",
                    delete=False,
                    dir=profile.parent,
                    prefix=f".{profile.name}.",
                    suffix=".tmp",
            ) as temporary:
                temporary.write(contents)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, profile)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return profile

    def install_me3(self, extracted_directory: Path | str, version: str) -> None:
        source = Path(extracted_directory)
        if not all((source / relative).is_file() for relative in ME3_REQUIRED_FILES):
            raise ValueError("ModEngine 3 archive has an unexpected structure")
        runtime = self.me3_runtime_directory
        runtime.parent.mkdir(parents=True, exist_ok=True)
        if runtime.is_symlink():
            raise ValueError("Managed ModEngine 3 runtime cannot be a symbolic link")
        prepared = Path(tempfile.mkdtemp(prefix=".me3-install-", dir=runtime.parent))
        backup = prepared.with_name(f"{prepared.name}.backup")
        previous_moved = False
        try:
            shutil.copytree(source, prepared, dirs_exist_ok=True)
            (prepared / ME3_MANIFEST_NAME).write_text(
                json.dumps({"version": version}, indent=2) + "\n",
                encoding="utf-8",
            )
            if runtime.exists():
                os.replace(runtime, backup)
                previous_moved = True
            try:
                os.replace(prepared, runtime)
            except OSError:
                if previous_moved:
                    os.replace(backup, runtime)
                    previous_moved = False
                raise
            if previous_moved:
                shutil.rmtree(backup)
                previous_moved = False
        finally:
            if prepared.exists():
                shutil.rmtree(prepared)
            if previous_moved and backup.exists() and not runtime.exists():
                os.replace(backup, runtime)
            elif backup.exists():
                shutil.rmtree(backup)

    def launch_command(
            self,
            game_directory: Path | str,
            kind: LoaderKind,
    ) -> LaunchCommand:
        game = Path(game_directory).expanduser().resolve()
        if kind is LoaderKind.MODENGINE3:
            profile = self.write_me3_profile(game)
            return LaunchCommand(
                executable=self.me3_runtime_directory / "bin" / "me3.exe",
                arguments=(
                    "launch",
                    "--profile",
                    str(profile),
                    "--exe",
                    str(game / "eldenring.exe"),
                ),
                working_directory=self.me3_runtime_directory,
            )
        batch = game / "launchmod_eldenring.bat"
        return LaunchCommand(executable=batch, working_directory=game)

    def remove(self, game_directory: Path | str, kind: LoaderKind) -> None:
        game = Path(game_directory).expanduser().resolve()
        if kind is LoaderKind.MODENGINE3:
            if self.me3_runtime_directory.exists():
                shutil.rmtree(self.me3_runtime_directory)
            return
        for relative in ME2_OWNED_PATHS:
            target = game / relative
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)

    def _me3_version(self) -> str | None:
        manifest = self.me3_runtime_directory / ME3_MANIFEST_NAME
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        version = payload.get("version") if isinstance(payload, dict) else None
        return version.strip() if isinstance(version, str) and version.strip() else None
