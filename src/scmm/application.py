from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication, QMessageBox

from scmm.installer import ModInstaller
from scmm.localization import TranslationCatalogError, TranslationService
from scmm.logging_config import configure_logging
from scmm.resource_loader import load_stylesheet
from scmm.runtime_config import RuntimeConfig
from scmm.settings import SettingsStore
from scmm.steam import SteamService
from scmm.ui.main_window import MainWindow
from scmm.ui.pages import build_page_specs

LOGGER = logging.getLogger("scmm.application")


def get_application(arguments: Sequence[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    application = QApplication(list(arguments) if arguments is not None else sys.argv)
    application.setApplicationName("Seamless Co-op Mod Manager")
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
    except TranslationCatalogError as error:
        LOGGER.exception("Unable to initialize localization")
        QMessageBox.critical(
            None,
            "Ошибка локализации",
            f"Не удалось загрузить русский перевод.\n\n{error}",
        )
        return 1
    try:
        application.setStyleSheet(load_stylesheet())
        settings_store = SettingsStore()
        settings_store.ensure_exists()
        window = build_main_window(translator, settings_store, SteamService())
    except Exception as error:
        LOGGER.exception("Unable to build application window")
        QMessageBox.critical(
            None,
            translator.translate("bootstrap.startup_error_title"),
            translator.translate("bootstrap.startup_error_message", error=error),
        )
        return 1
    window.show()
    return application.exec()
