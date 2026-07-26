from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import QPoint, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QProgressBar,
    QTableWidgetItem,
    QVBoxLayout,
)

from sct.errors import localized_error_message
from sct.game.builds import PlayerDetails, SavedBuild
from sct.game.cheats import Cheat
from sct.game.inventory import RemovalReport
from sct.game.players import PlayerSnapshot, player_details_from_snapshot
from sct.game.recent_players import RecentPlayerRecord
from sct.game.runtime import EldenRingRuntime, GameSnapshot
from sct.items import (
    REQUIRED_ITEM_FILES,
    ItemCatalog,
    ItemDataNotFound,
    resolve_items_directory,
)
from sct.localization import TranslationService
from sct.ui.dialogs.cheats import CheatDialog
from sct.ui.dialogs.player_details import PlayerDetailsDialog
from sct.ui.dialogs.runes import RuneDialog
from sct.ui.pages.base import LocalizedPage
from sct.ui.widgets.forms import action_button, translated_table
from sct.ui.widgets.popups import SquarePopupMenu
from sct.ui.workers.current_game import CurrentGameWorker

LOCAL_ROW_COLOR = QColor("#36515e")


class CurrentGamePage(LocalizedPage):
    polling_requested = Signal(bool)
    runes_requested = Signal(int)
    cheat_requested = Signal(object, bool)
    details_requested = Signal(int)
    build_apply_requested = Signal(object, bool)
    seamless_items_remove_requested = Signal()
    shutdown_requested = Signal()

    def __init__(
            self,
            translator: TranslationService,
            runtime: EldenRingRuntime,
            *,
            start_worker_thread: bool = True,
    ) -> None:
        super().__init__(translator)
        self.runtime = runtime
        self._current_players: tuple[PlayerSnapshot, ...] = ()
        self._recent_players: tuple[RecentPlayerRecord, ...] = ()
        self._cheat_dialog: CheatDialog | None = None
        self._details_dialogs: list[PlayerDetailsDialog] = []
        self._pending_build_dialog: PlayerDetailsDialog | None = None
        self._missing_items_dialog: QMessageBox | None = None
        self._item_data_error: ItemDataNotFound | None = None
        try:
            self._item_catalog: ItemCatalog | None = ItemCatalog(
                resolve_items_directory(),
                locale=translator.locale,
            )
        except ItemDataNotFound as error:
            self._item_catalog = None
            self._item_data_error = error
        self._shutdown = False
        self._worker_thread: QThread | None = None
        self.worker = CurrentGameWorker(runtime)
        if start_worker_thread:
            self._worker_thread = QThread(self)
            self.worker.moveToThread(self._worker_thread)
            self.worker.shutdown_finished.connect(
                self._worker_thread.quit,
                Qt.ConnectionType.DirectConnection,
            )
            self._worker_thread.start()

        self.polling_requested.connect(self.worker.set_polling)
        self.runes_requested.connect(self.worker.set_runes)
        self.cheat_requested.connect(self.worker.set_cheat)
        self.details_requested.connect(self.worker.request_player_details)
        self.build_apply_requested.connect(self.worker.apply_build)
        self.seamless_items_remove_requested.connect(
            self.worker.remove_seamless_items
        )
        self.shutdown_requested.connect(self.worker.shutdown)
        self.worker.snapshot_ready.connect(self.apply_snapshot)
        self.worker.action_failed.connect(self._handle_action_error)
        self.worker.cheat_changed.connect(self._handle_cheat_changed)
        self.worker.details_ready.connect(self._open_details_dialog)
        self.worker.seamless_items_removed.connect(
            self._handle_seamless_items_removed
        )
        self.worker.action_succeeded.connect(self._handle_action_succeeded)

        layout = QVBoxLayout(self)

        current_title = QLabel()
        self.bind(current_title.setText, "current_game.current_players")
        layout.addWidget(current_title)
        self.current_table = translated_table(
            self,
            (
                "current_game.username",
                "current_game.level",
                "current_game.health",
                "current_game.runes",
            ),
            "currentPlayersTable",
        )
        self.current_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.current_table.customContextMenuRequested.connect(
            self._show_current_context_menu
        )
        layout.addWidget(self.current_table, 1)
        layout.addWidget(
            action_button(self, "current_game.loading_fix", "loadingFixButton")
        )

        recent_title = QLabel()
        self.bind(recent_title.setText, "current_game.recent_players")
        layout.addWidget(recent_title)
        self.recent_table = translated_table(
            self,
            ("current_game.username", "current_game.level", "current_game.date"),
            "recentPlayersTable",
        )
        self.recent_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.recent_table.customContextMenuRequested.connect(
            self._show_recent_context_menu
        )
        layout.addWidget(self.recent_table, 1)

    @Slot(object)
    def apply_snapshot(self, snapshot: GameSnapshot) -> None:
        self._current_players = tuple(
            sorted(
                snapshot.current_players,
                key=lambda player: (not player.is_local, player.player_num),
            )
        )
        self._recent_players = snapshot.recent_players
        self._render_current_players()
        self._render_recent_players()

    def current_action_keys(self, row: int, column: int) -> tuple[str, ...]:
        if not 0 <= row < len(self._current_players):
            return ()
        player = self._current_players[row]
        if player.is_local and column in {0, 1}:
            return (
                "current_game.actions.details_build",
                "current_game.actions.cheats",
            )
        if player.is_local and column == 3:
            return ("current_game.actions.edit_runes",)
        if not player.is_local and column in {0, 1}:
            return ("current_game.actions.details",)
        return ()

    def recent_action_keys(self, row: int, column: int) -> tuple[str, ...]:
        if 0 <= row < len(self._recent_players) and column in {0, 1}:
            return ("current_game.actions.details",)
        return ()

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        if self._worker_thread is None:
            self.worker.shutdown()
            return
        self.shutdown_requested.emit()
        if not self._worker_thread.wait(3000):
            self._worker_thread.quit()
            self._worker_thread.wait(1000)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._shutdown:
            self.polling_requested.emit(True)

    def hideEvent(self, event: QHideEvent) -> None:
        self.polling_requested.emit(False)
        super().hideEvent(event)

    def _render_current_players(self) -> None:
        self.current_table.setRowCount(len(self._current_players))
        for row, player in enumerate(self._current_players):
            values = (
                player.name,
                str(player.level),
                "",
                str(player.runes) if player.runes is not None else "",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if player.is_local:
                    item.setBackground(LOCAL_ROW_COLOR)
                    item.setData(Qt.ItemDataRole.UserRole, "local")
                self.current_table.setItem(row, column, item)
            progress = QProgressBar()
            progress.setObjectName("healthProgress")
            progress.setRange(0, 100)
            percentage = (
                max(0, min(100, round(player.hp / player.max_hp * 100)))
                if player.max_hp > 0
                else 0
            )
            progress.setValue(percentage)
            progress.setFormat(f"{percentage}%")
            self.current_table.setCellWidget(row, 2, progress)

    def _render_recent_players(self) -> None:
        self.recent_table.setRowCount(len(self._recent_players))
        for row, record in enumerate(self._recent_players):
            values = (
                record.player.name,
                str(record.player.level),
                self._format_date(record.last_seen),
            )
            for column, value in enumerate(values):
                self.recent_table.setItem(row, column, QTableWidgetItem(value))

    @staticmethod
    def _format_date(value: str) -> str:
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return value

    def _show_current_context_menu(self, position: QPoint) -> None:
        index = self.current_table.indexAt(position)
        if not index.isValid():
            return
        keys = self.current_action_keys(index.row(), index.column())
        self._show_context_menu(
            keys,
            self.current_table.viewport().mapToGlobal(position),
            index.row(),
            recent=False,
        )

    def _show_recent_context_menu(self, position: QPoint) -> None:
        index = self.recent_table.indexAt(position)
        if not index.isValid():
            return
        keys = self.recent_action_keys(index.row(), index.column())
        self._show_context_menu(
            keys,
            self.recent_table.viewport().mapToGlobal(position),
            index.row(),
            recent=True,
        )

    def _show_context_menu(
            self,
            keys: tuple[str, ...],
            global_position: QPoint,
            row: int,
            *,
            recent: bool,
    ) -> None:
        if not keys:
            return
        menu = SquarePopupMenu(self)
        for key in keys:
            action = menu.addAction(self.translator.translate(key))
            if key == "current_game.actions.cheats":
                action.triggered.connect(self._open_cheat_dialog)
            elif key == "current_game.actions.edit_runes":
                action.triggered.connect(lambda _checked=False, value=row: self._open_rune_dialog(value))
            elif key in {
                "current_game.actions.details",
                "current_game.actions.details_build",
            }:
                if recent:
                    action.triggered.connect(
                        lambda _checked=False, value=row: self._open_recent_details(
                            value
                        )
                    )
                else:
                    action.triggered.connect(
                        lambda _checked=False, value=row: self._request_details(value)
                    )
        menu.popup(global_position)

    def _open_rune_dialog(self, row: int) -> None:
        if not 0 <= row < len(self._current_players):
            return
        player = self._current_players[row]
        if not player.is_local or player.runes is None:
            return
        dialog = RuneDialog(self.translator, player.runes, self)
        if dialog.exec() == RuneDialog.DialogCode.Accepted:
            self.runes_requested.emit(dialog.rune_value())

    def _open_cheat_dialog(self) -> None:
        if self._cheat_dialog is not None:
            self._cheat_dialog.raise_()
            self._cheat_dialog.activateWindow()
            return
        dialog = CheatDialog(
            self.translator,
            self.runtime.enabled_cheats(),
            self.cheat_requested.emit,
            self,
            on_remove_items=self._confirm_remove_seamless_items,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.destroyed.connect(lambda _object=None: self._clear_cheat_dialog())
        self._cheat_dialog = dialog
        dialog.show()

    def _clear_cheat_dialog(self) -> None:
        self._cheat_dialog = None

    def _request_details(self, row: int) -> None:
        if 0 <= row < len(self._current_players):
            self.details_requested.emit(self._current_players[row].player_num)

    def _open_recent_details(self, row: int) -> None:
        if not 0 <= row < len(self._recent_players):
            return
        record = self._recent_players[row]
        details = record.details or player_details_from_snapshot(record.player)
        self._open_details_dialog(details)

    @Slot(object)
    def _open_details_dialog(self, details: PlayerDetails) -> None:
        if self._item_catalog is None:
            self._show_missing_item_data_message()
            return
        dialog = PlayerDetailsDialog(
            self.translator,
            details,
            self._item_catalog,
            self,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.apply_requested.connect(
            lambda build, equipment_only, source=dialog: self._apply_build(
                source,
                build,
                equipment_only,
            )
        )
        dialog.destroyed.connect(
            lambda _object=None, value=dialog: self._forget_details_dialog(value)
        )
        self._details_dialogs.append(dialog)
        dialog.show()

    def _show_missing_item_data_message(self) -> None:
        if self._missing_items_dialog is not None:
            self._missing_items_dialog.raise_()
            self._missing_items_dialog.activateWindow()
            return
        dialog = self._create_missing_item_data_message()
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.destroyed.connect(
            lambda _object=None: self._clear_missing_item_data_message()
        )
        self._missing_items_dialog = dialog
        dialog.show()

    def _create_missing_item_data_message(self) -> QMessageBox:
        missing_files = (
            self._item_data_error.missing_files
            if self._item_data_error is not None
            else REQUIRED_ITEM_FILES
        )
        file_list = "\n".join(f"• {filename}" for filename in missing_files)
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(
            self.translator.translate("player_details.item_data_missing_title")
        )
        dialog.setText(
            self.translator.translate(
                (
                    "player_details.item_data_missing"
                    if getattr(sys, "frozen", False)
                    else "player_details.item_data_missing_development"
                ),
                files=file_list,
            )
        )
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.button(QMessageBox.StandardButton.Ok).setText(
            self.translator.translate("common.ok")
        )
        return dialog

    def _clear_missing_item_data_message(self) -> None:
        self._missing_items_dialog = None

    def _forget_details_dialog(self, dialog: PlayerDetailsDialog) -> None:
        if dialog in self._details_dialogs:
            self._details_dialogs.remove(dialog)
        if self._pending_build_dialog is dialog:
            self._pending_build_dialog = None

    def _apply_build(
            self,
            dialog: PlayerDetailsDialog,
            build: SavedBuild,
            equipment_only: bool,
    ) -> None:
        self._pending_build_dialog = dialog
        self.build_apply_requested.emit(build, equipment_only)

    def _confirm_remove_seamless_items(self) -> None:
        dialog = self._create_remove_seamless_items_confirmation()
        if dialog.exec() == QMessageBox.StandardButton.Yes:
            self.seamless_items_remove_requested.emit()

    def _create_remove_seamless_items_confirmation(self) -> QMessageBox:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(
            self.translator.translate("cheats.remove_confirm_title")
        )
        dialog.setText(self.translator.translate("cheats.remove_confirm_message"))
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
        return dialog

    @Slot(object)
    def _handle_seamless_items_removed(self, report: RemovalReport) -> None:
        QMessageBox.information(
            self,
            self.translator.translate("cheats.remove_success_title"),
            self.translator.translate(
                "cheats.remove_success_message",
                count=report.calls_made,
            ),
        )

    @Slot(str)
    def _handle_action_succeeded(self, action: str) -> None:
        if action != "build_applied":
            return
        dialog = self._pending_build_dialog
        self._pending_build_dialog = None
        if dialog is not None:
            dialog.mark_applied()
        QMessageBox.information(
            self,
            self.translator.translate("player_details.success_title"),
            self.translator.translate("player_details.success_message"),
        )

    @Slot(object, bool)
    def _handle_cheat_changed(self, cheat: Cheat, enabled: bool) -> None:
        if self._cheat_dialog is not None:
            self._cheat_dialog.set_cheat_state(cheat, enabled)

    @Slot(object)
    def _handle_action_error(self, error: BaseException) -> None:
        self._pending_build_dialog = None
        if self._cheat_dialog is not None:
            for cheat in Cheat:
                self._cheat_dialog.set_cheat_state(
                    cheat,
                    cheat in self.runtime.enabled_cheats(),
                )
        QMessageBox.critical(
            self,
            self.translator.translate("current_game.error_title"),
            localized_error_message(self.translator, error),
        )
