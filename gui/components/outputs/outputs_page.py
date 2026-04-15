"""
gui/components/outputs/outputs_page.py
"""

import json
import logging
import traceback

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal

from gui.themes import get_token, theme_manager
from gui.styles import (
    font as _f,
    btn_primary,
    btn_outline,
    btn_ghost,
)
from gui.theme import (
    SP1, SP2, SP3, SP4,
    RADIUS_SM, RADIUS_MD,
    FS_XS, FS_SM, FS_BASE, FS_MD, FS_LG, FS_XL,
    FW_MEDIUM, FW_SEMIBOLD, FW_BOLD,
    BTN_MD, BTN_SM
)
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
from three_ps_lcca_core.core.main import run_full_lcc_analysis

from .lcc_plot import LCCBreakdownTable, LCCChartWidget, LCCDetailsTable
from .plots_helper.Pie import LCCPieWidget
from .data_preparer import DataPreparer
from .report_section_dialog import ReportSectionDialog



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
        "Analysis period exceeds 500 years - please verify",
    ),
}
_log = logging.getLogger(__name__)


def _make_issue_card(page_name: str, issues: list, icon: str, navigate_cb) -> QGroupBox:
    """Standalone card widget for a single page's validation errors or warnings."""
    card = QGroupBox()
    card.setStyleSheet(
        f"QGroupBox {{ border: 1px solid {get_token('surface_mid')}; "
        f"border-radius: {RADIUS_MD}px; padding: {SP3}px; }}"
    )
    layout = QVBoxLayout(card)
    layout.setSpacing(SP2)

    h_row = QWidget()
    h_lay = QHBoxLayout(h_row)
    h_lay.setContentsMargins(0, 0, 0, 0)

    name_lbl = QLabel(page_name.upper())
    name_lbl.setFont(_f(FS_XS, FW_BOLD))
    name_lbl.setStyleSheet(f"color: {get_token('text_disabled')}; letter-spacing: 1px;")
    h_lay.addWidget(name_lbl, 0, Qt.AlignVCenter)
    h_lay.addStretch()

    go_btn = QPushButton("Fix Issues →")
    go_btn.setFixedHeight(26)
    go_btn.setFont(_f(FS_XS, FW_SEMIBOLD))
    go_btn.setStyleSheet(btn_ghost())
    go_btn.setCursor(Qt.PointingHandCursor)
    go_btn.clicked.connect(lambda checked=False, p=page_name: navigate_cb(p))
    h_lay.addWidget(go_btn, 0, Qt.AlignVCenter)

    layout.addWidget(h_row)

    for issue in issues:
        msg = issue if isinstance(issue, str) else issue.get("msg", str(issue))
        
        issue_row = QHBoxLayout()
        issue_row.setSpacing(SP2)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(_f(FS_SM))
        issue_row.addWidget(icon_lbl, 0, Qt.AlignTop)

        txt_lbl = QLabel(msg)
        txt_lbl.setFont(_f(FS_BASE))
        txt_lbl.setStyleSheet(f"color: {get_token('text')};")
        txt_lbl.setWordWrap(True)
        issue_row.addWidget(txt_lbl, 1)

        layout.addLayout(issue_row)

    return card



class _LCCAWorker(QObject):
    """Runs the heavy LCCA calculation on a background thread.

    Signals
    -------
    finished(results)   - emitted with the raw results dict on success.
    errored(exc, tb)    - emitted with the exception and formatted traceback on failure.
    """

    # Carries (results, all_data, lcc_breakdown) - all owned by main thread on receipt.
    finished = Signal(object, object, object)
    errored = Signal(object, str)  # (Exception, traceback_str)

    def __init__(self, all_data: dict, analysis_period_years: int):
        super().__init__()
        self._all_data = all_data
        self._analysis_period_years = analysis_period_years

    def run(self):
        try:
            all_data = self._all_data

            _log.debug("Worker: calling DataPreparer.prepare_data_object …")
            is_global, data_object = DataPreparer.prepare_data_object(
                all_data, self._analysis_period_years
            )
            _log.debug(
                f"Worker: is_global={is_global}  data_object={type(data_object).__name__}"
            )

            wpi_metadata = None
            if not is_global:
                _log.debug("Worker: calling DataPreparer.prepare_wpi_object …")
                wpi_metadata = DataPreparer.prepare_wpi_object(all_data)

            _log.debug("Worker: calling DataPreparer.prepare_life_cycle_construction_cost …")
            lcc_breakdown = DataPreparer.prepare_life_cycle_construction_cost(all_data)

            _log.debug("Worker: calling run_full_lcc_analysis …")
            results = run_full_lcc_analysis(
                data_object,
                lcc_breakdown,
                wpi=wpi_metadata,
                debug=True,
            )
            _log.debug(
                f"Worker: run_full_lcc_analysis returned: {list(results.keys()) if isinstance(results, dict) else type(results).__name__}"
            )

            # Emit all three payloads so the main thread owns the data - no
            # cross-thread attribute writes on the page object.
            self.finished.emit(results, all_data, lcc_breakdown)

        except Exception as exc:
            tb_str = traceback.format_exc()
            _log.debug(f"Worker ERROR: {type(exc).__name__}: {exc}\n{tb_str}")
            self.errored.emit(exc, tb_str)


class OutputsPage(ScrollableForm):

    navigate_requested = Signal(str)
    calculation_completed = Signal()  # emitted after a successful calculation
    validate_requested = (
        Signal()
    )  # emitted when user clicks Validate - project_window handles it

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
        self._currency = "INR"  # default project currency
        # State tracking for theme-change re-render
        self._current_status = "idle"   # idle | calculating | issues | success | calc_error | calc_success
        self._status_args: dict = {}    # args needed to re-render current status
        self._build_ui()
        theme_manager().theme_changed.connect(self._refresh_styles)

    def _build_ui(self):
        f = self.form
        self._header = QLabel("Outputs")
        self._header.setFont(_f(FS_XL, FW_BOLD))
        self._header.setStyleSheet(f"color: {get_token('primary')}; margin-bottom: {SP2}px;")
        f.addRow(self._header)

        # ── Analysis Period ───────────────────────────────────────────────
        self.required_keys = build_form(self, OUTPUTS_FIELDS, None)

        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, SP2, 0, SP4)

        self.btn_calculate = QPushButton("Validate  ▶")
        self.btn_calculate.setFixedHeight(BTN_MD)
        self.btn_calculate.setFixedWidth(180)
        self.btn_calculate.setFont(_f(FS_BASE, FW_MEDIUM))
        self.btn_calculate.setCursor(Qt.PointingHandCursor)
        self.btn_calculate.setStyleSheet(btn_primary())
        self.btn_calculate.clicked.connect(self.validate_requested.emit)
        
        btn_layout.addWidget(self.btn_calculate)
        btn_layout.addStretch()
        f.addRow(btn_row)

        self._status_widget = QWidget()
        self._status_layout = QVBoxLayout(self._status_widget)
        self._status_layout.setContentsMargins(0, 0, 0, 0)
        self._status_layout.setSpacing(SP4)
        f.addRow(self._status_widget)

        self._show_idle()

    # ── Theme refresh ─────────────────────────────────────────────────────────

    def _refresh_styles(self):
        """Reapply all token-based styles. Called on every theme change."""
        # Persistent widgets
        self._header.setStyleSheet(f"color: {get_token('primary')}; margin-bottom: {SP2}px;")
        self.btn_calculate.setStyleSheet(btn_primary())

        # Re-render the status area using the saved state + args.
        # Skip "calculating" — the calculation is in flight; it will finish and
        # call its own _show_* which will pick up fresh tokens at that point.
        status = self._current_status
        args = self._status_args
        if status == "idle":
            self._show_idle()
        elif status == "issues":
            self.show_results(args["errors"], args["warnings"])
        elif status == "success":
            self.show_success()
        elif status == "calc_error":
            self._show_calculation_error(args["error"], args.get("tb", ""))
        elif status == "calc_success" and hasattr(self, "_last_results"):
            self._show_calculation_success(self._last_results)

    # ── Status area ───────────────────────────────────────────────────────────

    def _clear_status(self):
        while self._status_layout.count():
            item = self._status_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)

    def _show_idle(self):
        self._current_status = "idle"
        self._status_args = {}
        self._clear_status()
        note = QLabel("Press Validate to check all pages for consistency before calculation.")
        note.setFont(_f(FS_BASE))
        note.setStyleSheet(f"color: {get_token('text_secondary')}; font-style: italic;")
        self._status_layout.addWidget(note)

    # ── Calculation timeout constant ──────────────────────────────────────────
    CALC_TIMEOUT_MS = 30_000  # 30 seconds

    def _show_calculating(self):
        """Show an animated progress bar, elapsed-time counter, and disable the button."""
        self._current_status = "calculating"
        self._status_args = {}
        self._clear_status()
        self.btn_calculate.setEnabled(False)

        # ── Container ──────────────────────────────────────────────────────
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        v = QVBoxLayout(container)
        v.setContentsMargins(SP4, SP4, SP4, SP4)
        v.setSpacing(SP2)

        # ── Header row: spinner label + elapsed counter ────────────────────
        h_row = QWidget()
        h = QHBoxLayout(h_row)
        h.setContentsMargins(0, 0, 0, 0)

        spin_lbl = QLabel("⏳  Performing Analysis…")
        spin_lbl.setFont(_f(FS_BASE, FW_MEDIUM))
        spin_lbl.setStyleSheet(f"color: {get_token('text')};")
        h.addWidget(spin_lbl)
        h.addStretch()

        self._elapsed_label = QLabel("0s / 30s")
        self._elapsed_label.setFont(_f(FS_SM))
        self._elapsed_label.setStyleSheet(f"color: {get_token('text_secondary')};")
        h.addWidget(self._elapsed_label)
        v.addWidget(h_row)

        # ── Marquee progress bar ───────────────────────────────────────────
        bar = QProgressBar()
        bar.setRange(0, 0)  # range(0,0) = indeterminate / marquee
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                border: none;
                border-radius: 4px;
                background: {get_token('surface_mid')};
            }}
            QProgressBar::chunk {{
                border-radius: 4px;
                background: {get_token('primary')};
            }}
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
            f"""
            QProgressBar {{
                border: none;
                border-radius: 2px;
                background: {get_token('surface_mid')};
            }}
            QProgressBar::chunk {{
                border-radius: 2px;
                background: {get_token('warning')};
            }}
            """
        )
        v.addWidget(self._countdown_bar)

        timeout_lbl = QLabel(
            f"Analysis will timeout in {self.CALC_TIMEOUT_MS // 1000}s if not complete."
        )
        timeout_lbl.setFont(_f(FS_XS))
        timeout_lbl.setStyleSheet(f"color: {get_token('text_disabled')};")
        v.addWidget(timeout_lbl)

        self._status_layout.addWidget(container)

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
        """Called when the 30 s timeout fires - terminate the thread and show error."""
        _log.debug(
            "=== _on_calc_timeout: calculation exceeded timeout, terminating thread ==="
        )
        self._stop_timers()

        if self._calc_thread and self._calc_thread.isRunning():
            self._calc_thread.terminate()  # forceful stop - never call wait() on main thread

        self.btn_calculate.setEnabled(True)
        timeout_exc = TimeoutError(
            f"Analysis did not complete within {self.CALC_TIMEOUT_MS // 1000} seconds.\n"
            "The processing thread was terminated to prevent system hang.\n"
            "This usually happens with extremely complex scenarios or invalid data ranges."
        )
        self._show_calculation_error(timeout_exc, "")

    def show_results(self, all_errors: dict, all_warnings: dict):
        """Show errors and warnings together. Proceed button only when no errors."""
        self._current_status = "issues"
        self._status_args = {"errors": all_errors, "warnings": all_warnings}
        self._clear_status()

        if all_errors:
            banner = QGroupBox()
            banner.setStyleSheet(
                f"QGroupBox {{ background: transparent; border: 1px solid {get_token('danger')}; "
                f"border-radius: {RADIUS_MD}px; padding: {SP3}px; }}"
            )
            layout = QVBoxLayout(banner)
            title = QLabel("🛑  Calculation Blocked - Please fix the following errors")
            title.setFont(_f(FS_MD, FW_BOLD))
            title.setStyleSheet(f"color: {get_token('danger')};")
            layout.addWidget(title)
            self._status_layout.addWidget(banner)
            self._status_layout.addSpacing(SP2)

            for page, issues in all_errors.items():
                self._status_layout.addWidget(_make_issue_card(page, issues, "❌", self.navigate_requested.emit))

        if all_warnings:
            if all_errors:
                self._status_layout.addSpacing(SP4)
            banner = QGroupBox()
            banner.setStyleSheet(
                f"QGroupBox {{ background: transparent; border: 1px solid {get_token('warning')}; "
                f"border-radius: {RADIUS_MD}px; padding: {SP3}px; }}"
            )
            layout = QVBoxLayout(banner)
            label = (
                "⚠️  Warnings - fix errors above before proceeding."
                if all_errors
                else "⚠️  Warnings - Data looks unusual but you can proceed."
            )
            title = QLabel(label)
            title.setFont(_f(FS_MD, FW_BOLD))
            title.setStyleSheet(f"color: {get_token('warning')};")
            layout.addWidget(title)
            self._status_layout.addWidget(banner)
            self._status_layout.addSpacing(SP2)

            for page, issues in all_warnings.items():
                self._status_layout.addWidget(_make_issue_card(page, issues, "🟡", self.navigate_requested.emit))

        if not all_errors and (all_warnings or self._pages):
            btn_container = QWidget()
            btn_lay = QHBoxLayout(btn_container)
            btn_lay.setContentsMargins(0, SP4, 0, 0)
            
            run_btn = QPushButton("Proceed with Calculation ▶")
            run_btn.setFixedHeight(BTN_MD)
            run_btn.setMinimumWidth(240)
            run_btn.setFont(_f(FS_BASE, FW_SEMIBOLD))
            run_btn.setStyleSheet(btn_primary())
            run_btn.setCursor(Qt.PointingHandCursor)
            run_btn.clicked.connect(self._on_proceed)
            
            btn_lay.addStretch()
            btn_lay.addWidget(run_btn)
            btn_lay.addStretch()
            self._status_layout.addWidget(btn_container)

        self._status_layout.addStretch()
        self._save_state("issues", {"errors": all_errors, "warnings": all_warnings})

    def show_success(self):
        self._current_status = "success"
        self._status_args = {}
        self._clear_status()
        banner = QGroupBox()
        banner.setStyleSheet(
            f"QGroupBox {{ background: transparent; border: 1px solid {get_token('success')}; "
            f"border-radius: {RADIUS_MD}px; padding: {SP3}px; }}"
        )
        layout = QVBoxLayout(banner)
        title = QLabel("✅  All checks passed - Ready to calculate.")
        title.setFont(_f(FS_MD, FW_BOLD))
        title.setStyleSheet(f"color: {get_token('success')};")
        layout.addWidget(title)
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
        _log.debug(f"Registered pages: {list(self._pages.keys())}")

    def run_validation(self):
        _log.debug("=== run_validation START ===")

        all_errors = {}
        all_warnings = {}

        ap = self.analysis_period.value()
        if ap <= 0:
            self.analysis_period.setStyleSheet(
                f"border: 1.5px solid {get_token('danger')};"
            )
            all_errors["Analysis Period"] = [
                "Analysis Period is required - please enter a value greater than zero."
            ]
        else:
            self.analysis_period.setStyleSheet("")

        for name, page in self._pages.items():
            _log.debug(f"Validating page: '{name}' ({type(page).__name__})")
            result = page.validate()
            _log.debug(f"  result type={type(result).__name__}  value={result!r}")

            if isinstance(result, dict):
                errors = result.get("errors", [])
                warnings = result.get("warnings", [])
                _log.debug(f"  dict-format => errors={errors}  warnings={warnings}")
                if errors:
                    all_errors[name] = errors
                if warnings:
                    all_warnings[name] = warnings
            else:
                # legacy tuple format (status, issues)
                status, issues = result
                _log.debug(f"  tuple-format => status={status}  issues={issues}")
                if status == ValidationStatus.ERROR and issues:
                    all_errors[name] = issues
                elif status == ValidationStatus.WARNING and issues:
                    all_warnings[name] = issues

        _log.debug(
            f"Validation done => all_errors={list(all_errors.keys())}  all_warnings={list(all_warnings.keys())}"
        )

        if all_errors or all_warnings:
            self.show_results(all_errors, all_warnings)
        else:
            self.show_success()
            self.run_calculation()

    def run_calculation(self):
        _log.debug("=== run_calculation START ===")
        _log.debug(f"self._pages at entry: {list(self._pages.keys())}")

        # Collect data from all pages (fast, main-thread safe)
        all_data = {}
        for name, page in self._pages.items():
            has_get = hasattr(page, "get_data")
            _log.debug(f"  page='{name}'  has_get_data={has_get}")
            if has_get:
                result = page.get_data()
                chunk_key = result["chunk"]
                _log.debug(
                    f"    chunk_key='{chunk_key}'  data_keys={list(result['data'].keys()) if isinstance(result['data'], dict) else type(result['data']).__name__}"
                )
                all_data[chunk_key] = result["data"]

        _log.debug(f"all_data keys collected: {list(all_data.keys())}")
        self._currency = all_data.get('general_info', {}).get('project_currency', "INR")
        print(f"Project Currency: {self._currency}")

        # Show "calculating" state and disable the button immediately
        self._show_calculating()

        # Build worker + thread
        analysis_period_years = int(self.analysis_period.value())
        self._calc_thread = QThread(self)
        self._calc_worker = _LCCAWorker(all_data, analysis_period_years)
        self._calc_worker.moveToThread(self._calc_thread)

        self._calc_thread.started.connect(self._calc_worker.run)
        self._calc_worker.finished.connect(self._on_calc_finished)
        self._calc_worker.errored.connect(self._on_calc_errored)

        # Cleanup when done
        self._calc_worker.finished.connect(self._calc_thread.quit)
        self._calc_worker.errored.connect(self._calc_thread.quit)
        self._calc_thread.finished.connect(self._calc_thread.deleteLater)

        # Bug fix: defer start by one event-loop cycle so Qt can paint the
        # progress bar before the thread begins consuming CPU.
        QTimer.singleShot(0, self._calc_thread.start)
        _log.debug("Calculation thread start deferred.")

    # ── Thread result handlers (called on main thread via queued signal) ──────

    def _on_calc_finished(self, results, all_data, lcc_breakdown):
        _log.debug(f"_on_calc_finished: results type={type(results).__name__}")
        self._stop_timers()
        # Store on main thread - no cross-thread writes needed anymore.
        self._last_all_data = all_data
        self._last_lcc_breakdown = lcc_breakdown
        self._show_calculation_success(results)

    def _on_calc_errored(self, exc, tb):
        _log.debug(f"_on_calc_errored: {type(exc).__name__}: {exc}")
        self._stop_timers()
        self._show_calculation_error(exc, tb)

    def _show_calculation_error(self, error: Exception, tb: str = ""):
        self._current_status = "calc_error"
        self._status_args = {"error": error, "tb": tb}
        self.btn_calculate.setEnabled(True)
        self._clear_status()
        banner = QGroupBox()
        banner.setStyleSheet(
            f"QGroupBox {{ border: 1px solid {get_token('danger')}; "
            f"border-radius: {RADIUS_MD}px; padding: {SP4}px; }}"
        )
        layout = QVBoxLayout(banner)

        # ── Short summary ──────────────────────────────────────────────────
        title = QLabel(f"🛑  Analysis Failed: {type(error).__name__}")
        title.setFont(_f(FS_LG, FW_BOLD))
        title.setStyleSheet(f"color: {get_token('danger')};")
        layout.addWidget(title)

        # Show only the first line of the error message
        first_line = str(error).splitlines()[0] if str(error) else "An unexpected error occurred during calculation."
        msg = QLabel(first_line)
        msg.setWordWrap(True)
        msg.setFont(_f(FS_BASE))
        msg.setStyleSheet(f"color: {get_token('text')}; margin-top: {SP2}px;")
        layout.addWidget(msg)

        if tb:
            layout.addSpacing(SP4)
            # ── Toggle + copy row ──────────────────────────────────────────
            btn_row = QHBoxLayout()
            btn_row.setContentsMargins(0, 0, 0, 0)

            toggle_btn = QPushButton("▸  Show details")
            toggle_btn.setFlat(True)
            toggle_btn.setCursor(Qt.PointingHandCursor)
            toggle_btn.setFont(_f(FS_SM, FW_MEDIUM))
            toggle_btn.setStyleSheet(f"text-align: left; color: {get_token('text_secondary')}; border: none;")
            btn_row.addWidget(toggle_btn)
            btn_row.addStretch()

            copy_btn = QPushButton("Copy Error")
            copy_btn.setFixedHeight(BTN_SM)
            copy_btn.setFixedWidth(100)
            copy_btn.setFont(_f(FS_SM))
            copy_btn.setStyleSheet(btn_ghost())
            copy_btn.clicked.connect(
                lambda: QApplication.clipboard().setText(f"{error}\n\n{tb.strip()}")
            )
            btn_row.addWidget(copy_btn)
            layout.addLayout(btn_row)

            # ── Traceback box (hidden by default) ─────────────────────────
            tb_box = QTextEdit()
            tb_box.setReadOnly(True)
            tb_box.setPlainText(tb.strip())
            tb_box.setFont(_f(FS_SM))
            tb_box.setStyleSheet(
                f"border: 1px solid {get_token('surface_mid')}; "
                f"border-radius: {RADIUS_SM}px; color: {get_token('text_secondary')};"
            )
            tb_box.setFixedHeight(200)
            tb_box.setVisible(False)
            layout.addWidget(tb_box)

            def _toggle():
                visible = not tb_box.isVisible()
                tb_box.setVisible(visible)
                toggle_btn.setText(
                    "▾  Hide details" if visible else "▸  Show details"
                )

            toggle_btn.clicked.connect(_toggle)

        self._status_layout.addWidget(banner)
        self._status_layout.addStretch()

    def _show_calculation_success(self, results):
        self._current_status = "calc_success"
        self._status_args = {}   # results already in self._last_results
        self.btn_calculate.setEnabled(True)
        self._last_results = results
        self._clear_status()

        # ── Success banner + Action buttons ───────────────────────────────
        banner = QGroupBox()
        banner.setStyleSheet(
            f"QGroupBox {{ background: transparent; border: 1px solid {get_token('success')}; "
            f"border-radius: {RADIUS_MD}px; padding: {SP3}px; }}"
        )
        banner_lay = QVBoxLayout(banner)

        top_row = QHBoxLayout()
        title = QLabel("✅  Analysis completed successfully.")
        title.setFont(_f(FS_MD, FW_BOLD))
        title.setStyleSheet(f"color: {get_token('success')};")
        top_row.addWidget(title, stretch=1)
        banner_lay.addLayout(top_row)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(SP3)

        dl_btn = QPushButton("⬇  Export Data")
        dl_btn.setFixedHeight(34)
        dl_btn.setMinimumWidth(150)
        dl_btn.setFont(_f(FS_SM, FW_MEDIUM))
        dl_btn.setStyleSheet(btn_outline())
        dl_btn.setToolTip("Export raw analysis data as .3psLCCAFile")
        dl_btn.clicked.connect(self._download_report)
        actions_row.addWidget(dl_btn)

        pdf_btn = QPushButton("📄  Generate PDF Report")
        pdf_btn.setFixedHeight(34)
        pdf_btn.setMinimumWidth(180)
        pdf_btn.setFont(_f(FS_SM, FW_MEDIUM))
        pdf_btn.setStyleSheet(btn_primary())
        pdf_btn.setToolTip("Create a formatted PDF document with charts and tables")
        pdf_btn.clicked.connect(self._generate_pdf_report)
        actions_row.addWidget(pdf_btn)

        actions_row.addStretch()
        banner_lay.addLayout(actions_row)
        self._status_layout.addWidget(banner)

        # ── Warnings from Core ─────────────────────────────────────────────
        core_warnings = results.get("warnings", [])
        if core_warnings:
            self._status_layout.addSpacing(SP2)
            warn_container = QWidget()
            wv = QVBoxLayout(warn_container)
            wv.setContentsMargins(SP2, 0, 0, 0)
            wv.setSpacing(SP1)
            for w in core_warnings:
                lbl = QLabel(f"⚠️  {w}")
                lbl.setFont(_f(FS_SM))
                lbl.setStyleSheet(f"color: {get_token('warning')};")
                lbl.setWordWrap(True)
                wv.addWidget(lbl)
            self._status_layout.addWidget(warn_container)

        # ── Loading placeholder - replaced once charts are built ──────────
        self._charts_loading_lbl = QLabel("Building charts…")
        self._charts_loading_lbl.setFont(_f(FS_SM))
        self._charts_loading_lbl.setStyleSheet(
            f"color: {get_token('text_secondary')}; font-style: italic;"
        )
        self._status_layout.addWidget(self._charts_loading_lbl)
        self._status_layout.addStretch()

        # Emit now so the project window can react (e.g. unlock navigation)
        # before the heavy widget construction below runs.
        self._has_results = True
        self.calculation_completed.emit()

        # ── Defer heavy widget construction so the banner paints first ─────
        # Each widget is added in its own event-loop cycle to keep the UI
        # responsive. The order matches the visual top-to-bottom layout.
        self._pending_results = results
        self._result_build_steps = [
            lambda r: LCCChartWidget(r, currency=self._currency),
            lambda r: LCCPieWidget(r, currency=self._currency),
            lambda r: LCCBreakdownTable(r, currency=self._currency),
            lambda r: LCCDetailsTable(r, currency=self._currency),
        ]
        QTimer.singleShot(0, self._build_next_result_widget)

    def _build_next_result_widget(self):
        """Add one result widget per event-loop cycle to avoid a UI freeze."""
        if not self._result_build_steps:
            # All done - remove the loading label
            if hasattr(self, "_charts_loading_lbl") and self._charts_loading_lbl:
                self._charts_loading_lbl.hide()
                self._charts_loading_lbl.setParent(None)
                self._charts_loading_lbl = None
            return

        factory = self._result_build_steps.pop(0)
        try:
            widget = factory(self._pending_results)
            # Insert before the trailing stretch (last item)
            stretch_idx = self._status_layout.count() - 1
            self._status_layout.insertWidget(stretch_idx, widget)
        except Exception as e:
            err = QLabel(f"Chart error: {e}\n{traceback.format_exc(limit=4)}")
            err.setStyleSheet("color: gray; font-style: italic;")
            stretch_idx = self._status_layout.count() - 1
            self._status_layout.insertWidget(stretch_idx, err)

        QTimer.singleShot(0, self._build_next_result_widget)

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

    # ── Chunk routing - analysis_period saves to its own chunk ────────────────

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

    # ── Report download ───────────────────────────────────────────────────────

    def _build_export_dict(self) -> dict:
        """Build the export dict shared by both export paths."""
        return DataPreparer.build_export_dict(
            getattr(self, "_last_all_data", {}),
            getattr(self, "_last_lcc_breakdown", {}),
            getattr(self, "_last_results", {}),
        )

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
            export = self._build_export_dict()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Saved", f"Report saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"{type(e).__name__}: {e}\n\n{traceback.format_exc(limit=4)}",
            )

    def _generate_pdf_report(self):
        """Open the section selection dialog and generate a PDF report."""
        dlg = ReportSectionDialog(
            export_dict=self._build_export_dict(),
            parent=self,
        )
        dlg.exec()

    def _on_proceed(self):
        self.run_calculation()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_state(self, status: str, data: dict):
        if self.controller and self.controller.engine:
            self.controller.engine.stage_update(
                chunk_name=self.chunk_name, data={"status": status, "data": data}
            )

    def on_refresh(self):
        if not self.controller or not self.controller.engine:
            _log.debug("on_refresh: no controller/engine, skipping")
            return

        self.refresh_from_engine()

        state = self.controller.engine.fetch_chunk(CHUNK) or {}
        status = state.get("status", "idle")
        data = state.get("data", {})
        _log.debug(
            f"on_refresh: status='{status}'  data_keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
        )
        
        # Try to restore currency if we have all_data in state (though unlikely)
        # or just wait for run_calculation to set it.
        
        if status == "issues":
            self.show_results(data.get("errors", {}), data.get("warnings", {}))
        elif status == "success":
            self.show_success()
        else:
            self._show_idle()
