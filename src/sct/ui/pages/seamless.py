from __future__ import annotations

import logging

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sct.ersc_settings import ErscSettings, ErscSettingsStore
from sct.localization import TranslationService
from sct.settings import SettingsStore
from sct.ui.pages.base import LocalizedPage
from sct.ui.widgets import CompactComboBox
from sct.ui.widgets.forms import action_button, add_form_row, section

LOGGER = logging.getLogger("sct.ui.seamless")


def spin_box(value: int, minimum: int = 0, maximum: int = 999) -> QSpinBox:
    control = QSpinBox()
    control.setRange(minimum, maximum)
    control.setValue(value)
    return control


class SeamlessPage(LocalizedPage):
    def __init__(
        self,
        translator: TranslationService,
        settings_store: SettingsStore,
    ) -> None:
        super().__init__(translator)
        self.settings_store = settings_store
        self._loading_settings = True
        self.ersc_store: ErscSettingsStore | None = None
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
        self.append_steam_id = QCheckBox()
        self.always_spectate = QCheckBox()
        for control, key in (
            (self.allow_invaders, "seamless.gameplay.allow_invaders"),
            (self.death_debuffs, "seamless.gameplay.death_debuffs"),
            (self.allow_summons, "seamless.gameplay.allow_summons"),
            (self.skip_splash, "seamless.gameplay.skip_splash"),
            (self.append_steam_id, "seamless.gameplay.append_steam_id"),
            (self.always_spectate, "seamless.gameplay.always_spectate"),
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

        self.reset_button = action_button(self, "seamless.reset", "resetSettingsButton")
        layout.addWidget(self.reset_button)
        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll)

        for control in (
            self.allow_invaders,
            self.death_debuffs,
            self.allow_summons,
            self.skip_splash,
            self.append_steam_id,
            self.always_spectate,
        ):
            control.toggled.connect(self._save_settings)
        self.overhead_combo.currentIndexChanged.connect(self._save_settings)
        self.volume_spin.valueChanged.connect(self._save_settings)
        for control in self.scaling_spins:
            control.valueChanged.connect(self._save_settings)
        self.password_edit.editingFinished.connect(self._save_settings)
        self.extension_edit.editingFinished.connect(self._save_settings)
        self.mod_language_edit.editingFinished.connect(self._save_settings)
        self.reset_button.clicked.connect(self._reset_settings)
        self.set_game_directory(self.settings_store.load().mod_path)

    def set_game_directory(self, game_directory: str) -> None:
        self.ersc_store = (
            ErscSettingsStore.from_game_directory(game_directory)
            if game_directory.strip()
            else None
        )
        self._load_settings()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        current_directory = self.settings_store.load().mod_path
        expected_path = (
            ErscSettingsStore.from_game_directory(current_directory).path
            if current_directory
            else None
        )
        if self.ersc_store is None or self.ersc_store.path != expected_path:
            self.set_game_directory(current_directory)
        elif self.ersc_store.path.is_file():
            self._load_settings()

    def _load_settings(self) -> None:
        settings = self.ersc_store.load() if self.ersc_store is not None else ErscSettings()
        self._loading_settings = True
        self.allow_invaders.setChecked(settings.allow_invaders)
        self.death_debuffs.setChecked(settings.death_debuffs)
        self.allow_summons.setChecked(settings.allow_summons)
        self.skip_splash.setChecked(settings.skip_splash_screens)
        self.append_steam_id.setChecked(settings.append_steam_id_to_players)
        self.always_spectate.setChecked(settings.always_spectate_on_death)
        self.overhead_combo.setCurrentIndex(settings.overhead_player_display)
        self.volume_spin.setValue(settings.default_boot_master_volume)
        scaling_values = (
            settings.enemy_health_scaling,
            settings.enemy_damage_scaling,
            settings.enemy_posture_scaling,
            settings.boss_health_scaling,
            settings.boss_damage_scaling,
            settings.boss_posture_scaling,
        )
        for control, value in zip(self.scaling_spins, scaling_values, strict=True):
            control.setValue(value)
        self.password_edit.setText(settings.cooppassword)
        self.extension_edit.setText(settings.save_file_extension)
        self.mod_language_edit.setText(settings.mod_language_override)
        self._loading_settings = False

    def _current_settings(self) -> ErscSettings:
        scaling = [control.value() for control in self.scaling_spins]
        return ErscSettings(
            allow_invaders=self.allow_invaders.isChecked(),
            death_debuffs=self.death_debuffs.isChecked(),
            allow_summons=self.allow_summons.isChecked(),
            overhead_player_display=self.overhead_combo.currentIndex(),
            skip_splash_screens=self.skip_splash.isChecked(),
            append_steam_id_to_players=self.append_steam_id.isChecked(),
            always_spectate_on_death=self.always_spectate.isChecked(),
            default_boot_master_volume=self.volume_spin.value(),
            enemy_health_scaling=scaling[0],
            enemy_damage_scaling=scaling[1],
            enemy_posture_scaling=scaling[2],
            boss_health_scaling=scaling[3],
            boss_damage_scaling=scaling[4],
            boss_posture_scaling=scaling[5],
            cooppassword=self.password_edit.text().strip(),
            save_file_extension=self.extension_edit.text().strip(),
            mod_language_override=self.mod_language_edit.text().strip(),
        )

    def _save_settings(self, _value: object = None) -> None:
        if self._loading_settings or self.ersc_store is None or not self.ersc_store.path.is_file():
            return
        try:
            self.ersc_store.save(self._current_settings())
        except OSError:
            LOGGER.exception("Unable to save Seamless Co-op settings")

    def _reset_settings(self) -> None:
        defaults = ErscSettings()
        self._loading_settings = True
        self._apply_settings(defaults)
        self._loading_settings = False
        self._save_settings()

    def _apply_settings(self, settings: ErscSettings) -> None:
        self.allow_invaders.setChecked(settings.allow_invaders)
        self.death_debuffs.setChecked(settings.death_debuffs)
        self.allow_summons.setChecked(settings.allow_summons)
        self.skip_splash.setChecked(settings.skip_splash_screens)
        self.append_steam_id.setChecked(settings.append_steam_id_to_players)
        self.always_spectate.setChecked(settings.always_spectate_on_death)
        self.overhead_combo.setCurrentIndex(settings.overhead_player_display)
        self.volume_spin.setValue(settings.default_boot_master_volume)
        values = (
            settings.enemy_health_scaling,
            settings.enemy_damage_scaling,
            settings.enemy_posture_scaling,
            settings.boss_health_scaling,
            settings.boss_damage_scaling,
            settings.boss_posture_scaling,
        )
        for control, value in zip(self.scaling_spins, values, strict=True):
            control.setValue(value)
        self.password_edit.setText(settings.cooppassword)
        self.extension_edit.setText(settings.save_file_extension)
        self.mod_language_edit.setText(settings.mod_language_override)
