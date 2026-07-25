from __future__ import annotations

import unittest
from types import MappingProxyType

from sct.game.builds import PlayerDetails, SavedBuild
from sct.game.inventory import RemovalReport
from sct.game.runtime import GameSnapshot
from sct.ui.workers.current_game import CurrentGameWorker
from tests.qt_helpers import get_qapplication


class FakeRuntime:
    def __init__(self) -> None:
        self.poll_calls = 0
        self.runes: list[int] = []
        self.cheats: list[tuple[object, bool]] = []
        self.closed = False
        self.details = PlayerDetails(
            player_num=0,
            is_local=True,
            name="Local",
            steam_id=None,
            stats=MappingProxyType({"level": 1}),
            equipment=MappingProxyType({}),
        )
        self.removal_report = RemovalReport((), (), ())
        self.applied_builds: list[tuple[SavedBuild, bool]] = []

    def poll(self) -> GameSnapshot:
        self.poll_calls += 1
        return GameSnapshot((), ())

    def set_runes(self, value: int) -> GameSnapshot:
        self.runes.append(value)
        return GameSnapshot((), ())

    def set_cheat(self, cheat: object, enabled: bool) -> None:
        self.cheats.append((cheat, enabled))

    def player_details(self, player_num: int) -> PlayerDetails:
        return self.details

    def remove_seamless_items(self) -> RemovalReport:
        return self.removal_report

    def apply_build(
        self,
        build: SavedBuild,
        *,
        equipment_only: bool = False,
    ) -> GameSnapshot:
        self.applied_builds.append((build, equipment_only))
        return GameSnapshot((), ())

    def close(self) -> None:
        self.closed = True


class CurrentGameWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_enabling_polling_reads_immediately_and_uses_five_second_timer(self) -> None:
        runtime = FakeRuntime()
        worker = CurrentGameWorker(runtime)
        received: list[GameSnapshot] = []
        worker.snapshot_ready.connect(received.append)

        worker.set_polling(True)

        self.assertEqual(runtime.poll_calls, 1)
        self.assertEqual(received, [GameSnapshot((), ())])
        self.assertTrue(worker.timer.isActive())
        self.assertEqual(worker.timer.interval(), 5000)

        worker.set_polling(False)
        self.assertFalse(worker.timer.isActive())

    def test_busy_worker_does_not_start_an_overlapping_poll(self) -> None:
        worker: CurrentGameWorker

        class ReentrantRuntime(FakeRuntime):
            def poll(self) -> GameSnapshot:
                self.poll_calls += 1
                worker.poll_now()
                return GameSnapshot((), ())

        runtime = ReentrantRuntime()
        worker = CurrentGameWorker(runtime)

        worker.poll_now()

        self.assertEqual(runtime.poll_calls, 1)

    def test_explicit_actions_emit_updated_snapshot_and_shutdown_runtime(self) -> None:
        runtime = FakeRuntime()
        worker = CurrentGameWorker(runtime)
        received: list[GameSnapshot] = []
        worker.snapshot_ready.connect(received.append)

        worker.set_runes(777)
        worker.shutdown()

        self.assertEqual(runtime.runes, [777])
        self.assertEqual(received, [GameSnapshot((), ())])
        self.assertTrue(runtime.closed)

    def test_details_and_removal_emit_typed_results(self) -> None:
        runtime = FakeRuntime()
        worker = CurrentGameWorker(runtime)
        details: list[PlayerDetails] = []
        reports: list[RemovalReport] = []
        worker.details_ready.connect(details.append)
        worker.seamless_items_removed.connect(reports.append)

        worker.request_player_details(0)
        worker.remove_seamless_items()

        self.assertEqual(details, [runtime.details])
        self.assertEqual(reports, [runtime.removal_report])

    def test_apply_build_emits_refreshed_snapshot(self) -> None:
        runtime = FakeRuntime()
        worker = CurrentGameWorker(runtime)
        build = SavedBuild(
            source_name="Hero",
            stats=MappingProxyType({"level": 1}),
            equipment=MappingProxyType({}),
        )
        snapshots: list[GameSnapshot] = []
        worker.snapshot_ready.connect(snapshots.append)

        worker.apply_build(build, True)

        self.assertEqual(runtime.applied_builds, [(build, True)])
        self.assertEqual(snapshots, [GameSnapshot((), ())])


if __name__ == "__main__":
    unittest.main()
