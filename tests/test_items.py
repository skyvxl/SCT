from __future__ import annotations

import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from sct.items import (
    ItemCatalog,
    ItemCategory,
    ItemDataNotFound,
    resolve_items_directory,
)


def write_catalog(
    root: Path,
    filename: str,
    rows: list[dict[str, object]],
) -> None:
    fieldnames = ["ID", "icon_id", "Upgrade", "en", "ru"]
    with (root / filename).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class ItemDirectoryTests(unittest.TestCase):
    def test_explicit_directory_has_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            explicit = root / "explicit"
            executable = root / "app"
            development = root / "project"
            explicit.mkdir()
            (executable / "items").mkdir(parents=True)
            (development / "data" / "items").mkdir(parents=True)

            resolved = resolve_items_directory(
                explicit=explicit,
                executable_dir=executable,
                project_root=development,
            )

            self.assertEqual(resolved, explicit.resolve())

    def test_executable_items_precede_development_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "app"
            development = root / "project"
            packaged = executable / "items"
            packaged.mkdir(parents=True)
            (development / "data" / "items").mkdir(parents=True)

            resolved = resolve_items_directory(
                executable_dir=executable,
                project_root=development,
            )

            self.assertEqual(resolved, packaged.resolve())

    def test_missing_item_data_reports_checked_locations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            with self.assertRaises(ItemDataNotFound) as raised:
                resolve_items_directory(
                    executable_dir=root / "app",
                    project_root=root / "project",
                )

            self.assertIn(str(root / "app" / "items"), str(raised.exception))
            self.assertIn(str(root / "project" / "data" / "items"), str(raised.exception))


class ItemCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        write_catalog(
            self.root,
            "Weapons.csv",
            [
                {
                    "ID": 1_000_000,
                    "icon_id": 10_000,
                    "Upgrade": "Smithing Stones",
                    "en": "Dagger",
                    "ru": "Кинжал",
                },
                {
                    "ID": 1_100_000,
                    "icon_id": 10_010,
                    "Upgrade": "Somber Smithing Stones",
                    "en": "Black Knife",
                    "ru": "Черный нож",
                },
            ],
        )
        write_catalog(
            self.root,
            "Talismans.csv",
            [
                {
                    "ID": 20_000,
                    "icon_id": 20_001,
                    "Upgrade": "",
                    "en": "Crimson Amber Medallion",
                    "ru": "",
                }
            ],
        )
        write_catalog(
            self.root,
            "QuickItems.csv",
            [
                {
                    "ID": 1_000,
                    "icon_id": "00015",
                    "Upgrade": "",
                    "en": "Flask of Crimson Tears",
                    "ru": "Фляга багровых слёз",
                }
            ],
        )
        with zipfile.ZipFile(self.root / "images.zip", "w") as archive:
            archive.writestr("icons/MENU_Knowledge_10000.webp", b"dagger-image")
            archive.writestr("icons/MENU_Knowledge_20001.webp", b"talisman-image")
            archive.writestr("icons/MENU_Knowledge_15.webp", b"flask-image")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_localized_lookup_search_and_english_fallback(self) -> None:
        catalog = ItemCatalog(self.root, locale="ru")

        dagger = catalog.get(ItemCategory.WEAPONS, 1_000_000)
        fallback = catalog.get(ItemCategory.TALISMANS, 20_000)

        self.assertIsNotNone(dagger)
        self.assertEqual(dagger.name, "Кинжал")
        self.assertEqual(fallback.name, "Crimson Amber Medallion")
        self.assertEqual(
            [item.id for item in catalog.search(ItemCategory.WEAPONS, "кинж")],
            [1_000_000],
        )
        self.assertEqual(
            [item.id for item in catalog.search(ItemCategory.WEAPONS, "1100000")],
            [1_100_000],
        )

    def test_weapon_upgrade_limit_comes_from_upgrade_kind(self) -> None:
        catalog = ItemCatalog(self.root, locale="en")

        ordinary = catalog.get(ItemCategory.WEAPONS, 1_000_000)
        somber = catalog.get(ItemCategory.WEAPONS, 1_100_000)

        self.assertEqual(ordinary.max_upgrade, 25)
        self.assertEqual(somber.max_upgrade, 10)

    def test_icon_bytes_are_resolved_by_icon_id_and_missing_icons_are_optional(self) -> None:
        catalog = ItemCatalog(self.root, locale="en")
        dagger = catalog.get(ItemCategory.WEAPONS, 1_000_000)
        black_knife = catalog.get(ItemCategory.WEAPONS, 1_100_000)

        self.assertEqual(catalog.icon_bytes(dagger), b"dagger-image")
        self.assertIsNone(catalog.icon_bytes(black_knife))

    def test_leading_zero_icon_id_is_parsed_as_decimal(self) -> None:
        catalog = ItemCatalog(self.root, locale="ru")

        flask = catalog.get(ItemCategory.QUICK_ITEMS, 1_000)

        self.assertIsNotNone(flask)
        self.assertEqual(flask.icon_id, 15)
        self.assertEqual(catalog.icon_bytes(flask), b"flask-image")

    def test_missing_catalog_is_loaded_as_an_empty_category(self) -> None:
        catalog = ItemCatalog(self.root, locale="en")

        self.assertEqual(catalog.items(ItemCategory.SPELLS), ())
        self.assertEqual(catalog.search(ItemCategory.SPELLS, "anything"), ())


if __name__ == "__main__":
    unittest.main()
