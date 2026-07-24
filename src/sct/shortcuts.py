from __future__ import annotations

from PySide6.QtCore import QKeyCombination
from PySide6.QtGui import QKeySequence


def serialize_key_sequence(sequence: QKeySequence) -> str:
    return ",".join(str(sequence[index].toCombined()) for index in range(sequence.count()))


def deserialize_key_sequence(value: str) -> QKeySequence:
    if not value.strip():
        return QKeySequence()
    try:
        combinations = [
            QKeyCombination.fromCombined(int(part.strip())) for part in value.split(",")
        ]
    except (TypeError, ValueError):
        return QKeySequence()
    if not combinations or len(combinations) > 4:
        return QKeySequence()
    return QKeySequence(*combinations)
