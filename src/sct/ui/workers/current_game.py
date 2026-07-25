from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from sct.game.builds import PlayerDetails, SavedBuild
from sct.game.cheats import Cheat
from sct.game.inventory import RemovalReport
from sct.game.runtime import GameSnapshot


class CurrentGameRuntimeProtocol(Protocol):
    def poll(self) -> GameSnapshot: ...

    def set_runes(self, value: int) -> GameSnapshot: ...

    def set_cheat(self, cheat: Cheat, enabled: bool) -> None: ...

    def player_details(self, player_num: int) -> PlayerDetails: ...

    def remove_seamless_items(self) -> RemovalReport: ...

    def apply_build(
        self,
        build: SavedBuild,
        *,
        equipment_only: bool = False,
    ) -> GameSnapshot: ...

    def close(self) -> None: ...


class CurrentGameWorker(QObject):
    snapshot_ready = Signal(object)
    action_failed = Signal(object)
    action_succeeded = Signal(str)
    cheat_changed = Signal(object, bool)
    details_ready = Signal(object)
    seamless_items_removed = Signal(object)
    shutdown_finished = Signal()

    def __init__(
        self,
        runtime: CurrentGameRuntimeProtocol,
        *,
        interval_ms: int = 5000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.runtime = runtime
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.poll_now)
        self._busy = False

    @Slot(bool)
    def set_polling(self, enabled: bool) -> None:
        if enabled:
            if not self.timer.isActive():
                self.poll_now()
                self.timer.start()
            return
        self.timer.stop()

    @Slot()
    def poll_now(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            self.snapshot_ready.emit(self.runtime.poll())
        except Exception as error:
            self.action_failed.emit(error)
        finally:
            self._busy = False

    @Slot(int)
    def set_runes(self, value: int) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            snapshot = self.runtime.set_runes(value)
            self.snapshot_ready.emit(snapshot)
            self.action_succeeded.emit("runes")
        except Exception as error:
            self.action_failed.emit(error)
        finally:
            self._busy = False

    @Slot(object, bool)
    def set_cheat(self, cheat: Cheat, enabled: bool) -> None:
        try:
            self.runtime.set_cheat(cheat, enabled)
            self.cheat_changed.emit(cheat, enabled)
            self.action_succeeded.emit("cheat")
        except Exception as error:
            self.action_failed.emit(error)

    @Slot(int)
    def request_player_details(self, player_num: int) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            self.details_ready.emit(self.runtime.player_details(player_num))
        except Exception as error:
            self.action_failed.emit(error)
        finally:
            self._busy = False

    @Slot()
    def remove_seamless_items(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            report = self.runtime.remove_seamless_items()
            self.seamless_items_removed.emit(report)
            self.action_succeeded.emit("seamless_items_removed")
        except Exception as error:
            self.action_failed.emit(error)
        finally:
            self._busy = False

    @Slot(object, bool)
    def apply_build(self, build: SavedBuild, equipment_only: bool = False) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            snapshot = self.runtime.apply_build(
                build,
                equipment_only=equipment_only,
            )
            self.snapshot_ready.emit(snapshot)
            self.action_succeeded.emit("build_applied")
        except Exception as error:
            self.action_failed.emit(error)
        finally:
            self._busy = False

    @Slot()
    def shutdown(self) -> None:
        self.timer.stop()
        try:
            self.runtime.close()
        finally:
            self.shutdown_finished.emit()
