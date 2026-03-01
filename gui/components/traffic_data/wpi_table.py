"""
gui/components/traffic_data/wpi_table.py

_WPITable — vehicle × category matrix for WPI adjustment ratios.

Rows    : 8 vehicles + 2 header rows (group + individual label) + 1 checkbox row
Columns : 16 cost categories grouped under 6 headings
Modes   : read-only (DB profile) / editable (custom profile)
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QHBoxLayout,
)

# ── Vehicles ──────────────────────────────────────────────────────────────────

_VEHICLES = [
    ("small_cars", "Small Car"),
    ("big_cars", "Big Car"),
    ("two_wheelers", "Two Wheeler"),
    ("o_buses", "Ordinary Bus"),
    ("d_buses", "Deluxe Bus"),
    ("lcv", "LCV"),
    ("hcv", "HCV"),
    ("mcv", "MCV"),
]
from ..utils.wpi_manager import WPIManager, WPIProfile, empty_data

# ── Column definitions ────────────────────────────────────────────────────────


@dataclass
class _ColDef:
    group: str
    label: str
    path: tuple


_COLUMNS: list[_ColDef] = [
    _ColDef("Fuel Cost", "Petrol", ("fuelCost", "petrol")),
    _ColDef("Fuel Cost", "Diesel", ("fuelCost", "diesel")),
    _ColDef("Fuel Cost", "Engine Oil", ("fuelCost", "engine_oil")),
    _ColDef("Fuel Cost", "Other Oil", ("fuelCost", "other_oil")),
    _ColDef("Fuel Cost", "Grease", ("fuelCost", "grease")),
    _ColDef("Vehicle Cost", "Prop. Damage", ("vehicleCost", "propertyDamage", "{v}")),
    _ColDef("Vehicle Cost", "Tyre Cost", ("vehicleCost", "tyreCost", "{v}")),
    _ColDef("Vehicle Cost", "Spare Parts", ("vehicleCost", "spareParts", "{v}")),
    _ColDef("Vehicle Cost", "Fixed Depr.", ("vehicleCost", "fixedDepreciation", "{v}")),
    _ColDef("Commodity", "Hold. Cost", ("commodityHoldingCost", "{v}")),
    _ColDef("Pass. & Crew", "Passenger", ("passengerCrewCost", "passenger")),
    _ColDef("Pass. & Crew", "Crew", ("passengerCrewCost", "crew")),
    _ColDef("Medical Cost", "Fatal", ("medicalCost", "fatal")),
    _ColDef("Medical Cost", "Major", ("medicalCost", "major")),
    _ColDef("Medical Cost", "Minor", ("medicalCost", "minor")),
    _ColDef("VOT Cost", "VOT Cost", ("votCost", "{v}")),
]

_N_COLS = len(_COLUMNS)
_N_ROWS = len(_VEHICLES) + 3  # group + label + checkbox + 8 vehicles
_ROW_GROUP = 0
_ROW_LABEL = 1
_ROW_CB = 2
_ROW_DATA = 3


def _get_value(data: dict, path: tuple, vehicle_key: str) -> float:
    node = data
    for segment in path:
        key = vehicle_key if segment == "{v}" else segment
        node = node.get(key, {})
    return float(node) if isinstance(node, (int, float)) else 1.0


def _set_value(data: dict, path: tuple, vehicle_key: str, value: float):
    node = data
    for segment in path[:-1]:
        key = vehicle_key if segment == "{v}" else segment
        node = node.setdefault(key, {})
    last = vehicle_key if path[-1] == "{v}" else path[-1]
    node[last] = value


def _is_vehicle_dim(col: _ColDef) -> bool:
    return "{v}" in col.path


# ── _WPITable ─────────────────────────────────────────────────────────────────


class _WPITable(QTableWidget):
    """
    Vehicle × Category WPI ratio table.

    Row 0 : group colour band  (Fuel Cost, Vehicle Cost …)
    Row 1 : individual labels  (Petrol, Diesel …)
    Row 2 : "Common to All" checkboxes
    Rows 3+: one row per vehicle
    """

    data_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(_N_ROWS, _N_COLS, parent)
        self._editable: bool = False
        self._spinboxes: dict[tuple[int, int], QDoubleSpinBox] = {}
        self._checkboxes: dict[int, QCheckBox] = {}
        self._loading: bool = False

        self._setup_table()
        self._build_group_row()
        self._build_label_row()
        self._build_checkbox_row()
        self._build_data_rows()
        self.update_height()
        # Apply initial read-only opacity to all spinboxes
        for sb in self._spinboxes.values():
            self._apply_spinbox_opacity(sb, False)

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_table(self):
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionMode(QTableWidget.NoSelection)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # Hide Qt's built-in column header — we use row 0 and 1 instead
        self.horizontalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setMinimumSectionSize(72)

        self.verticalHeader().setVisible(True)
        self.verticalHeader().setDefaultSectionSize(34)

        self.setRowHeight(_ROW_GROUP, 22)
        self.setRowHeight(_ROW_LABEL, 26)
        self.setRowHeight(_ROW_CB, 30)

    def _build_group_row(self):
        """Row 0 — group labels with colspan (setSpan) per group."""
        bold = QFont()
        bold.setBold(True)

        group_spans: dict[str, list] = {}
        for col, cdef in enumerate(_COLUMNS):
            if cdef.group not in group_spans:
                group_spans[cdef.group] = [col, 0]
            group_spans[cdef.group][1] += 1

        placed: set[str] = set()
        for col, cdef in enumerate(_COLUMNS):
            if cdef.group not in placed:
                first_col, span = group_spans[cdef.group]
                item = QTableWidgetItem(cdef.group)
                item.setFlags(Qt.ItemIsEnabled)
                item.setFont(bold)
                item.setTextAlignment(Qt.AlignCenter)
                self.setItem(_ROW_GROUP, col, item)
                if span > 1:
                    self.setSpan(_ROW_GROUP, col, 1, span)
                placed.add(cdef.group)

        self.setVerticalHeaderItem(_ROW_GROUP, QTableWidgetItem(""))

    def _build_label_row(self):
        """Row 1 — individual column labels."""
        small_bold = QFont()
        small_bold.setBold(True)
        small_bold.setPointSize(8)
        for col, cdef in enumerate(_COLUMNS):
            item = QTableWidgetItem(cdef.label)
            item.setFlags(Qt.ItemIsEnabled)
            item.setFont(small_bold)
            item.setTextAlignment(Qt.AlignCenter)
            self.setItem(_ROW_LABEL, col, item)
        self.setVerticalHeaderItem(_ROW_LABEL, QTableWidgetItem(""))

    def _build_checkbox_row(self):
        """Row 2 — one centered QCheckBox per column."""
        for col in range(_N_COLS):
            cb = QCheckBox()
            cb.setToolTip("Common to all vehicles")
            cb.setChecked(True)
            cb.stateChanged.connect(lambda state, c=col: self._on_common_toggled(c))

            container = QWidget()
            layout = QHBoxLayout(container)
            layout.addWidget(cb)
            layout.setAlignment(Qt.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            self.setCellWidget(_ROW_CB, col, container)
            self._checkboxes[col] = cb

            item = QTableWidgetItem()
            item.setFlags(Qt.ItemIsEnabled)
            self.setItem(_ROW_CB, col, item)

        self.setVerticalHeaderItem(_ROW_CB, QTableWidgetItem("Common\nto All"))

    def _build_data_rows(self):
        """Rows 3+ — one QDoubleSpinBox per cell, vehicle name in vertical header."""
        for row_idx, (vkey, vlabel) in enumerate(_VEHICLES):
            row = _ROW_DATA + row_idx
            self.setVerticalHeaderItem(row, QTableWidgetItem(vlabel))

            for col in range(_N_COLS):
                sb = QDoubleSpinBox()
                sb.setRange(0.0, 99.9999)
                sb.setDecimals(4)
                sb.setValue(1.0)
                sb.setButtonSymbols(QDoubleSpinBox.NoButtons)
                sb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                sb.setReadOnly(True)
                sb.setFrame(False)
                # opacity applied via _apply_spinbox_opacity after palette is available
                sb.valueChanged.connect(
                    lambda val, r=row, c=col: self._on_spinbox_changed(r, c, val)
                )
                self.setCellWidget(row, col, sb)
                self._spinboxes[(row, col)] = sb

    # ── Height ────────────────────────────────────────────────────────────────

    def update_height(self):
        """Fix height to exact content — no empty space, no scrollbar."""
        h = 0
        for r in range(self.rowCount()):
            h += self.rowHeight(r)
        self.setFixedHeight(h + 4)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.viewport().width()
        per_col = max(72, w // _N_COLS)
        for col in range(_N_COLS):
            self.setColumnWidth(col, per_col)

    # ── Mode ──────────────────────────────────────────────────────────────────

    def set_editable(self, editable: bool):
        self._editable = editable
        for (row, col), sb in self._spinboxes.items():
            cb = self._checkboxes[col]
            is_first = row == _ROW_DATA
            is_common = cb.isChecked()
            self._set_cell_editable(row, col, editable and (is_first or not is_common))
        for cb in self._checkboxes.values():
            cb.setEnabled(editable)

    def _set_cell_editable(self, row: int, col: int, editable: bool):
        sb = self._spinboxes.get((row, col))
        if sb is None:
            return
        sb.setReadOnly(not editable)
        sb.setFrame(editable)
        self._apply_spinbox_opacity(sb, editable)

    # ── Common-to-all logic ───────────────────────────────────────────────────

    def _on_common_toggled(self, col: int):
        if self._loading:
            return
        cb = self._checkboxes[col]
        is_common = cb.isChecked()

        if is_common:
            first_val = self._spinboxes[(_ROW_DATA, col)].value()
            self._loading = True
            for row_idx in range(1, len(_VEHICLES)):
                self._spinboxes[(_ROW_DATA + row_idx, col)].setValue(first_val)
            self._loading = False

        for row_idx in range(len(_VEHICLES)):
            row = _ROW_DATA + row_idx
            is_first = row == _ROW_DATA
            self._set_cell_editable(
                row, col, self._editable and (is_first or not is_common)
            )

        self._apply_common_style(col, is_common)
        self.data_changed.emit()

    def _apply_spinbox_opacity(self, sb: QDoubleSpinBox, active: bool):
        """
        Set spinbox text colour by deriving it from the current palette's
        WindowText role and applying alpha — works in both light and dark mode.
        active=True  → full opacity (palette default)
        active=False → 40% opacity (dimmed, read-only)
        """
        if active:
            sb.setStyleSheet("")
        else:
            base = sb.palette().color(QPalette.WindowText)
            base.setAlpha(102)  # ~40% of 255
            r, g, b, a = base.red(), base.green(), base.blue(), base.alpha()
            sb.setStyleSheet(
                f"QDoubleSpinBox {{ background: transparent; border: none;"
                f" color: rgba({r},{g},{b},{a}); }}"
            )

    def _apply_common_style(self, col: int, is_common: bool):
        for row_idx in range(1, len(_VEHICLES)):
            row = _ROW_DATA + row_idx
            sb = self._spinboxes.get((row, col))
            if sb is None:
                continue
            # Dimmed when common (non-editable secondary rows), active when independent
            active = not is_common and self._editable
            self._apply_spinbox_opacity(sb, active)

    def _on_spinbox_changed(self, row: int, col: int, value: float):
        if self._loading:
            return
        if row == _ROW_DATA and self._checkboxes[col].isChecked():
            self._loading = True
            for row_idx in range(1, len(_VEHICLES)):
                self._spinboxes[(_ROW_DATA + row_idx, col)].setValue(value)
            self._loading = False
        self.data_changed.emit()

    # ── Load / Collect ────────────────────────────────────────────────────────

    def load_from_data(self, data: dict):
        self._loading = True
        try:
            for col, cdef in enumerate(_COLUMNS):
                values = []
                for row_idx, (vkey, _) in enumerate(_VEHICLES):
                    val = _get_value(data, cdef.path, vkey)
                    values.append(val)
                    self._spinboxes[(_ROW_DATA + row_idx, col)].setValue(val)

                all_same = len(set(round(v, 6) for v in values)) == 1
                cb = self._checkboxes[col]
                cb.setChecked(all_same)
                self._apply_common_style(col, all_same)
        finally:
            self._loading = False

        self.set_editable(self._editable)

    def collect_to_data(self) -> dict:

        data = empty_data()
        for col, cdef in enumerate(_COLUMNS):
            for row_idx, (vkey, _) in enumerate(_VEHICLES):
                row = _ROW_DATA + row_idx
                val = self._spinboxes[(row, col)].value()
                _set_value(data, cdef.path, vkey, val)
        return data

    def is_common(self, col: int) -> bool:
        return self._checkboxes[col].isChecked()

    def common_state(self) -> dict[int, bool]:
        return {col: cb.isChecked() for col, cb in self._checkboxes.items()}

    def load_common_state(self, state: dict[int, bool]):
        self._loading = True
        for col, checked in state.items():
            if col in self._checkboxes:
                self._checkboxes[col].setChecked(checked)
                self._apply_common_style(col, checked)
        self._loading = False
