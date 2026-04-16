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
from ..utils.validation_helpers import (
    clear_field_styles,
    freeze_form,
    freeze_widgets,
    validate_form,
    confirm_clear_all,
)
from ..utils.countries_data import CURRENCIES, COUNTRIES
from ..utils.display_format import DECIMAL_PLACES
from three_ps_lcca_gui.gui.themes import get_token


from ..utils.doc_handler import make_doc_opener
_DOC_OPENER = make_doc_opener("bridge")


BRIDGE_FIELDS = [
    # ── Identification ───────────────────────────────────────────────────
    Section("Bridge Identification"),
    FieldDef(
        "bridge_name",
        "Name of Bridge",
        "",
        "text"
    ),
    FieldDef(
        "user_agency",
        "Owner",
        "Name of the owner, client, or responsible agency for this bridge.",
        "text"
    ),
    # ── Location ─────────────────────────────────────────────────────────
    Section("Location"),
    FieldDef(
        "project_country",
        "Country",
        "Country in which the bridge is situated.",
        "text",
        options=COUNTRIES,
        required=True
    ),
    FieldDef(
        "location_from",
        "From",
        "Starting point of the bridge (city, road name, landmark, or coordinates).",
        "text"
    ),
    FieldDef(
        "location_via",
        "Via",
        "Intermediate feature crossed by the bridge (e.g., river, valley, railway, highway).",
        "text"
    ),
    FieldDef(
        "location_to",
        "To",
        "Ending point of the bridge (city, road name, landmark, or coordinates).",
        "text"
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
        doc_slug="bridge-type",
    ),
    FieldDef(
        "span",
        "Span",
        "Total span length of the bridge between supports.",
        "float",
        options=(0.0, 99999.0, DECIMAL_PLACES),
        unit="(m)",
        default=0.0,
    ),
    FieldDef(
        "carriageway_width",
        "Carriageway Width",
        "Clear width of the roadway portion of the bridge deck.",
        "float",
        options=(0.0, 9999.0, DECIMAL_PLACES),
        unit="(m)",
        default=0.0,
    ),
    FieldDef(
        "num_lanes",
        "Number of Lanes",
        "Total number of traffic lanes on the bridge deck.",
        "int",
        options=(0, 50),
        default=0,
    ),
    FieldDef(
        "vehicle_path_direction",
        "Vehicle Path Direction",
        "Indicates whether the road allows one-way or two-way traffic.",
        "combo",
        options=["One Way", "Two Way"],
    ),
    FieldDef(
        "footpath",
        "Footpath",
        "Indicates whether a dedicated pedestrian footpath is provided.",
        "combo",
        options=["Yes", "No"],
    ),
    FieldDef(
        "wind_speed",
        "Wind Speed",
        "Design wind speed used for structural analysis at the bridge site.",
        "float",
        options=(0.0, 999.0, DECIMAL_PLACES),
        unit="(m/s)",
        default=0.0,
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
        default=0,
    ),
    FieldDef(
        "year_of_construction",
        "Year of Construction",
        "Year the bridge was (or is planned to be) constructed, used as the "
        "baseline for life cycle cost assessment.",
        "int",
        options=(2000, 2500),
        required=True,
        default=date.today().year,
    ),
    # ── Construction Schedule ─────────────────────────────────────────────
    Section("Construction Schedule"),
    FieldDef(
        "duration_construction_months",
        "Duration of Construction",
        "Construction duration expressed in months.",
        "float",
        options=(0.0, 1200.0, DECIMAL_PLACES),
        required=True,
        unit="(months)",
        default=0.0,
    ),
    FieldDef(
        "working_days_per_month",
        "Working Days per Month",
        "Number of working days assumed per month for scheduling purposes.",
        "int",
        options=(0, 31),
        unit="(days)",
        default=22,
    ),
    FieldDef(
        "days_per_month",
        "Days per Month",
        "Days assumed per month the traffic of the road is affected.",
        "int",
        options=(0, 31),
        unit="(days)",
        default=30,
    ),
]


BRIDGE_WARN_RULES = {
    "span": (None, 5000.0, None, "Span exceeds 5000 m - please verify"),
    "carriageway_width": (
        1.5,
        50.0,
        "Carriageway width is very small - verify",
        "Carriageway width exceeds 50 m - please verify",
    ),
    "num_lanes": (None, 16, None, "Number of lanes exceeds 16 - please verify"),
    "wind_speed": (None, 80.0, None, "Wind speed exceeds 80 m/s - please verify"),
    "design_life": (
        10,
        200,
        "Design life below 10 years - verify",
        "Design life exceeds 200 years - verify",
    ),
    "duration_construction_months": (
        None,
        240,
        None,
        "Construction duration exceeds 240 months - verify",
    ),
    "working_days_per_month": (None, 31, None, "Working days per month exceeds 31"),
}


class BridgeData(ScrollableForm):
    _LOCKED = {"project_country"}

    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name="bridge_data")

        self.required_keys = build_form(self, BRIDGE_FIELDS, _DOC_OPENER)

        # location_country is set at project creation - lock it

        self.required_keys = [k for k in self.required_keys if k not in self._LOCKED]
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
        self.form.addRow(btn_row)

    # ── Suggested values ─────────────────────────────────────────────────
    def load_suggested_values(self):
        self._on_field_changed()

        if self.controller and self.controller.engine:
            self.controller.engine._log("Bridge: Suggested values applied.")

    # ── Clear All ────────────────────────────────────────────────────────
    def clear_all(self):
        if not confirm_clear_all(self):
            return

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
    def freeze(self, frozen: bool = True):
        freeze_form(BRIDGE_FIELDS, self, frozen, skip_keys=self._LOCKED)
        freeze_widgets(frozen, self.btn_clear_all)

    def clear_validation(self):
        clear_field_styles(BRIDGE_FIELDS, self, skip_keys=self._LOCKED)

    def validate(self):
        result = validate_form(
            BRIDGE_FIELDS, self, warn_rules=BRIDGE_WARN_RULES, skip_keys=self._LOCKED
        )
        # days_per_month must be 29–31
        dm = getattr(self, "days_per_month", None)
        if dm is not None and not (29 <= dm.value() <= 31):
            result["errors"].append("Days per Month must be between 29 and 31")
            dm.setStyleSheet(f"border: 1px solid {get_token('danger')};")
        # Cross-field: working_days_per_month must not exceed days_per_month
        wd = getattr(self, "working_days_per_month", None)
        if (
            wd is not None
            and dm is not None
            and wd.value() > 0
            and dm.value() > 0
            and wd.value() > dm.value()
        ):
            result["warnings"].append(
                "Working days per month exceeds days per month - please verify"
            )
            wd.setStyleSheet("border: 1px solid orange;")
        # year_of_construction should be >= current year
        yoc = getattr(self, "year_of_construction", None)
        if yoc is not None and yoc.value() < date.today().year:
            result["warnings"].append(
                f"Year of construction ({yoc.value()}) is before "
                f"{date.today().year} - verify this is intentional"
            )
            yoc.setStyleSheet("border: 1px solid orange;")
        return result

    def get_data(self) -> dict:
        return {"chunk": "bridge_data", "data": self.get_data_dict()}


