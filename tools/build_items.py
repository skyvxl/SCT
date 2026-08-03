from __future__ import annotations

import sys
import zipfile
from pathlib import Path

from sct.items import REQUIRED_ITEM_FILES


class ItemBuildError(RuntimeError):
    """Raised when the item data archive cannot be assembled safely."""


def validate_items(source: Path | str) -> tuple[Path, ...]:
    root = Path(source)
    missing = tuple(
        root / filename
        for filename in REQUIRED_ITEM_FILES
        if not (root / filename).is_file()
    )
    if missing:
        names = ", ".join(path.name for path in missing)
        raise ItemBuildError(f"Required item data is missing: {names}")
    return tuple(root / filename for filename in REQUIRED_ITEM_FILES)


def create_items_zip(
        items_dir: Path | str,
        destination: Path | str,
) -> Path:
    source = Path(items_dir).resolve()
    files = validate_items(source)
    archive = Path(destination).resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(
            archive,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
    ) as items_zip:
        for path in sorted(files, key=lambda value: value.name):
            items_zip.write(
                path,
                f"items/{path.name}",
                compress_type=(
                    zipfile.ZIP_STORED
                    if path.suffix.casefold() == ".zip"
                    else zipfile.ZIP_DEFLATED
                ),
            )
    return archive


def build_items(project_root: Path | str) -> Path:
    root = Path(project_root).resolve()
    return create_items_zip(
        root / "data" / "items",
        root / "dist" / "items.zip",
    )


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    try:
        archive_path = build_items(project_root)
    except ItemBuildError as error:
        print(f"Item build failed: {error}", file=sys.stderr)
        return 1
    print(f"Item data archive: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
