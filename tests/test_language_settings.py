from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sct.localization import TranslationService
from sct.settings import SettingsStore
from sct.ui.pages.settings import SettingsPage
from tests.qt_helpers import get_qapplication


class FakeSteamService:
    def is_running(self) -> bool:
        return False

    def profiles(self, _executable: str) -> tuple[object, ...]:
        return ()


class LanguageSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_selecting_english_retranslates_and_persists_locale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.ini")
            store.ensure_exists()
            store.update(preferred_language="ru")
            translator = TranslationService()
            page = SettingsPage(translator, store, FakeSteamService())
            page.steam_status_timer.stop()

            english_index = page.language_combo.findData("en")
            self.assertGreaterEqual(english_index, 0)
            page.language_combo.setCurrentIndex(english_index)
            self.application.processEvents()

            self.assertEqual(translator.locale, "en")
            self.assertEqual(store.load().preferred_language, "en")
            self.assertEqual(page.language_combo.currentText(), "English")


if __name__ == "__main__":
    unittest.main()
