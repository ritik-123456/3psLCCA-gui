"""
gui/pages/bridge_data.py
"""

from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from ..base_widget import ScrollableForm
from ..utils.form_builder.form_definitions import FieldDef, Section
from ..utils.form_builder.form_builder import build_form, _IMG_PREVIEWS_ATTR
from ..utils.countries_data import CURRENCIES, COUNTRIES


BASE_DOCS_URL = "https://yourdocs.com/bridge/"


BRIDGE_FIELDS = [
    # ── Identification ───────────────────────────────────────────────────
    Section("Bridge Identification"),
    FieldDef(
        "bridge_name",
        "Name of Bridge",
        "The official or commonly used name identifying the bridge.",
        "text",
        required=True,
        doc_slug="bridge-name",
    ),
    FieldDef(
        "user_agency",
        "Owner",
        "Name of the owner, client, or responsible agency for this bridge.",
        "text",
        required=True,
        doc_slug="user-agency",
    ),
    # ── Location ─────────────────────────────────────────────────────────
    Section("Location"),
    FieldDef(
        "project_country",
        "Country",
        "Country in which the bridge is situated.",
        "text",
        options=COUNTRIES,
        required=True,
        doc_slug="location-country",
    ),
    FieldDef(
        "location_address",
        "Address",
        "Full address or site description of the bridge location.",
        "text",
        doc_slug="location-address",
    ),
    FieldDef(
        "location_from",
        "From",
        "Starting point of the bridge (city, road name, landmark, or coordinates).",
        "text",
        doc_slug="location-from",
    ),
    FieldDef(
        "location_via",
        "Via",
        "Intermediate feature crossed by the bridge (e.g., river, valley, railway, highway).",
        "text",
        doc_slug="location-via",
    ),
    FieldDef(
        "location_to",
        "To",
        "Ending point of the bridge (city, road name, landmark, or coordinates).",
        "text",
        doc_slug="location-to",
    ),
    # ── Technical Specifications ─────────────────────────────────────────
    Section("Technical Specifications"),
    FieldDef(
        "bridge_type",
        "Type of Bridge",
        "Structural classification of the bridge (e.g. Girder, Arch, Cable-stayed).",
        "combo",
        options=[
            "Girder",
            "Arch",
            "Cable-Stayed",
            "Suspension",
            "Truss",
            "Box Girder",
            "Slab",
            "Other",
        ],
        required=True,
        doc_slug="bridge-type",
    ),
    FieldDef(
        "span",
        "Span",
        "Total span length of the bridge between supports.",
        "float",
        options=(0.0, 99999.0, 2),
        unit="(m)",
        required=True,
        doc_slug="span",
    ),
    FieldDef(
        "num_lanes",
        "Number of Lanes",
        "Total number of traffic lanes on the bridge deck.",
        "int",
        options=(0, 20),
        required=True,
        doc_slug="num-lanes",
    ),
    FieldDef(
        "footpath",
        "Footpath",
        "Indicates whether a dedicated pedestrian footpath is provided.",
        "combo",
        options=["Yes", "No"],
        required=True,
        doc_slug="footpath",
    ),
    FieldDef(
        "wind_speed",
        "Wind Speed",
        "Design wind speed used for structural analysis at the bridge site.",
        "float",
        options=(0.0, 999.0, 2),
        unit="(m/s)",
        required=True,
        doc_slug="wind-speed",
    ),
    FieldDef(
        "carriageway_width",
        "Carriageway Width",
        "Clear width of the roadway portion of the bridge deck.",
        "float",
        options=(0.0, 9999.0, 2),
        unit="(m)",
        required=True,
        doc_slug="carriageway-width",
    ),
    # ── Timeline ─────────────────────────────────────────────────────────
    Section("Timeline"),
    FieldDef(
        "year_of_construction",
        "Year of Construction / Present Year",
        "Year the bridge was (or is planned to be) constructed, used as the "
        "baseline for life cycle cost assessment.",
        "int",
        options=(1900, 2200),
        required=True,
        doc_slug="year-of-construction",
    ),
    FieldDef(
        "duration_construction_months",
        "Duration of Construction",
        "Construction duration expressed in months.",
        "int",
        options=(0, 1200),
        unit="(months)",
        doc_slug="duration-construction-months",
    ),
    FieldDef(
        "working_days_per_month",
        "Working Days per Month",
        "Number of working days assumed per month for scheduling purposes.",
        "int",
        options=(0, 31),
        unit="(days)",
        doc_slug="working-days-per-month",
    ),
    # ── Life Cycle ───────────────────────────────────────────────────────
    Section("Life Cycle"),
    FieldDef(
        "design_life",
        "Design Life",
        "Expected operational lifetime of the bridge structure.",
        "int",
        options=(0, 999),
        unit="(years)",
        required=True,
        doc_slug="design-life",
    ),
    FieldDef(
        "service_life",
        "Service Life",
        "Actual or anticipated years the bridge remains in serviceable condition.",
        "int",
        options=(0, 999),
        unit="(years)",
        required=True,
        doc_slug="service-life",
    ),
]


class BridgeData(ScrollableForm):
    _LOCKED = {"project_country"}

    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name="bridge_data")

        self.required_keys = build_form(self, BRIDGE_FIELDS, BASE_DOCS_URL)

        # location_country is set at project creation — lock it

        self.required_keys = [
            k for k in self.required_keys if k not in self._LOCKED]
        for key in self._LOCKED:
            w = getattr(self, key, None)
            if w is not None:
                w.setEnabled(False)

        # ── Buttons row ───────────────────────────────────────────────────
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 10, 0, 10)
        btn_layout.setSpacing(10)

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setMinimumHeight(35)
        self.btn_clear_all.clicked.connect(self.clear_all)

        btn_layout.addWidget(self.btn_clear_all)
        btn_layout.addStretch()
        self.form.addRow(btn_row)

    # ── Suggested values ─────────────────────────────────────────────────
    def load_suggested_values(self):
        defaults = {
            "year_of_construction": date.today().year,
        }

        for key, val in defaults.items():
            widget = getattr(self, key, None)
            if widget is None:
                continue
            if isinstance(widget, QComboBox):
                idx = widget.findText(str(val))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(val)
            elif isinstance(widget, QLineEdit):
                widget.setText(str(val))
            widget.setStyleSheet("")

        self._on_field_changed()

        if self.controller and self.controller.engine:
            self.controller.engine._log("Bridge: Suggested values applied.")

    # ── Clear All ────────────────────────────────────────────────────────
    def clear_all(self):
        for entry in BRIDGE_FIELDS:
            if isinstance(entry, Section):
                continue
            if entry.key in self._LOCKED:
                continue  # never clear country or currency

            widget = getattr(self, entry.key, None)
            if widget is None:
                continue

            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(widget.minimum())
            widget.setStyleSheet("")

        self._on_field_changed()

        if self.controller and self.controller.engine:
            self.controller.engine._log("Bridge: All fields cleared.")

    # ── Validation ───────────────────────────────────────────────────────
    def validate(self):
        errors = []

        for key in self.required_keys:
            widget = getattr(self, key, None)
            if widget is None:
                continue

            empty = False
            if isinstance(widget, QLineEdit):
                empty = widget.text().strip() == ""
            elif isinstance(widget, QComboBox):
                empty = False  # always has a selection
            else:
                empty = widget.value() <= 0

            if empty:
                label = next(
                    f.title
                    for f in BRIDGE_FIELDS
                    if isinstance(f, FieldDef) and f.key == key
                )
                errors.append(label)
                widget.setStyleSheet("border: 1px solid red;")

        if errors:
            msg = f"Missing required bridge data: {', '.join(errors)}"
            if self.controller and self.controller.engine:
                self.controller.engine._log(msg)
            return False, errors

        return True, []
