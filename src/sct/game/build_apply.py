from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from sct.game.builds import (
    AMMUNITION_SLOTS,
    ARMOR_SLOTS,
    ATTRIBUTE_NAMES,
    PHYSICK_SLOTS,
    QUICK_ITEM_SLOTS,
    SPELL_SLOTS,
    TALISMAN_SLOTS,
    WEAPON_SLOTS,
    EquipmentItem,
    EquipmentValue,
    SavedBuild,
)
from sct.game.errors import GameRuntimeError
from sct.game.memory import MemoryClientProtocol
from sct.game.players import MAX_RUNES, ResolverProtocol, load_elden_ring_offsets

WEAPON_TYPE = 0x00000000
ARMOR_TYPE = 0x10000000
ACCESSORY_TYPE = 0x20000000
GOODS_TYPE = 0x40000000
OTHER_TYPE = 0x80000000

MAX_INVENTORY_ENTRIES = 2689
INVENTORY_ENTRY_SIZE = 0x18
INVENTORY_ID_OFFSET = 0x04

SLOT_NUMBERS = {
    **{name: index for index, name in enumerate(WEAPON_SLOTS)},
    **{name: index + 6 for index, name in enumerate(AMMUNITION_SLOTS)},
    "helmet": 12,
    "armor": 13,
    "gauntlet": 14,
    "leggings": 15,
    **{name: index + 17 for index, name in enumerate(TALISMAN_SLOTS)},
    **{name: index + 22 for index, name in enumerate(QUICK_ITEM_SLOTS)},
    "physick_tear_1": 32,
    "physick_tear_2": 33,
}

EMPTY_DEFAULTS = {
    **{name: 110_000 for name in WEAPON_SLOTS},
    "helmet": 10_000,
    "armor": 10_100,
    "gauntlet": 10_200,
    "leggings": 10_300,
}

STAT_OFFSETS = {
    "level": 0x68,
    "vigor": 0x3C,
    "mind": 0x40,
    "endurance": 0x44,
    "strength": 0x48,
    "dexterity": 0x4C,
    "intelligence": 0x50,
    "faith": 0x54,
    "arcane": 0x58,
    "runes": 0x6C,
}


class EquipmentApplierProtocol(Protocol):
    def prepare(self, equipment: Mapping[str, EquipmentValue]) -> None: ...

    def apply(self, equipment: Mapping[str, EquipmentValue]) -> None: ...


EquipmentApplierFactory = Callable[
    [MemoryClientProtocol, ResolverProtocol],
    EquipmentApplierProtocol,
]


class EldenRingBuildApplyService:
    def __init__(
        self,
        memory: MemoryClientProtocol,
        resolver: ResolverProtocol,
        *,
        equipment_applier_factory: EquipmentApplierFactory | None = None,
    ) -> None:
        self._memory = memory
        self._resolver = resolver
        self._equipment_applier_factory = (
            equipment_applier_factory or EldenRingEquipmentApplier
        )

    def apply(
        self,
        *,
        player_num: int,
        build: SavedBuild,
        equipment_only: bool = False,
    ) -> None:
        if player_num != 0:
            raise GameRuntimeError("Builds can only be applied to the local player")
        if not equipment_only:
            self._validate_stats(build.stats)
        applier = self._equipment_applier_factory(self._memory, self._resolver)
        applier.prepare(build.equipment)
        base = self._local_player_base()
        if not equipment_only:
            self._write_stats(base, build.stats)
        applier.apply(build.equipment)

    @staticmethod
    def _validate_stats(stats: Mapping[str, int]) -> None:
        for name in ATTRIBUTE_NAMES:
            if name not in stats:
                continue
            value = int(stats[name])
            if not 1 <= value <= 99:
                raise ValueError(f"{name} must be between 1 and 99")
        if "level" in stats and not 1 <= int(stats["level"]) <= 713:
            raise ValueError("level must be between 1 and 713")
        if "runes" in stats and not 0 <= int(stats["runes"]) <= MAX_RUNES:
            raise ValueError(f"runes must be between 0 and {MAX_RUNES}")
        if "scadutree_blessing" in stats and not 0 <= int(
            stats["scadutree_blessing"]
        ) <= 20:
            raise ValueError("scadutree_blessing must be between 0 and 20")
        if "revered_spirit_ash_blessing" in stats and not 0 <= int(
            stats["revered_spirit_ash_blessing"]
        ) <= 10:
            raise ValueError(
                "revered_spirit_ash_blessing must be between 0 and 10"
            )

    def _local_player_base(self) -> int:
        world_slot = self._resolver.resolve("WorldChrManPtrAddr").address
        world = self._memory.read_ptr(world_slot)
        slots = self._memory.read_ptr(world + 0x10EF8) if world else 0
        player_ins = self._memory.read_ptr(slots) if slots else 0
        base = self._memory.read_ptr(player_ins + 0x580) if player_ins else 0
        if not base:
            raise GameRuntimeError("Local player is not loaded")
        return base

    def _write_stats(self, base: int, stats: Mapping[str, int]) -> None:
        for name, offset in STAT_OFFSETS.items():
            if name in stats:
                self._memory.write_u32(base + offset, int(stats[name]))
        if "scadutree_blessing" in stats:
            self._memory.write_u8(base + 0xFC, int(stats["scadutree_blessing"]))
        if "revered_spirit_ash_blessing" in stats:
            self._memory.write_u8(
                base + 0xFD,
                int(stats["revered_spirit_ash_blessing"]),
            )


@dataclass(frozen=True, slots=True)
class _PreparedEquipment:
    game_data_man: int
    player_game_data: int
    equip_game_data: int
    equip_inventory_data: int
    inventory_list: int
    equip_gear_function: int
    equip_goods_function: int
    item_give_function: int
    local_player_base: int


class EldenRingEquipmentApplier:
    def __init__(
        self,
        memory: MemoryClientProtocol,
        resolver: ResolverProtocol,
    ) -> None:
        self._memory = memory
        self._resolver = resolver
        self._offsets = load_elden_ring_offsets()
        self._prepared: _PreparedEquipment | None = None

    def prepare(self, equipment: Mapping[str, EquipmentValue]) -> None:
        if not equipment:
            self._prepared = None
            return
        self._validate_equipment(equipment)
        equip_gear = self._resolver.resolve("EquipGearFunc").address
        equip_goods = self._resolver.resolve("EquipGoodsFunc").address
        item_give = self._resolver.resolve("ItemGiveFunc").address
        game_data_slot = self._resolver.resolve("GameDataManPtrAddr").address
        world_slot = self._resolver.resolve("WorldChrManPtrAddr").address

        game_data_man = self._require_pointer(
            self._memory.read_ptr(game_data_slot),
            "GameDataMan",
        )
        player_game_data = self._require_pointer(
            self._memory.read_ptr(game_data_man + 0x08),
            "PlayerGameData",
        )
        equip_inventory_data = self._require_pointer(
            self._memory.read_ptr(player_game_data + 0x5D0),
            "EquipInventoryData",
        )
        inventory_list = self._require_pointer(
            self._memory.read_ptr(equip_inventory_data + 0x10),
            "InventoryList",
        )
        count = self._memory.read_u32(equip_inventory_data + 0x18)
        if count > MAX_INVENTORY_ENTRIES:
            raise GameRuntimeError(
                f"Inventory count {count} exceeds {MAX_INVENTORY_ENTRIES}"
            )
        tail = self._memory.read_u32(equip_inventory_data + 0x1C)
        if tail > 8192:
            raise GameRuntimeError(f"Inventory tail index {tail} is invalid")

        world = self._memory.read_ptr(world_slot)
        slots = self._memory.read_ptr(world + 0x10EF8) if world else 0
        player_ins = self._memory.read_ptr(slots) if slots else 0
        local_base = self._memory.read_ptr(player_ins + 0x580) if player_ins else 0
        self._prepared = _PreparedEquipment(
            game_data_man=game_data_man,
            player_game_data=player_game_data,
            equip_game_data=player_game_data + 0x2B0,
            equip_inventory_data=equip_inventory_data,
            inventory_list=inventory_list,
            equip_gear_function=self._require_pointer(equip_gear, "EquipGear function"),
            equip_goods_function=self._require_pointer(
                equip_goods, "EquipGoods function"
            ),
            item_give_function=self._require_pointer(item_give, "ItemGive function"),
            local_player_base=self._require_pointer(local_base, "LocalPlayer base"),
        )

    def apply(self, equipment: Mapping[str, EquipmentValue]) -> None:
        if not equipment:
            return
        prepared = self._prepared
        if prepared is None:
            raise GameRuntimeError("Equipment application was not prepared")
        equip_data = self._memory.allocate(0x40)
        item_give_data = self._memory.allocate(0x200)
        try:
            used_weapon_indices: set[int] = set()
            for slot_name in QUICK_ITEM_SLOTS:
                if slot_name in equipment and equipment[slot_name] is None:
                    self._equip_slot(prepared, equip_data, SLOT_NUMBERS[slot_name], -1)
            for slot_name, value in equipment.items():
                if slot_name in SPELL_SLOTS:
                    continue
                self._apply_slot(
                    prepared,
                    equip_data,
                    item_give_data,
                    slot_name,
                    value,
                    used_weapon_indices,
                )
            self._apply_spells(prepared, item_give_data, equipment)
        finally:
            self._memory.free(equip_data)
            self._memory.free(item_give_data)

    @staticmethod
    def _validate_equipment(equipment: Mapping[str, EquipmentValue]) -> None:
        for slot, value in equipment.items():
            if slot not in SLOT_NUMBERS and slot not in SPELL_SLOTS:
                raise ValueError(f"Unsupported equipment slot: {slot}")
            if value is not None and not isinstance(value, EquipmentItem):
                raise TypeError(f"Invalid equipment item for slot {slot}")

    @staticmethod
    def _require_pointer(value: int, label: str) -> int:
        if not isinstance(value, int) or value <= 0:
            raise GameRuntimeError(f"{label} is null or invalid")
        return value

    def _apply_slot(
        self,
        prepared: _PreparedEquipment,
        equip_data: int,
        item_give_data: int,
        slot_name: str,
        value: EquipmentValue,
        used_weapon_indices: set[int],
    ) -> None:
        slot = SLOT_NUMBERS[slot_name]
        if value is None:
            default = EMPTY_DEFAULTS.get(slot_name)
            if default is None:
                if slot in {32, 33}:
                    offset = 0x694 + (slot - 32) * 4
                    self._memory.write_u32(
                        prepared.player_game_data + offset,
                        0xFFFFFFFF,
                    )
                else:
                    self._equip_slot(prepared, equip_data, slot, -1)
                return
            value = EquipmentItem(default)

        full_item_id = self._full_item_id(slot_name, value)
        if slot in {32, 33}:
            self._ensure_item(
                prepared,
                item_give_data,
                GOODS_TYPE | 250,
                quantity=1,
            )
            self._ensure_item(
                prepared,
                item_give_data,
                full_item_id,
                quantity=1,
            )
            offset = 0x694 + (slot - 32) * 4
            self._memory.write_u32(
                prepared.player_game_data + offset,
                full_item_id,
            )
            return

        if slot_name in WEAPON_SLOTS and value.ash_of_war is not None:
            self._ensure_ash_of_war(prepared, item_give_data, value.ash_of_war)
            index = self._give_new_item(
                prepared,
                item_give_data,
                full_item_id,
                quantity=1,
                gem=value.ash_of_war,
            )
        else:
            candidates = [
                index
                for index in self._item_indices(prepared, full_item_id)
                if index not in used_weapon_indices
            ]
            index = candidates[0] if candidates else None
            if index is None:
                index = self._give_new_item(
                    prepared,
                    item_give_data,
                    full_item_id,
                    quantity=(1 if slot_name in WEAPON_SLOTS else value.quantity),
                )
        if index is None:
            raise GameRuntimeError(
                f"Unable to give or find item 0x{full_item_id:08X}"
            )
        if slot_name in WEAPON_SLOTS or slot_name in AMMUNITION_SLOTS:
            used_weapon_indices.add(index)
        if slot_name in QUICK_ITEM_SLOTS or slot_name in AMMUNITION_SLOTS:
            self._write_inventory_quantity(prepared, index, value.quantity)
        self._equip_slot(prepared, equip_data, slot, index)

    def _apply_spells(
        self,
        prepared: _PreparedEquipment,
        item_give_data: int,
        equipment: Mapping[str, EquipmentValue],
    ) -> None:
        relevant = [(slot, equipment[slot]) for slot in SPELL_SLOTS if slot in equipment]
        if not relevant:
            return
        magic_base = self._require_pointer(
            self._memory.read_ptr(prepared.local_player_base + 0x530),
            "MagicSlots",
        )
        offsets = self._offsets.get("equipment", {}).get("magic_slot_offsets", {})
        for slot_name, value in relevant:
            index = int(slot_name.rsplit("_", 1)[-1])
            raw_offset = offsets.get(f"slot_{index}")
            if raw_offset is None:
                raise GameRuntimeError(f"Missing magic slot offset for {slot_name}")
            address = magic_base + int(str(raw_offset), 0)
            if value is None:
                self._memory.write_u32(address, 0xFFFFFFFF)
                continue
            self._ensure_item(
                prepared,
                item_give_data,
                GOODS_TYPE | (value.item_id & 0x0FFFFFFF),
                quantity=1,
            )
            self._memory.write_u32(address, value.item_id & 0x0FFFFFFF)

    @staticmethod
    def _full_item_id(slot_name: str, value: EquipmentItem) -> int:
        item_id = value.effective_item_id & 0x0FFFFFFF
        if slot_name in WEAPON_SLOTS or slot_name in AMMUNITION_SLOTS:
            return WEAPON_TYPE | item_id
        if slot_name in ARMOR_SLOTS:
            return ARMOR_TYPE | item_id
        if slot_name in TALISMAN_SLOTS:
            return ACCESSORY_TYPE | item_id
        if slot_name in QUICK_ITEM_SLOTS or slot_name in PHYSICK_SLOTS:
            return GOODS_TYPE | item_id
        return item_id

    def _inventory_entries(
        self,
        prepared: _PreparedEquipment,
    ) -> list[tuple[int, int]]:
        count = self._memory.read_u32(prepared.equip_inventory_data + 0x18)
        if count > MAX_INVENTORY_ENTRIES:
            raise GameRuntimeError(f"Inventory count {count} is invalid")
        entries: list[tuple[int, int]] = []
        populated = 0
        for index in range(MAX_INVENTORY_ENTRIES):
            item_id = self._memory.read_u32(
                prepared.inventory_list
                + index * INVENTORY_ENTRY_SIZE
                + INVENTORY_ID_OFFSET
            )
            if item_id == 0xFFFFFFFF:
                continue
            populated += 1
            entries.append((index, item_id))
            if populated >= count:
                break
        if populated < count:
            raise GameRuntimeError(
                f"Inventory expected {count} populated entries, found {populated}"
            )
        return entries

    def _item_indices(
        self,
        prepared: _PreparedEquipment,
        full_item_id: int,
    ) -> list[int]:
        wanted = full_item_id & 0xFFFFFFFF
        return [
            index
            for index, item_id in self._inventory_entries(prepared)
            if item_id == wanted
        ]

    def _ensure_item(
        self,
        prepared: _PreparedEquipment,
        item_give_data: int,
        full_item_id: int,
        *,
        quantity: int,
    ) -> int | None:
        indices = self._item_indices(prepared, full_item_id)
        if indices:
            return indices[0]
        return self._give_new_item(
            prepared,
            item_give_data,
            full_item_id,
            quantity=quantity,
        )

    def _give_new_item(
        self,
        prepared: _PreparedEquipment,
        item_give_data: int,
        full_item_id: int,
        *,
        quantity: int,
        gem: int = -1,
    ) -> int | None:
        before = set(self._item_indices(prepared, full_item_id))
        table = item_give_data + 32
        self._memory.write_u32(table, 1)
        self._memory.write_u32(table + 4, full_item_id & 0xFFFFFFFF)
        self._memory.write_u32(table + 8, quantity)
        self._memory.write_u32(table + 12, 0xFFFFFFFF)
        self._memory.write_u32(table + 16, gem & 0xFFFFFFFF)
        shellcode = self._build_item_give_stub(
            prepared.item_give_function,
            prepared.game_data_man,
            table,
            item_give_data,
        )
        self._run_shellcode(shellcode)
        after = self._item_indices(prepared, full_item_id)
        return next((index for index in after if index not in before), None) or (
            after[0] if after else None
        )

    def _ensure_ash_of_war(
        self,
        prepared: _PreparedEquipment,
        item_give_data: int,
        ash_of_war: int,
    ) -> None:
        base = ash_of_war & 0x0FFFFFFF
        for item_type in (OTHER_TYPE, GOODS_TYPE):
            if (
                self._ensure_item(
                    prepared,
                    item_give_data,
                    item_type | base,
                    quantity=1,
                )
                is not None
            ):
                return
        raise GameRuntimeError(f"Unable to give Ash of War {ash_of_war}")

    def _write_inventory_quantity(
        self,
        prepared: _PreparedEquipment,
        index: int,
        quantity: int,
    ) -> None:
        self._memory.write_u32(
            prepared.inventory_list + index * INVENTORY_ENTRY_SIZE + 0x08,
            quantity,
        )

    def _equip_slot(
        self,
        prepared: _PreparedEquipment,
        equip_data: int,
        slot: int,
        inventory_index: int,
    ) -> None:
        tail = self._memory.read_u32(prepared.equip_inventory_data + 0x1C)
        if tail > 8192:
            raise GameRuntimeError(f"Inventory tail index {tail} is invalid")
        if inventory_index == -1:
            self._memory.write_u32(equip_data + 0x10, 0xFFFFFFFF)
            final_index = -1
        else:
            inventory_token = self._memory.read_u32(
                prepared.inventory_list + inventory_index * INVENTORY_ENTRY_SIZE
            )
            self._memory.write_u32(equip_data + 0x10, inventory_token)
            final_index = inventory_index + tail

        if slot <= 21:
            function = prepared.equip_gear_function
            remote_slot = slot
            extra_arguments = (1, 1, 0)
        else:
            function = prepared.equip_goods_function
            remote_slot = slot - 22
            extra_arguments = ()
        shellcode = bytearray(
            
                b"\x48\x83\xEC\x38"
                + b"\x48\xB9"
                + prepared.equip_game_data.to_bytes(8, "little")
                + b"\xBA"
                + remote_slot.to_bytes(4, "little")
                + b"\x49\xB8"
                + (equip_data + 0x10).to_bytes(8, "little")
                + b"\x41\xB9"
                + final_index.to_bytes(4, "little", signed=True)
            
        )
        for index, argument in enumerate(extra_arguments):
            shellcode.extend(
                b"\xC7\x44\x24"
                + bytes([0x20 + index * 8])
                + argument.to_bytes(4, "little")
            )
        shellcode.extend(
            b"\x48\xB8"
            + function.to_bytes(8, "little")
            + b"\xFF\xD0\x48\x83\xC4\x38\xC3"
        )
        self._run_shellcode(bytes(shellcode))

    def _run_shellcode(self, shellcode: bytes) -> None:
        remote = self._memory.allocate(len(shellcode))
        try:
            self._memory.write_bytes(remote, shellcode)
            self._memory.start_thread(remote)
        finally:
            self._memory.free(remote)

    @staticmethod
    def _build_item_give_stub(
        function: int,
        game_data_man: int,
        item_table: int,
        scratch: int,
    ) -> bytes:
        return b"".join(
            (
                b"\x48\x83\xEC\x28",
                b"\x48\xB9" + game_data_man.to_bytes(8, "little"),
                b"\x48\xBA" + item_table.to_bytes(8, "little"),
                b"\x49\xB8" + scratch.to_bytes(8, "little"),
                b"\x41\xB9\x00\x00\x00\x00",
                b"\x48\xB8" + function.to_bytes(8, "little"),
                b"\xFF\xD0",
                b"\x48\x83\xC4\x28",
                b"\xC3",
            )
        )
