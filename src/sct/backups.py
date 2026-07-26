from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sct.errors import LocalizedError

SUPPORTED_SAVE_FILES = frozenset({"ER0000.co2", "ER0000.sl2"})
PIN_INDEX_NAME = "pinned_backups.json"
_INVALID_WINDOWS_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class BackupEntry:
    name: str
    path: Path
    created_at: datetime
    pinned: bool


class SaveLocator:
    def __init__(self, appdata: Path | str) -> None:
        self.root = Path(appdata) / "EldenRing"

    def resolve(self, filename: str, steam_id: str = "") -> Path:
        self._validate_filename(filename)
        selected_id = steam_id.strip()
        if selected_id:
            candidate = self.root / selected_id / filename
            if candidate.is_file():
                return candidate
            raise LocalizedError(
                "backup_save_not_found",
                f"Selected Elden Ring save was not found: {candidate}",
                params={"path": candidate},
            )

        candidates = tuple(
            path / filename
            for path in self._steam_directories()
            if (path / filename).is_file()
        )
        if not candidates:
            raise LocalizedError(
                "backup_save_not_found",
                f"No Elden Ring save named {filename} was found below {self.root}",
                params={"path": self.root},
            )
        if len(candidates) > 1:
            raise LocalizedError(
                "backup_save_account_ambiguous",
                f"More than one Steam account contains {filename}",
            )
        return candidates[0]

    def target_for_restore(self, filename: str, steam_id: str = "") -> Path:
        self._validate_filename(filename)
        selected_id = steam_id.strip()
        if selected_id:
            directory = self.root / selected_id
            if directory.is_dir():
                return directory / filename
        return self.resolve(filename, steam_id)

    def _steam_directories(self) -> tuple[Path, ...]:
        if not self.root.is_dir():
            return ()
        return tuple(
            sorted(
                (
                    child
                    for child in self.root.iterdir()
                    if child.is_dir() and child.name.isdecimal()
                ),
                key=lambda child: child.name,
            )
        )

    @staticmethod
    def _validate_filename(filename: str) -> None:
        if filename not in SUPPORTED_SAVE_FILES:
            raise LocalizedError(
                "backup_save_type_invalid",
                f"Unsupported Elden Ring save filename: {filename!r}",
            )


class BackupRepository:
    def __init__(
            self,
            directory: Path | str,
            *,
            now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.directory = Path(directory)
        self._now = now

    def create(
            self,
            save_path: Path | str,
            *,
            prefix: str = "backup",
            screenshot: bytes | None = None,
    ) -> BackupEntry:
        source = Path(save_path)
        self._validate_save_path(source)
        self.directory.mkdir(parents=True, exist_ok=True)
        name = self._unique_name(prefix)
        destination = self.directory / name
        temporary = self._temporary_path(destination.name)
        try:
            with zipfile.ZipFile(
                    temporary,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                archive.write(source, source.name)
                if screenshot:
                    archive.writestr("screenshot.png", screenshot)
            self._validate_archive(temporary, source.name)
            os.replace(temporary, destination)
        except LocalizedError:
            raise
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            raise LocalizedError(
                "backup_create_failed",
                f"Unable to create backup {destination}: {error}",
            ) from error
        finally:
            temporary.unlink(missing_ok=True)
        return self._entry(destination, self._read_pins())

    def list_entries(self) -> tuple[BackupEntry, ...]:
        if not self.directory.is_dir():
            return ()
        pins = self._read_pins()
        entries: list[BackupEntry] = []
        for path in self.directory.glob("*.zip"):
            if not path.is_file():
                continue
            try:
                entries.append(self._entry(path, pins))
            except OSError:
                continue
        return tuple(
            sorted(
                entries,
                key=lambda entry: entry.created_at,
                reverse=True,
            )
        )

    def read_screenshot(self, name: str) -> bytes | None:
        path = self._archive_path(name)
        if not path.is_file():
            raise LocalizedError(
                "backup_archive_not_found",
                f"Backup archive not found: {path}",
                params={"name": path.name},
            )
        try:
            with zipfile.ZipFile(path, "r") as archive:
                try:
                    return archive.read("screenshot.png")
                except KeyError:
                    return None
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            raise LocalizedError(
                "backup_archive_invalid",
                f"Unable to read screenshot from backup {path}: {error}",
                params={"name": path.name},
            ) from error

    def restore(self, name: str, save_path: Path | str) -> Path:
        destination = Path(save_path)
        self._validate_save_path(destination, must_exist=False)
        archive_path = self._archive_path(name)
        if not archive_path.is_file():
            raise LocalizedError(
                "backup_archive_not_found",
                f"Backup archive not found: {archive_path}",
                params={"name": archive_path.name},
            )
        member = self._validate_archive(archive_path, destination.name)
        temporary = self._temporary_path(destination.name, directory=destination.parent)
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                data = archive.read(member)
            with temporary.open("wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        except LocalizedError:
            raise
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            raise LocalizedError(
                "backup_restore_failed",
                f"Unable to restore {archive_path} to {destination}: {error}",
            ) from error
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def delete(self, name: str) -> None:
        path = self._archive_path(name)
        if not path.is_file():
            raise LocalizedError(
                "backup_archive_not_found",
                f"Backup archive not found: {path}",
                params={"name": path.name},
            )
        try:
            path.unlink()
            pins = self._read_pins()
            if path.name in pins:
                pins.remove(path.name)
                self._write_pins(pins)
        except OSError as error:
            raise LocalizedError(
                "backup_delete_failed",
                f"Unable to delete backup {path}: {error}",
            ) from error

    def set_pinned(self, name: str, pinned: bool) -> BackupEntry:
        path = self._archive_path(name)
        if not path.is_file():
            raise LocalizedError(
                "backup_archive_not_found",
                f"Backup archive not found: {path}",
                params={"name": path.name},
            )
        pins = self._read_pins()
        if pinned:
            pins.add(path.name)
        else:
            pins.discard(path.name)
        self._write_pins(pins)
        return self._entry(path, pins)

    def rename(self, name: str, new_name: str) -> BackupEntry:
        source = self._archive_path(name)
        if not source.is_file():
            raise LocalizedError(
                "backup_archive_not_found",
                f"Backup archive not found: {source}",
                params={"name": source.name},
            )
        normalized = self._normalize_archive_name(new_name)
        destination = self.directory / normalized
        if destination.exists():
            raise LocalizedError(
                "backup_name_exists",
                f"A backup named {normalized!r} already exists",
                params={"name": normalized},
            )
        try:
            source.rename(destination)
            pins = self._read_pins()
            if source.name in pins:
                pins.remove(source.name)
                pins.add(destination.name)
                self._write_pins(pins)
        except OSError as error:
            raise LocalizedError(
                "backup_rename_failed",
                f"Unable to rename {source} to {destination}: {error}",
            ) from error
        return self._entry(destination, self._read_pins())

    def enforce_limit(self, max_regular: int) -> None:
        keep = max(1, int(max_regular))
        regular = [entry for entry in self.list_entries() if not entry.pinned]
        for entry in regular[keep:]:
            try:
                entry.path.unlink()
            except OSError as error:
                raise LocalizedError(
                    "backup_cleanup_failed",
                    f"Unable to remove old backup {entry.path}: {error}",
                ) from error

    def _unique_name(self, prefix: str) -> str:
        safe_prefix = prefix.strip()
        if (
                not safe_prefix
                or _INVALID_WINDOWS_NAME.search(safe_prefix)
                or safe_prefix.endswith((".", " "))
        ):
            raise LocalizedError(
                "backup_name_invalid",
                f"Invalid backup prefix: {prefix!r}",
            )
        timestamp = self._now().strftime("%Y%m%d_%H%M%S")
        base = f"{safe_prefix}_{timestamp}"
        candidate = f"{base}.zip"
        counter = 1
        while (self.directory / candidate).exists():
            candidate = f"{base}_{counter:03d}.zip"
            counter += 1
        return candidate

    def _archive_path(self, name: str) -> Path:
        return self.directory / self._normalize_archive_name(name)

    @staticmethod
    def _normalize_archive_name(name: str) -> str:
        normalized = name.strip()
        if not normalized.casefold().endswith(".zip"):
            normalized += ".zip"
        stem = normalized[:-4]
        if (
                not stem
                or stem in {".", ".."}
                or stem.endswith((".", " "))
                or _INVALID_WINDOWS_NAME.search(normalized)
                or Path(normalized).name != normalized
        ):
            raise LocalizedError(
                "backup_name_invalid",
                f"Invalid backup archive name: {name!r}",
            )
        return normalized

    @staticmethod
    def _validate_save_path(path: Path, *, must_exist: bool = True) -> None:
        if path.name not in SUPPORTED_SAVE_FILES:
            raise LocalizedError(
                "backup_save_type_invalid",
                f"Unsupported Elden Ring save path: {path}",
            )
        if must_exist and not path.is_file():
            raise LocalizedError(
                "backup_save_not_found",
                f"Elden Ring save file not found: {path}",
                params={"path": path},
            )
        if not path.parent.is_dir():
            raise LocalizedError(
                "backup_save_directory_missing",
                f"Elden Ring save directory not found: {path.parent}",
                params={"path": path.parent},
            )

    @staticmethod
    def _validate_archive(path: Path, expected_member: str) -> str:
        try:
            with zipfile.ZipFile(path, "r") as archive:
                members = archive.namelist()
                corrupt_member = archive.testzip()
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            raise LocalizedError(
                "backup_archive_invalid",
                f"Unable to validate backup archive {path}: {error}",
                params={"name": path.name},
            ) from error
        valid_members = (
            [expected_member],
            [expected_member, "screenshot.png"],
        )
        if corrupt_member is not None or members not in valid_members:
            raise LocalizedError(
                "backup_archive_invalid",
                f"Backup {path} contains unexpected members: {members!r}",
                params={"name": path.name},
            )
        return expected_member

    def _read_pins(self) -> set[str]:
        path = self.directory / PIN_INDEX_NAME
        if not path.is_file():
            return set()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return set()
        if not isinstance(value, list):
            return set()
        return {
            item
            for item in value
            if isinstance(item, str)
               and item.casefold().endswith(".zip")
               and Path(item).name == item
        }

    def _write_pins(self, pins: set[str]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / PIN_INDEX_NAME
        temporary = self._temporary_path(PIN_INDEX_NAME)
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as output:
                json.dump(sorted(pins), output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        except OSError as error:
            raise LocalizedError(
                "backup_pin_index_failed",
                f"Unable to update backup pin index {destination}: {error}",
            ) from error
        finally:
            temporary.unlink(missing_ok=True)

    def _temporary_path(self, name: str, *, directory: Path | None = None) -> Path:
        parent = directory or self.directory
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{name}.",
            suffix=".tmp",
            dir=parent,
        )
        os.close(file_descriptor)
        return Path(temporary_name)

    @staticmethod
    def _entry(path: Path, pins: set[str]) -> BackupEntry:
        stat = path.stat()
        return BackupEntry(
            name=path.name,
            path=path,
            created_at=datetime.fromtimestamp(stat.st_mtime),
            pinned=path.name in pins,
        )
