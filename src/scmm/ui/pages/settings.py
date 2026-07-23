from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from scmm.localization import TranslationService
from scmm.resource_loader import load_optional_icon
from scmm.ui.pages.base import LocalizedPage
from scmm.ui.widgets import CompactComboBox
from scmm.ui.widgets.forms import action_button, add_form_row, section


def horizontal_widget(*widgets: QWidget) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    return container


def configured_spin(value: int, minimum: int, maximum: int) -> QSpinBox:
    control = QSpinBox()
    control.setRange(minimum, maximum)
    control.setValue(value)
    return control


class SettingsPage(LocalizedPage):
    def __init__(self, translator: TranslationService) -> None:
        super().__init__(translator)
        root = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("settingsScrollArea")
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)

        language = section(self, "settings.language.title")
        language_form = QFormLayout(language)
        self.language_combo = CompactComboBox()
        self.language_combo.setObjectName("languageCombo")
        self.language_combo.addItem("", "ru")
        russian_flag = load_optional_icon("flags", "ru.png")
        if russian_flag is not None:
            self.language_combo.setItemIcon(0, russian_flag)
        self.bind(
            lambda text: self.language_combo.setItemText(0, text),
            "settings.language.russian",
        )
        add_form_row(self, language_form, "settings.language.label", self.language_combo)
        layout.addWidget(language)

        game_path = section(self, "settings.game_path.title")
        game_form = QFormLayout(game_path)
        self.game_path_edit = QLineEdit()
        self.game_path_edit.setObjectName("gamePathEdit")
        browse_game = action_button(self, "common.browse", "browseGameButton")
        add_form_row(
            self,
            game_form,
            "settings.game_path.label",
            horizontal_widget(self.game_path_edit, browse_game),
        )
        layout.addWidget(game_path)

        launcher = section(self, "settings.launcher.title")
        launcher_form = QFormLayout(launcher)
        self.launcher_edit = QLineEdit()
        self.launcher_edit.setObjectName("seamlessExeEdit")
        browse_launcher = action_button(self, "common.browse", "browseLauncherButton")
        add_form_row(
            self,
            launcher_form,
            "settings.launcher.executable",
            horizontal_widget(self.launcher_edit, browse_launcher),
        )
        self.launcher_auto_update = QCheckBox()
        self.launcher_auto_update.setChecked(True)
        self.bind(self.launcher_auto_update.setText, "settings.launcher.auto_update")
        launcher_form.addRow(self.launcher_auto_update)
        layout.addWidget(launcher)

        steam = section(self, "settings.steam.title")
        steam_form = QFormLayout(steam)
        self.steam_edit = QLineEdit()
        self.steam_edit.setObjectName("steamExeEdit")
        browse_steam = action_button(self, "common.browse", "browseSteamButton")
        detect_steam = action_button(self, "settings.steam.auto_detect", "detectSteamButton")
        add_form_row(
            self,
            steam_form,
            "settings.steam.executable",
            horizontal_widget(self.steam_edit, browse_steam, detect_steam),
        )
        steam_status = QLabel()
        steam_status.setObjectName("steamStatusLabel")
        steam_status.setProperty("role", "danger")
        self.bind(steam_status.setText, "settings.steam.not_running")
        steam_form.addRow(steam_status)
        self.silent_steam = QCheckBox()
        self.silent_steam.setChecked(False)
        self.bind(self.silent_steam.setText, "settings.steam.silent")
        steam_form.addRow(self.silent_steam)
        self.steam_id_combo = CompactComboBox()
        self.steam_id_combo.setObjectName("steamIdCombo")
        self.steam_id_combo.addItem("")
        self.bind(
            lambda text: self.steam_id_combo.setItemText(0, text),
            "settings.steam.choose_id",
        )
        add_form_row(self, steam_form, "settings.steam.id", self.steam_id_combo)
        layout.addWidget(steam)

        modengine = section(self, "settings.modengine.title")
        modengine.setObjectName("modEngineSection")
        modengine.setMinimumHeight(180)
        modengine_layout = QVBoxLayout(modengine)
        modengine_layout.setContentsMargins(16, 18, 16, 18)
        modengine_layout.setSpacing(12)

        manager_card = QFrame()
        manager_card.setObjectName("modEngineManagerCard")
        manager_card_layout = QHBoxLayout(manager_card)
        manager_card_layout.setContentsMargins(12, 10, 8, 10)
        manager_card_layout.setSpacing(12)

        manager_copy = QVBoxLayout()
        manager_copy.setContentsMargins(0, 0, 0, 0)
        manager_copy.setSpacing(3)
        modengine_manager = QLabel()
        modengine_manager.setObjectName("modEngineManagerLabel")
        self.bind(modengine_manager.setText, "settings.modengine.manager")
        manager_copy.addWidget(modengine_manager)
        modengine_description = QLabel()
        modengine_description.setObjectName("modEngineDescriptionLabel")
        modengine_description.setWordWrap(True)
        self.bind(modengine_description.setText, "settings.modengine.description")
        manager_copy.addWidget(modengine_description)
        manager_card_layout.addLayout(manager_copy, 1)

        open_mod_folder = action_button(self, "common.open_folder", "openModFolderButton")
        open_mod_folder.setEnabled(False)
        manager_card_layout.addWidget(open_mod_folder, alignment=Qt.AlignmentFlag.AlignVCenter)
        modengine_layout.addWidget(manager_card)

        modengine_layout.addStretch(1)
        layout.addWidget(modengine)

        fps = section(self, "settings.fps.title")
        fps_form = QFormLayout(fps)
        current_fps = QLabel()
        self.bind(current_fps.setText, "settings.fps.current", value="60.0")
        fps_form.addRow(current_fps)
        self.fps_target = configured_spin(60, 30, 360)
        self.fps_target.setObjectName("fpsTargetSpin")
        add_form_row(self, fps_form, "settings.fps.target", self.fps_target)
        fps_form.addRow(action_button(self, "settings.fps.choose_exe", "chooseEldenRingExeButton"))
        fps_form.addRow(action_button(self, "settings.fps.restore", "restoreEldenRingExeButton"))
        layout.addWidget(fps)

        backup = section(self, "settings.backup.title")
        backup_form = QFormLayout(backup)
        self.backup_format = CompactComboBox()
        self.backup_format.setObjectName("backupFormatCombo")
        self.backup_format.addItem("ER0000.co2")
        self.backup_format.addItem("ER0000.sl2")
        add_form_row(self, backup_form, "settings.backup.format", self.backup_format)
        self.backup_folder = QLineEdit()
        self.backup_folder.setObjectName("backupFolderEdit")
        browse_backup = action_button(self, "common.browse", "browseBackupFolderButton")
        add_form_row(
            self,
            backup_form,
            "settings.backup.folder",
            horizontal_widget(self.backup_folder, browse_backup),
        )
        self.backup_method = CompactComboBox()
        self.backup_method.setObjectName("backupMethodCombo")
        for index, key in enumerate(
            ("settings.backup.fixed_interval", "settings.backup.event_monitoring")
        ):
            self.backup_method.addItem("")
            self.bind(
                lambda text, item_index=index: self.backup_method.setItemText(item_index, text),
                key,
            )
        add_form_row(self, backup_form, "settings.backup.method", self.backup_method)
        self.backup_interval = configured_spin(5, 1, 1440)
        self.backup_interval.setObjectName("backupIntervalSpin")
        add_form_row(self, backup_form, "settings.backup.interval", self.backup_interval)
        self.maximum_backups = configured_spin(20, 1, 999)
        self.maximum_backups.setObjectName("maximumBackupsSpin")
        add_form_row(self, backup_form, "settings.backup.maximum", self.maximum_backups)
        self.notification_sounds = QCheckBox()
        self.notification_sounds.setChecked(True)
        self.bind(self.notification_sounds.setText, "settings.backup.sounds")
        backup_form.addRow(self.notification_sounds)
        self.notification_volume = QSlider(Qt.Orientation.Horizontal)
        self.notification_volume.setObjectName("notificationVolumeSlider")
        self.notification_volume.setRange(0, 100)
        self.notification_volume.setValue(20)
        add_form_row(self, backup_form, "settings.backup.volume", self.notification_volume)

        shortcuts = section(self, "settings.backup.shortcuts")
        shortcuts_form = QFormLayout(shortcuts)
        self.shortcut_edits: list[QKeySequenceEdit] = []
        for key in (
            "settings.backup.shortcut_save",
            "settings.backup.shortcut_load",
            "settings.backup.shortcut_start",
            "settings.backup.shortcut_stop",
        ):
            editor = QKeySequenceEdit()
            self.shortcut_edits.append(editor)
            add_form_row(self, shortcuts_form, key, editor)
        backup_form.addRow(shortcuts)
        layout.addWidget(backup)

        layout.addStretch(1)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll)
