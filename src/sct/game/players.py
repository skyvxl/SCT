from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Protocol

from sct.game.builds import WEAPON_SLOTS, EquipmentItem, PlayerDetails
from sct.game.elden_ring import OFFSETS_PATH
from sct.game.memory import MemoryClientProtocol

MAX_PLAYER_SLOTS = 6
MAX_RUNES = 999_999_999


class ResolverProtocol(Protocol):
    def resolve(self, symbol: str) -> Any: ...


@lru_cache(maxsize=1)
def load_elden_ring_offsets() -> dict[str, Any]:
    return tomllib.loads(OFFSETS_PATH.read_text(encoding="utf-8"))


def _hex_value(mapping: Mapping[str, Any], *keys: str) -> int:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            raise KeyError(".".join(keys))
        value = value[key]
    if isinstance(value, int):
        return value
    return int(str(value), 0)


@dataclass(frozen=True, slots=True)
class PlayerSnapshot:
    player_num: int
    is_local: bool
    name: str
    steam_id: str | None
    level: int
    hp: int
    max_hp: int
    runes: int | None
    equipment: Mapping[str, int]


class EldenRingPlayerService:
    def __init__(
        self,
        memory: MemoryClientProtocol,
        resolver: ResolverProtocol,
        offsets: Mapping[str, Any] | None = None,
    ) -> None:
        self._memory = memory
        self._resolver = resolver
        self._offsets = offsets or load_elden_ring_offsets()

    def list_players(self) -> tuple[PlayerSnapshot, ...]:
        players: list[PlayerSnapshot] = []
        for player_num in range(MAX_PLAYER_SLOTS):
            player = self.read_player(player_num)
            if player is not None:
                players.append(player)
        return tuple(players)

    def read_player(self, player_num: int) -> PlayerSnapshot | None:
        if not 0 <= player_num < MAX_PLAYER_SLOTS:
            return None
        try:
            player_ins, base = self._player_addresses(player_num)
            if not player_ins or not base:
                return None
            level = self._memory.read_i32(base + 0x68)
            max_hp = self._memory.read_i32(base + 0x14)
            if not 0 <= level <= 713 or max_hp <= 0:
                return None
            name = self._read_name(base + 0x9C)
            hp = self._memory.read_i32(base + 0x10)
            steam_id = self._read_steam_id(player_ins)
            equipment = self._read_equipment(base, local=player_num == 0)
            return PlayerSnapshot(
                player_num=player_num,
                is_local=player_num == 0,
                name=name or "Unknown",
                steam_id=steam_id,
                level=level,
                hp=hp,
                max_hp=max_hp,
                runes=self._memory.read_i32(base + 0x6C) if player_num == 0 else None,
                equipment=MappingProxyType(equipment),
            )
        except (OSError, RuntimeError, TypeError, ValueError, KeyError):
            return None

    def write_local_runes(self, value: int) -> None:
        if not 0 <= value <= MAX_RUNES:
            raise ValueError(f"Rune count must be between 0 and {MAX_RUNES}")
        _player_ins, base = self._player_addresses(0)
        if not base:
            raise RuntimeError("Local player is not loaded")
        self._memory.write_u32(base + 0x6C, value)

    def read_player_details(self, player_num: int) -> PlayerDetails | None:
        player = self.read_player(player_num)
        if player is None:
            return None
        try:
            _player_ins, base = self._player_addresses(player_num)
            if not base:
                return None
            stats = {
                "level": self._memory.read_i32(base + 0x68),
                "vigor": self._memory.read_i32(base + 0x3C),
                "mind": self._memory.read_i32(base + 0x40),
                "endurance": self._memory.read_i32(base + 0x44),
                "strength": self._memory.read_i32(base + 0x48),
                "dexterity": self._memory.read_i32(base + 0x4C),
                "intelligence": self._memory.read_i32(base + 0x50),
                "faith": self._memory.read_i32(base + 0x54),
                "arcane": self._memory.read_i32(base + 0x58),
            }
            if player.is_local:
                stats.update(
                    {
                        "runes": self._memory.read_i32(base + 0x6C),
                        "scadutree_blessing": self._memory.read_u8(base + 0xFC),
                        "revered_spirit_ash_blessing": self._memory.read_u8(
                            base + 0xFD
                        ),
                    }
                )
            return PlayerDetails(
                player_num=player.player_num,
                is_local=player.is_local,
                name=player.name,
                steam_id=player.steam_id,
                stats=MappingProxyType(stats),
                equipment=MappingProxyType(
                    self._normalize_equipment(player.equipment)
                ),
            )
        except (OSError, RuntimeError, TypeError, ValueError, KeyError):
            return None

    def _world_character_manager(self) -> int:
        pointer_address = self._resolver.resolve("WorldChrManPtrAddr").address
        return self._memory.read_ptr(pointer_address)

    def _player_addresses(self, player_num: int) -> tuple[int, int]:
        world = self._world_character_manager()
        if not world:
            return 0, 0
        slots = self._memory.read_ptr(world + 0x10EF8)
        if not slots:
            return 0, 0
        player_ins = self._memory.read_ptr(slots + player_num * 0x10)
        if not player_ins:
            return 0, 0
        return player_ins, self._memory.read_ptr(player_ins + 0x580)

    def _read_name(self, address: int) -> str:
        characters: list[str] = []
        for index in range(32):
            codepoint = self._memory.read_u16(address + index * 2)
            if codepoint == 0:
                break
            characters.append(chr(codepoint))
        return "".join(characters)

    def _read_steam_id(self, player_ins: int) -> str | None:
        try:
            steam_data = self._memory.read_ptr(player_ins + 0x5B0)
            if not steam_data:
                return None
            value = self._memory.read_u64(steam_data + 0x8)
            return str(value) if value > 0 else None
        except (OSError, RuntimeError, ValueError):
            return None

    def _read_equipment(self, base: int, *, local: bool) -> dict[str, int]:
        fields = {
            "primary_left_wep": 0x398,
            "primary_right_wep": 0x39C,
            "secondary_left_wep": 0x3A0,
            "secondary_right_wep": 0x3A4,
            "tertiary_left_wep": 0x3A8,
            "tertiary_right_wep": 0x3AC,
            "primary_arrow": 0x3B0,
            "primary_bolt": 0x3B4,
            "secondary_arrow": 0x3B8,
            "secondary_bolt": 0x3BC,
            "tertiary_arrow": 0x3C0,
            "tertiary_bolt": 0x3C4,
            "helmet": 0x3C8,
            "armor": 0x3CC,
            "gauntlet": 0x3D0,
            "leggings": 0x3D4,
            "hair": 0x3D8,
            "accessory_1": 0x3DC,
            "accessory_2": 0x3E0,
            "accessory_3": 0x3E4,
            "accessory_4": 0x3E8,
            "accessory_5": 0x3EC,
        }
        equipment = {
            name: self._memory.read_i32(base + offset) for name, offset in fields.items()
        }
        self._read_magic_slots(base, equipment)
        if local:
            self._read_local_quick_items(equipment)
        return equipment

    def _read_magic_slots(self, base: int, equipment: dict[str, int]) -> None:
        magic_base_offset = _hex_value(self._offsets, "equipment", "magic_slots_base")
        magic_base = self._memory.read_ptr(base + magic_base_offset)
        if not magic_base:
            return
        entries = self._offsets.get("equipment", {}).get("magic_slot_offsets", {})
        for slot in range(14):
            offset_value = entries.get(f"slot_{slot}")
            if offset_value is None:
                continue
            value = self._memory.read_u32(magic_base + int(str(offset_value), 0))
            item_id = value & 0x0FFFFFFF
            equipment[f"magic_slot_{slot}"] = (
                -1 if item_id in {0x0FFFFFFF, 0xFFFFFFFF} else item_id
            )

    def _read_local_quick_items(self, equipment: dict[str, int]) -> None:
        game_data_pointer = self._resolver.resolve("GameDataManPtrAddr").address
        game_data_manager = self._memory.read_ptr(game_data_pointer)
        if not game_data_manager:
            return
        player_data_offset = _hex_value(self._offsets, "equipment", "player_game_data")
        player_data = self._memory.read_ptr(game_data_manager + player_data_offset)
        if not player_data:
            return
        for name, address in (
            ("physick_tear_1", player_data + 0x694),
            ("physick_tear_2", player_data + 0x698),
        ):
            value = self._memory.read_u32(address)
            equipment[name] = -1 if value == 0xFFFFFFFF else value & 0x0FFFFFFF
        entries = self._offsets.get("equipment", {}).get("quick_item_offsets", {})
        for slot in range(1, 11):
            offset_value = entries.get(f"slot_{slot}")
            if offset_value is None:
                continue
            value = self._memory.read_u32(player_data + int(str(offset_value), 0))
            equipment[f"quick_item_{slot}"] = value & 0x0FFFFFFF

    @staticmethod
    def _normalize_equipment(
        equipment: Mapping[str, int],
    ) -> dict[str, EquipmentItem | None]:
        normalized: dict[str, EquipmentItem | None] = {}
        for slot, raw_value in equipment.items():
            if slot == "hair":
                continue
            value = int(raw_value)
            if value in {-1, 0xFFFFFFFF, 0x0FFFFFFF}:
                normalized[slot] = None
                continue
            if slot in WEAPON_SLOTS:
                upgrade_level = value % 100
                normalized[slot] = EquipmentItem(
                    item_id=value - upgrade_level,
                    upgrade_level=upgrade_level,
                )
            else:
                normalized[slot] = EquipmentItem(item_id=value & 0x0FFFFFFF)
        return normalized


def player_details_from_snapshot(player: PlayerSnapshot) -> PlayerDetails:
    stats = {"level": player.level}
    if player.runes is not None:
        stats["runes"] = player.runes
    return PlayerDetails(
        player_num=player.player_num,
        is_local=player.is_local,
        name=player.name,
        steam_id=player.steam_id,
        stats=MappingProxyType(stats),
        equipment=MappingProxyType(
            EldenRingPlayerService._normalize_equipment(player.equipment)
        ),
    )
