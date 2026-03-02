import math
import uuid
import datetime

from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QMessageBox,
    QCheckBox,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QDoubleValidator, QColor, QFont

# Assuming these utilities are available in your project structure
# from ...utils.definitions import DEFAULT_VEHICLES
# from ...utils.unit_resolver import analyze_conversion_sympy

# ---------------------------------------------------------------------------
# Constants & Styling
# ---------------------------------------------------------------------------

STRUCTURE_CHUNKS = [
    ("str_foundation", "Foundation"),
    ("str_sub_structure", "Sub Structure"),
    ("str_super_structure", "Super Structure"),
    ("str_misc", "Misc"),
]

# Row background states
BG_INVALID = "#fff1f0"  # Light Red (Error)
BG_SUSPICIOUS = "#fffbe6"  # Light Yellow (Warning)
BG_DISABLED = "#f5f5f5"  # Gray (Assigned)
BG_READY = "#f6ffed"  # Light Green (Valid)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    return lbl


# ---------------------------------------------------------------------------
# Step 1 — Vehicle + Route
# ---------------------------------------------------------------------------


class VehicleRouteStep(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignTop)

        # ── Template Selection ──────────────────────────────────────────
        layout.addWidget(_section_label("Vehicle Template"))

        template_layout = QHBoxLayout()
        self.dropdown = QComboBox()
        self.dropdown.setMinimumHeight(35)
        self.dropdown.addItem("-- Select a Preset Template --", userData=None)
        

        # 1. Load Default Presets
        try:
            # First try to get from controller engine if available
            presets = getattr(self.controller, "DEFAULT_VEHICLES", {})
            # Fallback to a local import simulation if controller doesn't have it
            # Replace the try/except preset block with:
            try:
                from ...utils.definitions import DEFAULT_VEHICLES

                presets = DEFAULT_VEHICLES
            except ImportError as e:
                print(f"[TransportDialog] Could not load DEFAULT_VEHICLES: {e}")
                presets = {}

                presets = DEFAULT_VEHICLES
        except Exception:
            presets = {}

        for name, specs in presets.items():
            self.dropdown.addItem(name, userData=specs)

        # 2. Load Custom Vehicles
        custom_vehicles = self._fetch_custom()
        if custom_vehicles:
            self.dropdown.addItem("── Custom Vehicles ──", userData=None)
            for v in custom_vehicles:
                self.dropdown.addItem(v.get("name", "Unnamed Custom"), userData=v)

        self.dropdown.currentIndexChanged.connect(self._on_template_selected)
        template_layout.addWidget(self.dropdown)
        layout.addLayout(template_layout)

        layout.addWidget(_divider())

        # ── Vehicle Details Grid ──────────────────────────────────────────
        layout.addWidget(_section_label("Vehicle Specifications"))

        v_grid = QGridLayout()
        v_grid.setSpacing(12)

        self.name_in = self._create_labeled_input(v_grid, "Vehicle Name *", 0, 0)
        self.payload_lbl = self._create_labeled_readonly(
            v_grid, "Available Payload (t)", 0, 1
        )

        self.capacity_in = self._create_labeled_spin(
            v_grid, "Gross Capacity of Vehicle (t) *", 0, 1000, 2, 1, 0
        )
        self.loading_in = self._create_labeled_spin(
            v_grid, "Target Loading (%) *", 0, 100, 1, 1, 1, default=100
        )

        self.empty_wt_in = self._create_labeled_spin(
            v_grid, "Empty Weight of Vehicle (t) *", 0, 1000, 2, 2, 0
        )
        self.eff_pay_lbl = self._create_labeled_readonly(
            v_grid, "Effective Payload (t)", 2, 1
        )

        self.ef_in = self._create_labeled_spin(
            v_grid, "Emission Factor (kgCO2e/t-km) *", 0, 10, 6, 3, 0, default=0.055
        )

        layout.addLayout(v_grid)

        self.save_custom_chk = QCheckBox("Save as custom vehicle for this project")
        # self.save_custom_chk.setStyleSheet("font-size: 12px; color: #262626;")
        layout.addWidget(self.save_custom_chk)

        layout.addWidget(_divider())

        # ── Route Details Grid ──────────────────────────────────────────
        layout.addWidget(_section_label("Route Information"))

        r_grid = QGridLayout()
        r_grid.setSpacing(12)

        self.origin_in = self._create_labeled_input(r_grid, "Origin Location", 0, 0)
        self.dest_in = self._create_labeled_input(r_grid, "Destination Location", 0, 1)
        self.dist_in = self._create_labeled_spin(
            r_grid, "Total Distance (km) *", 0, 100000, 1, 1, 0
        )

        layout.addLayout(r_grid)

        # Connections
        self.capacity_in.valueChanged.connect(self._recalculate)
        self.empty_wt_in.valueChanged.connect(self._recalculate)
        self.loading_in.valueChanged.connect(self._recalculate)

    def _fetch_custom(self) -> list:
        """Fetches custom vehicles stored in the project state."""
        try:
            data = self.controller.engine.fetch_chunk("project_vehicles") or {}
            return data.get("custom", [])
        except Exception:
            return []

    def _create_labeled_input(self, grid, label, row, col) -> QLineEdit:
        container = QWidget()
        l = QVBoxLayout(container)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(4)
        lbl = QLabel(label)
        # lbl.setStyleSheet("font-weight: 600; color: #262626; font-size: 12px;")
        le = QLineEdit()
        le.setMinimumHeight(32)
        l.addWidget(lbl)
        l.addWidget(le)
        grid.addWidget(container, row, col)
        return le

    def _create_labeled_spin(
        self, grid, label, mn, mx, dec, row, col, default=0.0
    ) -> QDoubleSpinBox:
        container = QWidget()
        l = QVBoxLayout(container)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(4)
        lbl = QLabel(label)
        # lbl.setStyleSheet("font-weight: 600; color: #262626; font-size: 12px;")
        sb = QDoubleSpinBox()
        sb.setRange(mn, mx)
        sb.setDecimals(dec)
        sb.setValue(default)
        sb.setMinimumHeight(32)
        l.addWidget(lbl)
        l.addWidget(sb)
        grid.addWidget(container, row, col)
        return sb

    def _create_labeled_readonly(self, grid, label, row, col) -> QLabel:
        container = QWidget()
        l = QVBoxLayout(container)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(4)
        lbl = QLabel(label)
        # lbl.setStyleSheet("font-weight: 600; color: #8c8c8c; font-size: 11px;")
        val = QLabel("—")
        val.setMinimumHeight(32)
        # val.setStyleSheet(
        #     "background: #f5f5f5; border: 1px solid #d9d9d9; border-radius: 4px; padding-left: 8px; font-weight: 700;"
        # )
        l.addWidget(lbl)
        l.addWidget(val)
        grid.addWidget(container, row, col)
        return val

    def _on_template_selected(self, index):
        specs = self.dropdown.itemData(index)
        if not specs:
            return
        self.name_in.setText(specs.get("name", ""))
        self.capacity_in.setValue(specs.get("capacity", 0))
        self.empty_wt_in.setValue(specs.get("empty_weight", 0))
        self.ef_in.setValue(specs.get("emission_factor", 0))
        self._recalculate()

    def _recalculate(self):
        cap = self.capacity_in.value()
        empty = self.empty_wt_in.value()
        loading = self.loading_in.value()

        payload = max(0.0, cap - empty)
        eff = payload * (loading / 100)

        self.payload_lbl.setText(f"{payload:,.2f} t")
        self.eff_pay_lbl.setText(f"{eff:,.2f} t")

        if empty >= cap and cap > 0:
            self.payload_lbl.setStyleSheet("background: #fff1f0; color: #000000;")
        else:
            self.payload_lbl.setStyleSheet("")

    def validate(self) -> bool:
        """UX-Driven Hard Blocker Checks"""
        if not self.name_in.text().strip():
            QMessageBox.critical(self, "Error", "Vehicle Name is required.")
            return False

        cap = self.capacity_in.value()
        empty = self.empty_wt_in.value()
        dist = self.dist_in.value()

        if empty <= 0:
            QMessageBox.critical(self, "Error", "Empty Weight must be greater than 0.")
            return False

        if cap <= empty:
            QMessageBox.critical(
                self, "Error", "Total Capacity must be greater than Empty Weight."
            )
            return False

        if dist <= 0:
            QMessageBox.critical(
                self,
                "Error",
                "Distance must be greater than 0 km to calculate emissions.",
            )
            return False

        return True

    def get_data(self) -> dict:
        cap = self.capacity_in.value()
        empty = self.empty_wt_in.value()
        loading = self.loading_in.value()
        payload = cap - empty
        return {
            "vehicle": {
                "name": self.name_in.text().strip(),
                "capacity": cap,
                "empty_weight": empty,
                "payload": payload,
                "loading_pct": loading,
                "effective_payload": payload * (loading / 100),
                "emission_factor": self.ef_in.value(),
                "is_custom": self.save_custom_chk.isChecked(),
            },
            "route": {
                "origin": self.origin_in.text().strip(),
                "destination": self.dest_in.text().strip(),
                "distance_km": self.dist_in.value(),
            },
        }


# ---------------------------------------------------------------------------
# Step 2 — Material Selection
# ---------------------------------------------------------------------------


class MaterialSelectionStep(QWidget):
    HEADERS = [
        "",
        "Category",
        "Material",
        "Qty",
        "Unit",
        "kg Factor",
        "Qty (kg)",
        "Status",
    ]

    def __init__(
        self, controller, assigned_uuids: set, saved_kg_factors: dict, parent=None
    ):
        super().__init__(parent)
        self.controller = controller
        self.assigned_uuids = assigned_uuids
        self.saved_kg_factors = saved_kg_factors
        self._rows_metadata = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(_section_label("Assign Materials to Vehicle"))

        # Legend / Summary Area
        info_bar = QHBoxLayout()

        self.counter_lbl = QLabel("Total Selected Load: 0.00 t / 0.00 t")

        info_bar.addWidget(self.counter_lbl)
        info_bar.addStretch()

        for color, text in [
            (BG_INVALID, "Error"),
            (BG_SUSPICIOUS, "Warning"),
            (BG_DISABLED, "Assigned"),
        ]:
            dot = QLabel()
            dot.setFixedSize(12, 12)
            # dot.setStyleSheet(
            #     f"background: {color}; border: 1px solid #d9d9d9; border-radius: 2px;"
            # )
            lbl = QLabel(text)
            # lbl.setStyleSheet("font-size: 11px; color: #8c8c8c;")
            info_bar.addWidget(dot)
            info_bar.addWidget(lbl)
            info_bar.addSpacing(10)

        layout.addLayout(info_bar)

        # Table Setup
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)

        # High Contrast Styling
        # self.table.setStyleSheet(
        #     """
        #     QTableWidget { border: 1px solid #d9d9d9; }
        #     """
        # )

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)  # Checkbox
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Category
        h.setSectionResizeMode(2, QHeaderView.Stretch)  # Material
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Unit
        self.table.setColumnWidth(5, 100)  # Factor
        h.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Total kg
        h.setSectionResizeMode(7, QHeaderView.Stretch)  # Status
        self.table.setColumnHidden(6, True)


        layout.addWidget(self.table)
        self._populate()

    def _item(self, text="", align=None) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(Qt.ItemIsEnabled)
        if align:
            it.setTextAlignment(align)
        return it

    def _populate(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._rows_metadata = []

        for chunk_id, category in STRUCTURE_CHUNKS:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            for comp_name, items in data.items():
                for item in items:
                    if item.get("state", {}).get("in_trash", False):
                        continue

                    mat_uuid = item.get("id", "")
                    v = item.get("values", {})
                    unit = v.get("unit", "")
                    qty = float(v.get("quantity", 0) or 0)

                    kg_factor = self.saved_kg_factors.get(mat_uuid, 1.0)
                    is_suspicious = abs(kg_factor - 1.0) < 1e-6 and unit.lower() != "kg"
                    is_assigned = mat_uuid in self.assigned_uuids

                    row = self.table.rowCount()
                    self.table.insertRow(row)

                    # Col 0: Checkbox
                    chk_w = QWidget()
                    chk_l = QHBoxLayout(chk_w)
                    chk = QCheckBox()
                    chk.setChecked(
                        mat_uuid in self.saved_kg_factors and not is_assigned
                    )
                    chk.setEnabled(not is_assigned)
                    chk.stateChanged.connect(self.update_weight_counter)
                    chk_l.addWidget(chk)
                    chk_l.setAlignment(Qt.AlignCenter)
                    chk_l.setContentsMargins(0, 0, 0, 0)

                    sort_chk = self._item()
                    sort_chk.setData(Qt.UserRole, 1 if chk.isChecked() else 0)
                    self.table.setItem(row, 0, sort_chk)
                    self.table.setCellWidget(row, 0, chk_w)

                    # Col 1: Category
                    self.table.setItem(row, 1, self._item(category))

                    # Col 2: Material Name
                    mat_item = self._item(v.get("material_name", ""))
                    font = mat_item.font()
                    font.setBold(True)
                    mat_item.setFont(font)
                    self.table.setItem(row, 2, mat_item)

                    # Col 3: Qty
                    qty_item = self._item(
                        f"{qty:,.2f} {unit}", Qt.AlignRight | Qt.AlignVCenter
                    )
                    qty_item.setData(Qt.UserRole, qty)
                    self.table.setItem(row, 3, qty_item)

                    # Col 4: Unit
                    self.table.setItem(row, 4, self._item(unit))

                    # Col 5: kg Factor (LineEdit)
                    kg_edit = QLineEdit(str(kg_factor))
                    kg_edit.setValidator(QDoubleValidator(0, 1e9, 4))
                    kg_edit.setMinimumHeight(28)
                    kg_edit.textChanged.connect(
                        lambda t, r=row, q=qty: self._on_factor_changed(t, r, q)
                    )

                    factor_sort = self._item()
                    factor_sort.setData(Qt.UserRole, kg_factor)
                    self.table.setItem(row, 5, factor_sort)
                    self.table.setCellWidget(row, 5, kg_edit)

                    # Col 6: Total (kg)
                    tot_item = self._item(
                        f"{qty * kg_factor:,.0f} kg", Qt.AlignRight | Qt.AlignVCenter
                    )
                    tot_item.setData(Qt.UserRole, qty * kg_factor)
                    self.table.setItem(row, 6, tot_item)

                    # Col 7: Status
                    self.table.setItem(row, 7, self._item("", Qt.AlignCenter))

                    self._rows_metadata.append(
                        {"uuid": mat_uuid, "unit": unit, "qty": qty}
                    )

                    # Row color state
                    if is_assigned:
                        self.table.item(row, 6).setText("Locked")
                    else:
                        self._update_row_status(row, kg_factor, is_suspicious)

        self.table.setSortingEnabled(True)
        self.update_weight_counter()

    def _on_factor_changed(self, text, row, qty):
        try:
            val = float(text or 0)
            # Live calculate col 6
            self.table.item(row, 6).setText(f"{qty * val:,.0f} kg")
            self.table.item(row, 6).setData(Qt.UserRole, qty * val)

            # Check suspicious (1.0 warning)
            unit = self._rows_metadata[row]["unit"]
            is_sus = abs(val - 1.0) < 1e-6 and unit.lower() != "kg"
            self._update_row_status(row, val, is_sus)
            self.update_weight_counter()
        except:
            pass

    def _update_row_status(self, row, factor, is_sus):
        if factor <= 0:
            self.table.item(row, 7).setText("❌ Missing Factor")
        elif is_sus:
            self.table.item(row, 7).setText("⚠️ Check Factor")
        else:
            self.table.item(row, 7).setText("✓ Ready")

    def update_weight_counter(self):
        total_kg = 0.0
        for row in range(self.table.rowCount()):
            chk_w = self.table.cellWidget(row, 0)
            if not chk_w:
                continue
            chk = chk_w.findChild(QCheckBox)
            if chk and chk.isChecked():
                total_kg += self.table.item(row, 6).data(Qt.UserRole) or 0.0

        total_t = total_kg / 1000.0

        # Pull capacity from Step 1
        parent_dialog = self.window()
        if hasattr(parent_dialog, "step1"):
            capacity = parent_dialog.step1.get_data()["vehicle"]["payload"]
        else:
            capacity = 0.0

        self.counter_lbl.setText(
            f"Total Selected Load: {total_t:,.2f} t / {capacity:,.2f} t Capacity"
        )
        if total_t > capacity and capacity > 0:
            self.counter_lbl.setStyleSheet("color: #ff0000;")
        else:
            self.counter_lbl.setStyleSheet("")

    def validate(self) -> bool:
        selected = self.get_selected_materials()
        if not selected:
            QMessageBox.critical(
                self, "Selection Error", "Please select at least one material."
            )
            return False

        # Check for 0 factors in selected items
        for m in selected:
            if m["kg_factor"] <= 0:
                QMessageBox.critical(
                    self,
                    "Factor Error",
                    "Selected materials must have a kg factor > 0.",
                )
                return False

        # Warning for 1:1 factors
        has_warnings = False
        for m in selected:
            meta = next(
                (r for r in self._rows_metadata if r["uuid"] == m["uuid"]), None
            )
            if (
                meta
                and abs(m["kg_factor"] - 1.0) < 1e-6
                and meta["unit"].lower() != "kg"
            ):
                has_warnings = True
                break

        if has_warnings:
            res = QMessageBox.warning(
                self,
                "Verify Data",
                "One or more materials use a 1:1 mass factor (1 unit = 1kg). Continue anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if res == QMessageBox.No:
                return False

        return True

    def get_selected_materials(self) -> list:
        results = []
        for row in range(self.table.rowCount()):
            chk_w = self.table.cellWidget(row, 0)
            if not chk_w:
                continue
            chk = chk_w.findChild(QCheckBox)
            if chk and chk.isChecked():
                kg_edit = self.table.cellWidget(row, 5)
                factor = float(kg_edit.text() or 0)
                results.append(
                    {"uuid": self._rows_metadata[row]["uuid"], "kg_factor": factor}
                )
        return results


# ---------------------------------------------------------------------------
# Main Dialog
# ---------------------------------------------------------------------------


class TransportDialog(QDialog):
    def __init__(self, controller, assigned_uuids: set, data: dict = None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.assigned_uuids = assigned_uuids
        self.is_edit = data is not None
        self.existing_data = data or {}

        self.setWindowTitle(
            "Transport Log Editor" if self.is_edit else "Add Transport Log"
        )
        self.setMinimumSize(850, 650)

        # Standard flags to ensure close button is available and context help is hidden
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(15, 15, 15, 15)
        outer.setSpacing(10)

        # Header / Step Indicator
        self.step_lbl = QLabel("Step 1: Vehicle & Route Details")
        self.step_lbl.setStyleSheet(
            "font-weight: bold; font-size: 16px;"
        )
        outer.addWidget(self.step_lbl)
        outer.addWidget(_divider())

        # Scrollable Stack
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.stack = QStackedWidget()
        saved_kg = (
            {m["uuid"]: m["kg_factor"] for m in self.existing_data.get("materials", [])}
            if self.is_edit
            else {}
        )

        self.step1 = VehicleRouteStep(controller)
        self.step2 = MaterialSelectionStep(controller, assigned_uuids, saved_kg)

        self.stack.addWidget(self.step1)
        self.stack.addWidget(self.step2)

        if self.is_edit:
            self._load_existing()

        scroll.setWidget(self.stack)
        outer.addWidget(scroll)

        outer.addWidget(_divider())

        # Navigation Bar
        btn_bar = QHBoxLayout()
        self.back_btn = QPushButton("← Previous Step")
        self.back_btn.setMinimumHeight(35)
        self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self._go_back)

        self.next_btn = QPushButton("Continue to Materials →")
        self.next_btn.setMinimumHeight(40)

        self.next_btn.clicked.connect(self._go_next)

        self.finish_btn = QPushButton("Save Transport Entry")
        self.finish_btn.setMinimumHeight(40)

        self.finish_btn.setVisible(False)
        self.finish_btn.clicked.connect(self._finish)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(35)
        self.cancel_btn.clicked.connect(self.reject)

        btn_bar.addWidget(self.back_btn)
        btn_bar.addStretch()
        btn_bar.addWidget(self.cancel_btn)
        btn_bar.addWidget(self.next_btn)
        btn_bar.addWidget(self.finish_btn)
        outer.addLayout(btn_bar)

    def _go_next(self):
        if not self.step1.validate():
            return
        self.stack.setCurrentIndex(1)
        self.step_lbl.setText("Step 2: Cargo & Material Assignment")
        self.next_btn.setVisible(False)
        self.finish_btn.setVisible(True)
        self.back_btn.setVisible(True)
        self.step2.update_weight_counter()  # Refresh capacity link

    def _load_existing(self):
        d = self.existing_data
        v = d.get("vehicle", {})
        r = d.get("route", {})

        # Step 1 — Vehicle
        self.step1.name_in.setText(v.get("name", ""))
        self.step1.capacity_in.setValue(v.get("capacity", 0))
        self.step1.empty_wt_in.setValue(v.get("empty_weight", 0))
        self.step1.loading_in.setValue(v.get("loading_pct", 100))
        self.step1.ef_in.setValue(v.get("emission_factor", 0.055))

        # Step 1 — Route
        self.step1.origin_in.setText(r.get("origin", ""))
        self.step1.dest_in.setText(r.get("destination", ""))
        self.step1.dist_in.setValue(r.get("distance_km", 0))

        # Trigger recalculate so payload labels update
        self.step1._recalculate()

    def _go_back(self):
        self.stack.setCurrentIndex(0)
        self.step_lbl.setText("Step 1: Vehicle & Route Details")
        self.next_btn.setVisible(True)
        self.finish_btn.setVisible(False)
        self.back_btn.setVisible(False)

    def _finish(self):
        if not self.step2.validate():
            return
        self.accept()

    def get_vehicle_entry(self) -> dict:
        step1_data = self.step1.get_data()
        materials = self.step2.get_selected_materials()

        vehicle = step1_data["vehicle"]
        route = step1_data["route"]

        total_kg = sum(
            m["kg_factor"]
            * next(
                (r["qty"] for r in self.step2._rows_metadata if r["uuid"] == m["uuid"]),
                0.0,
            )
            for m in materials
        )
        total_t = total_kg / 1000.0
        distance = route["distance_km"]
        ef = vehicle["emission_factor"]
        emissions = total_t * distance * ef

        return {
            "id": self.existing_data.get("id", str(uuid.uuid4())),
            "vehicle": vehicle,
            "route": route,
            "materials": materials,
            "summary": {
                "total_cargo_kg": total_kg,
                "total_cargo_t": total_t,
                "distance_km": distance,
                "emission_factor": ef,
                "total_emissions_kgco2e": emissions,
            },
            "meta": {
                "created_at": self.existing_data.get("meta", {}).get(
                    "created_at", datetime.datetime.now().isoformat()
                ),
                "updated_at": datetime.datetime.now().isoformat(),
            },
        }
