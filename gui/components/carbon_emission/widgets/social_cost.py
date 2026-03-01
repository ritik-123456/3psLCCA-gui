from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QWidget,
    QLabel,
    QFormLayout,
    QStackedWidget,
    QSizePolicy,
)
from PySide6.QtCore import Qt

from ...base_widget import ScrollableForm
from ...utils.form_builder.form_definitions import FieldDef, Section
from ...utils.form_builder.form_builder import build_form
from ...utils.remarks_editor import RemarksEditor

# ── Constants & Options ───────────────────────────────────────────────────────

CHUNK = "social_cost_data"
GLOBAL_CHUNK = "general_info"
BASE_DOCS_URL = "https://yourdocs.com/carbon/social-cost/"

_MODE_NITI = "NITI Aayog"
_MODE_RICKE = "K. Ricke et al. (Country-Level)"
_MODE_CUSTOM = "Custom / Manual Override"
_SOURCES = [_MODE_NITI, _MODE_RICKE, _MODE_CUSTOM]

_SSP_OPTIONS = [
    "SSP1 (Sustainability)",
    "SSP2 (Middle of the Road)",
    "SSP3 (Regional Rivalry)",
    "SSP4 (Inequality)",
    "SSP5 (Fossil-fueled Development)",
]
_RCP_OPTIONS = [
    "RCP 2.6 (Low Warming)",
    "RCP 4.5 (Intermediate)",
    "RCP 6.0 (High)",
    "RCP 8.5 (Extreme)",
]

NITI_AAYOG_SCC_INR = 6.3936

_RICKE_SCC_TABLE = {
    ("SSP1 (Sustainability)", "RCP 2.6 (Low Warming)"): 0.085,
    ("SSP1 (Sustainability)", "RCP 4.5 (Intermediate)"): 0.095,
    ("SSP2 (Middle of the Road)", "RCP 4.5 (Intermediate)"): 0.110,
    ("SSP2 (Middle of the Road)", "RCP 6.0 (High)"): 0.135,
    ("SSP3 (Regional Rivalry)", "RCP 8.5 (Extreme)"): 0.185,
    ("SSP5 (Fossil-fueled Development)", "RCP 8.5 (Extreme)"): 0.210,
}

# ── Field Definitions ─────────────────────────────────────────────────────────

HEADER_FIELDS = [
    Section("Economic Valuation Methodology"),
    FieldDef(
        "source",
        "Cost Methodology",
        "Choose between government standards or peer-reviewed scientific models.",
        "combo",
        options=_SOURCES,
        doc_slug="scc-methodology",
    ),
]

VALUE_FIELDS = [
    FieldDef(
        "scc_value",
        "Social Cost of Carbon (SCC)",
        "The financial cost attributed to 1 kg of CO2e emissions.",
        "float",
        options=(0.0, 1e6, 6),
        unit="Currency/kgCO2e",
    ),
]

NITI_CONVERSION_FIELDS = [
    Section("Regional Valuation Adjustment"),
    FieldDef(
        "inr_to_local_rate",
        "INR Conversion Rate",
        "As NITI Aayog values are in INR, provide conversion to your global currency.",
        "float",
        options=(1e-6, 1e6, 6),
        unit="Currency/INR",
    ),
]

SCIENTIFIC_FIELDS = [
    Section("Climate & Socioeconomic Scenarios"),
    FieldDef(
        "usd_to_local_rate",
        "USD Conversion Rate",
        "Conversion rate for international scientific model outputs.",
        "float",
        options=(1e-6, 1e6, 6),
        unit="Currency/USD",
    ),
    FieldDef(
        "ssp_scenario",
        "Socioeconomic Pathway (SSP)",
        "Assumptions on future population, GDP, and energy use.",
        "combo",
        options=_SSP_OPTIONS,
    ),
    FieldDef(
        "rcp_scenario",
        "Climate Trajectory (RCP)",
        "Representative Concentration Pathway for greenhouse gases.",
        "combo",
        options=_RCP_OPTIONS,
    ),
]

# ── SocialCost Class ──────────────────────────────────────────────────────────


class SocialCost(ScrollableForm):
    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name=CHUNK)
        self._suppress_signals = False
        self._project_currency = ""
        self._inr_section = None
        self._build_ui()

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        main_form = self.form

        # ── Methodology selector ──────────────────────────────────────────────
        build_form(self, HEADER_FIELDS, BASE_DOCS_URL)
        self._field_map.pop("source", None)  # prevent base save loop partial write
        self.source.currentIndexChanged.connect(self._on_source_mode_changed)

        # ── Result summary label ──────────────────────────────────────────────
        self._result_label = QLabel()
        self._result_label.setWordWrap(True)
        self._result_label.setTextFormat(Qt.RichText)
        main_form.addRow(self._result_label)

        # ── Stack: one panel per methodology ─────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # ── Panel 0: NITI Aayog ───────────────────────────────────────────────
        niti_widget = QWidget()
        niti_layout = QFormLayout(niti_widget)
        niti_layout.setContentsMargins(0, 0, 0, 0)
        niti_layout.setSpacing(8)
        niti_layout.setLabelAlignment(Qt.AlignRight)

        self._niti_base_label = QLabel(
            f"Base Value: <b>{NITI_AAYOG_SCC_INR} INR/kgCO2e</b> (NITI Aayog, 2023)"
        )
        self._niti_base_label.setTextFormat(Qt.RichText)
        niti_layout.addRow(self._niti_base_label)

        _temp = self.form
        self.form = niti_layout
        build_form(self, NITI_CONVERSION_FIELDS, BASE_DOCS_URL)
        self._field_map.pop("inr_to_local_rate", None)
        self.form = _temp

        self.inr_to_local_rate.valueChanged.connect(self._update_niti_result)

        # Store the section container so we can show/hide it cleanly
        self._inr_section = self.inr_to_local_rate.parentWidget()

        self._niti_result_lbl = QLabel()
        self._niti_result_lbl.setTextFormat(Qt.RichText)
        self._niti_result_lbl.setWordWrap(True)
        niti_layout.addRow(self._niti_result_lbl)

        self._stack.addWidget(niti_widget)  # index 0

        # ── Panel 1: Ricke et al. ─────────────────────────────────────────────
        ricke_widget = QWidget()
        ricke_layout = QFormLayout(ricke_widget)
        ricke_layout.setContentsMargins(0, 0, 0, 0)
        ricke_layout.setSpacing(8)
        ricke_layout.setLabelAlignment(Qt.AlignRight)

        _temp = self.form
        self.form = ricke_layout
        build_form(self, SCIENTIFIC_FIELDS, BASE_DOCS_URL)
        self._field_map.pop("usd_to_local_rate", None)
        self._field_map.pop("ssp_scenario", None)
        self._field_map.pop("rcp_scenario", None)
        self.form = _temp

        self.usd_to_local_rate.valueChanged.connect(self._update_scientific_result)
        self.ssp_scenario.currentIndexChanged.connect(self._update_scientific_result)
        self.rcp_scenario.currentIndexChanged.connect(self._update_scientific_result)

        self._scientific_result_lbl = QLabel()
        self._scientific_result_lbl.setTextFormat(Qt.RichText)
        self._scientific_result_lbl.setWordWrap(True)
        ricke_layout.addRow(self._scientific_result_lbl)

        self._stack.addWidget(ricke_widget)  # index 1

        # ── Panel 2: Custom ───────────────────────────────────────────────────
        custom_widget = QWidget()
        custom_layout = QFormLayout(custom_widget)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(8)
        custom_layout.setLabelAlignment(Qt.AlignRight)

        _temp = self.form
        self.form = custom_layout
        build_form(self, VALUE_FIELDS, BASE_DOCS_URL)
        self._field_map.pop("scc_value", None)
        self.form = _temp

        self.scc_value.valueChanged.connect(self._on_field_changed)

        self._stack.addWidget(custom_widget)  # index 2

        main_form.addRow(self._stack)
        self._shrink_stack()  # set initial height to sizeHint

        # ── Remarks ───────────────────────────────────────────────────────────
        # self._remarks = RemarksEditor(
        #     title="Remarks / Notes", on_change=self._on_field_changed
        # )
        # main_form.addRow(self._remarks)

        # ── Clear All ─────────────────────────────────────────────────────────
        btn_clear = QPushButton("Clear All")
        btn_clear.setMinimumHeight(35)
        btn_clear.setFixedWidth(120)
        btn_clear.clicked.connect(self.clear_all)
        btn_clear.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        btn_widget = QWidget()
        btn_widget.setLayout(btn_row)
        btn_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        main_form.addRow(btn_widget)

    # ── Stack sizing ──────────────────────────────────────────────────────────

    def _shrink_stack(self):
        """Cap the stack height to its current panel's sizeHint so the scroll
        area never leaves blank space below the content."""
        w = self._stack.currentWidget()
        if w is None:
            return
        hint = w.sizeHint().height()
        self._stack.setMaximumHeight(max(hint, 0))
        self._stack.updateGeometry()

    # ── showEvent ─────────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_with_global_settings()

    # ── Source Mode ───────────────────────────────────────────────────────────

    def _on_source_mode_changed(self, _idx: int = 0):
        if self._suppress_signals:
            return
        mode = self.source.currentText()
        if _MODE_NITI in mode:
            self._stack.setCurrentIndex(0)
            self._update_niti_result()
        elif _MODE_RICKE in mode:
            self._stack.setCurrentIndex(1)
            self._update_scientific_result()
        else:
            self._stack.setCurrentIndex(2)
        self._shrink_stack()
        self._on_field_changed()

    # ── Result Calculations ───────────────────────────────────────────────────

    def _toggle_inr_field(self):
        """Hide INR conversion row when project currency is already INR."""
        if self._inr_section:
            self._inr_section.setVisible(self._project_currency != "INR")

    def _update_niti_result(self):
        if self._suppress_signals:
            return
        currency = self._project_currency or "INR"
        rate = self.inr_to_local_rate.value() if currency != "INR" else 1.0
        local_value = NITI_AAYOG_SCC_INR * rate
        self._niti_result_lbl.setText(
            f"NITI Aayog Base: <b>{NITI_AAYOG_SCC_INR} INR/kgCO2e</b><br/>"
            f"Adjusted Local Cost: <b>{local_value:.6f} {currency}/kgCO2e</b>"
        )
        self._update_result_label(local_value)
        self._on_field_changed()

    def _update_scientific_result(self):
        if self._suppress_signals:
            return
        ssp = self.ssp_scenario.currentText()
        rcp = self.rcp_scenario.currentText()
        usd_base = _RICKE_SCC_TABLE.get((ssp, rcp), 0.0)
        rate = self.usd_to_local_rate.value()
        local_value = usd_base * rate
        currency = self._project_currency or "USD"

        if usd_base == 0:
            self._scientific_result_lbl.setText(
                "<i>Scenario combination not found in Ricke et al. table.</i>"
            )
            self._update_result_label(0.0)
        else:
            self._scientific_result_lbl.setText(
                f"Scenario Baseline: <b>${usd_base:.4f} USD/kg</b><br/>"
                f"Adjusted Local Cost: <b>{local_value:.6f} {currency}/kgCO2e</b>"
            )
            self._update_result_label(local_value)
        self._on_field_changed()

    def _update_result_label(self, value: float):
        currency = self._project_currency or ""
        self._result_label.setText(
            f"<b>Effective SCC: {value:.6f} {currency}/kgCO2e</b>"
        )

    # ── Global Sync ───────────────────────────────────────────────────────────

    def _sync_with_global_settings(self):
        if not self.controller or not self.controller.engine:
            return

        global_info = self.controller.engine.fetch_chunk(GLOBAL_CHUNK) or {}
        self._project_currency = global_info.get("currency", "INR")
        rate_to_usd = float(global_info.get("currency_to_usd_rate", 1.0))

        # Update unit suffixes
        self.usd_to_local_rate.setSuffix(f" {self._project_currency}/USD")
        self.inr_to_local_rate.setSuffix(f" {self._project_currency}/INR")
        self.scc_value.setSuffix(f" {self._project_currency}/kgCO2e")

        # Auto-fill conversion rates from global info
        if rate_to_usd > 0:
            self._suppress_signals = True
            self.usd_to_local_rate.setValue(1.0 / rate_to_usd)
            self._suppress_signals = False

        if self._project_currency == "INR":
            self._suppress_signals = True
            self.inr_to_local_rate.setValue(1.0)
            self._suppress_signals = False

        # Show/hide INR conversion field based on currency
        self._toggle_inr_field()

        # Re-trigger current mode's calculation with updated rates
        self._on_source_mode_changed()

    # ── Data Collection ───────────────────────────────────────────────────────

    def collect_data(self) -> dict:
        currency = self._project_currency
        mode = self.source.currentText()

        # NITI
        niti_rate = 1.0 if currency == "INR" else self.inr_to_local_rate.value()
        niti_local_value = NITI_AAYOG_SCC_INR * niti_rate
        niti_data = {
            "base_value_inr": NITI_AAYOG_SCC_INR,
            "inr_to_local_rate": niti_rate,
            "cost_local": round(niti_local_value, 6),
            "currency": currency,
        }

        # Ricke
        ssp = self.ssp_scenario.currentText()
        rcp = self.rcp_scenario.currentText()
        usd_base = _RICKE_SCC_TABLE.get((ssp, rcp), 0.0)
        usd_to_local = self.usd_to_local_rate.value()
        ricke_local_value = usd_base * usd_to_local
        ricke_data = {
            "ssp": ssp,
            "rcp": rcp,
            "base_value_usd": usd_base,
            "usd_to_local_rate": usd_to_local,
            "cost_local": round(ricke_local_value, 6),
            "currency": currency,
        }

        # Custom
        custom_value = self.scc_value.value()
        custom_data = {
            "entered_value": custom_value,
            "currency": currency,
            "unit": f"{currency}/kgCO2e",
        }

        # Final result
        if _MODE_NITI in mode:
            final_value = niti_local_value
        elif _MODE_RICKE in mode:
            final_value = ricke_local_value
        else:
            final_value = custom_value

        result_data = {
            "methodology": mode,
            "cost_of_carbon_local": round(final_value, 6),
            "currency": currency,
            "unit": f"{currency}/kgCO2e",
            "scientific_params": {
                "ssp": ssp,
                "rcp": rcp,
                "usd_to_local_rate": usd_to_local,
            },
        }

        return {
            "source": mode,
            "niti": niti_data,
            "ricke": ricke_data,
            "custom": custom_data,
            "result": result_data,
            # "remarks": self._remarks.to_html(),
        }

    # ── Base Overrides ────────────────────────────────────────────────────────

    def _on_field_changed(self):
        """Override base — saves full collect_data(), not just _field_map."""
        if self._loading:
            return
        if self.controller and self.controller.engine and self.chunk_name:
            self.controller.engine.stage_update(
                chunk_name=self.chunk_name, data=self.collect_data()
            )
        self.data_changed.emit()

    def get_data_dict(self) -> dict:
        return self.collect_data()

    def load_data_dict(self, data: dict):
        self._load_own_data(data)

    def refresh_from_engine(self):
        if not self.controller or not self.controller.engine:
            return
        if not self.controller.engine.is_active() or not self.chunk_name:
            return
        data = self.controller.engine.fetch_chunk(self.chunk_name)
        if data:
            self._load_own_data(data)
        self._sync_with_global_settings()

    # ── Data Loading ──────────────────────────────────────────────────────────

    def _load_own_data(self, data: dict):
        if not data:
            return
        self._suppress_signals = True
        try:
            # Source/mode
            self.source.blockSignals(True)
            idx = self.source.findText(data.get("source", _MODE_NITI))
            self.source.setCurrentIndex(idx if idx >= 0 else 0)
            self.source.blockSignals(False)

            # NITI fields
            niti = data.get("niti", {})
            self.inr_to_local_rate.blockSignals(True)
            self.inr_to_local_rate.setValue(float(niti.get("inr_to_local_rate", 1.0)))
            self.inr_to_local_rate.blockSignals(False)

            # Ricke fields
            ricke = data.get("ricke", {})
            self.usd_to_local_rate.blockSignals(True)
            self.usd_to_local_rate.setValue(float(ricke.get("usd_to_local_rate", 1.0)))
            self.usd_to_local_rate.blockSignals(False)

            self.ssp_scenario.blockSignals(True)
            ssp_idx = self.ssp_scenario.findText(ricke.get("ssp", _SSP_OPTIONS[0]))
            self.ssp_scenario.setCurrentIndex(ssp_idx if ssp_idx >= 0 else 0)
            self.ssp_scenario.blockSignals(False)

            self.rcp_scenario.blockSignals(True)
            rcp_idx = self.rcp_scenario.findText(ricke.get("rcp", _RCP_OPTIONS[0]))
            self.rcp_scenario.setCurrentIndex(rcp_idx if rcp_idx >= 0 else 0)
            self.rcp_scenario.blockSignals(False)

            # Custom
            custom = data.get("custom", {})
            self.scc_value.blockSignals(True)
            self.scc_value.setValue(float(custom.get("entered_value", 0.0)))
            self.scc_value.blockSignals(False)

            # Remarks
            # self._remarks.from_html(data.get("remarks", ""))

        finally:
            self._suppress_signals = False

        # Sync stack and recalculate for the loaded mode
        self._on_source_mode_changed()

    # ── Clear All ─────────────────────────────────────────────────────────────

    def clear_all(self):
        self._suppress_signals = True
        self.source.setCurrentIndex(0)
        self.inr_to_local_rate.setValue(1.0)
        self.usd_to_local_rate.setValue(1.0)
        self.ssp_scenario.setCurrentIndex(0)
        self.rcp_scenario.setCurrentIndex(0)
        self.scc_value.setValue(0.0)
        # self._remarks.clear_content()
        self._suppress_signals = False
        self._on_source_mode_changed()
        self._on_field_changed()
