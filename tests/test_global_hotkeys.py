from __future__ import annotations

import unittest

from PySide6.QtGui import QKeySequence

from sct.global_hotkeys import key_sequence_to_windows_hotkey


class GlobalHotkeyTests(unittest.TestCase):
    def test_converts_letters_and_modifiers_to_windows_values(self) -> None:
        modifiers, virtual_key = key_sequence_to_windows_hotkey(
            QKeySequence("Ctrl+Shift+B")
        )

        self.assertEqual(modifiers, 0x0002 | 0x0004)
        self.assertEqual(virtual_key, ord("B"))

    def test_converts_function_and_navigation_keys(self) -> None:
        self.assertEqual(
            key_sequence_to_windows_hotkey(QKeySequence("Alt+F8")),
            (0x0001, 0x77),
        )
        self.assertEqual(
            key_sequence_to_windows_hotkey(QKeySequence("Ctrl+Home")),
            (0x0002, 0x24),
        )

    def test_rejects_multi_chord_shortcuts(self) -> None:
        with self.assertRaises(ValueError):
            key_sequence_to_windows_hotkey(QKeySequence("Ctrl+K, Ctrl+B"))


if __name__ == "__main__":
    unittest.main()
