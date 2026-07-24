from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QPushButton, QVBoxLayout

from scmm.localization import TranslationService
from scmm.resource_loader import load_optional_icon
from scmm.settings import AppSettings, SettingsStore
from scmm.steam import SteamService
from scmm.ui.pages.base import LocalizedPage

LOGGER = logging.getLogger("scmm.ui.home")


class HomePage(LocalizedPage):
    def __init__(
        self,
        translator: TranslationService,
        settings_store: SettingsStore,
        steam_service: SteamService,
    ) -> None:
        super().__init__(translator)
        self.settings_store = settings_store
        self.steam_service = steam_service
        self._pending_launch: AppSettings | None = None
        self._steam_wait_attempts = 0
        layout = QVBoxLayout(self)
        layout.addStretch(2)
        self.launch_button = QPushButton()
        self.launch_button.setObjectName("launchButton")
        self.launch_button.setMinimumHeight(42)
        self.bind(self.launch_button.setText, "home.launch")
        controller = load_optional_icon("icons", "controller.png")
        if controller is not None:
            self.launch_button.setIcon(controller)
        self.launch_button.setIconSize(QSize(28, 28))
        self.launch_button.clicked.connect(self._launch)
        layout.addWidget(self.launch_button)
        layout.addStretch(3)

        self.credit_button = QPushButton()
        self.credit_button.setObjectName("creditButton")
        self.credit_button.setFlat(True)
        self.credit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.credit_button.setText("❤️by skyvxl❤️")
        self.credit_button.clicked.connect(
            lambda _checked=False: QDesktopServices.openUrl(QUrl("https://github.com/skyvxl"))
        )
        layout.addWidget(self.credit_button, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _launch(self) -> None:
        settings = self.settings_store.load()
        launcher = Path(settings.game_exe_path)
        if not launcher.is_file():
            QMessageBox.warning(
                self,
                self.translator.translate("launch.missing_launcher_title"),
                self.translator.translate("launch.missing_launcher_message"),
            )
            return
        if self.steam_service.is_running():
            if not self._selected_profile_is_active(settings):
                return
            self._launch_game(launcher)
            return

        steam_executable = Path(settings.steam_exe_path)
        if not steam_executable.is_file():
            QMessageBox.warning(
                self,
                self.translator.translate("launch.missing_steam_title"),
                self.translator.translate("launch.missing_steam_message"),
            )
            return
        if not self._selected_profile_can_auto_start(settings):
            return
        try:
            self.steam_service.start(
                steam_executable,
                silently=settings.run_steam_silently,
            )
        except OSError as error:
            LOGGER.exception("Unable to start Steam")
            self._show_launch_error(error)
            return
        self._pending_launch = settings
        self._steam_wait_attempts = 0
        self.launch_button.setEnabled(False)
        QTimer.singleShot(500, self._wait_for_steam)

    def _wait_for_steam(self) -> None:
        settings = self._pending_launch
        if settings is None:
            self.launch_button.setEnabled(True)
            return
        if self.steam_service.is_running():
            self._pending_launch = None
            self.launch_button.setEnabled(True)
            if self._selected_profile_is_active(settings):
                self._launch_game(Path(settings.game_exe_path))
            return
        self._steam_wait_attempts += 1
        if self._steam_wait_attempts >= 30:
            self._pending_launch = None
            self.launch_button.setEnabled(True)
            QMessageBox.warning(
                self,
                self.translator.translate("launch.steam_timeout_title"),
                self.translator.translate("launch.steam_timeout_message"),
            )
            return
        QTimer.singleShot(500, self._wait_for_steam)

    def _selected_profile_is_active(self, settings: AppSettings) -> bool:
        if not settings.steam_id:
            return True
        active_id = self.steam_service.active_steam_id()
        if active_id is None or active_id == settings.steam_id:
            return True
        QMessageBox.warning(
            self,
            self.translator.translate("launch.profile_mismatch_title"),
            self.translator.translate("launch.profile_mismatch_message"),
        )
        return False

    def _selected_profile_can_auto_start(self, settings: AppSettings) -> bool:
        if not settings.steam_id:
            return True
        profiles = self.steam_service.profiles(settings.steam_exe_path)
        selected = next(
            (profile for profile in profiles if profile.steam_id == settings.steam_id),
            None,
        )
        if selected is None or selected.most_recent:
            return True
        QMessageBox.warning(
            self,
            self.translator.translate("launch.profile_mismatch_title"),
            self.translator.translate("launch.profile_autostart_message"),
        )
        return False

    def _launch_game(self, launcher: Path) -> None:
        try:
            self.steam_service.launch_game(launcher)
        except OSError as error:
            LOGGER.exception("Unable to start Seamless Co-op")
            self._show_launch_error(error)

    def _show_launch_error(self, error: OSError) -> None:
        QMessageBox.critical(
            self,
            self.translator.translate("launch.error_title"),
            self.translator.translate("launch.error_message", error=error),
        )
