from __future__ import annotations

import time
import unittest

from sct.backup_controller import BackupController
from tests.qt_helpers import get_qapplication


class FakeBackupManager:
    def __init__(self, screenshot: bytes | None) -> None:
        self.screenshot = screenshot

    def read_backup_screenshot(self, _name: str) -> bytes | None:
        return self.screenshot

    def shutdown(self) -> None:
        return None


class BackupControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_preview_read_emits_archive_name_and_png_without_busy_state(self) -> None:
        png = b"\x89PNG\r\n\x1a\npreview"
        controller = BackupController(FakeBackupManager(png))  # type: ignore[arg-type]
        loaded: list[tuple[str, bytes | None]] = []
        busy: list[bool] = []
        controller.screenshot_loaded.connect(
            lambda name, payload: loaded.append((name, payload))
        )
        controller.busy_changed.connect(busy.append)

        controller.load_screenshot("backup.zip")
        deadline = time.monotonic() + 1.0
        while not loaded and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)
        controller.shutdown()

        self.assertEqual(loaded, [("backup.zip", png)])
        self.assertEqual(busy, [])


if __name__ == "__main__":
    unittest.main()
