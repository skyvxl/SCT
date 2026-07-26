from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from enum import Enum
from typing import Any, Protocol

from sct.game.errors import GameProcessNotFound
from sct.game.memory import MemoryClientProtocol
from sct.game.players import load_elden_ring_offsets
from sct.game.signatures import AOBScanner

NO_WEIGHT_ORIGINAL_PATTERN = "FF C3 83 FB 05 7C CB 4C 8D 5C 24 70"
NO_WEIGHT_PATCHED_PATTERN = "0F 57 F6 90 90 7C CB 4C 8D 5C 24 70"
NO_WEIGHT_PATCH = b"\x0f\x57\xf6\x90\x90"
NO_WEIGHT_FALLBACK_ORIGINAL = b"\xff\xc3\x83\xfb\x05"


class Cheat(Enum):
    NO_WEIGHT = "NoWeight"
    NO_DEATH = "NoDead"
    NO_DAMAGE = "NoDamage"
    NO_HIT = "NoHit"
    INFINITE_STAMINA = "NoStaminaConsumption"
    INFINITE_FP = "NoFPConsumption"
    INFINITE_CONSUMABLES = "NoGoodsConsume"


class ResolverProtocol(Protocol):
    def resolve(self, symbol: str) -> Any: ...


class ScannerProtocol(Protocol):
    def scan_module_unique(
            self,
            module: Any,
            pattern: str,
            *,
            symbol: str,
    ) -> int: ...


MemoryFactory = Callable[[], MemoryClientProtocol]
ResolverFactory = Callable[[MemoryClientProtocol], ResolverProtocol]
ScannerFactory = Callable[[MemoryClientProtocol], ScannerProtocol]


def _offset(mapping: Mapping[str, Any], *keys: str) -> int:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, Mapping):
            raise KeyError(".".join(keys))
        value = value[key]
    return value if isinstance(value, int) else int(str(value), 0)


class EldenRingCheatRuntime:
    def __init__(
            self,
            memory_factory: MemoryFactory,
            resolver_factory: ResolverFactory,
            *,
            scanner_factory: ScannerFactory = AOBScanner,
            offsets: Mapping[str, Any] | None = None,
            start_background: bool = True,
            interval: float = 0.1,
    ) -> None:
        self._memory_factory = memory_factory
        self._resolver_factory = resolver_factory
        self._scanner_factory = scanner_factory
        self._offsets = offsets or load_elden_ring_offsets()
        self._start_background = start_background
        self._interval = interval
        self._lock = threading.Lock()
        self._enabled: set[Cheat] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._no_weight_originals: dict[int, bytes] = {}

    def enabled_cheats(self) -> frozenset[Cheat]:
        with self._lock:
            return frozenset(self._enabled)

    def set_enabled(self, cheat: Cheat, enabled: bool) -> None:
        with self._lock:
            previous = cheat in self._enabled
            if enabled:
                self._enabled.add(cheat)
            else:
                self._enabled.discard(cheat)
        try:
            self._apply_single_with_new_session(cheat, enabled)
        except Exception:
            with self._lock:
                if previous:
                    self._enabled.add(cheat)
                else:
                    self._enabled.discard(cheat)
            raise
        if enabled:
            self._ensure_thread()

    def enforce_once(self) -> None:
        enabled = self.enabled_cheats()
        if not enabled:
            return
        try:
            memory = self._memory_factory()
        except GameProcessNotFound:
            self._clear_enabled()
            return
        try:
            resolver = self._resolver_factory(memory)
            for cheat in enabled - {Cheat.NO_WEIGHT}:
                self._write_state(memory, resolver, cheat, True)
        finally:
            memory.close()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1.0, self._interval * 4))
        for cheat in self.enabled_cheats():
            try:
                self._apply_single_with_new_session(cheat, False)
            except Exception:
                pass
        self._clear_enabled()

    def _clear_enabled(self) -> None:
        with self._lock:
            self._enabled.clear()

    def _ensure_thread(self) -> None:
        if not self._start_background:
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._enforcement_loop,
                name="EldenRingCheatRuntime",
                daemon=True,
            )
            self._thread.start()

    def _enforcement_loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            if not self.enabled_cheats():
                continue
            try:
                self.enforce_once()
            except Exception:
                time.sleep(min(1.0, self._interval * 5))

    def _apply_single_with_new_session(self, cheat: Cheat, enabled: bool) -> None:
        memory = self._memory_factory()
        try:
            if cheat is Cheat.NO_WEIGHT:
                self._apply_no_weight(memory, enabled)
                return
            resolver = self._resolver_factory(memory)
            self._write_state(memory, resolver, cheat, enabled)
        finally:
            memory.close()

    def _apply_no_weight(self, memory: MemoryClientProtocol, enabled: bool) -> None:
        module = memory.module("eldenring.exe")
        scanner = self._scanner_factory(memory)
        if enabled:
            address = scanner.scan_module_unique(
                module,
                NO_WEIGHT_ORIGINAL_PATTERN,
                symbol="ER_NoWeight_Original",
            )
            self._no_weight_originals[address] = memory.read_bytes(address, 5)
            memory.write_bytes(address, NO_WEIGHT_PATCH)
            return
        if self._no_weight_originals:
            for address, original in tuple(self._no_weight_originals.items()):
                memory.write_bytes(address, original)
            self._no_weight_originals.clear()
            return
        address = scanner.scan_module_unique(
            module,
            NO_WEIGHT_PATCHED_PATTERN,
            symbol="ER_NoWeight_Patched",
        )
        memory.write_bytes(address, NO_WEIGHT_FALLBACK_ORIGINAL)

    def _write_state(
            self,
            memory: MemoryClientProtocol,
            resolver: ResolverProtocol,
            cheat: Cheat,
            enabled: bool,
    ) -> None:
        world_pointer = resolver.resolve("WorldChrManPtrAddr").address
        world = memory.read_ptr(world_pointer)
        slots = memory.read_ptr(world + 0x10EF8) if world else 0
        local_player = memory.read_ptr(slots) if slots else 0
        if not local_player:
            raise RuntimeError("Local Elden Ring player is not loaded")

        if cheat in {
            Cheat.NO_DEATH,
            Cheat.NO_DAMAGE,
            Cheat.INFINITE_FP,
            Cheat.INFINITE_STAMINA,
        }:
            flags_pointer = memory.read_ptr(local_player + 0x190)
            flags = memory.read_ptr(flags_pointer) if flags_pointer else 0
            if not flags:
                raise RuntimeError("Local Elden Ring player flags are unavailable")
            address = flags + _offset(self._offsets, "cheats", "flag_base")
            bit_name = cheat.value
            bit = _offset(self._offsets, "cheats", "bits", bit_name)
            self._set_bit(memory, address, bit, enabled)
            return

        if cheat is Cheat.INFINITE_CONSUMABLES:
            address = local_player + _offset(
                self._offsets,
                "cheats",
                "no_goods_base",
            )
            self._set_bit(memory, address, 0, enabled)
            return

        if cheat is Cheat.NO_HIT:
            address = local_player + _offset(self._offsets, "cheats", "no_hit_base")
            self._set_bit(memory, address, 3, enabled)
            return

        raise ValueError(f"Unsupported Elden Ring cheat: {cheat.value}")

    @staticmethod
    def _set_bit(
            memory: MemoryClientProtocol,
            address: int,
            bit: int,
            enabled: bool,
    ) -> None:
        current = memory.read_u8(address)
        updated = current | (1 << bit) if enabled else current & ~(1 << bit)
        if updated != current:
            memory.write_u8(address, updated)
