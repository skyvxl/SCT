from __future__ import annotations

from pathlib import Path

PROCESS_NAME = "eldenring.exe"
MODULE_NAME = "eldenring.exe"
RESOURCE_ROOT = Path(__file__).resolve().parent
SIGNATURES_PATH = RESOURCE_ROOT / "signatures.toml"
OFFSETS_PATH = RESOURCE_ROOT / "offsets.toml"
