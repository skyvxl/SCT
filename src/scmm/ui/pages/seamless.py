from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from scmm.localization import TranslationService
from scmm.ui.pages.base import LocalizedPage
from scmm.ui.widgets import CompactComboBox
from scmm.ui.widgets.forms import action_button, add_form_row, section


def spin_box(value: int, minimum: int = 0, maximum: int = 999) -> QSpinBox:
    control = QSpinBox()
    control.setRange(minimum, maximum)
    control.setValue(value)
    return control


class SeamlessPage(LocalizedPage):
    def __init__(self, translator: TranslationService) -> None:
        super().__init__(translator)
        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)

        gameplay = section(self, "seamless.gameplay.title")
        gameplay_layout = QFormLayout(gameplay)
        self.allow_invaders = QCheckBox()
        self.allow_invaders.setChecked(True)
        self.death_debuffs = QCheckBox()
        self.death_debuffs.setChecked(True)
        self.allow_summons = QCheckBox()
        self.allow_summons.setChecked(True)
        self.skip_splash = QCheckBox()
        self.skip_splash.setChecked(True)
        for control, key in (
            (self.allow_invaders, "seamless.gameplay.allow_invaders"),
            (self.death_debuffs, "seamless.gameplay.death_debuffs"),
            (self.allow_summons, "seamless.gameplay.allow_summons"),
            (self.skip_splash, "seamless.gameplay.skip_splash"),
        ):
            self.bind(control.setText, key)
            gameplay_layout.addRow(control)
        self.overhead_combo = CompactComboBox()
        self.overhead_combo.setObjectName("overheadDisplayCombo")
        overhead_keys = (
            "seamless.gameplay.overhead_normal",
            "seamless.gameplay.overhead_empty",
            "seamless.gameplay.overhead_ping",
            "seamless.gameplay.overhead_soul_level",
            "seamless.gameplay.overhead_deaths",
            "seamless.gameplay.overhead_soul_level_and_ping",
        )
        for index, key in enumerate(overhead_keys):
            self.overhead_combo.addItem("")
            self.bind(
                lambda text, item_index=index: self.overhead_combo.setItemText(item_index, text),
                key,
            )
        add_form_row(self, gameplay_layout, "seamless.gameplay.overhead", self.overhead_combo)
        self.volume_spin = spin_box(5, 0, 10)
        add_form_row(self, gameplay_layout, "seamless.gameplay.volume", self.volume_spin)
        layout.addWidget(gameplay)

        scaling = section(self, "seamless.scaling.title")
        scaling_layout = QFormLayout(scaling)
        scaling_values = (
            ("seamless.scaling.enemy_health", 35),
            ("seamless.scaling.enemy_damage", 0),
            ("seamless.scaling.enemy_posture", 15),
            ("seamless.scaling.boss_health", 100),
            ("seamless.scaling.boss_damage", 0),
            ("seamless.scaling.boss_posture", 20),
        )
        self.scaling_spins: list[QSpinBox] = []
        for key, value in scaling_values:
            control = spin_box(value)
            self.scaling_spins.append(control)
            add_form_row(self, scaling_layout, key, control)
        layout.addWidget(scaling)

        password = section(self, "seamless.password.title")
        password_layout = QFormLayout(password)
        self.password_edit = QLineEdit("12345")
        add_form_row(self, password_layout, "seamless.password.label", self.password_edit)
        layout.addWidget(password)

        save = section(self, "seamless.save.title")
        save_layout = QFormLayout(save)
        self.extension_edit = QLineEdit("co2")
        add_form_row(self, save_layout, "seamless.save.extension", self.extension_edit)
        layout.addWidget(save)

        language = section(self, "seamless.language.title")
        language_layout = QFormLayout(language)
        self.mod_language_edit = QLineEdit()
        self.bind(self.mod_language_edit.setPlaceholderText, "seamless.language.hint")
        add_form_row(self, language_layout, "seamless.language.override", self.mod_language_edit)
        layout.addWidget(language)

        layout.addWidget(action_button(self, "seamless.reset", "resetSettingsButton"))
        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll)
