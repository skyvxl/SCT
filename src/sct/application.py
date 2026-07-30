from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication, QMessageBox

from sct.backup_manager import BackupManager, build_backup_manager
from sct.game.runtime import EldenRingRuntime, build_elden_ring_runtime
from sct.installer import ModInstaller
from sct.localization import TranslationCatalogError, TranslationService
from sct.logging_config import configure_logging
from sct.resource_loader import load_stylesheet
from sct.runtime_config import RuntimeConfig
from sct.screenshots import GameWindowCapture
from sct.settings import SettingsStore
from sct.steam import SteamService
from sct.ui.main_window import MainWindow
from sct.ui.pages import build_page_specs
from sct.updates import UpdateService

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
        game_runtime: EldenRingRuntime | None = None,
        backup_manager: BackupManager | None = None,
) -> MainWindow:
    runtime = game_runtime or build_elden_ring_runtime(settings_store.path)
    screenshot_capture: GameWindowCapture | None = None
    if backup_manager is None:
        screenshot_capture = GameWindowCapture()
        backups = build_backup_manager(
            settings_store,
            screenshot_provider=screenshot_capture.capture,
        )
    else:
        backups = backup_manager
    window = MainWindow(
        translator,
        build_page_specs(
            translator,
            settings_store,
            steam_service,
            runtime,
            backups,
        ),
        settings_store,
        lambda: ModInstaller(RuntimeConfig.load()),
        lambda: UpdateService(RuntimeConfig.load()),
    )
    if screenshot_capture is not None:
        screenshot_capture.setParent(window)
    return window


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
        settings = settings_store.ensure_exists()
        if settings.preferred_language != translator.locale:
            translator.set_locale(settings.preferred_language)
        window = build_main_window(translator, settings_store, SteamService())
    except TranslationCatalogError:
        LOGGER.exception("Unable to initialize localization")
        QMessageBox.critical(
            None,
            "Localization error",
            "Unable to load localization resources.",
        )
        return 1
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
