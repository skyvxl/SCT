from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QComboBox, QMenu, QWidget

from sct.ui.native_windows import request_square_corners


class CompactComboBox(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "compactCombo")
        self.setIconSize(QSize(16, 16))
        self.view().setObjectName("compactComboPopupView")

    def showPopup(self) -> None:
        super().showPopup()
        request_square_corners(self.view().window())


class SquarePopupMenu(QMenu):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        request_square_corners(self)
