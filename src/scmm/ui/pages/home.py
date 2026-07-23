from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QPushButton, QVBoxLayout

from scmm.localization import TranslationService
from scmm.resource_loader import load_optional_icon
from scmm.ui.pages.base import LocalizedPage


class HomePage(LocalizedPage):
    def __init__(self, translator: TranslationService) -> None:
        super().__init__(translator)
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
