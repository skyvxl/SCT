from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sct.logging_config import configure_logging, log_file_path
from sct.resource_loader import (
    load_optional_icon,
    load_stylesheet,
    optional_resource_path,
)
from tests.qt_helpers import get_qapplication


class ResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_optional_resource_returns_none_when_absent(self) -> None:
        with self.assertLogs("sct.resources", level="WARNING") as logs:
            self.assertIsNone(optional_resource_path("icons", "does-not-exist.png"))
        self.assertTrue(any("does-not-exist.png" in entry for entry in logs.output))

    def test_corrupt_icon_falls_back_to_none_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corrupt_icon = Path(directory) / "corrupt.ico"
            corrupt_icon.write_text("not an icon", encoding="utf-8")
            with patch("sct.resource_loader.optional_resource_path", return_value=corrupt_icon):
                with self.assertLogs("sct.resources", level="WARNING"):
                    self.assertIsNone(load_optional_icon("icons", "icon.ico"))

    def test_log_path_uses_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                expected = Path(directory) / "SeamlessCoopToolkit" / "logs" / "sct.log"
                self.assertEqual(log_file_path(), expected)

    def test_missing_stylesheet_falls_back_to_empty_qss(self) -> None:
        missing = Path(tempfile.gettempdir()) / "missing-sct-theme.qss"
        with patch("sct.resource_loader.resource_path", return_value=missing):
            with self.assertLogs("sct.resources", level="WARNING"):
                self.assertEqual(load_stylesheet(), "")

    def test_logging_uses_stderr_when_file_handler_cannot_open(self) -> None:
        logger = logging.getLogger("sct")
        original_handlers = logger.handlers[:]
        original_level = logger.level
        original_propagate = logger.propagate
        try:
            with patch("sct.logging_config.logging.FileHandler", side_effect=OSError):
                self.assertIsNone(configure_logging())
        finally:
            logger.handlers.clear()
            logger.handlers.extend(original_handlers)
            logger.setLevel(original_level)
            logger.propagate = original_propagate


if __name__ == "__main__":
    unittest.main()
