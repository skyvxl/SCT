from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from pathlib import Path

from sct.backups import SUPPORTED_SAVE_FILES, BackupRepository, SaveLocator
from sct.errors import LocalizedError
from sct.settings import SettingsStore, default_settings_path

SAVE_MAGIC = 0x34444E42
SAVE_SIZE = 28_967_888
SAVE_SLOTS = 10
SAVE_LENGTH = 2_621_440
HEADER_LENGTH = 588
CHAR_NAME_LENGTH = 34

SLOT_DATA_OFFSET = 784
SLOT_RECORD_LENGTH = SAVE_LENGTH + 16
FOOTER_MD5_OFFSET = 26_215_328
FOOTER_DATA_OFFSET = 26_215_344
FOOTER_DATA_LENGTH = 393_216
STEAM_ID_OFFSET = 26_215_348
ACTIVE_FLAGS_OFFSET = 26_221_828
HEADERS_OFFSET = 26_221_838
STATS_SEARCH_LENGTH = 120_000
STATS_LEVEL_OFFSET = 44


@dataclass(frozen=True, slots=True)
class CharacterSlot:
    index: int
    active: bool
    name: str
    level: int
    seconds_played: int
    data: bytes
    header: bytes


@dataclass(frozen=True, slots=True)
class SaveDocument:
    path: Path | None
    steam_id: int
    slots: tuple[CharacterSlot, ...]
    payload: bytes


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    modified_ns: int
    size: int


@dataclass(frozen=True, slots=True)
class LoadedSave:
    document: SaveDocument
    fingerprint: FileFingerprint


@dataclass(frozen=True, slots=True)
class ArchiveCharacter:
    name: str
    level: int
    seconds_played: int
    steam_id: int | None
    data: bytes
    header: bytes


@dataclass(frozen=True, slots=True)
class CharacterStats:
    vigor: int
    mind: int
    endurance: int
    strength: int
    dexterity: int
    intelligence: int
    faith: int
    arcane: int
    seconds_played: int
    offset: int

    @property
    def attributes(self) -> tuple[int, ...]:
        return (
            self.vigor,
            self.mind,
            self.endurance,
            self.strength,
            self.dexterity,
            self.intelligence,
            self.faith,
            self.arcane,
        )

    @property
    def level(self) -> int:
        return sum(self.attributes) - 79


class EldenRingSaveCodec:
    def load(self, path: Path | str) -> SaveDocument:
        source = Path(path)
        try:
            payload = source.read_bytes()
        except OSError as error:
            raise LocalizedError(
                "character_save_read_failed",
                f"Unable to read Elden Ring save {source}: {error}",
                params={"path": source},
            ) from error
        return self.parse(payload, source)

    def parse(
            self,
            data: bytes,
            path: Path | str | None = None,
    ) -> SaveDocument:
        if len(data) != SAVE_SIZE:
            raise LocalizedError(
                "character_save_size_invalid",
                f"Unexpected Elden Ring save size: {len(data)}",
                params={"actual": len(data), "expected": SAVE_SIZE},
            )
        magic = struct.unpack_from("<I", data, 0)[0]
        if magic != SAVE_MAGIC:
            raise LocalizedError(
                "character_save_magic_invalid",
                f"Unexpected Elden Ring save magic: {magic:#x}",
            )

        slots: list[CharacterSlot] = []
        for index in range(SAVE_SLOTS):
            data_offset = SLOT_DATA_OFFSET + index * SLOT_RECORD_LENGTH
            slot_data = data[data_offset:data_offset + SAVE_LENGTH]
            expected_md5 = data[data_offset - 16:data_offset]
            actual_md5 = hashlib.md5(slot_data).digest()
            if actual_md5 != expected_md5:
                raise LocalizedError(
                    "character_save_slot_checksum_invalid",
                    f"Invalid checksum for character slot {index + 1}",
                    params={"slot": index + 1},
                )

            header_offset = HEADERS_OFFSET + index * HEADER_LENGTH
            header = data[header_offset:header_offset + HEADER_LENGTH]
            slots.append(
                CharacterSlot(
                    index=index,
                    active=bool(data[ACTIVE_FLAGS_OFFSET + index]),
                    name=self._decode_name(header[:CHAR_NAME_LENGTH]),
                    level=struct.unpack_from("<I", header, 34)[0],
                    seconds_played=struct.unpack_from("<I", header, 38)[0],
                    data=slot_data,
                    header=header,
                )
            )

        footer = data[FOOTER_DATA_OFFSET:FOOTER_DATA_OFFSET + FOOTER_DATA_LENGTH]
        expected_footer_md5 = data[FOOTER_MD5_OFFSET:FOOTER_MD5_OFFSET + 16]
        if hashlib.md5(footer).digest() != expected_footer_md5:
            raise LocalizedError(
                "character_save_footer_checksum_invalid",
                "Invalid Elden Ring save footer checksum",
            )

        steam_id = struct.unpack_from("<Q", data, STEAM_ID_OFFSET)[0]
        return SaveDocument(
            path=Path(path) if path is not None else None,
            steam_id=steam_id,
            slots=tuple(slots),
            payload=data,
        )

    def serialize(self, document: SaveDocument) -> bytes:
        if len(document.payload) != SAVE_SIZE or len(document.slots) != SAVE_SLOTS:
            raise LocalizedError(
                "character_save_structure_invalid",
                "The in-memory Elden Ring save structure is incomplete",
            )

        payload = bytearray(document.payload)
        struct.pack_into("<Q", payload, STEAM_ID_OFFSET, document.steam_id)
        for index, slot in enumerate(document.slots):
            if slot.index != index:
                raise LocalizedError(
                    "character_save_structure_invalid",
                    f"Character slot index {slot.index} is out of order",
                )
            if len(slot.data) != SAVE_LENGTH or len(slot.header) != HEADER_LENGTH:
                raise LocalizedError(
                    "character_save_structure_invalid",
                    f"Character slot {index + 1} has invalid data lengths",
                )

            data_offset = SLOT_DATA_OFFSET + index * SLOT_RECORD_LENGTH
            payload[data_offset:data_offset + SAVE_LENGTH] = slot.data
            payload[data_offset - 16:data_offset] = hashlib.md5(slot.data).digest()

            header = bytearray(slot.header)
            header[:CHAR_NAME_LENGTH] = self._encode_name(slot.name)
            struct.pack_into("<I", header, 34, slot.level)
            struct.pack_into("<I", header, 38, slot.seconds_played)
            header_offset = HEADERS_OFFSET + index * HEADER_LENGTH
            payload[header_offset:header_offset + HEADER_LENGTH] = header
            payload[ACTIVE_FLAGS_OFFSET + index] = int(slot.active)

        footer = payload[FOOTER_DATA_OFFSET:FOOTER_DATA_OFFSET + FOOTER_DATA_LENGTH]
        payload[FOOTER_MD5_OFFSET:FOOTER_MD5_OFFSET + 16] = hashlib.md5(footer).digest()
        return bytes(payload)

    @staticmethod
    def _decode_name(raw_name: bytes) -> str:
        return raw_name.decode("utf-16-le", errors="ignore").split("\0", 1)[0]

    @staticmethod
    def _encode_name(name: str) -> bytes:
        encoded = name.encode("utf-16-le")
        if len(encoded) > CHAR_NAME_LENGTH - 2:
            raise LocalizedError(
                "character_name_too_long",
                f"Character name is too long: {name!r}",
            )
        return encoded.ljust(CHAR_NAME_LENGTH, b"\0")


class CharacterArchiveRepository:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = (
            Path(path)
            if path is not None
            else default_settings_path().parent / "CharacterManager.json"
        )

    def load(self) -> tuple[ArchiveCharacter, ...]:
        if not self.path.is_file():
            return ()
        return self.load_from(self.path)

    def load_from(self, path: Path | str) -> tuple[ArchiveCharacter, ...]:
        source = Path(path)
        try:
            raw_entries = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(raw_entries, list):
                raise TypeError("archive root is not a list")
            return tuple(self._decode_entry(entry) for entry in raw_entries)
        except LocalizedError:
            raise
        except (OSError, TypeError, ValueError, KeyError) as error:
            raise LocalizedError(
                "character_archive_read_failed",
                f"Unable to read character archive {source}: {error}",
                params={"path": source},
            ) from error

    def save(self, entries: Iterable[ArchiveCharacter]) -> None:
        encoded = [self._encode_entry(entry) for entry in entries]
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
                json.dump(encoded, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise LocalizedError(
                "character_archive_write_failed",
                f"Unable to write character archive {self.path}: {error}",
                params={"path": self.path},
            ) from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _decode_entry(raw: object) -> ArchiveCharacter:
        if not isinstance(raw, dict):
            raise TypeError("character entry is not an object")
        data = bytes.fromhex(str(raw["data"]))
        header = bytes.fromhex(str(raw["header"]))
        if len(data) != SAVE_LENGTH or len(header) != HEADER_LENGTH:
            raise ValueError("character entry has invalid binary lengths")
        raw_steam_id = raw.get("steam_id")
        steam_id = int(raw_steam_id) if raw_steam_id not in (None, "") else None
        return ArchiveCharacter(
            name=str(raw["name"]),
            level=int(raw["level"]),
            seconds_played=int(raw["seconds_played"]),
            steam_id=steam_id,
            data=data,
            header=header,
        )

    @staticmethod
    def _encode_entry(entry: ArchiveCharacter) -> dict[str, object]:
        return {
            "name": entry.name,
            "level": entry.level,
            "seconds_played": entry.seconds_played,
            "steam_id": str(entry.steam_id) if entry.steam_id is not None else None,
            "data": entry.data.hex(),
            "header": entry.header.hex(),
        }


def archive_identity(character: ArchiveCharacter) -> tuple[str, int]:
    return character.name.strip().casefold(), character.level


def archive_from_slot(slot: CharacterSlot, steam_id: int | None) -> ArchiveCharacter:
    if not slot.active:
        raise LocalizedError(
            "character_slot_inactive",
            f"Character slot {slot.index + 1} is inactive",
            params={"slot": slot.index + 1},
        )
    return ArchiveCharacter(
        name=slot.name,
        level=slot.level,
        seconds_played=slot.seconds_played,
        steam_id=steam_id,
        data=slot.data,
        header=slot.header,
    )


def clear_slot(slot: CharacterSlot) -> CharacterSlot:
    return CharacterSlot(
        index=slot.index,
        active=False,
        name="",
        level=0,
        seconds_played=0,
        data=bytes(SAVE_LENGTH),
        header=bytes(HEADER_LENGTH),
    )


def replace_document_slot(
        document: SaveDocument,
        index: int,
        slot: CharacterSlot,
) -> SaveDocument:
    if index < 0 or index >= SAVE_SLOTS:
        raise LocalizedError(
            "character_slot_invalid",
            f"Invalid character slot index: {index}",
            params={"slot": index + 1},
        )
    slots = list(document.slots)
    slots[index] = dataclass_replace(slot, index=index)
    return dataclass_replace(document, slots=tuple(slots))


def install_archived_character(
        document: SaveDocument,
        character: ArchiveCharacter,
        index: int,
) -> SaveDocument:
    data = character.data
    if character.steam_id is not None and character.steam_id != document.steam_id:
        old_id = struct.pack("<Q", character.steam_id)
        new_id = struct.pack("<Q", document.steam_id)
        data = data.replace(old_id, new_id)
    slot = CharacterSlot(
        index=index,
        active=True,
        name=character.name,
        level=character.level,
        seconds_played=character.seconds_played,
        data=data,
        header=character.header,
    )
    return replace_document_slot(document, index, slot)


def find_character_stats(slot: CharacterSlot) -> CharacterStats:
    data = slot.data
    candidates: list[CharacterStats] = []
    limit = min(STATS_SEARCH_LENGTH, len(data) - STATS_LEVEL_OFFSET - 2)
    for offset in range(max(limit, 0)):
        stored_level = struct.unpack_from("<H", data, offset + STATS_LEVEL_OFFSET)[0]
        if stored_level != slot.level:
            continue
        values = tuple(data[offset + index * 4] for index in range(8))
        if not all(1 <= value <= 99 for value in values):
            continue
        if sum(values) - 79 != slot.level:
            continue
        candidates.append(
            CharacterStats(
                vigor=values[0],
                mind=values[1],
                endurance=values[2],
                strength=values[3],
                dexterity=values[4],
                intelligence=values[5],
                faith=values[6],
                arcane=values[7],
                seconds_played=slot.seconds_played,
                offset=offset,
            )
        )
    if len(candidates) != 1:
        raise LocalizedError(
            "character_stats_not_found",
            f"Expected one stats block in slot {slot.index + 1}, found {len(candidates)}",
            params={"slot": slot.index + 1},
        )
    return candidates[0]


def update_character_stats(
        slot: CharacterSlot,
        stats: CharacterStats,
) -> CharacterSlot:
    if not all(1 <= value <= 99 for value in stats.attributes):
        raise LocalizedError(
            "character_stats_invalid",
            "Character attributes must be between 1 and 99",
        )
    if stats.level < 1 or stats.seconds_played < 0:
        raise LocalizedError(
            "character_stats_invalid",
            "Character level or play time is invalid",
        )
    if stats.offset < 0 or stats.offset + STATS_LEVEL_OFFSET + 2 > len(slot.data):
        raise LocalizedError(
            "character_stats_invalid",
            "Character stats offset is outside the slot data",
        )

    data = bytearray(slot.data)
    for index, value in enumerate(stats.attributes):
        data[stats.offset + index * 4] = value
    struct.pack_into("<H", data, stats.offset + STATS_LEVEL_OFFSET, stats.level)

    header = bytearray(slot.header)
    struct.pack_into("<I", header, 34, stats.level)
    struct.pack_into("<I", header, 38, stats.seconds_played)
    return dataclass_replace(
        slot,
        level=stats.level,
        seconds_played=stats.seconds_played,
        data=bytes(data),
        header=bytes(header),
    )


class CharacterManagerService:
    def __init__(
            self,
            settings_store: SettingsStore,
            *,
            appdata: Path | str | None = None,
            game_running: Callable[[], bool] | None = None,
            codec: EldenRingSaveCodec | None = None,
    ) -> None:
        self.settings_store = settings_store
        if appdata is None:
            roaming = os.environ.get("APPDATA")
            self.appdata = (
                Path(roaming)
                if roaming
                else Path.home() / "AppData" / "Roaming"
            )
        else:
            self.appdata = Path(appdata)
        if game_running is None:
            from sct.backup_manager import elden_ring_is_running

            self._game_running = elden_ring_is_running
        else:
            self._game_running = game_running
        self.codec = codec or EldenRingSaveCodec()

    def configured_save_path(self) -> Path:
        settings = self.settings_store.load()
        return SaveLocator(self.appdata).resolve(
            settings.save_file_type,
            settings.steam_id,
        )

    def load_save(self, path: Path | str | None = None) -> LoadedSave:
        source = self.configured_save_path() if path is None else Path(path)
        if source.name not in SUPPORTED_SAVE_FILES:
            raise LocalizedError(
                "character_save_type_invalid",
                f"Unsupported Elden Ring save file: {source}",
                params={"path": source},
            )
        document = self.codec.load(source)
        return LoadedSave(document=document, fingerprint=self._fingerprint(source))

    def mutate_save(
            self,
            loaded: LoadedSave,
            mutator: Callable[[SaveDocument], SaveDocument],
    ) -> LoadedSave:
        path = loaded.document.path
        if path is None:
            raise LocalizedError(
                "character_save_path_missing",
                "The loaded Elden Ring save has no source path",
            )
        if self._game_running():
            raise LocalizedError(
                "character_game_running",
                "Elden Ring must be closed before changing a save",
            )
        if self._fingerprint(path) != loaded.fingerprint:
            raise LocalizedError(
                "character_save_changed",
                f"Elden Ring save changed after it was loaded: {path}",
                params={"path": path},
            )

        settings = self.settings_store.load()
        if not settings.backup_directory.strip():
            raise LocalizedError(
                "backup_directory_required",
                "A backup directory is required before changing a character",
            )

        current = self.codec.load(path)
        BackupRepository(settings.backup_directory).create(
            path,
            prefix="before_character_change",
        )
        changed = mutator(current)
        serialized = self.codec.serialize(changed)
        self._atomic_validated_replace(path, serialized)
        return self.load_save(path)

    def _atomic_validated_replace(self, path: Path, payload: bytes) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                    "wb",
                    delete=False,
                    dir=path.parent,
                    prefix=f".{path.name}.",
                    suffix=".tmp",
            ) as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            self.codec.load(temporary_path)
            os.replace(temporary_path, path)
        except LocalizedError:
            raise
        except OSError as error:
            raise LocalizedError(
                "character_save_write_failed",
                f"Unable to safely replace Elden Ring save {path}: {error}",
                params={"path": path},
            ) from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _fingerprint(path: Path) -> FileFingerprint:
        try:
            stat = path.stat()
        except OSError as error:
            raise LocalizedError(
                "character_save_read_failed",
                f"Unable to stat Elden Ring save {path}: {error}",
                params={"path": path},
            ) from error
        return FileFingerprint(modified_ns=stat.st_mtime_ns, size=stat.st_size)
