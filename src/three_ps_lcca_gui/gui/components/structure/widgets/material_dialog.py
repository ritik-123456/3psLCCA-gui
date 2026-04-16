"""
gui/components/structure/widgets/material_dialog.py
====================================================
MaterialDialog and its helper classes / functions.
Extracted from manager.py so it can be imported by other modules
(carbon_emission, recycling, etc.) without pulling in StructureManagerWidget.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QDialog,
    QLineEdit,
    QFrame,
    QLabel,
    QMessageBox,
    QCheckBox,
    QComboBox,
    QCompleter,
    QScrollArea,
)
from PySide6.QtCore import Qt, QUrl, QStringListModel
from PySide6.QtGui import (
    QDoubleValidator,
    QDesktopServices,
    QStandardItemModel,
    QStandardItem,
)

from ...utils.definitions import (
    _CONSTRUCTION_UNITS,
    UNIT_TO_SI,
    UNIT_DIMENSION,
    SI_BASE_UNITS,
    UNIT_DISPLAY,
)
from ...utils.display_format import fmt, fmt_comma, DECIMAL_PLACES
from ...utils.unit_resolver import (
    get_custom_units,
    load_custom_units,
    _UNIT_ALIASES as _SOR_UNIT_ALIASES,
)
from ...utils.input_fields.add_material import FIELD_DEFINITIONS
from ...utils.unit_resolver import get_unit_info as _get_unit_info_impl

import os
import sys

from three_ps_lcca_gui.gui.themes import get_token

try:
    from ..registry.custom_material_db import CustomMaterialDB, CUSTOM_PREFIX
except ImportError:
    CustomMaterialDB = None
    CUSTOM_PREFIX = "custom::"

# NOTE: material_catalog and search_engine live inside the registry directory
# which is only added to sys.path at runtime by _ensure_registry_on_path().
# These are therefore imported lazily inside each function that needs them.


# ---------------------------------------------------------------------------
# Info Popup
# ---------------------------------------------------------------------------


class InfoPopup(QDialog):
    def __init__(self, field_key: str, parent=None):
        super().__init__(parent)
        defn = FIELD_DEFINITIONS.get(field_key, {})

        self.setWindowTitle(defn.get("label", field_key))
        self.setMinimumWidth(360)
        self.setMaximumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(420, 260)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title_lbl = QLabel(f"<b>{defn.get('label', field_key)}</b>")
        title_lbl.setStyleSheet("font-size: 13px;")
        layout.addWidget(title_lbl)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        expl_lbl = QLabel(defn.get("explanation", "No description available."))
        expl_lbl.setWordWrap(True)
        expl_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(expl_lbl)

        btn_row = QHBoxLayout()
        doc_slug = defn.get("doc_slug", "")
        if doc_slug:
            read_more = QPushButton("Read More →")
            read_more.setStyleSheet("font-weight: 600; border: none;")
            read_more.setCursor(Qt.PointingHandCursor)
            # read_more.clicked.connect(
            #     lambda: QDesktopServices.openUrl(QUrl(f"{BASE_DOCS_URL}{doc_slug}"))
            # )
            btn_row.addWidget(read_more)

        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------


def _field_block(key: str, input_widget: QWidget, parent_dialog: QDialog) -> QWidget:
    defn = FIELD_DEFINITIONS.get(key, {})
    label = defn.get("label", key)
    expl = defn.get("explanation", "")
    required = defn.get("required", False)

    block = QWidget()
    layout = QVBoxLayout(block)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(3)

    title_lbl = QLabel(f"{label} *" if required else label)
    title_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
    layout.addWidget(title_lbl)

    expl_row = QHBoxLayout()
    expl_row.setContentsMargins(0, 0, 0, 0)
    expl_row.setSpacing(6)

    expl_lbl = QLabel(expl)
    expl_lbl.setWordWrap(True)
    expl_lbl.setStyleSheet("font-size: 11px;")
    expl_row.addWidget(expl_lbl, stretch=1)

    info_btn = QPushButton("ⓘ")
    info_btn.setFixedSize(22, 22)
    info_btn.setFlat(True)
    info_btn.setStyleSheet(
        "QPushButton {font-weight: bold; font-size: 13px; border: none; }"
    )
    info_btn.setFocusPolicy(Qt.NoFocus)
    info_btn.setCursor(Qt.PointingHandCursor)
    info_btn.clicked.connect(lambda: InfoPopup(key, parent_dialog).exec())
    expl_row.addWidget(info_btn, alignment=Qt.AlignTop)

    layout.addLayout(expl_row)

    input_widget.setMinimumHeight(30)
    layout.addWidget(input_widget)

    return block


def _section_header(title: str) -> QLabel:
    lbl = QLabel(f"<b>{title}</b>")
    lbl.setStyleSheet("font-size: 13px; margin-top: 4px;")
    return lbl


def _lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight: 600; font-size: 11px;")
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


# ---------------------------------------------------------------------------
# CustomUnitDialog
# ---------------------------------------------------------------------------


class CustomUnitDialog(QDialog):
    # (dimension label, SI base unit code, display symbol, placeholder example, note)
    _DIMS = [
        ("Mass", "kg", "kg", "e.g. 50  (1 bag = 50 kg)", "SI base: kilogram (kg)"),
        ("Length", "m", "m", "e.g. 0.3048  (1 ft = 0.3048 m)", "SI base: meter (m)"),
        (
            "Area",
            "m2",
            "m²",
            "e.g. 25.29  (1 perch = 25.29 m²)",
            "SI base: square meter (m²)",
        ),
        (
            "Volume",
            "m3",
            "m³",
            "e.g. 0.0283  (1 cft = 0.0283 m³)",
            "SI base: cubic meter (m³)",
        ),
        (
            "Count",
            "nos",
            "nos",
            "e.g. 100  (1 bundle = 100 nos)",
            "SI base: number (nos)",
        ),
    ]

    def __init__(self, parent=None, existing_symbols: list | None = None):
        super().__init__(parent)
        self._existing_symbols = {s.lower() for s in (existing_symbols or [])}

        self.setWindowTitle("Add Custom Unit")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)

        dbl = QDoubleValidator()
        dbl.setBottom(1e-12)
        dbl.setNotation(QDoubleValidator.StandardNotation)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        desc = QLabel(
            "Define a custom unit by selecting its dimension and providing "
            "its equivalent in the SI base unit."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 11px; color: {get_token('text_secondary')};")
        layout.addWidget(desc)

        # ── Symbol + Name ─────────────────────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        sym_col = QVBoxLayout()
        sym_col.setSpacing(3)
        sym_col.addWidget(_lbl("Symbol *"))
        self.symbol_in = QLineEdit()
        self.symbol_in.setPlaceholderText("e.g. bag, rft, perch")
        self.symbol_in.setMinimumHeight(32)
        sym_col.addWidget(self.symbol_in)
        row1.addLayout(sym_col, stretch=1)

        name_col = QVBoxLayout()
        name_col.setSpacing(3)
        name_col.addWidget(_lbl("Name (optional)"))
        self.name_in = QLineEdit()
        self.name_in.setPlaceholderText("e.g. Cement Bag")
        self.name_in.setMinimumHeight(32)
        name_col.addWidget(self.name_in)
        row1.addLayout(name_col, stretch=2)

        layout.addLayout(row1)

        # ── Dimension selector ────────────────────────────────────────────────
        layout.addWidget(_lbl("Dimension *"))
        self.dim_cb = QComboBox()
        self.dim_cb.setMinimumHeight(32)
        self.dim_cb.wheelEvent = lambda event: event.ignore()
        for dim_label, si_code, si_sym, _, _ in self._DIMS:
            self.dim_cb.addItem(f"{dim_label}  (SI base: {si_sym})", dim_label)
        layout.addWidget(self.dim_cb)

        # ── SI equivalent row ─────────────────────────────────────────────────
        layout.addWidget(_lbl("SI Equivalent *"))
        conv_row = QHBoxLayout()
        conv_row.setSpacing(8)
        self.conv_prefix_lbl = QLabel("1 unit  =")
        self.conv_prefix_lbl.setStyleSheet(f"color: {get_token('text_secondary')}; font-size: 12px;")
        conv_row.addWidget(self.conv_prefix_lbl)
        self.conv_in = QLineEdit()
        self.conv_in.setMinimumHeight(32)
        self.conv_in.setValidator(dbl)
        conv_row.addWidget(self.conv_in, stretch=1)
        self.si_sym_lbl = QLabel("kg")
        self.si_sym_lbl.setStyleSheet(
            f"background: {get_token('surface')}; color: {get_token('text_secondary')}; padding: 4px 8px; "
            f"border: 1px solid {get_token('surface_mid')}; border-radius: 4px; font-size: 12px;"
        )
        self.si_sym_lbl.setMinimumHeight(32)
        self.si_sym_lbl.setMinimumWidth(48)
        self.si_sym_lbl.setAlignment(Qt.AlignCenter)
        conv_row.addWidget(self.si_sym_lbl)
        layout.addLayout(conv_row)

        # ── Live preview ──────────────────────────────────────────────────────
        self.preview_lbl = QLabel("")
        self.preview_lbl.setStyleSheet(
            f"font-size: 12px; color: {get_token('success')}; background: {get_token('success', 'pressed')}; "
            f"padding: 6px 10px; border-radius: 4px;"
        )
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setVisible(False)
        layout.addWidget(self.preview_lbl)

        # ── Note ──────────────────────────────────────────────────────────────
        self._note_lbl = QLabel("")
        self._note_lbl.setStyleSheet(f"font-size: 10px; color: {get_token('text_disabled')};")
        self._note_lbl.setWordWrap(True)
        layout.addWidget(self._note_lbl)

        layout.addStretch()

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("Add Unit")
        self._add_btn.setStyleSheet("font-weight: bold; padding: 6px 20px;")
        self._add_btn.setMinimumHeight(32)
        self._add_btn.clicked.connect(self._validate_and_accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── Wire signals ──────────────────────────────────────────────────────
        self.dim_cb.currentIndexChanged.connect(self._on_dim_changed)
        self.symbol_in.textChanged.connect(self._update_preview)
        self.conv_in.textChanged.connect(self._update_preview)

        self._on_dim_changed(0)  # initialise labels for Mass

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_dim_changed(self, idx: int):
        if idx < 0 or idx >= len(self._DIMS):
            return
        _, _, si_sym, placeholder, note = self._DIMS[idx]
        self.si_sym_lbl.setText(si_sym)
        self.conv_in.setPlaceholderText(placeholder.split("(")[0].strip())
        self._note_lbl.setText(note)
        self._update_preview()

    def _update_preview(self):
        sym = self.symbol_in.text().strip()
        raw = self.conv_in.text().strip()
        idx = self.dim_cb.currentIndex()

        # Update "1 <symbol> =" prefix
        self.conv_prefix_lbl.setText(f"1 {sym}  =" if sym else "1 unit  =")

        if not sym or not raw:
            self.preview_lbl.setVisible(False)
            return

        try:
            val = float(raw)
            if val <= 0:
                raise ValueError
        except ValueError:
            self.preview_lbl.setVisible(False)
            return

        _, _, si_sym, _, _ = self._DIMS[idx]
        self.preview_lbl.setText(f"1 {sym} = {val:g} {si_sym}")
        self.preview_lbl.setVisible(True)

    # ── Validation & output ───────────────────────────────────────────────────

    def _validate_and_accept(self):
        sym = self.symbol_in.text().strip()
        if not sym:
            QMessageBox.critical(self, "Error", "Symbol is required.")
            return

        if sym.lower() in self._existing_symbols:
            QMessageBox.critical(
                self,
                "Symbol Already Exists",
                f'"{sym}" is already defined. Choose a different symbol.',
            )
            return

        raw = self.conv_in.text().strip()
        try:
            val = float(raw)
            if val <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.critical(
                self, "Invalid Value", "SI equivalent must be a positive number."
            )
            return

        self.accept()

    def get_unit(self) -> dict:
        idx = self.dim_cb.currentIndex()
        dim_label, si_code, si_sym, _, _ = self._DIMS[max(idx, 0)]
        return {
            "symbol": self.symbol_in.text().strip(),
            "name": self.name_in.text().strip(),
            "dimension": dim_label,
            "to_si": float(self.conv_in.text()),
            "si_unit": si_code,
        }


# ---------------------------------------------------------------------------
# SOR / registry helpers
# ---------------------------------------------------------------------------


def _unit_sym(code: str) -> str:
    """
    Return the pretty display symbol for a unit code.
    Handles compound codes like 'm2-mm' → 'm²-mm' by prettifying each
    dash-separated part individually.
    """
    if not code:
        return "unit"

    code = code.replace(" ", "").strip()

    if code in UNIT_DISPLAY:
        return UNIT_DISPLAY[code]

    # Compound unit - prettify each part separated by '-'
    parts = code.split("-")
    if len(parts) > 1:
        return "-".join(UNIT_DISPLAY.get(p, p) for p in parts)

    return code


def _resolve_unit_code(sor_unit: str, combo: "QComboBox") -> int:
    """
    Find the combo index for sor_unit.  If no standard match is found and
    add_if_missing=True (default), the raw unit string is appended as a
    plain-text fallback item so compound units like 'sqm-mm' are preserved.
    """
    if not sor_unit:
        return -1
    idx = combo.findData(sor_unit)
    if idx >= 0:
        return idx
    lower = sor_unit.lower()
    idx = combo.findData(lower)
    if idx >= 0:
        return idx
    alias = _SOR_UNIT_ALIASES.get(lower)
    if alias:
        idx = combo.findData(alias)
        if idx >= 0:
            return idx
    # Unit not in the standard list - append it so it isn't silently dropped.
    combo.addItem(_unit_sym(sor_unit), sor_unit)
    return combo.count() - 1


def _registry_dir() -> str:
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "registry")
    )


def _ensure_registry_on_path():
    d = _registry_dir()
    if d not in sys.path:
        sys.path.insert(0, d)


def _list_sor_options(country: str = None) -> list[dict]:
    _ensure_registry_on_path()
    result = []
    try:
        from material_catalog import list_databases

        raw = list_databases(country=country.strip() if country else None)
        for e in raw:
            if e.get("status") != "OK":
                continue
            region = e.get("region", "")
            result.append(
                {"db_key": e["db_key"], "region": region, "label": e["db_key"]}
            )
    except Exception as ex:
        print(f"[MaterialDialog] Could not list SOR options: {ex}")

    try:
        if CustomMaterialDB is not None:
            cdb = CustomMaterialDB()
            for db_name in cdb.list_db_names():
                result.append(
                    {
                        "db_key": f"{CUSTOM_PREFIX}{db_name}",
                        "region": "Custom",
                        "label": f"{db_name}  (Custom)",
                    }
                )
    except Exception as ex:
        print(f"[MaterialDialog] Could not list custom databases: {ex}")

    return result


def _list_sor_types(db_keys: list = None) -> list[str]:
    _ensure_registry_on_path()
    try:
        from material_catalog import list_databases as _list_dbs

        available = [
            e["db_key"]
            for e in _list_dbs()
            if e.get("status") == "OK" and (db_keys is None or e["db_key"] in db_keys)
        ]
        if not available:
            return []
        from search_engine import MaterialSearchEngine

        engine = MaterialSearchEngine(db_keys=db_keys)
        return sorted(
            {
                item.get("type", "").strip()
                for item in engine._iter_items()
                if item.get("type", "").strip()
            }
        )
    except Exception:
        return []


_REQUIRED_ITEM_KEYS = (
    "name",
    "unit",
    "rate",
    "rate_src",
    "carbon_emission",
    "carbon_emission_units_den",
    "conversion_factor",
    "carbon_emission_src",
)
_ITEM_DEFAULTS = {
    "rate": "not_available",
    "rate_src": "not_available",
    "carbon_emission": "not_available",
    "carbon_emission_units_den": "not_available",
    "conversion_factor": "not_available",
    "carbon_emission_src": "not_available",
}


def _validate_item(item: dict) -> bool:
    """
    Ensure item has all required schema keys, filling optional ones with
    'not_available' defaults rather than dropping the item entirely.
    Returns False only if the truly essential keys (name, unit) are missing.
    """
    if not item.get("name") or not item.get("unit"):
        return False
    for key, default in _ITEM_DEFAULTS.items():
        item.setdefault(key, default)
    return True


def build_excel_snapshot(values_dict: dict) -> dict:
    """
    Build a complete snapshot from an Excel-imported values_dict.
    Captures all parsed fields to ensure 100% data parity for audit logs.
    """
    # Create a shallow copy and explicitly set the action tag
    snapshot = dict(values_dict)
    snapshot["action"] = "excel"

    # Optional: Remove internal keys that start with "_" if you want to
    # keep only "real" data in the snapshot.
    return {k: v for k, v in snapshot.items() if not k.startswith("_")}


def _load_material_suggestions(db_keys: list = None, comp_name: str = None) -> dict:
    _ensure_registry_on_path()

    if db_keys is not None:
        regular_keys = [k for k in db_keys if not k.startswith("custom::")]
        custom_names = [
            k[len("custom::") :] for k in db_keys if k.startswith("custom::")
        ]
        load_all_custom = False
    else:
        regular_keys = None
        custom_names = []
        load_all_custom = True

    result = {}
    comp_lower = comp_name.strip().lower() if comp_name else None

    skip_regular = db_keys is not None and not regular_keys
    if not skip_regular:
        try:
            from material_catalog import list_databases as _list_dbs

            _available = [
                e["db_key"]
                for e in _list_dbs()
                if e.get("status") == "OK"
                and (regular_keys is None or e["db_key"] in regular_keys)
            ]
            if not _available:
                skip_regular = True
        except Exception:
            skip_regular = True

    if not skip_regular:
        try:
            from search_engine import MaterialSearchEngine

            engine = MaterialSearchEngine(db_keys=regular_keys)

            if comp_lower:
                for item in engine._iter_items():
                    if not _validate_item(item):
                        print(
                            f"[MaterialDialog] Skipping item with missing schema keys: {item.get('name', '<unnamed>')}"
                        )
                        continue
                    t = item.get("type", "").lower()
                    if t == comp_lower or comp_lower in t or t in comp_lower:
                        name = item.get("name", "").strip()
                        if name:
                            result[name] = item
                if not result:
                    for item in engine._iter_items():
                        if not _validate_item(item):
                            continue
                        name = item.get("name", "").strip()
                        if name:
                            result[name] = item
            else:
                for item in engine._iter_items():
                    if not _validate_item(item):
                        print(
                            f"[MaterialDialog] Skipping item with missing schema keys: {item.get('name', '<unnamed>')}"
                        )
                        continue
                    name = item.get("name", "").strip()
                    if name:
                        result[name] = item
        except Exception as e:
            print(f"[MaterialDialog] Could not load material suggestions: {e}")

    if load_all_custom or custom_names:
        try:
            from ..registry.custom_material_db import CustomMaterialDB

            cdb = CustomMaterialDB()
            names_to_load = cdb.list_db_names() if load_all_custom else custom_names
            for db_name in names_to_load:
                for item in cdb.get_items(db_name):
                    if not _validate_item(item):
                        print(
                            f"[MaterialDialog] Skipping custom item with missing schema keys: {item.get('name', '<unnamed>')}"
                        )
                        continue
                    name = item.get("name", "").strip()
                    if not name:
                        continue
                    if comp_lower:
                        t = item.get("type", "").lower()
                        if not (t == comp_lower or comp_lower in t or t in comp_lower):
                            continue
                    result[name] = item
        except Exception as e:
            print(f"[MaterialDialog] Could not load custom material suggestions: {e}")

    return result


# ---------------------------------------------------------------------------
# _SaveToCustomDBDialog
# ---------------------------------------------------------------------------


class _SaveToCustomDBDialog(QDialog):
    def __init__(self, existing_db_names: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save to Custom Database")
        self.setMinimumWidth(360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        layout.addWidget(
            QLabel(
                "Select an existing database or type a new name\n"
                "(e.g. biharSOR-2026, MyMaterials):"
            )
        )

        self.db_combo = QComboBox()
        self.db_combo.setEditable(True)
        self.db_combo.setMinimumHeight(32)
        self.db_combo.addItems(existing_db_names)
        self.db_combo.setCurrentIndex(-1)
        if self.db_combo.lineEdit():
            self.db_combo.lineEdit().setPlaceholderText("e.g. biharSOR-2026")
        layout.addWidget(self.db_combo)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.setMinimumHeight(32)
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _on_save(self):
        if not self.selected_name():
            QMessageBox.warning(self, "Missing Name", "Enter a database name to continue.")
            return
        self.accept()

    def selected_name(self) -> str:
        return self.db_combo.currentText().strip()


# ---------------------------------------------------------------------------
# Migration helper - moves custom units embedded in old project data → DB
# ---------------------------------------------------------------------------


def _migrate_embedded_custom_units(values: dict) -> None:
    """If *values* contains a legacy '_custom_units' list (old per-material
    storage), save any unknown symbols to the global DB and refresh the cache.
    Safe to call on every dialog open; does nothing when no legacy data exists.
    """
    raw = values.get("_custom_units") or values.get("_custom_unit")
    if not raw:
        return
    units = [raw] if isinstance(raw, dict) else list(raw)
    if not units:
        return

    known = {c["symbol"] for c in get_custom_units()}
    new_units = [u for u in units if u.get("symbol") and u["symbol"] not in known]
    if not new_units:
        return

    try:
        if CustomMaterialDB is None:
            raise ImportError("custom_material_db not available")
        cdb = CustomMaterialDB()
        for u in new_units:
            cdb.save_custom_unit(u)
        load_custom_units()  # refresh global cache
    except Exception as exc:
        print(f"[MaterialDialog] Custom unit migration failed: {exc}")


# ---------------------------------------------------------------------------
# MaterialDialog
# ---------------------------------------------------------------------------


class MaterialDialog(QDialog):
    _CUSTOM_CODE = "__custom__"
    _NO_SUGGESTIONS_CODE = "__no_suggestions__"

    def __init__(
        self,
        comp_name: str,
        parent=None,
        data: dict = None,
        emissions_only: bool = False,
        recyclability_only: bool = False,
        country: str = None,
        sor_db_key: str = None,
    ):
        super().__init__(parent)
        self.is_edit = data is not None
        self.emissions_only = emissions_only
        self.recyclability_only = recyclability_only
        self._comp_name = comp_name
        self._sor_item = None
        self._sor_filled_name = None  # name that triggered the last autofill
        self._sor_filling = False
        self._is_modified_by_user = False
        self._is_customized = False
        self._pre_allow_edit_source = None  # saved when "Allow editing" is checked
        self._sor_carbon_available = True  # False when SOR has no carbon data
        self._db_original = {}  # immutable snapshot of DB values at suggestion time

        mat_name = (
            data.get("values", {}).get("material_name", "") if data else ""
        ) or comp_name
        if recyclability_only:
            self.setWindowTitle(f"Edit Recyclability - {mat_name}")
        elif emissions_only:
            self.setWindowTitle(f"Edit Emission Data - {mat_name}")
        elif self.is_edit:
            self.setWindowTitle(f"Edit Material - {comp_name}")
        else:
            self.setWindowTitle(f"Add Material - {comp_name}")
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        v = data.get("values", {}) if self.is_edit else {}
        s = data.get("state", {}) if self.is_edit else {}
        # Restore the immutable DB snapshot saved when this material was first added.
        # "db_original" is the canonical meta key; "db_snapshot" is accepted as a
        # legacy alias so old project files still load correctly.
        _meta = data.get("meta", {}) if data else {}
        self._db_original = _meta.get("db_original") or _meta.get("db_snapshot") or {}

        # Migrate any custom units embedded in old project data → global DB
        _migrate_embedded_custom_units(v)

        dbl = QDoubleValidator()
        dbl.setNotation(QDoubleValidator.StandardNotation)
        dbl.setDecimals(DECIMAL_PLACES)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(20, 16, 20, 12)
        root.setSpacing(10)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # SOR database is selected project-wide (General Info → Project Settings).
        self.sor_cb = None
        self._sor_db_key = (sor_db_key or "").strip()

        # ── Active SOR info label ─────────────────────────────────────────
        if not (emissions_only or recyclability_only):
            sor_info_row = QHBoxLayout()
            sor_info_row.setContentsMargins(0, 0, 0, 0)
            sor_info_row.setSpacing(4)
            sor_info_row.addWidget(QLabel("Suggestions from:"))
            _sor_val = (
                self._sor_db_key
                if self._sor_db_key
                else "- not set (configure in Project Settings)"
            )
            sor_val_lbl = QLabel(_sor_val)
            sor_val_lbl.setStyleSheet(
                f"font-size: 11px; color: {get_token('text_secondary')}; font-style: italic;"
            )
            sor_info_row.addWidget(sor_val_lbl, stretch=1)
            root.addLayout(sor_info_row)

        # ── Sub-category filter ───────────────────────────────────────────
        self.type_filter_cb = None
        if self._sor_db_key and not (emissions_only or recyclability_only):
            sub_row = QHBoxLayout()
            sub_row.setContentsMargins(0, 0, 0, 0)
            sub_row.setSpacing(8)
            sub_lbl = QLabel("Sub-category:")
            sub_lbl.setStyleSheet(f"font-size: 11px; color: {get_token('text_secondary')};")
            sub_row.addWidget(sub_lbl)
            self.type_filter_cb = QComboBox()
            self.type_filter_cb.setMinimumHeight(26)
            self.type_filter_cb.wheelEvent = lambda event: event.ignore()
            sub_row.addWidget(self.type_filter_cb, stretch=1)
            root.addLayout(sub_row)
            self._populate_type_filter(preselect=comp_name)
            self.type_filter_cb.currentIndexChanged.connect(
                self._on_type_filter_changed
            )

        # ── Material Name (Always visible) ────────────────────────────────
        root.addWidget(_lbl("Material Name *"))
        self.name_in = QLineEdit(v.get("material_name", ""))
        self.name_in.setPlaceholderText(
            "e.g. Ready-mix Concrete M25  (type ? to browse all)"
        )
        self.name_in.setMinimumHeight(32)
        root.addWidget(self.name_in)

        # ── Item ID (Always visible) ──────────────────────────────────────
        root.addWidget(_lbl("Item ID / SOR Code"))
        self.id_in = QLineEdit(v.get("id", ""))
        self.id_in.setPlaceholderText("e.g. 12.01 (Leave blank for manual)")
        self.id_in.setMinimumHeight(32)
        root.addWidget(self.id_in)

        # ── Completer ─────────────────────────────────────────────────────
        self._suggestions = {}
        self._active_completer = None
        self._skip_suggestions = False
        self._ui_ready = False
        self._user_edited_snapshot = {}  # saved when user unchecks "Allow editing"
        self._reload_suggestions()
        self.name_in.textChanged.connect(self._on_name_search_changed)
        if self.sor_cb:
            self.sor_cb.currentIndexChanged.connect(self._on_sor_changed)

        self._skip_btn = None

        # ── Allow-edit checkbox ───────────────────────────────────────────
        self._allow_edit_chk = QCheckBox("Allow editing DB-filled values")
        self._allow_edit_chk.setEnabled(False)
        self._allow_edit_chk.toggled.connect(self._on_allow_edit_toggled)
        root.addWidget(self._allow_edit_chk)

        # ── Quantity + Unit ───────────────────────────────────────────────
        qty_unit_row = QHBoxLayout()
        qty_unit_row.setSpacing(12)

        qty_col = QVBoxLayout()
        qty_col.setSpacing(3)
        qty_col.addWidget(_lbl("Quantity *"))
        qty_val = v.get("quantity", "")
        self.qty_in = QLineEdit("" if not qty_val else fmt(qty_val))
        self.qty_in.setPlaceholderText("e.g. 100")
        self.qty_in.setMinimumHeight(32)
        self.qty_in.setValidator(dbl)
        qty_col.addWidget(self.qty_in)
        qty_unit_row.addLayout(qty_col, stretch=1)

        unit_col = QVBoxLayout()
        unit_col.setSpacing(3)
        unit_col.addWidget(_lbl("Unit *"))
        current_unit = v.get("unit", "m3")
        self.unit_in = self._build_unit_dropdown(current_unit, None)
        self.unit_in.wheelEvent = lambda event: event.ignore()
        self.unit_in.currentIndexChanged.connect(self._on_unit_combobox_changed)
        unit_col.addWidget(self.unit_in)
        qty_unit_row.addLayout(unit_col, stretch=2)

        root.addLayout(qty_unit_row)

        # ── Rate + Rate Source ────────────────────────────────────────────
        rate_row = QHBoxLayout()
        rate_row.setSpacing(12)

        rate_col = QVBoxLayout()
        rate_col.setSpacing(3)
        rate_col.addWidget(_lbl("Rate (Cost)"))
        rate_val = v.get("rate", "")
        self.rate_in = QLineEdit("" if not rate_val else str(rate_val))
        self.rate_in.setPlaceholderText("e.g. 4500")
        self.rate_in.setMinimumHeight(32)
        self.rate_in.setValidator(dbl)
        rate_col.addWidget(self.rate_in)
        rate_row.addLayout(rate_col, stretch=1)

        src_col = QVBoxLayout()
        src_col.setSpacing(3)
        src_col.addWidget(_lbl("Rate Source"))
        # Store original source so it can be restored when "Allow editing" is unchecked
        self._original_source = v.get("rate_source", "")
        self.src_in = QLineEdit(self._original_source)
        self.src_in.setPlaceholderText("e.g. DSR 2023, Market Rate")
        self.src_in.setMinimumHeight(32)
        # Clear the source field when editing an existing material;
        # it is restored when the user unchecks "Allow editing DB-filled values"
        # or selects a new DB suggestion.
        if self.is_edit:
            self.src_in.clear()
        src_col.addWidget(self.src_in)
        rate_row.addLayout(src_col, stretch=2)

        root.addLayout(rate_row)

        # ── Carbon Emission ───────────────────────────────────────────────
        root.addWidget(_divider())

        carbon_hdr = QHBoxLayout()
        carbon_title = QLabel("Carbon Emission")
        carbon_title.setStyleSheet("font-weight: 600; font-size: 12px;")
        carbon_hdr.addWidget(carbon_title)
        carbon_hdr.addStretch()
        self.carbon_chk = QCheckBox("Include")
        self.carbon_chk.setChecked(s.get("included_in_carbon_emission", True))
        carbon_hdr.addWidget(self.carbon_chk)
        root.addLayout(carbon_hdr)

        self.carbon_container = QWidget()
        cl = QVBoxLayout(self.carbon_container)
        cl.setContentsMargins(0, 4, 0, 0)
        cl.setSpacing(8)

        ef_row = QHBoxLayout()
        ef_row.setSpacing(12)

        ef_col = QVBoxLayout()
        ef_col.setSpacing(3)
        ef_col.addWidget(_lbl("Emission Factor"))
        ef_val = v.get("carbon_emission", "")
        self.carbon_em_in = QLineEdit("" if not ef_val else str(ef_val))
        self.carbon_em_in.setPlaceholderText("e.g. 0.179")
        self.carbon_em_in.setMinimumHeight(32)
        self.carbon_em_in.setValidator(dbl)
        ef_col.addWidget(self.carbon_em_in)
        ef_row.addLayout(ef_col, stretch=1)

        denom_col = QVBoxLayout()
        denom_col.setSpacing(3)
        denom_col.addWidget(_lbl("Per Unit  (kgCO₂e / ...)"))
        self.carbon_denom_cb = QComboBox()
        self.carbon_denom_cb.setMinimumHeight(32)
        self.carbon_denom_cb.wheelEvent = lambda event: event.ignore()
        self.carbon_denom_cb.setModel(self._build_full_unit_model())

        existing_carbon_unit = v.get("carbon_unit", "")
        if existing_carbon_unit and "/" in existing_carbon_unit:
            saved_denom = existing_carbon_unit.split("/")[-1].strip()
            didx = _resolve_unit_code(saved_denom, self.carbon_denom_cb)
            if didx >= 0:
                self.carbon_denom_cb.setCurrentIndex(didx)
        else:
            didx = self.carbon_denom_cb.findData(current_unit)
            if didx >= 0:
                self.carbon_denom_cb.setCurrentIndex(didx)

        denom_col.addWidget(self.carbon_denom_cb)
        ef_row.addLayout(denom_col, stretch=1)

        src_col = QVBoxLayout()
        src_col.setSpacing(3)
        src_col.addWidget(_lbl("Emission Factor Source"))
        self._original_carbon_src = v.get("carbon_emission_src", "")
        self.carbon_src_in = QLineEdit(self._original_carbon_src)
        self.carbon_src_in.setPlaceholderText("e.g. ICE v3.0, IPCC")
        self.carbon_src_in.setMinimumHeight(32)
        if self.is_edit:
            self.carbon_src_in.clear()
        src_col.addWidget(self.carbon_src_in)
        ef_row.addLayout(src_col, stretch=1)

        cl.addLayout(ef_row)

        self.cf_row_widget = QWidget()
        cf_inner = QVBoxLayout(self.cf_row_widget)
        cf_inner.setContentsMargins(0, 0, 0, 0)
        cf_inner.setSpacing(3)

        self.cf_row_lbl = _lbl("Conversion Factor")
        cf_inner.addWidget(self.cf_row_lbl)

        cf_input_row = QHBoxLayout()
        cf_input_row.setSpacing(6)
        self.cf_prefix_lbl = QLabel("1 unit =")
        self.cf_prefix_lbl.setStyleSheet(f"color: {get_token('text_secondary')}; font-size: 12px;")
        cf_input_row.addWidget(self.cf_prefix_lbl)

        cf_val = v.get("conversion_factor", "")
        self.conv_factor_in = QLineEdit("" if not cf_val else str(cf_val))
        self.conv_factor_in.setPlaceholderText("e.g. 2400")
        self.conv_factor_in.setMinimumHeight(32)
        self.conv_factor_in.setMaximumWidth(120)
        self.conv_factor_in.setValidator(dbl)
        cf_input_row.addWidget(self.conv_factor_in)

        self.cf_suffix_lbl = QLabel("unit")
        self.cf_suffix_lbl.setStyleSheet(f"color: {get_token('text_secondary')}; font-size: 12px;")
        cf_input_row.addWidget(self.cf_suffix_lbl)

        self.cf_status_lbl = QLabel("")
        self.cf_status_lbl.setStyleSheet(f"font-size: 11px; color: {get_token('text_disabled')};")
        cf_input_row.addWidget(self.cf_status_lbl)
        cf_input_row.addStretch()
        cf_inner.addLayout(cf_input_row)

        cl.addWidget(self.cf_row_widget)

        self.formula_lbl = QLabel("")
        self.formula_lbl.setWordWrap(True)
        self.formula_lbl.setStyleSheet(f"font-size: 11px; color: {get_token('text_secondary')};")
        self.formula_lbl.setVisible(False)
        cl.addWidget(self.formula_lbl)

        root.addWidget(self.carbon_container)

        # ── Recyclability ─────────────────────────────────────────────────
        root.addWidget(_divider())

        recycle_hdr = QHBoxLayout()
        recycle_title = QLabel("Recyclability")
        recycle_title.setStyleSheet("font-weight: 600; font-size: 12px;")
        recycle_hdr.addWidget(recycle_title)
        recycle_hdr.addStretch()
        self.recycle_chk = QCheckBox("Include")
        self.recycle_chk.setChecked(s.get("included_in_recyclability", False))
        recycle_hdr.addWidget(self.recycle_chk)
        root.addLayout(recycle_hdr)

        self.recycle_container = QWidget()
        rl = QHBoxLayout(self.recycle_container)
        rl.setContentsMargins(0, 4, 0, 0)
        rl.setSpacing(12)

        scrap_col = QVBoxLayout()
        scrap_col.setSpacing(3)
        scrap_col.addWidget(_lbl("Scrap Rate (per unit)"))
        scrap_val = v.get("scrap_rate", "")
        self.scrap_in = QLineEdit("" if not scrap_val else fmt(scrap_val))
        self.scrap_in.setPlaceholderText("e.g. 50")
        self.scrap_in.setMinimumHeight(32)
        self.scrap_in.setValidator(dbl)
        scrap_col.addWidget(self.scrap_in)
        rl.addLayout(scrap_col, stretch=1)

        recov_col = QVBoxLayout()
        recov_col.setSpacing(3)
        recov_col.addWidget(_lbl("Recovery after Demolition (%)"))
        recov_val = v.get("post_demolition_recovery_percentage", "")
        self.recycling_perc_in = QLineEdit("" if not recov_val else fmt(recov_val))
        self.recycling_perc_in.setPlaceholderText("e.g. 90")
        self.recycling_perc_in.setMinimumHeight(32)
        self.recycling_perc_in.setValidator(dbl)
        recov_col.addWidget(self.recycling_perc_in)
        rl.addLayout(recov_col, stretch=1)

        root.addWidget(self.recycle_container)

        # ── Categorization ────────────────────────────────────────────────
        root.addWidget(_divider())

        cat_row = QHBoxLayout()
        cat_row.setSpacing(12)

        grade_col = QVBoxLayout()
        grade_col.setSpacing(3)
        grade_col.addWidget(_lbl("Grade"))
        self.grade_in = QLineEdit(v.get("grade", ""))
        self.grade_in.setPlaceholderText("e.g. M25, Fe500")
        self.grade_in.setMinimumHeight(32)
        grade_col.addWidget(self.grade_in)
        cat_row.addLayout(grade_col, stretch=1)

        type_col = QVBoxLayout()
        type_col.setSpacing(3)
        type_col.addWidget(_lbl("Type"))
        self.type_in = QComboBox()
        self.type_in.setEditable(True)
        self.type_in.setMinimumHeight(32)
        self.type_in.wheelEvent = lambda event: event.ignore()
        for t in [
            "Concrete",
            "Steel",
            "Masonry",
            "Timber",
            "Finishing",
            "Insulation",
            "Glass",
            "Aluminum",
            "Other",
        ]:
            self.type_in.addItem(t)
        existing_type = v.get("type", "")
        if existing_type:
            tidx = self.type_in.findText(existing_type)
            if tidx >= 0:
                self.type_in.setCurrentIndex(tidx)
            else:
                self.type_in.setCurrentText(existing_type)
        else:
            self.type_in.setCurrentIndex(-1)
            self.type_in.lineEdit().setPlaceholderText("e.g. Concrete, Steel")
        type_col.addWidget(self.type_in)
        cat_row.addLayout(type_col, stretch=1)

        root.addLayout(cat_row)
        root.addStretch()

        # ── Button bar ────────────────────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setObjectName("btn_bar")
        btn_bar.setStyleSheet(
            f"#btn_bar {{ border-top: 1px solid {get_token('surface_mid')}; }}"
        )
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(20, 10, 20, 10)
        btn_layout.setSpacing(8)

        self.custom_db_btn = QPushButton("Save to Custom DB…")
        self.custom_db_btn.setMinimumHeight(34)
        self.custom_db_btn.setMinimumWidth(150)
        self.custom_db_btn.setToolTip(
            "Save this material to a user-created custom database"
        )
        self.custom_db_btn.clicked.connect(self._on_save_to_custom_db)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(34)
        self.cancel_btn.setMinimumWidth(90)
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton(
            "Update Changes" if self.is_edit else "Add to Table"
        )
        self.save_btn.setMinimumHeight(34)
        self.save_btn.setMinimumWidth(120)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.validate_and_accept)

        btn_layout.addWidget(self.custom_db_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        outer.addWidget(btn_bar)

        # ── Disable save/db buttons when project is locked ────────────────
        # Walk up the parent chain to find the ProjectWindow._frozen flag.
        # Works regardless of which module opens this dialog.
        _w, _frozen = parent, False
        while _w is not None:
            if hasattr(_w, "_frozen"):
                _frozen = bool(_w._frozen)
                break
            _w = _w.parent() if callable(getattr(_w, "parent", None)) else None
        if _frozen:
            # Buttons
            self.custom_db_btn.setEnabled(False)
            self.save_btn.setEnabled(False)

            # Text inputs → read-only
            for _w in (
                self.name_in,
                self.qty_in,
                self.rate_in,
                self.src_in,
                self.carbon_em_in,
                self.conv_factor_in,
                self.scrap_in,
                self.recycling_perc_in,
                self.grade_in,
            ):
                _w.setReadOnly(True)

            # Dropdowns and checkboxes → disabled
            for _w in (
                self.unit_in,
                self.carbon_denom_cb,
                self.type_in,
                self._allow_edit_chk,
                self.carbon_chk,
                self.recycle_chk,
            ):
                _w.setEnabled(False)

            # Optional widgets (may be None)
            if self.sor_cb:
                self.sor_cb.setEnabled(False)
            if self.type_filter_cb:
                self.type_filter_cb.setEnabled(False)

        # ── Freeze fields for emissions_only / recyclability_only modes ───
        if emissions_only:
            for w in (
                self.name_in,
                self.qty_in,
                self.rate_in,
                self.src_in,
                self.scrap_in,
                self.recycling_perc_in,
                self.grade_in,
            ):
                w.setReadOnly(True)
            self.unit_in.setEnabled(False)
            self.recycle_chk.setEnabled(False)
            self.type_in.setEnabled(False)
            self.save_btn.setText("Save Emission Data")
        elif recyclability_only:
            for w in (
                self.name_in,
                self.qty_in,
                self.rate_in,
                self.src_in,
                self.carbon_em_in,
                self.conv_factor_in,
                self.grade_in,
            ):
                w.setReadOnly(True)
            self.unit_in.setEnabled(False)
            self.carbon_chk.setEnabled(False)
            self.carbon_denom_cb.setEnabled(False)
            self.type_in.setEnabled(False)
            self.save_btn.setText("Save Recyclability Data")

        # ── Wire signals ──────────────────────────────────────────────────
        self.carbon_chk.toggled.connect(self.carbon_container.setVisible)
        self.recycle_chk.toggled.connect(self.recycle_container.setVisible)
        self.carbon_container.setVisible(self.carbon_chk.isChecked())
        self.recycle_container.setVisible(self.recycle_chk.isChecked())

        self.carbon_denom_cb.currentIndexChanged.connect(
            self._on_denom_combobox_changed
        )
        self.carbon_em_in.textChanged.connect(self._update_formula_preview)
        self.conv_factor_in.textChanged.connect(self._update_formula_preview)
        self.qty_in.textChanged.connect(self._update_formula_preview)

        for _w in (
            self.name_in,
            self.qty_in,
            self.rate_in,
            self.src_in,
            self.carbon_em_in,
            self.conv_factor_in,
            self.scrap_in,
            self.recycling_perc_in,
            self.grade_in,
        ):
            _w.textChanged.connect(self._on_field_manually_changed)
        self.unit_in.currentIndexChanged.connect(self._on_field_manually_changed)
        self.carbon_denom_cb.currentIndexChanged.connect(
            self._on_field_manually_changed
        )
        self.type_in.currentIndexChanged.connect(self._on_field_manually_changed)

        self._update_cf()
        self._ui_ready = True

        # ── Re-apply DB lock when editing a previously SOR-filled material ──
        _src = (data.get("meta", {}).get("source", "") if data else "") or (
            self._db_original  # already decoded above
        ).get("action", "user_added")
        if self.is_edit and _src in (
            "internal_db",
            "custom_db",
            "excel",
            "db",
            "db_modified",
            "custom_db_modified",
        ):
            mat_name = v.get("material_name", "")
            self._sor_item = self._suggestions.get(mat_name)
            self._allow_edit_chk.setEnabled(True)
            # Restore checkbox + lock state directly from what was saved
            saved_allow_edit = s.get("allow_edit_checked", False)
            self._allow_edit_chk.blockSignals(True)
            self._allow_edit_chk.setChecked(saved_allow_edit)
            self._allow_edit_chk.blockSignals(False)
            self._lock_autofilled_fields(not saved_allow_edit)

    # ── SOR / suggestion helpers ──────────────────────────────────────────

    def _reload_suggestions(self):
        if not self._sor_db_key or self._sor_db_key == self._NO_SUGGESTIONS_CODE:
            self._suggestions = {}
            self.name_in.setCompleter(None)
            self._active_completer = None
            return

        db_keys = [self._sor_db_key]

        if self.type_filter_cb is not None:
            type_filter = self.type_filter_cb.currentData()
        else:
            type_filter = self._comp_name

        self._suggestions = _load_material_suggestions(
            db_keys=db_keys, comp_name=type_filter
        )

        if self._suggestions:
            if self._active_completer is None:
                self._active_completer = QCompleter(self)
                self._active_completer.setCompletionMode(
                    QCompleter.UnfilteredPopupCompletion
                )
                self._active_completer.setCaseSensitivity(Qt.CaseInsensitive)
                self._active_completer.setMaxVisibleItems(10)

                popup = self._active_completer.popup()
                popup.setStyleSheet(
                    f"QListView {{"
                    f"  background: {get_token('base')};"
                    f"  border: 1px solid {get_token('surface_mid')};"
                    f"  border-radius: 8px;"
                    f"  padding: 4px 0;"
                    f"  outline: none;"
                    f"}}"
                    f"QListView::item {{"
                    f"  padding: 6px 12px;"
                    f"  color: {get_token('text')};"
                    f"  border: none;"
                    f"  border-radius: 4px;"
                    f"  margin: 1px 6px;"
                    f"  min-height: 22px;"
                    f"}}"
                    f"QListView::item:hover {{"
                    f"  background: {get_token('surface')};"
                    f"}}"
                    f"QListView::item:selected {{"
                    f"  background: {get_token('surface_pressed')};"
                    f"  color: {get_token('text')};"
                    f"}}"
                )

                self._active_completer.activated.connect(self._on_suggestion_selected)
                self.name_in.setCompleter(self._active_completer)
            # Re-filter with current text whenever suggestions are reloaded
            self._on_name_search_changed(self.name_in.text())
        else:
            self.name_in.setCompleter(None)
            self._active_completer = None

    def _on_name_search_changed(self, text: str):
        """
        Filter completer suggestions using order-independent token matching.

        Also handles autofill: when the text is an exact match of a known
        suggestion (i.e. the user just selected one from the popup), call
        _on_suggestion_selected directly instead of relying on the activated
        signal, whose timing relative to textChanged is not guaranteed.
        """
        if not self._suggestions:
            return
        q = text.strip()
        # Exact match → selection just happened; autofill and stop.
        # Guard with _ui_ready so this doesn't fire during __init__ before
        # all widgets (unit_in, carbon_em_in, etc.) have been created.
        if q in self._suggestions and not self._skip_suggestions:
            if self._ui_ready:
                self._on_suggestion_selected(q)
            return
        # Name no longer matches the autofilled suggestion → clear stale DB values.
        if self._ui_ready and self._sor_item is not None and q != self._sor_filled_name:
            self._reset_sor_state()
        if self._active_completer is None:
            return
        _ensure_registry_on_path()
        try:
            from search_engine import AdvancedSearchEngine
        except ImportError:
            return
        if not q or q == "?":
            filtered = sorted(self._suggestions.keys())
        else:
            filtered = sorted(
                name
                for name in self._suggestions
                if AdvancedSearchEngine.is_match(q, name)
            )
        self._active_completer.setModel(QStringListModel(filtered, self))
        if filtered and (q == "?" or q):
            self._active_completer.complete()

    def _reset_sor_state(self):
        """Clear DB-autofilled values when the user edits the name away from a suggestion."""
        self._sor_filling = True
        try:
            self.rate_in.clear()
            self.src_in.clear()
            self.carbon_em_in.clear()
            self.conv_factor_in.clear()
            self.carbon_chk.setEnabled(True)
        finally:
            self._sor_filling = False
        self._sor_item = None
        self._sor_filled_name = None
        self._is_customized = False
        self._db_original = {}
        self._user_edited_snapshot = {}
        self._lock_autofilled_fields(False)
        self._allow_edit_chk.blockSignals(True)
        self._allow_edit_chk.setChecked(False)
        self._allow_edit_chk.blockSignals(False)
        self._allow_edit_chk.setEnabled(False)
        self._update_cf()

    def _populate_type_filter(self, preselect: str = None):
        db_keys = None
        if self._sor_db_key and self._sor_db_key != self._NO_SUGGESTIONS_CODE:
            db_keys = [self._sor_db_key]

        types = _list_sor_types(db_keys=db_keys)

        self.type_filter_cb.blockSignals(True)
        self.type_filter_cb.clear()
        self.type_filter_cb.addItem("All types", None)
        for t in types:
            self.type_filter_cb.addItem(t, t)

        best_idx = 0
        if preselect:
            pre_lower = preselect.strip().lower()
            best_score = -1
            for i in range(1, self.type_filter_cb.count()):
                t = (self.type_filter_cb.itemData(i) or "").lower()
                if t == pre_lower:
                    best_idx = i
                    break  # exact match - nothing better
                elif pre_lower in t:
                    score = 2 + len(t)  # comp fits into type; prefer shorter
                    if score > best_score:
                        best_score = score
                        best_idx = i
                elif t in pre_lower:
                    score = 1 + len(t)  # type fits into comp; prefer longer
                    if score > best_score:
                        best_score = score
                        best_idx = i

        self.type_filter_cb.setCurrentIndex(best_idx)
        self.type_filter_cb.blockSignals(False)

    def _on_sor_changed(self):
        if self.sor_cb and self.sor_cb.currentData() == self._NO_SUGGESTIONS_CODE:
            if self.type_filter_cb is not None:
                self.type_filter_cb.setEnabled(False)
            self._on_skip_suggestion()
            return
        if self.type_filter_cb is not None:
            self.type_filter_cb.setEnabled(True)
            current_type = self.type_filter_cb.currentData()
            self._populate_type_filter(preselect=current_type or self._comp_name)
        self._restore_suggestions()

    def _on_type_filter_changed(self):
        self._restore_suggestions()

    def _restore_suggestions(self):
        """Re-enable the suggestion system (called when the user switches database/type filter)."""
        self._skip_suggestions = False
        self._reload_suggestions()
        if self._skip_btn is not None:
            self._skip_btn.setVisible(True)

    def _on_skip_suggestion(self):
        """User chose to enter all fields manually - bypass the suggestion system."""
        self._skip_suggestions = True
        self._reset_sor_state()
        self.name_in.setCompleter(None)
        self._active_completer = None
        if self._skip_btn is not None:
            self._skip_btn.setVisible(False)

    def _lock_autofilled_fields(self, lock: bool):
        # qty_in is always freely editable; everything else is DB-filled.
        self.unit_in.setEnabled(not lock)
        self.id_in.setReadOnly(lock)
        self.rate_in.setReadOnly(lock)
        self.src_in.setReadOnly(lock)
        self.carbon_em_in.setReadOnly(lock)
        self.carbon_denom_cb.setEnabled(not lock)
        self.carbon_src_in.setReadOnly(lock)
        self.conv_factor_in.setReadOnly(lock)

    def _on_allow_edit_toggled(self, checked: bool):
        """Unlock autofilled fields when checked; restore values and re-lock when unchecked."""
        if checked:
            if self._user_edited_snapshot:
                # Restore previously saved user edits instead of blanking the fields
                self._sor_filling = True
                try:
                    snap = self._user_edited_snapshot
                    self.rate_in.setText(snap.get("rate", ""))
                    if snap.get("unit_idx", -1) >= 0:
                        self.unit_in.setCurrentIndex(snap["unit_idx"])
                    self.src_in.setText(snap.get("src", ""))
                    self.carbon_em_in.setText(snap.get("carbon_em", ""))
                    if snap.get("carbon_denom_idx", -1) >= 0:
                        self.carbon_denom_cb.setCurrentIndex(snap["carbon_denom_idx"])
                    self.carbon_src_in.setText(snap.get("carbon_src", ""))
                    self.conv_factor_in.setText(snap.get("conv_factor", ""))
                    self.carbon_chk.setChecked(snap.get("carbon_chk", False))
                    self.recycle_chk.setChecked(snap.get("recycle_chk", False))
                finally:
                    self._sor_filling = False
            else:
                # First time allowing edit - only clear source attribution fields
                self._sor_filling = True
                self.src_in.clear()
                self.carbon_src_in.clear()
                self._sor_filling = False
            self._is_modified_by_user = True
            self.carbon_chk.setEnabled(True)
        else:
            if self._sor_item is not None:
                # Snapshot all current user-edited values before overwriting with DB values
                self._user_edited_snapshot = {
                    "rate": self.rate_in.text(),
                    "unit_idx": self.unit_in.currentIndex(),
                    "src": self.src_in.text(),
                    "carbon_em": self.carbon_em_in.text(),
                    "carbon_denom_idx": self.carbon_denom_cb.currentIndex(),
                    "carbon_src": self.carbon_src_in.text(),
                    "conv_factor": self.conv_factor_in.text(),
                    "carbon_chk": self.carbon_chk.isChecked(),
                    "recycle_chk": self.recycle_chk.isChecked(),
                }
                # Restore all values from the DB suggestion that was selected
                self._sor_filling = True
                try:
                    item = self._sor_item
                    unit = item.get("unit", "")
                    if unit:
                        idx = _resolve_unit_code(unit, self.unit_in)
                        if idx >= 0:
                            self.unit_in.setCurrentIndex(idx)

                    rate = item.get("rate", "")
                    self.rate_in.setText(
                        fmt(rate) if rate not in ("", "not_available", None) else ""
                    )

                    src = item.get("rate_src", "")
                    self.src_in.setText(
                        str(src) if src not in ("", "not_available", None) else ""
                    )

                    carbon_src = item.get("carbon_emission_src", "")
                    self.carbon_src_in.setText(
                        str(carbon_src)
                        if carbon_src not in ("", "not_available", None)
                        else ""
                    )

                    carbon = item.get("carbon_emission", "not_available")
                    denom = item.get("carbon_emission_units_den", "not_available")
                    carbon_available = carbon not in (
                        "not_available",
                        "",
                        None,
                    ) and denom not in ("not_available", "", None)
                    self._sor_carbon_available = carbon_available
                    if carbon_available:
                        self.carbon_em_in.setText(fmt(carbon))
                        didx = _resolve_unit_code(denom, self.carbon_denom_cb)
                        if didx >= 0:
                            self.carbon_denom_cb.setCurrentIndex(didx)
                    else:
                        self.carbon_em_in.setText("")
                    self.carbon_chk.setChecked(carbon_available)
                    self.carbon_chk.setEnabled(carbon_available)

                    cf = item.get("conversion_factor", "not_available")
                    self.conv_factor_in.setText(
                        fmt(cf) if cf not in ("not_available", "", None, 0, 0.0) else ""
                    )

                    self.recycle_chk.setChecked(False)
                    self.recycle_chk.setEnabled(True)
                finally:
                    self._sor_filling = False
                self._is_customized = False
                self._is_modified_by_user = False
                self._update_cf()
            else:
                # No DB suggestion - restore the sources saved at check time, or the originals
                restore_src = getattr(self, "_pre_allow_edit_source", None)
                if restore_src is None:
                    restore_src = self._original_source
                restore_carbon_src = getattr(self, "_pre_allow_edit_carbon_src", None)
                if restore_carbon_src is None:
                    restore_carbon_src = self._original_carbon_src
                self._sor_filling = True
                if restore_src:
                    self.src_in.setText(restore_src)
                if restore_carbon_src:
                    self.carbon_src_in.setText(restore_carbon_src)
                self._sor_filling = False

        self._lock_autofilled_fields(not checked)

    def _on_save_to_custom_db(self):
        if not self.name_in.text().strip():
            QMessageBox.warning(
                self,
                "Missing Name",
                "A material name is required before saving.",
            )
            return

        try:
            if CustomMaterialDB is None:
                raise ImportError("custom_material_db not available")
            cdb = CustomMaterialDB()
            existing = cdb.list_db_names()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open custom database:\n{e}")
            return

        dlg = _SaveToCustomDBDialog(existing, parent=self)
        if not dlg.exec():
            return

        db_name = dlg.selected_name()
        try:
            cdb.save_material(db_name, self.get_values())
            QMessageBox.information(
                self,
                "Saved",
                f"Material saved to '{db_name}'.\n"
                f"It will appear in suggestions next time you open this dialog.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def _on_field_manually_changed(self):
        if not self._sor_filling and self._sor_item is not None:
            self._is_customized = True

    # ── Suggestion auto-fill ──────────────────────────────────────────────

    def _on_suggestion_selected(self, name: str):
        item = self._suggestions.get(name)
        if not item:
            return

        # New suggestion - discard any snapshot from a previous suggestion's edit session
        self.id_in.setText(str(item.get("id", "")))
        self._user_edited_snapshot = {}
        self._sor_filling = True
        try:
            unit = item.get("unit", "")
            unit_filled = bool(unit)
            if unit_filled:
                idx = _resolve_unit_code(unit, self.unit_in)
                if idx >= 0:
                    self.unit_in.setCurrentIndex(idx)

            rate = item.get("rate", "")
            rate_filled = rate not in ("", "not_available", None)
            if rate_filled:
                self.rate_in.setText(fmt(rate))

            src = item.get("rate_src", "")
            src_filled = src not in ("", "not_available", None)
            if src_filled:
                self.src_in.setText(str(src))

            carbon = item.get("carbon_emission", "not_available")
            denom = item.get("carbon_emission_units_den", "not_available")
            carbon_available = carbon not in (
                "not_available",
                "",
                None,
            ) and denom not in ("not_available", "", None)
            self._sor_carbon_available = carbon_available

            if carbon_available:
                self.carbon_em_in.setText(fmt(carbon))
                didx = _resolve_unit_code(denom, self.carbon_denom_cb)
                if didx >= 0:
                    self.carbon_denom_cb.setCurrentIndex(didx)
            else:
                self.carbon_em_in.setText("")
            self.carbon_chk.setChecked(carbon_available)
            self.carbon_chk.setEnabled(carbon_available)

            carbon_src = item.get("carbon_emission_src", "")
            self.carbon_src_in.setText(
                str(carbon_src) if carbon_src not in ("", "not_available", None) else ""
            )

            cf = item.get("conversion_factor", "not_available")
            if cf not in ("not_available", "", None, 0, 0.0):
                self.conv_factor_in.setText(fmt(cf))
            else:
                self.conv_factor_in.setText("")

            self.recycle_chk.setChecked(False)
            self.recycle_chk.setEnabled(True)

            self._sor_item = item
            self._sor_filled_name = name
            self._is_customized = False

            # Snapshot original DB values (written once; never overwritten on re-open).
            # Store the full item so every field is available for modification detection.
            if not self._db_original:
                _db_key = item.get("db_key", "") or self._sor_db_key
                _action = (
                    "custom_db" if _db_key.startswith("custom::") else "internal_db"
                )
                self._db_original = {
                    **item,
                    "action": _action,
                    "db_key": _db_key,
                }

        finally:
            self._sor_filling = False

        self._update_cf()

        self._allow_edit_chk.blockSignals(True)
        self._allow_edit_chk.setChecked(False)
        self._allow_edit_chk.blockSignals(False)
        self._allow_edit_chk.setEnabled(True)
        self._lock_autofilled_fields(True)
        self._is_modified_by_user = False

    # ── Unit model helpers ────────────────────────────────────────────────

    def _build_full_unit_model(self) -> QStandardItemModel:
        model = QStandardItemModel()

        for dim, units in _CONSTRUCTION_UNITS.units.items():
            sep = QStandardItem(f"── {dim} ──")
            sep.setFlags(Qt.ItemFlag(0))
            model.appendRow(sep)
            for code, info in units.items():
                si_val = UNIT_TO_SI.get(code)
                si_unit_code = SI_BASE_UNITS.get(dim, "")
                sym = (
                    _unit_sym(code)
                    if code in UNIT_DISPLAY
                    else info["name"].split(",")[0].strip()
                )
                si_sym = _unit_sym(si_unit_code)
                short_name = info["name"].split(",")[-1].strip()
                item = QStandardItem(f"{sym} - {short_name}")
                item.setData(code, Qt.UserRole)
                tooltip = (
                    f"1 {sym} = {si_val:g} {si_sym}  |  Example: {info['example']}"
                    if si_val is not None and si_val != 1.0
                    else f"SI base unit  |  Example: {info['example']}"
                )
                item.setData(tooltip, Qt.ToolTipRole)
                model.appendRow(item)

        _global_custom = get_custom_units()
        if _global_custom:
            sep_c = QStandardItem("── Custom ──")
            sep_c.setFlags(Qt.ItemFlag(0))
            model.appendRow(sep_c)
            for cu in _global_custom:
                display = (
                    f"{cu['symbol']} - {cu['name']}" if cu.get("name") else cu["symbol"]
                )
                item = QStandardItem(display)
                item.setData(cu["symbol"], Qt.UserRole)
                item.setData(
                    f"Custom: 1 {cu['symbol']} = {cu['to_si']:g} {cu.get('si_unit', '')}  |  {cu.get('dimension', '')}",
                    Qt.ToolTipRole,
                )
                model.appendRow(item)

        sep2 = QStandardItem("──────────────")
        sep2.setFlags(Qt.ItemFlag(0))
        model.appendRow(sep2)
        add_item = QStandardItem("+ Add Custom Unit...")
        add_item.setData(self._CUSTOM_CODE, Qt.UserRole)
        model.appendRow(add_item)

        return model

    def _build_unit_dropdown(self, current_unit: str, _=None) -> QComboBox:
        cb = QComboBox()
        cb.setMinimumHeight(30)
        cb.setModel(self._build_full_unit_model())
        idx = cb.findData(current_unit)
        if idx >= 0:
            cb.setCurrentIndex(idx)
        return cb

    def _get_unit_info(self, code: str):
        return _get_unit_info_impl(code)

    _DB_NA = frozenset({"not_available", "", None})

    def _compute_modified_fields(self) -> list:
        """
        Compare current dialog values against the immutable DB snapshot.
        Returns a list of field names whose values differ from the DB original.
        Empty list means either no DB source or no changes made.
        """
        orig = self._db_original
        if not orig:
            return []

        modified = []

        # Unit
        orig_unit = orig.get("unit", "")
        if orig_unit and self.unit_in.currentData() != orig_unit:
            modified.append("unit")

        # Rate
        orig_rate = orig.get("rate", "")
        if orig_rate not in self._DB_NA:
            try:
                if abs(float(self.rate_in.text() or 0) - float(orig_rate)) > 1e-9:
                    modified.append("rate")
            except (ValueError, TypeError):
                pass

        # Carbon emission factor
        orig_em = orig.get("carbon_emission", "")
        if orig_em not in self._DB_NA:
            try:
                if abs(float(self.carbon_em_in.text() or 0) - float(orig_em)) > 1e-9:
                    modified.append("carbon_emission")
            except (ValueError, TypeError):
                pass

        # Carbon denominator unit
        orig_denom = orig.get("carbon_emission_units_den", "")
        if orig_denom not in self._DB_NA:
            if self.carbon_denom_cb.currentData() != orig_denom:
                modified.append("carbon_emission_units_den")

        # Conversion factor
        orig_cf = orig.get("conversion_factor", "")
        if orig_cf not in self._DB_NA and orig_cf not in (0, 0.0):
            try:
                if abs(float(self.conv_factor_in.text() or 0) - float(orig_cf)) > 1e-9:
                    modified.append("conversion_factor")
            except (ValueError, TypeError):
                pass

        return modified

    def _rebuild_unit_models(self, mat_sel: str = None, denom_sel: str = None):
        self.unit_in.blockSignals(True)
        self.carbon_denom_cb.blockSignals(True)

        self.unit_in.setModel(self._build_full_unit_model())
        self.carbon_denom_cb.setModel(self._build_full_unit_model())

        if mat_sel:
            idx = self.unit_in.findData(mat_sel)
            if idx >= 0:
                self.unit_in.setCurrentIndex(idx)
        if denom_sel:
            idx = self.carbon_denom_cb.findData(denom_sel)
            if idx >= 0:
                self.carbon_denom_cb.setCurrentIndex(idx)

        self.unit_in.blockSignals(False)
        self.carbon_denom_cb.blockSignals(False)

    def _add_custom_unit(self, triggering_cb: QComboBox):
        prev_mat = self.unit_in.currentData()
        prev_denom = self.carbon_denom_cb.currentData()

        existing_syms = list(UNIT_TO_SI.keys()) + [
            c["symbol"] for c in get_custom_units()
        ]
        dialog = CustomUnitDialog(self, existing_symbols=existing_syms)
        if dialog.exec():
            cu = dialog.get_unit()
            # Persist to DB and refresh the global cache so all open dialogs see it
            try:
                if CustomMaterialDB is not None:
                    CustomMaterialDB().save_custom_unit(cu)
                load_custom_units()
            except Exception as exc:
                print(f"[MaterialDialog] Could not save custom unit: {exc}")
            new_sym = cu["symbol"]
            mat_sel = (
                new_sym
                if triggering_cb is self.unit_in
                else (prev_mat if prev_mat != self._CUSTOM_CODE else new_sym)
            )
            denom_sel = (
                new_sym
                if triggering_cb is self.carbon_denom_cb
                else (prev_denom if prev_denom != self._CUSTOM_CODE else new_sym)
            )
            self._rebuild_unit_models(mat_sel=mat_sel, denom_sel=denom_sel)
        else:
            prev = prev_mat if triggering_cb is self.unit_in else prev_denom
            restore = prev if (prev and prev != self._CUSTOM_CODE) else None
            triggering_cb.blockSignals(True)
            if restore:
                idx = triggering_cb.findData(restore)
                if idx >= 0:
                    triggering_cb.setCurrentIndex(idx)
            triggering_cb.blockSignals(False)

        self._update_cf()

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_unit_combobox_changed(self):
        code = self.unit_in.currentData()
        if code == self._CUSTOM_CODE:
            self._add_custom_unit(self.unit_in)
            return
        if code:
            self.carbon_denom_cb.blockSignals(True)
            didx = self.carbon_denom_cb.findData(code)
            if didx >= 0:
                self.carbon_denom_cb.setCurrentIndex(didx)
            self.carbon_denom_cb.blockSignals(False)
        self._update_cf()

    def _on_denom_combobox_changed(self):
        code = self.carbon_denom_cb.currentData()
        if code == self._CUSTOM_CODE:
            self._add_custom_unit(self.carbon_denom_cb)
            return
        self._update_cf()

    # ── Auto conversion factor ────────────────────────────────────────────

    def _update_cf(self):
        mat_code = self.unit_in.currentData() or ""
        denom_code = self.carbon_denom_cb.currentData() or ""
        mat_sym = _unit_sym(mat_code)
        denom_sym = _unit_sym(denom_code)

        mat_si, mat_dim = self._get_unit_info(mat_code)
        denom_si, denom_dim = self._get_unit_info(denom_code)

        if mat_code == denom_code:
            self._auto_cf = "1"
            self.conv_factor_in.setText("1")
            self.cf_row_widget.setVisible(False)
        elif mat_si is not None and denom_si is not None and mat_dim == denom_dim:
            suggested = f"{mat_si / denom_si:g}"
            self._auto_cf = suggested
            self.conv_factor_in.setText(suggested)
            self.cf_row_widget.setVisible(True)
            self.cf_prefix_lbl.setText(f"1 {mat_sym} =")
            self.cf_suffix_lbl.setText(denom_sym)
            self.cf_status_lbl.setText("(suggested - you can change this)")
        else:
            # Clear the field only if it still holds a previously auto-written value
            if self.conv_factor_in.text() == getattr(self, "_auto_cf", None):
                self.conv_factor_in.clear()
            self._auto_cf = None
            self.cf_row_widget.setVisible(True)
            self.cf_prefix_lbl.setText(f"1 {mat_sym} =")
            self.cf_suffix_lbl.setText(denom_sym)
            if mat_dim and denom_dim:
                self.cf_status_lbl.setText(f"e.g. density for {mat_dim} → {denom_dim}")
            else:
                self.cf_status_lbl.setText("")

        self._update_formula_preview()

    # ── Formula preview ───────────────────────────────────────────────────

    def _update_formula_preview(self):
        try:
            qty = float(self.qty_in.text() or 0)
            ef = float(self.carbon_em_in.text() or 0)
            cf = float(self.conv_factor_in.text() or 0)

            mat_code = self.unit_in.currentData() or ""
            mat_sym = _unit_sym(mat_code)
            denom_code = self.carbon_denom_cb.currentData() or ""
            denom_sym = _unit_sym(denom_code)

            if qty > 0 and ef > 0 and cf > 0:
                total = qty * cf * ef
                if cf == 1.0:
                    self.formula_lbl.setText(
                        f"{qty:g} {mat_sym}  ×  {ef:g} kgCO₂e/{denom_sym}"
                        f"  =  {fmt_comma(total)} kgCO₂e"
                    )
                else:
                    self.formula_lbl.setText(
                        f"{qty:g} {mat_sym}  ×  {cf:g}  ×  {ef:g} kgCO₂e/{denom_sym}"
                        f"  =  {fmt_comma(total)} kgCO₂e"
                    )
                self.formula_lbl.setVisible(True)
            else:
                self.formula_lbl.setVisible(False)
        except (ValueError, ZeroDivisionError):
            self.formula_lbl.setVisible(False)

    # ── Validation ────────────────────────────────────────────────────────

    def validate_and_accept(self):
        if not self.name_in.text().strip():
            QMessageBox.critical(self, "Validation Error", "Material Name is required.")
            return

        try:
            qty = float(self.qty_in.text() or 0)
        except ValueError:
            qty = 0
        if qty <= 0:
            QMessageBox.critical(
                self, "Validation Error", "Quantity must be greater than zero."
            )
            return

        if self.carbon_chk.isChecked():
            try:
                ef = float(self.carbon_em_in.text() or 0)
                cf = float(self.conv_factor_in.text() or 0)
            except ValueError:
                ef, cf = 0, 0

            if ef <= 0:
                reply = QMessageBox.warning(
                    self,
                    "Emission Factor",
                    "Emission factor is 0 - carbon cost will be skipped.\n\nContinue?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    return
                self.carbon_chk.setChecked(False)
            elif cf <= 0:
                reply = QMessageBox.warning(
                    self,
                    "Conversion Factor",
                    "Conversion factor is 0 - carbon cost will be skipped.\n\nContinue?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    return
                self.carbon_chk.setChecked(False)
            else:
                mat_code = self.unit_in.currentData() or ""
                denom_code = self.carbon_denom_cb.currentData() or ""
                _, mat_dim = self._get_unit_info(mat_code)
                _, denom_dim = self._get_unit_info(denom_code)
                if mat_dim != denom_dim and abs(cf - 1.0) < 1e-6:
                    res = QMessageBox.warning(
                        self,
                        "Check Conversion Factor",
                        f"Unit mismatch: material is {mat_dim}, carbon unit is {denom_dim}.\nConversion factor is 1.0 - is this correct?\n\nContinue?",
                        QMessageBox.Yes | QMessageBox.No,
                    )
                    if res == QMessageBox.No:
                        return

        if self.recycle_chk.isChecked():
            try:
                scrap = float(self.scrap_in.text() or 0)
                recycle = float(self.recycling_perc_in.text() or 0)
            except ValueError:
                scrap, recycle = 0, 0
            if scrap <= 0 and recycle <= 0:
                reply = QMessageBox.warning(
                    self,
                    "Recyclability",
                    "Both scrap rate and recovery percentage are zero - recyclability will be excluded.\n\nContinue?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    return
                self.recycle_chk.setChecked(False)

        self.accept()

    # ── Output ────────────────────────────────────────────────────────────

    def _compute_action(self) -> str:
        """Determines the source 'action' for metadata: user_added, internal_db, custom_db, or excel."""
        if self._db_original.get("action") == "excel":
            return "excel"
        if self._sor_item:
            return (
                "custom_db"
                if (self._db_original.get("db_key") or "").startswith("custom::")
                else "internal_db"
            )
        return "user_added"

    def get_values(self) -> dict:
        """Returns a clean dictionary of material data for the OsBridgeLCCA database.

        Private keys (prefixed with _) are consumed by add_material() /
        open_edit_dialog() in manager.py and are never stored inside item["values"].

        Key contract (must stay in sync with manager.py):
          _included_in_carbon_emission  → item["state"]
          _included_in_recyclability    → item["state"]
          _allow_edit_checked           → item["state"]
          _from_sor                     → drives source / source_db_key in item["meta"]
          _sor_db_key                   → same
          _is_excel_import              → same
          _is_customized                → metadata flag (popped, not stored)
          _db_original                  → encoded snapshot → item["meta"]["db_original"]
        """
        actual_unit = self.unit_in.currentData() or ""
        unit_to_si, _ = self._get_unit_info(actual_unit)

        carbon_on = self.carbon_chk.isChecked()
        recycle_on = self.recycle_chk.isChecked()

        action = self._compute_action()
        is_from_sor = action in ("internal_db", "custom_db")
        is_excel = action == "excel"

        return {
            # ── field values (stored in item["values"]) ───────────────────
            "id": self.id_in.text().strip(),
            "material_name": self.name_in.text().strip(),
            "quantity": float(self.qty_in.text() or 0),
            "unit": actual_unit,
            "unit_to_si": unit_to_si or 1.0,
            "rate": float(self.rate_in.text() or 0),
            "rate_source": self.src_in.text().strip(),
            # Zero-out carbon / recycle fields when the checkbox is off so
            # downstream code sees a clean 0 rather than a stale DB value.
            "carbon_emission": float(self.carbon_em_in.text() or 0) if carbon_on else 0.0,
            "carbon_unit": f"kgCO₂e/{self.carbon_denom_cb.currentData() or ''}",
            "conversion_factor": float(self.conv_factor_in.text() or 0),
            "scrap_rate": float(self.scrap_in.text() or 0) if recycle_on else 0.0,
            "post_demolition_recovery_percentage": float(
                self.recycling_perc_in.text() or 0
            ) if recycle_on else 0.0,
            "grade": self.grade_in.text().strip(),
            "type": self.type_in.currentText().strip(),
            # ── private keys consumed by manager (never reach item["values"]) ─
            "_included_in_carbon_emission": carbon_on,
            "_included_in_recyclability": recycle_on,
            "_allow_edit_checked": self._allow_edit_chk.isChecked(),
            "_from_sor": is_from_sor,
            "_sor_db_key": self._db_original.get("db_key", "") if is_from_sor else "",
            "_is_excel_import": is_excel,
            "_is_customized": self._is_customized,
            # snapshot stored as plain dict in item["meta"]["db_original"]
            "_db_original": self._db_original,
        }

    # ── Window close / Escape ─────────────────────────────────────────────

    def closeEvent(self, event):
        """X button on the title bar - always treated as Cancel."""
        self.reject()
        event.accept()

    def keyPressEvent(self, event):
        """Escape → Cancel. Enter/Return → trigger the default button only if
        focus is not on a text field (prevents accidental submission)."""
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focused = self.focusWidget()
            if isinstance(focused, QLineEdit):
                event.ignore()  # let the line-edit handle it, don't submit
            else:
                self.save_btn.click()
        else:
            super().keyPressEvent(event)


