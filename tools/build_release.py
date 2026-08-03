from __future__ import annotations

import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tomllib
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path
from urllib.parse import urlparse

from sct.version import DISPLAY_VERSION, DISTRIBUTION_VERSION

APP_NAME = "Seamless Co-op Toolkit"
RELEASE_PREFIX = "Seamless-Co-op-Toolkit"
ERSC_RELEASE_API_URL = "ERSC_RELEASE_API_URL"
STABLE_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

LICENSE_DISTRIBUTIONS = (
    "PyInstaller",
    "pyinstaller-hooks-contrib",
    "PySide6",
    "PySide6-Essentials",
    "PySide6-Addons",
    "shiboken6",
    "pymem",
)


class ReleaseBuildError(RuntimeError):
    """Raised when a portable release cannot be assembled safely."""


@dataclass(frozen=True, slots=True)
class ReleaseLayout:
    project_root: Path
    build_root: Path
    bundle_dir: Path
    dist_root: Path
    release_name: str
    release_dir: Path
    archive_path: Path

    @classmethod
    def from_project(cls, project_root: Path | str) -> ReleaseLayout:
        root = Path(project_root).resolve()
        build_root = root / "build" / "pyinstaller"
        dist_root = root / "dist"
        release_name = f"{RELEASE_PREFIX}-{DISPLAY_VERSION}-win64"
        return cls(
            project_root=root,
            build_root=build_root,
            bundle_dir=build_root / "dist" / APP_NAME,
            dist_root=dist_root,
            release_name=release_name,
            release_dir=dist_root / release_name,
            archive_path=dist_root / f"{release_name}.zip",
        )


@dataclass(frozen=True, slots=True)
class LicenseComponent:
    name: str
    version: str
    declared_license: str
    license_files: tuple[Path, ...]


def validate_project_version(project_root: Path | str) -> str:
    root = Path(project_root)
    pyproject_path = root / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as pyproject_file:
            project_version = tomllib.load(pyproject_file)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        raise ReleaseBuildError(
            f"Unable to read project version from {pyproject_path}"
        ) from error

    versions = {
        "pyproject.toml": project_version,
        "DISPLAY_VERSION": DISPLAY_VERSION,
        "DISTRIBUTION_VERSION": DISTRIBUTION_VERSION,
    }
    if any(not isinstance(value, str) for value in versions.values()) or len(
            set(versions.values())
    ) != 1:
        details = ", ".join(f"{name}={value}" for name, value in versions.items())
        raise ReleaseBuildError(f"Toolkit versions do not match: {details}")
    if STABLE_VERSION_PATTERN.fullmatch(project_version) is None:
        raise ReleaseBuildError(
            f"Release version must use stable major.minor.patch syntax: {project_version}"
        )
    return project_version


def _dotenv_release_url(path: Path) -> str:
    if not path.is_file():
        return ""
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if separator and key.strip() == ERSC_RELEASE_API_URL:
            value = raw_value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            return value.strip()
    return ""


def _resolve_release_url(
        project_root: Path | str,
        environment: Mapping[str, str] | None,
) -> str:
    values = os.environ if environment is None else environment
    release_url = values.get(ERSC_RELEASE_API_URL, "").strip()
    if not release_url:
        release_url = _dotenv_release_url(Path(project_root) / ".env")
    parsed = urlparse(release_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ReleaseBuildError(
            f"{ERSC_RELEASE_API_URL} must be set to a valid HTTP(S) URL"
        )
    return release_url


def write_release_environment(
        destination: Path | str,
        project_root: Path | str,
        environment: Mapping[str, str] | None = None,
) -> None:
    release_url = _resolve_release_url(project_root, environment)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{ERSC_RELEASE_API_URL}={release_url}\n",
        encoding="utf-8",
    )


def _remove_release_directory(path: Path, dist_root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = dist_root.resolve()
    if (
            resolved_path.parent != resolved_root
            or not resolved_path.name.startswith(f"{RELEASE_PREFIX}-")
    ):
        raise ReleaseBuildError(f"Refusing to remove unsafe release path: {path}")
    if resolved_path.exists():
        shutil.rmtree(resolved_path)


def assemble_release(
        layout: ReleaseLayout,
        *,
        environment: Mapping[str, str] | None = None,
) -> Path:
    executable = layout.bundle_dir / f"{APP_NAME}.exe"
    if not executable.is_file():
        raise ReleaseBuildError(f"PyInstaller bundle is missing: {executable}")
    if not (layout.project_root / "LICENSE").is_file():
        raise ReleaseBuildError("Project file is missing: LICENSE")

    layout.dist_root.mkdir(parents=True, exist_ok=True)
    _remove_release_directory(layout.release_dir, layout.dist_root)
    shutil.copytree(layout.bundle_dir, layout.release_dir)
    shutil.copy2(layout.project_root / "LICENSE", layout.release_dir / "LICENSE")
    write_release_environment(
        layout.release_dir / ".env",
        layout.project_root,
        environment,
    )
    collect_third_party_licenses(layout.release_dir / "third-party-licenses")
    return layout.release_dir


def run_pyinstaller(layout: ReleaseLayout) -> Path:
    if sys.platform != "win32" or struct.calcsize("P") * 8 != 64:
        raise ReleaseBuildError("The release must be built with 64-bit Python on Windows")
    specification = layout.project_root / "packaging" / "sct.spec"
    if not specification.is_file():
        raise ReleaseBuildError(f"PyInstaller specification is missing: {specification}")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(layout.build_root / "dist"),
        "--workpath",
        str(layout.build_root / "work"),
        str(specification),
    ]
    try:
        subprocess.run(
            command,
            cwd=layout.project_root,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReleaseBuildError("PyInstaller failed to build the application") from error
    executable = layout.bundle_dir / f"{APP_NAME}.exe"
    if not executable.is_file():
        raise ReleaseBuildError(f"PyInstaller did not create the executable: {executable}")
    return layout.bundle_dir


def _safe_component_directory(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9._-]+", name)
    return "-".join(parts) or "unknown-component"


def write_third_party_licenses(
        destination: Path | str,
        components: Sequence[LicenseComponent],
) -> tuple[Path, ...]:
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    manifest = [
        "Third-party components included in this release",
        "",
    ]
    for component in sorted(components, key=lambda value: value.name.casefold()):
        directory_name = _safe_component_directory(component.name)
        manifest.extend(
            (
                f"{component.name} {component.version}",
                f"Declared license: {component.declared_license}",
            )
        )
        if component.license_files:
            component_directory = root / directory_name
            component_directory.mkdir(parents=True, exist_ok=True)
            for source in component.license_files:
                destination_path = component_directory / source.name
                shutil.copy2(source, destination_path)
                written.append(destination_path)
                manifest.append(
                    f"License file: {directory_name}/{destination_path.name}"
                )
        else:
            manifest.append("License file: not included in the installed distribution")
        manifest.append("")
    manifest_path = root / "README.txt"
    manifest_path.write_text("\n".join(manifest), encoding="utf-8")
    written.insert(0, manifest_path)
    return tuple(written)


def _distribution_license_files(package: Distribution) -> tuple[Path, ...]:
    result: list[Path] = []
    for entry in package.files or ():
        text = str(entry).replace("\\", "/")
        name = Path(text).name.casefold()
        parts = {part.casefold() for part in Path(text).parts}
        if (
                "licenses" not in parts
                and not name.startswith(("license", "copying", "notice"))
        ):
            continue
        path = Path(package.locate_file(entry)).resolve()
        if path.is_file() and path not in result:
            result.append(path)
    return tuple(result)


def _installed_license_components() -> tuple[LicenseComponent, ...]:
    components: list[LicenseComponent] = []
    for distribution_name in LICENSE_DISTRIBUTIONS:
        try:
            package = distribution(distribution_name)
        except PackageNotFoundError as error:
            raise ReleaseBuildError(
                f"Required build distribution is missing: {distribution_name}"
            ) from error
        metadata = package.metadata
        components.append(
            LicenseComponent(
                name=metadata.get("Name", distribution_name),
                version=metadata.get("Version", package.version),
                declared_license=(
                        metadata.get("License-Expression")
                        or metadata.get("License")
                        or "Not declared"
                ),
                license_files=_distribution_license_files(package),
            )
        )

    python_candidates = (
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE",
        Path(sys.prefix) / "LICENSE.txt",
        Path(sys.prefix) / "LICENSE",
    )
    python_license = next(
        (path.resolve() for path in python_candidates if path.is_file()),
        None,
    )
    components.append(
        LicenseComponent(
            name="Python",
            version=platform.python_version(),
            declared_license="Python Software Foundation License 2.0",
            license_files=(python_license,) if python_license is not None else (),
        )
    )
    return tuple(components)


def collect_third_party_licenses(destination: Path | str) -> tuple[Path, ...]:
    return write_third_party_licenses(
        destination,
        _installed_license_components(),
    )


def build_release(
        project_root: Path | str,
        *,
        environment: Mapping[str, str] | None = None,
) -> tuple[Path, Path]:
    validate_project_version(project_root)
    layout = ReleaseLayout.from_project(project_root)
    _resolve_release_url(layout.project_root, environment)
    run_pyinstaller(layout)
    release_dir = assemble_release(layout, environment=environment)
    archive_path = create_release_zip(release_dir, layout.archive_path)
    return release_dir, archive_path


def create_release_zip(
        release_dir: Path | str,
        destination: Path | str,
) -> Path:
    source = Path(release_dir).resolve()
    archive = Path(destination).resolve()
    if not source.is_dir():
        raise ReleaseBuildError(f"Release directory is missing: {source}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(
            archive,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
    ) as release_zip:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                release_zip.write(
                    path,
                    path.relative_to(source.parent).as_posix(),
                )
    return archive


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    try:
        release_dir, archive_path = build_release(project_root)
    except ReleaseBuildError as error:
        print(f"Release build failed: {error}", file=sys.stderr)
        return 1
    print(f"Release directory: {release_dir}")
    print(f"Release archive: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
