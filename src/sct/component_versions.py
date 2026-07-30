from __future__ import annotations

import re
from pathlib import Path

_ERSC_VERSION_PATTERN = re.compile(
    rb"SteamMatchMaking\d+\x00"
    rb"v?(\d+\.\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.-]+)?)\x00"
)
_SEMANTIC_VERSION_PATTERN = re.compile(
    r"^\s*v?(\d+(?:\.\d+){2,3})(?:[-+][0-9A-Za-z.-]+)?\s*$",
    re.IGNORECASE,
)


def detect_ersc_version(game_directory: Path | str) -> str | None:
    dll_path = Path(game_directory) / "SeamlessCoop" / "ersc.dll"
    if not dll_path.is_file():
        return None
    try:
        match = _ERSC_VERSION_PATTERN.search(dll_path.read_bytes())
    except OSError:
        return None
    if match is None:
        return None
    return match.group(1).decode("ascii")


def compare_versions(first: str, second: str) -> int:
    first_parts = _version_parts(first)
    second_parts = _version_parts(second)
    width = max(len(first_parts), len(second_parts))
    left = first_parts + (0,) * (width - len(first_parts))
    right = second_parts + (0,) * (width - len(second_parts))
    return (left > right) - (left < right)


def _version_parts(value: str) -> tuple[int, ...]:
    match = _SEMANTIC_VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"Unsupported version: {value}")
    return tuple(int(part) for part in match.group(1).split("."))
