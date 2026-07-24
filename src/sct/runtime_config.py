from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from sct.errors import LocalizedError

ERSC_RELEASE_API_URL = "ERSC_RELEASE_API_URL"


class RuntimeConfigError(LocalizedError):
    pass


def default_dotenv_paths() -> tuple[Path, ...]:
    if getattr(sys, "frozen", False):
        return (Path(sys.executable).resolve().parent / ".env",)
    project_root = Path(__file__).resolve().parents[2]
    current_directory = Path.cwd().resolve()
    candidates = (current_directory / ".env", project_root / ".env")
    return tuple(dict.fromkeys(candidates))


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        key, separator, raw_value = line.partition("=")
        if not separator:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    ersc_release_api_url: str

    @classmethod
    def load(
        cls,
        *,
        environment: Mapping[str, str] | None = None,
        search_paths: Sequence[Path] | None = None,
    ) -> RuntimeConfig:
        environment_values = os.environ if environment is None else environment
        release_url = environment_values.get(ERSC_RELEASE_API_URL, "").strip()
        if not release_url:
            for path in default_dotenv_paths() if search_paths is None else search_paths:
                release_url = _read_dotenv(Path(path)).get(ERSC_RELEASE_API_URL, "").strip()
                if release_url:
                    break
        parsed = urlparse(release_url)
        if not release_url or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeConfigError(
                "runtime_config_invalid",
                f"{ERSC_RELEASE_API_URL} must contain a valid GitHub Releases API URL",
            )
        return cls(ersc_release_api_url=release_url)
