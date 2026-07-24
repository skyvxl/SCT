from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import winreg
except ImportError:  # pragma: no cover - the application is Windows-only
    winreg = None  # type: ignore[assignment]

STEAM_ID64_BASE = 76561197960265728
_TOKEN_PATTERN = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])')


@dataclass(frozen=True, slots=True)
class SteamProfile:
    steam_id: str
    account_name: str
    persona_name: str
    most_recent: bool

    @property
    def display_name(self) -> str:
        name = self.persona_name or self.account_name or self.steam_id
        return f"{name} ({self.steam_id})"


def steam_id64_from_account_id(account_id: int) -> str | None:
    if account_id <= 0:
        return None
    return str(STEAM_ID64_BASE + account_id)


def parse_loginusers(path: Path | str) -> tuple[SteamProfile, ...]:
    loginusers_path = Path(path)
    if not loginusers_path.is_file():
        return ()
    document = loginusers_path.read_text(encoding="utf-8-sig", errors="replace")
    parsed = _parse_vdf(document)
    users = parsed.get("users", {})
    if not isinstance(users, dict):
        return ()
    profiles: list[SteamProfile] = []
    for steam_id, values in users.items():
        if not steam_id.isdecimal() or not isinstance(values, dict):
            continue
        profiles.append(
            SteamProfile(
                steam_id=steam_id,
                account_name=str(values.get("AccountName", "")),
                persona_name=str(values.get("PersonaName", "")),
                most_recent=str(values.get("MostRecent", "0")) == "1",
            )
        )
    return tuple(profiles)


def _parse_vdf(document: str) -> dict[str, Any]:
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(document):
        brace = match.group(2)
        if brace is not None:
            tokens.append(brace)
        else:
            tokens.append(re.sub(r'\\(["\\])', r"\1", match.group(1)))

    def parse_mapping(index: int, stop_at_brace: bool) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(tokens):
            token = tokens[index]
            if token == "}":
                return result, index + 1
            if token == "{":
                index += 1
                continue
            key = token
            index += 1
            if index >= len(tokens):
                result[key] = ""
                break
            if tokens[index] == "{":
                value, index = parse_mapping(index + 1, True)
            else:
                value = tokens[index]
                index += 1
            result[key] = value
        if stop_at_brace:
            return result, index
        return result, index

    return parse_mapping(0, False)[0]


class SteamService:
    def __init__(
        self,
        *,
        run_process: Callable[..., Any] = subprocess.run,
        start_process: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        self._run_process = run_process
        self._start_process = start_process

    def detect_executable(self) -> Path | None:
        candidates: list[Path] = []
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
        if program_files_x86:
            candidates.append(Path(program_files_x86) / "Steam" / "Steam.exe")
        candidates.append(Path(r"C:\Program Files (x86)\Steam\Steam.exe"))
        registry_path = self._registry_steam_path()
        if registry_path is not None:
            candidates.append(registry_path)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def profiles(self, executable: Path | str) -> tuple[SteamProfile, ...]:
        return parse_loginusers(Path(executable).parent / "config" / "loginusers.vdf")

    def active_steam_id(self) -> str | None:
        if winreg is None:
            return None
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Valve\Steam\ActiveProcess",
            ) as key:
                active_user = int(winreg.QueryValueEx(key, "ActiveUser")[0])
        except (OSError, TypeError, ValueError):
            return None
        return steam_id64_from_account_id(active_user)

    def is_running(self) -> bool:
        try:
            result = self._run_process(
                ["tasklist", "/FI", "IMAGENAME eq steam.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return '"steam.exe"' in (result.stdout or "").lower()

    def start(self, executable: Path | str, *, silently: bool) -> None:
        arguments = [str(executable)]
        if silently:
            arguments.append("-silent")
        self._start_process(arguments)

    def launch_game(self, launcher: Path | str) -> None:
        launcher_path = Path(launcher)
        arguments = [str(launcher_path)]
        if launcher_path.suffix.casefold() in {".bat", ".cmd"}:
            arguments = [
                os.environ.get("COMSPEC", "cmd.exe"),
                "/d",
                "/s",
                "/c",
                launcher_path.name,
            ]
        self._start_process(arguments, cwd=str(launcher_path.parent))

    @staticmethod
    def _registry_steam_path() -> Path | None:
        if winreg is None:
            return None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                value = str(winreg.QueryValueEx(key, "SteamExe")[0])
        except OSError:
            return None
        return Path(value.replace("/", "\\"))
