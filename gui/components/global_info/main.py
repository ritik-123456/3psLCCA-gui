# """
# gui\components\global_info\main.py
# """

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QWidget,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap

from ..base_widget import ScrollableForm
from ..utils.form_builder.form_definitions import FieldDef, Section
from ..utils.form_builder.form_builder import build_form, _IMG_PREVIEWS_ATTR
from ..utils.countries_data import CURRENCIES, COUNTRIES


BASE_DOCS_URL = "https://yourdocs.com/general/"


GENERAL_FIELDS = [
    # ── Project Information ──────────────────────────────────────────────
    Section("Project Information"),
    FieldDef(
        "project_name",
        "Project Name",
        "Official name or title of the bridge/infrastructure project.",
        "text",
        required=True,
        doc_slug="project-name",
    ),
    FieldDef(
        "project_code",
        "Project Code",
        "Unique reference code assigned to this project.",
        "text",
        doc_slug="project-code",
    ),
    FieldDef(
        "project_description",
        "Project Description",
        "Brief description of the project scope, objectives, or background.",
        "textarea",
        doc_slug="project-description",
    ),
    FieldDef(
        "remarks",
        "Remarks",
        "Any additional notes, assumptions, or comments relevant to this evaluation.",
        "textarea",
        doc_slug="remarks",
    ),
    # ── Evaluating Agency ────────────────────────────────────────────────
    Section("Evaluating Agency"),
    FieldDef(
        "agency_name",
        "Agency Name",
        "Name of the organization responsible for this evaluation.",
        "text",
        required=True,
        doc_slug="agency-name",
    ),
    FieldDef(
        "contact_person",
        "Contact Person",
        "Primary contact handling this project.",
        "text",
        doc_slug="contact-person",
    ),
    FieldDef(
        "agency_address",
        "Agency Address",
        "Street address of the evaluating agency.",
        "text",
        doc_slug="agency-address",
    ),
    FieldDef(
        "agency_country",
        "Country",
        "Country where the evaluating agency is based.",
        "combo",
        options=COUNTRIES,
        doc_slug="agency-country",
    ),
    FieldDef(
        "agency_email",
        "Email",
        "Official email address for correspondence.",
        "text",
        doc_slug="agency-email",
    ),
    FieldDef(
        "agency_phone",
        "Phone",
        "Contact phone number.",
        "phone",   # ← new custom type
    ),
    FieldDef(
        "agency_logo",
        "Agency Logo",
        "Upload agency logo (JPG or PNG, auto-resized to 3 cm × 3 cm print size).",
        "upload_img",
        options="default",
        doc_slug="agency-logo",
    ),
    # ── Project Settings ─────────────────────────────────────────────────
    Section("Project Settings"),
    FieldDef(
        "project_country",
        "Country",
        "Country where the bridge project is located. Set at project creation.",
        "text",
        doc_slug="project_country",
    ),
    FieldDef(
        "project_currency",
        "Currency",
        "Currency used for all cost figures. Set at project creation.",
        "text",
        doc_slug="project_currency",
    ),
    # FieldDef(
    #     "currency_to_usd_rate",
    #     "Exchange Rate to USD",
    #     "Conversion rate from the selected currency to USD (1 unit of selected currency equals X USD).",
    #     "float",
    #     options=(0.0001, 1000.0, 6),
    #     unit="(USD)",
    #     required=True,
    #     doc_slug="currency-to-usd-rate",
    # ),
]


class GeneralInfo(ScrollableForm):

    created = Signal()

    _LOCKED = {"project_country", "project_currency"}

    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name="general_info")

        self.required_keys = build_form(self, GENERAL_FIELDS, BASE_DOCS_URL)

        # Lock country and currency — disable widget so user can't edit,
        # but keep in _field_map so get_data_dict() saves them normally
        self.required_keys = [k for k in self.required_keys if k not in self._LOCKED]
        for key in self._LOCKED:
            w = getattr(self, key, None)
            if w is not None:
                w.setEnabled(False)

        # ── Clear All button ─────────────────────────────────────────────
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 10, 0, 10)

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setMinimumHeight(35)
        self.btn_clear_all.clicked.connect(self.clear_all)

        btn_layout.addWidget(self.btn_clear_all)
        self.form.addRow(btn_row)

    # ── Clear All ────────────────────────────────────────────────────────
    def clear_all(self):
        for entry in GENERAL_FIELDS:
            if isinstance(entry, Section):
                continue
            if entry.key in self._LOCKED:
                continue  # never clear country or currency

            widget = getattr(self, entry.key, None)
            if widget is None:
                continue

            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QTextEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(widget.minimum())

        # Reset all upload_img previews
        for key, preview in getattr(self, _IMG_PREVIEWS_ATTR, {}).items():
            preview.setPixmap(QPixmap())
            preview.setText("No image selected")

        self._on_field_changed()

    # ── Validation ───────────────────────────────────────────────────────
    def validate(self):
        errors = []

        for key in self.required_keys:
            widget = getattr(self, key, None)
            if isinstance(widget, QLineEdit) and widget.text().strip() == "":
                label = next(
                    f.title
                    for f in GENERAL_FIELDS
                    if isinstance(f, FieldDef) and f.key == key
                )
                errors.append(label)
                widget.setStyleSheet("border: 1px solid red;")

        if errors:
            return False, errors

        return True, []

    def _on_field_changed(self):
        super()._on_field_changed()
        self.created.emit()
