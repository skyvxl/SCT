from __future__ import annotations

import configparser
import os
import re
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

_SECTION_PATTERN = re.compile(r"^\s*\[([^\]]+)]")
_OPTION_PATTERN = re.compile(r"^(\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*?)(\r?\n)?$")


@dataclass(frozen=True, slots=True)
class ErscSettings:
    allow_invaders: bool = True
    death_debuffs: bool = True
    allow_summons: bool = True
    overhead_player_display: int = 0
    skip_splash_screens: bool = True
    append_steam_id_to_players: bool = False
    always_spectate_on_death: bool = False
    default_boot_master_volume: int = 5
    enemy_health_scaling: int = 35
    enemy_damage_scaling: int = 0
    enemy_posture_scaling: int = 15
    boss_health_scaling: int = 100
    boss_damage_scaling: int = 0
    boss_posture_scaling: int = 20
    cooppassword: str = "12345"
    save_file_extension: str = "co2"
    mod_language_override: str = ""


FIELD_OPTIONS: dict[str, tuple[str, str]] = {
    "allow_invaders": ("GAMEPLAY", "allow_invaders"),
    "death_debuffs": ("GAMEPLAY", "death_debuffs"),
    "allow_summons": ("GAMEPLAY", "allow_summons"),
    "overhead_player_display": ("GAMEPLAY", "overhead_player_display"),
    "skip_splash_screens": ("GAMEPLAY", "skip_splash_screens"),
    "append_steam_id_to_players": ("GAMEPLAY", "append_steam_id_to_players"),
    "always_spectate_on_death": ("GAMEPLAY", "always_spectate_on_death"),
    "default_boot_master_volume": ("GAMEPLAY", "default_boot_master_volume"),
    "enemy_health_scaling": ("SCALING", "enemy_health_scaling"),
    "enemy_damage_scaling": ("SCALING", "enemy_damage_scaling"),
    "enemy_posture_scaling": ("SCALING", "enemy_posture_scaling"),
    "boss_health_scaling": ("SCALING", "boss_health_scaling"),
    "boss_damage_scaling": ("SCALING", "boss_damage_scaling"),
    "boss_posture_scaling": ("SCALING", "boss_posture_scaling"),
    "cooppassword": ("PASSWORD", "cooppassword"),
    "save_file_extension": ("SAVE", "save_file_extension"),
    "mod_language_override": ("LANGUAGE", "mod_language_override"),
}
SECTION_ORDER = ("GAMEPLAY", "SCALING", "PASSWORD", "SAVE", "LANGUAGE")


class ErscSettingsStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    @classmethod
    def from_game_directory(cls, game_directory: Path | str) -> ErscSettingsStore:
        return cls(Path(game_directory) / "SeamlessCoop" / "ersc_settings.ini")

    def load(self) -> ErscSettings:
        defaults = ErscSettings()
        if not self.path.is_file():
            return defaults
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(self.path, encoding="utf-8-sig")
        loaded: dict[str, Any] = {}
        for field in fields(defaults):
            section, option = FIELD_OPTIONS[field.name]
            default = getattr(defaults, field.name)
            raw = parser.get(section, option, fallback=None)
            loaded[field.name] = self._parse_value(raw, default)
        return ErscSettings(**loaded)

    def save(self, settings: ErscSettings) -> None:
        document = self.path.read_text(encoding="utf-8-sig") if self.path.is_file() else ""
        newline = "\r\n" if "\r\n" in document else "\n"
        lines = document.splitlines(keepends=True)
        values = {
            FIELD_OPTIONS[field.name]: self._serialize_value(getattr(settings, field.name))
            for field in fields(settings)
        }
        lookup = {
            (section.casefold(), option.casefold()): value
            for (section, option), value in values.items()
        }
        found: set[tuple[str, str]] = set()
        current_section = ""
        updated_lines: list[str] = []
        for line in lines:
            section_match = _SECTION_PATTERN.match(line)
            if section_match:
                current_section = section_match.group(1).casefold()
                updated_lines.append(line)
                continue
            option_match = _OPTION_PATTERN.match(line)
            if option_match:
                key = (current_section, option_match.group(2).casefold())
                if key in lookup:
                    line_ending = option_match.group(5) or ""
                    line = (
                        f"{option_match.group(1)}{option_match.group(2)}"
                        f"{option_match.group(3)}{lookup[key]}{line_ending}"
                    )
                    found.add(key)
            updated_lines.append(line)

        for section in SECTION_ORDER:
            missing = [
                (option, value)
                for (field_section, option), value in values.items()
                if field_section == section and (section.casefold(), option.casefold()) not in found
            ]
            if not missing:
                continue
            updated_lines = self._insert_missing_options(
                updated_lines,
                section,
                missing,
                newline,
            )

        self._atomic_write("".join(updated_lines))

    @staticmethod
    def _insert_missing_options(
        lines: list[str],
        section: str,
        missing: list[tuple[str, str]],
        newline: str,
    ) -> list[str]:
        section_index: int | None = None
        insertion_index = len(lines)
        for index, line in enumerate(lines):
            match = _SECTION_PATTERN.match(line)
            if match and match.group(1).casefold() == section.casefold():
                section_index = index
                continue
            if section_index is not None and match and index > section_index:
                insertion_index = index
                break
        additions = [f"{option} = {value}{newline}" for option, value in missing]
        if section_index is not None:
            if insertion_index > 0 and not lines[insertion_index - 1].endswith(("\n", "\r")):
                lines = [*lines]
                lines[insertion_index - 1] += newline
            return lines[:insertion_index] + additions + lines[insertion_index:]

        prefix: list[str] = []
        if lines and lines[-1].strip():
            prefix.append(newline)
        prefix.append(f"[{section}]{newline}")
        return lines + prefix + additions

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

    @staticmethod
    def _parse_value(raw: str | None, default: Any) -> Any:
        if raw is None:
            return default
        try:
            if isinstance(default, bool):
                return int(raw.strip()) != 0
            if isinstance(default, int):
                return int(raw.strip())
            return raw.strip()
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _serialize_value(value: Any) -> str:
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)
