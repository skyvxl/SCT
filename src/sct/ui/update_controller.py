from __future__ import annotations

import html
import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QWidget

from sct.errors import localized_error_message
from sct.localization import TranslationService
from sct.settings import SettingsStore
from sct.updates import UpdateCheck, UpdateService, UpdateState

LOGGER = logging.getLogger("sct.ui.updates")
UpdateServiceFactory = Callable[[], UpdateService]
ProgressOperation = Callable[[Callable[[str, int], None]], object]


class UpdateWorker(QObject):
    progress = Signal(str, int)
    completed = Signal(object)
    failed = Signal(object)
    finished = Signal()

    def __init__(self, operation: ProgressOperation) -> None:
        super().__init__()
        self.operation = operation

    @Slot()
    def run(self) -> None:
        try:
            result = self.operation(self.progress.emit)
        except Exception as error:
            LOGGER.exception("Update operation failed")
            self.failed.emit(error)
        else:
            self.completed.emit(result)
        finally:
            self.finished.emit()


class UpdateCallbackRelay(QObject):
    def __init__(
            self,
            completed: Callable[[object], None],
            failed: Callable[[BaseException], None],
            progress: Callable[[str, int], None] | None,
            parent: QObject,
    ) -> None:
        super().__init__(parent)
        self._completed = completed
        self._failed = failed
        self._progress = progress

    @Slot(object)
    def handle_completed(self, result: object) -> None:
        self._completed(result)

    @Slot(object)
    def handle_failed(self, error: BaseException) -> None:
        self._failed(error)

    @Slot(str, int)
    def handle_progress(self, phase: str, percent: int) -> None:
        if self._progress is not None:
            self._progress(phase, percent)


class UpdateController(QObject):
    ersc_updated = Signal(object)
    auto_setup_requested = Signal()

    def __init__(
            self,
            translator: TranslationService,
            settings_store: SettingsStore,
            service_factory: UpdateServiceFactory,
            parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.settings_store = settings_store
        self.service_factory = service_factory
        self._jobs: dict[QThread, tuple[UpdateWorker, UpdateCallbackRelay]] = {}

    def check_toolkit(self, parent: QWidget) -> None:
        self._start_job(
            lambda _progress: self.service_factory().check_toolkit(),
            lambda result: self._handle_toolkit_check(parent, result),
            lambda error: self._show_error(parent, error),
        )

    def check_ersc(self, parent: QWidget) -> None:
        game_directory = self.settings_store.load().mod_path
        self._start_job(
            lambda _progress: self.service_factory().check_ersc(game_directory),
            lambda result: self._handle_ersc_check(parent, game_directory, result),
            lambda error: self._show_error(parent, error),
        )

    def shutdown(self) -> None:
        for thread in tuple(self._jobs):
            thread.quit()
            thread.wait()

    def _handle_toolkit_check(self, parent: QWidget, result: UpdateCheck) -> None:
        if result.state is UpdateState.AVAILABLE:
            answer = QMessageBox.question(
                parent,
                self.translator.translate("updates.toolkit.title"),
                self.translator.translate(
                    "updates.toolkit.available",
                    installed=result.installed_version,
                    latest=result.latest_version,
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes and result.release_url:
                QDesktopServices.openUrl(QUrl(result.release_url))
            return
        key = (
            "updates.toolkit.ahead"
            if result.state is UpdateState.AHEAD
            else "updates.toolkit.current"
        )
        QMessageBox.information(
            parent,
            self.translator.translate("updates.toolkit.title"),
            self.translator.translate(
                key,
                installed=result.installed_version,
                latest=result.latest_version,
            ),
        )

    def _handle_ersc_check(
            self,
            parent: QWidget,
            game_directory: str,
            result: UpdateCheck,
    ) -> None:
        if result.state is UpdateState.NOT_INSTALLED:
            answer = QMessageBox.question(
                parent,
                self.translator.translate("updates.ersc.title"),
                self._with_nexus_warning(
                    self.translator.translate("updates.ersc.not_installed")
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.auto_setup_requested.emit()
            return
        if result.state is UpdateState.CURRENT:
            QMessageBox.information(
                parent,
                self.translator.translate("updates.ersc.title"),
                self._with_nexus_warning(
                    self.translator.translate(
                        "updates.ersc.current",
                        installed=result.installed_version,
                    )
                ),
            )
            return
        if result.state is UpdateState.AHEAD:
            QMessageBox.information(
                parent,
                self.translator.translate("updates.ersc.title"),
                self._with_nexus_warning(
                    self.translator.translate(
                        "updates.ersc.ahead",
                        installed=result.installed_version,
                        latest=result.latest_version,
                    )
                ),
            )
            return

        answer = QMessageBox.question(
            parent,
            self.translator.translate("updates.ersc.title"),
            self._with_nexus_warning(
                self.translator.translate(
                    "updates.ersc.available",
                    installed=result.installed_version,
                    latest=result.latest_version,
                )
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes and result.asset is not None:
            self._install_ersc(parent, game_directory, result)

    def _install_ersc(
            self,
            parent: QWidget,
            game_directory: str,
            result: UpdateCheck,
    ) -> None:
        progress_dialog = QProgressDialog(parent)
        progress_dialog.setWindowTitle(
            self.translator.translate("updates.ersc.installing_title")
        )
        progress_dialog.setLabelText(
            self.translator.translate("updates.ersc.installing")
        )
        progress_dialog.setRange(0, 100)
        progress_dialog.setCancelButton(None)
        progress_dialog.setAutoClose(False)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()

        def operation(progress: Callable[[str, int], None]) -> object:
            service = self.service_factory()
            return service.install_ersc_update(
                Path(game_directory),
                result.asset,
                progress=progress,
            )

        def completed(install_result: object) -> None:
            progress_dialog.close()
            self.ersc_updated.emit(install_result)
            QMessageBox.information(
                parent,
                self.translator.translate("updates.ersc.success_title"),
                self.translator.translate(
                    "updates.ersc.success",
                    version=result.latest_version,
                ),
            )

        def failed(error: BaseException) -> None:
            progress_dialog.close()
            self._show_error(parent, error)

        self._start_job(
            operation,
            completed,
            failed,
            progress=lambda _phase, value: progress_dialog.setValue(value),
        )

    def _start_job(
            self,
            operation: ProgressOperation,
            completed: Callable[[object], None],
            failed: Callable[[BaseException], None],
            *,
            progress: Callable[[str, int], None] | None = None,
    ) -> None:
        thread = QThread(self)
        worker = UpdateWorker(operation)
        relay = UpdateCallbackRelay(completed, failed, progress, self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(relay.handle_completed)
        worker.failed.connect(relay.handle_failed)
        if progress is not None:
            worker.progress.connect(relay.handle_progress)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(relay.deleteLater)
        thread.finished.connect(lambda thread=thread: self._jobs.pop(thread, None))
        self._jobs[thread] = (worker, relay)
        thread.start()

    def _show_error(self, parent: QWidget, error: BaseException) -> None:
        QMessageBox.critical(
            parent,
            self.translator.translate("updates.error_title"),
            self.translator.translate(
                "updates.error",
                message=localized_error_message(self.translator, error),
            ),
        )

    def _with_nexus_warning(self, message: str) -> str:
        warning = self.translator.translate("updates.ersc.github_nexus_warning")
        body = html.escape(message).replace("\n", "<br>")
        return (
            f"<p>{body}</p>"
            f'<p style="color:#ffb020;font-weight:600">{html.escape(warning)}</p>'
        )
