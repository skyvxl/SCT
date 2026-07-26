from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

BUILD_SCHEMA_VERSION = 1
BUILD_FILE_FILTER = "Seamless Co-op Toolkit build (*.sctbuild)"
ATTRIBUTE_NAMES = (
    "vigor",
    "mind",
    "endurance",
    "strength",
    "dexterity",
    "intelligence",
    "faith",
    "arcane",
)

WEAPON_SLOTS = (
    "primary_left_wep",
    "primary_right_wep",
    "secondary_left_wep",
    "secondary_right_wep",
    "tertiary_left_wep",
    "tertiary_right_wep",
)
AMMUNITION_SLOTS = (
    "primary_arrow",
    "primary_bolt",
    "secondary_arrow",
    "secondary_bolt",
    "tertiary_arrow",
    "tertiary_bolt",
)
ARMOR_SLOTS = ("helmet", "armor", "gauntlet", "leggings")
TALISMAN_SLOTS = tuple(f"accessory_{slot}" for slot in range(1, 6))
SPELL_SLOTS = tuple(f"magic_slot_{slot}" for slot in range(14))
QUICK_ITEM_SLOTS = tuple(f"quick_item_{slot}" for slot in range(1, 11))
PHYSICK_SLOTS = ("physick_tear_1", "physick_tear_2")
ALL_EQUIPMENT_SLOTS = (
        WEAPON_SLOTS
        + AMMUNITION_SLOTS
        + ARMOR_SLOTS
        + TALISMAN_SLOTS
        + SPELL_SLOTS
        + QUICK_ITEM_SLOTS
        + PHYSICK_SLOTS
)


def _frozen_int_mapping(values: Mapping[str, object]) -> Mapping[str, int]:
    return MappingProxyType({str(key): int(value) for key, value in values.items()})


@dataclass(frozen=True, slots=True)
class EquipmentItem:
    item_id: int
    quantity: int = 1
    upgrade_level: int = 0
    ash_of_war: int | None = None

    def __post_init__(self) -> None:
        if self.item_id < 0:
            raise ValueError("Equipment item ID cannot be negative")
        if not 1 <= self.quantity <= 9999:
            raise ValueError("Equipment quantity must be between 1 and 9999")
        if not 0 <= self.upgrade_level <= 25:
            raise ValueError("Equipment upgrade level must be between 0 and 25")
        if self.ash_of_war is not None and self.ash_of_war < 0:
            raise ValueError("Ash of War ID cannot be negative")

    @property
    def effective_item_id(self) -> int:
        return self.item_id + self.upgrade_level

    def to_dict(self) -> dict[str, int | None]:
        return {
            "item_id": self.item_id,
            "quantity": self.quantity,
            "upgrade_level": self.upgrade_level,
            "ash_of_war": self.ash_of_war,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> EquipmentItem:
        if "item_id" not in payload:
            raise ValueError("Equipment item is missing item_id")
        ash = payload.get("ash_of_war")
        return cls(
            item_id=int(payload["item_id"]),
            quantity=int(payload.get("quantity", 1)),
            upgrade_level=int(payload.get("upgrade_level", 0)),
            ash_of_war=None if ash is None else int(ash),
        )


EquipmentValue = EquipmentItem | None


@dataclass(frozen=True, slots=True)
class PlayerDetails:
    player_num: int
    is_local: bool
    name: str
    steam_id: str | None
    stats: Mapping[str, int]
    equipment: Mapping[str, EquipmentValue]

    def __post_init__(self) -> None:
        if self.player_num < 0:
            raise ValueError("Player number cannot be negative")
        unknown = set(self.equipment).difference(ALL_EQUIPMENT_SLOTS)
        if unknown:
            raise ValueError(f"Unknown equipment slots: {', '.join(sorted(unknown))}")


@dataclass(frozen=True, slots=True)
class SavedBuild:
    source_name: str
    stats: Mapping[str, int]
    equipment: Mapping[str, EquipmentValue]
    schema_version: int = BUILD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BUILD_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported build schema {self.schema_version}; "
                f"expected {BUILD_SCHEMA_VERSION}"
            )
        unknown = set(self.equipment).difference(ALL_EQUIPMENT_SLOTS)
        if unknown:
            raise ValueError(f"Unknown equipment slots: {', '.join(sorted(unknown))}")

    @classmethod
    def from_player(cls, player: PlayerDetails) -> SavedBuild:
        return cls(
            source_name=player.name,
            stats=_frozen_int_mapping(player.stats),
            equipment=MappingProxyType(dict(player.equipment)),
        )

    def to_dict(self) -> dict[str, Any]:
        equipment: dict[str, dict[str, int | None] | None] = {}
        for slot, item in self.equipment.items():
            equipment[slot] = None if item is None else item.to_dict()
        return {
            "schema_version": self.schema_version,
            "source_name": self.source_name,
            "stats": dict(self.stats),
            "equipment": equipment,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> SavedBuild:
        try:
            schema_version = int(payload["schema_version"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Build file is missing a valid schema_version") from error
        if schema_version != BUILD_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported build schema {schema_version}; "
                f"expected {BUILD_SCHEMA_VERSION}"
            )
        stats_payload = payload.get("stats", {})
        equipment_payload = payload.get("equipment", {})
        if not isinstance(stats_payload, Mapping) or not isinstance(
                equipment_payload, Mapping
        ):
            raise ValueError("Build stats and equipment must be objects")
        equipment: dict[str, EquipmentValue] = {}
        for slot, value in equipment_payload.items():
            if value is None:
                equipment[str(slot)] = None
            elif isinstance(value, Mapping):
                equipment[str(slot)] = EquipmentItem.from_dict(value)
            else:
                raise ValueError(f"Invalid equipment value for slot {slot}")
        return cls(
            source_name=str(payload.get("source_name", "")).strip() or "Unknown",
            stats=_frozen_int_mapping(stats_payload),
            equipment=MappingProxyType(equipment),
            schema_version=schema_version,
        )

    @classmethod
    def from_json(cls, value: str) -> SavedBuild:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("Build file is not valid JSON") from error
        if not isinstance(payload, Mapping):
            raise ValueError("Build root must be an object")
        return cls.from_dict(payload)

    def save(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json() + "\n", encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: Path | str) -> SavedBuild:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


def calculate_level(stats: Mapping[str, int]) -> int:
    attributes = [max(1, min(99, int(stats.get(name, 1)))) for name in ATTRIBUTE_NAMES]
    return max(1, min(713, sum(attributes) - 79))
