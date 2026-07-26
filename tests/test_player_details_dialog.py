from __future__ import annotations

import unittest
from types import MappingProxyType

from sct.game.builds import EquipmentItem, PlayerDetails
from sct.localization import TranslationService
from sct.ui.dialogs.player_details import PlayerDetailsDialog
from tests.qt_helpers import get_qapplication


def details(*, local: bool) -> PlayerDetails:
    stats = {
        "level": 11,
        "vigor": 20,
        "mind": 10,
        "endurance": 10,
        "strength": 10,
        "dexterity": 10,
        "intelligence": 10,
        "faith": 10,
        "arcane": 10,
    }
    if local:
        stats.update(
            {
                "runes": 100,
                "scadutree_blessing": 5,
                "revered_spirit_ash_blessing": 3,
            }
        )
    return PlayerDetails(
        player_num=0 if local else 1,
        is_local=local,
        name="Local" if local else "Phantom",
        steam_id=None if local else "7656",
        stats=MappingProxyType(stats),
        equipment=MappingProxyType(
            {
                "primary_right_wep": EquipmentItem(
                    1_000_000,
                    upgrade_level=10,
                ),
                "helmet": None,
            }
        ),
    )


class PlayerDetailsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()
        cls.translator = TranslationService()

    def test_local_dialog_is_fixed_editable_and_builds_current_state(self) -> None:
        dialog = PlayerDetailsDialog(self.translator, details(local=True))

        self.assertEqual(dialog.minimumSize(), dialog.maximumSize())
        self.assertTrue(dialog.editable)
        self.assertIsNotNone(dialog.apply_button)
        self.assertIsNotNone(dialog.load_button)
        self.assertIsNotNone(dialog.save_button)
        self.assertIn("quick_item_1", dialog.slot_widgets)

        dialog.stats_inputs["vigor"].setValue(21)
        build = dialog.current_build()

        self.assertEqual(build.stats["vigor"], 21)
        self.assertEqual(
            build.equipment["primary_right_wep"],
            EquipmentItem(1_000_000, upgrade_level=10),
        )
        self.assertNotIn("quick_item_1", build.equipment)

    def test_remote_dialog_is_read_only_but_can_save_observed_build(self) -> None:
        dialog = PlayerDetailsDialog(self.translator, details(local=False))

        self.assertEqual(dialog.minimumSize(), dialog.maximumSize())
        self.assertFalse(dialog.editable)
        self.assertIsNone(dialog.apply_button)
        self.assertIsNone(dialog.load_button)
        self.assertIsNotNone(dialog.save_button)
        self.assertNotIn("quick_item_1", dialog.slot_widgets)
        self.assertTrue(dialog.stats_inputs["vigor"].isReadOnly())
        self.assertEqual(dialog.current_build().source_name, "Phantom")

    def test_apply_button_is_visible_only_while_build_differs_from_opened_state(
            self,
    ) -> None:
        dialog = PlayerDetailsDialog(self.translator, details(local=True))
        original_vigor = dialog.stats_inputs["vigor"].value()

        self.assertTrue(dialog.apply_button.isHidden())

        dialog.stats_inputs["vigor"].setValue(original_vigor + 1)
        self.assertFalse(dialog.apply_button.isHidden())

        dialog.stats_inputs["vigor"].setValue(original_vigor)
        self.assertTrue(dialog.apply_button.isHidden())

    def test_successful_apply_promotes_current_build_to_clean_baseline(self) -> None:
        dialog = PlayerDetailsDialog(self.translator, details(local=True))
        original_vigor = dialog.stats_inputs["vigor"].value()
        dialog.stats_inputs["vigor"].setValue(original_vigor + 1)

        dialog.mark_applied()

        self.assertTrue(dialog.apply_button.isHidden())
        dialog.stats_inputs["vigor"].setValue(original_vigor)
        self.assertFalse(dialog.apply_button.isHidden())

    def test_apply_writes_manual_stats_when_equipment_only_load_is_enabled(
            self,
    ) -> None:
        dialog = PlayerDetailsDialog(self.translator, details(local=True))
        requested: list[tuple[object, bool]] = []
        dialog.apply_requested.connect(
            lambda build, equipment_only: requested.append(
                (build, equipment_only)
            )
        )
        dialog.stats_inputs["vigor"].setValue(21)

        dialog.apply_button.click()

        self.assertEqual(len(requested), 1)
        build, equipment_only = requested[0]
        self.assertEqual(build.stats["vigor"], 21)
        self.assertFalse(equipment_only)


if __name__ == "__main__":
    unittest.main()
