from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scmm.localization import TranslationService
from scmm.resource_loader import load_optional_icon
from scmm.version import DISPLAY_VERSION


class AboutDialog(QDialog):
    def __init__(
        self,
        translator: TranslationService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.setObjectName("aboutDialog")
        self.setModal(True)
        self.setMinimumSize(480, 245)

        root = QVBoxLayout(self)
        content = QHBoxLayout()
        application_icon = load_optional_icon("icons", "icon.ico")
        if application_icon is not None:
            icon = QLabel()
            icon.setPixmap(application_icon.pixmap(40, 40))
            icon.setAlignment(Qt.AlignmentFlag.AlignTop)
            content.addWidget(icon)

        self.body_label = QLabel()
        self.body_label.setObjectName("aboutBodyLabel")
        self.body_label.setWordWrap(True)
        self.body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content.addWidget(self.body_label, 1)
        root.addLayout(content)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.accept_button = QPushButton()
        self.accept_button.setObjectName("aboutAcceptButton")
        self.accept_button.clicked.connect(self.accept)
        button_row.addWidget(self.accept_button)
        root.addLayout(button_row)

        translator.language_changed.connect(lambda _locale: self.retranslate_ui())
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.translator.translate("menu.about"))
        self.body_label.setText(
            "\n".join(
                (
                    self.translator.translate("about.product_name"),
                    self.translator.translate("about.version", version=DISPLAY_VERSION),
                    "",
                    self.translator.translate("about.description"),
                    "",
                    self.translator.translate("about.maintainer"),
                    self.translator.translate("about.based_on"),
                    self.translator.translate("about.license"),
                )
            )
        )
        self.accept_button.setText(self.translator.translate("common.accept"))
