from __future__ import annotations

import unittest

from sct.localization import TranslationService
from sct.ui.dialogs.runes import RuneDialog
from tests.qt_helpers import get_qapplication


class RuneDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()
        cls.translator = TranslationService()

    def test_dialog_is_fixed_and_exposes_the_game_rune_range(self) -> None:
        dialog = RuneDialog(self.translator, 123456)

        self.assertEqual(dialog.minimumSize(), dialog.maximumSize())
        self.assertEqual(dialog.value_spin.minimum(), 0)
        self.assertEqual(dialog.value_spin.maximum(), 999_999_999)
        self.assertEqual(dialog.rune_value(), 123456)

    def test_accept_and_cancel_buttons_close_with_standard_results(self) -> None:
        accepted = RuneDialog(self.translator, 1)
        rejected = RuneDialog(self.translator, 1)

        accepted.accept_button.click()
        rejected.cancel_button.click()

        self.assertEqual(accepted.result(), RuneDialog.DialogCode.Accepted)
        self.assertEqual(rejected.result(), RuneDialog.DialogCode.Rejected)


if __name__ == "__main__":
    unittest.main()
