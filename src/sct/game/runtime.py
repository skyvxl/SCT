from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sct.errors import LocalizedError
from sct.game.build_apply import EldenRingBuildApplyService
from sct.game.builds import PlayerDetails, SavedBuild
from sct.game.cheats import Cheat, EldenRingCheatRuntime
from sct.game.elden_ring import PROCESS_NAME, SIGNATURES_PATH
from sct.game.errors import GameProcessNotFound
from sct.game.inventory import (
    EldenRingInventoryService,
    RemovalReport,
)
from sct.game.memory import MemoryClient, MemoryClientProtocol
from sct.game.players import EldenRingPlayerService, PlayerSnapshot
from sct.game.recent_players import (
    RecentPlayerRecord,
    RecentPlayerStore,
    SessionRosterTracker,
    player_identity,
)
from sct.game.signatures import SymbolResolver

LOGGER = logging.getLogger("sct.game.runtime")


class PlayerServiceProtocol(Protocol):
    def list_players(self) -> tuple[PlayerSnapshot, ...]: ...

    def write_local_runes(self, value: int) -> None: ...

    def read_player_details(self, player_num: int) -> PlayerDetails | None: ...


class InventoryServiceProtocol(Protocol):
    def remove_seamless_items(self) -> RemovalReport: ...


class BuildApplyServiceProtocol(Protocol):
    def apply(
            self,
            *,
            player_num: int,
            build: SavedBuild,
            equipment_only: bool = False,
    ) -> None: ...


class RosterTrackerProtocol(Protocol):
    def restore(self) -> tuple[RecentPlayerRecord, ...]: ...

    def observe(
            self,
            players: tuple[PlayerSnapshot, ...],
            details: dict[str, PlayerDetails] | None = None,
    ) -> tuple[RecentPlayerRecord, ...]: ...


class CheatRuntimeProtocol(Protocol):
    def set_enabled(self, cheat: Cheat, enabled: bool) -> None: ...

    def enabled_cheats(self) -> frozenset[Cheat]: ...

    def stop(self) -> None: ...


MemoryFactory = Callable[[], MemoryClientProtocol]
ResolverFactory = Callable[[MemoryClientProtocol], Any]
PlayerServiceFactory = Callable[[MemoryClientProtocol, Any], PlayerServiceProtocol]
InventoryServiceFactory = Callable[[MemoryClientProtocol, Any], InventoryServiceProtocol]
BuildApplyServiceFactory = Callable[
    [MemoryClientProtocol, Any],
    BuildApplyServiceProtocol,
]


@dataclass(frozen=True, slots=True)
class GameSnapshot:
    current_players: tuple[PlayerSnapshot, ...]
    recent_players: tuple[RecentPlayerRecord, ...]


class EldenRingRuntime:
    def __init__(
            self,
            *,
            memory_factory: MemoryFactory,
            resolver_factory: ResolverFactory,
            player_service_factory: PlayerServiceFactory,
            roster_tracker: RosterTrackerProtocol,
            cheat_runtime: CheatRuntimeProtocol,
            inventory_service_factory: InventoryServiceFactory = EldenRingInventoryService,
            build_apply_service_factory: BuildApplyServiceFactory = (
                    EldenRingBuildApplyService
            ),
    ) -> None:
        self._memory_factory = memory_factory
        self._resolver_factory = resolver_factory
        self._player_service_factory = player_service_factory
        self._roster_tracker = roster_tracker
        self._cheat_runtime = cheat_runtime
        self._inventory_service_factory = inventory_service_factory
        self._build_apply_service_factory = build_apply_service_factory
        self._memory: MemoryClientProtocol | None = None
        self._resolver: Any | None = None
        self._player_service: PlayerServiceProtocol | None = None

    def poll(self) -> GameSnapshot:
        try:
            service = self._ensure_player_service()
            players = service.list_players()
            details: dict[str, PlayerDetails] = {}
            reader = getattr(service, "read_player_details", None)
            if callable(reader):
                for player in players:
                    value = reader(player.player_num)
                    if value is not None:
                        details[player_identity(player)] = value
            recent = self._roster_tracker.observe(players, details)
            return GameSnapshot(players, recent)
        except Exception as error:
            LOGGER.debug("Unable to poll Elden Ring runtime: %s", error)
            self._disconnect()
            recent = self._roster_tracker.observe((), {})
            return GameSnapshot((), recent)

    def set_runes(self, value: int) -> GameSnapshot:
        try:
            self._ensure_player_service().write_local_runes(value)
        except GameProcessNotFound as error:
            self._disconnect()
            raise LocalizedError(
                "game_not_running",
                f"Unable to write runes because Elden Ring is not running: {error}",
            ) from error
        except ValueError as error:
            raise LocalizedError(
                "invalid_rune_count",
                f"Invalid Elden Ring rune count: {error}",
            ) from error
        except Exception as error:
            LOGGER.exception("Unable to write local Elden Ring runes")
            raise LocalizedError(
                "rune_write_failed",
                f"Unable to write local Elden Ring runes: {error}",
            ) from error
        return self.poll()

    def set_cheat(self, cheat: Cheat, enabled: bool) -> None:
        try:
            self._cheat_runtime.set_enabled(cheat, enabled)
        except GameProcessNotFound as error:
            raise LocalizedError(
                "game_not_running",
                f"Unable to toggle {cheat.value} because Elden Ring is not running: {error}",
            ) from error
        except Exception as error:
            LOGGER.exception("Unable to toggle Elden Ring cheat %s", cheat.value)
            raise LocalizedError(
                "cheat_toggle_failed",
                f"Unable to toggle Elden Ring cheat {cheat.value}: {error}",
            ) from error

    def player_details(self, player_num: int) -> PlayerDetails:
        try:
            details = self._ensure_player_service().read_player_details(player_num)
            if details is None:
                raise LocalizedError(
                    "player_details_unavailable",
                    f"Player details are unavailable for slot {player_num}",
                )
            return details
        except LocalizedError:
            raise
        except GameProcessNotFound as error:
            self._disconnect()
            raise LocalizedError(
                "game_not_running",
                f"Unable to read player details because Elden Ring is not running: {error}",
            ) from error
        except Exception as error:
            LOGGER.exception("Unable to read Elden Ring player details")
            raise LocalizedError(
                "player_details_unavailable",
                f"Unable to read player details for slot {player_num}: {error}",
            ) from error

    def remove_seamless_items(self) -> RemovalReport:
        try:
            self._ensure_player_service()
            if self._memory is None or self._resolver is None:
                raise RuntimeError("Elden Ring memory session is unavailable")
            service = self._inventory_service_factory(self._memory, self._resolver)
            return service.remove_seamless_items()
        except GameProcessNotFound as error:
            self._disconnect()
            raise LocalizedError(
                "game_not_running",
                "Unable to remove Seamless Co-op items because "
                f"Elden Ring is not running: {error}",
            ) from error
        except Exception as error:
            LOGGER.exception("Unable to remove Seamless Co-op items")
            raise LocalizedError(
                "seamless_items_remove_failed",
                f"Unable to remove Seamless Co-op items: {error}",
            ) from error

    def apply_build(
            self,
            build: SavedBuild,
            *,
            equipment_only: bool = False,
    ) -> GameSnapshot:
        try:
            self._ensure_player_service()
            if self._memory is None or self._resolver is None:
                raise RuntimeError("Elden Ring memory session is unavailable")
            service = self._build_apply_service_factory(
                self._memory,
                self._resolver,
            )
            service.apply(
                player_num=0,
                build=build,
                equipment_only=equipment_only,
            )
            return self.poll()
        except GameProcessNotFound as error:
            self._disconnect()
            raise LocalizedError(
                "game_not_running",
                "Unable to apply the build because Elden Ring is not running: "
                f"{error}",
            ) from error
        except Exception as error:
            LOGGER.exception("Unable to apply Elden Ring build")
            raise LocalizedError(
                "build_apply_failed",
                f"Unable to apply Elden Ring build: {error}",
            ) from error

    def enabled_cheats(self) -> frozenset[Cheat]:
        return self._cheat_runtime.enabled_cheats()

    def close(self) -> None:
        self._roster_tracker.observe((), {})
        self._cheat_runtime.stop()
        self._disconnect()

    def _ensure_player_service(self) -> PlayerServiceProtocol:
        if self._player_service is not None:
            return self._player_service
        memory = self._memory_factory()
        try:
            resolver = self._resolver_factory(memory)
            service = self._player_service_factory(memory, resolver)
        except Exception:
            memory.close()
            raise
        self._memory = memory
        self._resolver = resolver
        self._player_service = service
        return service

    def _disconnect(self) -> None:
        memory = self._memory
        self._memory = None
        self._resolver = None
        self._player_service = None
        if memory is not None:
            memory.close()


def build_elden_ring_runtime(settings_path: Path | str) -> EldenRingRuntime:
    recent_path = Path(settings_path).parent / "recent_players_eldenring.json"

    def memory_factory() -> MemoryClient:
        return MemoryClient(PROCESS_NAME)

    def resolver_factory(memory: MemoryClientProtocol) -> SymbolResolver:
        return SymbolResolver(
            memory,
            SIGNATURES_PATH,
            default_module=PROCESS_NAME,
        )

    cheat_runtime = EldenRingCheatRuntime(memory_factory, resolver_factory)
    return EldenRingRuntime(
        memory_factory=memory_factory,
        resolver_factory=resolver_factory,
        player_service_factory=EldenRingPlayerService,
        roster_tracker=SessionRosterTracker(RecentPlayerStore(recent_path)),
        cheat_runtime=cheat_runtime,
    )
