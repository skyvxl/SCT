from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from sct.qt_environment import configure_qt_environment


def get_qapplication() -> QApplication:
    configure_qt_environment()
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application
