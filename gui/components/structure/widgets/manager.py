from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QGroupBox,
    QDialog,
    QLineEdit,
    QInputDialog,
    QFrame,
    QLabel,
    QMessageBox,
    QCheckBox,
    QComboBox,
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDoubleValidator, QDesktopServices
import time
import uuid
import datetime
from .base_table import StructureTableWidget
from ...utils.definitions import (
    FIELD_DEFINITIONS,
    BASE_DOCS_URL,
    UNIT_TO_KG,
    UNIT_DROPDOWN_DATA,
    _CONSTRUCTION_UNITS,
)

# ---------------------------------------------------------------------------
# Info Popup
# Shown when user clicks ⓘ — short explanation + Read More link to docs
# ---------------------------------------------------------------------------


class InfoPopup(QDialog):
    def __init__(self, field_key: str, parent=None):
        super().__init__(parent)
        defn = FIELD_DEFINITIONS.get(field_key, {})

        self.setWindowTitle(defn.get("label", field_key))
        self.setMinimumWidth(360)
        self.setMaximumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumHeight(420)
        self.resize(500, 700)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Title
        title_lbl = QLabel(f"<b>{defn.get('label', field_key)}</b>")
        title_lbl.setStyleSheet("font-size: 13px;")
        layout.addWidget(title_lbl)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Explanation
        expl_lbl = QLabel(defn.get("explanation", "No description available."))
        expl_lbl.setWordWrap(True)
        expl_lbl.setStyleSheet("font-size: 12px;")
        layout.addWidget(expl_lbl)

        # Buttons row
        btn_row = QHBoxLayout()

        doc_slug = defn.get("doc_slug", "")
        if doc_slug:
            read_more = QPushButton("Read More →")
            read_more.setStyleSheet("font-weight: 600; border: none;")
            read_more.setCursor(Qt.PointingHandCursor)
            read_more.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(f"{BASE_DOCS_URL}{doc_slug}"))
            )
            btn_row.addWidget(read_more)

        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)


# ---------------------------------------------------------------------------
# _field_block
# Builds one input block styled like the financial tab:
#   Bold Title *
#   Explanation text...   ⓘ
#   [Input Widget        ]
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

    # Title
    title_lbl = QLabel(f"{label} *" if required else label)
    title_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
    layout.addWidget(title_lbl)

    # Explanation + ⓘ on same row
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

    # Input widget
    input_widget.setMinimumHeight(30)
    layout.addWidget(input_widget)

    return block


def _section_header(title: str) -> QLabel:
    lbl = QLabel(f"<b>{title}</b>")
    lbl.setStyleSheet("font-size: 13px; margin-top: 4px;")
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


# ---------------------------------------------------------------------------
# MaterialDialog
# ---------------------------------------------------------------------------


class MaterialDialog(QDialog):
    def __init__(self, comp_name: str, parent=None, data: dict = None):
        super().__init__(parent)
        self.is_edit = data is not None
        self.setWindowTitle(
            f"Edit Material — {comp_name}"
            if self.is_edit
            else f"Add Material — {comp_name}"
        )
        self.setMinimumWidth(500)

        v = data.get("values", {}) if self.is_edit else {}
        s = data.get("state", {}) if self.is_edit else {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 8)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(16, 12, 16, 4)
        root.setSpacing(4)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        dbl = QDoubleValidator()
        dbl.setNotation(QDoubleValidator.StandardNotation)

        # ── Section 1: Basic Information ─────────────────────────────────
        root.addWidget(_section_header("Basic Information"))

        self.name_in = QLineEdit(v.get("material_name", ""))
        self.qty_in = QLineEdit(str(v.get("quantity", "0.0")))
        self.qty_in.setValidator(dbl)

        # Unit dropdown
        self.unit_in = QComboBox()
        self.unit_in.setMinimumHeight(30)
        self.unit_in.wheelEvent = lambda event: event.ignore()
        for category, units in _CONSTRUCTION_UNITS.units.items():
            for code, info in units.items():
                display = f"{code} — {info['name']}"  # e.g. "m3 — m³ , Cubic Meter"
                self.unit_in.addItem(display, userData=code)
                idx = self.unit_in.count() - 1
                self.unit_in.setItemData(
                    idx, f"Example: {info['example']}", Qt.ToolTipRole
                )

        current_unit = v.get("unit", "m3")
        idx = self.unit_in.findData(current_unit)
        if idx >= 0:
            self.unit_in.setCurrentIndex(idx)

        self.rate_in = QLineEdit(str(v.get("rate", "0.0")))
        self.src_in = QLineEdit(v.get("rate_source", "Standard"))
        self.rate_in.setValidator(dbl)

        for key, widget in [
            ("material_name", self.name_in),
            ("quantity", self.qty_in),
            ("unit", self.unit_in),
            ("rate", self.rate_in),
            ("rate_source", self.src_in),
        ]:
            root.addWidget(_field_block(key, widget, self))

        # ── Section 2: Carbon Emission ───────────────────────────────────
        root.addWidget(_divider())

        carbon_hdr = QHBoxLayout()
        carbon_hdr.addWidget(_section_header("Carbon Emission"))
        carbon_hdr.addStretch()
        self.carbon_chk = QCheckBox("Include in Carbon Calculation")
        self.carbon_chk.setChecked(s.get("included_in_carbon_emission", True))
        carbon_hdr.addWidget(self.carbon_chk)
        root.addLayout(carbon_hdr)

        self.carbon_container = QWidget()
        cl = QVBoxLayout(self.carbon_container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)

        self.carbon_em_in = QLineEdit(str(v.get("carbon_emission", "0.0")))
        self.carbon_em_in.setValidator(dbl)

        # Carbon unit widget — "kgCO2e /" + dropdown
        carbon_unit_widget = QWidget()
        cu_layout = QHBoxLayout(carbon_unit_widget)
        cu_layout.setContentsMargins(0, 0, 0, 0)
        cu_layout.setSpacing(4)

        prefix_lbl = QLabel("kgCO2e /")
        prefix_lbl.setStyleSheet("font-weight: bold;")
        cu_layout.addWidget(prefix_lbl)

        # Set this BEFORE the carbon_denom_cb population loop:
        existing_carbon_unit = v.get("carbon_unit", "kgCO2e/kg")
        denom = (
            existing_carbon_unit.split("/")[-1].strip()
            if "/" in existing_carbon_unit
            else "kg"
        )

        self.carbon_denom_cb = QComboBox()
        self.carbon_denom_cb.setMinimumHeight(30)
        self.carbon_denom_cb.wheelEvent = lambda event: event.ignore()
        for category, units in _CONSTRUCTION_UNITS.units.items():
            for code, info in units.items():
                print(info)
                display = f"{info['name'].split(',')[-1].strip()}"
                print(display)
                self.carbon_denom_cb.addItem(display, userData=code)
                idx = self.carbon_denom_cb.count() - 1
                self.carbon_denom_cb.setItemData(
                    idx, f"Example: {info['example']}", Qt.ToolTipRole
                )

        didx = self.carbon_denom_cb.findData(denom)
        if didx >= 0:
            self.carbon_denom_cb.setCurrentIndex(didx)

        cu_layout.addWidget(self.carbon_denom_cb, stretch=1)

        self.conv_factor_in = QLineEdit(str(v.get("conversion_factor", "1.0")))
        self.conv_factor_in.setValidator(dbl)

        for key, widget in [
            ("carbon_emission", self.carbon_em_in),
            ("carbon_unit", carbon_unit_widget),
            ("conversion_factor", self.conv_factor_in),
        ]:
            cl.addWidget(_field_block(key, widget, self))

        root.addWidget(self.carbon_container)

        # ── Section 3: Recyclability ─────────────────────────────────────
        root.addWidget(_divider())

        recycle_hdr = QHBoxLayout()
        recycle_hdr.addWidget(_section_header("Recyclability"))
        recycle_hdr.addStretch()
        self.recycle_chk = QCheckBox("Include in Recyclability")
        self.recycle_chk.setChecked(s.get("included_in_recyclability", True))
        recycle_hdr.addWidget(self.recycle_chk)
        root.addLayout(recycle_hdr)

        self.recycle_container = QWidget()
        rl = QVBoxLayout(self.recycle_container)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        self.scrap_in = QLineEdit(str(v.get("scrap_rate", "0.0")))
        self.recycling_perc_in = QLineEdit(
            str(v.get("recyclability_percentage", "0.0"))
        )
        self.scrap_in.setValidator(dbl)
        self.recycling_perc_in.setValidator(dbl)

        for key, widget in [
            ("scrap_rate", self.scrap_in),
            ("recyclability_percentage", self.recycling_perc_in),
        ]:
            rl.addWidget(_field_block(key, widget, self))

        root.addWidget(self.recycle_container)

        # ── Section 4: Categorization ────────────────────────────────────
        root.addWidget(_divider())
        root.addWidget(_section_header("Categorization"))

        self.grade_in = QLineEdit(v.get("grade", ""))
        self.type_in = QLineEdit(v.get("type", ""))

        for key, widget in [
            ("grade", self.grade_in),
            ("type", self.type_in),
        ]:
            root.addWidget(_field_block(key, widget, self))

        root.addStretch()

        # ── Button bar ───────────────────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setStyleSheet("border-top: 1px solid #ddd;")
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(16, 8, 16, 4)

        self.save_btn = QPushButton(
            "Update Changes" if self.is_edit else "Add to Table"
        )
        self.save_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.save_btn.setMinimumHeight(32)
        self.save_btn.clicked.connect(self.validate_and_accept)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        outer.addWidget(btn_bar)

        # ── Progressive visibility ───────────────────────────────────────
        self.carbon_chk.toggled.connect(self.carbon_container.setVisible)
        self.recycle_chk.toggled.connect(self.recycle_container.setVisible)
        self.carbon_container.setVisible(self.carbon_chk.isChecked())
        self.recycle_container.setVisible(self.recycle_chk.isChecked())

        # ── Auto CF logic ────────────────────────────────────────────────
        self.unit_in.currentIndexChanged.connect(self._on_unit_changed)
        self.carbon_denom_cb.currentIndexChanged.connect(self._on_unit_changed)

    # ── Auto CF ─────────────────────────────────────────────────────────

    def _on_unit_changed(self):
        mat_unit = self.unit_in.currentData() or self.unit_in.currentText()
        denom = self.carbon_denom_cb.currentData() or self.carbon_denom_cb.currentText()
        mat_unit = mat_unit.strip().lower()
        denom = denom.strip().lower()

        if mat_unit == denom:
            # Same unit — CF must be 1
            self.conv_factor_in.setText("1.0")
            self.conv_factor_in.setEnabled(False)
        else:
            # Check if both are mass units with known conversion
            mat_kg = UNIT_TO_KG.get(mat_unit)
            den_kg = UNIT_TO_KG.get(denom)

            if mat_kg is not None and den_kg is not None:
                # Auto calculate — e.g. tonne material, kg denom → CF = 1000
                cf = mat_kg / den_kg
                self.conv_factor_in.setText(f"{cf:.4g}")
                self.conv_factor_in.setEnabled(False)
            else:
                # Cannot auto-resolve — let user enter
                self.conv_factor_in.setEnabled(True)
                # Only prompt if CF is still 1.0 and units differ (likely needs correction)
                if abs(float(self.conv_factor_in.text() or 1) - 1.0) < 1e-6:
                    self.conv_factor_in.setStyleSheet("border: 1px solid orange;")
                else:
                    self.conv_factor_in.setStyleSheet("")

    # ── Validation ───────────────────────────────────────────────────────

    def validate_and_accept(self):
        if not self.name_in.text().strip():
            QMessageBox.critical(self, "Validation Error", "Material Name is required.")
            return
        try:
            qty = float(self.qty_in.text() or 0)
            rate = float(self.rate_in.text() or 0)

            if qty <= 0:
                QMessageBox.critical(
                    self, "Validation Error", "Quantity cannot be zero."
                )
                return
            if rate <= 0:
                QMessageBox.critical(self, "Validation Error", "Rate cannot be zero.")
                return

            # Carbon section
            if self.carbon_chk.isChecked():
                ef = float(self.carbon_em_in.text() or 0)
                cf = float(self.conv_factor_in.text() or 0)
                if ef <= 0 or cf <= 0:
                    self.carbon_chk.setChecked(False)
                elif ef > 0:
                    mat_unit = self.unit_in.currentData() or ""
                    denom = self.carbon_denom_cb.currentData() or ""
                    if mat_unit.lower() != denom.lower() and abs(cf - 1.0) < 1e-6:
                        res = QMessageBox.warning(
                            self,
                            "Check Conversion Factor",
                            f"Material unit '{mat_unit}' and carbon unit '{denom}' are different.\n"
                            f"Conversion factor is 1.0 — this is likely incorrect.\n\n"
                            f"Continue anyway?",
                            QMessageBox.Yes | QMessageBox.No,
                        )
                        if res == QMessageBox.No:
                            return

            # Recyclability section
            if self.recycle_chk.isChecked():
                scrap = float(self.scrap_in.text() or 0)
                recycle = float(self.recycling_perc_in.text() or 0)
                if scrap <= 0 and recycle <= 0:
                    self.recycle_chk.setChecked(False)

            self.accept()
        except ValueError:
            QMessageBox.critical(
                self, "Validation Error", "Please ensure all numeric fields are valid."
            )

    # ── Output ───────────────────────────────────────────────────────────

    def get_values(self) -> dict:
        recycle_pct = (
            float(self.recycling_perc_in.text() or 0)
            if self.recycle_chk.isChecked()
            else 0.0
        )
        denom = self.carbon_denom_cb.currentText().strip()
        return {
            "material_name": self.name_in.text().strip(),
            "quantity": float(self.qty_in.text() or 0),
            "unit": self.unit_in.currentData() or self.unit_in.currentText(),
            "rate": float(self.rate_in.text() or 0),
            "rate_source": self.src_in.text().strip(),
            "carbon_emission": (
                float(self.carbon_em_in.text() or 0)
                if self.carbon_chk.isChecked()
                else 0.0
            ),
            "carbon_unit": f"kgCO2e/{self.carbon_denom_cb.currentData() or self.carbon_denom_cb.currentText()}",
            "conversion_factor": (
                float(self.conv_factor_in.text() or 1)
                if self.carbon_chk.isChecked()
                else 1.0
            ),
            "scrap_rate": (
                float(self.scrap_in.text() or 0)
                if self.recycle_chk.isChecked()
                else 0.0
            ),
            "recyclability_percentage": recycle_pct,
            "is_recyclable": recycle_pct > 0,
            "grade": self.grade_in.text().strip(),
            "type": self.type_in.text().strip(),
            "_included_in_carbon_emission": self.carbon_chk.isChecked(),
            "_included_in_recyclability": self.recycle_chk.isChecked(),
        }


# ---------------------------------------------------------------------------
# StructureManagerWidget  (unchanged logic)
# ---------------------------------------------------------------------------


class StructureManagerWidget(QWidget):
    def __init__(self, controller, chunk_name, default_components):
        super().__init__()
        self.controller = controller
        self.chunk_name = chunk_name
        self.default_components = default_components
        self.sections = {}
        self.data = {}

        self.main_layout = QVBoxLayout(self)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; }")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.scroll.setWidget(self.container)
        self.main_layout.addWidget(self.scroll)

        btn_layout = QHBoxLayout()
        self.add_comp_btn = QPushButton("+ Add Component Section")
        self.add_comp_btn.clicked.connect(self.add_new_component)
        btn_layout.addWidget(self.add_comp_btn)
        btn_layout.addStretch()
        self.main_layout.addLayout(btn_layout)

    def on_refresh(self):
        try:
            if not self.controller or not getattr(self.controller, "engine", None):
                return

            data = self.controller.engine.fetch_chunk(self.chunk_name) or {}

            if not data and self.default_components:
                for comp in self.default_components:
                    data[comp] = []
                self.controller.engine.stage_update(
                    chunk_name=self.chunk_name, data=data
                )

            self.data = data
            self.refresh_ui()
        except Exception as e:
            import traceback

            print(f"[ERROR] on_refresh crashed: {e}")
            traceback.print_exc()

    def refresh_ui(self):
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        self.sections = {}

        for comp_name, items in self.data.items():
            self.create_section(comp_name)
            table = self.sections.get(comp_name)
            if table:
                for original_index, item in enumerate(items):
                    if not item.get("state", {}).get("in_trash", False):
                        table.add_row(item, original_index)

        self.container_layout.addStretch()
        self.container.adjustSize()

    def create_section(self, name):
        group = QGroupBox(name)
        g_layout = QVBoxLayout(group)

        table = StructureTableWidget(self, name)
        self.sections[name] = table

        add_row_btn = QPushButton(f"Add Material to {name}")
        add_row_btn.clicked.connect(lambda checked=False, n=name: self.open_dialog(n))

        g_layout.addWidget(table)
        g_layout.addWidget(add_row_btn)
        self.container_layout.addWidget(group)

    def add_material(self, comp_name, values_dict, is_trash=False):
        now = datetime.datetime.now().isoformat()

        included_carbon = values_dict.pop("_included_in_carbon_emission", True)
        included_recycling = values_dict.pop("_included_in_recyclability", True)

        new_entry = {
            "id": str(uuid.uuid4()),
            "values": values_dict,
            "meta": {
                "created_on": now,
                "modified_on": now,
                "is_user_defined": True,
                "is_from_db": False,
                "source_version": "1.0",
            },
            "state": {
                "in_trash": is_trash,
                "included_in_carbon_emission": included_carbon,
                "included_in_recyclability": included_recycling,
            },
        }

        current_data = self.controller.engine.fetch_chunk(self.chunk_name) or {}
        if comp_name not in current_data:
            current_data[comp_name] = []

        current_data[comp_name].append(new_entry)
        self.controller.engine.stage_update(
            chunk_name=self.chunk_name, data=current_data
        )
        self.save_current_state()
        self.on_refresh()

    def open_dialog(self, comp_name):
        dialog = MaterialDialog(comp_name, self)
        if dialog.exec():
            self.add_material(comp_name, dialog.get_values())

    def open_edit_dialog(self, comp_name, table_row_index):
        try:
            current_data = self.controller.engine.fetch_chunk(self.chunk_name) or {}
            items = current_data.get(comp_name, [])

            active_indices = [
                i
                for i, item in enumerate(items)
                if not item.get("state", {}).get("in_trash", False)
            ]

            if table_row_index < len(active_indices):
                original_idx = active_indices[table_row_index]
                item_to_edit = items[original_idx]

                dialog = MaterialDialog(comp_name, self, data=item_to_edit)
                if dialog.exec():
                    new_values = dialog.get_values()

                    included_carbon = new_values.pop(
                        "_included_in_carbon_emission", True
                    )
                    included_recycling = new_values.pop(
                        "_included_in_recyclability", True
                    )

                    item_to_edit["values"] = new_values
                    item_to_edit["meta"][
                        "modified_on"
                    ] = datetime.datetime.now().isoformat()
                    item_to_edit["state"][
                        "included_in_carbon_emission"
                    ] = included_carbon
                    item_to_edit["state"][
                        "included_in_recyclability"
                    ] = included_recycling

                    self.controller.engine.stage_update(
                        chunk_name=self.chunk_name, data=current_data
                    )
                    self.save_current_state()
                    QTimer.singleShot(0, self.on_refresh)
        except Exception as e:
            import traceback

            print(f"[ERROR] open_edit_dialog crashed: {e}")
            traceback.print_exc()

    def toggle_trash_status(self, comp_name, data_index, should_trash):
        data = self.controller.engine.fetch_chunk(self.chunk_name) or {}
        if comp_name in data and len(data[comp_name]) > data_index:
            if "state" not in data[comp_name][data_index]:
                data[comp_name][data_index]["state"] = {}
            data[comp_name][data_index]["state"]["in_trash"] = should_trash

            self.controller.engine.stage_update(chunk_name=self.chunk_name, data=data)
            self.save_current_state()
            self.on_refresh()

            main_view = self.window().findChild(QWidget, "StructureTabView")
            if main_view and hasattr(main_view, "on_refresh"):
                main_view.on_refresh()

    def add_new_component(self):
        name, ok = QInputDialog.getText(self, "New Component", "Enter Component Name:")
        if ok and name.strip():
            clean_name = name.strip()
            self.create_section(clean_name)
            current_data = self.controller.engine.fetch_chunk(self.chunk_name) or {}
            if clean_name not in current_data:
                current_data[clean_name] = []
                self.controller.engine.stage_update(
                    chunk_name=self.chunk_name, data=current_data
                )
                self.save_current_state()

    def save_current_state(self):
        if self.controller and self.controller.engine:
            eng = self.controller.engine
            eng._last_keystroke_time = time.time()
            eng._has_unsaved_changes = True
            try:
                eng.on_dirty(True)
            except:
                pass
