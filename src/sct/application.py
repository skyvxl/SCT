from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication, QMessageBox

from sct.installer import ModInstaller
from sct.localization import TranslationCatalogError, TranslationService
from sct.logging_config import configure_logging
from sct.resource_loader import load_stylesheet
from sct.runtime_config import RuntimeConfig
from sct.settings import SettingsStore
from sct.steam import SteamService
from sct.ui.main_window import MainWindow
from sct.ui.pages import build_page_specs

LOGGER = logging.getLogger("sct.application")


def get_application(arguments: Sequence[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    application = QApplication(list(arguments) if arguments is not None else sys.argv)
    application.setApplicationName("Seamless Co-op Toolkit")
    application.setOrganizationName("skyvxl")
    return application


def build_main_window(
    translator: TranslationService,
    settings_store: SettingsStore,
    steam_service: SteamService,
) -> MainWindow:
    return MainWindow(
        translator,
        build_page_specs(translator, settings_store, steam_service),
        settings_store,
        lambda: ModInstaller(RuntimeConfig.load()),
    )


def main(arguments: Sequence[str] | None = None) -> int:
    configure_logging()
    application = get_application(arguments)
    try:
        translator = TranslationService()
    except TranslationCatalogError:
        LOGGER.exception("Unable to initialize localization")
        QMessageBox.critical(
            None,
            "Localization error",
            "Unable to load localization resources.",
        )
        return 1
    try:
        application.setStyleSheet(load_stylesheet())
        settings_store = SettingsStore()
        settings_store.ensure_exists()
        window = build_main_window(translator, settings_store, SteamService())
    except Exception:
        LOGGER.exception("Unable to build application window")
        QMessageBox.critical(
            None,
            translator.translate("bootstrap.startup_error_title"),
            translator.translate("bootstrap.startup_error_message"),
        )
        return 1
    window.show()
    return application.exec()
