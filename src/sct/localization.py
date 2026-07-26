from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Formatter
from typing import Any

from PySide6.QtCore import QObject, Signal

from sct.resource_loader import resource_path

LOGGER = logging.getLogger("sct.localization")


class TranslationCatalogError(RuntimeError):
    pass


def validate_catalog(catalog: object, path: Path, key_prefix: str = "") -> None:
    if isinstance(catalog, dict):
        for key, value in catalog.items():
            if not isinstance(key, str) or not key:
                raise TranslationCatalogError(
                    f"Invalid translation key in {path}: keys must be non-empty text"
                )
            dotted_key = f"{key_prefix}.{key}" if key_prefix else key
            validate_catalog(value, path, dotted_key)
        return
    if not isinstance(catalog, str):
        raise TranslationCatalogError(
            f"Invalid translation value for '{key_prefix}' in {path}: expected text"
        )
    try:
        fields = tuple(Formatter().parse(catalog))
    except ValueError as error:
        raise TranslationCatalogError(
            f"Invalid translation format for '{key_prefix}' in {path}: {error}"
        ) from error
    for _literal, _field_name, _format_spec, conversion in fields:
        if conversion not in (None, "s", "r", "a"):
            raise TranslationCatalogError(
                f"Invalid translation format for '{key_prefix}' in {path}: "
                f"unsupported conversion '!{conversion}'"
            )


class TranslationService(QObject):
    language_changed = Signal(str)

    def __init__(
            self,
            catalog_root: Path | None = None,
            locale: str = "ru",
            parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._catalog_root = catalog_root or resource_path("i18n")
        self._locale = ""
        self._catalog: dict[str, Any] = {}
        self.set_locale(locale, emit=False)

    @property
    def locale(self) -> str:
        return self._locale

    def available_locales(self) -> tuple[str, ...]:
        return tuple(sorted(path.stem for path in self._catalog_root.glob("*.json")))

    def set_locale(self, locale: str, *, emit: bool = True) -> None:
        path = self._catalog_root / f"{locale}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TranslationCatalogError(f"Unable to load translation catalog: {path}") from error
        if not isinstance(payload, dict):
            raise TranslationCatalogError(f"Translation catalog must contain an object: {path}")
        validate_catalog(payload, path)
        self._catalog = payload
        self._locale = locale
        if emit:
            self.language_changed.emit(locale)

    def translate(self, key: str, *args: object, **kwargs: object) -> str:
        value: Any = self._catalog
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                LOGGER.warning("Missing translation key: %s", key)
                return key
            value = value[part]
        if not isinstance(value, str):
            LOGGER.warning("Translation key does not resolve to text: %s", key)
            return key
        try:
            return value.format(*args, **kwargs)
        except (IndexError, KeyError, ValueError):
            LOGGER.warning("Unable to format translation key: %s", key, exc_info=True)
            return value
