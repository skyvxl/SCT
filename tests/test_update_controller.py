from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from sct.localization import TranslationService
from sct.settings import SettingsStore
from sct.ui.update_controller import UpdateController
from sct.updates import UpdateCheck, UpdateState
from tests.qt_helpers import get_qapplication


class CompletionProbe(QObject):
    completed = Signal()


class FakeUpdateService:
    @staticmethod
    def check_toolkit() -> UpdateCheck:
        return UpdateCheck(
            installed_version="0.2.0",
            latest_version="v0.2.0",
            state=UpdateState.CURRENT,
            release_url="https://example.invalid/releases/v0.2.0",
        )


class UpdateControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_toolkit_result_opens_message_box_on_gui_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsStore(Path(directory) / "settings.ini")
            settings.ensure_exists()
            controller = UpdateController(
                TranslationService(locale="en"),
                settings,
                service_factory=FakeUpdateService,
            )
            parent = QWidget()
            loop = QEventLoop()
            probe = CompletionProbe()
            probe.completed.connect(loop.quit)
            callback_threads: list[QThread] = []

            def information(*_args: object, **_kwargs: object) -> object:
                callback_threads.append(QThread.currentThread())
                probe.completed.emit()
                return QMessageBox.StandardButton.Ok

            with patch(
                "sct.ui.update_controller.QMessageBox.information",
                side_effect=information,
            ):
                controller.check_toolkit(parent)
                QTimer.singleShot(2000, loop.quit)
                loop.exec()
                controller.shutdown()

            self.assertEqual(callback_threads, [self.application.thread()])


if __name__ == "__main__":
    unittest.main()
