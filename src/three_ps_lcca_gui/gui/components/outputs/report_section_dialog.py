"""
Report Section Selection Dialog - Hierarchical tree for choosing PDF report sections.

Adapted from lcca_gui.py SectionTreeWidget for use as a modal dialog within
the main 3psLCCA GUI application.
"""

import sys
import os
import json
import shutil
import tempfile
import traceback

# ─────────────────────────────────────────────────────────────────────────────
# Fix sys.path so report modules can be imported
# ─────────────────────────────────────────────────────────────────────────────
_project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_report_dir = os.path.join(_project_root, "report")
for p in [_report_dir, _project_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QApplication,
    QFileDialog,
    QSizePolicy,
    QWidget,
    QStyle,
)
from PySide6.QtCore import Qt, Signal, QThread, QSize, QRect
from PySide6.QtGui import QPainter, QColor, QPalette

from three_ps_lcca_gui.gui.themes import get_token, theme_manager
from three_ps_lcca_gui.gui.theme import (
    FS_DISP, FS_MD, FS_BASE, FS_SM,
    FW_BOLD, FW_SEMIBOLD, FW_MEDIUM, FW_NORMAL,
    SP4, RADIUS_MD, BTN_LG
)
from three_ps_lcca_gui.gui.styles import font as _f, btn_primary, btn_outline

# ─────────────────────────────────────────────────────────────────────────────
# Config keys
# ─────────────────────────────────────────────────────────────────────────────
from lcca_template import (
    KEY_SHOW_BRIDGE_DESC,
    KEY_SHOW_FINANCIAL,
    KEY_SHOW_CONSTRUCTION,
    KEY_SHOW_LCC_ASSUMPTIONS,
    KEY_SHOW_USE_STAGE,
    KEY_SHOW_AVG_TRAFFIC,
    KEY_SHOW_ROAD_TRAFFIC,
    KEY_SHOW_PEAK_HOUR,
    KEY_SHOW_HUMAN_INJURY,
    KEY_SHOW_VEHICLE_DAMAGE,
    KEY_SHOW_TYRE_COST,
    KEY_SHOW_FUEL_OIL,
    KEY_SHOW_NEW_VEHICLE,
    KEY_SHOW_SOCIAL_CARBON,
    KEY_SHOW_MATERIAL_EMISSION,
    KEY_SHOW_USE_EMISSION,
    KEY_SHOW_VEHICLE_EMISSION,
    KEY_SHOW_ONSITE_EMISSION,
    KEY_SHOW_TRANSPORT_EMISSION,
)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION_MAP - hierarchical structure of report sections/subsections
# ─────────────────────────────────────────────────────────────────────────────

SECTION_MAP = {
    "Introduction": [],
    "Input data": [
        "Bridge geometry and description",
        "User note",
        "Construction data",
        "Traffic data",
        "Environmental input data",
    ],
    "LCCA results": [],
}

# ─────────────────────────────────────────────────────────────────────────────
# MAPPING: Subsection names to their config keys and table labels
# ─────────────────────────────────────────────────────────────────────────────

SUBSECTION_TABLE_MAP = {
    "Bridge geometry and description": [
        ("Table 2-1: Bridge description", KEY_SHOW_BRIDGE_DESC),
    ],
    "User note": [
        ("Table 2-2: Financial Data", KEY_SHOW_FINANCIAL),
    ],
    "Construction data": [
        ("Table 2-3: Construction materials", KEY_SHOW_CONSTRUCTION),
        ("Table 2-4: LCC assumptions", KEY_SHOW_LCC_ASSUMPTIONS),
        ("Table 2-5: Use stage details", KEY_SHOW_USE_STAGE),
    ],
    "Traffic data": [
        ("Table 2-6: Average daily traffic", KEY_SHOW_AVG_TRAFFIC),
        ("Table 2-7: Road and traffic data", KEY_SHOW_ROAD_TRAFFIC),
        ("Table 2-8: Peak hour distribution", KEY_SHOW_PEAK_HOUR),
        ("Table 2-9: Human injury cost", KEY_SHOW_HUMAN_INJURY),
        ("Table 2-10: Vehicle damage cost", KEY_SHOW_VEHICLE_DAMAGE),
        ("Table 2-11: Tyre cost data", KEY_SHOW_TYRE_COST),
        ("Table 2-12: Fuel, oil and grease", KEY_SHOW_FUEL_OIL),
        ("Table 2-13: Cost of new vehicle", KEY_SHOW_NEW_VEHICLE),
    ],
    "Environmental input data": [
        ("Table 2-14: Social cost of carbon", KEY_SHOW_SOCIAL_CARBON),
        ("Table 2-15: Material emission factors", KEY_SHOW_MATERIAL_EMISSION),
        ("Table 2-16: Use stage emissions", KEY_SHOW_USE_EMISSION),
        ("Table 2-17: Vehicle emission factors", KEY_SHOW_VEHICLE_EMISSION),
        ("Table 2-18: On-site emissions", KEY_SHOW_ONSITE_EMISSION),
        ("Table 2-19: Transport emissions", KEY_SHOW_TRANSPORT_EMISSION),
    ],
}

# Section-level toggle keys (for sections without tables)
KEY_SHOW_INTRODUCTION = "show_introduction"
KEY_SHOW_LCCA_RESULTS = "show_lcca_results"


# ==============================================================================
# CLASS: SectionTreeWidget - Interactive tree for selecting report sections
# ==============================================================================


class SectionTreeWidget(QTreeWidget):
    """
    Professional tree widget for selecting report sections.
    Uses custom drawRow for polished hover/select effects matching the sidebar.
    """

    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tree_sections")
        self.setHeaderLabel("Report Sections")
        self.itemChanged.connect(self.on_item_changed)
        
        self.setIndentation(28)
        self.setAnimated(True)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        
        # Style the header and basic properties
        self._apply_theme_style()
        theme_manager().theme_changed.connect(self._apply_theme_style)

    def _apply_theme_style(self):
        """Apply theme-consistent styling to the tree widget."""
        # Sync Base/AlternateBase so viewport background matches window
        p = self.palette()
        p.setColor(QPalette.Base, p.color(QPalette.Window))
        self.setPalette(p)

        self.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
                font-family: 'Ubuntu';
                font-size: {FS_BASE}pt;
                color: {get_token("text")};
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 6px 0;
                border: none;
                color: {get_token("text")};
            }}

            /* ── Branch arrows ───────────────────────────────────────── */
            QTreeWidget::branch {{
                background: transparent;
            }}
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {{
                image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M8 5v14l11-7z' fill='{get_token("text_secondary").replace("#", "%23")}'/%3E%3C/svg%3E");
            }}
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {{
                image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M7 10l5 5 5-5z' fill='{get_token("text_secondary").replace("#", "%23")}'/%3E%3C/svg%3E");
            }}

            /* ── Checkboxes ───────────────────────────────────────────── */
            QTreeWidget::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {get_token("surface_mid")};
                border-radius: 4px;
                background-color: {get_token("base")};
            }}
            QTreeWidget::indicator:checked {{
                background-color: {get_token("primary")};
                border-color: {get_token("primary")};
                image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z' fill='white'/%3E%3C/svg%3E");
            }}
            QTreeWidget::indicator:indeterminate {{
                background-color: {get_token("primary")};
                border-color: {get_token("primary")};
                image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Crect x='4' y='11' width='16' height='2' fill='white'/%3E%3C/svg%3E");
            }}
            QTreeWidget::indicator:unchecked:hover {{
                border-color: {get_token("primary")};
            }}

            /* ── Header ──────────────────────────────────────────────── */
            QHeaderView::section {{
                background-color: {get_token("surface")};
                color: {get_token("text")};
                font-weight: {FW_SEMIBOLD};
                padding: 8px 12px;
                border: none;
                border-bottom: 2px solid {get_token("surface_mid")};
                font-size: 11px;
                text-transform: uppercase;
            }}
        """)

    def _row_state(self, index):
        """Return (is_selected, is_hovered) for a model index."""
        item = self.itemFromIndex(index)
        is_sel = item in self.selectedItems()
        is_hovered = index == self.indexAt(
            self.viewport().mapFromGlobal(self.cursor().pos())
        )
        return is_sel, is_hovered

    def drawRow(self, painter: QPainter, option, index):
        """Pre-paint full-width background for professional hover/selection."""
        is_sel, is_hovered = self._row_state(index)
        full = option.rect

        painter.save()
        painter.setPen(Qt.NoPen)
        # Background fill
        painter.setBrush(self.palette().window())
        painter.drawRect(full)
        
        # Hover tint
        if is_hovered and not is_sel:
            tint = QColor(get_token("primary")); tint.setAlpha(11)
            painter.setBrush(tint); painter.drawRect(full)
        
        # Selection tint
        if is_sel:
            tint = QColor(get_token("primary")); tint.setAlpha(22)
            painter.setBrush(tint); painter.drawRect(full)
        
        painter.restore()

        # Strip standard selection states so Qt doesn't paint its own (often harsh) highlight
        option.state &= ~(QStyle.State_Selected | QStyle.State_MouseOver | QStyle.State_HasFocus)
        super().drawRow(painter, option, index)

    def build_from_sections(self, section_map, table_map):
        """Populate tree widget from SECTION_MAP and SUBSECTION_TABLE_MAP."""
        self.clear()
        if not isinstance(section_map, dict):
            return

        from PySide6.QtGui import QFont as _QFont, QColor as _QColor
        font_section = _QFont("Ubuntu", FS_BASE); font_section.setWeight(_QFont.Weight.DemiBold)
        font_sub    = _QFont("Ubuntu", FS_BASE)
        font_table  = _QFont("Ubuntu", FS_SM)
        col_section = _QColor(get_token("text"))
        col_sub     = _QColor(get_token("text"))
        col_table   = _QColor(get_token("text_secondary"))

        for section_name, subsections in section_map.items():
            section_item = QTreeWidgetItem(self, [section_name])
            section_item.setFlags(section_item.flags() | Qt.ItemIsUserCheckable)
            section_item.setCheckState(0, Qt.Checked)
            section_item.setFont(0, font_section)
            section_item.setForeground(0, col_section)
            if section_name == "Introduction":
                section_item.setData(0, Qt.UserRole, KEY_SHOW_INTRODUCTION)
            elif section_name == "LCCA results":
                section_item.setData(0, Qt.UserRole, KEY_SHOW_LCCA_RESULTS)

            if isinstance(subsections, (list, tuple)):
                for subsection in subsections:
                    sub_item = QTreeWidgetItem(section_item, [str(subsection)])
                    sub_item.setFlags(sub_item.flags() | Qt.ItemIsUserCheckable)
                    sub_item.setCheckState(0, Qt.Checked)
                    sub_item.setFont(0, font_sub)
                    sub_item.setForeground(0, col_sub)

                    if subsection in table_map:
                        for label, config_key in table_map[subsection]:
                            table_item = QTreeWidgetItem(sub_item, [label])
                            table_item.setFlags(
                                table_item.flags() | Qt.ItemIsUserCheckable
                            )
                            table_item.setCheckState(0, Qt.Checked)
                            table_item.setFont(0, font_table)
                            table_item.setForeground(0, col_table)
                            table_item.setData(0, Qt.UserRole, config_key)

        self.expandAll()

    def on_item_changed(self, item, column):
        """Handle checkbox changes with parent-child propagation."""
        if column == 0:
            self.blockSignals(True)
            state = item.checkState(0)
            self._set_children_state(item, state)
            self.update_parent_state(item)
            self.blockSignals(False)
            self.selectionChanged.emit()

    def _set_children_state(self, item, state):
        """Recursively set check state on all descendants."""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_state(child, state)

    def update_parent_state(self, item):
        """Update parent checkbox state based on children states."""
        parent = item.parent()
        if parent is None:
            return

        total_children = parent.childCount()
        checked_children = sum(
            1
            for i in range(total_children)
            if parent.child(i).checkState(0) == Qt.Checked
        )

        if checked_children == total_children:
            parent.setCheckState(0, Qt.Checked)
        elif checked_children == 0:
            parent.setCheckState(0, Qt.Unchecked)
        else:
            parent.setCheckState(0, Qt.PartiallyChecked)

        self.update_parent_state(parent)

    def get_config(self):
        """Build config dict from current tree selection state."""
        config = {}
        self._collect_config(self.invisibleRootItem(), config)
        # Ensure section-level keys are always present
        config.setdefault(KEY_SHOW_INTRODUCTION, True)
        config.setdefault(KEY_SHOW_LCCA_RESULTS, True)
        return config

    def _collect_config(self, item, config):
        """Recursively collect config flags from tree items."""
        for i in range(item.childCount()):
            child = item.child(i)
            config_key = child.data(0, Qt.UserRole)
            if config_key:
                config[config_key] = child.checkState(0) == Qt.Checked
            self._collect_config(child, config)


# ==============================================================================
# CLASS: _PdfGenWorker - Background thread for PDF generation
# ==============================================================================


class _PdfGenWorker(QThread):
    """Runs PDF generation on a background thread to avoid freezing the UI."""

    finished = Signal(str)        # emitted with final PDF path on success
    errored = Signal(str, str)    # (error_msg, tex_path_or_empty) — work dir kept alive when tex_path set

    def __init__(self, export_dict, config, output_dir):
        super().__init__()
        self._export_dict = export_dict
        self._config = config
        self._output_dir = output_dir

    def run(self):
        work_dir = tempfile.mkdtemp(prefix="3psLCCA_")
        try:
            stem = "LCCA_Report"
            work_stem = os.path.join(work_dir, stem)

            # Write temp JSON
            tmp_json = os.path.join(work_dir, "input.3psLCCAFile")
            with open(tmp_json, "w", encoding="utf-8") as f:
                json.dump(self._export_dict, f, indent=2, ensure_ascii=False)

            try:
                from lcca_generate import generate_report
                generate_report(
                    work_stem, input_json=tmp_json, config_override=self._config,
                    output_dir=work_dir,
                )
            finally:
                try:
                    os.remove(tmp_json)
                except OSError:
                    pass

            work_pdf = work_stem + ".pdf"
            if os.path.exists(work_pdf):
                final_pdf = os.path.join(self._output_dir, stem + ".pdf")
                shutil.copy2(work_pdf, final_pdf)
                shutil.rmtree(work_dir, ignore_errors=True)
                self.finished.emit(final_pdf)
            else:
                tex_path = work_stem + ".tex"
                if os.path.exists(tex_path):
                    # Keep work_dir alive — dialog cleans it up after export/close
                    self.errored.emit(
                        "PDF compilation failed — LaTeX could not produce a PDF.\n"
                        "You can export the .tex file and compile it manually:\n"
                        "  pdflatex LCCA_Report.tex",
                        tex_path,
                    )
                else:
                    shutil.rmtree(work_dir, ignore_errors=True)
                    self.errored.emit(
                        "Report generation completed but no output file was found.", ""
                    )

        except Exception as e:
            shutil.rmtree(work_dir, ignore_errors=True)
            self.errored.emit(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}", "")


# ==============================================================================
# CLASS: ReportSectionDialog - Modal dialog for section selection + generation
# ==============================================================================


class ReportSectionDialog(QDialog):
    """
    Modal dialog that lets the user select which sections/tables to include
    in the PDF report, then generates it via generate_report().
    """

    def __init__(self, export_dict: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Report")
        self.setObjectName("report_section_dialog")
        self.resize(600, 700)
        self._export_dict = export_dict
        self._worker = None
        self._init_ui()

    def _init_ui(self):
        """Build the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setSpacing(16)

        # Title
        self.lbl_title = QLabel("Report Customization")
        self.lbl_title.setFont(_f(FS_DISP, FW_BOLD))
        self.lbl_title.setStyleSheet(f"color: {get_token('primary')};")
        self.lbl_title.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel("Select the sections and data tables to include in your final LCCA PDF report.")
        self.lbl_subtitle.setFont(_f(FS_BASE, FW_NORMAL))
        self.lbl_subtitle.setStyleSheet(f"color: {get_token('text_secondary')};")
        self.lbl_subtitle.setWordWrap(True)
        main_layout.addWidget(self.lbl_subtitle)

        # Separator-like gap
        main_layout.addSpacing(8)

        # Tree widget container
        tree_container = QWidget()
        tree_container.setObjectName("tree_container")
        tree_container.setStyleSheet(f"""
            QWidget#tree_container {{
                background-color: {get_token("base")};
                border: 1px solid {get_token("surface_mid")};
                border-radius: {RADIUS_MD}px;
            }}
        """)
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)

        # Tree widget
        self.tree_sections = SectionTreeWidget()
        self.tree_sections.build_from_sections(SECTION_MAP, SUBSECTION_TABLE_MAP)
        self.tree_sections.selectionChanged.connect(self.on_selection_changed)
        tree_layout.addWidget(self.tree_sections)

        main_layout.addWidget(tree_container, stretch=1)

        # Status and Buttons bottom area
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 8, 0, 0)
        
        # Status label
        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_f(FS_SM, FW_MEDIUM))
        self.lbl_status.setStyleSheet(f"color: {get_token('text_secondary')};")
        bottom_layout.addWidget(self.lbl_status)
        
        bottom_layout.addStretch()

        # Buttons
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(110)
        self.btn_cancel.setMinimumHeight(BTN_LG)
        self.btn_cancel.setStyleSheet(btn_outline())
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_save_as = QPushButton("Generate PDF")
        self.btn_save_as.setFixedWidth(170)
        self.btn_save_as.setMinimumHeight(BTN_LG)
        self.btn_save_as.setStyleSheet(btn_primary())
        self.btn_save_as.clicked.connect(self.generate_report_with_path)
        bottom_layout.addWidget(self.btn_save_as)

        main_layout.addLayout(bottom_layout)
        
        self.on_selection_changed()

    def on_selection_changed(self):
        """Update status label when tree selection changes."""
        config = self.tree_sections.get_config()
        selected_count = sum(1 for v in config.values() if v)
        total_count = len(config)
        self.lbl_status.setText(f"{selected_count} of {total_count} sections selected")

    def _set_ui_enabled(self, enabled):
        """Enable/disable UI controls during generation."""
        self.btn_save_as.setEnabled(enabled)
        self.btn_cancel.setEnabled(enabled)
        self.tree_sections.setEnabled(enabled)
        if enabled:
            self.btn_save_as.setText("Generate PDF")
        else:
            self.btn_save_as.setText("Generating...")

    def generate_report_with_path(self):
        """Ask user for save location, then generate PDF."""
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF Report",
            "LCCA_Report.pdf",
            "PDF Files (*.pdf)",
        )
        if not save_path:
            return

        # Ensure .pdf extension
        if not save_path.lower().endswith(".pdf"):
            save_path += ".pdf"

        self._generate_pdf(os.path.dirname(save_path), os.path.splitext(os.path.basename(save_path))[0])

    def _generate_pdf(self, output_dir, filename):
        """Launch background PDF generation."""
        config = self.tree_sections.get_config()
        export = self._export_dict

        self._set_ui_enabled(False)
        QApplication.processEvents()

        self._worker = _PdfGenWorker(export, config, output_dir)
        self._worker.finished.connect(self._on_pdf_success)
        self._worker.errored.connect(self._on_pdf_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.errored.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_pdf_success(self, pdf_path):
        """Handle successful PDF generation."""
        self._set_ui_enabled(True)
        QMessageBox.information(
            self,
            "Report Saved",
            f"Report saved to:\n{pdf_path}",
        )
        # Attempt to open the PDF
        if os.path.exists(pdf_path):
            os.startfile(pdf_path)
        self.accept()

    def _on_pdf_error(self, error_msg: str, tex_path: str):
        """Handle PDF generation error — offer .tex export when available."""
        self._set_ui_enabled(True)

        if not tex_path:
            QMessageBox.critical(self, "PDF Generation Failed", error_msg)
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("PDF Compilation Failed")
        dlg.setMinimumWidth(460)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        lbl = QLabel(error_msg)
        lbl.setWordWrap(True)
        lbl.setFont(_f(FS_BASE))
        lay.addWidget(lbl)

        note = QLabel(
            "The .tex source file is ready. Export it, then run:\n"
            "  <b>pdflatex LCCA_Report.tex</b>"
        )
        note.setTextFormat(Qt.RichText)
        note.setWordWrap(True)
        note.setFont(_f(FS_SM))
        note.setStyleSheet(f"color: {get_token('text_secondary')};")
        lay.addWidget(note)

        btns = QDialogButtonBox()
        export_btn = btns.addButton("Export .tex File…", QDialogButtonBox.AcceptRole)
        btns.addButton("Close", QDialogButtonBox.RejectRole)
        lay.addWidget(btns)

        work_dir = os.path.dirname(tex_path)

        def _cleanup():
            shutil.rmtree(work_dir, ignore_errors=True)

        def _export():
            dest, _ = QFileDialog.getSaveFileName(
                dlg, "Save .tex File", "LCCA_Report.tex", "LaTeX Files (*.tex)"
            )
            if dest:
                if not dest.lower().endswith(".tex"):
                    dest += ".tex"
                try:
                    shutil.copy2(tex_path, dest)
                    QMessageBox.information(
                        dlg, "Saved",
                        f"Saved to:\n{dest}\n\nCompile with:\n  pdflatex \"{dest}\""
                    )
                    dlg.accept()
                except Exception as e:
                    QMessageBox.critical(dlg, "Export Failed", str(e))

        export_btn.clicked.connect(_export)
        btns.rejected.connect(dlg.reject)
        dlg.finished.connect(lambda _: _cleanup())
        dlg.exec()
