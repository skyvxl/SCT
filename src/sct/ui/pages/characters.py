from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from PySide6.QtCore import QByteArray, QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QDrag, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from sct.characters import (
    ArchiveCharacter,
    CharacterArchiveRepository,
    CharacterManagerService,
    LoadedSave,
    archive_from_slot,
    archive_identity,
    clear_slot,
    find_character_stats,
    install_archived_character,
    replace_document_slot,
    update_character_stats,
)
from sct.errors import LocalizedError, localized_error_message
from sct.localization import TranslationService
from sct.settings import SettingsStore
from sct.ui.dialogs.character_stats import CharacterStatsDialog
from sct.ui.pages.base import LocalizedPage
from sct.ui.widgets.forms import action_button
from sct.ui.widgets.popups import SquarePopupMenu

LOGGER = logging.getLogger("sct.ui.characters")
CHARACTER_MIME = "application/x-sct-character"
INACTIVE_COLOR = QColor("#808080")


@dataclass(frozen=True, slots=True)
class CharacterReference:
    kind: str
    row: int


class CharacterTable(QTableWidget):
    character_dropped = Signal(str, int, int, bool)

    def __init__(self, kind: str) -> None:
        super().__init__(0, 3)
        self.kind = kind
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        row = self.currentRow()
        if row < 0:
            return
        mime = QMimeData()
        mime.setData(CHARACTER_MIME, QByteArray(f"{self.kind}:{row}".encode("ascii")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        default = (
            Qt.DropAction.CopyAction
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
            else Qt.DropAction.MoveAction
        )
        drag.exec(
            Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
            default,
        )

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(CHARACTER_MIME):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(CHARACTER_MIME):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        raw = bytes(event.mimeData().data(CHARACTER_MIME)).decode("ascii", errors="ignore")
        try:
            source_kind, raw_row = raw.split(":", 1)
            source_row = int(raw_row)
        except (TypeError, ValueError):
            event.ignore()
            return
        target_row = self.rowAt(int(event.position().y()))
        copy = bool(
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        )
        event.setDropAction(
            Qt.DropAction.CopyAction if copy else Qt.DropAction.MoveAction
        )
        self.character_dropped.emit(source_kind, source_row, target_row, copy)
        event.accept()


class CharactersPage(LocalizedPage):
    def __init__(
            self,
            translator: TranslationService,
            settings_store: SettingsStore,
            *,
            service: CharacterManagerService | None = None,
            archive_repository: CharacterArchiveRepository | None = None,
    ) -> None:
        super().__init__(translator)
        self._settings_store = settings_store
        self._service = service or CharacterManagerService(settings_store)
        self._archive_repository = archive_repository or CharacterArchiveRepository()
        self._archive: tuple[ArchiveCharacter, ...] = ()
        self._loaded_save: LoadedSave | None = None
        self._clipboard: CharacterReference | None = None
        self._changing_selection = False

        layout = QVBoxLayout(self)
        instructions_title = QLabel()
        instructions_title.setProperty("role", "accent")
        instructions_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bind(instructions_title.setText, "characters.instructions_title")
        layout.addWidget(instructions_title)
        instructions = QLabel()
        instructions.setWordWrap(True)
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bind(instructions.setText, "characters.instructions")
        layout.addWidget(instructions)

        archive_title = QLabel()
        self.bind(archive_title.setText, "characters.archive")
        layout.addWidget(archive_title)
        self.archive_table = self._create_table("archive", "archivedCharactersTable")
        layout.addWidget(self.archive_table, 1)
        archive_buttons = QGridLayout()
        self.load_archive_button = action_button(
            self,
            "characters.load_archive",
            "loadArchiveButton",
        )
        self.delete_archive_button = action_button(
            self,
            "common.delete",
            "deleteArchiveButton",
        )
        archive_buttons.addWidget(self.load_archive_button, 0, 0)
        archive_buttons.addWidget(self.delete_archive_button, 0, 1)
        layout.addLayout(archive_buttons)

        game_title = QLabel()
        self.bind(game_title.setText, "characters.game_save")
        layout.addWidget(game_title)
        self.game_table = self._create_table("game", "gameCharactersTable")
        self.game_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.game_table.customContextMenuRequested.connect(self._show_game_context_menu)
        layout.addWidget(self.game_table, 1)
        game_buttons = QGridLayout()
        self.load_game_button = action_button(
            self,
            "characters.load_game",
            "loadGameSaveButton",
        )
        self.delete_game_button = action_button(
            self,
            "common.delete",
            "deleteGameCharacterButton",
        )
        game_buttons.addWidget(self.load_game_button, 0, 0)
        game_buttons.addWidget(self.delete_game_button, 0, 1)
        layout.addLayout(game_buttons)

        self._shortcuts: list[QShortcut] = []
        self._add_shortcut(QKeySequence.StandardKey.Copy, self.copy_selection)
        self._add_shortcut(QKeySequence.StandardKey.Paste, self.paste_selection)
        self._add_shortcut(QKeySequence(Qt.Key.Key_Delete), self.delete_selection)
        self.load_archive_button.clicked.connect(self._choose_archive)
        self.load_game_button.clicked.connect(self._choose_game_save)
        self.delete_archive_button.clicked.connect(self._delete_archive_selection)
        self.delete_game_button.clicked.connect(self._delete_game_selection)

        self._reload_archive()
        self.reload_game_save(silent=True)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reload_archive()
        self.reload_game_save(silent=True)

    def copy_selection(self) -> None:
        reference = self._selected_reference()
        if reference is not None and self._reference_is_active(reference):
            self._clipboard = reference

    def paste_selection(self) -> None:
        if self._clipboard is None:
            return
        try:
            if self._clipboard.kind == "game":
                self._game_to_archive(self._clipboard.row, move=False)
            else:
                self._archive_to_game(
                    self._clipboard.row,
                    self.game_table.currentRow(),
                    move=False,
                )
        except Exception as error:
            self._show_error(error)

    def delete_selection(self) -> None:
        reference = self._selected_reference()
        if reference is None:
            return
        if reference.kind == "archive":
            self._delete_archive_row(reference.row)
        else:
            self._delete_game_row(reference.row)

    def game_action_keys(self, row: int) -> tuple[str, ...]:
        if (
                self._loaded_save is not None
                and 0 <= row < len(self._loaded_save.document.slots)
                and self._loaded_save.document.slots[row].active
        ):
            return ("characters.edit_stats",)
        return ()

    def reload_game_save(
            self,
            path: Path | str | None = None,
            *,
            silent: bool = False,
    ) -> None:
        try:
            self._loaded_save = self._service.load_save(path)
        except Exception as error:
            self._loaded_save = None
            self._render_game()
            if not silent:
                self._show_error(error)
            return
        self._render_game()

    def _create_table(self, kind: str, object_name: str) -> CharacterTable:
        table = CharacterTable(kind)
        table.setObjectName(object_name)
        for column, key in enumerate(
                ("characters.name", "characters.level", "characters.playtime")
        ):
            item = QTableWidgetItem()
            table.setHorizontalHeaderItem(column, item)
            self.bind(item.setText, key)
        table.itemSelectionChanged.connect(
            lambda source=table: self._selection_changed(source)
        )
        table.character_dropped.connect(self._handle_drop)
        return table

    def _add_shortcut(self, key, callback) -> None:
        shortcut = QShortcut(QKeySequence(key), self)
        shortcut.activated.connect(callback)
        self._shortcuts.append(shortcut)

    def _reload_archive(self) -> None:
        try:
            self._archive = self._archive_repository.load()
        except Exception as error:
            self._archive = ()
            self._show_error(error)
        self._render_archive()

    def _render_archive(self) -> None:
        self.archive_table.setRowCount(len(self._archive))
        for row, character in enumerate(self._archive):
            self._set_row(
                self.archive_table,
                row,
                character.name,
                character.level,
                character.seconds_played,
                active=True,
            )

    def _render_game(self) -> None:
        slots = self._loaded_save.document.slots if self._loaded_save is not None else ()
        self.game_table.setRowCount(10)
        for row in range(10):
            if row < len(slots) and slots[row].active:
                slot = slots[row]
                self._set_row(
                    self.game_table,
                    row,
                    slot.name,
                    slot.level,
                    slot.seconds_played,
                    active=True,
                )
            else:
                self._set_row(self.game_table, row, "", 0, 0, active=False)

    @staticmethod
    def _set_row(
            table: QTableWidget,
            row: int,
            name: str,
            level: int,
            seconds_played: int,
            *,
            active: bool,
    ) -> None:
        values = (
            name if active else "",
            str(level) if active else "",
            str(timedelta(seconds=seconds_played)) if active else "",
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, active)
            if not active:
                item.setForeground(INACTIVE_COLOR)
            table.setItem(row, column, item)

    def _selection_changed(self, source: CharacterTable) -> None:
        if self._changing_selection or not source.selectedItems():
            return
        other = self.game_table if source is self.archive_table else self.archive_table
        self._changing_selection = True
        other.clearSelection()
        self._changing_selection = False

    def _selected_reference(self) -> CharacterReference | None:
        if self.archive_table.selectedItems():
            return CharacterReference("archive", self.archive_table.currentRow())
        if self.game_table.selectedItems():
            return CharacterReference("game", self.game_table.currentRow())
        return None

    def _reference_is_active(self, reference: CharacterReference) -> bool:
        if reference.kind == "archive":
            return 0 <= reference.row < len(self._archive)
        return bool(self.game_action_keys(reference.row))

    def _handle_drop(
            self,
            source_kind: str,
            source_row: int,
            target_row: int,
            copy: bool,
    ) -> None:
        target = self.sender()
        if not isinstance(target, CharacterTable) or target.kind == source_kind:
            return
        try:
            if source_kind == "game":
                self._game_to_archive(source_row, move=not copy)
            else:
                self._archive_to_game(source_row, target_row, move=not copy)
        except Exception as error:
            self._show_error(error)

    def _game_to_archive(self, row: int, *, move: bool) -> None:
        if self._loaded_save is None or not 0 <= row < 10:
            return
        slot = self._loaded_save.document.slots[row]
        character = archive_from_slot(slot, self._loaded_save.document.steam_id)
        identity = archive_identity(character)
        if any(archive_identity(existing) == identity for existing in self._archive):
            raise LocalizedError(
                "character_archive_duplicate",
                f"Character already exists in archive: {character.name}",
                params={"name": character.name, "level": character.level},
            )
        previous = self._archive
        self._archive = (*previous, character)
        self._archive_repository.save(self._archive)
        if move:
            try:
                self._loaded_save = self._service.mutate_save(
                    self._loaded_save,
                    lambda document: replace_document_slot(
                        document,
                        row,
                        clear_slot(document.slots[row]),
                    ),
                )
            except Exception:
                self._archive = previous
                self._archive_repository.save(previous)
                raise
        self._render_archive()
        self._render_game()

    def _archive_to_game(self, row: int, target_row: int, *, move: bool) -> None:
        if self._loaded_save is None or not 0 <= row < len(self._archive):
            return
        destination = self._game_destination(target_row)
        character = self._archive[row]
        self._loaded_save = self._service.mutate_save(
            self._loaded_save,
            lambda document: install_archived_character(
                document,
                character,
                destination,
            ),
        )
        if move:
            self._archive = tuple(
                entry for index, entry in enumerate(self._archive) if index != row
            )
            self._archive_repository.save(self._archive)
        self._render_archive()
        self._render_game()

    def _game_destination(self, requested_row: int) -> int:
        if self._loaded_save is None:
            raise LocalizedError(
                "character_save_not_loaded",
                "No Elden Ring save is loaded",
            )
        slots = self._loaded_save.document.slots
        if 0 <= requested_row < len(slots):
            if not slots[requested_row].active or self._confirm(
                    "characters.overwrite_title",
                    "characters.overwrite_message",
                    name=slots[requested_row].name,
            ):
                return requested_row
            raise LocalizedError(
                "character_operation_cancelled",
                "Character overwrite was cancelled",
            )
        for slot in slots:
            if not slot.active:
                return slot.index
        raise LocalizedError(
            "character_no_free_slot",
            "No free character slot is available",
        )

    def _delete_archive_selection(self) -> None:
        reference = self._selected_reference()
        if reference is not None and reference.kind == "archive":
            self._delete_archive_row(reference.row)

    def _delete_game_selection(self) -> None:
        reference = self._selected_reference()
        if reference is not None and reference.kind == "game":
            self._delete_game_row(reference.row)

    def _delete_archive_row(self, row: int) -> None:
        if not 0 <= row < len(self._archive):
            return
        character = self._archive[row]
        if not self._confirm(
                "characters.delete_title",
                "characters.delete_archive_message",
                name=character.name,
        ):
            return
        self._archive = tuple(
            entry for index, entry in enumerate(self._archive) if index != row
        )
        try:
            self._archive_repository.save(self._archive)
        except Exception as error:
            self._show_error(error)
            self._reload_archive()
            return
        self._render_archive()

    def _delete_game_row(self, row: int) -> None:
        if self._loaded_save is None or not self.game_action_keys(row):
            return
        slot = self._loaded_save.document.slots[row]
        if not self._confirm(
                "characters.delete_title",
                "characters.delete_game_message",
                name=slot.name,
        ):
            return
        try:
            self._loaded_save = self._service.mutate_save(
                self._loaded_save,
                lambda document: replace_document_slot(
                    document,
                    row,
                    clear_slot(document.slots[row]),
                ),
            )
        except Exception as error:
            self._show_error(error)
            return
        self._render_game()

    def _choose_archive(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            self.translator.translate("characters.archive_dialog"),
            str(self._archive_repository.path.parent),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            imported = self._archive_repository.load_from(path)
            identities = {archive_identity(entry) for entry in self._archive}
            additions = tuple(
                entry for entry in imported if archive_identity(entry) not in identities
            )
            self._archive = (*self._archive, *additions)
            self._archive_repository.save(self._archive)
            self._render_archive()
        except Exception as error:
            self._show_error(error)

    def _choose_game_save(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            self.translator.translate("characters.game_dialog"),
            "",
            "Elden Ring saves (ER0000.co2 ER0000.sl2)",
        )
        if path:
            self.reload_game_save(path)

    def _show_game_context_menu(self, position: QPoint) -> None:
        index = self.game_table.indexAt(position)
        if not index.isValid() or not self.game_action_keys(index.row()):
            return
        menu = SquarePopupMenu(self)
        action = QAction(self.translator.translate("characters.edit_stats"), menu)
        action.triggered.connect(lambda: self._edit_stats(index.row()))
        menu.addAction(action)
        menu.exec(self.game_table.viewport().mapToGlobal(position))

    def _edit_stats(self, row: int) -> None:
        if self._loaded_save is None or not self.game_action_keys(row):
            return
        try:
            stats = find_character_stats(self._loaded_save.document.slots[row])
        except Exception as error:
            self._show_error(error)
            return
        dialog = CharacterStatsDialog(self.translator, stats, self)
        if dialog.exec() != CharacterStatsDialog.DialogCode.Accepted:
            return
        try:
            edited = dialog.result_value()
            self._loaded_save = self._service.mutate_save(
                self._loaded_save,
                lambda document: replace_document_slot(
                    document,
                    row,
                    update_character_stats(document.slots[row], edited),
                ),
            )
        except Exception as error:
            self._show_error(error)
            return
        self._render_game()

    def _confirm(self, title_key: str, message_key: str, **params: object) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(self.translator.translate(title_key))
        dialog.setText(self.translator.translate(message_key, **params))
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.button(QMessageBox.StandardButton.Yes).setText(
            self.translator.translate("common.yes")
        )
        dialog.button(QMessageBox.StandardButton.No).setText(
            self.translator.translate("common.no")
        )
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def _show_error(self, error: BaseException) -> None:
        if isinstance(error, LocalizedError) and error.code == "character_operation_cancelled":
            return
        LOGGER.warning("Character operation failed: %s", error)
        QMessageBox.warning(
            self,
            self.translator.translate("characters.error_title"),
            localized_error_message(
                self.translator,
                error,
                fallback_key="errors.character_operation_failed",
            ),
        )
