from __future__ import annotations

import csv
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import unicodedata


class ItemDataNotFound(FileNotFoundError):
    """Raised when no external Elden Ring item-data directory is available."""

    def __init__(
            self,
            message: str,
            *,
            missing_files: tuple[str, ...] = (),
            checked_locations: tuple[Path, ...] = (),
    ) -> None:
        super().__init__(message)
        self.missing_files = missing_files
        self.checked_locations = checked_locations


class ItemCategory(StrEnum):
    WEAPONS = "weapons"
    AMMUNITION = "ammunition"
    HEADS = "heads"
    CHESTS = "chests"
    GAUNTLETS = "gauntlets"
    LEGGINGS = "leggings"
    TALISMANS = "talismans"
    SPELLS = "spells"
    QUICK_ITEMS = "quick_items"
    PHYSICK_TEARS = "physick_tears"
    ASHES_OF_WAR = "ashes_of_war"
    GEMS = "gems"


CATALOG_FILES: Mapping[ItemCategory, str] = MappingProxyType(
    {
        ItemCategory.WEAPONS: "Weapons.csv",
        ItemCategory.AMMUNITION: "Ammunitions.csv",
        ItemCategory.HEADS: "Heads.csv",
        ItemCategory.CHESTS: "Chests.csv",
        ItemCategory.GAUNTLETS: "Gauntlets.csv",
        ItemCategory.LEGGINGS: "Leggings.csv",
        ItemCategory.TALISMANS: "Talismans.csv",
        ItemCategory.SPELLS: "Spells.csv",
        ItemCategory.QUICK_ITEMS: "QuickItems.csv",
        ItemCategory.PHYSICK_TEARS: "PhysickTears.csv",
        ItemCategory.ASHES_OF_WAR: "AshOfWarsIDs.csv",
        ItemCategory.GEMS: "Gems.csv",
    }
)
REQUIRED_ITEM_FILES = tuple(CATALOG_FILES.values()) + ("images.zip",)


@dataclass(frozen=True, slots=True)
class ItemRecord:
    category: ItemCategory
    id: int
    name: str
    icon_id: int | None
    max_upgrade: int
    raw: Mapping[str, str]


def resolve_items_directory(
        *,
        explicit: Path | str | None = None,
        executable_dir: Path | str | None = None,
        project_root: Path | str | None = None,
) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    if executable_dir is not None:
        candidates.append(Path(executable_dir).expanduser() / "items")
    elif getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "items")
    root = (
        Path(project_root).expanduser()
        if project_root is not None
        else Path(__file__).resolve().parents[2]
    )
    candidates.append(root / "data" / "items")

    checked: list[Path] = []
    closest_missing = REQUIRED_ITEM_FILES
    for candidate in candidates:
        resolved = candidate.resolve()
        checked.append(resolved)
        missing = tuple(
            filename
            for filename in REQUIRED_ITEM_FILES
            if not (resolved / filename).is_file()
        )
        if not missing:
            return resolved
        if len(missing) < len(closest_missing):
            closest_missing = missing
    locations = ", ".join(str(path) for path in checked)
    raise ItemDataNotFound(
        f"Elden Ring item data was not found. Checked: {locations}",
        missing_files=closest_missing,
        checked_locations=tuple(checked),
    )


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.casefold().split())


def _parse_optional_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.casefold().lstrip("+-")
        return int(text, 16 if normalized.startswith("0x") else 10)
    except ValueError:
        return None


def _weapon_max_upgrade(value: object) -> int:
    normalized = _normalize(value)
    if "somber" in normalized:
        return 10
    if "smithing" in normalized:
        return 25
    return 0


class ItemCatalog:
    def __init__(self, root: Path | str, *, locale: str = "ru") -> None:
        self.root = Path(root).resolve()
        self.locale = locale.strip().lower().replace("-", "_") or "en"
        self._items: dict[ItemCategory, tuple[ItemRecord, ...]] = {}
        self._by_id: dict[ItemCategory, dict[int, ItemRecord]] = {}
        self._icon_entries: dict[int, str] | None = None

    def items(self, category: ItemCategory) -> tuple[ItemRecord, ...]:
        category = ItemCategory(category)
        if category not in self._items:
            loaded = self._load_category(category)
            self._items[category] = loaded
            self._by_id[category] = {item.id: item for item in loaded}
        return self._items[category]

    def get(self, category: ItemCategory, item_id: int) -> ItemRecord | None:
        category = ItemCategory(category)
        self.items(category)
        return self._by_id[category].get(int(item_id))

    def search(
            self,
            category: ItemCategory,
            query: str = "",
            *,
            limit: int | None = None,
    ) -> tuple[ItemRecord, ...]:
        normalized = _normalize(query)
        values = self.items(category)
        if normalized:
            values = tuple(
                item
                for item in values
                if normalized in _normalize(item.name) or normalized in str(item.id)
            )
        if limit is not None:
            return values[: max(0, int(limit))]
        return values

    def icon_bytes(self, item: ItemRecord | None) -> bytes | None:
        if item is None or item.icon_id is None:
            return None
        entries = self._load_icon_entries()
        entry = entries.get(item.icon_id)
        archive_path = self.root / "images.zip"
        if entry is None or not archive_path.is_file():
            return None
        try:
            with zipfile.ZipFile(archive_path) as archive:
                return archive.read(entry)
        except (OSError, KeyError, zipfile.BadZipFile):
            return None

    def _load_category(self, category: ItemCategory) -> tuple[ItemRecord, ...]:
        path = self.root / CATALOG_FILES[category]
        if not path.is_file():
            return ()
        records: list[ItemRecord] = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    item_id = _parse_optional_int(row.get("ID"))
                    if item_id is None:
                        continue
                    raw = MappingProxyType(
                        {
                            str(key): str(value or "")
                            for key, value in row.items()
                            if key is not None
                        }
                    )
                    records.append(
                        ItemRecord(
                            category=category,
                            id=item_id,
                            name=self._localized_name(raw, item_id),
                            icon_id=_parse_optional_int(raw.get("icon_id")),
                            max_upgrade=(
                                _weapon_max_upgrade(raw.get("Upgrade"))
                                if category is ItemCategory.WEAPONS
                                else 0
                            ),
                            raw=raw,
                        )
                    )
        except (OSError, csv.Error, UnicodeError):
            return ()
        return tuple(records)

    def _localized_name(self, row: Mapping[str, str], item_id: int) -> str:
        language = self.locale.split("_", 1)[0]
        for key in (self.locale, language, "en"):
            name = str(row.get(key, "")).strip()
            if name:
                return name
        return str(item_id)

    def _load_icon_entries(self) -> dict[int, str]:
        if self._icon_entries is not None:
            return self._icon_entries
        entries: dict[int, str] = {}
        archive_path = self.root / "images.zip"
        if archive_path.is_file():
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    for name in archive.namelist():
                        stem = Path(name).stem
                        icon_id = _parse_optional_int(stem.rsplit("_", 1)[-1])
                        if icon_id is not None:
                            entries.setdefault(icon_id, name)
            except (OSError, zipfile.BadZipFile):
                entries.clear()
        self._icon_entries = entries
        return entries
