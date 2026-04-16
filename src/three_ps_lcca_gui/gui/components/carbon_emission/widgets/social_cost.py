from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QWidget,
    QLabel,
    QFormLayout,
    QStackedWidget,
)
from PySide6.QtCore import Qt, QTimer

from ...base_widget import ScrollableForm
from ...utils.form_builder.form_definitions import FieldDef, Section
from ...utils.form_builder.form_builder import build_form
from ...utils.display_format import fmt, DECIMAL_PLACES
from ...utils.validation_helpers import freeze_form, freeze_widgets, confirm_clear_all

# ── Constants ─────────────────────────────────────────────────────────────────

CHUNK = "social_cost_data"
GLOBAL_CHUNK = "general_info"
from ...utils.doc_handler import make_doc_opener
_DOC_OPENER = make_doc_opener("carbon/social-cost")

_MODE_NITI = "NITI Aayog"
_MODE_RICKE = "K. Ricke et al. (Country-Level)"
_MODE_CUSTOM = "Custom / Manual Override"
# _SOURCES = [_MODE_NITI, _MODE_RICKE, _MODE_CUSTOM]
_SOURCES = [_MODE_RICKE, _MODE_CUSTOM]


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
NITI_FIELDS = [
    Section("Regional Valuation Adjustment"),
    FieldDef(
        "inr_to_local_rate",
        "INR Conversion Rate",
        "As NITI Aayog values are in INR, provide conversion to your global currency.",
        "float",
        options=(1e-6, 1e6, DECIMAL_PLACES),
        unit="(Currency/INR)",
    ),
]
RICKE_FIELDS = [
    Section("Climate & Socioeconomic Scenarios"),
    FieldDef(
        "usd_to_local_rate",
        "USD Conversion Rate",
        "Conversion rate for international scientific model outputs.",
        "float",
        options=(1e-6, 1e6, DECIMAL_PLACES),
        unit="(Currency/USD)",
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
CUSTOM_FIELDS = [
    FieldDef(
        "scc_value",
        "Social Cost of Carbon (SCC)",
        "The financial cost attributed to 1 kg of CO₂e emissions.",
        "float",
        options=(0.0, 1e6, DECIMAL_PLACES),
        unit="(Currency/kgCO₂e)",
    ),
]

# ── Widget ────────────────────────────────────────────────────────────────────


class SocialCost(ScrollableForm):
    """
    Economic valuation of carbon emissions using government or scientific models.
    
    References:
    - Ricke, K., Drouet, L., Caldeira, K. et al. Country-level social cost of carbon. 
      Nature Clim Change 8, 895–900 (2018). https://doi.org/10.1038/s41558-018-0282-y
    """
    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name=CHUNK)
        self.__suppress = 0
        self._project_currency = ""
        self._synced = False
        self._build_ui()

    # ── Suppression ───────────────────────────────────────────────────────────
    # Simple counter so nested suppression scopes dont clobber each other.
    # Stored as int; the bool property keeps all `if self._suppress_signals:` checks working.

    @property
    def _suppress_signals(self):
        return self.__suppress > 0

    @_suppress_signals.setter
    def _suppress_signals(self, val):
        # Accept True/False as increment/decrement so existing call-sites work unchanged.
        if val:
            self.__suppress += 1
        else:
            self.__suppress = max(0, self.__suppress - 1)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        f = self.form  # main QFormLayout

        # Header: methodology selector
        build_form(self, HEADER_FIELDS, _DOC_OPENER)
        self._field_map.pop("source", None)  # managed manually, not via base autosave
        self.source.currentIndexChanged.connect(self._on_mode_changed)

        # Effective SCC summary - padded container gives it breathing room
        # between the combo above and the stack below.
        _rc, self._result_lbl = self._padded_label(top=10, bottom=6)
        f.addRow(_rc)

        # Stack - one panel per methodology
        self._stack = QStackedWidget()
        f.addRow(self._stack)

        self._stack.addWidget(self._build_niti_panel())  # index 0
        self._stack.addWidget(self._build_ricke_panel())  # index 1
        self._stack.addWidget(self._build_custom_panel())  # index 2

        QTimer.singleShot(0, self._fit_stack)

        # Clear button
        self.btn_clear = QPushButton("Clear All")
        # self.btn_clear.setFixedWidth(120)
        self.btn_clear.setMinimumHeight(35)
        self.btn_clear.setMaximumHeight(35)
        self.btn_clear.clicked.connect(self.clear_all)
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 0)
        row.addWidget(self.btn_clear)
        f.addRow(row)

    def _make_panel_layout(self, parent):
        """Return a QFormLayout on `parent` matching the main form's style."""
        layout = QFormLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.setLabelAlignment(Qt.AlignRight)
        return layout

    def _padded_label(self, text="", top=8, bottom=8):
        """Wrap a QLabel in a slim container widget so vertical breathing room
        is controlled by explicit margins, not QFormLayout row stretch."""
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, top, 0, bottom)
        vbox.setSpacing(0)
        lbl = QLabel(text)
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(True)
        vbox.addWidget(lbl)
        return container, lbl

    def _find_row_for_widget(self, layout, target_widget):
        """Helper to safely and recursively locate the QFormLayout row index containing a specific widget."""
        def _contains(item, target):
            if not item:
                return False
            # Check direct widget match
            if item.widget() == target:
                return True
            # Check if it's deeply nested inside a wrapper widget
            if item.widget() and item.widget().isAncestorOf(target):
                return True
            # Check if it's nested inside a sub-layout
            lay = item.layout()
            if lay:
                for j in range(lay.count()):
                    if _contains(lay.itemAt(j), target):
                        return True
            return False

        # Scan every row in the form layout
        for i in range(layout.rowCount()):
            for role in (QFormLayout.FieldRole, QFormLayout.SpanningRole, QFormLayout.LabelRole):
                if _contains(layout.itemAt(i, role), target_widget):
                    return i
        return -1  # Not found

    def _build_niti_panel(self):
        w = QWidget()
        layout = self._make_panel_layout(w)

        _bc, _ = self._padded_label(
            f"Base Value: <b>{NITI_AAYOG_SCC_INR} INR/kgCO₂e</b> (NITI Aayog, 2023)",
            top=4,
            bottom=4,
        )
        layout.addRow(_bc)

        # Temporarily point self.form at this sub-layout so build_form adds rows here
        self.form, _saved = layout, self.form
        try:
            build_form(self, NITI_FIELDS, _DOC_OPENER)
            self._field_map.pop("inr_to_local_rate", None)
        finally:
            self.form = _saved

        self.inr_to_local_rate.valueChanged.connect(self._update_niti_result)

        # Track inr row for show/hide robustly
        self._niti_layout = layout
        self._inr_row = self._find_row_for_widget(layout, self.inr_to_local_rate)

        _nrc, self._niti_result_lbl = self._padded_label(top=6, bottom=4)
        layout.addRow(_nrc)
        return w

    def _build_ricke_panel(self):
        w = QWidget()
        layout = self._make_panel_layout(w)

        # Scientific Paper Reference
        _ref_c, _ref_lbl = self._padded_label(
            "<b>Reference:</b> Ricke, K., Drouet, L., Caldeira, K. et al. <i>Country-level social cost of carbon.</i> "
            "Nature Clim Change 8, 895-900 (2018). <a href='https://doi.org/10.1038/s41558-018-0282-y' style='color: palette(highlight);'>"
            "doi:10.1038/s41558-018-0282-y</a>",
            top=0,
            bottom=10,
        )
        _ref_lbl.setOpenExternalLinks(True)
        layout.addRow(_ref_c)

        self.form, _saved = layout, self.form
        try:
            build_form(self, RICKE_FIELDS, _DOC_OPENER)
            self._field_map.pop("usd_to_local_rate", None)
            self._field_map.pop("ssp_scenario", None)
            self._field_map.pop("rcp_scenario", None)
        finally:
            self.form = _saved

        self.usd_to_local_rate.valueChanged.connect(self._update_ricke_result)
        self.ssp_scenario.currentIndexChanged.connect(self._update_ricke_result)
        self.rcp_scenario.currentIndexChanged.connect(self._update_ricke_result)

        # Track usd row for show/hide robustly
        self._ricke_layout = layout
        self._usd_row = self._find_row_for_widget(layout, self.usd_to_local_rate)

        _rrc, self._ricke_result_lbl = self._padded_label(top=6, bottom=4)
        layout.addRow(_rrc)
        return w

    def _build_custom_panel(self):
        w = QWidget()
        layout = self._make_panel_layout(w)

        self.form, _saved = layout, self.form
        try:
            build_form(self, CUSTOM_FIELDS, _DOC_OPENER)
            self._field_map.pop("scc_value", None)
        finally:
            self.form = _saved

        self.scc_value.valueChanged.connect(self._update_custom_result)
        return w

    # ── Stack height ──────────────────────────────────────────────────────────

    def _fit_stack(self):
        """Lock the stack to exactly its current panel's natural height."""
        w = self._stack.currentWidget()
        if w:
            self._stack.setFixedHeight(max(w.sizeHint().height(), 0))
            self._stack.updateGeometry()

    # ── Mode switching ────────────────────────────────────────────────────────

    def _on_mode_changed(self, _idx=0):
        if self._suppress_signals:
            return
        mode = self.source.currentText()

        # Release the fixed height BEFORE the panel swap - otherwise Qt stretches
        # the new (shorter) panel's rows to fill the old panel's locked height.
        self._stack.setMaximumHeight(16777215)
        self._stack.setMinimumHeight(0)

        if _MODE_NITI in mode:
            self._stack.setCurrentIndex(0)
            self._update_niti_result()
        elif _MODE_RICKE in mode:
            self._stack.setCurrentIndex(1)
            self._update_ricke_result()
        else:
            self._stack.setCurrentIndex(2)
            self._update_custom_result()

        QTimer.singleShot(0, self._fit_stack)

    # ── Calculations ──────────────────────────────────────────────────────────

    def _toggle_currency_rows(self):
        cur = str(self._project_currency or "").strip().upper()
        
        # Hide INR Conversion input field if current project currency is INR
        if hasattr(self, '_inr_row') and self._inr_row >= 0:
            self._niti_layout.setRowVisible(self._inr_row, cur != "INR")
            
        # Hide USD Conversion input field if current project currency is USD
        if hasattr(self, '_usd_row') and self._usd_row >= 0:
            self._ricke_layout.setRowVisible(self._usd_row, cur != "USD")

    def _update_niti_result(self):
        if self._suppress_signals:
            return
        cur = str(self._project_currency or "INR").strip().upper()
        rate = self.inr_to_local_rate.value() if cur != "INR" else 1.0
        val = NITI_AAYOG_SCC_INR * rate
        
        if cur == "INR":
            self._niti_result_lbl.setText(
                f"NITI Aayog Base: <b>{fmt(NITI_AAYOG_SCC_INR)} INR/kgCO₂e</b>"
            )
        else:
            self._niti_result_lbl.setText(
                f"NITI Aayog Base: <b>{fmt(NITI_AAYOG_SCC_INR)} INR/kgCO₂e</b><br/>"
                f"Adjusted Local Cost: <b>{fmt(val)} {cur}/kgCO₂e</b>"
            )
            
        self._set_result(
            val,
            mode=_MODE_NITI,
            base_price=NITI_AAYOG_SCC_INR,
            base_unit="INR/kgCO₂e",
            conversion_rate=rate,
            rate_unit=f"{cur}/INR",
        )
        self._on_field_changed()

    def _update_ricke_result(self):
        if self._suppress_signals:
            return
        ssp = self.ssp_scenario.currentText()
        rcp = self.rcp_scenario.currentText()
        base = _RICKE_SCC_TABLE.get((ssp, rcp), 0.0)
        usd_rate = self.usd_to_local_rate.value()
        val = base * usd_rate
        cur = str(self._project_currency or "USD").strip().upper()
        
        if base == 0:
            self._ricke_result_lbl.setText(
                "<span style='color:red;'><b>Invalid combination</b> - this SSP/RCP pair "
                "does not exist in the Ricke et al. table. "
                "Valid pairs: SSP1+RCP2.6, SSP1+RCP4.5, SSP2+RCP4.5, "
                "SSP2+RCP6.0, SSP3+RCP8.5, SSP5+RCP8.5.</span>"
            )
            self._set_result(
                0.0,
                mode=_MODE_RICKE,
                base_price=0.0,
                base_unit="USD/kgCO₂e",
                conversion_rate=usd_rate,
                rate_unit=f"{cur}/USD",
            )
        else:
            if cur == "USD":
                self._ricke_result_lbl.setText(
                    f"Scenario Baseline: <b>${fmt(base)} USD/kgCO₂e</b>"
                )
            else:
                self._ricke_result_lbl.setText(
                    f"Scenario Baseline: <b>${fmt(base)} USD/kgCO₂e</b><br/>"
                    f"Adjusted Local Cost: <b>{fmt(val)} {cur}/kgCO₂e</b>"
                )
                
            self._set_result(
                val,
                mode=_MODE_RICKE,
                base_price=base,
                base_unit="USD/kgCO₂e",
                conversion_rate=usd_rate,
                rate_unit=f"{cur}/USD",
            )
        self._on_field_changed()

    def _update_custom_result(self):
        if self._suppress_signals:
            return
        val = self.scc_value.value()
        cur = self._project_currency or ""
        self._set_result(
            val,
            mode=_MODE_CUSTOM,
            base_price=val,
            base_unit=f"{cur}/kgCO₂e",
            conversion_rate=1.0,
            rate_unit="(direct entry)",
        )
        self._on_field_changed()

    def _set_result(self, value, mode=None, base_price=None, base_unit=None, conversion_rate=None, rate_unit=None):
        cur = self._project_currency or ""
        if mode is not None and base_price is not None and conversion_rate is not None:
            # Build the result label dynamically
            lines = [
                f"<b>Selected Mode:</b> {mode}",
                f"<b>Base Price:</b> {fmt(base_price)} {base_unit}"
            ]
            
            # Only add the Conversion Rate line if it's a cross-currency conversion
            if rate_unit not in ("INR/INR", "USD/USD"):
                lines.append(f"<b>Conversion Rate:</b> {fmt(conversion_rate)} {rate_unit}")
                
            lines.append(f"<b>Effective SCC:</b> {fmt(value)} {cur}/kgCO₂e")
            
            self._result_lbl.setText("<br/>".join(lines))
        else:
            self._result_lbl.setText(f"<b>Effective SCC: {fmt(value)} {cur}/kgCO₂e</b>")

    # ── Global sync ───────────────────────────────────────────────────────────

    def _sync_with_global_settings(self):
        if not self.controller or not self.controller.engine:
            return
        info = self.controller.engine.fetch_chunk(GLOBAL_CHUNK) or {}
        raw_cur = info.get("project_currency", "INR")
        self._project_currency = str(raw_cur).strip().upper() if raw_cur else "INR"
        rate_usd = float(info.get("currency_to_usd_rate", 1.0))

        self.usd_to_local_rate.setSuffix(f" {self._project_currency}/USD")
        self.inr_to_local_rate.setSuffix(f" {self._project_currency}/INR")
        self.scc_value.setSuffix(f" {self._project_currency}/kgCO₂e")

        self._suppress_signals = True
        if rate_usd > 0:
            self.usd_to_local_rate.setValue(1.0 / rate_usd)
        if self._project_currency == "INR":
            self.inr_to_local_rate.setValue(1.0)
        self._suppress_signals = False

        self._toggle_currency_rows()
        self._on_mode_changed()

    # ── Data ──────────────────────────────────────────────────────────────────

    def collect_data(self):
        cur = self._project_currency
        mode = self.source.currentText()

        niti_rate = 1.0 if cur == "INR" else self.inr_to_local_rate.value()
        niti_val = NITI_AAYOG_SCC_INR * niti_rate

        ssp = self.ssp_scenario.currentText()
        rcp = self.rcp_scenario.currentText()
        usd_base = _RICKE_SCC_TABLE.get((ssp, rcp), 0.0)
        usd_rate = self.usd_to_local_rate.value()
        ricke_val = usd_base * usd_rate

        custom_val = self.scc_value.value()

        final = (
            niti_val
            if _MODE_NITI in mode
            else ricke_val if _MODE_RICKE in mode else custom_val
        )

        return {
            "source": mode,
            "niti": {
                "base_value_inr": NITI_AAYOG_SCC_INR,
                "inr_to_local_rate": niti_rate,
                "cost_local": round(niti_val, DECIMAL_PLACES),
                "currency": cur,
            },
            "ricke": {
                "ssp": ssp,
                "rcp": rcp,
                "base_value_usd": usd_base,
                "usd_to_local_rate": usd_rate,
                "cost_local": round(ricke_val, DECIMAL_PLACES),
                "currency": cur,
            },
            "custom": {
                "entered_value": custom_val,
                "currency": cur,
                "unit": f"{cur}/kgCO₂e",
            },
            "result": {
                "selected_mode": mode,
                "base_price": (
                    NITI_AAYOG_SCC_INR if _MODE_NITI in mode
                    else usd_base if _MODE_RICKE in mode
                    else custom_val
                ),
                "base_price_unit": (
                    "INR/kgCO₂e" if _MODE_NITI in mode
                    else "USD/kgCO₂e" if _MODE_RICKE in mode
                    else f"{cur}/kgCO₂e"
                ),
                "conversion_rate": (
                    niti_rate if _MODE_NITI in mode
                    else usd_rate if _MODE_RICKE in mode
                    else 1.0
                ),
                "cost_of_carbon_local": round(final, DECIMAL_PLACES),
                "currency": cur,
                "unit": f"{cur}/kgCO₂e",
            },
        }

    # ── Base overrides ────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not self._synced:
            self._synced = True
            self._sync_with_global_settings()

    def _on_field_changed(self):
        if self._loading or self._suppress_signals:
            return
        if self.controller and self.controller.engine and self.chunk_name:
            self.controller.engine.stage_update(
                chunk_name=self.chunk_name, data=self.collect_data()
            )
        self.data_changed.emit()

    def get_data_dict(self):
        return self.collect_data()

    def refresh_from_engine(self):
        if not self.controller or not self.controller.engine:
            return
        if not self.controller.engine.is_active() or not self.chunk_name:
            return
        data = self.controller.get_chunk(self.chunk_name)
        if not data or data == self._loaded_data:
            self._sync_with_global_settings()
            return
        self._loaded_data = data
        self.load_data_dict(data)
        self._sync_with_global_settings()

    def load_data_dict(self, data):
        if not data:
            return
        self._loading = True
        try:
            self.source.blockSignals(True)
            idx = self.source.findText(data.get("source", _MODE_NITI))
            self.source.setCurrentIndex(idx if idx >= 0 else 0)
            self.source.blockSignals(False)

            niti = data.get("niti", {})
            self.inr_to_local_rate.blockSignals(True)
            self.inr_to_local_rate.setValue(float(niti.get("inr_to_local_rate", 1.0)))
            self.inr_to_local_rate.blockSignals(False)

            ricke = data.get("ricke", {})
            self.usd_to_local_rate.blockSignals(True)
            self.usd_to_local_rate.setValue(float(ricke.get("usd_to_local_rate", 1.0)))
            self.usd_to_local_rate.blockSignals(False)

            self.ssp_scenario.blockSignals(True)
            i = self.ssp_scenario.findText(ricke.get("ssp", _SSP_OPTIONS[0]))
            self.ssp_scenario.setCurrentIndex(i if i >= 0 else 0)
            self.ssp_scenario.blockSignals(False)

            self.rcp_scenario.blockSignals(True)
            i = self.rcp_scenario.findText(ricke.get("rcp", _RCP_OPTIONS[0]))
            self.rcp_scenario.setCurrentIndex(i if i >= 0 else 0)
            self.rcp_scenario.blockSignals(False)

            custom = data.get("custom", {})
            self.scc_value.blockSignals(True)
            self.scc_value.setValue(float(custom.get("entered_value", 0.0)))
            self.scc_value.blockSignals(False)
        finally:
            self._loading = False

        # Sync stack to loaded mode - suppressed so it doesn't trigger a save
        self._suppress_signals = True
        self._on_mode_changed()
        self._suppress_signals = False

    def validate(self) -> dict:
        data = self.collect_data()
        errors = []
        warnings = []
        mode = data.get("source", "")

        if _MODE_RICKE in mode:
            ssp = data.get("ricke", {}).get("ssp", "")
            rcp = data.get("ricke", {}).get("rcp", "")
            if (ssp, rcp) not in _RICKE_SCC_TABLE:
                errors.append(
                    f"Invalid SSP/RCP combination: '{ssp}' + '{rcp}' does not exist "
                    f"in the Ricke et al. table. "
                    f"Valid pairs: "
                    + ", ".join(f"{s} + {r}" for s, r in _RICKE_SCC_TABLE)
                    + "."
                )
            elif data.get("ricke", {}).get("usd_to_local_rate", 0.0) == 0.0:
                warnings.append(
                    "USD Conversion Rate is 0 - the effective SCC will be 0."
                )
        elif _MODE_NITI in mode:
            cur = data.get("niti", {}).get("currency", "INR")
            if cur != "INR" and data.get("niti", {}).get("inr_to_local_rate", 0.0) == 0.0:
                warnings.append(
                    "INR Conversion Rate is 0 - the effective SCC will be 0."
                )
        else:
            scc = data.get("result", {}).get("cost_of_carbon_local", 0.0)
            if scc == 0.0:
                if _MODE_CUSTOM in mode:
                    warnings.append(
                        "Social Cost of Carbon is 0 - enter a custom SCC value."
                    )
                else:
                    warnings.append("Social Cost of Carbon is 0.")

        return {"errors": errors, "warnings": warnings}

    def freeze(self, frozen: bool = True):
        freeze_widgets(frozen, self.btn_clear)
        freeze_form(
            HEADER_FIELDS + NITI_FIELDS + RICKE_FIELDS + CUSTOM_FIELDS,
            self,
            frozen,
        )

    def clear_all(self):
        if not confirm_clear_all(self):
            return

        self._suppress_signals = True
        self.source.setCurrentIndex(0)
        self.inr_to_local_rate.setValue(1.0)
        self.usd_to_local_rate.setValue(1.0)
        self.ssp_scenario.setCurrentIndex(0)
        self.rcp_scenario.setCurrentIndex(0)
        self.scc_value.setValue(0.0)
        self._suppress_signals = False
        self._on_mode_changed()
        self._on_field_changed()

    def get_data(self) -> dict:
        return {"chunk": CHUNK, "data": self.get_data_dict()}


