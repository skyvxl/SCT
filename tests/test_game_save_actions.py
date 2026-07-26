from __future__ import annotations

import unittest
from types import MappingProxyType, SimpleNamespace

from sct.errors import LocalizedError
from sct.game.errors import GameProcessNotFound
from sct.game.players import PlayerSnapshot
from sct.game.save_actions import EldenRingSaveActions, GameSaveStatus


def player(*, local: bool) -> PlayerSnapshot:
    return PlayerSnapshot(
        player_num=0 if local else 1,
        is_local=local,
        name="Local" if local else "Remote",
        steam_id=None,
        level=10,
        hp=400,
        max_hp=400,
        runes=0 if local else None,
        equipment=MappingProxyType({}),
    )


class FakeMemory:
    def __init__(self, game_manager: int = 0x5000) -> None:
        self.game_manager = game_manager
        self.closed = False
        self.writes: list[tuple[int, int]] = []

    def read_ptr(self, address: int) -> int:
        self.last_read = address
        return self.game_manager

    def write_u8(self, address: int, value: int) -> None:
        self.writes.append((address, value))

    def close(self) -> None:
        self.closed = True


class SaveActionsTests(unittest.TestCase):
    def build_actions(
            self,
            memory_factory,
            players: tuple[PlayerSnapshot, ...] = (),
    ) -> EldenRingSaveActions:
        class PlayerService:
            def list_players(self) -> tuple[PlayerSnapshot, ...]:
                return players

        return EldenRingSaveActions(
            memory_factory=memory_factory,
            resolver_factory=lambda _memory: SimpleNamespace(
                resolve=lambda _symbol: SimpleNamespace(address=0x1000)
            ),
            player_service_factory=lambda _memory, _resolver: PlayerService(),
            offsets={"save_backup": {"save_flag_offset": "0xb72"}},
        )

    def test_status_reports_missing_process_without_leaking_memory(self) -> None:
        def missing_process():
            raise GameProcessNotFound("eldenring.exe")

        actions = self.build_actions(missing_process)

        self.assertEqual(actions.status(), GameSaveStatus(False, False))

    def test_status_requires_the_local_player_and_closes_session(self) -> None:
        memory = FakeMemory()
        actions = self.build_actions(lambda: memory, (player(local=False),))

        self.assertEqual(actions.status(), GameSaveStatus(True, False))
        self.assertTrue(memory.closed)

    def test_request_save_writes_game_manager_flag_and_closes_session(self) -> None:
        memory = FakeMemory()
        actions = self.build_actions(lambda: memory, (player(local=True),))

        actions.request_save()

        self.assertEqual(memory.last_read, 0x1000)
        self.assertEqual(memory.writes, [(0x5B72, 1)])
        self.assertTrue(memory.closed)

    def test_request_save_requires_a_loaded_local_player(self) -> None:
        memory = FakeMemory()
        actions = self.build_actions(lambda: memory, (player(local=False),))

        with self.assertRaises(LocalizedError) as raised:
            actions.request_save()

        self.assertEqual(raised.exception.code, "backup_player_not_loaded")
        self.assertEqual(memory.writes, [])
        self.assertTrue(memory.closed)

    def test_request_save_rejects_a_null_game_manager(self) -> None:
        memory = FakeMemory(game_manager=0)
        actions = self.build_actions(lambda: memory, (player(local=True),))

        with self.assertRaises(LocalizedError) as raised:
            actions.request_save()

        self.assertEqual(raised.exception.code, "backup_save_request_failed")
        self.assertTrue(memory.closed)


if __name__ == "__main__":
    unittest.main()
