"""
devtools/unit_manager_gui.py

Unit Manager - browse built-in units, add new units, manage custom units,
and test raw unit string resolution.

Tabs
----
1. Built-in Units  - read-only table from units.json + Add Unit button
2. Custom Units    - CustomMaterialDB entries + Promote to Built-in
3. Tester          - type any raw string, see what it resolves to
"""

from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEVTOOLS_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT  = os.path.dirname(_DEVTOOLS_DIR)
_GUI_UTILS     = os.path.join(_PROJECT_ROOT, "gui", "components", "utils")
_UNITS_JSON    = os.path.join(_GUI_UTILS, "units.json")

# Make registry importable
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Style palette (Catppuccin Mocha)
# ---------------------------------------------------------------------------

_BG      = "#1e1e2e"
_BG2     = "#252535"
_BG3     = "#313244"
_SURFACE = "#181825"
_TEXT    = "#cdd6f4"
_DIM     = "#585b70"
_BLUE    = "#89b4fa"
_GREEN   = "#a6e3a1"
_MAUVE   = "#cba6f7"
_PEACH   = "#fab387"
_YELLOW  = "#f9e2af"
_TEAL    = "#94e2d5"
_RED     = "#f38ba8"
_BORDER  = "#2a2a3e"

_BASE_STYLE = f"""
    QDialog, QWidget {{ background: {_BG}; color: {_TEXT}; }}
    QTabWidget::pane {{ border: 1px solid {_BORDER}; background: {_BG}; }}
    QTabBar::tab {{
        background: {_BG2}; color: {_DIM}; padding: 6px 18px;
        border: 1px solid {_BORDER}; border-bottom: none;
    }}
    QTabBar::tab:selected {{ background: {_BG}; color: {_TEXT}; }}
    QTableWidget {{
        background: {_BG2}; color: {_TEXT};
        gridline-color: {_BORDER}; border: none;
    }}
    QTableWidget QHeaderView::section {{
        background: {_BG3}; color: {_DIM};
        border: none; padding: 4px 8px; font-size: 11px;
    }}
    QTableWidget::item:selected {{ background: {_BG3}; color: {_TEXT}; }}
    QLineEdit, QComboBox {{
        background: {_BG2}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px; padding: 4px 8px;
    }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {_BLUE}; }}
    QComboBox QAbstractItemView {{
        background: {_BG2}; color: {_TEXT};
        selection-background-color: {_BG3};
    }}
    QPushButton {{
        background: {_BG3}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 5px 14px; font-size: 12px;
    }}
    QPushButton:hover {{ background: {_BLUE}; color: {_SURFACE}; }}
    QPushButton:disabled {{ color: {_DIM}; }}
    QLabel {{ color: {_TEXT}; background: transparent; }}
"""

# ---------------------------------------------------------------------------
# units.json helpers
# ---------------------------------------------------------------------------

def _read_units_json() -> dict:
    with open(_UNITS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_units_json(data: dict) -> None:
    with open(_UNITS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _all_systems(data: dict) -> list[str]:
    """Return all non-underscore, non-dimensions keys (i.e. system names)."""
    return [k for k in data if not k.startswith("_") and k != "dimensions"]


def _resolve_fresh(raw: str) -> dict:
    """Resolve a raw unit string against the current units.json (no cache)."""
    data    = _read_units_json()
    units: dict = {}
    units.update(data.get("_common", {}))
    for key, val in data.items():
        if not key.startswith("_") and key != "dimensions":
            units.update(val)

    # Build alias map
    aliases: dict[str, str] = {}
    for code, u in units.items():
        for alias in u.get("aliases", []):
            k = alias.strip().lower()
            if k and k not in aliases:
                aliases[k] = code

    key = raw.strip().lower()

    # Direct hit
    if key in units:
        u = units[key]
        return {"code": key, "dimension": u["dimension"],
                "to_si": u["to_si"], "display": u.get("display", key),
                "via": "direct"}

    # Alias hit
    if key in aliases:
        code = aliases[key]
        u = units[code]
        return {"code": code, "dimension": u["dimension"],
                "to_si": u["to_si"], "display": u.get("display", code),
                "via": f"alias → {code}"}

    return {}


# ---------------------------------------------------------------------------
# Shared table helpers
# ---------------------------------------------------------------------------

def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setSelectionMode(QTableWidget.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.setAlternatingRowColors(True)
    t.setStyleSheet(
        f"QTableWidget {{ alternate-background-color: {_SURFACE}; }}"
    )
    return t


def _cell(text: str, color: str | None = None) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if color:
        from PySide6.QtGui import QColor
        item.setForeground(QColor(color))
    return item


# ---------------------------------------------------------------------------
# Add Unit Dialog
# ---------------------------------------------------------------------------

class AddUnitDialog(QDialog):
    """Collect data for a new unit entry in units.json."""

    DIMENSIONS = ["Mass", "Length", "Area", "Volume", "Count"]

    def __init__(self, systems: list[str], prefill: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Unit" if not prefill else "Promote to Built-in")
        self.setMinimumWidth(460)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet(_BASE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # Code
        self._code = QLineEdit(prefill.get("symbol", "") if prefill else "")
        self._code.setPlaceholderText("e.g. bag")
        form.addRow("Code *", self._code)

        # Name
        self._name = QLineEdit(prefill.get("name", "") if prefill else "")
        self._name.setPlaceholderText("e.g. Cement Bag")
        form.addRow("Name *", self._name)

        # Display symbol
        self._display = QLineEdit(prefill.get("symbol", "") if prefill else "")
        self._display.setPlaceholderText("e.g. bag  (shown in UI)")
        form.addRow("Display *", self._display)

        # Dimension
        self._dim = QComboBox()
        self._dim.addItems(self.DIMENSIONS)
        if prefill and prefill.get("dimension") in self.DIMENSIONS:
            self._dim.setCurrentText(prefill["dimension"])
        form.addRow("Dimension *", self._dim)

        # to_si
        self._to_si = QLineEdit(str(prefill.get("to_si", "")) if prefill else "")
        self._to_si.setPlaceholderText("e.g. 50  (1 bag = 50 kg)")
        self._to_si.setValidator(QDoubleValidator(0.0, 1e12, 10))
        form.addRow("to_si factor *", self._to_si)

        # System
        self._system = QComboBox()
        self._system.addItems(systems)
        form.addRow("System *", self._system)

        # Aliases
        self._aliases = QLineEdit()
        self._aliases.setPlaceholderText("comma-separated  e.g. Bag, bags, BAG")
        form.addRow("Aliases", self._aliases)

        layout.addLayout(form)

        # Hint
        hint = QLabel("* Required. to_si: how many SI base units equal 1 of this unit.")
        hint.setStyleSheet(f"color: {_DIM}; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        code = self._code.text().strip().lower()
        name = self._name.text().strip()
        display = self._display.text().strip()
        to_si_txt = self._to_si.text().strip()

        errors = []
        if not code:
            errors.append("Code is required.")
        if not name:
            errors.append("Name is required.")
        if not display:
            errors.append("Display symbol is required.")
        if not to_si_txt:
            errors.append("to_si factor is required.")
        else:
            try:
                float(to_si_txt)
            except ValueError:
                errors.append("to_si must be a number.")

        if errors:
            QMessageBox.warning(self, "Validation", "\n".join(errors))
            return

        self.accept()

    def get_unit(self) -> dict:
        aliases_raw = self._aliases.text()
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        return {
            "code":      self._code.text().strip().lower(),
            "system":    self._system.currentText(),
            "entry": {
                "dimension": self._dim.currentText(),
                "to_si":     float(self._to_si.text().strip()),
                "display":   self._display.text().strip(),
                "name":      self._name.text().strip(),
                "example":   "",
                "aliases":   aliases,
                "systems":   [self._system.currentText()],
            }
        }


# ---------------------------------------------------------------------------
# Edit Unit Dialog
# ---------------------------------------------------------------------------

class EditUnitDialog(QDialog):
    """Edit an existing unit entry in units.json. Code and system are read-only."""

    DIMENSIONS = ["Mass", "Length", "Area", "Volume", "Count"]

    def __init__(self, code: str, system: str, entry: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Unit - {code}")
        self.setMinimumWidth(480)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet(_BASE_STYLE)

        self._code   = code
        self._system = system
        self._entry  = entry

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # Code - read-only label
        code_lbl = QLabel(code)
        code_lbl.setStyleSheet(f"color: {_BLUE}; font-weight: bold;")
        form.addRow("Code", code_lbl)

        # System - read-only label
        sys_lbl = QLabel(system)
        sys_lbl.setStyleSheet(f"color: {_DIM};")
        form.addRow("System", sys_lbl)

        # Dimension
        self._dim = QComboBox()
        self._dim.addItems(self.DIMENSIONS)
        if entry.get("dimension") in self.DIMENSIONS:
            self._dim.setCurrentText(entry["dimension"])
        form.addRow("Dimension *", self._dim)

        # Name
        self._name = QLineEdit(entry.get("name", ""))
        form.addRow("Name *", self._name)

        # Display symbol
        self._display = QLineEdit(entry.get("display", code))
        form.addRow("Display *", self._display)

        # to_si
        self._to_si = QLineEdit(str(entry.get("to_si", "")))
        self._to_si.setValidator(QDoubleValidator(0.0, 1e12, 10))
        form.addRow("to_si factor *", self._to_si)

        # Aliases - most important field for devs
        aliases_str = ", ".join(entry.get("aliases", []))
        self._aliases = QLineEdit(aliases_str)
        self._aliases.setPlaceholderText("comma-separated  e.g.  Sqm, Sqm., SQM, sqmt")
        form.addRow("Aliases", self._aliases)

        # Example
        self._example = QLineEdit(entry.get("example", ""))
        self._example.setPlaceholderText("Short usage example shown in dropdown")
        form.addRow("Example", self._example)

        layout.addLayout(form)

        hint = QLabel("Code and system cannot be changed. Add aliases to help the resolver recognise more SOR strings.")
        hint.setStyleSheet(f"color: {_DIM}; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        errors = []
        if not self._name.text().strip():
            errors.append("Name is required.")
        if not self._display.text().strip():
            errors.append("Display symbol is required.")
        if not self._to_si.text().strip():
            errors.append("to_si factor is required.")
        else:
            try:
                float(self._to_si.text())
            except ValueError:
                errors.append("to_si must be a number.")
        if errors:
            QMessageBox.warning(self, "Validation", "\n".join(errors))
            return
        self.accept()

    def get_updated_entry(self) -> dict:
        aliases = [a.strip() for a in self._aliases.text().split(",") if a.strip()]
        updated = dict(self._entry)
        updated["dimension"] = self._dim.currentText()
        updated["name"]      = self._name.text().strip()
        updated["display"]   = self._display.text().strip()
        updated["to_si"]     = float(self._to_si.text().strip())
        updated["aliases"]   = aliases
        updated["example"]   = self._example.text().strip()
        return updated


# ---------------------------------------------------------------------------
# Tab 1 - Built-in Units
# ---------------------------------------------------------------------------

class BuiltinUnitsTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict = {}
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Filter row
        fr = QHBoxLayout()
        fr.setSpacing(8)

        fr.addWidget(QLabel("System:"))
        self._sys_cb = QComboBox()
        self._sys_cb.setFixedWidth(150)
        self._sys_cb.currentIndexChanged.connect(self._apply_filter)
        fr.addWidget(self._sys_cb)

        fr.addWidget(QLabel("Dimension:"))
        self._dim_cb = QComboBox()
        self._dim_cb.setFixedWidth(130)
        self._dim_cb.addItem("All", None)
        for d in ["Mass", "Length", "Area", "Volume", "Count"]:
            self._dim_cb.addItem(d, d)
        self._dim_cb.currentIndexChanged.connect(self._apply_filter)
        fr.addWidget(self._dim_cb)

        fr.addStretch()

        # self._edit_btn = QPushButton("Edit")
        self._edit_btn = QPushButton("✏️")
        self._edit_btn.setFixedHeight(30)
        self._edit_btn.setEnabled(False)
        self._edit_btn.setStyleSheet(
            f"QPushButton:enabled {{ background: {_BLUE}; color: {_SURFACE};"
            f" border: none; border-radius: 4px; font-weight: bold; padding: 0 14px; }}"
            f"QPushButton:enabled:hover {{ background: #a8c8ff; }}"
            f"QPushButton:disabled {{ background: {_BG3}; color: {_DIM};"
            f" border: none; border-radius: 4px; padding: 0 14px; }}"
        )
        self._edit_btn.clicked.connect(self._on_edit)
        fr.addWidget(self._edit_btn)

        self._add_btn = QPushButton("+ Add Unit")
        self._add_btn.setFixedHeight(30)
        self._add_btn.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: {_SURFACE};"
            f" border: none; border-radius: 4px; font-weight: bold; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: #b5ead7; }}"
        )
        self._add_btn.clicked.connect(self._on_add)
        fr.addWidget(self._add_btn)

        layout.addLayout(fr)

        # Table
        self._table = _make_table(["Code", "Name", "Display", "Dimension", "to_si", "System", "Aliases"])
        self._table.setColumnWidth(0, 80)
        self._table.setColumnWidth(1, 160)
        self._table.setColumnWidth(2, 70)
        self._table.setColumnWidth(3, 90)
        self._table.setColumnWidth(4, 80)
        self._table.setColumnWidth(5, 90)
        self._table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._table)

        # Count label
        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        layout.addWidget(self._count_lbl)

    def refresh(self):
        self._data = _read_units_json()
        systems = _all_systems(self._data)

        # Rebuild system combo
        prev = self._sys_cb.currentData()
        self._sys_cb.blockSignals(True)
        self._sys_cb.clear()
        self._sys_cb.addItem("All", None)
        self._sys_cb.addItem("_common", "_common")
        for s in systems:
            self._sys_cb.addItem(s, s)
        if prev:
            idx = self._sys_cb.findData(prev)
            if idx >= 0:
                self._sys_cb.setCurrentIndex(idx)
        self._sys_cb.blockSignals(False)

        self._apply_filter()

    def _apply_filter(self):
        sys_filter = self._sys_cb.currentData()
        dim_filter = self._dim_cb.currentData()

        rows = []
        blocks = (
            [sys_filter] if sys_filter
            else ["_common"] + _all_systems(self._data)
        )
        for block_key in blocks:
            block = self._data.get(block_key, {})
            for code, u in block.items():
                if dim_filter and u.get("dimension") != dim_filter:
                    continue
                rows.append((code, u, block_key))

        self._rows = rows  # store for selection lookup
        self._table.setRowCount(len(rows))
        for r, (code, u, system) in enumerate(rows):
            aliases = ", ".join(u.get("aliases", []))
            self._table.setItem(r, 0, _cell(code, _BLUE))
            self._table.setItem(r, 1, _cell(u.get("name", "")))
            self._table.setItem(r, 2, _cell(u.get("display", code)))
            self._table.setItem(r, 3, _cell(u.get("dimension", "")))
            self._table.setItem(r, 4, _cell(str(u.get("to_si", ""))))
            self._table.setItem(r, 5, _cell(system, _DIM))
            self._table.setItem(r, 6, _cell(aliases))

        self._count_lbl.setText(f"{len(rows)} unit(s) shown")
        self._edit_btn.setEnabled(False)

    def _on_selection(self):
        rows = self._table.selectionModel().selectedRows()
        self._edit_btn.setEnabled(bool(rows))

    def _selected_row(self) -> tuple | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._rows[rows[0].row()]   # (code, entry_dict, system)

    def _on_edit(self):
        row = self._selected_row()
        if not row:
            return
        code, entry, system = row

        dlg = EditUnitDialog(code, system, entry, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        updated = dlg.get_updated_entry()
        self._data[system][code] = updated
        _write_units_json(self._data)
        self.refresh()
        self._show_restart_banner()

    def _on_add(self):
        systems = ["_common"] + _all_systems(self._data)
        dlg = AddUnitDialog(systems, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        result = dlg.get_unit()
        code   = result["code"]
        system = result["system"]
        entry  = result["entry"]

        # Check for duplicate
        all_codes = set()
        for blk in (["_common"] + _all_systems(self._data)):
            all_codes |= set(self._data.get(blk, {}).keys())

        if code in all_codes:
            QMessageBox.warning(self, "Duplicate", f"Unit code '{code}' already exists.")
            return

        # Write
        if system not in self._data:
            self._data[system] = {}
        self._data[system][code] = entry
        _write_units_json(self._data)

        self.refresh()
        self._show_restart_banner()

    def _show_restart_banner(self):
        QMessageBox.information(
            self, "Saved",
            "Unit saved to units.json.\n\nRestart the app to apply changes."
        )


# ---------------------------------------------------------------------------
# Tab 2 - Custom Units
# ---------------------------------------------------------------------------

class CustomUnitsTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(8)

        info = QLabel("Custom units defined in this installation (global, not per-project).")
        info.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        tb.addWidget(info)
        tb.addStretch()

        self._promote_btn = QPushButton("Promote to Built-in →")
        self._promote_btn.setFixedHeight(30)
        self._promote_btn.setEnabled(False)
        self._promote_btn.setStyleSheet(
            f"QPushButton:enabled {{ background: {_MAUVE}; color: {_SURFACE};"
            f" border: none; border-radius: 4px; font-weight: bold; padding: 0 14px; }}"
            f"QPushButton:enabled:hover {{ background: #d9b3ff; }}"
            f"QPushButton:disabled {{ background: {_BG3}; color: {_DIM};"
            f" border: none; border-radius: 4px; padding: 0 14px; }}"
        )
        self._promote_btn.clicked.connect(self._on_promote)
        tb.addWidget(self._promote_btn)

        self._del_btn = QPushButton("Delete")
        self._del_btn.setFixedHeight(30)
        self._del_btn.setEnabled(False)
        self._del_btn.setStyleSheet(
            f"QPushButton:enabled {{ background: {_RED}; color: {_SURFACE};"
            f" border: none; border-radius: 4px; font-weight: bold; padding: 0 14px; }}"
            f"QPushButton:enabled:hover {{ background: #ff9eb5; }}"
            f"QPushButton:disabled {{ background: {_BG3}; color: {_DIM};"
            f" border: none; border-radius: 4px; padding: 0 14px; }}"
        )
        self._del_btn.clicked.connect(self._on_delete)
        tb.addWidget(self._del_btn)

        layout.addLayout(tb)

        # Table
        self._table = _make_table(["Symbol", "Dimension", "to_si"])
        self._table.setColumnWidth(0, 120)
        self._table.setColumnWidth(1, 120)
        self._table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._table)

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        layout.addWidget(self._count_lbl)

    def _load_db(self):
        try:
            from three_ps_lcca_gui.gui.components.structure.registry.custom_material_db import CustomMaterialDB
            return CustomMaterialDB()
        except Exception as e:
            print(f"[UnitManager] Could not load CustomMaterialDB: {e}")
            return None

    def refresh(self):
        db = self._load_db()
        self._units = db.list_custom_units() if db else []

        self._table.setRowCount(len(self._units))
        for r, u in enumerate(self._units):
            self._table.setItem(r, 0, _cell(u.get("symbol", ""), _PEACH))
            self._table.setItem(r, 1, _cell(u.get("dimension", "")))
            self._table.setItem(r, 2, _cell(str(u.get("to_si", ""))))

        self._count_lbl.setText(f"{len(self._units)} custom unit(s)")
        self._promote_btn.setEnabled(False)
        self._del_btn.setEnabled(False)

    def _on_selection(self):
        has = bool(self._table.selectedItems())
        self._promote_btn.setEnabled(has)
        self._del_btn.setEnabled(has)

    def _selected_unit(self) -> dict | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._units[rows[0].row()]

    def _on_promote(self):
        u = self._selected_unit()
        if not u:
            return

        units_data = _read_units_json()
        systems    = _all_systems(units_data)

        dlg = AddUnitDialog(
            ["_common"] + systems,
            prefill=u,
            parent=self,
        )
        dlg.setWindowTitle("Promote Custom Unit to Built-in")
        if dlg.exec() != QDialog.Accepted:
            return

        result = dlg.get_unit()
        code   = result["code"]
        system = result["system"]
        entry  = result["entry"]

        # Duplicate check
        all_codes = set()
        for blk in (["_common"] + systems):
            all_codes |= set(units_data.get(blk, {}).keys())
        if code in all_codes:
            QMessageBox.warning(self, "Duplicate", f"Unit code '{code}' already exists in units.json.")
            return

        # Write to units.json
        if system not in units_data:
            units_data[system] = {}
        units_data[system][code] = entry
        _write_units_json(units_data)

        # Remove from CustomMaterialDB
        db = self._load_db()
        if db:
            try:
                db.delete_custom_unit(u["symbol"])
            except Exception as e:
                print(f"[UnitManager] Could not remove from DB: {e}")

        self.refresh()
        QMessageBox.information(
            self, "Promoted",
            f"'{code}' moved to units.json ({system}).\n\nRestart the app to apply changes."
        )

    def _on_delete(self):
        u = self._selected_unit()
        if not u:
            return
        sym = u.get("symbol", "?")
        if QMessageBox.question(
            self, "Delete Custom Unit",
            f"Delete custom unit '{sym}'?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return

        db = self._load_db()
        if db:
            try:
                db.delete_custom_unit(sym)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not delete: {e}")
                return
        self.refresh()


# ---------------------------------------------------------------------------
# Tab 3 - Tester
# ---------------------------------------------------------------------------

class TesterTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(12)

        # Input
        in_row = QHBoxLayout()
        in_row.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type any unit string - e.g.  Sqm.   MT   Nos.   cft   RMt")
        self._input.setFixedHeight(36)
        self._input.returnPressed.connect(self._on_test)
        in_row.addWidget(self._input, stretch=1)

        test_btn = QPushButton("Test")
        test_btn.setFixedHeight(36)
        test_btn.setFixedWidth(80)
        test_btn.setStyleSheet(
            f"QPushButton {{ background: {_BLUE}; color: {_SURFACE};"
            f" border: none; border-radius: 4px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #a8c8ff; }}"
        )
        test_btn.clicked.connect(self._on_test)
        in_row.addWidget(test_btn)
        layout.addLayout(in_row)

        # Result card
        self._result = QFrame()
        self._result.setStyleSheet(
            f"QFrame {{ background: {_BG2}; border: 1px solid {_BORDER};"
            f" border-radius: 6px; }}"
        )
        rl = QVBoxLayout(self._result)
        rl.setContentsMargins(16, 14, 16, 14)
        rl.setSpacing(6)

        self._res_status = QLabel("Enter a unit string above and click Test.")
        sf = QFont(); sf.setPointSize(11); sf.setBold(True)
        self._res_status.setFont(sf)
        rl.addWidget(self._res_status)

        self._res_detail = QLabel()
        self._res_detail.setWordWrap(True)
        self._res_detail.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        rl.addWidget(self._res_detail)

        layout.addWidget(self._result)
        layout.addStretch()

        hint = QLabel(
            "The tester reads units.json directly - reflects any units added in this session "
            "without needing an app restart."
        )
        hint.setStyleSheet(f"color: {_DIM}; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _on_test(self):
        raw = self._input.text().strip()
        if not raw:
            return

        result = _resolve_fresh(raw)

        if result:
            self._res_status.setStyleSheet(f"color: {_GREEN}; font-weight: bold;")
            self._res_status.setText(f"✓  Recognised  →  {result['code']}")
            self._res_detail.setText(
                f"Dimension: {result['dimension']}    "
                f"to_si: {result['to_si']}    "
                f"Display: {result['display']}    "
                f"({result['via']})"
            )
        else:
            self._res_status.setStyleSheet(f"color: {_RED}; font-weight: bold;")
            self._res_status.setText(f"✗  Unrecognised  -  '{raw}'")
            self._res_detail.setText(
                "This string is not in units.json as a canonical code or alias. "
                "Add it via the Built-in Units tab or define it as a custom unit in the material dialog."
            )


# ---------------------------------------------------------------------------
# Main Dialog
# ---------------------------------------------------------------------------

class UnitManagerDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unit Manager")
        self.setMinimumSize(820, 540)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinMaxButtonsHint
        )
        self.setStyleSheet(_BASE_STYLE)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(60)
        hdr.setStyleSheet(f"background: {_BG2}; border-bottom: 1px solid {_BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)

        title = QLabel("Unit Manager")
        tf = QFont(); tf.setPointSize(12); tf.setBold(True)
        title.setFont(tf)
        hl.addWidget(title)
        hl.addStretch()

        badge = QLabel("units.json")
        badge.setStyleSheet(
            f"background: {_BG3}; color: {_DIM}; font-size: 10px;"
            f" border-radius: 3px; padding: 2px 8px;"
        )
        hl.addWidget(badge)
        layout.addWidget(hdr)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setContentsMargins(0, 0, 0, 0)

        self._builtin_tab = BuiltinUnitsTab()
        self._custom_tab  = CustomUnitsTab()
        self._tester_tab  = TesterTab()

        self._tabs.addTab(self._builtin_tab, "Built-in Units")
        self._tabs.addTab(self._custom_tab,  "Custom Units")
        self._tabs.addTab(self._tester_tab,  "Tester")

        layout.addWidget(self._tabs)

        # Footer
        footer = QWidget()
        footer.setFixedHeight(36)
        footer.setStyleSheet(f"background: {_BG2}; border-top: 1px solid {_BORDER};")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 0, 20, 0)

        tip = QLabel("Changes to units.json require an app restart to take effect in the main app.")
        tip.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        fl.addWidget(tip)
        fl.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(24)
        refresh_btn.clicked.connect(self._refresh_all)
        fl.addWidget(refresh_btn)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(24)
        close_btn.clicked.connect(self.reject)
        fl.addWidget(close_btn)

        layout.addWidget(footer)

    def closeEvent(self, event):
        event.accept()

    def _refresh_all(self):
        self._builtin_tab.refresh()
        self._custom_tab.refresh()


