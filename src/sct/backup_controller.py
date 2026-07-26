from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from sct.backup_manager import BackupManager
from sct.backups import BackupEntry
from sct.errors import LocalizedError


class BackupController(QObject):
    backups_loaded = Signal(object)
    screenshot_loaded = Signal(str, object)
    backup_created = Signal(object)
    backup_restored = Signal(str)
    backup_deleted = Signal(str)
    backup_changed = Signal(object)
    auto_state_changed = Signal(bool)
    operation_failed = Signal(object)
    busy_changed = Signal(bool)
    _completed = Signal(object)
    _preview_completed = Signal(object)

    def __init__(self, manager: BackupManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="sct-backup",
        )
        self._pending = 0
        self._completed.connect(self._handle_completion)
        self._preview_completed.connect(self._handle_preview_completion)

    def refresh(self) -> None:
        self._submit(self._manager.list_backups, self.backups_loaded.emit)

    def create_backup(self) -> None:
        self._submit(self._manager.create_backup, self._created)

    def load_screenshot(self, name: str) -> None:
        future = self._executor.submit(
            self._manager.read_backup_screenshot,
            name,
        )
        future.add_done_callback(
            lambda completed: self._complete_preview_future(name, completed)
        )

    def restore_backup(self, name: str | None = None) -> None:
        def restore() -> str:
            selected = name or self._latest_backup_name()
            self._manager.restore_backup(selected)
            return selected

        self._submit(restore, self._restored)

    def delete_backup(self, name: str) -> None:
        def delete() -> str:
            self._manager.delete_backup(name)
            return name

        self._submit(delete, self._deleted)

    def set_backup_pinned(self, name: str, pinned: bool) -> None:
        self._submit(
            lambda: self._manager.set_backup_pinned(name, pinned),
            self._changed,
        )

    def rename_backup(self, name: str, new_name: str) -> None:
        self._submit(
            lambda: self._manager.rename_backup(name, new_name),
            self._changed,
        )

    def start_auto_backup(self) -> None:
        def start() -> None:
            self._manager.start_auto_backup(
                on_backup=self._auto_backup_created,
                on_error=self.operation_failed.emit,
                on_stopped=lambda: self.auto_state_changed.emit(False),
            )

        self._submit(
            start,
            lambda _result: self.auto_state_changed.emit(
                self._manager.auto_backup_running
            ),
        )

    def stop_auto_backup(self) -> None:
        self._submit(
            self._manager.stop_auto_backup,
            lambda _result: self.auto_state_changed.emit(False),
        )

    def shutdown(self) -> None:
        self._manager.shutdown()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _latest_backup_name(self) -> str:
        entries = self._manager.list_backups()
        if not entries:
            raise LocalizedError(
                "backup_none_available",
                "There are no backups available to restore",
            )
        return entries[0].name

    def _submit(
            self,
            operation: Callable[[], Any],
            on_success: Callable[[Any], None],
    ) -> None:
        self._pending += 1
        if self._pending == 1:
            self.busy_changed.emit(True)
        future = self._executor.submit(operation)
        future.add_done_callback(
            lambda completed: self._complete_future(completed, on_success)
        )

    def _complete_future(
            self,
            future: Future[Any],
            on_success: Callable[[Any], None],
    ) -> None:
        try:
            result = future.result()
        except BaseException as error:
            self._completed.emit((None, None, error))
        else:
            self._completed.emit((on_success, result, None))

    def _complete_preview_future(
            self,
            name: str,
            future: Future[bytes | None],
    ) -> None:
        try:
            result = future.result()
        except BaseException as error:
            self._preview_completed.emit((name, None, error))
        else:
            self._preview_completed.emit((name, result, None))

    @Slot(object)
    def _handle_completion(self, payload: object) -> None:
        on_success, result, error = payload  # type: ignore[misc]
        self._pending = max(0, self._pending - 1)
        if self._pending == 0:
            self.busy_changed.emit(False)
        if error is not None:
            self.operation_failed.emit(error)
            return
        on_success(result)

    @Slot(object)
    def _handle_preview_completion(self, payload: object) -> None:
        name, result, error = payload  # type: ignore[misc]
        if error is not None:
            self.operation_failed.emit(error)
            return
        self.screenshot_loaded.emit(name, result)

    def _created(self, entry: BackupEntry) -> None:
        self.backup_created.emit(entry)
        self.refresh()

    def _restored(self, name: str) -> None:
        self.backup_restored.emit(name)
        self.refresh()

    def _deleted(self, name: str) -> None:
        self.backup_deleted.emit(name)
        self.refresh()

    def _changed(self, entry: BackupEntry) -> None:
        self.backup_changed.emit(entry)
        self.refresh()

    def _auto_backup_created(self, entry: BackupEntry) -> None:
        self.backup_created.emit(entry)
        self.refresh()
