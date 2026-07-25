from __future__ import annotations

import struct
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Final, Protocol

from sct.game.errors import GameRuntimeError
from sct.game.memory import MemoryClientProtocol

GOODS_TYPE_BASE: Final = 0x40000000
EMPTY_ITEM_ID: Final = 0xFFFFFFFF
ITEM_ENTRY_SIZE: Final = 0x18
ITEM_ID_OFFSET: Final = 0x04
ITEM_QUANTITY_OFFSET: Final = 0x08

PLAYER_GAME_DATA_OFFSET: Final = 0x08
INVENTORY_LIST_OFFSET: Final = 0x10
INVENTORY_COUNT_OFFSET: Final = 0x18
TAIL_DATA_INDEX_OFFSET: Final = 0x1C
KEY_ITEMS_BLOCK_OFFSET: Final = 0x10


def pack_goods_id(raw_id: int) -> int:
    if not isinstance(raw_id, int):
        raise TypeError("raw_id must be int")
    if not 0 <= raw_id <= 0x0FFFFFFF:
        raise ValueError("raw_id must fit in the lower 28 bits")
    return GOODS_TYPE_BASE | raw_id


@dataclass(frozen=True, slots=True)
class SeamlessItem:
    raw_id: int
    name: str

    @property
    def packed_id(self) -> int:
        return pack_goods_id(self.raw_id)


SEAMLESS_ITEMS: Final[tuple[SeamlessItem, ...]] = (
    SeamlessItem(8_380_001, "Tiny Great Pot"),
    SeamlessItem(8_380_002, "Effigy of Malenia"),
    SeamlessItem(8_380_003, "Challenger's Lynchpin"),
    SeamlessItem(8_380_004, "Separation Mist"),
    SeamlessItem(8_380_005, "Judicator's Rulebook"),
    SeamlessItem(8_380_006, "Rune Decanter"),
)
_ITEM_BY_PACKED_ID: Final = {item.packed_id: item for item in SEAMLESS_ITEMS}


class InventoryKind(IntEnum):
    PLAYER = 0
    STORAGE = 1
    PLAYER_KEY = 2
    STORAGE_KEY = 3


@dataclass(frozen=True, slots=True)
class InventoryLayout:
    offset: int
    key_items: bool
    max_index: int

    @property
    def key_offset(self) -> int:
        return KEY_ITEMS_BLOCK_OFFSET if self.key_items else 0


DEFAULT_LAYOUTS: Final[Mapping[InventoryKind, InventoryLayout]] = {
    InventoryKind.PLAYER: InventoryLayout(0x5D0, False, 2688),
    InventoryKind.STORAGE: InventoryLayout(0x8D0, False, 1920),
    InventoryKind.PLAYER_KEY: InventoryLayout(0x5D0, True, 384),
    InventoryKind.STORAGE_KEY: InventoryLayout(0x8D0, True, 128),
}


class InventoryMemoryProtocol(Protocol):
    def read_u32(self, address: int) -> int: ...

    def read_ptr(self, address: int) -> int: ...


GameFunctionCaller = Callable[[int, int, int, int], int]


@dataclass(frozen=True, slots=True)
class InventoryHit:
    kind: InventoryKind
    index: int
    raw_id: int
    packed_id: int
    name: str
    quantity: int
    equip_inventory_data: int


@dataclass(frozen=True, slots=True)
class RemovalAttempt:
    hit: InventoryHit
    absolute_index: int
    function_result: int


@dataclass(frozen=True, slots=True)
class RemovalReport:
    initial: tuple[InventoryHit, ...]
    attempts: tuple[RemovalAttempt, ...]
    remaining: tuple[InventoryHit, ...]

    @property
    def calls_made(self) -> int:
        return len(self.attempts)


def _require_pointer(value: int, label: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise GameRuntimeError(f"{label} is null or invalid: {value!r}")
    return value


def _target_signature(
    hits: Sequence[InventoryHit],
) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        sorted((int(hit.kind), hit.packed_id, hit.quantity) for hit in hits)
    )


class SeamlessInventoryCleaner:
    def __init__(
        self,
        *,
        memory: InventoryMemoryProtocol,
        invoke: GameFunctionCaller | None = None,
        layouts: Mapping[InventoryKind, InventoryLayout] = DEFAULT_LAYOUTS,
    ) -> None:
        self._memory = memory
        self._invoke = invoke
        self._layouts = dict(layouts)

    def scan(
        self,
        game_data_man: int,
        *,
        include_storage: bool = False,
    ) -> tuple[InventoryHit, ...]:
        game_data_man = _require_pointer(game_data_man, "GameDataMan")
        player_game_data = _require_pointer(
            self._memory.read_ptr(game_data_man + PLAYER_GAME_DATA_OFFSET),
            "PlayerGameData",
        )
        kinds = [InventoryKind.PLAYER, InventoryKind.PLAYER_KEY]
        if include_storage:
            kinds.extend((InventoryKind.STORAGE, InventoryKind.STORAGE_KEY))
        missing = [kind.name for kind in kinds if kind not in self._layouts]
        if missing:
            raise GameRuntimeError(
                f"Inventory layouts are missing: {', '.join(missing)}"
            )
        hits: list[InventoryHit] = []
        for kind in kinds:
            hits.extend(self._scan_bank(player_game_data, kind))
        return tuple(hits)

    def remove_all(
        self,
        *,
        game_data_man: int,
        remove_item_function: int,
        include_storage: bool = False,
        max_calls: int = 64,
    ) -> RemovalReport:
        if max_calls <= 0:
            raise ValueError("max_calls must be greater than zero")
        function = _require_pointer(remove_item_function, "RemoveItem function")
        if self._invoke is None:
            raise GameRuntimeError("RemoveItem caller is not configured")

        initial = self.scan(game_data_man, include_storage=include_storage)
        if not initial:
            return RemovalReport((), (), ())
        self._preflight(initial, max_calls=max_calls)

        current = initial
        attempts: list[RemovalAttempt] = []
        while current:
            hit = current[0]
            absolute_index = self._absolute_index(hit)
            before = _target_signature(current)
            result = self._invoke(
                function,
                hit.equip_inventory_data,
                absolute_index,
                1,
            )
            attempts.append(RemovalAttempt(hit, absolute_index, result))
            current = self.scan(game_data_man, include_storage=include_storage)
            self._preflight(current, max_calls=max_calls - len(attempts))
            if _target_signature(current) == before:
                raise GameRuntimeError(
                    "RemoveItem made no observable progress for "
                    f"{hit.name} ({hit.raw_id}) in {hit.kind.name}; "
                    "the signature or inventory offsets may be stale"
                )
        return RemovalReport(initial, tuple(attempts), current)

    def _scan_bank(
        self,
        player_game_data: int,
        kind: InventoryKind,
    ) -> list[InventoryHit]:
        layout = self._layouts[kind]
        equip = _require_pointer(
            self._memory.read_ptr(player_game_data + layout.offset),
            f"EquipInventoryData[{kind.name}]",
        )
        count = self._memory.read_u32(
            equip + INVENTORY_COUNT_OFFSET + layout.key_offset
        )
        max_entries = layout.max_index + 1
        if count > max_entries:
            raise GameRuntimeError(
                f"Inventory count for {kind.name} exceeds {max_entries}; "
                "inventory offsets may be stale"
            )
        if count == 0:
            return []
        inventory_list = _require_pointer(
            self._memory.read_ptr(
                equip + INVENTORY_LIST_OFFSET + layout.key_offset
            ),
            f"InventoryList[{kind.name}]",
        )

        hits: list[InventoryHit] = []
        populated = 0
        for index in range(max_entries):
            entry = inventory_list + index * ITEM_ENTRY_SIZE
            packed_id = self._memory.read_u32(entry + ITEM_ID_OFFSET)
            if packed_id == EMPTY_ITEM_ID:
                continue
            populated += 1
            target = _ITEM_BY_PACKED_ID.get(packed_id)
            if target is not None:
                hits.append(
                    InventoryHit(
                        kind=kind,
                        index=index,
                        raw_id=target.raw_id,
                        packed_id=packed_id,
                        name=target.name,
                        quantity=self._memory.read_u32(
                            entry + ITEM_QUANTITY_OFFSET
                        ),
                        equip_inventory_data=equip,
                    )
                )
            if populated >= count:
                break
        if populated < count:
            raise GameRuntimeError(
                f"Inventory count for {kind.name} is {count}, but only "
                f"{populated} populated entries were readable"
            )
        return hits

    def _preflight(
        self,
        hits: Sequence[InventoryHit],
        *,
        max_calls: int,
    ) -> None:
        required_calls = 0
        for hit in hits:
            if hit.quantity <= 0:
                raise GameRuntimeError(
                    f"Invalid quantity {hit.quantity} for {hit.name}"
                )
            required_calls += hit.quantity
            self._absolute_index(hit)
        if required_calls > max_calls:
            raise GameRuntimeError(
                f"Removing Seamless items requires {required_calls} calls, "
                f"but the safety limit is {max_calls}"
            )

    def _absolute_index(self, hit: InventoryHit) -> int:
        layout = self._layouts[hit.kind]
        total_capacity = sum(value.max_index + 1 for value in self._layouts.values())
        tail = self._memory.read_u32(
            hit.equip_inventory_data
            + TAIL_DATA_INDEX_OFFSET
            + layout.key_offset
        )
        if tail >= total_capacity:
            raise GameRuntimeError(
                f"Inventory tail index {tail} for {hit.kind.name} exceeds "
                f"the configured capacity {total_capacity}; "
                "inventory offsets may be stale"
            )
        absolute = hit.index + tail
        if not 0 <= absolute < total_capacity + layout.max_index + 1:
            raise GameRuntimeError(
                f"Inventory absolute index {absolute} for {hit.kind.name} is invalid"
            )
        return absolute


def _u64(value: int, label: str) -> int:
    if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"{label} must be an unsigned 64-bit integer")
    return value


def build_win64_call3_stub(
    function_address: int,
    rcx: int,
    rdx: int,
    r8: int,
) -> bytes:
    function_address = _u64(function_address, "function_address")
    rcx = _u64(rcx, "rcx")
    rdx = _u64(rdx, "rdx")
    r8 = _u64(r8, "r8")
    return b"".join(
        (
            b"\x48\xB9" + struct.pack("<Q", rcx),
            b"\x48\xBA" + struct.pack("<Q", rdx),
            b"\x49\xB8" + struct.pack("<Q", r8),
            b"\x48\xB8" + struct.pack("<Q", function_address),
            b"\x48\x83\xEC\x28",
            b"\xFF\xD0",
            b"\x48\x83\xC4\x28",
            b"\xC3",
        )
    )


class EldenRingInventoryService:
    def __init__(self, memory: MemoryClientProtocol, resolver: object) -> None:
        self._memory = memory
        self._resolver = resolver

    def remove_seamless_items(self) -> RemovalReport:
        game_data_slot = self._resolver.resolve("GameDataManPtrAddr").address
        game_data_man = _require_pointer(
            self._memory.read_ptr(game_data_slot),
            "GameDataMan",
        )
        function = self._resolver.resolve("RemoveItemFunc").address
        cleaner = SeamlessInventoryCleaner(
            memory=self._memory,
            invoke=self._call_three_arguments,
        )
        return cleaner.remove_all(
            game_data_man=game_data_man,
            remove_item_function=function,
        )

    def _call_three_arguments(
        self,
        function_address: int,
        rcx: int,
        rdx: int,
        r8: int,
    ) -> int:
        shellcode = build_win64_call3_stub(function_address, rcx, rdx, r8)
        remote = self._memory.allocate(len(shellcode))
        try:
            self._memory.write_bytes(remote, shellcode)
            return self._memory.start_thread(remote)
        finally:
            self._memory.free(remote)
