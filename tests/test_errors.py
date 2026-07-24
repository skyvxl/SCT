from __future__ import annotations

import unittest

from sct.errors import LocalizedError, localized_error_message
from sct.localization import TranslationService


class LocalizedErrorTests(unittest.TestCase):
    def test_expected_error_uses_translation_key_without_exposing_debug_message(self) -> None:
        translator = TranslationService()
        error = LocalizedError(
            "download_size_mismatch",
            "Downloaded size mismatch: expected 10, got 7",
            params={"expected": 10, "actual": 7},
        )

        message = localized_error_message(translator, error)

        self.assertEqual(
            message,
            "Размер загруженного архива не совпадает: ожидалось 10, получено 7.",
        )
        self.assertNotIn("Downloaded size mismatch", message)

    def test_unexpected_error_uses_localized_fallback_without_raw_system_text(self) -> None:
        translator = TranslationService()

        message = localized_error_message(
            translator,
            OSError("The system cannot find the file specified"),
        )

        self.assertEqual(message, "Произошла непредвиденная ошибка.")
        self.assertNotIn("system", message.casefold())


if __name__ == "__main__":
    unittest.main()
