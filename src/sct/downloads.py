from __future__ import annotations

import hashlib
import shutil
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sct.errors import LocalizedError

ProgressCallback = Callable[[int, int | None], None]


class DownloadError(LocalizedError):
    pass


class UnsafeArchiveError(LocalizedError):
    pass


def download_file(
    url: str,
    destination: Path | str,
    *,
    expected_digest: str | None = None,
    expected_size: int | None = None,
    progress: ProgressCallback | None = None,
    chunk_size: int = 1024 * 256,
) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    received = 0
    request = Request(url, headers={"User-Agent": "Seamless-Coop-Mod-Manager"})
    try:
        with urlopen(request, timeout=60) as response, target.open("wb") as output:
            header_size = response.headers.get("Content-Length")
            total = expected_size
            if total is None and header_size and header_size.isdigit():
                total = int(header_size)
            while chunk := response.read(chunk_size):
                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress is not None:
                    progress(received, total)
    except (HTTPError, URLError, OSError) as error:
        target.unlink(missing_ok=True)
        raise DownloadError(
            "download_failed",
            f"Unable to download archive: {error}",
        ) from error

    if expected_size is not None and received != expected_size:
        target.unlink(missing_ok=True)
        raise DownloadError(
            "download_size_mismatch",
            f"Downloaded size mismatch: expected {expected_size}, got {received}",
            params={"expected": expected_size, "actual": received},
        )
    normalized_digest = (expected_digest or "").casefold().removeprefix("sha256:")
    if normalized_digest and digest.hexdigest().casefold() != normalized_digest:
        target.unlink(missing_ok=True)
        raise DownloadError(
            "download_checksum_mismatch",
            "Downloaded archive SHA-256 mismatch",
        )
    return target


def _validated_member_path(info: zipfile.ZipInfo) -> PurePosixPath:
    normalized_name = info.filename.replace("\\", "/")
    posix_path = PurePosixPath(normalized_name)
    windows_path = PureWindowsPath(info.filename)
    if (
        not normalized_name
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in posix_path.parts
    ):
        raise UnsafeArchiveError(
            "archive_path_unsafe",
            f"Archive contains an unsafe path: {info.filename}",
            params={"path": info.filename},
        )
    file_type = (info.external_attr >> 16) & 0o170000
    if info.create_system == 3 and file_type == stat.S_IFLNK:
        raise UnsafeArchiveError(
            "archive_symlink_unsafe",
            f"Archive contains a symbolic link: {info.filename}",
            params={"path": info.filename},
        )
    return posix_path


def safe_extract_zip(archive: Path | str, destination: Path | str) -> Path:
    target_root = Path(destination)
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = [(info, _validated_member_path(info)) for info in bundle.infolist()]
            target_root.mkdir(parents=True, exist_ok=True)
            for info, relative_path in members:
                target = target_root.joinpath(*relative_path.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except UnsafeArchiveError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise UnsafeArchiveError(
            "archive_extract_failed",
            f"Unable to extract ZIP archive: {error}",
        ) from error
    return target_root
