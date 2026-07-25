from __future__ import annotations

import unittest
from types import MappingProxyType

from sct.errors import LocalizedError
from sct.game.builds import PlayerDetails, SavedBuild
from sct.game.cheats import Cheat
from sct.game.errors import GameProcessNotFound
from sct.game.inventory import RemovalReport
from sct.game.players import PlayerSnapshot
from sct.game.runtime import EldenRingRuntime


def local_player(runes: int = 10) -> PlayerSnapshot:
    return PlayerSnapshot(
        player_num=0,
        is_local=True,
        name="Local",
        steam_id=None,
        level=20,
        hp=500,
        max_hp=600,
        runes=runes,
        equipment=MappingProxyType({}),
    )


class FakeMemory:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeTracker:
    def __init__(self) -> None:
        self.observed: list[tuple[PlayerSnapshot, ...]] = []

    def restore(self) -> tuple[object, ...]:
        return ()

    def observe(
        self,
        players: tuple[PlayerSnapshot, ...],
        details: dict[str, PlayerDetails] | None = None,
    ) -> tuple[object, ...]:
        self.observed.append(players)
        return ()


class FakeCheatRuntime:
    def __init__(self) -> None:
        self.enabled: set[Cheat] = set()
        self.stopped = False

    def set_enabled(self, cheat: Cheat, enabled: bool) -> None:
        if enabled:
            self.enabled.add(cheat)
        else:
            self.enabled.discard(cheat)

    def enabled_cheats(self) -> frozenset[Cheat]:
        return frozenset(self.enabled)

    def stop(self) -> None:
        self.stopped = True


class RuntimeTests(unittest.TestCase):
    def test_poll_reuses_live_memory_session(self) -> None:
        memory_calls = 0
        service_calls = 0
        memory = FakeMemory()
        tracker = FakeTracker()

        def memory_factory() -> FakeMemory:
            nonlocal memory_calls
            memory_calls += 1
            return memory

        class Service:
            def list_players(self) -> tuple[PlayerSnapshot, ...]:
                nonlocal service_calls
                service_calls += 1
                return (local_player(),)

            def write_local_runes(self, value: int) -> None:
                return None

        runtime = EldenRingRuntime(
            memory_factory=memory_factory,
            resolver_factory=lambda _memory: object(),
            player_service_factory=lambda _memory, _resolver: Service(),
            roster_tracker=tracker,
            cheat_runtime=FakeCheatRuntime(),
        )

        first = runtime.poll()
        second = runtime.poll()

        self.assertEqual(memory_calls, 1)
        self.assertEqual(service_calls, 2)
        self.assertEqual(first.current_players[0].name, "Local")
        self.assertEqual(second.current_players[0].name, "Local")

    def test_process_failure_closes_session_and_finalizes_live_roster(self) -> None:
        memory = FakeMemory()
        tracker = FakeTracker()

        class Service:
            calls = 0

            def list_players(self) -> tuple[PlayerSnapshot, ...]:
                self.calls += 1
                if self.calls == 1:
                    return (local_player(),)
                raise GameProcessNotFound("eldenring.exe")

            def write_local_runes(self, value: int) -> None:
                return None

        service = Service()
        runtime = EldenRingRuntime(
            memory_factory=lambda: memory,
            resolver_factory=lambda _memory: object(),
            player_service_factory=lambda _memory, _resolver: service,
            roster_tracker=tracker,
            cheat_runtime=FakeCheatRuntime(),
        )
        runtime.poll()

        disconnected = runtime.poll()

        self.assertEqual(disconnected.current_players, ())
        self.assertTrue(memory.closed)
        self.assertEqual(tracker.observed[-1], ())

    def test_set_runes_writes_and_returns_immediate_snapshot(self) -> None:
        memory = FakeMemory()
        tracker = FakeTracker()

        class Service:
            value = 10

            def list_players(self) -> tuple[PlayerSnapshot, ...]:
                return (local_player(self.value),)

            def write_local_runes(self, value: int) -> None:
                self.value = value

        service = Service()
        runtime = EldenRingRuntime(
            memory_factory=lambda: memory,
            resolver_factory=lambda _memory: object(),
            player_service_factory=lambda _memory, _resolver: service,
            roster_tracker=tracker,
            cheat_runtime=FakeCheatRuntime(),
        )

        snapshot = runtime.set_runes(12345)

        self.assertEqual(snapshot.current_players[0].runes, 12345)

    def test_explicit_action_failure_becomes_localized_error(self) -> None:
        runtime = EldenRingRuntime(
            memory_factory=lambda: (_ for _ in ()).throw(
                GameProcessNotFound("eldenring.exe")
            ),
            resolver_factory=lambda _memory: object(),
            player_service_factory=lambda _memory, _resolver: object(),
            roster_tracker=FakeTracker(),
            cheat_runtime=FakeCheatRuntime(),
        )

        with self.assertRaises(LocalizedError) as raised:
            runtime.set_runes(100)

        self.assertEqual(raised.exception.code, "game_not_running")

    def test_details_and_seamless_removal_use_live_session_services(self) -> None:
        memory = FakeMemory()
        details = PlayerDetails(
            player_num=0,
            is_local=True,
            name="Local",
            steam_id=None,
            stats=MappingProxyType({"level": 20}),
            equipment=MappingProxyType({}),
        )
        report = RemovalReport((), (), ())

        class Service:
            def list_players(self) -> tuple[PlayerSnapshot, ...]:
                return (local_player(),)

            def write_local_runes(self, value: int) -> None:
                return None

            def read_player_details(self, player_num: int) -> PlayerDetails | None:
                return details if player_num == 0 else None

        class InventoryService:
            def remove_seamless_items(self) -> RemovalReport:
                return report

        runtime = EldenRingRuntime(
            memory_factory=lambda: memory,
            resolver_factory=lambda _memory: object(),
            player_service_factory=lambda _memory, _resolver: Service(),
            inventory_service_factory=lambda _memory, _resolver: InventoryService(),
            roster_tracker=FakeTracker(),
            cheat_runtime=FakeCheatRuntime(),
        )

        self.assertIs(runtime.player_details(0), details)
        self.assertIs(runtime.remove_seamless_items(), report)

    def test_missing_player_details_uses_localized_error(self) -> None:
        class Service:
            def list_players(self) -> tuple[PlayerSnapshot, ...]:
                return ()

            def write_local_runes(self, value: int) -> None:
                return None

            def read_player_details(self, player_num: int) -> None:
                return None

        runtime = EldenRingRuntime(
            memory_factory=FakeMemory,
            resolver_factory=lambda _memory: object(),
            player_service_factory=lambda _memory, _resolver: Service(),
            roster_tracker=FakeTracker(),
            cheat_runtime=FakeCheatRuntime(),
        )

        with self.assertRaises(LocalizedError) as raised:
            runtime.player_details(3)

        self.assertEqual(raised.exception.code, "player_details_unavailable")

    def test_apply_build_uses_local_player_and_returns_refreshed_snapshot(self) -> None:
        memory = FakeMemory()
        applied: list[tuple[int, SavedBuild, bool]] = []
        build = SavedBuild(
            source_name="Hero",
            stats=MappingProxyType({"level": 20}),
            equipment=MappingProxyType({}),
        )

        class Service:
            def list_players(self) -> tuple[PlayerSnapshot, ...]:
                return (local_player(),)

            def write_local_runes(self, value: int) -> None:
                return None

            def read_player_details(self, player_num: int) -> None:
                return None

        class ApplyService:
            def apply(
                self,
                *,
                player_num: int,
                build: SavedBuild,
                equipment_only: bool,
            ) -> None:
                applied.append((player_num, build, equipment_only))

        runtime = EldenRingRuntime(
            memory_factory=lambda: memory,
            resolver_factory=lambda _memory: object(),
            player_service_factory=lambda _memory, _resolver: Service(),
            build_apply_service_factory=lambda _memory, _resolver: ApplyService(),
            roster_tracker=FakeTracker(),
            cheat_runtime=FakeCheatRuntime(),
        )

        snapshot = runtime.apply_build(build, equipment_only=True)

        self.assertEqual(applied, [(0, build, True)])
        self.assertEqual(snapshot.current_players, (local_player(),))


if __name__ == "__main__":
    unittest.main()
