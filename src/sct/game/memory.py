from __future__ import annotations

import contextlib
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sct.game.errors import GameModuleNotFound, GameProcessNotFound, GameRuntimeError


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    name: str
    base: int
    size: int


class MemoryBackendProtocol(Protocol):
    process_handle: int
    base_address: int

    def close(self) -> None: ...

    def module(self, module_name: str) -> ModuleInfo: ...

    def read_bytes(self, address: int, size: int) -> bytes: ...

    def write_bytes(self, address: int, data: bytes) -> None: ...

    def allocate(self, size: int) -> int: ...

    def free(self, address: int) -> None: ...

    def start_thread(self, address: int) -> int: ...


class MemoryClientProtocol(Protocol):
    process_handle: int
    base_address: int

    def close(self) -> None: ...

    def module(self, module_name: str) -> ModuleInfo: ...

    def read_bytes(self, address: int, size: int) -> bytes: ...

    def write_bytes(self, address: int, data: bytes) -> None: ...

    def read_u8(self, address: int) -> int: ...

    def write_u8(self, address: int, value: int) -> None: ...

    def read_u16(self, address: int) -> int: ...

    def read_u32(self, address: int) -> int: ...

    def write_u32(self, address: int, value: int) -> None: ...

    def read_i32(self, address: int) -> int: ...

    def write_i32(self, address: int, value: int) -> None: ...

    def read_u64(self, address: int) -> int: ...

    def write_u64(self, address: int, value: int) -> None: ...

    def read_ptr(self, address: int) -> int: ...

    def allocate(self, size: int) -> int: ...

    def free(self, address: int) -> None: ...

    def start_thread(self, address: int) -> int: ...


class _PymemBackend:
    def __init__(self, process_name: str) -> None:
        try:
            import pymem
        except ImportError as error:
            raise GameRuntimeError("pymem is required for game memory access") from error
        try:
            self._pymem = pymem.Pymem(process_name)
        except Exception as error:
            raise GameProcessNotFound(process_name) from error
        self.process_handle = int(self._pymem.process_handle)
        self.base_address = int(self._pymem.base_address)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._pymem.close_process()

    def module(self, module_name: str) -> ModuleInfo:
        import pymem.process

        module = pymem.process.module_from_name(self.process_handle, module_name)
        if module is None:
            raise GameModuleNotFound(module_name)
        return ModuleInfo(module_name, int(module.lpBaseOfDll), int(module.SizeOfImage))

    def read_bytes(self, address: int, size: int) -> bytes:
        return self._pymem.read_bytes(address, size)

    def write_bytes(self, address: int, data: bytes) -> None:
        self._pymem.write_bytes(address, data, len(data))

    def allocate(self, size: int) -> int:
        return int(self._pymem.allocate(size))

    def free(self, address: int) -> None:
        self._pymem.free(address)

    def start_thread(self, address: int) -> int:
        import ctypes

        handle = self._pymem.start_thread(address)
        ctypes.windll.kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        ctypes.windll.kernel32.CloseHandle(handle)
        return 0


BackendFactory = Callable[[str], MemoryBackendProtocol]


class MemoryClient:
    def __init__(
        self,
        process_name: str,
        *,
        backend_factory: BackendFactory = _PymemBackend,
    ) -> None:
        self.process_name = process_name
        self._backend = backend_factory(process_name)
        self.process_handle = self._backend.process_handle
        self.base_address = self._backend.base_address

    def close(self) -> None:
        self._backend.close()

    def module(self, module_name: str) -> ModuleInfo:
        return self._backend.module(module_name)

    def read_bytes(self, address: int, size: int) -> bytes:
        return self._backend.read_bytes(address, size)

    def write_bytes(self, address: int, data: bytes) -> None:
        self._backend.write_bytes(address, data)

    def read_u8(self, address: int) -> int:
        data = self.read_bytes(address, 1)
        return data[0] if data else 0

    def write_u8(self, address: int, value: int) -> None:
        self.write_bytes(address, bytes([value & 0xFF]))

    def read_u16(self, address: int) -> int:
        return struct.unpack("<H", self.read_bytes(address, 2))[0]

    def write_u16(self, address: int, value: int) -> None:
        self.write_bytes(address, struct.pack("<H", value))

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.read_bytes(address, 4))[0]

    def write_u32(self, address: int, value: int) -> None:
        self.write_bytes(address, struct.pack("<I", value))

    def read_i32(self, address: int) -> int:
        return struct.unpack("<i", self.read_bytes(address, 4))[0]

    def write_i32(self, address: int, value: int) -> None:
        self.write_bytes(address, struct.pack("<i", value))

    def read_u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read_bytes(address, 8))[0]

    def write_u64(self, address: int, value: int) -> None:
        self.write_bytes(address, struct.pack("<Q", value))

    def read_ptr(self, address: int) -> int:
        return self.read_u64(address)

    def allocate(self, size: int) -> int:
        return self._backend.allocate(size)

    def free(self, address: int) -> None:
        self._backend.free(address)

    def start_thread(self, address: int) -> int:
        return self._backend.start_thread(address)
