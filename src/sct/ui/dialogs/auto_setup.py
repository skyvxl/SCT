from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sct.installer import InstallResult, ModInstaller
from sct.localization import TranslationService
from sct.settings import SettingsStore

InstallerFactory = Callable[[], ModInstaller]


class InstallWorker(QObject):
    progress = Signal(str, int)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, installer: ModInstaller, game_directory: str, password: str) -> None:
        super().__init__()
        self.installer = installer
        self.game_directory = game_directory
        self.password = password

    @Slot()
    def run(self) -> None:
        try:
            result = self.installer.install(
                self.game_directory,
                self.password,
                progress=self.progress.emit,
            )
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.completed.emit(result)
        finally:
            self.finished.emit()


class AutoSetupDialog(QDialog):
    installation_completed = Signal(object)

    def __init__(
        self,
        translator: TranslationService,
        settings_store: SettingsStore,
        installer_factory: InstallerFactory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.settings_store = settings_store
        self.installer_factory = installer_factory
        self._thread: QThread | None = None
        self._worker: InstallWorker | None = None
        self._running = False
        self._pending_success_version: str | None = None

        self.setObjectName("autoSetupDialog")
        self.setModal(True)
        self.setMinimumWidth(600)

        root = QVBoxLayout(self)
        self.instructions = QLabel()
        self.instructions.setObjectName("autoSetupInstructions")
        self.instructions.setWordWrap(True)
        root.addWidget(self.instructions)

        self.game_path_label = QLabel()
        self.game_path_edit = QLineEdit()
        self.game_path_edit.setObjectName("autoSetupGamePathEdit")
        root.addWidget(self.game_path_label)
        game_row = QHBoxLayout()
        game_row.addWidget(self.game_path_edit, 1)
        self.browse_button = QPushButton()
        self.browse_button.setObjectName("autoSetupBrowseButton")
        self.browse_button.clicked.connect(self._browse_game_directory)
        game_row.addWidget(self.browse_button)
        root.addLayout(game_row)

        self.password_label = QLabel()
        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("autoSetupPasswordEdit")
        root.addWidget(self.password_label)
        root.addWidget(self.password_edit)

        self.status_label = QLabel()
        self.status_label.setObjectName("autoSetupStatusLabel")
        self.status_label.setVisible(False)
        root.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("autoSetupProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        self.start_button = QPushButton()
        self.start_button.setObjectName("autoSetupStartButton")
        self.start_button.clicked.connect(self._start_install)
        root.addWidget(self.start_button)

        self.translator.language_changed.connect(lambda _locale: self.retranslate_ui())
        self.retranslate_ui()
        self.adjustSize()
        self.setFixedSize(self.size())

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.translator.translate("auto_setup.title"))
        self.instructions.setText(self.translator.translate("auto_setup.instructions"))
        self.game_path_label.setText(self.translator.translate("auto_setup.game_path"))
        self.game_path_edit.setPlaceholderText(
            self.translator.translate("auto_setup.game_path_placeholder")
        )
        self.browse_button.setText(self.translator.translate("common.browse"))
        self.password_label.setText(self.translator.translate("auto_setup.password"))
        self.password_edit.setPlaceholderText(
            self.translator.translate("auto_setup.password_placeholder")
        )
        self.start_button.setText(self.translator.translate("auto_setup.start"))

    def _browse_game_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self.translator.translate("settings.game_path.dialog"),
            self.game_path_edit.text().strip(),
        )
        if selected:
            self.game_path_edit.setText(selected)

    def _start_install(self) -> None:
        game_directory = self.game_path_edit.text().strip()
        password = self.password_edit.text()
        if not (Path(game_directory) / "eldenring.exe").is_file():
            QMessageBox.warning(
                self,
                self.translator.translate("auto_setup.validation_title"),
                self.translator.translate("auto_setup.invalid_game_path"),
            )
            return
        if not password:
            QMessageBox.warning(
                self,
                self.translator.translate("auto_setup.validation_title"),
                self.translator.translate("auto_setup.password_required"),
            )
            return
        try:
            installer = self.installer_factory()
        except Exception as error:
            self._handle_failure(str(error))
            return

        self._set_running(True)
        self._thread = QThread(self)
        self._worker = InstallWorker(installer, game_directory, password)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._handle_progress)
        self._worker.completed.connect(self._handle_success)
        self._worker.failed.connect(self._handle_failure)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)
        self._thread.start()

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.game_path_edit.setEnabled(not running)
        self.password_edit.setEnabled(not running)
        self.browse_button.setEnabled(not running)
        self.start_button.setEnabled(not running)
        self.status_label.setVisible(running)
        self.progress_bar.setVisible(running)

    @Slot(str, int)
    def _handle_progress(self, phase: str, percent: int) -> None:
        self.progress_bar.setValue(percent)
        self.status_label.setText(
            self.translator.translate(f"auto_setup.phases.{phase}")
        )

    @Slot(object)
    def _handle_success(self, result: InstallResult) -> None:
        self.settings_store.update(
            mod_path=str(result.game_directory),
            game_exe_path=str(result.launcher_path),
        )
        self.installation_completed.emit(result)
        if self._thread is not None and self._thread.isRunning():
            self._pending_success_version = result.ersc_version
            return
        self._finish_success(result.ersc_version)

    def _finish_success(self, version: str) -> None:
        self._set_running(False)
        QMessageBox.information(
            self,
            self.translator.translate("auto_setup.success_title"),
            self.translator.translate(
                "auto_setup.success_message",
                version=version,
            ),
        )
        self.accept()

    @Slot(str)
    def _handle_failure(self, message: str) -> None:
        self._set_running(False)
        QMessageBox.critical(
            self,
            self.translator.translate("auto_setup.error_title"),
            self.translator.translate("auto_setup.error_message", error=message),
        )

    @Slot()
    def _clear_worker(self) -> None:
        pending_version = self._pending_success_version
        self._pending_success_version = None
        self._worker = None
        self._thread = None
        if pending_version is not None:
            self._finish_success(pending_version)

    def reject(self) -> None:
        if not self._running:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._running:
            event.ignore()
        else:
            super().closeEvent(event)
