from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Slot
from PySide6.QtGui import QAction, QPixmap, QResizeEvent, QShowEvent
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from sct.backup_controller import BackupController
from sct.backup_manager import BackupManager
from sct.backups import BackupEntry
from sct.errors import localized_error_message
from sct.global_hotkeys import GlobalHotkeyManager
from sct.localization import TranslationService
from sct.resource_loader import optional_resource_path
from sct.settings import SettingsStore
from sct.shortcuts import deserialize_key_sequence
from sct.ui.pages.base import LocalizedPage
from sct.ui.widgets.forms import action_button, translated_table
from sct.ui.widgets.popups import SquarePopupMenu

LOGGER = logging.getLogger("sct.ui.backups")


class BackupsPage(LocalizedPage):
    def __init__(
            self,
            translator: TranslationService,
            manager: BackupManager,
            settings_store: SettingsStore,
    ) -> None:
        super().__init__(translator)
        self._settings_store = settings_store
        self._controller = BackupController(manager, self)
        self._hotkeys = GlobalHotkeyManager(self)
        self._busy = False
        self._auto_running = False
        self._sounds: dict[str, QSoundEffect] = {}
        self._preview_source: QPixmap | None = None

        layout = QVBoxLayout(self)
        self.preview_label = QLabel()
        self.preview_label.setObjectName("backupScreenshotPreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview_label, 2)
        self.status_label = QLabel()
        self.status_label.setObjectName("backupStatusLabel")
        layout.addWidget(self.status_label)

        pinned_title = QLabel()
        self.bind(pinned_title.setText, "backups.pinned")
        layout.addWidget(pinned_title)
        self.pinned_table = translated_table(
            self,
            ("backups.name", "backups.date"),
            "pinnedBackupsTable",
        )
        layout.addWidget(self.pinned_table, 1)

        regular_title = QLabel()
        self.bind(regular_title.setText, "backups.regular")
        layout.addWidget(regular_title)
        self.regular_table = translated_table(
            self,
            ("backups.name", "backups.date"),
            "regularBackupsTable",
        )
        layout.addWidget(self.regular_table, 1)

        buttons = QGridLayout()
        self.save_button = action_button(self, "backups.save", "saveBackupButton")
        self.load_button = action_button(self, "backups.load", "loadBackupButton")
        self.refresh_button = action_button(
            self,
            "common.refresh",
            "refreshBackupsButton",
        )
        self.delete_button = action_button(self, "common.delete", "deleteBackupButton")
        self.start_button = action_button(self, "backups.start", "startAutoBackupButton")
        self.stop_button = action_button(self, "backups.stop", "stopAutoBackupButton")
        for column, button in enumerate(
                (self.save_button, self.load_button, self.refresh_button, self.delete_button)
        ):
            buttons.addWidget(button, 0, column)
        buttons.addWidget(self.start_button, 1, 0, 1, 2)
        buttons.addWidget(self.stop_button, 1, 2, 1, 2)
        layout.addLayout(buttons)

        self._configure_table(self.pinned_table)
        self._configure_table(self.regular_table)
        self._load_sounds()
        self._connect_actions()
        self._connect_controller()
        self._set_auto_state(False)
        self._update_buttons()
        self.reload_hotkeys()
        self.translator.language_changed.connect(
            lambda _locale: self._set_auto_state(self._auto_running)
        )

    def refresh(self) -> None:
        self._controller.refresh()

    def reload_hotkeys(self) -> None:
        settings = self._settings_store.load()
        bindings = {
            "save": (
                deserialize_key_sequence(settings.save_backup_key),
                self._controller.create_backup,
            ),
            "load": (
                deserialize_key_sequence(settings.load_backup_key),
                lambda: self._controller.restore_backup(self._selected_name()),
            ),
            "start": (
                deserialize_key_sequence(settings.start_auto_backup_key),
                self._controller.start_auto_backup,
            ),
            "stop": (
                deserialize_key_sequence(settings.stop_auto_backup_key),
                self._controller.stop_auto_backup,
            ),
        }
        try:
            self._hotkeys.register(bindings)
        except Exception as error:
            LOGGER.exception("Unable to register backup hotkeys")
            self._show_error(error)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._render_preview()

    def shutdown(self) -> None:
        self._hotkeys.shutdown()
        self._controller.shutdown()

    def _configure_table(self, table: QTableWidget) -> None:
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.itemSelectionChanged.connect(
            lambda source=table: self._selection_changed(source)
        )
        table.customContextMenuRequested.connect(
            lambda position, source=table: self._show_context_menu(source, position)
        )

    def _connect_actions(self) -> None:
        self.save_button.clicked.connect(self._controller.create_backup)
        self.load_button.clicked.connect(self._restore_selected)
        self.refresh_button.clicked.connect(self.refresh)
        self.delete_button.clicked.connect(self._delete_selected)
        self.start_button.clicked.connect(self._controller.start_auto_backup)
        self.stop_button.clicked.connect(self._controller.stop_auto_backup)

    def _connect_controller(self) -> None:
        self._controller.backups_loaded.connect(self._populate_tables)
        self._controller.screenshot_loaded.connect(self._show_screenshot)
        self._controller.backup_created.connect(
            lambda _entry: self._play_sound("save")
        )
        self._controller.backup_restored.connect(self._backup_restored)
        self._controller.auto_state_changed.connect(self._set_auto_state)
        self._controller.operation_failed.connect(self._show_error)
        self._controller.busy_changed.connect(self._set_busy)

    @Slot(object)
    def _populate_tables(self, entries: object) -> None:
        selected = self._selected_name()
        all_entries = tuple(entries)
        self._fill_table(
            self.pinned_table,
            tuple(entry for entry in all_entries if entry.pinned),
        )
        self._fill_table(
            self.regular_table,
            tuple(entry for entry in all_entries if not entry.pinned),
        )
        if selected:
            self._select_name(selected)
        self._update_buttons()

    def _fill_table(
            self,
            table: QTableWidget,
            entries: tuple[BackupEntry, ...],
    ) -> None:
        table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            name_item = QTableWidgetItem(entry.name)
            name_item.setData(Qt.ItemDataRole.UserRole, entry.name)
            date_item = QTableWidgetItem(entry.created_at.strftime("%d.%m.%Y %H:%M:%S"))
            date_item.setData(Qt.ItemDataRole.UserRole, entry.name)
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, date_item)

    def _selection_changed(self, source: QTableWidget) -> None:
        if not source.selectedItems():
            if self._selected_name() is None:
                self._clear_preview()
            self._update_buttons()
            return
        other = (
            self.regular_table
            if source is self.pinned_table
            else self.pinned_table
        )
        other.clearSelection()
        name = self._selected_name()
        if name is not None:
            self._controller.load_screenshot(name)
        self._update_buttons()

    @Slot(str, object)
    def _show_screenshot(self, name: str, payload: object) -> None:
        if name != self._selected_name():
            return
        if not isinstance(payload, bytes):
            self._clear_preview()
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(payload, "PNG"):
            self._clear_preview()
            return
        self._preview_source = pixmap
        self._render_preview()

    def _render_preview(self) -> None:
        if self._preview_source is None:
            self.preview_label.clear()
            return
        size = self.preview_label.size().boundedTo(QSize(720, 405))
        if size.width() <= 0 or size.height() <= 0:
            return
        self.preview_label.setPixmap(
            self._preview_source.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _clear_preview(self) -> None:
        self._preview_source = None
        self.preview_label.clear()

    def _selected_name(self) -> str | None:
        for table in (self.pinned_table, self.regular_table):
            selected = table.selectedItems()
            if selected:
                value = selected[0].data(Qt.ItemDataRole.UserRole)
                return str(value) if value else selected[0].text()
        return None

    def _select_name(self, name: str) -> None:
        for table in (self.pinned_table, self.regular_table):
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == name:
                    table.selectRow(row)
                    return

    def _selected_is_pinned(self) -> bool:
        return bool(self.pinned_table.selectedItems())

    def _restore_selected(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        if self._confirm(
                "backups.restore_confirm_title",
                "backups.restore_confirm_message",
                name=name,
        ):
            self._controller.restore_backup(name)

    def _delete_selected(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        if self._confirm(
                "backups.delete_confirm_title",
                "backups.delete_confirm_message",
                name=name,
        ):
            self._controller.delete_backup(name)

    def _show_context_menu(self, table: QTableWidget, position) -> None:
        item = table.itemAt(position)
        if item is None:
            return
        table.selectRow(item.row())
        name = self._selected_name()
        if name is None:
            return
        pinned = table is self.pinned_table
        menu = SquarePopupMenu(self)
        pin_action = QAction(
            self.translator.translate(
                "backups.unpin" if pinned else "backups.pin"
            ),
            menu,
        )
        rename_action = QAction(
            self.translator.translate("backups.rename"),
            menu,
        )
        pin_action.triggered.connect(
            lambda: self._controller.set_backup_pinned(name, not pinned)
        )
        rename_action.triggered.connect(lambda: self._rename(name))
        menu.addAction(pin_action)
        menu.addAction(rename_action)
        menu.exec(table.viewport().mapToGlobal(position))

    def _rename(self, name: str) -> None:
        value, accepted = QInputDialog.getText(
            self,
            self.translator.translate("backups.rename_title"),
            self.translator.translate("backups.rename_prompt"),
            text=Path(name).stem,
        )
        if accepted and value.strip():
            self._controller.rename_backup(name, value.strip())

    def _confirm(self, title_key: str, message_key: str, **params: object) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(self.translator.translate(title_key))
        dialog.setText(self.translator.translate(message_key, **params))
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setEscapeButton(QMessageBox.StandardButton.No)
        dialog.button(QMessageBox.StandardButton.Yes).setText(
            self.translator.translate("common.yes")
        )
        dialog.button(QMessageBox.StandardButton.No).setText(
            self.translator.translate("common.no")
        )
        return dialog.exec() == QMessageBox.StandardButton.Yes

    @Slot(str)
    def _backup_restored(self, name: str) -> None:
        self._play_sound("load")
        QMessageBox.information(
            self,
            self.translator.translate("backups.restore_success_title"),
            self.translator.translate("backups.restore_success_message", name=name),
        )

    @Slot(bool)
    def _set_auto_state(self, running: bool) -> None:
        changed = self._auto_running != running
        self._auto_running = running
        self.status_label.setText(
            self.translator.translate(
                "backups.status_running" if running else "backups.status_stopped"
            )
        )
        self.status_label.setProperty("role", "success" if running else "danger")
        style = self.status_label.style()
        style.unpolish(self.status_label)
        style.polish(self.status_label)
        if changed:
            self._play_sound("start" if running else "stop")
        self._update_buttons()

    @Slot(bool)
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_buttons()

    def _update_buttons(self) -> None:
        selected = self._selected_name() is not None
        self.save_button.setEnabled(not self._busy)
        self.load_button.setEnabled(selected and not self._busy)
        self.refresh_button.setEnabled(not self._busy)
        self.delete_button.setEnabled(selected and not self._busy)
        self.start_button.setEnabled(not self._busy and not self._auto_running)
        self.stop_button.setEnabled(not self._busy and self._auto_running)

    @Slot(object)
    def _show_error(self, error: object) -> None:
        QMessageBox.warning(
            self,
            self.translator.translate("backups.error_title"),
            localized_error_message(
                self.translator,
                error if isinstance(error, BaseException) else RuntimeError(str(error)),
                fallback_key="errors.backup_operation_failed",
            ),
        )

    def _load_sounds(self) -> None:
        files = {
            "save": "save_notification.wav",
            "load": "load_notification.wav",
            "start": "start_auto_save_notification.wav",
            "stop": "stop_auto_save_notification.wav",
        }
        for name, filename in files.items():
            sound = QSoundEffect(self)
            path = optional_resource_path("audios", filename)
            if path is not None:
                sound.setSource(QUrl.fromLocalFile(str(path)))
            self._sounds[name] = sound

    def _play_sound(self, name: str) -> None:
        settings = self._settings_store.load()
        if not settings.enable_sounds:
            return
        sound = self._sounds[name]
        sound.setVolume(settings.sound_volume / 100)
        if sound.source().isEmpty():
            QApplication.beep()
        else:
            sound.play()
