from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from sct.errors import LocalizedError
from sct.game.elden_ring import PROCESS_NAME, SIGNATURES_PATH
from sct.game.errors import GameProcessNotFound
from sct.game.memory import MemoryClient, MemoryClientProtocol
from sct.game.players import (
    EldenRingPlayerService,
    PlayerSnapshot,
    load_elden_ring_offsets,
)
from sct.game.signatures import SymbolResolver

LOGGER = logging.getLogger("sct.game.save_actions")


class PlayerServiceProtocol(Protocol):
    def list_players(self) -> tuple[PlayerSnapshot, ...]: ...


MemoryFactory = Callable[[], MemoryClientProtocol]
ResolverFactory = Callable[[MemoryClientProtocol], Any]
PlayerServiceFactory = Callable[[MemoryClientProtocol, Any], PlayerServiceProtocol]


@dataclass(frozen=True, slots=True)
class GameSaveStatus:
    process_running: bool
    player_loaded: bool


class EldenRingSaveActions:
    def __init__(
            self,
            *,
            memory_factory: MemoryFactory,
            resolver_factory: ResolverFactory,
            player_service_factory: PlayerServiceFactory = EldenRingPlayerService,
            offsets: Mapping[str, Any] | None = None,
    ) -> None:
        self._memory_factory = memory_factory
        self._resolver_factory = resolver_factory
        self._player_service_factory = player_service_factory
        self._offsets = offsets or load_elden_ring_offsets()

    def status(self) -> GameSaveStatus:
        memory: MemoryClientProtocol | None = None
        try:
            memory = self._memory_factory()
            resolver = self._resolver_factory(memory)
            service = self._player_service_factory(memory, resolver)
            loaded = any(player.is_local for player in service.list_players())
            return GameSaveStatus(True, loaded)
        except GameProcessNotFound:
            return GameSaveStatus(False, False)
        except Exception as error:
            LOGGER.debug("Unable to inspect Elden Ring save status: %s", error)
            raise LocalizedError(
                "backup_game_status_failed",
                f"Unable to inspect Elden Ring save status: {error}",
            ) from error
        finally:
            if memory is not None:
                memory.close()

    def request_save(self) -> None:
        memory: MemoryClientProtocol | None = None
        try:
            memory = self._memory_factory()
            resolver = self._resolver_factory(memory)
            service = self._player_service_factory(memory, resolver)
            if not any(player.is_local for player in service.list_players()):
                raise LocalizedError(
                    "backup_player_not_loaded",
                    "The local Elden Ring player is not loaded",
                )

            pointer_address = resolver.resolve("GameManPtrAddr").address
            game_manager = memory.read_ptr(pointer_address)
            if not game_manager:
                raise RuntimeError("GameMan pointer is null")
            save_flag_offset = self._save_flag_offset()
            memory.write_u8(game_manager + save_flag_offset, 1)
        except LocalizedError:
            raise
        except GameProcessNotFound as error:
            raise LocalizedError(
                "backup_game_not_running",
                f"Unable to request a save because Elden Ring is not running: {error}",
            ) from error
        except Exception as error:
            LOGGER.exception("Unable to request an Elden Ring save")
            raise LocalizedError(
                "backup_save_request_failed",
                f"Unable to request an Elden Ring save: {error}",
            ) from error
        finally:
            if memory is not None:
                memory.close()

    def _save_flag_offset(self) -> int:
        section = self._offsets.get("save_backup")
        if not isinstance(section, Mapping):
            raise KeyError("save_backup")
        value = section["save_flag_offset"]
        return value if isinstance(value, int) else int(str(value), 0)


def build_elden_ring_save_actions() -> EldenRingSaveActions:
    def memory_factory() -> MemoryClient:
        return MemoryClient(PROCESS_NAME)

    def resolver_factory(memory: MemoryClientProtocol) -> SymbolResolver:
        return SymbolResolver(
            memory,
            SIGNATURES_PATH,
            default_module=PROCESS_NAME,
        )

    return EldenRingSaveActions(
        memory_factory=memory_factory,
        resolver_factory=resolver_factory,
    )
