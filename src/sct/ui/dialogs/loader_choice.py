from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sct.localization import TranslationService
from sct.mod_loaders import LoaderKind


class LoaderChoiceDialog(QDialog):
    def __init__(
            self,
            translator: TranslationService,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.selected_loader: LoaderKind | None = None
        self.setModal(True)
        root = QVBoxLayout(self)
        description = QLabel(translator.translate("loader_choice.description"))
        description.setWordWrap(True)
        root.addWidget(description)
        self.me3_button = QPushButton(translator.translate("loader.me3_recommended"))
        self.me2_button = QPushButton(translator.translate("loader.me2_legacy"))
        self.me3_button.clicked.connect(
            lambda _checked=False: self._select(LoaderKind.MODENGINE3)
        )
        self.me2_button.clicked.connect(
            lambda _checked=False: self._select(LoaderKind.MODENGINE2)
        )
        root.addWidget(self.me3_button)
        root.addWidget(self.me2_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            translator.translate("common.cancel")
        )
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.setWindowTitle(translator.translate("loader_choice.title"))
        self.adjustSize()
        self.setFixedSize(self.size())

    def _select(self, loader: LoaderKind) -> None:
        self.selected_loader = loader
        self.accept()
