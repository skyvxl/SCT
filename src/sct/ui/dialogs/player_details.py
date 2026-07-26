from __future__ import annotations

from types import MappingProxyType

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sct.game.builds import (
    AMMUNITION_SLOTS,
    ARMOR_SLOTS,
    ATTRIBUTE_NAMES,
    BUILD_FILE_FILTER,
    PHYSICK_SLOTS,
    QUICK_ITEM_SLOTS,
    SPELL_SLOTS,
    TALISMAN_SLOTS,
    WEAPON_SLOTS,
    EquipmentValue,
    PlayerDetails,
    SavedBuild,
    calculate_level,
)
from sct.items import ItemCatalog, ItemCategory
from sct.localization import TranslationService
from sct.ui.dialogs.item_selector import ItemSelectorDialog
from sct.ui.widgets.item_slot import ItemSlotWidget

STAT_LABEL_KEYS = {
    "vigor": "player_details.stats.vigor",
    "mind": "player_details.stats.mind",
    "endurance": "player_details.stats.endurance",
    "strength": "player_details.stats.strength",
    "dexterity": "player_details.stats.dexterity",
    "intelligence": "player_details.stats.intelligence",
    "faith": "player_details.stats.faith",
    "arcane": "player_details.stats.arcane",
    "level": "player_details.stats.level",
}

SLOT_SPECS = {
    "primary_right_wep": (
        "player_details.slots.primary_right",
        ItemCategory.WEAPONS,
    ),
    "primary_left_wep": (
        "player_details.slots.primary_left",
        ItemCategory.WEAPONS,
    ),
    "secondary_right_wep": (
        "player_details.slots.secondary_right",
        ItemCategory.WEAPONS,
    ),
    "secondary_left_wep": (
        "player_details.slots.secondary_left",
        ItemCategory.WEAPONS,
    ),
    "tertiary_right_wep": (
        "player_details.slots.tertiary_right",
        ItemCategory.WEAPONS,
    ),
    "tertiary_left_wep": (
        "player_details.slots.tertiary_left",
        ItemCategory.WEAPONS,
    ),
    "primary_arrow": (
        "player_details.slots.primary_arrow",
        ItemCategory.AMMUNITION,
    ),
    "primary_bolt": (
        "player_details.slots.primary_bolt",
        ItemCategory.AMMUNITION,
    ),
    "secondary_arrow": (
        "player_details.slots.secondary_arrow",
        ItemCategory.AMMUNITION,
    ),
    "secondary_bolt": (
        "player_details.slots.secondary_bolt",
        ItemCategory.AMMUNITION,
    ),
    "tertiary_arrow": (
        "player_details.slots.tertiary_arrow",
        ItemCategory.AMMUNITION,
    ),
    "tertiary_bolt": (
        "player_details.slots.tertiary_bolt",
        ItemCategory.AMMUNITION,
    ),
    "helmet": ("player_details.slots.helmet", ItemCategory.HEADS),
    "armor": ("player_details.slots.armor", ItemCategory.CHESTS),
    "gauntlet": ("player_details.slots.gauntlet", ItemCategory.GAUNTLETS),
    "leggings": ("player_details.slots.leggings", ItemCategory.LEGGINGS),
    **{
        slot: (
            f"player_details.slots.talisman_{index}",
            ItemCategory.TALISMANS,
        )
        for index, slot in enumerate(TALISMAN_SLOTS, start=1)
    },
    **{
        slot: (
            f"player_details.slots.spell_{index}",
            ItemCategory.SPELLS,
        )
        for index, slot in enumerate(SPELL_SLOTS, start=1)
    },
    **{
        slot: (
            f"player_details.slots.quick_{index}",
            ItemCategory.QUICK_ITEMS,
        )
        for index, slot in enumerate(QUICK_ITEM_SLOTS, start=1)
    },
    "physick_tear_1": (
        "player_details.slots.physick_tear_1",
        ItemCategory.PHYSICK_TEARS,
    ),
    "physick_tear_2": (
        "player_details.slots.physick_tear_2",
        ItemCategory.PHYSICK_TEARS,
    ),
}


class PlayerDetailsDialog(QDialog):
    apply_requested = Signal(object, bool)

    def __init__(
            self,
            translator: TranslationService,
            details: PlayerDetails,
            catalog: ItemCatalog | None = None,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.details = details
        self.catalog = catalog
        self.editable = details.is_local
        self.stats_inputs: dict[str, QSpinBox] = {}
        self.slot_widgets: dict[str, ItemSlotWidget] = {}
        self._available_slots = set(details.equipment)
        self._touched_slots: set[str] = set()
        self._baseline_build: SavedBuild | None = None
        self.setObjectName("playerDetailsDialog")
        self.setWindowTitle(
            self.translator.translate(
                "player_details.window_title",
                name=details.name,
            )
        )

        root = QVBoxLayout(self)
        columns = QHBoxLayout()
        columns.setSpacing(18)
        identity_column = self._build_identity_and_stats_column()
        identity_column.setFixedWidth(330 if self.editable else 240)
        columns.addWidget(identity_column)
        if self.editable:
            quick_column = self._build_equipment_column(
                (
                    (
                        "player_details.sections.quick_items",
                        QUICK_ITEM_SLOTS + PHYSICK_SLOTS,
                    ),
                    ("player_details.sections.spells", SPELL_SLOTS),
                )
            )
            quick_column.setMinimumWidth(470)
            columns.addWidget(quick_column, 12)
        weapons_column = self._build_equipment_column(
            (
                ("player_details.sections.weapons", WEAPON_SLOTS),
                ("player_details.sections.ammunition", AMMUNITION_SLOTS),
            )
        )
        armor_column = self._build_equipment_column(
            (
                ("player_details.sections.armor", ARMOR_SLOTS),
                ("player_details.sections.talismans", TALISMAN_SLOTS),
            )
        )
        if self.editable:
            weapons_column.setMinimumWidth(400)
            armor_column.setMinimumWidth(370)
        columns.addWidget(weapons_column, 11)
        columns.addWidget(armor_column, 10)
        root.addLayout(columns, 1)

        actions = QHBoxLayout()
        self.apply_button: QPushButton | None = None
        self.load_button: QPushButton | None = None
        self.equipment_only_checkbox: QCheckBox | None = None
        if self.editable:
            self.apply_button = QPushButton(self.translator.translate("player_details.apply"))
            self.apply_button.setObjectName("applyBuildButton")
            self.apply_button.clicked.connect(self._request_apply)
            actions.addWidget(self.apply_button, 7)
        self.save_button = QPushButton(self.translator.translate("player_details.save_build"))
        self.save_button.setObjectName("saveBuildButton")
        self.save_button.clicked.connect(self._save_build)
        actions.addWidget(self.save_button, 2 if self.editable else 1)
        if self.editable:
            self.load_button = QPushButton(self.translator.translate("player_details.load_build"))
            self.load_button.setObjectName("loadBuildButton")
            self.load_button.clicked.connect(self._load_build)
            actions.addWidget(self.load_button, 2)
            self.equipment_only_checkbox = QCheckBox(
                self.translator.translate("player_details.equipment_only")
            )
            self.equipment_only_checkbox.setObjectName("equipmentOnlyCheckbox")
            self.equipment_only_checkbox.setChecked(True)
            actions.addWidget(self.equipment_only_checkbox)
        root.addLayout(actions)

        self._baseline_build = self.current_build()
        if self.apply_button is not None:
            self.apply_button.hide()
            for field in self.stats_inputs.values():
                field.valueChanged.connect(self._refresh_apply_visibility)

        if self.editable:
            self.setFixedSize(1712, 910)
        else:
            self.setFixedSize(808, 890)

    def current_build(self) -> SavedBuild:
        stats = {
            name: field.value()
            for name, field in self.stats_inputs.items()
            if name in self.details.stats or self.editable
        }
        if "runes" in self.details.stats:
            stats["runes"] = self.details.stats["runes"]
        for name in (
                "scadutree_blessing",
                "revered_spirit_ash_blessing",
        ):
            field = self.stats_inputs.get(name)
            if field is not None:
                stats[name] = field.value()
        equipment = {
            name: widget.value
            for name, widget in self.slot_widgets.items()
            if name in self._available_slots or name in self._touched_slots
        }
        return SavedBuild(
            source_name=self.details.name,
            stats=MappingProxyType(stats),
            equipment=MappingProxyType(equipment),
        )

    def _build_identity_and_stats_column(self) -> QWidget:
        column = QWidget()
        column.setObjectName("playerDetailsIdentityColumn")
        layout = QVBoxLayout(column)

        identity = QGroupBox(
            self.translator.translate(
                "player_details.sections.shadow"
                if self.editable
                else "player_details.sections.player_info"
            )
        )
        identity.setObjectName("playerDetailsIdentity")
        identity.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        if self.editable:
            blessing_form = QFormLayout(identity)
            self._add_spin(
                blessing_form,
                "scadutree_blessing",
                "player_details.stats.scadutree",
                0,
                20,
            )
            self._add_spin(
                blessing_form,
                "revered_spirit_ash_blessing",
                "player_details.stats.revered_spirit_ash",
                0,
                10,
            )
        else:
            identity_layout = QVBoxLayout(identity)
            identity_layout.addStretch(1)
        identity.setFixedHeight(150 if self.editable else 405)
        layout.addWidget(identity)

        stats_group = QGroupBox(self.translator.translate("player_details.sections.stats"))
        stats_group.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        stats_form = QFormLayout(stats_group)
        for name in ATTRIBUTE_NAMES:
            self._add_spin(stats_form, name, STAT_LABEL_KEYS[name], 1, 99)
        self._add_spin(stats_form, "level", STAT_LABEL_KEYS["level"], 1, 713)
        if self.editable:
            self.auto_level = QCheckBox(
                self.translator.translate("player_details.stats.auto_level")
            )
            self.auto_level.setChecked(True)
            self.auto_level.toggled.connect(self._toggle_auto_level)
            stats_form.addRow(self.auto_level)
            for name in ATTRIBUTE_NAMES:
                self.stats_inputs[name].valueChanged.connect(self._recalculate_level)
            self._toggle_auto_level(True)
        layout.addWidget(stats_group, 1)
        return column

    def _add_spin(
            self,
            form: QFormLayout,
            name: str,
            label_key: str,
            minimum: int,
            maximum: int,
    ) -> None:
        field = QSpinBox()
        field.setRange(minimum, maximum)
        field.setValue(max(minimum, min(maximum, int(self.details.stats.get(name, minimum)))))
        field.setReadOnly(not self.editable)
        if not self.editable:
            field.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        form.addRow(QLabel(self.translator.translate(label_key)), field)
        self.stats_inputs[name] = field

    def _build_equipment_column(
            self,
            sections: tuple[tuple[str, tuple[str, ...]], ...],
    ) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        for title_key, slots in sections:
            group = QGroupBox(self.translator.translate(title_key))
            group.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            group_layout = QVBoxLayout(group)
            content = QWidget()
            content.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            content_layout = QVBoxLayout(content)
            for slot_name in slots:
                label_key, category = SLOT_SPECS[slot_name]
                widget = ItemSlotWidget(
                    self.translator,
                    slot_name,
                    label_key,
                    category,
                    self.details.equipment.get(slot_name),
                    catalog=self.catalog,
                    editable=self.editable,
                )
                widget.browse_requested.connect(self._browse_slot)
                widget.value_changed.connect(self._slot_changed)
                if widget.browse_button is not None and self.catalog is None:
                    widget.browse_button.setEnabled(False)
                content_layout.addWidget(widget)
                self.slot_widgets[slot_name] = widget
            content_layout.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(content)
            group_layout.addWidget(scroll)
            layout.addWidget(group, 1)
        return column

    def _browse_slot(self, slot_name: str) -> None:
        if self.catalog is None:
            return
        _label_key, category = SLOT_SPECS[slot_name]
        dialog = ItemSelectorDialog(
            self.translator,
            self.catalog,
            category,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.selected_item()
        if value is not None:
            self.slot_widgets[slot_name].set_value(value)

    def _slot_changed(self, slot_name: str, _value: EquipmentValue) -> None:
        self._touched_slots.add(slot_name)
        self._refresh_apply_visibility()

    def _refresh_apply_visibility(self, _value: int | None = None) -> None:
        if self.apply_button is None or self._baseline_build is None:
            return
        self.apply_button.setVisible(self.current_build() != self._baseline_build)

    def _toggle_auto_level(self, enabled: bool) -> None:
        self.stats_inputs["level"].setReadOnly(enabled)
        self.stats_inputs["level"].setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
            if enabled
            else QAbstractSpinBox.ButtonSymbols.UpDownArrows
        )
        if enabled:
            self._recalculate_level()

    def _recalculate_level(self, _value: int | None = None) -> None:
        if not self.editable or not self.auto_level.isChecked():
            return
        self.stats_inputs["level"].setValue(
            calculate_level({name: self.stats_inputs[name].value() for name in ATTRIBUTE_NAMES})
        )

    def _request_apply(self) -> None:
        self.apply_requested.emit(self.current_build(), False)

    def mark_applied(self) -> None:
        self._baseline_build = self.current_build()
        self._refresh_apply_visibility()

    def _save_build(self) -> None:
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            self.translator.translate("player_details.save_build"),
            f"{self.details.name}.sctbuild",
            BUILD_FILE_FILTER,
        )
        if not filename:
            return
        path = filename if filename.lower().endswith(".sctbuild") else f"{filename}.sctbuild"
        try:
            self.current_build().save(path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(
                self,
                self.translator.translate("player_details.error_title"),
                str(error),
            )

    def _load_build(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            self.translator.translate("player_details.load_build"),
            "",
            BUILD_FILE_FILTER,
        )
        if not filename:
            return
        try:
            build = SavedBuild.load(filename)
        except (OSError, ValueError) as error:
            QMessageBox.critical(
                self,
                self.translator.translate("player_details.error_title"),
                str(error),
            )
            return
        equipment_only = bool(
            self.equipment_only_checkbox and self.equipment_only_checkbox.isChecked()
        )
        if not equipment_only:
            for name, value in build.stats.items():
                if name in self.stats_inputs:
                    self.stats_inputs[name].setValue(value)
        for name, value in build.equipment.items():
            if name in self.slot_widgets:
                self.slot_widgets[name].set_value(value)
