from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from sct.backups import BackupEntry
from sct.localization import TranslationService
from sct.settings import SettingsStore
from sct.ui.pages.backups import BackupsPage
from tests.qt_helpers import get_qapplication


class FakeBackupManager:
    def __init__(self, screenshot: bytes) -> None:
        self.screenshot = screenshot

    def read_backup_screenshot(self, _name: str) -> bytes:
        return self.screenshot

    def shutdown(self) -> None:
        return None


def make_png() -> bytes:
    image = QImage(16, 9, QImage.Format.Format_RGB32)
    image.fill(QColor(214, 65, 46))
    payload = QByteArray()
    buffer = QBuffer(payload)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(payload)


class BackupsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_selecting_backup_displays_its_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsStore(Path(directory) / "settings.ini")
            settings.ensure_exists()
            manager = FakeBackupManager(make_png())
            page = BackupsPage(
                TranslationService(),
                manager,  # type: ignore[arg-type]
                settings,
            )
            entry = BackupEntry(
                name="backup.zip",
                path=Path(directory) / "backup.zip",
                created_at=datetime(2026, 7, 26, 12, 0, 0),
                pinned=False,
            )

            page._populate_tables((entry,))
            page.regular_table.selectRow(0)
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                self.application.processEvents()
                if page.preview_label.pixmap() is not None:
                    break
                time.sleep(0.005)
            pixmap = page.preview_label.pixmap()
            page.shutdown()

            self.assertIsNotNone(pixmap)
            self.assertFalse(pixmap.isNull())


if __name__ == "__main__":
    unittest.main()
