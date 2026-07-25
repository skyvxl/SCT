from __future__ import annotations

import unittest
from types import MappingProxyType, SimpleNamespace

from sct.game.build_apply import EldenRingBuildApplyService
from sct.game.builds import EquipmentItem, SavedBuild
from sct.game.errors import GameRuntimeError


class FakeMemory:
    def __init__(self) -> None:
        self.ptrs: dict[int, int] = {}
        self.writes_u32: list[tuple[int, int]] = []
        self.writes_u8: list[tuple[int, int]] = []

    def read_ptr(self, address: int) -> int:
        return self.ptrs.get(address, 0)

    def write_u32(self, address: int, value: int) -> None:
        self.writes_u32.append((address, value))

    def write_u8(self, address: int, value: int) -> None:
        self.writes_u8.append((address, value))


class FakeResolver:
    def resolve(self, symbol: str) -> SimpleNamespace:
        self.last_symbol = symbol
        return SimpleNamespace(address=0x100)


class RecordingEquipmentApplier:
    def __init__(self) -> None:
        self.prepared: list[MappingProxyType] = []
        self.applied: list[MappingProxyType] = []

    def prepare(self, equipment: MappingProxyType) -> None:
        self.prepared.append(equipment)

    def apply(self, equipment: MappingProxyType) -> None:
        self.applied.append(equipment)


def make_build(*, vigor: int = 20) -> SavedBuild:
    return SavedBuild(
        source_name="Hero",
        stats=MappingProxyType(
            {
                "level": 11,
                "vigor": vigor,
                "mind": 10,
                "endurance": 10,
                "strength": 10,
                "dexterity": 10,
                "intelligence": 10,
                "faith": 10,
                "arcane": 10,
                "runes": 500,
                "scadutree_blessing": 12,
                "revered_spirit_ash_blessing": 5,
            }
        ),
        equipment=MappingProxyType(
            {
                "primary_right_wep": EquipmentItem(1_000_000, upgrade_level=10),
                "helmet": None,
            }
        ),
    )


class BuildApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = FakeMemory()
        self.memory.ptrs[0x100] = 0x1000
        self.memory.ptrs[0x1000 + 0x10EF8] = 0x2000
        self.memory.ptrs[0x2000] = 0x3000
        self.memory.ptrs[0x3000 + 0x580] = 0x4000
        self.backend = RecordingEquipmentApplier()
        self.service = EldenRingBuildApplyService(
            self.memory,
            FakeResolver(),
            equipment_applier_factory=lambda _memory, _resolver: self.backend,
        )

    def test_apply_preflights_equipment_then_writes_stats_and_equipment(self) -> None:
        build = make_build()

        self.service.apply(player_num=0, build=build)

        self.assertEqual(self.backend.prepared, [build.equipment])
        self.assertEqual(self.backend.applied, [build.equipment])
        self.assertIn((0x4000 + 0x3C, 20), self.memory.writes_u32)
        self.assertIn((0x4000 + 0x68, 11), self.memory.writes_u32)
        self.assertIn((0x4000 + 0x6C, 500), self.memory.writes_u32)
        self.assertIn((0x4000 + 0xFC, 12), self.memory.writes_u8)
        self.assertIn((0x4000 + 0xFD, 5), self.memory.writes_u8)

    def test_equipment_only_never_writes_statistics(self) -> None:
        build = make_build()

        self.service.apply(player_num=0, build=build, equipment_only=True)

        self.assertEqual(self.memory.writes_u32, [])
        self.assertEqual(self.memory.writes_u8, [])
        self.assertEqual(self.backend.applied, [build.equipment])

    def test_invalid_stats_fail_before_prepare_or_any_write(self) -> None:
        with self.assertRaisesRegex(ValueError, "vigor"):
            self.service.apply(player_num=0, build=make_build(vigor=0))

        self.assertEqual(self.backend.prepared, [])
        self.assertEqual(self.memory.writes_u32, [])

    def test_remote_player_mutation_is_rejected(self) -> None:
        with self.assertRaisesRegex(GameRuntimeError, "local player"):
            self.service.apply(player_num=1, build=make_build())

        self.assertEqual(self.backend.prepared, [])
        self.assertEqual(self.memory.writes_u32, [])


if __name__ == "__main__":
    unittest.main()
