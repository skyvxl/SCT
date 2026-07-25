from __future__ import annotations

import unittest

from PySide6.QtWidgets import QPushButton

from sct.game.cheats import Cheat
from sct.localization import TranslationService
from sct.ui.dialogs.cheats import CheatDialog
from tests.qt_helpers import get_qapplication


class CheatDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()
        cls.translator = TranslationService()

    def test_dialog_is_fixed_and_contains_seven_cheats_plus_removal_action(self) -> None:
        removals: list[bool] = []
        dialog = CheatDialog(
            self.translator,
            frozenset({Cheat.NO_DEATH}),
            lambda _cheat, _enabled: None,
            on_remove_items=lambda: removals.append(True),
        )

        self.assertEqual(dialog.minimumSize(), dialog.maximumSize())
        self.assertEqual(set(dialog.cheat_buttons), set(Cheat))
        self.assertEqual(len(dialog.cheat_buttons), 7)
        self.assertTrue(dialog.cheat_buttons[Cheat.NO_DEATH].isChecked())
        remove = dialog.findChild(QPushButton, "removeCoopItemsButton")
        self.assertIsNotNone(remove)
        remove.click()
        self.assertEqual(removals, [True])

    def test_toggle_calls_backend_callback_with_cheat_and_new_state(self) -> None:
        changes: list[tuple[Cheat, bool]] = []
        dialog = CheatDialog(
            self.translator,
            frozenset(),
            lambda cheat, enabled: changes.append((cheat, enabled)),
        )

        dialog.cheat_buttons[Cheat.INFINITE_FP].click()

        self.assertEqual(changes, [(Cheat.INFINITE_FP, True)])


if __name__ == "__main__":
    unittest.main()
