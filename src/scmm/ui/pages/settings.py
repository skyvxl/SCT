from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from scmm.localization import TranslationService
from scmm.resource_loader import load_optional_icon, optional_resource_path
from scmm.settings import AppSettings, SettingsStore
from scmm.shortcuts import deserialize_key_sequence, serialize_key_sequence
from scmm.steam import SteamService
from scmm.ui.pages.base import LocalizedPage
from scmm.ui.widgets import CompactComboBox
from scmm.ui.widgets.forms import action_button, add_form_row, section

LOGGER = logging.getLogger("scmm.ui.settings")


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
    game_directory_changed = Signal(str)

    def __init__(
        self,
        translator: TranslationService,
        settings_store: SettingsStore,
        steam_service: SteamService,
    ) -> None:
        super().__init__(translator)
        self.settings_store = settings_store
        self.steam_service = steam_service
        self._loading_settings = True
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
        self.browse_game_button = action_button(self, "common.browse", "browseGameButton")
        add_form_row(
            self,
            game_form,
            "settings.game_path.label",
            horizontal_widget(self.game_path_edit, self.browse_game_button),
        )
        layout.addWidget(game_path)

        launcher = section(self, "settings.launcher.title")
        launcher_form = QFormLayout(launcher)
        self.launcher_edit = QLineEdit()
        self.launcher_edit.setObjectName("seamlessExeEdit")
        self.browse_launcher_button = action_button(
            self,
            "common.browse",
            "browseLauncherButton",
        )
        add_form_row(
            self,
            launcher_form,
            "settings.launcher.executable",
            horizontal_widget(self.launcher_edit, self.browse_launcher_button),
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
        self.browse_steam_button = action_button(self, "common.browse", "browseSteamButton")
        self.detect_steam_button = action_button(
            self,
            "settings.steam.auto_detect",
            "detectSteamButton",
        )
        add_form_row(
            self,
            steam_form,
            "settings.steam.executable",
            horizontal_widget(
                self.steam_edit,
                self.browse_steam_button,
                self.detect_steam_button,
            ),
        )
        self.steam_status = QLabel()
        self.steam_status.setObjectName("steamStatusLabel")
        self.steam_status.setProperty("role", "danger")
        steam_form.addRow(self.steam_status)
        self.silent_steam = QCheckBox()
        self.silent_steam.setChecked(False)
        self.bind(self.silent_steam.setText, "settings.steam.silent")
        steam_form.addRow(self.silent_steam)
        self.steam_id_combo = CompactComboBox()
        self.steam_id_combo.setObjectName("steamIdCombo")
        self.steam_id_combo.addItem("", "")
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
        self.backup_format.addItem("ER0000.co2", "ER0000.co2")
        self.backup_format.addItem("ER0000.sl2", "ER0000.sl2")
        add_form_row(self, backup_form, "settings.backup.format", self.backup_format)
        self.backup_folder = QLineEdit()
        self.backup_folder.setObjectName("backupFolderEdit")
        self.browse_backup_button = action_button(
            self,
            "common.browse",
            "browseBackupFolderButton",
        )
        self.open_backup_button = action_button(
            self,
            "common.open",
            "openBackupFolderButton",
        )
        add_form_row(
            self,
            backup_form,
            "settings.backup.folder",
            horizontal_widget(
                self.backup_folder,
                self.browse_backup_button,
                self.open_backup_button,
            ),
        )
        self.backup_method = CompactComboBox()
        self.backup_method.setObjectName("backupMethodCombo")
        for index, key in enumerate(
            ("settings.backup.fixed_interval", "settings.backup.event_monitoring")
        ):
            self.backup_method.addItem("", index)
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

        self.notification_sound = QSoundEffect(self)
        notification_path = optional_resource_path("save_notification.wav")
        if notification_path is not None:
            self.notification_sound.setSource(QUrl.fromLocalFile(str(notification_path)))

        self._apply_settings(self.settings_store.ensure_exists())
        self._connect_controls()
        self._loading_settings = False
        self._refresh_steam_profiles()
        self._refresh_steam_status()
        self.steam_status_timer = QTimer(self)
        self.steam_status_timer.setInterval(2000)
        self.steam_status_timer.timeout.connect(self._refresh_steam_status)
        self.steam_status_timer.start()

    def _apply_settings(self, settings: AppSettings) -> None:
        self.language_combo.setCurrentIndex(
            max(self.language_combo.findData(settings.preferred_language), 0)
        )
        self.game_path_edit.setText(settings.mod_path)
        self.launcher_edit.setText(settings.game_exe_path)
        self.launcher_auto_update.setChecked(settings.auto_check_updates)
        self.steam_edit.setText(settings.steam_exe_path)
        self.silent_steam.setChecked(settings.run_steam_silently)
        self.fps_target.setValue(settings.fps_target)
        self.backup_format.setCurrentIndex(
            max(
                self.backup_format.findData(settings.save_file_type),
                0,
            )
        )
        self.backup_folder.setText(settings.backup_directory)
        self.backup_method.setCurrentIndex(
            max(
                self.backup_method.findData(settings.backup_method),
                0,
            )
        )
        self.backup_interval.setValue(settings.auto_backup_interval)
        self.maximum_backups.setValue(settings.max_backups)
        self.notification_sounds.setChecked(settings.enable_sounds)
        self.notification_volume.setValue(settings.sound_volume)
        shortcut_values = (
            settings.save_backup_key,
            settings.load_backup_key,
            settings.start_auto_backup_key,
            settings.stop_auto_backup_key,
        )
        for editor, value in zip(self.shortcut_edits, shortcut_values, strict=True):
            editor.setKeySequence(deserialize_key_sequence(value))
        self._update_backup_open_button(settings.backup_directory)

    def _connect_controls(self) -> None:
        self.language_combo.currentIndexChanged.connect(
            lambda _index: self._persist(preferred_language=str(self.language_combo.currentData()))
        )
        self.browse_game_button.clicked.connect(self._browse_game_directory)
        self.game_path_edit.editingFinished.connect(self._save_game_directory)
        self.browse_launcher_button.clicked.connect(self._browse_launcher)
        self.launcher_edit.editingFinished.connect(
            lambda: self._persist(game_exe_path=self.launcher_edit.text().strip())
        )
        self.launcher_auto_update.toggled.connect(
            lambda checked: self._persist(auto_check_updates=checked)
        )
        self.browse_steam_button.clicked.connect(self._browse_steam)
        self.detect_steam_button.clicked.connect(self._detect_steam)
        self.steam_edit.editingFinished.connect(self._save_steam_path)
        self.silent_steam.toggled.connect(lambda checked: self._persist(run_steam_silently=checked))
        self.steam_id_combo.currentIndexChanged.connect(
            lambda _index: self._persist(steam_id=str(self.steam_id_combo.currentData() or ""))
        )
        self.fps_target.valueChanged.connect(lambda value: self._persist(fps_target=value))
        self.backup_format.currentIndexChanged.connect(
            lambda _index: self._persist(save_file_type=str(self.backup_format.currentData()))
        )
        self.browse_backup_button.clicked.connect(self._browse_backup_directory)
        self.open_backup_button.clicked.connect(self._open_backup_directory)
        self.backup_folder.textChanged.connect(self._update_backup_open_button)
        self.backup_folder.editingFinished.connect(
            lambda: self._persist(backup_directory=self.backup_folder.text().strip())
        )
        self.backup_method.currentIndexChanged.connect(
            lambda _index: self._persist(backup_method=int(self.backup_method.currentData()))
        )
        self.backup_interval.valueChanged.connect(
            lambda value: self._persist(auto_backup_interval=value)
        )
        self.maximum_backups.valueChanged.connect(lambda value: self._persist(max_backups=value))
        self.notification_sounds.toggled.connect(
            lambda checked: self._persist(enable_sounds=checked)
        )
        self.notification_volume.valueChanged.connect(
            lambda value: self._persist(sound_volume=value)
        )
        self.notification_volume.sliderReleased.connect(self._preview_notification_sound)
        shortcut_fields = (
            "save_backup_key",
            "load_backup_key",
            "start_auto_backup_key",
            "stop_auto_backup_key",
        )
        for editor, field_name in zip(self.shortcut_edits, shortcut_fields, strict=True):
            editor.keySequenceChanged.connect(
                lambda sequence, name=field_name: self._persist(
                    **{name: serialize_key_sequence(sequence)}
                )
            )

    def _persist(self, **changes: object) -> None:
        if self._loading_settings:
            return
        try:
            self.settings_store.update(**changes)
        except OSError:
            LOGGER.exception("Unable to save manager settings")

    def _browse_game_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self.translator.translate("settings.game_path.dialog"),
            self.game_path_edit.text().strip(),
        )
        if not selected:
            return
        self.game_path_edit.setText(selected)
        candidate_launcher = Path(selected) / "ersc_launcher.exe"
        if not self.launcher_edit.text().strip() and candidate_launcher.is_file():
            self.launcher_edit.setText(str(candidate_launcher))
            self._persist(game_exe_path=str(candidate_launcher))
        self._save_game_directory()

    def _save_game_directory(self) -> None:
        path = self.game_path_edit.text().strip()
        self._persist(mod_path=path)
        self.game_directory_changed.emit(path)

    def _browse_launcher(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            self.translator.translate("settings.launcher.dialog"),
            self.launcher_edit.text().strip() or self.game_path_edit.text().strip(),
            "Executable (*.exe)",
        )
        if selected:
            self.launcher_edit.setText(selected)
            self._persist(game_exe_path=selected)

    def _browse_steam(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            self.translator.translate("settings.steam.dialog"),
            self.steam_edit.text().strip(),
            "Steam (Steam.exe);;Executable (*.exe)",
        )
        if selected:
            self.steam_edit.setText(selected)
            self._save_steam_path()

    def _detect_steam(self) -> None:
        detected = self.steam_service.detect_executable()
        if detected is None:
            QMessageBox.warning(
                self,
                self.translator.translate("settings.steam.not_found_title"),
                self.translator.translate("settings.steam.not_found_message"),
            )
            return
        self.steam_edit.setText(str(detected))
        self._save_steam_path()
        QMessageBox.information(
            self,
            self.translator.translate("settings.steam.detected_title"),
            self.translator.translate("settings.steam.detected_message", path=detected),
        )

    def _save_steam_path(self) -> None:
        self._persist(steam_exe_path=self.steam_edit.text().strip())
        self._refresh_steam_profiles()
        self._refresh_steam_status()

    def _refresh_steam_profiles(self) -> None:
        selected_id = self.settings_store.load().steam_id
        executable = self.steam_edit.text().strip()
        profiles = self.steam_service.profiles(executable) if executable else ()
        profiles = tuple(sorted(profiles, key=lambda profile: not profile.most_recent))
        self.steam_id_combo.blockSignals(True)
        self.steam_id_combo.clear()
        self.steam_id_combo.addItem(
            self.translator.translate("settings.steam.choose_id"),
            "",
        )
        for profile in profiles:
            self.steam_id_combo.addItem(profile.display_name, profile.steam_id)
        selected_index = self.steam_id_combo.findData(selected_id)
        if selected_id and selected_index < 0:
            self.steam_id_combo.addItem(f"Steam ID {selected_id}", selected_id)
            selected_index = self.steam_id_combo.count() - 1
        self.steam_id_combo.setCurrentIndex(max(selected_index, 0))
        self.steam_id_combo.blockSignals(False)

    def _refresh_steam_status(self) -> None:
        running = self.steam_service.is_running()
        self.steam_status.setText(
            self.translator.translate(
                "settings.steam.running" if running else "settings.steam.not_running"
            )
        )
        self.steam_status.setProperty("role", "success" if running else "danger")
        style = self.steam_status.style()
        style.unpolish(self.steam_status)
        style.polish(self.steam_status)

    def _browse_backup_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self.translator.translate("settings.backup.dialog"),
            self.backup_folder.text().strip(),
        )
        if selected:
            self.backup_folder.setText(selected)
            self._persist(backup_directory=selected)

    def _open_backup_directory(self) -> None:
        path = Path(self.backup_folder.text().strip())
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _update_backup_open_button(self, value: str) -> None:
        path = Path(value.strip()) if value.strip() else None
        self.open_backup_button.setVisible(path is not None)
        self.open_backup_button.setEnabled(path is not None and path.is_dir())

    def _preview_notification_sound(self) -> None:
        if not self.notification_sounds.isChecked():
            return
        self.notification_sound.setVolume(self.notification_volume.value() / 100)
        if self.notification_sound.source().isEmpty():
            QApplication.beep()
        else:
            self.notification_sound.play()
