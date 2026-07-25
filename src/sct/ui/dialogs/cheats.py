from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, QSize
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sct.game.cheats import Cheat
from sct.localization import TranslationService
from sct.resource_loader import load_optional_icon

ToggleCallback = Callable[[Cheat, bool], None]

CHEAT_TRANSLATION_KEYS = {
    Cheat.NO_WEIGHT: "cheats.items.no_weight",
    Cheat.NO_DEATH: "cheats.items.no_death",
    Cheat.NO_DAMAGE: "cheats.items.no_damage",
    Cheat.NO_HIT: "cheats.items.no_hit",
    Cheat.INFINITE_STAMINA: "cheats.items.infinite_stamina",
    Cheat.INFINITE_FP: "cheats.items.infinite_fp",
    Cheat.INFINITE_CONSUMABLES: "cheats.items.infinite_consumables",
}


class CheatDialog(QDialog):
    def __init__(
        self,
        translator: TranslationService,
        enabled_cheats: frozenset[Cheat],
        on_toggle: ToggleCallback,
        parent: QWidget | None = None,
        *,
        on_remove_items: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self._on_toggle = on_toggle
        self.cheat_labels: dict[Cheat, QLabel] = {}
        self.cheat_buttons: dict[Cheat, QPushButton] = {}
        self.remove_label: QLabel | None = None
        self.remove_button: QPushButton | None = None
        self.setObjectName("cheatDialog")
        self.setModal(False)

        root = QVBoxLayout(self)
        self.title_label = QLabel()
        self.title_label.setObjectName("cheatDialogTitle")
        root.addWidget(self.title_label)
        self.description_label = QLabel()
        self.description_label.setObjectName("cheatDialogDescription")
        root.addWidget(self.description_label)

        root.addSpacing(16)
        for cheat in Cheat:
            row = QFrame()
            row.setObjectName("cheatRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)
            label = QLabel()
            row_layout.addWidget(label, 1)
            button = QPushButton()
            button.setObjectName("cheatToggleButton")
            button.setCheckable(True)
            button.setFixedSize(30, 30)
            button.setIconSize(QSize(20, 20))
            button.setChecked(cheat in enabled_cheats)
            self._update_button(button)
            button.toggled.connect(
                lambda enabled, value=cheat: self._handle_toggle(value, enabled)
            )
            row_layout.addWidget(button)
            root.addWidget(row)
            self.cheat_labels[cheat] = label
            self.cheat_buttons[cheat] = button
        root.addStretch(1)
        if on_remove_items is not None:
            footer = QFrame()
            footer.setObjectName("cheatRemovalRow")
            footer_layout = QHBoxLayout(footer)
            self.remove_label = QLabel()
            footer_layout.addWidget(self.remove_label, 1)
            self.remove_button = QPushButton()
            self.remove_button.setObjectName("removeCoopItemsButton")
            self.remove_button.clicked.connect(on_remove_items)
            footer_layout.addWidget(self.remove_button)
            root.addWidget(footer)

        self.translator.language_changed.connect(lambda _locale: self.retranslate_ui())
        self.retranslate_ui()
        self.setFixedSize(420, 640 if on_remove_items is not None else 570)

    def set_cheat_state(self, cheat: Cheat, enabled: bool) -> None:
        button = self.cheat_buttons[cheat]
        blocker = QSignalBlocker(button)
        button.setChecked(enabled)
        del blocker
        self._update_button(button)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.translator.translate("cheats.window_title"))
        self.title_label.setText(self.translator.translate("cheats.title"))
        self.description_label.setText(self.translator.translate("cheats.description"))
        for cheat, label in self.cheat_labels.items():
            label.setText(self.translator.translate(CHEAT_TRANSLATION_KEYS[cheat]))
        if self.remove_label is not None:
            self.remove_label.setText(
                self.translator.translate("cheats.remove_coop_items")
            )
        if self.remove_button is not None:
            self.remove_button.setText(self.translator.translate("cheats.remove_button"))

    def _handle_toggle(self, cheat: Cheat, enabled: bool) -> None:
        self._update_button(self.cheat_buttons[cheat])
        self._on_toggle(cheat, enabled)

    @staticmethod
    def _update_button(button: QPushButton) -> None:
        enabled = button.isChecked()
        button.setProperty("enabledState", enabled)
        icon_name = "checkbox-checked.png" if enabled else "checkbox-unchecked.png"
        icon = load_optional_icon("icons", icon_name)
        if icon is not None:
            button.setIcon(icon)
        button.style().unpolish(button)
        button.style().polish(button)
