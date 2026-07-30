from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sct.localization import TranslationCatalogError, TranslationService
from sct.resource_loader import resource_path


def leaf_keys(value: object, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        return {
            key
            for name, child in value.items()
            for key in leaf_keys(child, f"{prefix}.{name}" if prefix else name)
        }
    return {prefix}


class TranslationServiceTests(unittest.TestCase):
    def test_loads_packaged_russian_catalog(self) -> None:
        service = TranslationService()
        self.assertEqual(service.locale, "ru")
        self.assertEqual(service.translate("app.title"), "Seamless Co-op Toolkit")
        self.assertEqual(service.translate("nav.home"), "Главная")
        self.assertEqual(service.translate("nav.seamless"), "Seamless Co-op")
        self.assertEqual(service.translate("nav.backups"), "Резервные копии")
        self.assertEqual(service.available_locales(), ("en", "ru"))

    def test_packaged_english_catalog_matches_russian_keys(self) -> None:
        root = resource_path("i18n")
        english_path = root / "en.json"
        self.assertTrue(english_path.is_file(), "Packaged English catalog is missing")
        russian = json.loads((root / "ru.json").read_text(encoding="utf-8"))
        english = json.loads(english_path.read_text(encoding="utf-8"))

        self.assertEqual(leaf_keys(english), leaf_keys(russian))

        service = TranslationService(locale="en")
        self.assertEqual(service.translate("nav.home"), "Home")
        self.assertEqual(service.translate("settings.language.english"), "English")
        self.assertEqual(
            service.translate("backups.restore_success_message", name="backup.zip"),
            'Backup "backup.zip" was restored successfully.',
        )

    def test_formats_positional_and_named_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ru.json").write_text(
                json.dumps(
                    {
                        "positional": "Версия: {}",
                        "named": "Разработка: {author}",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            service = TranslationService(root)

        self.assertEqual(service.translate("positional", "0.1"), "Версия: 0.1")
        self.assertEqual(service.translate("named", author="skyvxl"), "Разработка: skyvxl")

    def test_missing_key_returns_key_and_logs_warning(self) -> None:
        service = TranslationService()
        with self.assertLogs("sct.localization", level="WARNING") as logs:
            value = service.translate("missing.translation.key")

        self.assertEqual(value, "missing.translation.key")
        self.assertTrue(any("missing.translation.key" in entry for entry in logs.output))

    def test_malformed_catalog_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ru.json").write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(TranslationCatalogError, "ru.json"):
                TranslationService(root)

    def test_non_string_nested_catalog_leaf_raises_with_key_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ru.json").write_text('{"nav": {"home": 7}}', encoding="utf-8")
            with self.assertRaisesRegex(TranslationCatalogError, r"nav\.home.*ru\.json"):
                TranslationService(root)

    def test_malformed_format_field_raises_with_key_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ru.json").write_text('{"nav": {"home": "{value!z}"}}', encoding="utf-8")
            with self.assertRaisesRegex(TranslationCatalogError, r"nav\.home.*ru\.json"):
                TranslationService(root)

    def test_failed_locale_change_keeps_catalog_and_signal_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ru.json").write_text('{"label": "Русский"}', encoding="utf-8")
            (root / "en.json").write_text('{"nested": {"bad": 7}}', encoding="utf-8")
            service = TranslationService(root)
            emitted: list[str] = []
            service.language_changed.connect(emitted.append)

            with self.assertRaisesRegex(TranslationCatalogError, r"nested\.bad.*en\.json"):
                service.set_locale("en")

        self.assertEqual(service.locale, "ru")
        self.assertEqual(service.translate("label"), "Русский")
        self.assertEqual(emitted, [])

    def test_locale_change_loads_an_added_catalog_and_emits_signal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ru.json").write_text('{"label": "Русский"}', encoding="utf-8")
            (root / "en.json").write_text('{"label": "English"}', encoding="utf-8")
            service = TranslationService(root)
            emitted: list[str] = []
            service.language_changed.connect(emitted.append)
            service.set_locale("en")

        self.assertEqual(service.translate("label"), "English")
        self.assertEqual(emitted, ["en"])


if __name__ == "__main__":
    unittest.main()
