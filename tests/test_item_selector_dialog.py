from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from sct.game.builds import EquipmentItem
from sct.items import ItemCatalog, ItemCategory
from sct.localization import TranslationService
from sct.ui.dialogs.item_selector import ItemSelectorDialog
from tests.qt_helpers import get_qapplication


class ItemSelectorDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()
        cls.translator = TranslationService()

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        with (root / "Weapons.csv").open(
                "w",
                encoding="utf-8-sig",
                newline="",
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["ID", "icon_id", "Upgrade", "en", "ru"],
            )
            writer.writeheader()
            writer.writerows(
                (
                    {
                        "ID": 1_000_000,
                        "icon_id": 10_000,
                        "Upgrade": "Smithing Stones",
                        "en": "Dagger",
                        "ru": "Кинжал",
                    },
                    {
                        "ID": 2_000_000,
                        "icon_id": 20_000,
                        "Upgrade": "Somber Smithing Stones",
                        "en": "Unique Sword",
                        "ru": "Уникальный меч",
                    },
                )
            )
        self.catalog = ItemCatalog(root, locale="ru")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_weapon_dialog_is_fixed_and_enables_controls_after_selection(self) -> None:
        dialog = ItemSelectorDialog(
            self.translator,
            self.catalog,
            ItemCategory.WEAPONS,
        )

        self.assertEqual(dialog.minimumSize(), dialog.maximumSize())
        self.assertFalse(dialog.accept_button.isEnabled())
        self.assertFalse(dialog.ash_button.isEnabled())

        dialog.select_row(0)

        self.assertTrue(dialog.accept_button.isEnabled())
        self.assertTrue(dialog.ash_button.isEnabled())
        self.assertEqual(dialog.upgrade_spin.maximum(), 25)
        dialog.upgrade_spin.setValue(20)
        self.assertEqual(
            dialog.selected_item(),
            EquipmentItem(1_000_000, upgrade_level=20),
        )

        dialog.select_row(1)
        self.assertEqual(dialog.upgrade_spin.maximum(), 10)

    def test_search_filters_by_localized_name(self) -> None:
        dialog = ItemSelectorDialog(
            self.translator,
            self.catalog,
            ItemCategory.WEAPONS,
        )

        dialog.search_edit.setText("уник")

        self.assertEqual(dialog.model.rowCount(), 1)
        self.assertEqual(dialog.model.item_at(0).id, 2_000_000)


if __name__ == "__main__":
    unittest.main()
