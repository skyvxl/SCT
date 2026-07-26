from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from sct.characters import CharacterStats
from sct.localization import TranslationService

ATTRIBUTE_KEYS = (
    ("vigor", "characters.stats.vigor"),
    ("mind", "characters.stats.mind"),
    ("endurance", "characters.stats.endurance"),
    ("strength", "characters.stats.strength"),
    ("dexterity", "characters.stats.dexterity"),
    ("intelligence", "characters.stats.intelligence"),
    ("faith", "characters.stats.faith"),
    ("arcane", "characters.stats.arcane"),
)


class CharacterStatsDialog(QDialog):
    def __init__(
            self,
            translator: TranslationService,
            stats: CharacterStats,
            parent=None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self._offset = stats.offset
        self.attribute_inputs: dict[str, QSpinBox] = {}
        self._labels: list[tuple[QLabel, str]] = []

        layout = QVBoxLayout(self)
        form = QFormLayout()
        values = dict(
            zip(
                (name for name, _key in ATTRIBUTE_KEYS),
                stats.attributes,
                strict=True,
            )
        )
        for name, key in ATTRIBUTE_KEYS:
            field = QSpinBox()
            field.setRange(1, 99)
            field.setValue(values[name])
            field.valueChanged.connect(self._update_level)
            label = QLabel()
            self._labels.append((label, key))
            self.attribute_inputs[name] = field
            form.addRow(label, field)

        self.level_value = QLabel()
        level_label = QLabel()
        self._labels.append((level_label, "characters.stats.level"))
        form.addRow(level_label, self.level_value)

        hours = stats.seconds_played // 3600
        minutes = stats.seconds_played % 3600 // 60
        seconds = stats.seconds_played % 60
        self.hours_input = QSpinBox()
        self.hours_input.setRange(0, 9_999)
        self.hours_input.setValue(hours)
        self.minutes_input = QSpinBox()
        self.minutes_input.setRange(0, 59)
        self.minutes_input.setValue(minutes)
        self.seconds_input = QSpinBox()
        self.seconds_input.setRange(0, 59)
        self.seconds_input.setValue(seconds)
        for field, key in (
                (self.hours_input, "characters.stats.hours"),
                (self.minutes_input, "characters.stats.minutes"),
                (self.seconds_input, "characters.stats.seconds"),
        ):
            label = QLabel()
            self._labels.append((label, key))
            form.addRow(label, field)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.translator.language_changed.connect(lambda _locale: self._retranslate())
        self._retranslate()
        self._update_level()
        self.setMinimumWidth(320)
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def result_value(self) -> CharacterStats:
        values = {
            name: field.value()
            for name, field in self.attribute_inputs.items()
        }
        return CharacterStats(
            **values,
            seconds_played=(
                    self.hours_input.value() * 3600
                    + self.minutes_input.value() * 60
                    + self.seconds_input.value()
            ),
            offset=self._offset,
        )

    def _update_level(self) -> None:
        level = sum(field.value() for field in self.attribute_inputs.values()) - 79
        self.level_value.setText(str(level))

    def _retranslate(self) -> None:
        self.setWindowTitle(self.translator.translate("characters.stats.title"))
        for label, key in self._labels:
            label.setText(self.translator.translate(key))
        save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button is not None:
            save_button.setText(self.translator.translate("common.save"))
        if cancel_button is not None:
            cancel_button.setText(self.translator.translate("common.cancel"))
