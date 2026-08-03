from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_items import (
    REQUIRED_ITEM_FILES,
    ItemBuildError,
    build_items,
    create_items_zip,
    validate_items,
)


class ItemBuildTests(unittest.TestCase):
    def test_validate_items_reports_all_missing_release_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            items = Path(temporary_directory)
            (items / "Weapons.csv").write_text("ID,en\n", encoding="utf-8")

            with self.assertRaises(ItemBuildError) as raised:
                validate_items(items)

        message = str(raised.exception)
        self.assertNotIn("Weapons.csv", message)
        self.assertIn("Ammunitions.csv", message)
        self.assertIn("images.zip", message)

    def test_items_zip_has_extractable_items_root_and_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            for filename in REQUIRED_ITEM_FILES:
                (source / filename).write_bytes(filename.encode())
            (source / ".gitignore").write_text("*\n", encoding="utf-8")
            destination = root / "items.zip"

            archive = create_items_zip(source, destination)

            self.assertEqual(archive, destination)
            with zipfile.ZipFile(archive) as items_zip:
                self.assertEqual(
                    items_zip.namelist(),
                    [f"items/{filename}" for filename in sorted(REQUIRED_ITEM_FILES)],
                )

    def test_build_items_creates_dist_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "data" / "items"
            source.mkdir(parents=True)
            for filename in REQUIRED_ITEM_FILES:
                (source / filename).write_bytes(filename.encode())

            archive = build_items(root)

            self.assertEqual(archive, root / "dist" / "items.zip")
            self.assertTrue(archive.is_file())


if __name__ == "__main__":
    unittest.main()
