from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sct.errors import localized_error_message
from sct.installer import ModInstaller
from sct.localization import TranslationService
from sct.mod_loaders import LoaderKind, LoaderState, ModLoaderManager
from sct.settings import SettingsStore

LOGGER = logging.getLogger("sct.ui.loader_manager")
InstallerFactory = Callable[[], ModInstaller]


class LoaderInstallWorker(QObject):
    progress = Signal(str, int)
    completed = Signal(object)
    failed = Signal(object)
    finished = Signal()

    def __init__(
            self,
            installer: ModInstaller,
            game_directory: Path,
            loader: LoaderKind,
    ) -> None:
        super().__init__()
        self.installer = installer
        self.game_directory = game_directory
        self.loader = loader

    @Slot()
    def run(self) -> None:
        try:
            result = self.installer.install_loader(
                self.game_directory,
                self.loader,
                progress=self.progress.emit,
            )
        except Exception as error:
            LOGGER.exception("Unable to install mod loader")
            self.failed.emit(error)
        else:
            self.completed.emit(result)
        finally:
            self.finished.emit()


class LoaderManagerDialog(QDialog):
    loaders_changed = Signal()

    def __init__(
            self,
            translator: TranslationService,
            settings_store: SettingsStore,
            installer_factory: InstallerFactory,
            loader_manager: ModLoaderManager,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.settings_store = settings_store
        self.installer_factory = installer_factory
        self.loader_manager = loader_manager
        self.game_directory = Path(settings_store.load().mod_path)
        self._thread: QThread | None = None
        self._worker: LoaderInstallWorker | None = None
        self._pending_result: LoaderState | None = None
        self._pending_error: BaseException | None = None
        self.setModal(True)
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        self.description = QLabel()
        self.description.setWordWrap(True)
        root.addWidget(self.description)
        self.game_path_label = QLabel()
        self.game_path_label.setWordWrap(True)
        root.addWidget(self.game_path_label)

        self.rows: dict[LoaderKind, tuple[QLabel, QPushButton, QPushButton]] = {}
        for kind in (LoaderKind.MODENGINE3, LoaderKind.MODENGINE2):
            row = QHBoxLayout()
            status = QLabel()
            row.addWidget(status, 1)
            install_button = QPushButton()
            install_button.clicked.connect(
                lambda _checked=False, selected=kind: self._start_install(selected)
            )
            row.addWidget(install_button)
            remove_button = QPushButton()
            remove_button.clicked.connect(
                lambda _checked=False, selected=kind: self._remove(selected)
            )
            row.addWidget(remove_button)
            root.addLayout(row)
            self.rows[kind] = (status, install_button, remove_button)

        self.legacy_warning = QLabel()
        self.legacy_warning.setProperty("role", "warning")
        self.legacy_warning.setWordWrap(True)
        root.addWidget(self.legacy_warning)
        self.progress_label = QLabel()
        self.progress_label.setVisible(False)
        root.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText(
            translator.translate("common.close")
        )
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self.translator.language_changed.connect(lambda _locale: self.retranslate_ui())
        self.retranslate_ui()
        self.refresh()
        self.adjustSize()
        self.setFixedSize(self.size())

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.translator.translate("loader_manager.title"))
        self.description.setText(self.translator.translate("loader_manager.description"))
        game_path = str(self.game_directory) if str(self.game_directory) != "." else ""
        self.game_path_label.setText(
            self.translator.translate("loader_manager.game_path", path=game_path)
        )
        self.legacy_warning.setText(
            self.translator.translate("loader_manager.me2_warning")
        )
        self.refresh()

    def refresh(self) -> None:
        valid_game = (self.game_directory / "eldenring.exe").is_file()
        for kind, (status_label, install_button, remove_button) in self.rows.items():
            state = self.loader_manager.state(self.game_directory, kind)
            name_key = "loader.me3_recommended" if kind is LoaderKind.MODENGINE3 else "loader.me2_legacy"
            state_text = self.translator.translate(
                "loader_manager.installed" if state.installed else "loader_manager.not_installed",
                version=state.version or self.translator.translate("loader_manager.unknown_version"),
            )
            status_label.setText(
                self.translator.translate(
                    "loader_manager.status",
                    name=self.translator.translate(name_key),
                    state=state_text,
                )
            )
            install_button.setText(
                self.translator.translate(
                    "loader_manager.reinstall" if state.installed else "loader_manager.install"
                )
            )
            install_button.setEnabled(valid_game and self._thread is None)
            remove_button.setText(self.translator.translate("loader_manager.remove"))
            remove_button.setEnabled(state.installed and self._thread is None)

    def _start_install(self, loader: LoaderKind) -> None:
        if self._thread is not None:
            return
        try:
            installer = self.installer_factory()
        except Exception as error:
            self._show_error(error)
            return
        self._thread = QThread(self)
        self._set_running(True)
        self._worker = LoaderInstallWorker(installer, self.game_directory, loader)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._handle_progress)
        self._worker.completed.connect(self._store_success)
        self._worker.failed.connect(self._store_failure)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._finish_operation)
        self._thread.start()

    def _remove(self, loader: LoaderKind) -> None:
        dialog = QMessageBox(
            QMessageBox.Icon.Question,
            self.translator.translate("loader_manager.remove_title"),
            self.translator.translate(
                "loader_manager.remove_message",
                name=self._loader_name(loader),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            self,
        )
        dialog.button(QMessageBox.StandardButton.Yes).setText(
            self.translator.translate("common.yes")
        )
        dialog.button(QMessageBox.StandardButton.No).setText(
            self.translator.translate("common.no")
        )
        if dialog.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            self.installer_factory().remove_loader(self.game_directory, loader)
        except Exception as error:
            self._show_error(error)
            return
        if self.settings_store.load().default_mod_loader == loader.value:
            self.settings_store.update(default_mod_loader="")
        self.loaders_changed.emit()
        self.refresh()

    @Slot(str, int)
    def _handle_progress(self, phase: str, percent: int) -> None:
        self.progress_bar.setValue(percent)
        self.progress_label.setText(
            self.translator.translate(f"auto_setup.phases.{phase}")
        )

    @Slot(object)
    def _store_success(self, state: LoaderState) -> None:
        self._pending_result = state

    @Slot(object)
    def _store_failure(self, error: BaseException) -> None:
        self._pending_error = error

    @Slot()
    def _finish_operation(self) -> None:
        result = self._pending_result
        error = self._pending_error
        self._pending_result = None
        self._pending_error = None
        self._worker = None
        self._thread = None
        self._set_running(False)
        if error is not None:
            self._show_error(error)
            return
        if result is None:
            return
        if not self.settings_store.load().default_mod_loader:
            self.settings_store.update(default_mod_loader=result.kind.value)
        self.loaders_changed.emit()
        self.refresh()
        QMessageBox.information(
            self,
            self.translator.translate("loader_manager.success_title"),
            self.translator.translate(
                "loader_manager.success_message",
                name=self._loader_name(result.kind),
            ),
        )

    def _set_running(self, running: bool) -> None:
        self.progress_label.setVisible(running)
        self.progress_bar.setVisible(running)
        self.buttons.setEnabled(not running)
        self.refresh()

    def _loader_name(self, loader: LoaderKind) -> str:
        key = "loader.me3_recommended" if loader is LoaderKind.MODENGINE3 else "loader.me2_legacy"
        return self.translator.translate(key)

    def _show_error(self, error: BaseException) -> None:
        QMessageBox.critical(
            self,
            self.translator.translate("loader_manager.error_title"),
            localized_error_message(self.translator, error),
        )

    def reject(self) -> None:
        if self._thread is None:
            super().reject()
