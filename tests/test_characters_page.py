from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QByteArray, QMimeData, QPointF, Qt
from PySide6.QtGui import QDropEvent

from sct.characters import (
    CharacterArchiveRepository,
    CharacterManagerService,
    CharacterStats,
    EldenRingSaveCodec,
)
from sct.localization import TranslationService
from sct.settings import AppSettings, SettingsStore
from sct.ui.dialogs.character_stats import CharacterStatsDialog
from sct.ui.pages.characters import CHARACTER_MIME, CharactersPage, CharacterTable
from tests.qt_helpers import get_qapplication
from tests.test_characters import valid_save_bytes


class CharactersPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.appdata = self.root / "Roaming"
        self.steam_id = "76561198000000001"
        self.save_path = self.appdata / "EldenRing" / self.steam_id / "ER0000.co2"
        self.save_path.parent.mkdir(parents=True)
        self.save_path.write_bytes(valid_save_bytes())
        self.store = SettingsStore(self.root / "settings.ini")
        self.store.save(
            AppSettings(
                steam_id=self.steam_id,
                save_file_type="ER0000.co2",
                backup_directory=str(self.root / "backups"),
            )
        )
        self.repository = CharacterArchiveRepository(
            self.root / "CharacterManager.json"
        )
        self.service = CharacterManagerService(
            self.store,
            appdata=self.appdata,
            game_running=lambda: False,
        )
        self.page = CharactersPage(
            TranslationService(),
            self.store,
            service=self.service,
            archive_repository=self.repository,
        )

    def tearDown(self) -> None:
        self.page.deleteLater()
        self.application.processEvents()
        self.temporary.cleanup()

    def test_page_loads_all_ten_physical_save_slots(self) -> None:
        self.assertEqual(self.page.game_table.rowCount(), 10)
        self.assertEqual(self.page.game_table.item(0, 0).text(), "Tarnished")
        self.assertEqual(self.page.game_table.item(0, 1).text(), "42")
        self.assertEqual(self.page.game_table.item(1, 0).text(), "")

    def test_copy_and_paste_from_game_adds_character_to_archive(self) -> None:
        self.page.game_table.selectRow(0)

        self.page.copy_selection()
        self.page.paste_selection()

        self.assertEqual(self.page.archive_table.rowCount(), 1)
        self.assertEqual(self.repository.load()[0].name, "Tarnished")
        self.assertTrue(self.page.game_table.item(0, 0).text())

    def test_copy_from_archive_installs_character_in_selected_empty_slot(self) -> None:
        self.page.game_table.selectRow(0)
        self.page.copy_selection()
        self.page.paste_selection()
        self.page.archive_table.selectRow(0)
        self.page.copy_selection()
        self.page.game_table.selectRow(1)

        self.page.paste_selection()

        document = EldenRingSaveCodec().load(self.save_path)
        self.assertTrue(document.slots[1].active)
        self.assertEqual(document.slots[1].name, "Tarnished")
        self.assertEqual(
            len(tuple((self.root / "backups").glob("before_character_change_*.zip"))),
            1,
        )

    def test_only_active_game_slot_has_stats_context_action(self) -> None:
        self.assertEqual(
            self.page.game_action_keys(0),
            ("characters.edit_stats",),
        )
        self.assertEqual(self.page.game_action_keys(1), ())

    def test_move_from_game_archives_character_and_clears_original_slot(self) -> None:
        self.page._game_to_archive(0, move=True)

        document = EldenRingSaveCodec().load(self.save_path)
        self.assertFalse(document.slots[0].active)
        self.assertEqual(self.repository.load()[0].name, "Tarnished")

    def test_move_from_archive_installs_character_and_removes_archive_entry(self) -> None:
        self.page._game_to_archive(0, move=False)

        self.page._archive_to_game(0, 1, move=True)

        document = EldenRingSaveCodec().load(self.save_path)
        self.assertEqual(document.slots[1].name, "Tarnished")
        self.assertEqual(self.repository.load(), ())

    def test_delete_game_character_clears_slot_after_confirmation(self) -> None:
        with patch.object(self.page, "_confirm", return_value=True):
            self.page._delete_game_row(0)

        self.assertFalse(EldenRingSaveCodec().load(self.save_path).slots[0].active)


class CharacterStatsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_dialog_recalculates_level_and_preserves_playtime(self) -> None:
        stats = CharacterStats(
            vigor=13,
            mind=11,
            endurance=13,
            strength=12,
            dexterity=15,
            intelligence=9,
            faith=8,
            arcane=8,
            seconds_played=3_723,
            offset=500,
        )
        dialog = CharacterStatsDialog(TranslationService(), stats)

        dialog.attribute_inputs["vigor"].setValue(14)
        result = dialog.result_value()

        self.assertEqual(result.level, 11)
        self.assertEqual(result.seconds_played, 3_723)
        self.assertEqual(result.offset, 500)
        dialog.deleteLater()


class CharacterTableDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    @staticmethod
    def _drop(modifiers: Qt.KeyboardModifier):
        table = CharacterTable("archive")
        received: list[tuple[str, int, int, bool]] = []
        table.character_dropped.connect(
            lambda kind, source, target, copy: received.append(
                (kind, source, target, copy)
            )
        )
        mime = QMimeData()
        mime.setData(CHARACTER_MIME, QByteArray(b"game:0"))
        event = QDropEvent(
            QPointF(5, 5),
            Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            modifiers,
        )

        table.dropEvent(event)

        return table, event, received

    def test_plain_drag_requests_move(self) -> None:
        table, event, received = self._drop(Qt.KeyboardModifier.NoModifier)

        self.assertEqual(received, [("game", 0, -1, False)])
        self.assertEqual(event.dropAction(), Qt.DropAction.MoveAction)
        table.deleteLater()

    def test_control_drag_requests_copy(self) -> None:
        table, event, received = self._drop(
            Qt.KeyboardModifier.ControlModifier
        )

        self.assertEqual(received, [("game", 0, -1, True)])
        self.assertEqual(event.dropAction(), Qt.DropAction.CopyAction)
        table.deleteLater()


if __name__ == "__main__":
    unittest.main()
