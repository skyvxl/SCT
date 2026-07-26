from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from types import MappingProxyType
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from sct.game.cheats import Cheat
from sct.game.players import PlayerSnapshot, player_details_from_snapshot
from sct.game.recent_players import RecentPlayerRecord
from sct.game.runtime import GameSnapshot
from sct.items import ItemDataNotFound
from sct.localization import TranslationService
from sct.ui.pages.current_game import CurrentGamePage
from tests.qt_helpers import get_qapplication


def snapshot_player(
        player_num: int,
        name: str,
        *,
        local: bool,
        runes: int | None,
        hp: int = 900,
        max_hp: int = 1000,
) -> PlayerSnapshot:
    return PlayerSnapshot(
        player_num=player_num,
        is_local=local,
        name=name,
        steam_id=None if local else f"7656{player_num}",
        level=40 + player_num,
        hp=hp,
        max_hp=max_hp,
        runes=runes,
        equipment=MappingProxyType({}),
    )


class FakeRuntime:
    def __init__(self) -> None:
        self.enabled: set[Cheat] = set()
        self.closed = False

    def poll(self) -> GameSnapshot:
        return GameSnapshot((), ())

    def set_runes(self, value: int) -> GameSnapshot:
        return GameSnapshot((), ())

    def set_cheat(self, cheat: Cheat, enabled: bool) -> None:
        if enabled:
            self.enabled.add(cheat)
        else:
            self.enabled.discard(cheat)

    def enabled_cheats(self) -> frozenset[Cheat]:
        return frozenset(self.enabled)

    def close(self) -> None:
        self.closed = True


class CurrentGamePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()
        cls.translator = TranslationService()

    def setUp(self) -> None:
        self.runtime = FakeRuntime()
        self.page = CurrentGamePage(
            self.translator,
            self.runtime,
            start_worker_thread=False,
        )

    def tearDown(self) -> None:
        self.page.shutdown()

    def test_snapshot_populates_local_first_with_local_only_runes_and_highlight(self) -> None:
        local = snapshot_player(0, "Local", local=True, runes=123456)
        remote = snapshot_player(1, "Phantom", local=False, runes=None)
        recent = RecentPlayerRecord(
            snapshot_player(3, "Old Phantom", local=False, runes=None),
            datetime(2026, 7, 25, 12, 30, tzinfo=UTC).isoformat(),
        )

        self.page.apply_snapshot(GameSnapshot((local, remote), (recent,)))

        self.assertEqual(self.page.current_table.columnCount(), 4)
        self.assertEqual(self.page.current_table.rowCount(), 2)
        self.assertEqual(self.page.current_table.item(0, 0).text(), "Local")
        self.assertEqual(self.page.current_table.item(0, 3).text(), "123456")
        self.assertEqual(self.page.current_table.item(1, 3).text(), "")
        self.assertNotEqual(
            self.page.current_table.item(0, 0).background().color(),
            self.page.current_table.item(1, 0).background().color(),
        )
        health = self.page.current_table.cellWidget(0, 2)
        self.assertEqual(health.value(), 90)
        self.assertEqual(self.page.recent_table.rowCount(), 1)
        self.assertEqual(self.page.recent_table.item(0, 0).text(), "Old Phantom")

    def test_context_actions_depend_on_identity_and_column(self) -> None:
        local = snapshot_player(0, "Local", local=True, runes=10)
        remote = snapshot_player(1, "Phantom", local=False, runes=None)
        recent = RecentPlayerRecord(
            snapshot_player(2, "Recent", local=False, runes=None),
            datetime.now(UTC).isoformat(),
        )
        self.page.apply_snapshot(GameSnapshot((local, remote), (recent,)))

        self.assertEqual(
            self.page.current_action_keys(0, 0),
            (
                "current_game.actions.details_build",
                "current_game.actions.cheats",
            ),
        )
        self.assertEqual(
            self.page.current_action_keys(0, 1),
            (
                "current_game.actions.details_build",
                "current_game.actions.cheats",
            ),
        )
        self.assertEqual(
            self.page.current_action_keys(0, 3),
            ("current_game.actions.edit_runes",),
        )
        self.assertEqual(
            self.page.current_action_keys(1, 0),
            ("current_game.actions.details",),
        )
        self.assertEqual(self.page.current_action_keys(1, 3), ())
        self.assertEqual(
            self.page.recent_action_keys(0, 0),
            ("current_game.actions.details",),
        )
        self.assertEqual(self.page.recent_action_keys(0, 2), ())

    def test_remove_confirmation_uses_application_translations(self) -> None:
        dialog = self.page._create_remove_seamless_items_confirmation()

        self.assertEqual(
            dialog.button(QMessageBox.StandardButton.Yes).text(),
            "Да",
        )
        self.assertEqual(
            dialog.button(QMessageBox.StandardButton.No).text(),
            "Нет",
        )

    def test_missing_item_data_blocks_player_details_and_lists_missing_files(
            self,
    ) -> None:
        self.page._item_catalog = None
        self.page._item_data_error = ItemDataNotFound(
            "Item data is unavailable",
            missing_files=("Weapons.csv", "images.zip"),
        )
        details = player_details_from_snapshot(
            snapshot_player(0, "Local", local=True, runes=100)
        )

        self.page._open_details_dialog(details)

        self.assertEqual(self.page._details_dialogs, [])
        message = self.page._missing_items_dialog
        self.assertIsNotNone(message)
        self.assertIn("items.zip", message.text())
        self.assertIn("Weapons.csv", message.text())
        self.assertIn("images.zip", message.text())
        message.close()

    def test_frozen_item_warning_omits_development_directory(self) -> None:
        self.page._item_catalog = None
        self.page._item_data_error = ItemDataNotFound(
            "Item data is unavailable",
            missing_files=("Weapons.csv", "images.zip"),
        )

        with patch.object(sys, "frozen", True, create=True):
            message = self.page._create_missing_item_data_message()

        self.assertIn("items.zip", message.text())
        self.assertIn("Weapons.csv", message.text())
        self.assertNotIn("data/items", message.text())
        message.close()


if __name__ == "__main__":
    unittest.main()
