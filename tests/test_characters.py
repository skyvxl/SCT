from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from sct.characters import (
    ACTIVE_FLAGS_OFFSET,
    FOOTER_DATA_LENGTH,
    FOOTER_DATA_OFFSET,
    FOOTER_MD5_OFFSET,
    HEADER_LENGTH,
    HEADERS_OFFSET,
    SAVE_LENGTH,
    SAVE_MAGIC,
    SAVE_SIZE,
    SAVE_SLOTS,
    SLOT_DATA_OFFSET,
    SLOT_RECORD_LENGTH,
    STEAM_ID_OFFSET,
    CharacterArchiveRepository,
    CharacterManagerService,
    CharacterStats,
    EldenRingSaveCodec,
    archive_from_slot,
    archive_identity,
    clear_slot,
    find_character_stats,
    install_archived_character,
    update_character_stats,
)
from sct.errors import LocalizedError
from sct.settings import AppSettings, SettingsStore


def _encode_name(name: str) -> bytes:
    return name.encode("utf-16-le").ljust(34, b"\0")


def valid_save_bytes() -> bytes:
    payload = bytearray(SAVE_SIZE)
    struct.pack_into("<I", payload, 0, SAVE_MAGIC)
    struct.pack_into("<Q", payload, STEAM_ID_OFFSET, 76561198000000001)
    for index in range(SAVE_SLOTS):
        data_offset = SLOT_DATA_OFFSET + index * SLOT_RECORD_LENGTH
        slot_data = bytes([index + 1]) + bytes(SAVE_LENGTH - 1)
        payload[data_offset:data_offset + SAVE_LENGTH] = slot_data
        payload[data_offset - 16:data_offset] = hashlib.md5(slot_data).digest()

        header_offset = HEADERS_OFFSET + index * HEADER_LENGTH
        if index == 0:
            payload[ACTIVE_FLAGS_OFFSET + index] = 1
            payload[header_offset:header_offset + 34] = _encode_name("Tarnished")
            struct.pack_into("<I", payload, header_offset + 34, 42)
            struct.pack_into("<I", payload, header_offset + 38, 3_723)

    footer = payload[FOOTER_DATA_OFFSET:FOOTER_DATA_OFFSET + FOOTER_DATA_LENGTH]
    payload[FOOTER_MD5_OFFSET:FOOTER_MD5_OFFSET + 16] = hashlib.md5(footer).digest()
    return bytes(payload)


class EldenRingSaveCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = valid_save_bytes()
        cls.codec = EldenRingSaveCodec()

    def test_parse_reads_all_slots_and_account_metadata(self) -> None:
        document = self.codec.parse(self.payload, Path("ER0000.co2"))

        self.assertEqual(document.path, Path("ER0000.co2"))
        self.assertEqual(document.steam_id, 76561198000000001)
        self.assertEqual(len(document.slots), 10)
        self.assertTrue(document.slots[0].active)
        self.assertEqual(document.slots[0].name, "Tarnished")
        self.assertEqual(document.slots[0].level, 42)
        self.assertEqual(document.slots[0].seconds_played, 3_723)
        self.assertFalse(document.slots[1].active)
        self.assertEqual(document.slots[1].index, 1)

    def test_parse_rejects_wrong_size_and_magic(self) -> None:
        with self.assertRaises(LocalizedError) as size_error:
            self.codec.parse(self.payload[:-1])
        self.assertEqual(size_error.exception.code, "character_save_size_invalid")

        corrupted = bytearray(self.payload)
        struct.pack_into("<I", corrupted, 0, 0)
        with self.assertRaises(LocalizedError) as magic_error:
            self.codec.parse(bytes(corrupted))
        self.assertEqual(magic_error.exception.code, "character_save_magic_invalid")

    def test_parse_rejects_slot_and_footer_checksum_mismatches(self) -> None:
        corrupted_slot = bytearray(self.payload)
        corrupted_slot[SLOT_DATA_OFFSET + 100] ^= 0xFF
        with self.assertRaises(LocalizedError) as slot_error:
            self.codec.parse(bytes(corrupted_slot))
        self.assertEqual(slot_error.exception.code, "character_save_slot_checksum_invalid")
        self.assertEqual(slot_error.exception.params["slot"], 1)

        corrupted_footer = bytearray(self.payload)
        corrupted_footer[FOOTER_DATA_OFFSET + 100] ^= 0xFF
        with self.assertRaises(LocalizedError) as footer_error:
            self.codec.parse(bytes(corrupted_footer))
        self.assertEqual(footer_error.exception.code, "character_save_footer_checksum_invalid")

    def test_serialize_updates_headers_steam_id_and_checksums(self) -> None:
        document = self.codec.parse(self.payload)
        first = replace(
            document.slots[0],
            name="Melina",
            level=75,
            seconds_played=9_001,
        )
        changed = replace(
            document,
            steam_id=76561198000000002,
            slots=(first, *document.slots[1:]),
        )

        serialized = self.codec.serialize(changed)
        reparsed = self.codec.parse(serialized)

        self.assertEqual(reparsed.steam_id, 76561198000000002)
        self.assertEqual(reparsed.slots[0].name, "Melina")
        self.assertEqual(reparsed.slots[0].level, 75)
        self.assertEqual(reparsed.slots[0].seconds_played, 9_001)


class CharacterArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = EldenRingSaveCodec().parse(valid_save_bytes())

    def test_repository_reads_old_scmm_json_and_writes_it_atomically(self) -> None:
        slot = self.document.slots[0]
        old_record = {
            "name": slot.name,
            "level": slot.level,
            "seconds_played": slot.seconds_played,
            "steam_id": str(self.document.steam_id),
            "data": slot.data.hex(),
            "header": slot.header.hex(),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "CharacterManager.json"
            path.write_text(json.dumps([old_record]), encoding="utf-8")
            repository = CharacterArchiveRepository(path)

            loaded = repository.load()
            repository.save(loaded)
            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "Tarnished")
        self.assertEqual(loaded[0].steam_id, self.document.steam_id)
        self.assertEqual(saved[0]["data"], slot.data.hex())
        self.assertEqual(saved[0]["steam_id"], str(self.document.steam_id))

    def test_archive_identity_normalizes_name_but_keeps_level(self) -> None:
        first = archive_from_slot(self.document.slots[0], self.document.steam_id)
        second = replace(first, name="  TARNISHED ")

        self.assertEqual(archive_identity(first), archive_identity(second))
        self.assertNotEqual(
            archive_identity(first),
            archive_identity(replace(second, level=first.level + 1)),
        )

    def test_install_rewrites_embedded_steam_id_and_uses_requested_slot(self) -> None:
        source_id = self.document.steam_id
        target_id = source_id + 1
        source_bytes = struct.pack("<Q", source_id)
        slot = self.document.slots[0]
        data = bytearray(slot.data)
        data[100:108] = source_bytes
        data[500:508] = source_bytes
        archive = replace(
            archive_from_slot(replace(slot, data=bytes(data)), source_id),
            name="Copied",
        )
        target = replace(self.document, steam_id=target_id)

        changed = install_archived_character(target, archive, 4)
        installed = changed.slots[4]

        self.assertTrue(installed.active)
        self.assertEqual(installed.name, "Copied")
        self.assertEqual(
            installed.data.count(struct.pack("<Q", target_id)),
            2,
        )
        self.assertNotIn(source_bytes, installed.data)

    def test_clear_slot_removes_all_character_content(self) -> None:
        cleared = clear_slot(self.document.slots[0])

        self.assertFalse(cleared.active)
        self.assertEqual(cleared.name, "")
        self.assertEqual(cleared.level, 0)
        self.assertEqual(cleared.seconds_played, 0)
        self.assertEqual(cleared.data, bytes(SAVE_LENGTH))
        self.assertEqual(cleared.header, bytes(HEADER_LENGTH))


class CharacterStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        document = EldenRingSaveCodec().parse(valid_save_bytes())
        slot = document.slots[0]
        self.stats_offset = 500
        data = bytearray(slot.data)
        self.original_values = (13, 11, 13, 12, 15, 9, 8, 8)
        for index, value in enumerate(self.original_values):
            data[self.stats_offset + index * 4] = value
        struct.pack_into("<H", data, self.stats_offset + 44, 10)
        self.slot = replace(slot, level=10, data=bytes(data))

    def test_find_character_stats_locates_the_attribute_block(self) -> None:
        located = find_character_stats(self.slot)

        self.assertEqual(located.offset, self.stats_offset)
        self.assertEqual(located.attributes, self.original_values)
        self.assertEqual(located.level, 10)
        self.assertEqual(located.seconds_played, 3_723)

    def test_update_character_stats_changes_data_level_and_playtime(self) -> None:
        edited = CharacterStats(
            vigor=14,
            mind=11,
            endurance=13,
            strength=12,
            dexterity=15,
            intelligence=9,
            faith=8,
            arcane=8,
            seconds_played=7_261,
            offset=self.stats_offset,
        )

        changed = update_character_stats(self.slot, edited)
        rediscovered = find_character_stats(changed)

        self.assertEqual(changed.level, 11)
        self.assertEqual(changed.seconds_played, 7_261)
        self.assertEqual(rediscovered.attributes, edited.attributes)


class CharacterManagerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.appdata = self.root / "Roaming"
        self.steam_id = "76561198000000001"
        self.save_path = self.appdata / "EldenRing" / self.steam_id / "ER0000.co2"
        self.save_path.parent.mkdir(parents=True)
        self.save_path.write_bytes(valid_save_bytes())
        self.backup_directory = self.root / "backups"
        self.settings_store = SettingsStore(self.root / "settings.ini")
        self.settings_store.save(
            AppSettings(
                steam_id=self.steam_id,
                save_file_type="ER0000.co2",
                backup_directory=str(self.backup_directory),
            )
        )
        self.service = CharacterManagerService(
            self.settings_store,
            appdata=self.appdata,
            game_running=lambda: False,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_load_save_uses_selected_account_and_format(self) -> None:
        loaded = self.service.load_save()

        self.assertEqual(loaded.document.path, self.save_path)
        self.assertEqual(loaded.document.slots[0].name, "Tarnished")
        self.assertEqual(loaded.fingerprint.size, SAVE_SIZE)

    def test_mutation_creates_backup_and_atomically_replaces_save(self) -> None:
        loaded = self.service.load_save()

        changed = self.service.mutate_save(
            loaded,
            lambda document: replace(
                document,
                slots=(
                    replace(document.slots[0], name="Renamed"),
                    *document.slots[1:],
                ),
            ),
        )

        self.assertEqual(changed.document.slots[0].name, "Renamed")
        self.assertEqual(
            EldenRingSaveCodec().load(self.save_path).slots[0].name,
            "Renamed",
        )
        backups = tuple(self.backup_directory.glob("before_character_change_*.zip"))
        self.assertEqual(len(backups), 1)

    def test_mutation_requires_backup_directory(self) -> None:
        loaded = self.service.load_save()
        self.settings_store.update(backup_directory="")

        with self.assertRaises(LocalizedError) as raised:
            self.service.mutate_save(loaded, lambda document: document)

        self.assertEqual(raised.exception.code, "backup_directory_required")

    def test_mutation_refuses_to_write_while_game_is_running(self) -> None:
        service = CharacterManagerService(
            self.settings_store,
            appdata=self.appdata,
            game_running=lambda: True,
        )
        loaded = service.load_save()

        with self.assertRaises(LocalizedError) as raised:
            service.mutate_save(loaded, lambda document: document)

        self.assertEqual(raised.exception.code, "character_game_running")
        self.assertFalse(self.backup_directory.exists())

    def test_mutation_rejects_a_save_changed_after_loading(self) -> None:
        loaded = self.service.load_save()
        future = self.save_path.stat().st_mtime + 5
        os.utime(self.save_path, (future, future))

        with self.assertRaises(LocalizedError) as raised:
            self.service.mutate_save(loaded, lambda document: document)

        self.assertEqual(raised.exception.code, "character_save_changed")
        self.assertFalse(self.backup_directory.exists())

    def test_failed_serialization_keeps_original_save(self) -> None:
        loaded = self.service.load_save()
        original = self.save_path.read_bytes()

        with self.assertRaises(LocalizedError):
            self.service.mutate_save(
                loaded,
                lambda document: replace(document, slots=()),
            )

        self.assertEqual(self.save_path.read_bytes(), original)
        self.assertEqual(
            len(tuple(self.backup_directory.glob("before_character_change_*.zip"))),
            1,
        )


if __name__ == "__main__":
    unittest.main()
