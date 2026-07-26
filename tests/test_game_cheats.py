from __future__ import annotations

import unittest
from types import SimpleNamespace

from sct.game.cheats import Cheat, EldenRingCheatRuntime
from sct.game.errors import GameProcessNotFound
from sct.game.memory import ModuleInfo


class FakeMemory:
    def __init__(self) -> None:
        self.data: dict[int, int] = {}
        self.closed = False

    def seed(self, address: int, value: int, size: int) -> None:
        for offset, byte in enumerate(value.to_bytes(size, "little")):
            self.data[address + offset] = byte

    def seed_ptr(self, address: int, value: int) -> None:
        self.seed(address, value, 8)

    def read_bytes(self, address: int, size: int) -> bytes:
        return bytes(self.data.get(address + offset, 0) for offset in range(size))

    def write_bytes(self, address: int, data: bytes) -> None:
        for offset, byte in enumerate(data):
            self.data[address + offset] = byte

    def read_ptr(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 8), "little")

    def read_u8(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 1), "little")

    def write_u8(self, address: int, value: int) -> None:
        self.write_bytes(address, bytes([value & 0xFF]))

    def module(self, module_name: str) -> ModuleInfo:
        return ModuleInfo(module_name, 0x9000, 0x100)

    def close(self) -> None:
        self.closed = True


class FakeResolver:
    def resolve(self, symbol: str) -> SimpleNamespace:
        self.last_symbol = symbol
        return SimpleNamespace(address=0x100)


class FakeScanner:
    def __init__(self, address: int = 0x9000) -> None:
        self.address = address
        self.patterns: list[str] = []

    def scan_module_unique(
            self,
            module: ModuleInfo,
            pattern: str,
            *,
            symbol: str,
    ) -> int:
        self.patterns.append(pattern)
        return self.address


def seed_player_flags(memory: FakeMemory) -> None:
    memory.seed_ptr(0x100, 0x1000)
    memory.seed_ptr(0x1000 + 0x10EF8, 0x2000)
    memory.seed_ptr(0x2000, 0x3000)
    memory.seed_ptr(0x3000 + 0x190, 0x4000)
    memory.seed_ptr(0x4000, 0x5000)


class CheatRuntimeTests(unittest.TestCase):
    def test_public_cheats_match_the_seven_requested_actions(self) -> None:
        self.assertEqual(
            set(Cheat),
            {
                Cheat.NO_WEIGHT,
                Cheat.NO_DEATH,
                Cheat.NO_DAMAGE,
                Cheat.NO_HIT,
                Cheat.INFINITE_STAMINA,
                Cheat.INFINITE_FP,
                Cheat.INFINITE_CONSUMABLES,
            },
        )
        self.assertNotIn("NoArrowConsume", {cheat.value for cheat in Cheat})

    def test_flag_cheat_is_applied_immediately_and_can_be_disabled(self) -> None:
        memory = FakeMemory()
        seed_player_flags(memory)
        runtime = EldenRingCheatRuntime(
            lambda: memory,
            lambda _memory: FakeResolver(),
            start_background=False,
        )
        flag_address = 0x5000 + 0x19B

        runtime.set_enabled(Cheat.NO_DEATH, True)

        self.assertEqual(memory.read_u8(flag_address) & 0b1, 0b1)
        self.assertEqual(runtime.enabled_cheats(), frozenset({Cheat.NO_DEATH}))

        runtime.set_enabled(Cheat.NO_DEATH, False)

        self.assertEqual(memory.read_u8(flag_address) & 0b1, 0)
        self.assertEqual(runtime.enabled_cheats(), frozenset())

    def test_no_weight_patch_is_restored(self) -> None:
        memory = FakeMemory()
        memory.write_bytes(0x9000, b"\xFF\xC3\x83\xFB\x05")
        runtime = EldenRingCheatRuntime(
            lambda: memory,
            lambda _memory: FakeResolver(),
            scanner_factory=lambda _memory: FakeScanner(),
            start_background=False,
        )

        runtime.set_enabled(Cheat.NO_WEIGHT, True)
        self.assertEqual(memory.read_bytes(0x9000, 5), b"\x0F\x57\xF6\x90\x90")

        runtime.set_enabled(Cheat.NO_WEIGHT, False)
        self.assertEqual(memory.read_bytes(0x9000, 5), b"\xFF\xC3\x83\xFB\x05")

    def test_process_exit_clears_enabled_runtime_state(self) -> None:
        state = {"running": True}
        memory = FakeMemory()
        seed_player_flags(memory)

        def memory_factory() -> FakeMemory:
            if not state["running"]:
                raise GameProcessNotFound("eldenring.exe")
            return memory

        runtime = EldenRingCheatRuntime(
            memory_factory,
            lambda _memory: FakeResolver(),
            start_background=False,
        )
        runtime.set_enabled(Cheat.NO_DAMAGE, True)
        state["running"] = False

        runtime.enforce_once()

        self.assertEqual(runtime.enabled_cheats(), frozenset())


if __name__ == "__main__":
    unittest.main()
