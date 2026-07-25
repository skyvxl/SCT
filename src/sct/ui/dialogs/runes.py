from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sct.game.players import MAX_RUNES
from sct.localization import TranslationService


class RuneDialog(QDialog):
    def __init__(
        self,
        translator: TranslationService,
        current_value: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.setObjectName("runeDialog")
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.prompt_label = QLabel()
        layout.addWidget(self.prompt_label)

        self.value_spin = QSpinBox()
        self.value_spin.setObjectName("runeValueSpin")
        self.value_spin.setRange(0, MAX_RUNES)
        self.value_spin.setValue(max(0, min(current_value, MAX_RUNES)))
        layout.addWidget(self.value_spin)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.accept_button = QPushButton()
        self.accept_button.setObjectName("runeAcceptButton")
        self.accept_button.clicked.connect(self.accept)
        buttons.addWidget(self.accept_button)
        self.cancel_button = QPushButton()
        self.cancel_button.setObjectName("runeCancelButton")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.translator.language_changed.connect(lambda _locale: self.retranslate_ui())
        self.retranslate_ui()
        self.setFixedSize(330, 165)

    def rune_value(self) -> int:
        return self.value_spin.value()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.translator.translate("runes.dialog_title"))
        self.prompt_label.setText(self.translator.translate("runes.prompt"))
        self.accept_button.setText(self.translator.translate("common.ok"))
        self.cancel_button.setText(self.translator.translate("common.cancel"))
