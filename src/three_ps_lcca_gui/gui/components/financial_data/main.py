from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QWidget,
)

from ..base_widget import ScrollableForm
from ..utils.form_builder.form_definitions import FieldDef, Section
from ..utils.form_builder.form_builder import build_form
from ..utils.validation_helpers import clear_field_styles, freeze_form, freeze_widgets, validate_form, confirm_clear_all


from ..utils.doc_handler import make_doc_opener
_DOC_OPENER = make_doc_opener("financial")

FINANCIAL_FIELDS = [
    Section("Economic Parameters"),
    FieldDef(
        "discount_rate",
        "Discount Rate",
        "The rate used to convert future cash flows into present value. "
        "Reflects the time value of money and investment risk.",
        "float",
        options=(0.0, 100.0, 2),
        unit="(%)",
        required=True,
        doc_slug="discount-rate",
        default=0.0,
    ),
    FieldDef("discount_rate_source", "Source: Discount Rate", "", "text"),
    FieldDef(
        "inflation_rate",
        "Inflation Rate",
        "Expected annual increase in general price levels over time.",
        "float",
        options=(0.0, 100.0, 2),
        unit="(%)",
        required=True,
        doc_slug="inflation-rate",
        default=0.0,
    ),
    FieldDef("inflation_rate_source", "Source: Inflation Rate", "", "text"),
    FieldDef(
        "interest_rate",
        "Interest Rate",
        "The borrowing or lending rate applied to capital financing.",
        "float",
        options=(0.0, 100.0, 2),
        unit="(%)",
        required=True,
        doc_slug="interest-rate",
        default=0.0,
    ),
    FieldDef("interest_rate_source", "Source: Interest Rate", "", "text"),
    FieldDef(
        "investment_ratio",
        "Investment Ratio",
        "Proportion of total cost financed through investment (0 to 1).",
        "float",
        options=(0.0, 1.0, 4),
        required=True,
        doc_slug="investment-ratio",
        default=0.0,
    ),
    FieldDef("investment_ratio_source", "Source: Investment Ratio", "", "text"),
]

FINANCIAL_WARN_RULES = {
    "discount_rate": (0.0, 30.0,
                      None,
                      "Discount rate exceeds 30% - please verify"),
    "inflation_rate": (0.0, 25.0,
                       None,
                       "Inflation rate exceeds 25% - please verify"),
    "interest_rate": (0.0, 35.0,
                      None,
                      "Interest rate exceeds 35% - please verify"),
}

SUGGESTED_VALUES = {
    # ── Economic Parameters ───────────────────────────────────────────────
    "discount_rate": 6.70,
    "inflation_rate": 5.15,
    "interest_rate": 7.75,
    "investment_ratio": 0.5,
    # ── Carbon & Currency ─────────────────────────────────────────────────
    "social_cost_of_carbon": 86.40,
    "currency_conversion": 88.73,
}


class FinancialData(ScrollableForm):
    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name="financial_data")

        self.required_keys = build_form(self, FINANCIAL_FIELDS, _DOC_OPENER)

        # ── Buttons row ───────────────────────────────────────────────────
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 10, 0, 10)
        btn_layout.setSpacing(10)

        self.btn_load_suggested = QPushButton("Load Suggested Values")
        self.btn_load_suggested.setMinimumHeight(35)
        self.btn_load_suggested.clicked.connect(self.load_suggested_values)

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setMinimumHeight(35)
        self.btn_clear_all.clicked.connect(self.clear_all)

        btn_layout.addWidget(self.btn_load_suggested)
        btn_layout.addWidget(self.btn_clear_all)
        self.form.addRow(btn_row)

    # ── Suggested values ──────────────────────────────────────────────────────

    def load_suggested_values(self):
        for key, val in SUGGESTED_VALUES.items():
            widget = getattr(self, key, None)
            if widget is None:
                continue
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.setValue(val)
            widget.setStyleSheet("")

        self._on_field_changed()

        if self.controller and self.controller.engine:
            self.controller.engine._log("Financial: Suggested values applied.")

    # ── Clear All ─────────────────────────────────────────────────────────────

    def clear_all(self):
        if not confirm_clear_all(self):
            return

        for entry in FINANCIAL_FIELDS:
            if isinstance(entry, Section):
                continue
            widget = getattr(self, entry.key, None)
            if widget is None:
                continue
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.setValue(widget.minimum())
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif hasattr(widget, "clear"):
                widget.clear()
            widget.setStyleSheet("")

        self._on_field_changed()

        if self.controller and self.controller.engine:
            self.controller.engine._log("Financial: All fields cleared.")

    # ── Validation ────────────────────────────────────────────────────────────

    def freeze(self, frozen: bool = True):
        freeze_form(FINANCIAL_FIELDS, self, frozen)
        freeze_widgets(frozen, self.btn_load_suggested, self.btn_clear_all)

    def clear_validation(self):
        clear_field_styles(FINANCIAL_FIELDS, self)

    def validate(self):
        return validate_form(FINANCIAL_FIELDS, self, warn_rules=FINANCIAL_WARN_RULES)

    def get_data(self) -> dict:
        return {"chunk": "financial_data", "data": self.get_data_dict()}


