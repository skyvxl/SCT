from __future__ import annotations

import configparser
import os
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

SECTION = "Settings"
DIRECTORY_NAME = "SeamlessCoopToolkit"


@dataclass(frozen=True, slots=True)
class AppSettings:
    backup_method: int = 0
    preferred_language: str = "en"
    mod_path: str = ""
    game_exe_path: str = ""
    steam_exe_path: str = ""
    auto_check_updates: bool = True
    run_steam_silently: bool = False
    steam_id: str = ""
    save_file_type: str = "ER0000.co2"
    backup_directory: str = ""
    enable_sounds: bool = True
    sound_volume: int = 20
    auto_backup_interval: int = 5
    sleep_between_saves: int = 10
    max_backups: int = 20
    save_backup_key: str = ""
    load_backup_key: str = ""
    start_auto_backup_key: str = ""
    stop_auto_backup_key: str = ""
    fps_target: int = 60


def default_settings_path() -> Path:
    roaming = os.environ.get("APPDATA")
    base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    return base / DIRECTORY_NAME / "settings.ini"


class SettingsStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_settings_path()

    def ensure_exists(self) -> AppSettings:
        if not self.path.exists():
            defaults = AppSettings()
            self.save(defaults)
            return defaults
        return self.load()

    def load(self) -> AppSettings:
        parser = self._read_parser()
        values = parser[SECTION] if parser.has_section(SECTION) else {}
        defaults = AppSettings()
        loaded: dict[str, Any] = {}
        for field in fields(defaults):
            raw_value = values.get(field.name)
            default_value = getattr(defaults, field.name)
            loaded[field.name] = self._parse_value(raw_value, default_value)
        return AppSettings(**loaded)

    def update(self, **changes: Any) -> AppSettings:
        valid_names = {field.name for field in fields(AppSettings)}
        unknown = set(changes) - valid_names
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown settings fields: {names}")
        settings = replace(self.load(), **changes)
        self.save(settings)
        return settings

    def save(self, settings: AppSettings) -> None:
        parser = self._read_parser()
        if not parser.has_section(SECTION):
            parser.add_section(SECTION)
        section = parser[SECTION]
        for name, value in asdict(settings).items():
            section[name] = self._serialize_value(value)
        self._write_parser(parser)

    def _read_parser(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser(interpolation=None)
        if self.path.exists():
            parser.read(self.path, encoding="utf-8")
        return parser

    def _write_parser(self, parser: configparser.ConfigParser) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    newline="\n",
                    delete=False,
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
            ) as temporary:
                parser.write(temporary)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _parse_value(raw_value: str | None, default: Any) -> Any:
        if raw_value is None:
            return default
        try:
            if isinstance(default, bool):
                normalized = raw_value.strip().lower()
                if normalized in {"1", "yes", "true", "on"}:
                    return True
                if normalized in {"0", "no", "false", "off"}:
                    return False
                return default
            if isinstance(default, int):
                return int(raw_value)
            return raw_value
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _serialize_value(value: Any) -> str:
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)
