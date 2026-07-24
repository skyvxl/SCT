from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from sct.errors import LocalizedError

ERSC_DLL_PATH = r"SeamlessCoop\ersc.dll"
_ARRAY_START = re.compile(r"^[ \t]*external_dlls[ \t]*=[ \t]*\[")
_SECTION = re.compile(r"^[ \t]*\[([^\]]+)]")
_DLL_LINE = re.compile(
    r'^(?P<indent>[ \t]*)(?P<comment>#[ \t]*)?'
    r'(?P<entry>"(?P<raw>(?:\\.|[^"])*)"[ \t]*,?[ \t]*(?:#.*)?)'
    r"(?P<ending>\r?\n)?$"
)
_INLINE_STRING = re.compile(r'"(?P<raw>(?:\\.|[^"])*)"')


class ModEngineConfigError(LocalizedError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalDll:
    path: str
    enabled: bool
    locked: bool


def _normalized_dll_path(value: str) -> str:
    return value.replace("/", "\\").casefold()


def _decode_toml_string(raw_value: str) -> str:
    try:
        return str(tomllib.loads(f'value = "{raw_value}"')["value"])
    except (tomllib.TOMLDecodeError, KeyError) as error:
        raise ModEngineConfigError(
            "modengine_dll_string_invalid",
            "Invalid DLL string in config_eldenring.toml",
        ) from error


def _encode_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class ModEngineConfig:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    @classmethod
    def from_game_directory(cls, game_directory: Path | str) -> ModEngineConfig:
        return cls(Path(game_directory) / "config_eldenring.toml")

    def list_dlls(self) -> tuple[ExternalDll, ...]:
        lines = self._read_lines()
        bounds = self._array_bounds(lines)
        if bounds is None:
            return ()
        start, end = bounds
        parsed: list[ExternalDll] = []
        if start == end:
            source_lines = (lines[start],)
        else:
            source_lines = lines[start + 1 : end]
        for line in source_lines:
            if start == end:
                matches = _INLINE_STRING.finditer(line.partition("[")[2].rpartition("]")[0])
                entries = ((match.group("raw"), True) for match in matches)
            else:
                match = _DLL_LINE.match(line)
                entries = () if match is None else ((match.group("raw"), not match.group("comment")),)
            for raw_path, enabled in entries:
                dll_path = _decode_toml_string(raw_path)
                parsed.append(
                    ExternalDll(
                        path=dll_path,
                        enabled=enabled,
                        locked=_normalized_dll_path(dll_path)
                        == _normalized_dll_path(ERSC_DLL_PATH),
                    )
                )
        return tuple(parsed)

    def ensure_ersc(self) -> None:
        lines = self._read_lines()
        bounds = self._array_bounds(lines)
        if bounds is None:
            self._insert_array(lines)
            return
        start, end = bounds
        existing = self.list_dlls()
        ersc = next((dll for dll in existing if dll.locked), None)
        if ersc is not None:
            if not ersc.enabled:
                self._set_enabled_in_lines(lines, start, end, ERSC_DLL_PATH, True)
                self._atomic_write("".join(lines))
            return
        newline = self._newline(lines)
        encoded = _encode_toml_string(ERSC_DLL_PATH)
        if start == end:
            inline_paths = [dll.path for dll in existing]
            replacement = [f"external_dlls = [{newline}"]
            replacement.extend(
                f'    "{_encode_toml_string(path)}",{newline}' for path in inline_paths
            )
            replacement.append(f'    "{encoded}"{newline}')
            replacement.append(f"]{newline}")
            lines[start : start + 1] = replacement
        else:
            lines.insert(end, f'    "{encoded}"{newline}')
        self._atomic_write("".join(lines))

    def set_enabled(self, path: str, enabled: bool) -> None:
        if _normalized_dll_path(path) == _normalized_dll_path(ERSC_DLL_PATH) and not enabled:
            raise ModEngineConfigError(
                "modengine_ersc_required",
                "ersc.dll is required and cannot be disabled",
            )
        lines = self._read_lines()
        bounds = self._array_bounds(lines)
        if bounds is None:
            raise ModEngineConfigError(
                "modengine_external_dlls_missing",
                "external_dlls is missing from config_eldenring.toml",
            )
        if not self._set_enabled_in_lines(lines, *bounds, path, enabled):
            raise ModEngineConfigError(
                "modengine_dll_not_found",
                f"DLL is not present in external_dlls: {path}",
                params={"path": path},
            )
        self._atomic_write("".join(lines))

    def _set_enabled_in_lines(
        self,
        lines: list[str],
        start: int,
        end: int,
        path: str,
        enabled: bool,
    ) -> bool:
        if start == end:
            return False
        wanted = _normalized_dll_path(path)
        for index in range(start + 1, end):
            match = _DLL_LINE.match(lines[index])
            if match is None:
                continue
            dll_path = _decode_toml_string(match.group("raw"))
            if _normalized_dll_path(dll_path) != wanted:
                continue
            comment = match.group("comment")
            if enabled and comment:
                lines[index] = (
                    f"{match.group('indent')}{match.group('entry')}"
                    f"{match.group('ending') or ''}"
                )
            elif not enabled and not comment:
                lines[index] = (
                    f"{match.group('indent')}# {match.group('entry')}"
                    f"{match.group('ending') or ''}"
                )
            return True
        return False

    def _insert_array(self, lines: list[str]) -> None:
        newline = self._newline(lines)
        encoded = _encode_toml_string(ERSC_DLL_PATH)
        block = [
            f"external_dlls = [{newline}",
            f'    "{encoded}"{newline}',
            f"]{newline}",
        ]
        insertion_index = None
        for index, line in enumerate(lines):
            match = _SECTION.match(line)
            if match and match.group(1).strip().casefold() == "modengine":
                insertion_index = index + 1
                break
        if insertion_index is None:
            if lines and lines[-1].strip():
                lines.append(newline)
            lines.extend([f"[modengine]{newline}", *block])
        else:
            lines[insertion_index:insertion_index] = block
        self._atomic_write("".join(lines))

    def _read_lines(self) -> list[str]:
        if not self.path.is_file():
            return []
        return self.path.read_text(encoding="utf-8-sig").splitlines(keepends=True)

    @staticmethod
    def _newline(lines: list[str]) -> str:
        return "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"

    @staticmethod
    def _array_bounds(lines: list[str]) -> tuple[int, int] | None:
        for start, line in enumerate(lines):
            if not _ARRAY_START.match(line):
                continue
            value = line.partition("=")[2]
            if "]" in value:
                return start, start
            for end in range(start + 1, len(lines)):
                if "]" in lines[end]:
                    return start, end
            raise ModEngineConfigError(
                "modengine_array_unclosed",
                "external_dlls array is not closed",
            )
        return None

    def _atomic_write(self, document: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                delete=False,
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            ) as temporary:
                temporary.write(document)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
