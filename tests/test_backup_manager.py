from __future__ import annotations

import tempfile
import threading
import time
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

from sct.backup_manager import BackupManager
from sct.errors import LocalizedError
from sct.game.save_actions import GameSaveStatus
from sct.settings import AppSettings


class FakeSettingsStore:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def load(self) -> AppSettings:
        return self.settings


class FakeSaveActions:
    def __init__(
            self,
            status: GameSaveStatus,
            *,
            on_request=None,
    ) -> None:
        self.current_status = status
        self.on_request = on_request
        self.requests = 0

    def status(self) -> GameSaveStatus:
        return self.current_status

    def request_save(self) -> None:
        self.requests += 1
        if self.on_request is not None:
            self.on_request()


class BackupManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.appdata = self.root / "AppData" / "Roaming"
        self.save = (
                self.appdata
                / "EldenRing"
                / "76561198000000001"
                / "ER0000.co2"
        )
        self.save.parent.mkdir(parents=True)
        self.save.write_bytes(b"before")
        self.backups = self.root / "backups"
        self.settings = AppSettings(
            steam_id="76561198000000001",
            backup_directory=str(self.backups),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def manager(
            self,
            actions: FakeSaveActions,
            *,
            settings: AppSettings | None = None,
            game_running=lambda: False,
            screenshot_provider=lambda: None,
    ) -> BackupManager:
        return BackupManager(
            settings_store=FakeSettingsStore(settings or self.settings),
            appdata=self.appdata,
            save_actions=actions,
            game_running=game_running,
            screenshot_provider=screenshot_provider,
            save_settle_seconds=0.0,
            save_poll_seconds=0.01,
            auto_poll_seconds=0.02,
        )

    def test_backup_directory_is_mandatory(self) -> None:
        settings = replace(self.settings, backup_directory="")
        manager = self.manager(
            FakeSaveActions(GameSaveStatus(False, False)),
            settings=settings,
        )

        with self.assertRaises(LocalizedError) as raised:
            manager.create_backup()

        self.assertEqual(raised.exception.code, "backup_directory_required")

    def test_manual_backup_archives_existing_save_when_game_is_closed(self) -> None:
        actions = FakeSaveActions(GameSaveStatus(False, False))
        manager = self.manager(actions)

        entry = manager.create_backup()

        self.assertEqual(actions.requests, 0)
        with zipfile.ZipFile(entry.path) as archive:
            self.assertEqual(archive.read("ER0000.co2"), b"before")

    def test_manual_backup_requests_live_game_save_before_archiving(self) -> None:
        actions = FakeSaveActions(
            GameSaveStatus(True, True),
            on_request=lambda: self.save.write_bytes(b"after request"),
        )
        manager = self.manager(actions)

        entry = manager.create_backup()

        self.assertEqual(actions.requests, 1)
        with zipfile.ZipFile(entry.path) as archive:
            self.assertEqual(archive.read("ER0000.co2"), b"after request")

    def test_manual_backup_embeds_screenshot_when_capture_succeeds(self) -> None:
        png = b"\x89PNG\r\n\x1a\ncapture"
        manager = self.manager(
            FakeSaveActions(GameSaveStatus(False, False)),
            screenshot_provider=lambda: png,
        )

        entry = manager.create_backup()

        with zipfile.ZipFile(entry.path) as archive:
            self.assertEqual(archive.read("screenshot.png"), png)
        self.assertEqual(manager.read_backup_screenshot(entry.name), png)

    def test_screenshot_failure_does_not_cancel_save_backup(self) -> None:
        def fail_capture() -> bytes:
            raise OSError("capture unavailable")

        manager = self.manager(
            FakeSaveActions(GameSaveStatus(False, False)),
            screenshot_provider=fail_capture,
        )

        entry = manager.create_backup()

        with zipfile.ZipFile(entry.path) as archive:
            self.assertEqual(archive.namelist(), ["ER0000.co2"])

    def test_restore_is_blocked_while_game_is_running(self) -> None:
        actions = FakeSaveActions(GameSaveStatus(False, False))
        manager = self.manager(actions, game_running=lambda: True)
        entry = manager.create_backup()

        with self.assertRaises(LocalizedError) as raised:
            manager.restore_backup(entry.name)

        self.assertEqual(raised.exception.code, "backup_restore_game_running")

    def test_restore_creates_insurance_backup_before_replacing_save(self) -> None:
        actions = FakeSaveActions(GameSaveStatus(False, False))
        manager = self.manager(actions)
        entry = manager.create_backup()
        self.save.write_bytes(b"new progress")

        manager.restore_backup(entry.name)

        self.assertEqual(self.save.read_bytes(), b"before")
        insurance = [
            item
            for item in manager.list_backups()
            if item.name.startswith("before_restore_")
        ]
        self.assertEqual(len(insurance), 1)
        with zipfile.ZipFile(insurance[0].path) as archive:
            self.assertEqual(archive.read("ER0000.co2"), b"new progress")

    def test_fixed_interval_auto_backup_runs_immediately(self) -> None:
        actions = FakeSaveActions(GameSaveStatus(True, True))
        manager = self.manager(actions)
        created = threading.Event()

        manager.start_auto_backup(on_backup=lambda _entry: created.set())
        self.assertTrue(created.wait(2.0))
        manager.stop_auto_backup()

        self.assertFalse(manager.auto_backup_running)
        self.assertGreaterEqual(actions.requests, 1)
        self.assertEqual(len(manager.list_backups()), 1)

    def test_monitor_auto_backup_archives_changed_save_without_forcing_save(self) -> None:
        settings = replace(
            self.settings,
            backup_method=1,
            sleep_between_saves=0,
        )
        actions = FakeSaveActions(GameSaveStatus(True, True))
        manager = self.manager(actions, settings=settings)
        created = threading.Event()

        manager.start_auto_backup(on_backup=lambda _entry: created.set())
        time.sleep(0.05)
        self.save.write_bytes(b"game changed the save")
        self.assertTrue(created.wait(2.0))
        manager.stop_auto_backup()

        self.assertEqual(actions.requests, 0)
        self.assertEqual(len(manager.list_backups()), 1)


if __name__ == "__main__":
    unittest.main()
