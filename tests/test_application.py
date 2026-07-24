from __future__ import annotations

import unittest
from unittest.mock import patch

from sct.application import main
from sct.localization import TranslationCatalogError
from tests.qt_helpers import get_qapplication


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    @patch("sct.application.configure_logging")
    @patch("sct.application.QMessageBox.critical")
    @patch(
        "sct.application.TranslationService",
        side_effect=TranslationCatalogError("broken ru.json"),
    )
    def test_catalog_failure_returns_nonzero_before_event_loop(
        self,
        _translator: object,
        critical: object,
        _logging: object,
    ) -> None:
        with self.assertLogs("sct.application", level="ERROR") as logs:
            result = main([])
        self.assertEqual(result, 1)
        critical.assert_called_once()
        self.assertTrue(any("Unable to initialize localization" in entry for entry in logs.output))

    @patch("sct.application.configure_logging")
    @patch("sct.application.QMessageBox.critical")
    @patch("sct.application.SettingsStore")
    @patch("sct.application.build_main_window", side_effect=RuntimeError("broken window"))
    def test_unhandled_startup_failure_is_reported_without_event_loop(
        self,
        _window: object,
        _settings_store: object,
        critical: object,
        _logging: object,
    ) -> None:
        with self.assertLogs("sct.application", level="ERROR") as logs:
            result = main([])
        self.assertEqual(result, 1)
        critical.assert_called_once()
        self.assertTrue(any("Unable to build application window" in entry for entry in logs.output))


if __name__ == "__main__":
    unittest.main()
