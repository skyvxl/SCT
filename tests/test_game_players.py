from __future__ import annotations

import unittest
from types import SimpleNamespace

from sct.game.builds import EquipmentItem
from sct.game.players import EldenRingPlayerService


class FakeMemory:
    def __init__(self) -> None:
        self.data: dict[int, int] = {}
        self.writes: list[tuple[int, int]] = []

    def read_bytes(self, address: int, size: int) -> bytes:
        return bytes(self.data.get(address + offset, 0) for offset in range(size))

    def _seed(self, address: int, value: int, size: int, *, signed: bool = False) -> None:
        payload = value.to_bytes(size, "little", signed=signed)
        for offset, byte in enumerate(payload):
            self.data[address + offset] = byte

    def seed_ptr(self, address: int, value: int) -> None:
        self._seed(address, value, 8)

    def seed_i32(self, address: int, value: int) -> None:
        self._seed(address, value, 4, signed=True)

    def seed_u32(self, address: int, value: int) -> None:
        self._seed(address, value, 4)

    def seed_u64(self, address: int, value: int) -> None:
        self._seed(address, value, 8)

    def seed_u16(self, address: int, value: int) -> None:
        self._seed(address, value, 2)

    def seed_u8(self, address: int, value: int) -> None:
        self._seed(address, value, 1)

    def seed_name(self, address: int, value: str) -> None:
        for index, character in enumerate(value):
            self.seed_u16(address + index * 2, ord(character))
        self.seed_u16(address + len(value) * 2, 0)

    def read_ptr(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 8), "little")

    def read_i32(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 4), "little", signed=True)

    def read_u8(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 1), "little")

    def read_u16(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 2), "little")

    def read_u32(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 4), "little")

    def read_u64(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 8), "little")

    def write_u32(self, address: int, value: int) -> None:
        self.writes.append((address, value))
        self.seed_u32(address, value)


class FakeResolver:
    def resolve(self, symbol: str) -> SimpleNamespace:
        addresses = {
            "WorldChrManPtrAddr": 0x100,
            "GameDataManPtrAddr": 0x200,
        }
        return SimpleNamespace(address=addresses[symbol])


def seed_player(
    memory: FakeMemory,
    *,
    slot_array: int,
    slot: int,
    player_ins: int,
    base: int,
    name: str,
    level: int,
    hp: int,
    max_hp: int,
    runes: int,
) -> None:
    memory.seed_ptr(slot_array + slot * 0x10, player_ins)
    memory.seed_ptr(player_ins + 0x580, base)
    memory.seed_i32(base + 0x68, level)
    memory.seed_i32(base + 0x10, hp)
    memory.seed_i32(base + 0x14, max_hp)
    memory.seed_i32(base + 0x6C, runes)
    memory.seed_name(base + 0x9C, name)
    memory.seed_i32(base + 0x398, 1010000 + slot)
    memory.seed_i32(base + 0x3C8, 2000000 + slot)
    memory.seed_i32(base + 0x3DC, 3000000 + slot)
    magic = 0x8000 + slot * 0x100
    memory.seed_ptr(base + 0x530, magic)
    memory.seed_u32(magic + 0x10, 4000 + slot)


class PlayerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = FakeMemory()
        world = 0x1000
        slot_array = 0x2000
        self.memory.seed_ptr(0x100, world)
        self.memory.seed_ptr(world + 0x10EF8, slot_array)
        seed_player(
            self.memory,
            slot_array=slot_array,
            slot=0,
            player_ins=0x3000,
            base=0x4000,
            name="Local Hero",
            level=42,
            hp=1200,
            max_hp=1500,
            runes=987654,
        )
        seed_player(
            self.memory,
            slot_array=slot_array,
            slot=1,
            player_ins=0x3100,
            base=0x5000,
            name="Phantom",
            level=77,
            hp=900,
            max_hp=1000,
            runes=444,
        )
        self.memory.seed_ptr(0x3100 + 0x5B0, 0x6000)
        self.memory.seed_u64(0x6000 + 0x8, 76561198000000001)

        self.memory.seed_ptr(0x200, 0x7000)
        self.memory.seed_ptr(0x7000 + 0x8, 0x7100)
        self.memory.seed_u32(0x7100 + 0x694, 5001)
        self.memory.seed_u32(0x7100 + 0x698, 5002)
        self.memory.seed_u32(0x7100 + 0x650, 6001)
        self.service = EldenRingPlayerService(self.memory, FakeResolver())

    def test_list_players_returns_local_first_and_reads_remote_equipment(self) -> None:
        players = self.service.list_players()

        self.assertEqual([player.player_num for player in players], [0, 1])
        local, remote = players
        self.assertTrue(local.is_local)
        self.assertEqual(local.name, "Local Hero")
        self.assertEqual(local.level, 42)
        self.assertEqual((local.hp, local.max_hp), (1200, 1500))
        self.assertEqual(local.runes, 987654)
        self.assertEqual(local.equipment["primary_left_wep"], 1010000)
        self.assertEqual(local.equipment["magic_slot_0"], 4000)
        self.assertEqual(local.equipment["quick_item_1"], 6001)
        self.assertEqual(local.equipment["physick_tear_1"], 5001)

        self.assertFalse(remote.is_local)
        self.assertEqual(remote.steam_id, "76561198000000001")
        self.assertEqual(remote.runes, None)
        self.assertEqual(remote.equipment["primary_left_wep"], 1010001)
        self.assertEqual(remote.equipment["magic_slot_0"], 4001)
        self.assertNotIn("quick_item_1", remote.equipment)
        self.assertNotIn("physick_tear_1", remote.equipment)

    def test_invalid_slots_are_omitted_without_discarding_valid_players(self) -> None:
        self.memory.seed_ptr(0x2000 + 2 * 0x10, 0x3200)
        self.memory.seed_ptr(0x3200 + 0x580, 0x5200)
        self.memory.seed_i32(0x5200 + 0x68, 9999)
        self.memory.seed_i32(0x5200 + 0x14, 100)

        players = self.service.list_players()

        self.assertEqual([player.player_num for player in players], [0, 1])

    def test_write_local_runes_targets_local_player_and_validates_game_limit(self) -> None:
        self.service.write_local_runes(123456)

        self.assertEqual(self.memory.writes[-1], (0x4000 + 0x6C, 123456))
        with self.assertRaises(ValueError):
            self.service.write_local_runes(-1)
        with self.assertRaises(ValueError):
            self.service.write_local_runes(1_000_000_000)

    def test_read_details_includes_stats_and_normalizes_weapon_upgrade(self) -> None:
        base = 0x4000
        for offset, value in (
            (0x3C, 30),
            (0x40, 20),
            (0x44, 25),
            (0x48, 18),
            (0x4C, 22),
            (0x50, 10),
            (0x54, 12),
            (0x58, 9),
        ):
            self.memory.seed_i32(base + offset, value)
        self.memory.seed_u8(base + 0xFC, 15)
        self.memory.seed_u8(base + 0xFD, 7)
        self.memory.seed_i32(base + 0x39C, 1_000_025)
        self.memory.seed_i32(base + 0x3C8, -1)

        details = self.service.read_player_details(0)

        self.assertIsNotNone(details)
        self.assertEqual(details.stats["vigor"], 30)
        self.assertEqual(details.stats["scadutree_blessing"], 15)
        self.assertEqual(details.stats["revered_spirit_ash_blessing"], 7)
        self.assertEqual(
            details.equipment["primary_right_wep"],
            EquipmentItem(item_id=1_000_000, upgrade_level=25),
        )
        self.assertIsNone(details.equipment["helmet"])

    def test_remote_details_mark_local_only_equipment_as_unavailable(self) -> None:
        details = self.service.read_player_details(1)

        self.assertIsNotNone(details)
        self.assertFalse(details.is_local)
        self.assertNotIn("runes", details.stats)
        self.assertNotIn("quick_item_1", details.equipment)
        self.assertNotIn("physick_tear_1", details.equipment)
        self.assertEqual(
            details.equipment["primary_left_wep"],
            EquipmentItem(item_id=1_010_000, upgrade_level=1),
        )


if __name__ == "__main__":
    unittest.main()
