from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from sct.backups import BackupEntry, BackupRepository, SaveLocator
from sct.errors import LocalizedError
from sct.game.save_actions import (
    GameSaveStatus,
    build_elden_ring_save_actions,
)
from sct.settings import AppSettings, SettingsStore
from sct.steam import iter_windows_process_names

LOGGER = logging.getLogger("sct.backup_manager")


class SettingsStoreProtocol(Protocol):
    def load(self) -> AppSettings: ...


class SaveActionsProtocol(Protocol):
    def status(self) -> GameSaveStatus: ...

    def request_save(self) -> None: ...


BackupCallback = Callable[[BackupEntry], None]
ErrorCallback = Callable[[BaseException], None]
StoppedCallback = Callable[[], None]


class BackupManager:
    def __init__(
            self,
            *,
            settings_store: SettingsStoreProtocol,
            appdata: Path | str | None = None,
            save_actions: SaveActionsProtocol,
            game_running: Callable[[], bool],
            screenshot_provider: Callable[[], bytes | None] | None = None,
            save_settle_seconds: float = 0.75,
            save_poll_seconds: float = 0.1,
            save_wait_timeout: float = 5.0,
            auto_poll_seconds: float = 0.5,
    ) -> None:
        roaming = appdata or os.environ.get("APPDATA")
        self._appdata = (
            Path(roaming)
            if roaming is not None
            else Path.home() / "AppData" / "Roaming"
        )
        self._settings_store = settings_store
        self._save_actions = save_actions
        self._game_running = game_running
        self._screenshot_provider = screenshot_provider or (lambda: None)
        self._save_settle_seconds = max(0.0, save_settle_seconds)
        self._save_poll_seconds = max(0.01, save_poll_seconds)
        self._save_wait_timeout = max(
            self._save_settle_seconds,
            save_wait_timeout,
        )
        self._auto_poll_seconds = max(0.01, auto_poll_seconds)
        self._operation_lock = threading.RLock()
        self._auto_lock = threading.Lock()
        self._auto_stop = threading.Event()
        self._auto_thread: threading.Thread | None = None

    @property
    def auto_backup_running(self) -> bool:
        with self._auto_lock:
            return self._auto_thread is not None

    def list_backups(self) -> tuple[BackupEntry, ...]:
        settings = self._settings_store.load()
        return self._repository(settings).list_entries()

    def read_backup_screenshot(self, name: str) -> bytes | None:
        with self._operation_lock:
            settings = self._settings_store.load()
            return self._repository(settings).read_screenshot(name)

    def create_backup(self) -> BackupEntry:
        with self._operation_lock:
            return self._create_backup(force_game_save=True)

    def restore_backup(self, name: str) -> Path:
        if self._game_running():
            raise LocalizedError(
                "backup_restore_game_running",
                "Elden Ring must be closed before restoring a backup",
            )
        with self._operation_lock:
            settings = self._settings_store.load()
            repository = self._repository(settings)
            save_path = self._locator().target_for_restore(
                settings.save_file_type,
                settings.steam_id,
            )
            if save_path.is_file():
                repository.create(save_path, prefix="before_restore")
            restored = repository.restore(name, save_path)
            repository.enforce_limit(settings.max_backups)
            return restored

    def delete_backup(self, name: str) -> None:
        with self._operation_lock:
            settings = self._settings_store.load()
            self._repository(settings).delete(name)

    def set_backup_pinned(self, name: str, pinned: bool) -> BackupEntry:
        with self._operation_lock:
            settings = self._settings_store.load()
            return self._repository(settings).set_pinned(name, pinned)

    def rename_backup(self, name: str, new_name: str) -> BackupEntry:
        with self._operation_lock:
            settings = self._settings_store.load()
            return self._repository(settings).rename(name, new_name)

    def start_auto_backup(
            self,
            *,
            on_backup: BackupCallback | None = None,
            on_error: ErrorCallback | None = None,
            on_stopped: StoppedCallback | None = None,
    ) -> None:
        settings = self._settings_store.load()
        self._repository(settings)
        self._locator().resolve(settings.save_file_type, settings.steam_id)
        status = self._save_actions.status()
        if not status.process_running:
            raise LocalizedError(
                "backup_auto_game_not_running",
                "Elden Ring must be running before automatic backups can start",
            )
        if not status.player_loaded:
            raise LocalizedError(
                "backup_player_not_loaded",
                "The local Elden Ring player must be loaded",
            )

        with self._auto_lock:
            if self._auto_thread is not None:
                raise LocalizedError(
                    "backup_auto_already_running",
                    "Automatic backup is already running",
                )
            self._auto_stop.clear()
            thread = threading.Thread(
                target=self._auto_worker,
                args=(settings, on_backup, on_error, on_stopped),
                name="sct-auto-backup",
                daemon=True,
            )
            self._auto_thread = thread
            thread.start()

    def stop_auto_backup(self) -> None:
        with self._auto_lock:
            thread = self._auto_thread
            self._auto_stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)

    def shutdown(self) -> None:
        self.stop_auto_backup()

    def _create_backup(
            self,
            *,
            force_game_save: bool,
            settings: AppSettings | None = None,
            stop_event: threading.Event | None = None,
    ) -> BackupEntry:
        active_settings = settings or self._settings_store.load()
        repository = self._repository(active_settings)
        save_path = self._locator().resolve(
            active_settings.save_file_type,
            active_settings.steam_id,
        )
        if force_game_save:
            status = self._save_actions.status()
            if status.process_running and status.player_loaded:
                self._save_actions.request_save()
                self._wait_until_stable(save_path, stop_event=stop_event)
        entry = repository.create(
            save_path,
            screenshot=self._capture_screenshot(),
        )
        repository.enforce_limit(active_settings.max_backups)
        return entry

    def _auto_worker(
            self,
            settings: AppSettings,
            on_backup: BackupCallback | None,
            on_error: ErrorCallback | None,
            on_stopped: StoppedCallback | None,
    ) -> None:
        try:
            if settings.backup_method == 0:
                self._interval_worker(settings, on_backup, on_error)
            else:
                self._monitor_worker(settings, on_backup, on_error)
        finally:
            with self._auto_lock:
                if self._auto_thread is threading.current_thread():
                    self._auto_thread = None
            if on_stopped is not None:
                on_stopped()

    def _interval_worker(
            self,
            settings: AppSettings,
            on_backup: BackupCallback | None,
            on_error: ErrorCallback | None,
    ) -> None:
        interval_seconds = max(1.0, settings.auto_backup_interval * 60.0)
        while not self._auto_stop.is_set():
            if not self._continue_auto_backup():
                return
            try:
                with self._operation_lock:
                    entry = self._create_backup(
                        force_game_save=True,
                        settings=settings,
                        stop_event=self._auto_stop,
                    )
                if on_backup is not None:
                    on_backup(entry)
            except Exception as error:
                LOGGER.exception("Automatic interval backup failed")
                if on_error is not None:
                    on_error(error)
            if self._auto_stop.wait(interval_seconds):
                return

    def _monitor_worker(
            self,
            settings: AppSettings,
            on_backup: BackupCallback | None,
            on_error: ErrorCallback | None,
    ) -> None:
        save_path = self._locator().resolve(
            settings.save_file_type,
            settings.steam_id,
        )
        previous = self._file_signature(save_path)
        cooldown = max(0.0, float(settings.sleep_between_saves))
        while not self._auto_stop.wait(self._auto_poll_seconds):
            if not self._continue_auto_backup():
                return
            current = self._file_signature(save_path)
            if current == previous:
                continue
            try:
                self._wait_until_stable(save_path, stop_event=self._auto_stop)
                with self._operation_lock:
                    entry = self._create_backup(
                        force_game_save=False,
                        settings=settings,
                    )
                previous = self._file_signature(save_path)
                if on_backup is not None:
                    on_backup(entry)
            except Exception as error:
                LOGGER.exception("Automatic monitored backup failed")
                previous = self._file_signature(save_path)
                if on_error is not None:
                    on_error(error)
            if cooldown and self._auto_stop.wait(cooldown):
                return

    def _continue_auto_backup(self) -> bool:
        try:
            status = self._save_actions.status()
        except Exception:
            LOGGER.exception("Unable to inspect automatic backup status")
            return False
        return status.process_running and status.player_loaded

    def _wait_until_stable(
            self,
            path: Path,
            *,
            stop_event: threading.Event | None = None,
    ) -> None:
        deadline = time.monotonic() + self._save_wait_timeout
        previous = self._file_signature(path)
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            if time.monotonic() - stable_since >= self._save_settle_seconds:
                return
            if stop_event is None:
                time.sleep(self._save_poll_seconds)
            elif stop_event.wait(self._save_poll_seconds):
                return
            current = self._file_signature(path)
            if current != previous:
                previous = current
                stable_since = time.monotonic()

    def _repository(self, settings: AppSettings) -> BackupRepository:
        value = settings.backup_directory.strip()
        if not value:
            raise LocalizedError(
                "backup_directory_required",
                "A backup directory must be selected",
            )
        directory = Path(value).expanduser()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise LocalizedError(
                "backup_directory_invalid",
                f"Unable to use backup directory {directory}: {error}",
                params={"path": directory},
            ) from error
        if not directory.is_dir():
            raise LocalizedError(
                "backup_directory_invalid",
                f"Backup path is not a directory: {directory}",
                params={"path": directory},
            )
        return BackupRepository(directory)

    def _capture_screenshot(self) -> bytes | None:
        try:
            return self._screenshot_provider()
        except Exception as error:
            LOGGER.debug("Unable to capture backup screenshot: %s", error)
            return None

    def _locator(self) -> SaveLocator:
        return SaveLocator(self._appdata)

    @staticmethod
    def _file_signature(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size


def elden_ring_is_running() -> bool:
    try:
        return any(
            name.casefold() == "eldenring.exe"
            for name in iter_windows_process_names()
        )
    except OSError:
        return False


def build_backup_manager(
        settings_store: SettingsStore,
        *,
        screenshot_provider: Callable[[], bytes | None] | None = None,
) -> BackupManager:
    return BackupManager(
        settings_store=settings_store,
        save_actions=build_elden_ring_save_actions(),
        game_running=elden_ring_is_running,
        screenshot_provider=screenshot_provider,
    )
