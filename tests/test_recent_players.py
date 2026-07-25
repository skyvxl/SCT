from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

from sct.game.builds import EquipmentItem, PlayerDetails
from sct.game.players import PlayerSnapshot
from sct.game.recent_players import (
    RecentPlayerRecord,
    RecentPlayerStore,
    SessionRosterTracker,
    player_identity,
)


def player(
    player_num: int,
    name: str,
    level: int,
    *,
    steam_id: str | None = None,
    local: bool = False,
) -> PlayerSnapshot:
    return PlayerSnapshot(
        player_num=player_num,
        is_local=local,
        name=name,
        steam_id=steam_id,
        level=level,
        hp=900,
        max_hp=1000,
        runes=100 if local else None,
        equipment=MappingProxyType({"helmet": level}),
    )


class MemoryStore:
    def __init__(self, records: tuple[RecentPlayerRecord, ...] = ()) -> None:
        self.records = records
        self.saved: list[tuple[RecentPlayerRecord, ...]] = []

    def load(self) -> tuple[RecentPlayerRecord, ...]:
        return self.records

    def save(self, records: tuple[RecentPlayerRecord, ...]) -> None:
        self.records = records
        self.saved.append(records)


class RecentPlayerTests(unittest.TestCase):
    def test_identity_prefers_steam_id_and_falls_back_to_normalized_name_level(self) -> None:
        self.assertEqual(
            player_identity(player(1, "Any Name", 10, steam_id="7656")),
            "steam:7656",
        )
        self.assertEqual(
            player_identity(player(1, "  Same NAME  ", 55)),
            "fallback:same name:55",
        )

    def test_player_is_added_only_after_departure(self) -> None:
        store = MemoryStore()
        moment = datetime(2026, 7, 25, 12, 30, tzinfo=UTC)
        tracker = SessionRosterTracker(store, now=lambda: moment)
        remote = player(1, "Phantom", 70, steam_id="7656")

        while_connected = tracker.observe((player(0, "Local", 40, local=True), remote))
        after_departure = tracker.observe((player(0, "Local", 40, local=True),))

        self.assertEqual(while_connected, ())
        self.assertEqual(len(after_departure), 1)
        self.assertEqual(after_departure[0].player, remote)
        self.assertEqual(after_departure[0].last_seen, moment.isoformat())

    def test_historical_row_remains_live_and_updates_after_next_departure(self) -> None:
        old_time = datetime(2026, 7, 20, tzinfo=UTC)
        new_time = datetime(2026, 7, 25, tzinfo=UTC)
        old = RecentPlayerRecord(
            player(4, "Old Name", 60, steam_id="7656"),
            old_time.isoformat(),
        )
        store = MemoryStore((old,))
        tracker = SessionRosterTracker(store, now=lambda: new_time)
        live = player(1, "New Name", 61, steam_id="7656")

        while_connected = tracker.observe((live,))
        after_departure = tracker.observe(())

        self.assertEqual(while_connected, (old,))
        self.assertEqual(len(after_departure), 1)
        self.assertEqual(after_departure[0].player.name, "New Name")
        self.assertEqual(after_departure[0].player.level, 61)
        self.assertEqual(after_departure[0].last_seen, new_time.isoformat())

    def test_fallback_identity_deduplicates_by_name_and_level(self) -> None:
        moments = iter(
            (
                datetime(2026, 7, 24, tzinfo=UTC),
                datetime(2026, 7, 25, tzinfo=UTC),
            )
        )
        store = MemoryStore()
        tracker = SessionRosterTracker(store, now=lambda: next(moments))

        tracker.observe((player(2, "Traveler", 25),))
        tracker.observe(())
        tracker.observe((player(3, " traveler ", 25),))
        history = tracker.observe(())

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].player.player_num, 3)

    def test_store_round_trip_is_atomic_and_limits_newest_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recent_players_eldenring.json"
            store = RecentPlayerStore(path, limit=2)
            base = datetime(2026, 7, 20, tzinfo=UTC)
            records = tuple(
                RecentPlayerRecord(
                    player(index + 1, f"Player {index}", index),
                    (base + timedelta(days=index)).isoformat(),
                )
                for index in range(3)
            )

            store.save(records)
            loaded = store.load()

        self.assertEqual([record.player.name for record in loaded], ["Player 2", "Player 1"])
        self.assertFalse(any(record.player.is_local for record in loaded))

    def test_departed_player_keeps_detailed_snapshot_and_store_round_trips_it(self) -> None:
        remote = player(1, "Phantom", 70, steam_id="7656")
        details = PlayerDetails(
            player_num=1,
            is_local=False,
            name="Phantom",
            steam_id="7656",
            stats=MappingProxyType({"level": 70, "vigor": 40}),
            equipment=MappingProxyType(
                {"primary_right_wep": EquipmentItem(1_000_000, upgrade_level=10)}
            ),
        )
        store = MemoryStore()
        tracker = SessionRosterTracker(
            store,
            now=lambda: datetime(2026, 7, 25, tzinfo=UTC),
        )

        tracker.observe((remote,), {player_identity(remote): details})
        history = tracker.observe(())

        self.assertEqual(history[0].details, details)
        with tempfile.TemporaryDirectory() as directory:
            disk_store = RecentPlayerStore(Path(directory) / "recent.json")
            disk_store.save(history)
            loaded = disk_store.load()
        self.assertEqual(loaded[0].details, details)


if __name__ == "__main__":
    unittest.main()
