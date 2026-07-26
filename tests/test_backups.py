from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

from sct.errors import LocalizedError


class BackupRepositoryTests(unittest.TestCase):
    def backup_types(self):
        try:
            module = importlib.import_module("sct.backups")
        except ModuleNotFoundError:
            self.fail("sct.backups has not been implemented")
        return module.SaveLocator, module.BackupRepository

    def test_selected_steam_id_resolves_exact_save_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            appdata = Path(directory)
            save = appdata / "EldenRing" / "76561198000000001" / "ER0000.co2"
            save.parent.mkdir(parents=True)
            save.write_bytes(b"save")
            SaveLocator, _repository_type = self.backup_types()

            resolved = SaveLocator(appdata).resolve(
                "ER0000.co2",
                "76561198000000001",
            )

            self.assertEqual(resolved, save)

    def test_unselected_account_is_automatic_only_when_unique(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            appdata = Path(directory)
            root = appdata / "EldenRing"
            first = root / "76561198000000001" / "ER0000.co2"
            second = root / "76561198000000002" / "ER0000.co2"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(b"first")
            SaveLocator, _repository_type = self.backup_types()
            locator = SaveLocator(appdata)

            self.assertEqual(locator.resolve("ER0000.co2"), first)
            second.write_bytes(b"second")
            with self.assertRaises(LocalizedError) as raised:
                locator.resolve("ER0000.co2")

            self.assertEqual(raised.exception.code, "backup_save_account_ambiguous")

    def test_create_uses_unique_zip_names_and_preserves_original_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / "ER0000.co2"
            save.write_bytes(b"snapshot")
            _locator_type, Repository = self.backup_types()
            repository = Repository(
                root / "backups",
                now=lambda: datetime(2026, 7, 26, 12, 34, 56),
            )

            first = repository.create(save)
            second = repository.create(save)

            self.assertEqual(first.name, "backup_20260726_123456.zip")
            self.assertEqual(second.name, "backup_20260726_123456_001.zip")
            with zipfile.ZipFile(first.path) as archive:
                self.assertEqual(archive.namelist(), ["ER0000.co2"])
                self.assertEqual(archive.read("ER0000.co2"), b"snapshot")

    def test_create_stores_optional_screenshot_and_archive_can_be_restored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / "ER0000.co2"
            save.write_bytes(b"snapshot")
            _locator_type, Repository = self.backup_types()
            repository = Repository(root / "backups")
            png = b"\x89PNG\r\n\x1a\nexample"

            entry = repository.create(save, screenshot=png)
            save.write_bytes(b"newer")
            repository.restore(entry.name, save)

            with zipfile.ZipFile(entry.path) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["ER0000.co2", "screenshot.png"],
                )
                self.assertEqual(archive.read("screenshot.png"), png)
            self.assertEqual(save.read_bytes(), b"snapshot")

    def test_read_screenshot_returns_stored_png_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / "ER0000.co2"
            save.write_bytes(b"snapshot")
            _locator_type, Repository = self.backup_types()
            repository = Repository(root / "backups")
            png = b"\x89PNG\r\n\x1a\npreview"
            entry = repository.create(save, screenshot=png)

            screenshot = repository.read_screenshot(entry.name)

            self.assertEqual(screenshot, png)

    def test_read_screenshot_returns_none_when_archive_has_no_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / "ER0000.co2"
            save.write_bytes(b"snapshot")
            _locator_type, Repository = self.backup_types()
            repository = Repository(root / "backups")
            entry = repository.create(save)

            screenshot = repository.read_screenshot(entry.name)

            self.assertIsNone(screenshot)

    def test_pin_rename_delete_and_malformed_index_are_reflected_by_listing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / "ER0000.co2"
            save.write_bytes(b"snapshot")
            _locator_type, Repository = self.backup_types()
            repository = Repository(
                root / "backups",
                now=lambda: datetime(2026, 7, 26, 12, 34, 56),
            )
            entry = repository.create(save)

            repository.set_pinned(entry.name, True)
            renamed = repository.rename(entry.name, "boss defeated")

            self.assertEqual(renamed.name, "boss defeated.zip")
            self.assertTrue(repository.list_entries()[0].pinned)
            repository.delete(renamed.name)
            self.assertEqual(repository.list_entries(), ())
            (root / "backups" / "pinned_backups.json").write_text(
                "{not json",
                encoding="utf-8",
            )
            self.assertEqual(repository.list_entries(), ())

    def test_restore_rejects_unsafe_or_wrong_archive_before_changing_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / "ER0000.co2"
            save.write_bytes(b"current")
            backup_directory = root / "backups"
            backup_directory.mkdir()
            unsafe = backup_directory / "unsafe.zip"
            with zipfile.ZipFile(unsafe, "w") as archive:
                archive.writestr("../ER0000.co2", b"malicious")
            _locator_type, Repository = self.backup_types()
            repository = Repository(backup_directory)

            with self.assertRaises(LocalizedError) as raised:
                repository.restore(unsafe.name, save)

            self.assertEqual(raised.exception.code, "backup_archive_invalid")
            self.assertEqual(save.read_bytes(), b"current")

    def test_restore_atomically_replaces_save_with_valid_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / "ER0000.co2"
            save.write_bytes(b"old snapshot")
            _locator_type, Repository = self.backup_types()
            repository = Repository(
                root / "backups",
                now=lambda: datetime(2026, 7, 26, 12, 34, 56),
            )
            entry = repository.create(save)
            save.write_bytes(b"current")

            restored = repository.restore(entry.name, save)

            self.assertEqual(restored, save)
            self.assertEqual(save.read_bytes(), b"old snapshot")

    def test_retention_removes_only_old_unpinned_archives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / "ER0000.co2"
            save.write_bytes(b"snapshot")
            _locator_type, Repository = self.backup_types()
            repository = Repository(
                root / "backups",
                now=lambda: datetime(2026, 7, 26, 12, 34, 56),
            )
            entries = [repository.create(save) for _ in range(4)]
            for index, entry in enumerate(entries):
                os.utime(entry.path, (100 + index, 100 + index))
            repository.set_pinned(entries[0].name, True)

            repository.enforce_limit(2)

            remaining = repository.list_entries()
            self.assertEqual(len(remaining), 3)
            self.assertIn(entries[0].name, {entry.name for entry in remaining})
            self.assertEqual(
                len([entry for entry in remaining if not entry.pinned]),
                2,
            )
            index = json.loads(
                (root / "backups" / "pinned_backups.json").read_text(encoding="utf-8")
            )
            self.assertEqual(index, [entries[0].name])


if __name__ == "__main__":
    unittest.main()
