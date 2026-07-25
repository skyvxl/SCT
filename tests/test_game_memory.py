from __future__ import annotations

import unittest

from sct.game.memory import MemoryClient, ModuleInfo


class FakeMemoryBackend:
    def __init__(self) -> None:
        self.process_handle = 41
        self.base_address = 0x140000000
        self.data: dict[int, int] = {}
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def module(self, module_name: str) -> ModuleInfo:
        return ModuleInfo(module_name, 0x140000000, 0x2000)

    def read_bytes(self, address: int, size: int) -> bytes:
        return bytes(self.data.get(address + offset, 0) for offset in range(size))

    def write_bytes(self, address: int, data: bytes) -> None:
        for offset, value in enumerate(data):
            self.data[address + offset] = value

    def allocate(self, size: int) -> int:
        return 0x50000000

    def free(self, address: int) -> None:
        return None

    def start_thread(self, address: int) -> int:
        return 0


class MemoryClientTests(unittest.TestCase):
    def test_typed_reads_and_writes_use_little_endian_backend_bytes(self) -> None:
        backend = FakeMemoryBackend()
        memory = MemoryClient("eldenring.exe", backend_factory=lambda _name: backend)

        memory.write_u8(0x1000, 0xAB)
        memory.write_u16(0x1010, 0x1234)
        memory.write_u32(0x1020, 0x89ABCDEF)
        memory.write_i32(0x1030, -42)
        memory.write_u64(0x1040, 0x0123456789ABCDEF)

        self.assertEqual(memory.read_u8(0x1000), 0xAB)
        self.assertEqual(memory.read_u16(0x1010), 0x1234)
        self.assertEqual(memory.read_u32(0x1020), 0x89ABCDEF)
        self.assertEqual(memory.read_i32(0x1030), -42)
        self.assertEqual(memory.read_ptr(0x1040), 0x0123456789ABCDEF)
        self.assertEqual(memory.process_handle, 41)
        self.assertEqual(memory.base_address, 0x140000000)

        memory.close()

        self.assertTrue(backend.closed)


if __name__ == "__main__":
    unittest.main()
