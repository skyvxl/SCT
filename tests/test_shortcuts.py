from __future__ import annotations

import unittest

from PySide6.QtGui import QKeySequence

from scmm.shortcuts import deserialize_key_sequence, serialize_key_sequence


class ShortcutSerializationTests(unittest.TestCase):
    def test_shortcut_is_serialized_as_numeric_qt_key_codes(self) -> None:
        sequence = QKeySequence("Ctrl+Shift+S")

        encoded = serialize_key_sequence(sequence)

        self.assertRegex(encoded, r"^-?\d+(,-?\d+)*$")
        self.assertNotIn("S", encoded)

    def test_numeric_shortcut_round_trips_to_native_display_sequence(self) -> None:
        original = QKeySequence("Ctrl+Alt+F9")

        restored = deserialize_key_sequence(serialize_key_sequence(original))

        self.assertEqual(restored, original)

    def test_empty_or_invalid_shortcut_decodes_as_empty(self) -> None:
        self.assertTrue(deserialize_key_sequence("").isEmpty())
        self.assertTrue(deserialize_key_sequence("Ctrl+S").isEmpty())


if __name__ == "__main__":
    unittest.main()
