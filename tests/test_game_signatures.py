from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.game.errors import PatternNotFound, PatternNotUnique
from sct.game.memory import ModuleInfo
from sct.game.signatures import AOBScanner, SymbolResolver, compile_aob_regex


class FakeMemory:
    def __init__(self, data: bytes, *, base: int = 0x1000) -> None:
        self.data = data
        self.base = base

    def module(self, module_name: str) -> ModuleInfo:
        return ModuleInfo(module_name, self.base, len(self.data))

    def read_bytes(self, address: int, size: int) -> bytes:
        start = address - self.base
        return self.data[start: start + size]

    def read_i32(self, address: int) -> int:
        return int.from_bytes(self.read_bytes(address, 4), "little", signed=True)


class SignatureTests(unittest.TestCase):
    def test_aob_regex_matches_wildcards(self) -> None:
        regex = compile_aob_regex("48 8B ?? 89")

        self.assertIsNotNone(regex.search(bytes.fromhex("90 48 8B FF 89 90")))

    def test_unique_scan_reports_missing_and_duplicate_patterns(self) -> None:
        missing_memory = FakeMemory(bytes.fromhex("48 8B 01 90"))
        scanner = AOBScanner(missing_memory)

        with self.assertRaises(PatternNotFound):
            scanner.scan_module_unique(
                missing_memory.module("eldenring.exe"),
                "AA BB",
                symbol="Missing",
            )

        duplicate_memory = FakeMemory(bytes.fromhex("AA BB 00 AA BB"))
        scanner = AOBScanner(duplicate_memory)
        with self.assertRaises(PatternNotUnique):
            scanner.scan_module_unique(
                duplicate_memory.module("eldenring.exe"),
                "AA BB",
                symbol="Duplicate",
            )

    def test_resolver_calculates_rip_relative_target_and_caches_it(self) -> None:
        base = 0x1000
        target = 0x1800
        instruction = base + 2
        rip_base = instruction + 7
        relative = target - rip_base
        data = (
                b"\x90\x90"
                + b"\x48\x8B\x05"
                + relative.to_bytes(4, "little", signed=True)
                + b"\x90\x90"
        )
        memory = FakeMemory(data, base=base)

        with tempfile.TemporaryDirectory() as directory:
            signatures = Path(directory) / "signatures.toml"
            signatures.write_text(
                '[symbols.WorldChrManPtrAddr]\n'
                'pattern = "48 8B 05 ?? ?? ?? ??"\n'
                'offset = "0x0"\n'
                'kind = "rip_relative"\n'
                'module = "eldenring.exe"\n',
                encoding="utf-8",
            )
            resolver = SymbolResolver(
                memory,
                signatures,
                default_module="eldenring.exe",
            )

            first = resolver.resolve("WorldChrManPtrAddr")
            memory.data = b""
            second = resolver.resolve("WorldChrManPtrAddr")

        self.assertEqual(first.address, target)
        self.assertEqual(second.address, target)


if __name__ == "__main__":
    unittest.main()
