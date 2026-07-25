from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from sct.game.builds import (
    ATTRIBUTE_NAMES,
    BUILD_SCHEMA_VERSION,
    EquipmentItem,
    PlayerDetails,
    SavedBuild,
    calculate_level,
)


class BuildModelTests(unittest.TestCase):
    def test_build_round_trip_preserves_empty_and_unavailable_slots(self) -> None:
        details = PlayerDetails(
            player_num=0,
            is_local=True,
            name="Local Hero",
            steam_id=None,
            stats=MappingProxyType(
                {
                    "level": 42,
                    "vigor": 30,
                    "mind": 20,
                    "endurance": 25,
                    "strength": 18,
                    "dexterity": 22,
                    "intelligence": 10,
                    "faith": 12,
                    "arcane": 9,
                    "runes": 1234,
                }
            ),
            equipment=MappingProxyType(
                {
                    "primary_right_wep": EquipmentItem(
                        item_id=1_000_000,
                        upgrade_level=25,
                        ash_of_war=10_000,
                    ),
                    "helmet": None,
                    # quick_item_1 is intentionally unavailable and therefore absent.
                }
            ),
        )

        encoded = SavedBuild.from_player(details).to_json()
        decoded = SavedBuild.from_json(encoded)

        self.assertEqual(decoded.schema_version, BUILD_SCHEMA_VERSION)
        self.assertEqual(decoded.source_name, "Local Hero")
        self.assertEqual(decoded.stats["vigor"], 30)
        self.assertEqual(
            decoded.equipment["primary_right_wep"],
            EquipmentItem(1_000_000, 1, 25, 10_000),
        )
        self.assertIsNone(decoded.equipment["helmet"])
        self.assertNotIn("quick_item_1", decoded.equipment)

    def test_build_file_is_json_and_rejects_unknown_schema(self) -> None:
        build = SavedBuild(
            source_name="Hero",
            stats=MappingProxyType({"level": 1}),
            equipment=MappingProxyType({}),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hero.sctbuild"
            build.save(path)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], BUILD_SCHEMA_VERSION)
            self.assertEqual(SavedBuild.load(path), build)

            payload["schema_version"] = 999
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                SavedBuild.load(path)

    def test_level_calculation_uses_elden_ring_attribute_sum(self) -> None:
        attributes = {name: 10 for name in ATTRIBUTE_NAMES}

        self.assertEqual(calculate_level(attributes), 1)
        attributes["vigor"] = 20
        self.assertEqual(calculate_level(attributes), 11)

    def test_invalid_equipment_values_are_rejected_before_serialization(self) -> None:
        with self.assertRaises(ValueError):
            EquipmentItem(item_id=-2)
        with self.assertRaises(ValueError):
            EquipmentItem(item_id=1_000_000, quantity=0)
        with self.assertRaises(ValueError):
            EquipmentItem(item_id=1_000_000, upgrade_level=26)


if __name__ == "__main__":
    unittest.main()
