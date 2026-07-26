from __future__ import annotations

import unittest

from sct.game.errors import GameRuntimeError
from sct.game.inventory import (
    GOODS_TYPE_BASE,
    SEAMLESS_ITEMS,
    InventoryKind,
    InventoryLayout,
    SeamlessInventoryCleaner,
    build_win64_call3_stub,
    pack_goods_id,
)


class FakeMemory:
    def __init__(self) -> None:
        self.u32: dict[int, int] = {}
        self.ptrs: dict[int, int] = {}

    def read_u32(self, address: int) -> int:
        return self.u32.get(address, 0)

    def read_ptr(self, address: int) -> int:
        return self.ptrs.get(address, 0)


class FakeInventory:
    GAME_DATA_MAN = 0x1000
    PLAYER_DATA = 0x2000
    PLAYER_EQUIP = 0x3000
    PLAYER_LIST = 0x5000
    PLAYER_KEY_LIST = 0x6000

    LAYOUTS = {
        InventoryKind.PLAYER: InventoryLayout(0x5D0, False, 15),
        InventoryKind.PLAYER_KEY: InventoryLayout(0x5D0, True, 15),
    }

    def __init__(self) -> None:
        self.memory = FakeMemory()
        self.memory.ptrs[self.GAME_DATA_MAN + 0x8] = self.PLAYER_DATA
        self.memory.ptrs[self.PLAYER_DATA + 0x5D0] = self.PLAYER_EQUIP
        self._init_bank(False, self.PLAYER_LIST, tail=11)
        self._init_bank(True, self.PLAYER_KEY_LIST, tail=23)

    def _init_bank(self, key_items: bool, list_ptr: int, *, tail: int) -> None:
        key_offset = 0x10 if key_items else 0
        equip = self.PLAYER_EQUIP
        self.memory.ptrs[equip + 0x10 + key_offset] = list_ptr
        self.memory.u32[equip + 0x18 + key_offset] = 0
        self.memory.u32[equip + 0x1C + key_offset] = tail
        for index in range(16):
            entry = list_ptr + index * 0x18
            self.memory.u32[entry + 0x4] = 0xFFFFFFFF
            self.memory.u32[entry + 0x8] = 0

    def put(
            self,
            kind: InventoryKind,
            index: int,
            raw_id: int,
            *,
            quantity: int = 1,
    ) -> None:
        key_offset = 0x10 if self.LAYOUTS[kind].key_items else 0
        list_ptr = self.memory.ptrs[self.PLAYER_EQUIP + 0x10 + key_offset]
        entry = list_ptr + index * 0x18
        self.memory.u32[entry + 0x4] = pack_goods_id(raw_id)
        self.memory.u32[entry + 0x8] = quantity
        self.memory.u32[self.PLAYER_EQUIP + 0x18 + key_offset] += 1

    def remove(self, equip: int, absolute_index: int) -> None:
        for key_items in (False, True):
            key_offset = 0x10 if key_items else 0
            tail = self.memory.u32[equip + 0x1C + key_offset]
            index = absolute_index - tail
            if not 0 <= index <= 15:
                continue
            list_ptr = self.memory.ptrs[equip + 0x10 + key_offset]
            entry = list_ptr + index * 0x18
            if self.memory.u32[entry + 0x4] == 0xFFFFFFFF:
                continue
            quantity = self.memory.u32[entry + 0x8]
            if quantity > 1:
                self.memory.u32[entry + 0x8] = quantity - 1
            else:
                self.memory.u32[entry + 0x4] = 0xFFFFFFFF
                self.memory.u32[entry + 0x8] = 0
                self.memory.u32[equip + 0x18 + key_offset] -= 1
            return
        raise AssertionError("unknown fake inventory index")


class RecordingInvoker:
    def __init__(self, fixture: FakeInventory, *, mutate: bool = True) -> None:
        self.fixture = fixture
        self.mutate = mutate
        self.calls: list[tuple[int, int, int, int]] = []

    def __call__(self, function: int, rcx: int, rdx: int, r8: int) -> int:
        self.calls.append((function, rcx, rdx, r8))
        if self.mutate:
            self.fixture.remove(rcx, rdx)
        return 0


class SeamlessInventoryTests(unittest.TestCase):
    def cleaner(
            self,
            fixture: FakeInventory,
            invoker: RecordingInvoker | None = None,
    ) -> SeamlessInventoryCleaner:
        return SeamlessInventoryCleaner(
            memory=fixture.memory,
            invoke=invoker,
            layouts=fixture.LAYOUTS,
        )

    def test_exact_six_ids_are_packed_as_goods(self) -> None:
        self.assertEqual(GOODS_TYPE_BASE, 0x40000000)
        self.assertEqual(pack_goods_id(8_380_001), 0x407FDE61)
        self.assertEqual(pack_goods_id(8_380_006), 0x407FDE66)
        self.assertEqual(
            [item.raw_id for item in SEAMLESS_ITEMS],
            list(range(8_380_001, 8_380_007)),
        )

    def test_remove_uses_tail_adjusted_index_and_repeats_for_quantity(self) -> None:
        fixture = FakeInventory()
        fixture.put(InventoryKind.PLAYER_KEY, 6, 8_380_005, quantity=2)
        invoker = RecordingInvoker(fixture)

        report = self.cleaner(fixture, invoker).remove_all(
            game_data_man=fixture.GAME_DATA_MAN,
            remove_item_function=0xABCDEF,
        )

        self.assertEqual(report.calls_made, 2)
        self.assertEqual(report.remaining, ())
        self.assertEqual(
            invoker.calls,
            [
                (0xABCDEF, fixture.PLAYER_EQUIP, 29, 1),
                (0xABCDEF, fixture.PLAYER_EQUIP, 29, 1),
            ],
        )

    def test_invalid_tail_index_fails_before_any_game_call(self) -> None:
        fixture = FakeInventory()
        fixture.put(InventoryKind.PLAYER, 1, 8_380_001)
        fixture.put(InventoryKind.PLAYER_KEY, 2, 8_380_002)
        fixture.memory.u32[fixture.PLAYER_EQUIP + 0x1C + 0x10] = 0xFFFFFFFF
        invoker = RecordingInvoker(fixture)

        with self.assertRaisesRegex(GameRuntimeError, "tail index"):
            self.cleaner(fixture, invoker).remove_all(
                game_data_man=fixture.GAME_DATA_MAN,
                remove_item_function=0x1234,
            )

        self.assertEqual(invoker.calls, [])

    def test_call_limit_is_preflighted_before_mutation(self) -> None:
        fixture = FakeInventory()
        fixture.put(InventoryKind.PLAYER_KEY, 3, 8_380_006, quantity=3)
        invoker = RecordingInvoker(fixture)

        with self.assertRaisesRegex(GameRuntimeError, "requires 3 calls"):
            self.cleaner(fixture, invoker).remove_all(
                game_data_man=fixture.GAME_DATA_MAN,
                remove_item_function=0x1234,
                max_calls=2,
            )

        self.assertEqual(invoker.calls, [])

    def test_no_observable_progress_fails_closed(self) -> None:
        fixture = FakeInventory()
        fixture.put(InventoryKind.PLAYER_KEY, 1, 8_380_006)
        invoker = RecordingInvoker(fixture, mutate=False)

        with self.assertRaisesRegex(GameRuntimeError, "no observable progress"):
            self.cleaner(fixture, invoker).remove_all(
                game_data_man=fixture.GAME_DATA_MAN,
                remove_item_function=0x1234,
            )

    def test_win64_stub_uses_three_argument_calling_convention(self) -> None:
        code = build_win64_call3_stub(
            0x1122334455667788,
            0x0102030405060708,
            0x1112131415161718,
            1,
        )

        self.assertIn(b"\x48\xB9\x08\x07\x06\x05\x04\x03\x02\x01", code)
        self.assertIn(b"\x48\x83\xEC\x28\xFF\xD0\x48\x83\xC4\x28\xC3", code)


if __name__ == "__main__":
    unittest.main()
