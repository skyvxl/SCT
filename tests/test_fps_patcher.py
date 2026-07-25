from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

from sct.errors import LocalizedError

ORIGINAL_SIGNATURE = bytes.fromhex(
    "C7 43 1C 89 88 88 3C EB 6D 89 73 18 EB C7 89 73 18"
)
PREFIX = b"MZ" + (b"\x00" * 16)
SUFFIX = b"\xFF" * 32
FPS_VALUE_OFFSET = len(PREFIX) + 3


def executable_bytes() -> bytes:
    return PREFIX + ORIGINAL_SIGNATURE + SUFFIX


def expected_patched_bytes(fps_bytes: bytes) -> bytes:
    expected = bytearray(executable_bytes())
    expected[FPS_VALUE_OFFSET: FPS_VALUE_OFFSET + 4] = fps_bytes
    return bytes(expected)


class EldenRingFpsPatcherTests(unittest.TestCase):
    def patcher_type(self):
        try:
            module = importlib.import_module("sct.fps_patcher")
        except ModuleNotFoundError:
            self.fail("sct.fps_patcher has not been implemented")
        return module.EldenRingFpsPatcher

    def test_first_patch_preserves_original_backup_and_replaces_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory)
            executable = game_directory / "eldenring.exe"
            backup = game_directory / "eldenring.exe.bak"
            original = executable_bytes()
            executable.write_bytes(original)

            result = self.patcher_type()(game_directory).patch(144)

            self.assertEqual(result.target_fps, 144)
            self.assertEqual(result.executable_path, executable)
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(
                executable.read_bytes(),
                expected_patched_bytes(bytes.fromhex("39 8E E3 3B")),
            )

    def test_repeat_patch_is_rebuilt_from_unchanged_original_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory)
            executable = game_directory / "eldenring.exe"
            backup = game_directory / "eldenring.exe.bak"
            original = executable_bytes()
            executable.write_bytes(original)
            patcher = self.patcher_type()(game_directory)
            patcher.patch(144)

            patcher.patch(240)

            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(
                executable.read_bytes(),
                expected_patched_bytes(bytes.fromhex("89 88 88 3B")),
            )

    def test_restore_replaces_executable_and_removes_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory)
            executable = game_directory / "eldenring.exe"
            backup = game_directory / "eldenring.exe.bak"
            original = executable_bytes()
            executable.write_bytes(original)
            patcher = self.patcher_type()(game_directory)
            patcher.patch(144)

            restored_path = patcher.restore()

            self.assertEqual(restored_path, executable)
            self.assertEqual(executable.read_bytes(), original)
            self.assertFalse(backup.exists())

    def test_invalid_target_does_not_create_backup_or_change_executable(self) -> None:
        for invalid_target in (0, -1, 1001):
            with self.subTest(target=invalid_target), tempfile.TemporaryDirectory() as directory:
                game_directory = Path(directory)
                executable = game_directory / "eldenring.exe"
                backup = game_directory / "eldenring.exe.bak"
                original = executable_bytes()
                executable.write_bytes(original)

                with self.assertRaises(LocalizedError) as raised:
                    self.patcher_type()(game_directory).patch(invalid_target)

                self.assertEqual(raised.exception.code, "fps_target_invalid")
                self.assertEqual(executable.read_bytes(), original)
                self.assertFalse(backup.exists())

    def test_missing_signature_does_not_create_backup_or_change_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory)
            executable = game_directory / "eldenring.exe"
            backup = game_directory / "eldenring.exe.bak"
            unsupported = b"MZ" + (b"\x00" * 64)
            executable.write_bytes(unsupported)

            with self.assertRaises(LocalizedError) as raised:
                self.patcher_type()(game_directory).patch(144)

            self.assertEqual(raised.exception.code, "fps_signature_missing")
            self.assertEqual(executable.read_bytes(), unsupported)
            self.assertFalse(backup.exists())

    def test_duplicate_signature_does_not_create_backup_or_change_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory)
            executable = game_directory / "eldenring.exe"
            backup = game_directory / "eldenring.exe.bak"
            ambiguous = executable_bytes() + ORIGINAL_SIGNATURE
            executable.write_bytes(ambiguous)

            with self.assertRaises(LocalizedError) as raised:
                self.patcher_type()(game_directory).patch(144)

            self.assertEqual(raised.exception.code, "fps_signature_ambiguous")
            self.assertEqual(executable.read_bytes(), ambiguous)
            self.assertFalse(backup.exists())

    def test_repeat_patch_refuses_current_executable_changed_outside_fps_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory)
            executable = game_directory / "eldenring.exe"
            backup = game_directory / "eldenring.exe.bak"
            original = executable_bytes()
            executable.write_bytes(original)
            patcher = self.patcher_type()(game_directory)
            patcher.patch(144)
            changed = bytearray(executable.read_bytes())
            changed[-1] = 0x7F
            executable.write_bytes(changed)

            with self.assertRaises(LocalizedError) as raised:
                patcher.patch(240)

            self.assertEqual(raised.exception.code, "fps_executable_changed")
            self.assertEqual(executable.read_bytes(), changed)
            self.assertEqual(backup.read_bytes(), original)

    def test_restore_refuses_current_executable_changed_outside_fps_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory)
            executable = game_directory / "eldenring.exe"
            backup = game_directory / "eldenring.exe.bak"
            original = executable_bytes()
            executable.write_bytes(original)
            patcher = self.patcher_type()(game_directory)
            patcher.patch(144)
            changed = bytearray(executable.read_bytes())
            changed[-1] = 0x7F
            executable.write_bytes(changed)

            with self.assertRaises(LocalizedError) as raised:
                patcher.restore()

            self.assertEqual(raised.exception.code, "fps_executable_changed")
            self.assertEqual(executable.read_bytes(), changed)
            self.assertEqual(backup.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
