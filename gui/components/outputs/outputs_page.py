"""
gui/components/outputs/outputs_page.py
"""

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from gui.themes import get_token

from gui.components.base_widget import ScrollableForm
from gui.components.utils.form_builder.form_definitions import (
    FieldDef,
    ValidationStatus,
)
from gui.components.utils.form_builder.form_builder import build_form
from gui.components.utils.validation_helpers import (
    clear_field_styles,
    freeze_form,
    validate_form,
)
from .lcc_plot import LCCBreakdownTable, LCCChartWidget, LCCDetailsTable
from .Pie import LCCPieWidget


from three_ps_lcca_core.inputs.input import (
    InputMetaData,
    GeneralParameters,
    TrafficAndRoadData,
    VehicleData,
    VehicleMetaData,
    AccidentSeverityDistribution,
    AdditionalInputs,
    MaintenanceAndStageParameters,
    UseStageCost,
    Routine,
    RoutineInspection,
    RoutineMaintenance,
    Major,
    MajorInspection,
    MajorRepair,
    ReplacementCost,
    EndOfLifeStageCosts,
    DemolitionDisposal,
)
from three_ps_lcca_core.inputs.input_global import (
    InputGlobalMetaData,
    DailyRoadUserCost,
    TotalCarbonEmission,
)
from three_ps_lcca_core.core.main import run_full_lcc_analysis
from three_ps_lcca_core.inputs.wpi import WPIMetaData


CHUNK = "outputs_data"
CHUNK_AP = "analysis_period"

OUTPUTS_FIELDS = [
    FieldDef(
        "analysis_period",
        "Analysis Period",
        "Total time horizon used for life cycle cost evaluation.",
        "int",
        options=(0, 999),
        required=True,
        unit="(years)",
        doc_slug="analysis-period",
        default=0,
    ),
]

OUTPUTS_WARN_RULES = {
    "analysis_period": (
        None,
        500,
        None,
        "Analysis period exceeds 500 years — please verify",
    ),
}
DEBUG = False


def _dbg(*args):
    if DEBUG:
        import inspect

        caller = inspect.stack()[1].function
        print(f"[OUTPUTS DEBUG | {caller}]", *args)


class _LCCAWorker(QObject):
    """Runs the heavy LCCA calculation on a background thread.

    Signals
    -------
    finished(results)   - emitted with the raw results dict on success.
    errored(exc, tb)    - emitted with the exception and formatted traceback on failure.
    """

    finished = Signal(object)  # results dict
    errored = Signal(object, str)  # (Exception, traceback_str)

    def __init__(self, page: "OutputsPage", all_data: dict):
        super().__init__()
        self._page = page
        self._all_data = all_data

    def run(self):
        try:
            all_data = self._all_data
            page = self._page

            _dbg("Worker: calling _prepare_data_object …")
            is_global, data_object = page._prepare_data_object(all_data)
            _dbg(
                f"Worker: is_global={is_global}  data_object={type(data_object).__name__}"
            )

            wpi_metadata = None
            if not is_global:
                _dbg("Worker: calling _prepare_wpi_object …")
                wpi_metadata = page._prepare_wpi_object(all_data)

            _dbg("Worker: calling _prepare_life_cycle_construction_cost …")
            life_cycle_construction_cost_breakdown = (
                page._prepare_life_cycle_construction_cost(all_data)
            )

            _dbg("Worker: calling run_full_lcc_analysis …")
            

            results = run_full_lcc_analysis(
                data_object,
                life_cycle_construction_cost_breakdown,
                wpi=wpi_metadata,
                debug=True,
            )
            _dbg(
                f"Worker: run_full_lcc_analysis returned: {list(results.keys()) if isinstance(results, dict) else type(results).__name__}"
            )

            # Stash data on the page so _show_calculation_success can reference it.
            # Safe because these writes happen before the finished signal is processed
            # by the main thread (Qt queued connection orders them correctly).
            page._last_all_data = all_data
            page._last_lcc_breakdown = life_cycle_construction_cost_breakdown

            self.finished.emit(results)

        except Exception as exc:
            import traceback as _tb

            tb_str = _tb.format_exc()
            _dbg(f"Worker ERROR: {type(exc).__name__}: {exc}\n{tb_str}")
            self.errored.emit(exc, tb_str)


class OutputsPage(ScrollableForm):

    navigate_requested = Signal(str)
    calculation_completed = Signal()  # emitted after a successful calculation
    validate_requested = (
        Signal()
    )  # emitted when user clicks Validate — project_window handles it

    def __init__(self, controller=None):
        super().__init__(controller=controller, chunk_name=CHUNK)
        self._pages = {}
        self._has_results = False  # True while calculation results are displayed
        self._calc_thread = None  # QThread - kept alive during calculation
        self._calc_worker = None  # _LCCAWorker
        self._timeout_timer = (
            None  # QTimer - fires if calculation exceeds CALC_TIMEOUT_MS
        )
        self._elapsed_timer = (
            None  # QTimer - ticks every second to update elapsed label
        )
        self._elapsed_secs = 0  # seconds since calculation started
        self._build_ui()

    def _build_ui(self):
        f = self.form
        header = QLabel("Outputs")
        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(13)
        header.setFont(bold)
        f.addRow(header)

        # ── Analysis Period ───────────────────────────────────────────────
        self.required_keys = build_form(self, OUTPUTS_FIELDS, None)

        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 8, 0, 8)

        self.btn_calculate = QPushButton("Validate  ▶")
        self.btn_calculate.setMinimumHeight(38)
        self.btn_calculate.setFixedWidth(160)
        self.btn_calculate.clicked.connect(self.validate_requested.emit)
        btn_layout.addWidget(self.btn_calculate)
        btn_layout.addStretch()
        f.addRow(btn_row)

        self._status_widget = QWidget()
        self._status_layout = QVBoxLayout(self._status_widget)
        self._status_layout.setContentsMargins(0, 0, 0, 0)
        f.addRow(self._status_widget)

        self._show_idle()

    # ── Status area ───────────────────────────────────────────────────────────

    def _clear_status(self):
        while self._status_layout.count():
            item = self._status_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)

    def _show_idle(self):
        self._clear_status()
        note = QLabel("Press Calculate to validate all pages.")
        note.setStyleSheet("color: gray; font-style: italic;")
        self._status_layout.addWidget(note)

    # ── Calculation timeout constant ──────────────────────────────────────────
    CALC_TIMEOUT_MS = 30_000  # 30 seconds

    def _show_calculating(self):
        """Show an animated progress bar, elapsed-time counter, and disable the button."""
        self._clear_status()
        self.btn_calculate.setEnabled(False)

        # ── Container ──────────────────────────────────────────────────────
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(6)

        # ── Header row: spinner label + elapsed counter ────────────────────
        h_row = QWidget()
        h = QHBoxLayout(h_row)
        h.setContentsMargins(0, 0, 0, 0)

        spin_lbl = QLabel("⏳  Calculating…")
        spin_lbl.setStyleSheet("color: #555; font-style: italic;")
        h.addWidget(spin_lbl)
        h.addStretch()

        self._elapsed_label = QLabel("0s / 30s")
        self._elapsed_label.setStyleSheet("color: #888; font-size: 11px;")
        h.addWidget(self._elapsed_label)
        v.addWidget(h_row)

        # ── Marquee progress bar ───────────────────────────────────────────
        bar = QProgressBar()
        bar.setRange(0, 0)  # range(0,0) = indeterminate / marquee
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet(
            """
            QProgressBar {
                border: none;
                border-radius: 4px;
                background: #e9ecef;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4dabf7, stop:1 #228be6
                );
            }
        """
        )
        v.addWidget(bar)

        # ── Timeout countdown bar (full width → shrinks to zero in 30 s) ──
        self._countdown_bar = QProgressBar()
        self._countdown_bar.setRange(0, self.CALC_TIMEOUT_MS // 1000)
        self._countdown_bar.setValue(self.CALC_TIMEOUT_MS // 1000)
        self._countdown_bar.setTextVisible(False)
        self._countdown_bar.setFixedHeight(4)
        self._countdown_bar.setStyleSheet(
            """
            QProgressBar {
                border: none;
                border-radius: 2px;
                background: #e9ecef;
            }
            QProgressBar::chunk {
                border-radius: 2px;
                background: #fab005;
            }
        """
        )
        v.addWidget(self._countdown_bar)

        timeout_lbl = QLabel(
            f"Timeout in {self.CALC_TIMEOUT_MS // 1000}s if not complete."
        )
        timeout_lbl.setStyleSheet("color: #aaa; font-size: 10px;")
        v.addWidget(timeout_lbl)

        self._status_layout.addWidget(container)
        self._status_layout.addStretch()

        # ── Elapsed-time ticker (every 1 s) ───────────────────────────────
        self._elapsed_secs = 0
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1_000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start()

        # ── Hard timeout (30 s) ───────────────────────────────────────────
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.setInterval(self.CALC_TIMEOUT_MS)
        self._timeout_timer.timeout.connect(self._on_calc_timeout)
        self._timeout_timer.start()

    def _tick_elapsed(self):
        """Called every second to update the elapsed label and countdown bar."""
        self._elapsed_secs += 1
        remaining = max(0, self.CALC_TIMEOUT_MS // 1000 - self._elapsed_secs)
        if hasattr(self, "_elapsed_label"):
            self._elapsed_label.setText(
                f"{self._elapsed_secs}s / {self.CALC_TIMEOUT_MS // 1000}s"
            )
        if hasattr(self, "_countdown_bar"):
            self._countdown_bar.setValue(remaining)

    def _stop_timers(self):
        """Cancel both the timeout and elapsed timers."""
        if self._timeout_timer is not None:
            self._timeout_timer.stop()
            self._timeout_timer.deleteLater()
            self._timeout_timer = None
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer.deleteLater()
            self._elapsed_timer = None

    def _on_calc_timeout(self):
        """Called when the 30 s timeout fires — terminate the thread and show error."""
        _dbg(
            "=== _on_calc_timeout: calculation exceeded timeout, terminating thread ==="
        )
        self._stop_timers()

        if self._calc_thread and self._calc_thread.isRunning():
            self._calc_thread.terminate()  # forceful stop
            self._calc_thread.wait(2000)  # give it 2 s to die cleanly

        self.btn_calculate.setEnabled(True)
        timeout_exc = TimeoutError(
            f"Calculation did not complete within {self.CALC_TIMEOUT_MS // 1000} seconds.\n"
            "The thread was forcefully terminated.\n"
            "Check your input data for unusually large values, or contact support."
        )
        self._show_calculation_error(timeout_exc, "")

    def show_results(self, all_errors: dict, all_warnings: dict):
        """Show errors and warnings together. Proceed button only when no errors."""
        self._clear_status()

        if all_errors:
            banner = QGroupBox()
            banner.setStyleSheet(
                f"QGroupBox {{ border: 2px solid {get_token("danger")}; padding: 8px; }}"
            )
            layout = QVBoxLayout(banner)
            title = QLabel("🛑  Calculation Blocked — Fix the errors below to continue.")
            title.setStyleSheet(f"color: {get_token('danger')}; font-weight: {get_token('weight-bold')};")
            layout.addWidget(title)
            self._status_layout.addWidget(banner)
            self._status_layout.addSpacing(10)

            for page, issues in all_errors.items():
                self._status_layout.addWidget(self._create_card(page, issues, "❌"))

        if all_warnings:
            if all_errors:
                self._status_layout.addSpacing(12)
            banner = QGroupBox()
            banner.setStyleSheet(
                f"QGroupBox {{ border: 2px solid {get_token('warning')}; padding: 8px; }}"
            )
            layout = QVBoxLayout(banner)
            label = (
                "⚠️  Warnings — fix errors above before proceeding."
                if all_errors
                else "⚠️  Warnings — Data looks unusual but you can proceed."
            )
            title = QLabel(label)
            title.setStyleSheet(f"color: {get_token('warning')}; font-weight: {get_token('weight-bold')};")
            layout.addWidget(title)
            self._status_layout.addWidget(banner)
            self._status_layout.addSpacing(10)

            for page, issues in all_warnings.items():
                self._status_layout.addWidget(self._create_card(page, issues, "🟡"))

        if not all_errors and all_warnings:
            run_btn = QPushButton("Proceed with Calculation ▶")
            run_btn.setMinimumHeight(35)
            run_btn.clicked.connect(self._on_proceed)
            self._status_layout.addWidget(run_btn)

        self._status_layout.addStretch()
        self._save_state("issues", {"errors": all_errors, "warnings": all_warnings})

    def show_success(self):
        self._clear_status()
        banner = QGroupBox()
        banner.setStyleSheet("QGroupBox { border: 2px solid #198754; padding: 8px; }")
        layout = QVBoxLayout(banner)
        layout.addWidget(QLabel("✅  All checks passed — Ready to calculate."))
        self._status_layout.addWidget(banner)
        self._status_layout.addStretch()
        self._save_state("success", {"errors": {}, "warnings": {}})

    # ── Validation / calculation ───────────────────────────────────────────────

    def register_pages(self, widget_map: dict):
        self._pages = {
            name: page
            for name, page in widget_map.items()
            if name != "Outputs" and hasattr(page, "validate")
        }
        _dbg(f"Registered pages: {list(self._pages.keys())}")

    def run_validation(self):
        _dbg("=== run_validation START ===")

        all_errors = {}
        all_warnings = {}

        ap = self.analysis_period.value()
        if ap <= 0:
            self.analysis_period.setStyleSheet(
                f"border: 1.5px solid {get_token("danger")};"
            )
            all_errors["Analysis Period"] = [
                "Analysis Period is required — please enter a value greater than zero."
            ]
        else:
            self.analysis_period.setStyleSheet("")

        for name, page in self._pages.items():
            _dbg(f"Validating page: '{name}' ({type(page).__name__})")
            result = page.validate()
            _dbg(f"  result type={type(result).__name__}  value={result!r}")

            if isinstance(result, dict):
                errors = result.get("errors", [])
                warnings = result.get("warnings", [])
                _dbg(f"  dict-format => errors={errors}  warnings={warnings}")
                if errors:
                    all_errors[name] = errors
                if warnings:
                    all_warnings[name] = warnings
            else:
                # legacy tuple format (status, issues)
                status, issues = result
                _dbg(f"  tuple-format => status={status}  issues={issues}")
                if status == ValidationStatus.ERROR and issues:
                    all_errors[name] = issues
                elif status == ValidationStatus.WARNING and issues:
                    all_warnings[name] = issues

        _dbg(
            f"Validation done => all_errors={list(all_errors.keys())}  all_warnings={list(all_warnings.keys())}"
        )

        if all_errors or all_warnings:
            self.show_results(all_errors, all_warnings)
        else:
            self.show_success()
            self.run_calculation()

    def run_calculation(self):
        _dbg("=== run_calculation START ===")
        _dbg(f"self._pages at entry: {list(self._pages.keys())}")

        # Collect data from all pages (fast, main-thread safe)
        all_data = {}
        for name, page in self._pages.items():
            has_get = hasattr(page, "get_data")
            _dbg(f"  page='{name}'  has_get_data={has_get}")
            if has_get:
                result = page.get_data()
                chunk_key = result["chunk"]
                _dbg(
                    f"    chunk_key='{chunk_key}'  data_keys={list(result['data'].keys()) if isinstance(result['data'], dict) else type(result['data']).__name__}"
                )
                all_data[chunk_key] = result["data"]

        _dbg(f"all_data keys collected: {list(all_data.keys())}")

        # Show "calculating" state and disable the button immediately
        self._show_calculating()

        # Build worker + thread
        self._calc_thread = QThread(self)
        self._calc_worker = _LCCAWorker(self, all_data)
        self._calc_worker.moveToThread(self._calc_thread)

        self._calc_thread.started.connect(self._calc_worker.run)
        self._calc_worker.finished.connect(self._on_calc_finished)
        self._calc_worker.errored.connect(self._on_calc_errored)

        # Cleanup when done
        self._calc_worker.finished.connect(self._calc_thread.quit)
        self._calc_worker.errored.connect(self._calc_thread.quit)
        self._calc_thread.finished.connect(self._calc_thread.deleteLater)

        self._calc_thread.start()
        _dbg("Calculation thread started.")

    # ── Thread result handlers (called on main thread via queued signal) ──────

    def _on_calc_finished(self, results):
        _dbg(f"_on_calc_finished: results type={type(results).__name__}")
        self._stop_timers()
        self._show_calculation_success(results)

    def _on_calc_errored(self, exc, tb):
        _dbg(f"_on_calc_errored: {type(exc).__name__}: {exc}")
        self._stop_timers()
        self._show_calculation_error(exc, tb)

    def _show_calculation_error(self, error: Exception, tb: str = ""):
        self.btn_calculate.setEnabled(True)
        self._clear_status()
        banner = QGroupBox()
        banner.setStyleSheet(
            f"QGroupBox {{ border: 2px solid {get_token("danger")}; padding: 8px; }}"
        )
        layout = QVBoxLayout(banner)

        # ── Short summary ──────────────────────────────────────────────────
        title = QLabel(f"🛑  {type(error).__name__}")
        title.setStyleSheet(f"color: {get_token('danger')}; font-weight: {get_token('weight-bold')}; font-size: 13px;")
        layout.addWidget(title)

        # Show only the first line of the error message
        first_line = str(error).splitlines()[0] if str(error) else str(error)
        msg = QLabel(first_line)
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #b02a37;")
        layout.addWidget(msg)

        if tb:
            # ── Toggle + copy row ──────────────────────────────────────────
            btn_row = QHBoxLayout()

            toggle_btn = QPushButton("▸  Show full traceback")
            toggle_btn.setFlat(True)
            toggle_btn.setCursor(Qt.PointingHandCursor)
            toggle_btn.setStyleSheet("text-align: left; color: #555; padding: 2px 0;")
            btn_row.addWidget(toggle_btn)
            btn_row.addStretch()

            copy_btn = QPushButton("Copy to clipboard")
            copy_btn.setFixedWidth(130)
            copy_btn.clicked.connect(
                lambda: QApplication.clipboard().setText(tb.strip())
            )
            btn_row.addWidget(copy_btn)
            layout.addLayout(btn_row)

            # ── Traceback box (hidden by default) ─────────────────────────
            tb_box = QTextEdit()
            tb_box.setReadOnly(True)
            tb_box.setPlainText(tb.strip())
            tb_box.setStyleSheet("font-family: monospace; font-size: 11px;")
            tb_box.setFixedHeight(200)
            tb_box.setVisible(False)
            layout.addWidget(tb_box)

            def _toggle():
                visible = not tb_box.isVisible()
                tb_box.setVisible(visible)
                toggle_btn.setText(
                    "▾  Hide full traceback" if visible else "▸  Show full traceback"
                )

            toggle_btn.clicked.connect(_toggle)

        self._status_layout.addWidget(banner)
        self._status_layout.addStretch()

    def _show_calculation_success(self, results):
        self.btn_calculate.setEnabled(True)
        self._last_results = results
        self._clear_status()

        # ── Success banner + Download button ───────────────────────────────
        banner = QGroupBox()
        banner.setStyleSheet("QGroupBox { border: 2px solid #198754; padding: 8px; }")
        banner_row = QHBoxLayout(banner)
        banner_row.addWidget(
            QLabel("✅  Calculation completed successfully."), stretch=1
        )

        dl_btn = QPushButton("⬇  Export Report (.3psLCCAFile)")
        dl_btn.setFixedHeight(30)
        dl_btn.setFixedWidth(210)
        dl_btn.setToolTip("Export all inputs and LCC results as a .3psLCCAFile file")
        dl_btn.clicked.connect(self._download_report)
        banner_row.addWidget(dl_btn)

        pdf_btn = QPushButton("📄  Generate PDF Report")
        pdf_btn.setFixedHeight(30)
        pdf_btn.setFixedWidth(180)
        pdf_btn.setToolTip("Generate a customizable PDF report")
        pdf_btn.clicked.connect(self._generate_pdf_report)
        banner_row.addWidget(pdf_btn)

        self._status_layout.addWidget(banner)

        # ── Warnings ───────────────────────────────────────────────────────
        for w in results.get("warnings", []):
            lbl = QLabel(f"⚠ {w}")
            lbl.setStyleSheet("color: #856404;")
            lbl.setWordWrap(True)
            self._status_layout.addWidget(lbl)

        # ── Chart ──────────────────────────────────────────────────────────
        try:

            chart = LCCChartWidget(results)
            self._status_layout.addWidget(chart)
            pie = LCCPieWidget(results)
            self._status_layout.addWidget(pie)
            breakdown = LCCBreakdownTable(results)
            self._status_layout.addWidget(breakdown)
            table = LCCDetailsTable(results)
            self._status_layout.addWidget(table)
        except Exception as e:
            import traceback

            err = QLabel(f"Chart error: {e}\n{traceback.format_exc(limit=4)}")
            err.setStyleSheet("color: gray; font-style: italic;")
            self._status_layout.addWidget(err)

        self._status_layout.addStretch()

        self._has_results = True
        self.calculation_completed.emit()

    def reset_for_edit(self):
        """Clear results and return to idle state so inputs can be edited."""
        self._has_results = False
        self._show_idle()
        self._save_state("idle", {})

    def freeze(self, frozen: bool):
        self.btn_calculate.setEnabled(not frozen)
        freeze_form(OUTPUTS_FIELDS, self, frozen)

    def clear_validation(self):
        clear_field_styles(OUTPUTS_FIELDS, self)

    def validate(self):
        return validate_form(OUTPUTS_FIELDS, self, warn_rules=OUTPUTS_WARN_RULES)

    # ── Chunk routing — analysis_period saves to its own chunk ────────────────

    def _on_field_changed(self):
        if self._loading:
            return
        self.data_changed.emit()
        if self.controller:
            self.controller.save_chunk_data(CHUNK_AP, self.get_data_dict())

    def refresh_from_engine(self):
        if not self.controller or not self.controller.engine:
            return
        if not self.controller.engine.is_active():
            return
        data = self.controller.get_chunk(CHUNK_AP) or {}
        if not data or data == self._loaded_data:
            return
        self._loaded_data = data
        self.load_data_dict(data)

    # ==========Prepare-Mapping-for-Core==============================================

    def _prepare_life_cycle_construction_cost(self, data: dict):
        """
        This function creates the life cycle construction cost breakdown dict using the data from saved chunks.
        ex. life_cycle_construction_cost_breakdown = {
                    "initial_construction_cost": 12843979.44,
                    "initial_carbon_emissions_cost": 2065434.91,
                    "superstructure_construction_cost": 9356038.92,
                    "total_scrap_value": 2164095.02,
                }
        """
        _dbg("=== _prepare_life_cycle_construction_cost START ===")
        carbon_emissions = data.get("carbon_emission_data")
        _dbg(
            f"  carbon_emission_data keys: {list(carbon_emissions.keys()) if carbon_emissions else 'MISSING'}"
        )

        carbon_cost_per_kg = (
            carbon_emissions.get("social_cost_data")
            .get("result")
            .get("cost_of_carbon_local")
        )
        _dbg(f"  carbon_cost_per_kg={carbon_cost_per_kg!r}")

        mat_co2 = float(
            carbon_emissions.get("material_emissions_data").get("total_kgCO2e")
        )
        trans_co2 = float(
            carbon_emissions.get("transport_emissions_data").get("total_kgCO2e")
        )
        mach_co2 = float(
            carbon_emissions.get("machinery_emissions_data").get("total_kgCO2e")
        )
        total_kgCO2e = mat_co2 + trans_co2 + mach_co2
        _dbg(
            f"  material_kgCO2e={mat_co2}  transport_kgCO2e={trans_co2}  machinery_kgCO2e={mach_co2}  total_kgCO2e={total_kgCO2e}"
        )

        construction_work_data = data.get("construction_work_data")
        _dbg(
            f"  construction_work_data keys: {list(construction_work_data.keys()) if construction_work_data else 'MISSING'}"
        )
        grand_total = float(construction_work_data.get("grand_total"))
        super_total = float(construction_work_data.get("Super Structure").get("total"))
        scrap_value = float(data.get("recycling_data").get("total_recovered_value"))
        _dbg(
            f"  grand_total={grand_total}  super_total={super_total}  scrap_value={scrap_value}"
        )

        return {
            "initial_construction_cost": grand_total,
            "initial_carbon_emissions_cost": total_kgCO2e * carbon_cost_per_kg,
            "superstructure_construction_cost": super_total,
            "total_scrap_value": scrap_value,
        }

    def _prepare_wpi_object(self, data: dict):
        """
        This function creates a WPI object using the data from saved chunks.
        """
        _dbg("=== _prepare_wpi_object START ===")
        wpi_data = data.get("traffic_and_road_data").get("wpi")
        _dbg(f"  wpi_data keys: {list(wpi_data.keys()) if wpi_data else 'MISSING'}")
        wpi_dict = wpi_data.get("data_snapshot").get("ratio")
        _dbg(
            f"  wpi_dict (first 3 keys): { {k: wpi_dict[k] for k in list(wpi_dict)[:3]} if wpi_dict else 'MISSING' }"
        )
        year = int(
            wpi_data.get("selected_profile_year")
            or wpi_data.get("selected_profile_name", 0)
        )
        _dbg(f"  year={year}")

        return WPIMetaData.from_dict({"year": year, "WPI": wpi_dict})

    def _prepare_data_object(self, data: dict):
        """
        This function creates Core Data Object using the data from saved chunks.
        To be passed to 3psLCCAFile-core for calculation.
        """

        # --------------Prepare-General-Parameters-Start-------------------------------------------------
        _dbg("=== _prepare_data_object START ===")
        _dbg(f"  all_data keys present: {list(data.keys())}")

        _financial_data = data.get("financial_data")
        _dbg(f"  financial_data: {_financial_data!r}")
        if _financial_data is None:
            raise ValueError(
                "Financial Data is missing from the calculation inputs.\n"
                "Fill in the Financial Data page and try again."
            )

        analysis_period_years = int(self.analysis_period.value())
        discount_rate_percent = float(_financial_data.get("discount_rate"))
        inflation_rate_percent = float(_financial_data.get("inflation_rate"))
        interest_rate_percent = float(_financial_data.get("interest_rate"))
        investment_ratio = float(_financial_data.get("investment_ratio"))
        _dbg(
            f"  financial => analysis_period={analysis_period_years}  discount={discount_rate_percent}  inflation={inflation_rate_percent}  interest={interest_rate_percent}  inv_ratio={investment_ratio}"
        )

        # cost_of_carbon_local is in local_currency/kgCO2e (user-selected source).
        # The engine expects social_cost_of_carbon_per_mtco2e in local_currency/mtCO2e,
        # so multiply by 1000.
        scc_from_fin = _financial_data.get("social_cost_of_carbon")
        if scc_from_fin is not None:
            social_cost_of_carbon_per_mtco2e = float(scc_from_fin) * 1000
        else:
            _result = data.get("carbon_emission_data", {}).get("social_cost_data", {}).get("result", {})
            social_cost_of_carbon_per_mtco2e = (
                float(_result.get("cost_of_carbon_local", 0.0)) * 1000
            )
        
        currency_conversion = float(_financial_data.get("currency_conversion", 1.0))
        _dbg(f"  social_cost_of_carbon_per_mtco2e={social_cost_of_carbon_per_mtco2e}  currency_conversion={currency_conversion}")

        _bridge_data = data.get("bridge_data")
        _dbg(f"  bridge_data: {_bridge_data!r}")
        service_life_years = int(_bridge_data.get("design_life"))
        construction_period_months = float(
            _bridge_data.get("duration_construction_months")
        )
        working_days_per_month = float(_bridge_data.get("working_days_per_month"))
        days_per_month = float(_bridge_data.get("days_per_month"))
        _dbg(
            f"  bridge => service_life={service_life_years}  construction_months={construction_period_months}  working_days={working_days_per_month}  days_per_month={days_per_month}"
        )

        use_global_road_user_calculations = (
            data.get("traffic_and_road_data").get("mode") == "GLOBAL"
        )
        _dbg(
            f"  traffic mode='{data.get('traffic_and_road_data').get('mode')}'  use_global={use_global_road_user_calculations}"
        )

        general_parameters = GeneralParameters(
            service_life_years=service_life_years,
            analysis_period_years=analysis_period_years,
            discount_rate_percent=discount_rate_percent,
            inflation_rate_percent=inflation_rate_percent,
            interest_rate_percent=interest_rate_percent,
            investment_ratio=investment_ratio,
            social_cost_of_carbon_per_mtco2e=social_cost_of_carbon_per_mtco2e,
            currency_conversion=currency_conversion,
            construction_period_months=construction_period_months,
            working_days_per_month=working_days_per_month,
            days_per_month=days_per_month,
            use_global_road_user_calculations=use_global_road_user_calculations,
        )
        # --------------Prepare-General-Parameters-End-------------------------------------------------

        # --------------Prepare-Maintenance-&-EOL-Start-------------------------------------------------
        _maintenance_data = data.get("maintenance_data")
        _demolition_data = data.get("demolition_data")
        _dbg(f"  maintenance_data: {_maintenance_data!r}")
        _dbg(f"  demolition_data: {_demolition_data!r}")

        routine_inspection_picc_per_year = float(
            _maintenance_data.get("routine_inspection_cost")
        )
        routine_inspection_interval_in_years = int(
            _maintenance_data.get("routine_inspection_freq")
        )

        routine_maintenance_picc_per_year = float(
            _maintenance_data.get("periodic_maintenance_cost")
        )
        routine_maintenance_picec = float(
            _maintenance_data.get("periodic_maintenance_carbon_cost")
        )
        routine_maintenance_interval_in_years = int(
            _maintenance_data.get("periodic_maintenance_freq")
        )

        major_inspection_picc = float(_maintenance_data.get("major_inspection_cost"))
        major_inspection_interval_in_years = int(
            _maintenance_data.get("major_inspection_freq")
        )

        major_repair_picc = float(_maintenance_data.get("major_repair_cost"))
        major_repair_picec = float(_maintenance_data.get("major_repair_carbon_cost"))
        major_repair_interval_in_years = int(_maintenance_data.get("major_repair_freq"))
        major_repair_duration_months = int(
            _maintenance_data.get("major_repair_duration")
        )

        replace_bne_joint_pssc = float(_maintenance_data.get("bearing_exp_joint_cost"))
        replace_bne_joint_interval_in_years = int(
            _maintenance_data.get("bearing_exp_joint_freq")
        )
        replace_bne_joint_duration_in_days = int(
            _maintenance_data.get("bearing_exp_joint_duration")
        )

        eol_picc = float(_demolition_data.get("demolition_cost_pct"))
        eol_picec = float(_demolition_data.get("demolition_carbon_cost_pct"))
        eol_dd_in_months = int(_demolition_data.get("demolition_duration"))

        maintenance_and_stage_parameters = MaintenanceAndStageParameters(
            use_stage_cost=UseStageCost(
                routine=Routine(
                    inspection=RoutineInspection(
                        percentage_of_initial_construction_cost_per_year=routine_inspection_picc_per_year,
                        interval_in_years=routine_inspection_interval_in_years,
                    ),
                    maintenance=RoutineMaintenance(
                        percentage_of_initial_construction_cost_per_year=routine_maintenance_picc_per_year,
                        percentage_of_initial_carbon_emission_cost=routine_maintenance_picec,
                        interval_in_years=routine_maintenance_interval_in_years,
                    ),
                ),
                major=Major(
                    inspection=MajorInspection(
                        percentage_of_initial_construction_cost=major_inspection_picc,
                        interval_for_repair_and_rehabitation_in_years=major_inspection_interval_in_years,
                    ),
                    repair=MajorRepair(
                        percentage_of_initial_construction_cost=major_repair_picc,
                        percentage_of_initial_carbon_emission_cost=major_repair_picec,
                        interval_for_repair_and_rehabitation_in_years=major_repair_interval_in_years,
                        repairs_duration_months=major_repair_duration_months,
                    ),
                ),
                replacement_costs_for_bearing_and_expansion_joint=ReplacementCost(
                    percentage_of_super_structure_cost=replace_bne_joint_pssc,
                    interval_of_replacement_in_years=replace_bne_joint_interval_in_years,
                    duration_of_replacement_in_days=replace_bne_joint_duration_in_days,
                ),
            ),
            end_of_life_stage_costs=EndOfLifeStageCosts(
                demolition_and_disposal=DemolitionDisposal(
                    percentage_of_initial_construction_cost=eol_picc,
                    percentage_of_initial_carbon_emission_cost=eol_picec,
                    duration_for_demolition_and_disposal_in_months=eol_dd_in_months,
                )
            ),
        )

        # --------------Prepare-Maintenance-&-EOL-End-------------------------------------------------

        # Object to return
        object = None

        if not use_global_road_user_calculations:
            # ------------------------------------Traffic-and-Road-Data-India-Start--------------------------------------------
            _dbg("Branch: INDIA (non-global) road user calculations")
            _traffic_road_data = data.get("traffic_and_road_data")
            _dbg(
                f"  traffic_road_data keys: {list(_traffic_road_data.keys()) if _traffic_road_data else 'MISSING'}"
            )
            _traffic_vehicle_data = _traffic_road_data.get("vehicle_data")
            _dbg(
                f"  vehicle_data keys: {list(_traffic_vehicle_data.keys()) if _traffic_vehicle_data else 'MISSING'}"
            )
            _ef = (
                data.get("carbon_emission_data", {})
                .get("diversion_emissions", {})
                .get("emission_factors", {})
            )
            _emission_factors = {k: float(v or 0.0) for k, v in _ef.items()}
            _dbg(f"  emission_factors: {_emission_factors}")

            small_cars = VehicleMetaData(
                int(_traffic_vehicle_data.get("small_cars").get("vehicles_per_day")),
                _emission_factors.get("small_cars", 0.0),
                float(
                    _traffic_vehicle_data.get("small_cars").get("accident_percentage")
                ),
            )
            big_cars = VehicleMetaData(
                int(_traffic_vehicle_data.get("big_cars").get("vehicles_per_day")),
                _emission_factors.get("big_cars", 0.0),
                float(_traffic_vehicle_data.get("big_cars").get("accident_percentage")),
            )
            two_wheelers = VehicleMetaData(
                int(_traffic_vehicle_data.get("two_wheelers").get("vehicles_per_day")),
                _emission_factors.get("two_wheelers", 0.0),
                float(
                    _traffic_vehicle_data.get("two_wheelers").get("accident_percentage")
                ),
            )
            o_buses = VehicleMetaData(
                int(_traffic_vehicle_data.get("o_buses").get("vehicles_per_day")),
                _emission_factors.get("o_buses", 0.0),
                float(_traffic_vehicle_data.get("o_buses").get("accident_percentage")),
            )
            d_buses = VehicleMetaData(
                int(_traffic_vehicle_data.get("d_buses").get("vehicles_per_day")),
                _emission_factors.get("d_buses", 0.0),
                float(_traffic_vehicle_data.get("d_buses").get("accident_percentage")),
            )
            lcv = VehicleMetaData(
                int(_traffic_vehicle_data.get("lcv").get("vehicles_per_day")),
                _emission_factors.get("lcv", 0.0),
                float(_traffic_vehicle_data.get("lcv").get("accident_percentage")),
            )
            hcv = VehicleMetaData(
                int(_traffic_vehicle_data.get("hcv").get("vehicles_per_day")),
                _emission_factors.get("hcv", 0.0),
                float(_traffic_vehicle_data.get("hcv").get("accident_percentage")),
                pwr=float(_traffic_vehicle_data.get("hcv").get("pwr")),
            )
            mcv = VehicleMetaData(
                int(_traffic_vehicle_data.get("mcv").get("vehicles_per_day")),
                _emission_factors.get("mcv", 0.0),
                float(_traffic_vehicle_data.get("mcv").get("accident_percentage")),
                pwr=float(_traffic_vehicle_data.get("mcv").get("pwr")),
            )

            minor = float(_traffic_road_data.get("severity_minor"))
            major = float(_traffic_road_data.get("severity_major"))
            fatal = float(_traffic_road_data.get("severity_fatal"))

            alternate_road_carriageway = _traffic_road_data.get(
                "alternate_road_carriageway"
            )
            carriage_width_in_m = float(_traffic_road_data.get("carriage_width_in_m"))
            road_roughness_mm_per_km = float(
                _traffic_road_data.get("road_roughness_mm_per_km")
            )
            road_rise_m_per_km = float(_traffic_road_data.get("road_rise_m_per_km"))
            road_fall_m_per_km = float(_traffic_road_data.get("road_fall_m_per_km"))
            additional_reroute_distance_km = float(
                _traffic_road_data.get("additional_reroute_distance_km")
            )
            additional_travel_time_min = float(
                _traffic_road_data.get("additional_travel_time_min")
            )
            crash_rate_accidents_per_million_km = float(
                _traffic_road_data.get("crash_rate_accidents_per_million_km")
            )
            work_zone_multiplier = float(_traffic_road_data.get("work_zone_multiplier"))
            # Make the list of values for each hour of the day from the dict with hour keys
            peak_hour_traffic_percent_per_hour = list(
                _traffic_road_data.get("peak_hour_distribution").values()
            )
            hourly_capacity = int(_traffic_road_data.get("hourly_capacity"))
            force_free_flow_off_peak = bool(
                _traffic_road_data.get("force_free_flow_off_peak")
            )

            traffic_and_road_data = TrafficAndRoadData(
                vehicle_data=VehicleData(
                    small_cars=small_cars,
                    big_cars=big_cars,
                    two_wheelers=two_wheelers,
                    o_buses=o_buses,
                    d_buses=d_buses,
                    lcv=lcv,
                    hcv=hcv,
                    mcv=mcv,
                ),
                accident_severity_distribution=AccidentSeverityDistribution(
                    minor=minor,
                    major=major,
                    fatal=fatal,
                ),
                additional_inputs=AdditionalInputs(
                    alternate_road_carriageway=alternate_road_carriageway,
                    carriage_width_in_m=carriage_width_in_m,
                    road_roughness_mm_per_km=road_roughness_mm_per_km,
                    road_rise_m_per_km=road_rise_m_per_km,
                    road_fall_m_per_km=road_fall_m_per_km,
                    additional_reroute_distance_km=additional_reroute_distance_km,
                    additional_travel_time_min=additional_travel_time_min,
                    crash_rate_accidents_per_million_km=crash_rate_accidents_per_million_km,
                    work_zone_multiplier=work_zone_multiplier,
                    peak_hour_traffic_percent_per_hour=peak_hour_traffic_percent_per_hour,
                    hourly_capacity=hourly_capacity,
                    force_free_flow_off_peak=force_free_flow_off_peak,
                ),
            )
            # ------------------------------------Traffic-and-Road-Data-India-End--------------------------------------------

            _dbg(f"  severity => minor={minor}  major={major}  fatal={fatal}")
            _dbg(
                f"  road => carriageway='{alternate_road_carriageway}'  width={carriage_width_in_m}  roughness={road_roughness_mm_per_km}  rise={road_rise_m_per_km}  fall={road_fall_m_per_km}"
            )
            _dbg(
                f"  diversion => reroute_km={additional_reroute_distance_km}  travel_time_min={additional_travel_time_min}  crash_rate={crash_rate_accidents_per_million_km}"
            )
            _dbg(
                f"  work_zone_multiplier={work_zone_multiplier}  hourly_capacity={hourly_capacity}  force_free_flow={force_free_flow_off_peak}"
            )
            _dbg(
                f"  peak_hour_distribution (sum)={sum(peak_hour_traffic_percent_per_hour):.4f}"
            )
            _dbg("Building InputMetaData (India) ...")
            object = InputMetaData(
                general_parameters=general_parameters,
                traffic_and_road_data=traffic_and_road_data,
                maintenance_and_stage_parameters=maintenance_and_stage_parameters,
            )
        else:
            # ------------------------------------Traffic-and-Road-Data-Global-Start--------------------------------------------
            _dbg("Branch: GLOBAL road user calculations")
            _global_diversion = data.get("carbon_emission_data", {}).get(
                "diversion_emissions", {}
            )
            _dbg(
                f"  diversion_emissions keys: {list(_global_diversion.keys()) if _global_diversion else 'MISSING'}"
            )
            _dbg(f"  diversion mode: {_global_diversion.get('mode')!r}")
            if _global_diversion.get("mode") == "Calculate by Vehicle":
                total_vehicular_carbon_emission = float(
                    _global_diversion.get("total_calculated_emissions", 0.0)
                )
            else:
                total_vehicular_carbon_emission = float(
                    _global_diversion.get("total_direct_emissions", 0.0)
                )
            _dbg(f"  total_vehicular_carbon_emission={total_vehicular_carbon_emission}")
            total_daily_ruc = float(
                data.get("traffic_and_road_data").get("road_user_cost_per_day")
            )
            _dbg(f"  total_daily_ruc={total_daily_ruc}")

            daily_road_user_cost_with_vehicular_emissions = DailyRoadUserCost(
                total_daily_ruc=total_daily_ruc,
                total_carbon_emission=TotalCarbonEmission(
                    total_emission_kgCO2e=total_vehicular_carbon_emission
                ),
            )
            # ------------------------------------Traffic-and-Road-Data-Global-End--------------------------------------------

            _dbg("Building InputGlobalMetaData ...")
            object = InputGlobalMetaData(
                general_parameters=general_parameters,
                daily_road_user_cost_with_vehicular_emissions=daily_road_user_cost_with_vehicular_emissions,
                maintenance_and_stage_parameters=maintenance_and_stage_parameters,
            )

        _dbg(
            f"=== _prepare_data_object END => returning is_global={use_global_road_user_calculations}  object={type(object).__name__} ==="
        )
        return use_global_road_user_calculations, object

    # ===================================================================================

    # ── Report download ───────────────────────────────────────────────────────

    def _download_report(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Report",
            "LCC_Report.3psLCCAFile",
            "3psLCCAFile Files (*.3psLCCAFile)",
        )
        if not path:
            return
        # Ensure correct extension even if user typed something else
        if not path.endswith(".3psLCCAFile"):
            path += ".3psLCCAFile"
        try:
            import json

            export = self._build_export_dict(
                getattr(self, "_last_all_data", {}),
                getattr(self, "_last_lcc_breakdown", {}),
                getattr(self, "_last_results", {}),
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export, f, indent=2, ensure_ascii=False)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "Saved", f"Report saved to:\n{path}")
        except Exception as e:
            import traceback
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self,
                "Export Failed",
                f"{type(e).__name__}: {e}\n\n{traceback.format_exc(limit=4)}",
            )

    def _build_export_dict(
        self, all_data: dict, lcc_breakdown: dict, results: dict
    ) -> dict:
        """
        Build the full export dict written to a .3psLCCAFile file.

        Structure
        ---------
        {
          "format":      "3psLCCAFile",
          "version":     "1.0",
          "exported_at": "<ISO timestamp>",
          "inputs": {
            "construction_work_data": { ... },  # includes grand_total, page/component/item totals
            "carbon_emission_data":   { ... },  # includes total_kgCO2e per sub-section
            "recycling_data":         { ... },  # includes total_recovered_value, cat_totals
            "traffic_and_road_data":  { ... },
            "financial_data":         { ... },
            "bridge_data":            { ... },
            "maintenance_data":       { ... },
            "demolition_data":        { ... },
          },
          "computed": {
            "initial_construction_cost":       <float>,
            "initial_carbon_emissions_cost":   <float>,
            "superstructure_construction_cost":<float>,
            "total_scrap_value":               <float>,
          },
          "results": { ... }   # direct output of run_full_lcc_analysis
        }

        All values are sanitised to JSON-safe primitives.
        """
        import datetime

        def _sanitize(obj):
            """Recursively coerce non-JSON-serialisable values to primitives."""
            if obj is None or isinstance(obj, (bool, str)):
                return obj
            if isinstance(obj, float):
                return float(obj)
            if isinstance(obj, int):
                return int(obj)
            if isinstance(obj, dict):
                return {str(k): _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_sanitize(i) for i in obj]
            # dataclass / namedtuple / custom objects
            try:
                from dataclasses import asdict, fields

                fields(obj)
                return _sanitize(asdict(obj))
            except TypeError:
                pass
            try:
                return _sanitize(obj._asdict())
            except AttributeError:
                pass
            return str(obj)

        return {
            "format": "3psLCCAFile",
            "version": "1.0",
            "exported_at": datetime.datetime.now().isoformat(),
            "inputs": _sanitize(all_data),
            "computed": _sanitize(lcc_breakdown),
            "results": _sanitize(results),
        }

    def _generate_pdf_report(self):
        """Open the section selection dialog and generate a PDF report."""
        from .report_section_dialog import ReportSectionDialog

        dlg = ReportSectionDialog(
            build_export_dict=self._build_export_dict,
            all_data=getattr(self, "_last_all_data", {}),
            lcc_breakdown=getattr(self, "_last_lcc_breakdown", {}),
            results=getattr(self, "_last_results", {}),
            parent=self,
        )
        dlg.exec()

    def _on_proceed(self):
        self.run_calculation()

    # ── Card widget ───────────────────────────────────────────────────────────

    def _create_card(self, page_name, issues, icon):
        card = QGroupBox()
        card.setStyleSheet(
            "QGroupBox { border: 1px solid #dee2e6; border-radius: 4px; }"
        )
        layout = QVBoxLayout(card)

        h_row = QWidget()
        h_lay = QHBoxLayout(h_row)
        h_lay.setContentsMargins(0, 0, 0, 0)
        h_lay.addWidget(QLabel(f"<b>{page_name}</b>"))
        h_lay.addStretch()

        go_btn = QPushButton("Go →")
        go_btn.clicked.connect(
            lambda checked=False, p=page_name: self.navigate_requested.emit(p)
        )
        h_lay.addWidget(go_btn)

        layout.addWidget(h_row)
        for msg in issues:
            lbl = QLabel(f"{icon} {msg}")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
        return card

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_state(self, status: str, data: dict):
        if self.controller and self.controller.engine:
            self.controller.engine.stage_update(
                chunk_name=self.chunk_name, data={"status": status, "data": data}
            )

    def on_refresh(self):
        if not self.controller or not self.controller.engine:
            _dbg("on_refresh: no controller/engine, skipping")
            return

        self.refresh_from_engine()

        state = self.controller.engine.fetch_chunk(CHUNK) or {}
        status = state.get("status", "idle")
        data = state.get("data", {})
        _dbg(
            f"on_refresh: status='{status}'  data_keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
        )
        if status == "issues":
            self.show_results(data.get("errors", {}), data.get("warnings", {}))
        elif status == "success":
            self.show_success()
        else:
            self._show_idle()


