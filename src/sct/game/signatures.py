from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sct.game.errors import (
    PatternNotFound,
    PatternNotUnique,
    SignatureConfigError,
    SignatureNotFound,
)
from sct.game.memory import MemoryClientProtocol, ModuleInfo


def _parse_aob(pattern: str) -> tuple[int | None, ...]:
    tokens: list[int | None] = []
    for part in pattern.strip().split():
        tokens.append(None if part in {"?", "??"} else int(part, 16))
    return tuple(tokens)


def compile_aob_regex(pattern: str) -> re.Pattern[bytes]:
    tokens = _parse_aob(pattern)
    if not tokens:
        raise ValueError("AOB pattern cannot be empty")
    chunks = (b"." if token is None else re.escape(bytes([token])) for token in tokens)
    return re.compile(b"".join(chunks), flags=re.DOTALL)


@dataclass(frozen=True, slots=True)
class AobMatch:
    address: int


class AOBScanner:
    def __init__(self, memory: MemoryClientProtocol) -> None:
        self._memory = memory

    def scan_module(
            self,
            module: ModuleInfo,
            pattern: str,
            *,
            symbol: str,
    ) -> tuple[AobMatch, ...]:
        regex = compile_aob_regex(pattern)
        pattern_length = len(_parse_aob(pattern))
        chunk_size = 1024 * 1024
        overlap = max(pattern_length - 1, 0)
        previous_tail = b""
        module_offset = 0
        matches: list[AobMatch] = []
        while module_offset < module.size:
            read_size = min(chunk_size, module.size - module_offset)
            data = self._memory.read_bytes(module.base + module_offset, read_size)
            buffer = previous_tail + data
            origin = module.base + module_offset - len(previous_tail)
            matches.extend(AobMatch(origin + match.start()) for match in regex.finditer(buffer))
            previous_tail = buffer[-overlap:] if overlap else b""
            module_offset += read_size
        return tuple(matches)

    def scan_module_unique(self, module: ModuleInfo, pattern: str, *, symbol: str) -> int:
        matches = self.scan_module(module, pattern, symbol=symbol)
        if not matches:
            raise PatternNotFound(symbol)
        if len(matches) != 1:
            raise PatternNotUnique(symbol, len(matches))
        return matches[0].address


@dataclass(frozen=True, slots=True)
class Signature:
    symbol: str
    pattern: str
    offset: int
    module: str | None
    kind: str
    rel32_at: int
    rip_base_at: int


def _parse_offset(value: object) -> int:
    text = str(value).strip().lower()
    sign = 1
    if text.startswith("+"):
        text = text[1:]
    elif text.startswith("-"):
        sign = -1
        text = text[1:]
    if not text.startswith("0x"):
        raise SignatureConfigError(f"Signature offset must be hexadecimal: {value}")
    return sign * int(text, 16)


class SignatureStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        try:
            self._data: dict[str, Any] = tomllib.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise SignatureConfigError(f"Unable to load signature file: {self.path}") from error

    def get(self, symbol: str) -> Signature:
        entry = self._data.get("symbols", {}).get(symbol)
        if not isinstance(entry, dict) or not str(entry.get("pattern", "")).strip():
            raise SignatureNotFound(symbol)
        return Signature(
            symbol=symbol,
            pattern=str(entry["pattern"]),
            offset=_parse_offset(entry.get("offset", "0x0")),
            module=str(entry["module"]) if entry.get("module") else None,
            kind=str(entry.get("kind", "absolute")).strip().lower(),
            rel32_at=int(entry.get("rel32_at", 3)),
            rip_base_at=int(entry.get("rip_base_at", 7)),
        )


@dataclass(frozen=True, slots=True)
class ResolvedSymbol:
    symbol: str
    address: int


class SymbolResolver:
    def __init__(
            self,
            memory: MemoryClientProtocol,
            signature_path: Path | str,
            *,
            default_module: str,
    ) -> None:
        self._memory = memory
        self._scanner = AOBScanner(memory)
        self._store = SignatureStore(signature_path)
        self._default_module = default_module
        self._cache: dict[str, int] = {}

    def resolve(self, symbol: str) -> ResolvedSymbol:
        cached = self._cache.get(symbol)
        if cached is not None:
            return ResolvedSymbol(symbol, cached)
        signature = self._store.get(symbol)
        module = self._memory.module(signature.module or self._default_module)
        match = self._scanner.scan_module_unique(
            module,
            signature.pattern,
            symbol=symbol,
        )
        if signature.kind == "absolute":
            address = match + signature.offset
        elif signature.kind == "rip_relative":
            relative = self._memory.read_i32(match + signature.rel32_at)
            address = match + signature.rip_base_at + relative + signature.offset
        else:
            raise SignatureConfigError(
                f"Unknown signature kind '{signature.kind}' for '{symbol}'"
            )
        self._cache[symbol] = address
        return ResolvedSymbol(symbol, address)
