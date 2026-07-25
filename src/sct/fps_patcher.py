from __future__ import annotations

import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sct.errors import LocalizedError

_ORIGINAL_SIGNATURE = bytes.fromhex(
    "C7 43 1C 89 88 88 3C EB 6D 89 73 18 EB C7 89 73 18"
)
_FPS_VALUE_OFFSET = 3
_FPS_VALUE_SIZE = 4


@dataclass(frozen=True, slots=True)
class FpsPatchResult:
    executable_path: Path
    backup_path: Path
    target_fps: int


class EldenRingFpsPatcher:
    def __init__(self, game_directory: Path | str) -> None:
        self.game_directory = Path(game_directory)
        self.executable_path = self.game_directory / "eldenring.exe"
        self.backup_path = self.game_directory / "eldenring.exe.bak"

    def backup_exists(self) -> bool:
        return self.backup_path.is_file()

    def patch(self, target_fps: int) -> FpsPatchResult:
        if not isinstance(target_fps, int) or isinstance(target_fps, bool) or not 1 <= target_fps <= 1000:
            raise LocalizedError(
                "fps_target_invalid",
                f"FPS target must be an integer from 1 to 1000: {target_fps!r}",
                params={"value": target_fps},
            )

        source_path = self.backup_path if self.backup_exists() else self.executable_path
        if not source_path.is_file():
            raise LocalizedError(
                "fps_executable_missing",
                f"Elden Ring executable not found: {self.executable_path}",
                params={"path": self.executable_path},
            )

        original = source_path.read_bytes()
        value_offset = self._find_value_offset(original)
        if self.backup_exists():
            self._validate_current_matches_backup(original, value_offset)
        patched = bytearray(original)
        patched[value_offset: value_offset + _FPS_VALUE_SIZE] = struct.pack(
            "<f",
            1 / target_fps,
        )

        if not self.backup_exists():
            self._atomic_copy(self.executable_path, self.backup_path)
        self._atomic_write(self.executable_path, patched, metadata_source=source_path)
        return FpsPatchResult(
            executable_path=self.executable_path,
            backup_path=self.backup_path,
            target_fps=target_fps,
        )

    def restore(self) -> Path:
        if not self.backup_exists():
            raise LocalizedError(
                "fps_backup_missing",
                f"Elden Ring backup not found: {self.backup_path}",
                params={"path": self.backup_path},
            )
        original = self.backup_path.read_bytes()
        value_offset = self._find_value_offset(original)
        self._validate_current_matches_backup(original, value_offset)
        self._atomic_copy(self.backup_path, self.executable_path)
        self.backup_path.unlink()
        return self.executable_path

    def _validate_current_matches_backup(self, original: bytes, value_offset: int) -> None:
        if not self.executable_path.is_file():
            return
        current = self.executable_path.read_bytes()
        if (
                len(current) != len(original)
                or current[:value_offset] != original[:value_offset]
                or current[value_offset + _FPS_VALUE_SIZE:]
                != original[value_offset + _FPS_VALUE_SIZE:]
        ):
            raise LocalizedError(
                "fps_executable_changed",
                "Current Elden Ring executable differs from its backup outside the FPS value",
            )

    @staticmethod
    def _find_value_offset(data: bytes) -> int:
        signature_offset = data.find(_ORIGINAL_SIGNATURE)
        if signature_offset < 0:
            raise LocalizedError(
                "fps_signature_missing",
                "Supported Elden Ring FPS signature was not found",
            )
        if data.find(_ORIGINAL_SIGNATURE, signature_offset + 1) >= 0:
            raise LocalizedError(
                "fps_signature_ambiguous",
                "More than one Elden Ring FPS signature was found",
            )
        return signature_offset + _FPS_VALUE_OFFSET

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)
        try:
            shutil.copy2(source, temporary_path)
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _atomic_write(
            destination: Path,
            data: bytes | bytearray,
            *,
            metadata_source: Path,
    ) -> None:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "wb") as temporary_file:
                temporary_file.write(data)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            shutil.copystat(metadata_source, temporary_path)
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)
