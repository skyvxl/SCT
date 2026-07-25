from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from sct.game.builds import PlayerDetails, SavedBuild
from sct.game.players import PlayerSnapshot


def player_identity(player: PlayerSnapshot) -> str:
    if player.steam_id:
        return f"steam:{player.steam_id}"
    normalized_name = " ".join(player.name.split()).casefold()
    return f"fallback:{normalized_name}:{player.level}"


@dataclass(frozen=True, slots=True)
class RecentPlayerRecord:
    player: PlayerSnapshot
    last_seen: str
    details: PlayerDetails | None = None


class RecentStoreProtocol(Protocol):
    def load(self) -> tuple[RecentPlayerRecord, ...]: ...

    def save(self, records: tuple[RecentPlayerRecord, ...]) -> None: ...


class RecentPlayerStore:
    def __init__(self, path: Path | str, *, limit: int = 50) -> None:
        self.path = Path(path)
        self.limit = limit

    def load(self) -> tuple[RecentPlayerRecord, ...]:
        if not self.path.is_file():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                return ()
            records = tuple(self._record_from_dict(item) for item in payload)
            return tuple(sorted(records, key=lambda item: item.last_seen, reverse=True))[
                : self.limit
            ]
        except (OSError, ValueError, TypeError, KeyError):
            return ()

    def save(self, records: tuple[RecentPlayerRecord, ...]) -> None:
        ordered = tuple(sorted(records, key=lambda item: item.last_seen, reverse=True))[
            : self.limit
        ]
        payload = [self._record_to_dict(record) for record in ordered]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                delete=False,
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            ) as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _record_to_dict(record: RecentPlayerRecord) -> dict[str, object]:
        player = record.player
        payload: dict[str, object] = {
            "last_seen": record.last_seen,
            "player": {
                "player_num": player.player_num,
                "is_local": False,
                "name": player.name,
                "steam_id": player.steam_id,
                "level": player.level,
                "hp": player.hp,
                "max_hp": player.max_hp,
                "runes": None,
                "equipment": dict(player.equipment),
            },
        }
        if record.details is not None:
            payload["details"] = SavedBuild.from_player(record.details).to_dict()
        return payload

    @staticmethod
    def _record_from_dict(value: object) -> RecentPlayerRecord:
        if not isinstance(value, dict):
            raise TypeError("Recent player entry must be an object")
        raw_player = value["player"]
        if not isinstance(raw_player, dict):
            raise TypeError("Recent player snapshot must be an object")
        raw_equipment = raw_player.get("equipment", {})
        if not isinstance(raw_equipment, dict):
            raise TypeError("Recent player equipment must be an object")
        equipment = {
            str(name): int(item_id) for name, item_id in raw_equipment.items()
        }
        player = PlayerSnapshot(
            player_num=int(raw_player.get("player_num", -1)),
            is_local=False,
            name=str(raw_player.get("name", "")),
            steam_id=(
                str(raw_player["steam_id"]) if raw_player.get("steam_id") else None
            ),
            level=int(raw_player.get("level", 0)),
            hp=int(raw_player.get("hp", 0)),
            max_hp=int(raw_player.get("max_hp", 0)),
            runes=None,
            equipment=MappingProxyType(equipment),
        )
        details: PlayerDetails | None = None
        raw_details = value.get("details")
        if isinstance(raw_details, dict):
            build = SavedBuild.from_dict(raw_details)
            details = PlayerDetails(
                player_num=player.player_num,
                is_local=False,
                name=player.name,
                steam_id=player.steam_id,
                stats=build.stats,
                equipment=build.equipment,
            )
        return RecentPlayerRecord(player, str(value["last_seen"]), details)


class SessionRosterTracker:
    def __init__(
        self,
        store: RecentStoreProtocol,
        *,
        now: Callable[[], datetime] | None = None,
        limit: int = 50,
    ) -> None:
        self._store = store
        self._now = now or (lambda: datetime.now(UTC))
        self._limit = limit
        self._history = store.load()
        self._live_by_slot: dict[int, PlayerSnapshot] = {}
        self._live_details: dict[str, PlayerDetails] = {}

    def restore(self) -> tuple[RecentPlayerRecord, ...]:
        return self._history

    def observe(
        self,
        current: Sequence[PlayerSnapshot],
        details: dict[str, PlayerDetails] | None = None,
    ) -> tuple[RecentPlayerRecord, ...]:
        live = {
            player.player_num: player
            for player in current
            if not player.is_local
        }
        live_identities = {player_identity(player) for player in live.values()}
        departed = [
            player
            for player in self._live_by_slot.values()
            if player_identity(player) not in live_identities
        ]
        departed_details = {
            player_identity(player): self._live_details.get(player_identity(player))
            for player in departed
        }
        self._live_by_slot = live
        supplied_details = details or {}
        self._live_details = {
            identity: supplied_details[identity]
            for identity in live_identities
            if identity in supplied_details
        }
        if not departed:
            return self._history
        timestamp = self._now().isoformat()
        history = list(self._history)
        for player in departed:
            identity = player_identity(player)
            history = [
                record
                for record in history
                if player_identity(record.player) != identity
            ]
            history.append(
                RecentPlayerRecord(
                    player,
                    timestamp,
                    departed_details.get(identity),
                )
            )
        self._history = tuple(
            sorted(history, key=lambda record: record.last_seen, reverse=True)[
                : self._limit
            ]
        )
        self._store.save(self._history)
        return self._history
