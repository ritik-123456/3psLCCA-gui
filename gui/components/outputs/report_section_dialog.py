"""
Report Section Selection Dialog — Hierarchical tree for choosing PDF report sections.

Adapted from lcca_gui.py SectionTreeWidget for use as a modal dialog within
the main 3psLCCA GUI application.
"""

import sys
import os
import json
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
)
from PySide6.QtCore import Qt, Signal, QThread

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
# SECTION_MAP — hierarchical structure of report sections/subsections
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
# CLASS: SectionTreeWidget — Interactive tree for selecting report sections
# ==============================================================================


class SectionTreeWidget(QTreeWidget):
    """Custom tree widget for selecting report sections and subsections."""

    selectionChanged = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("tree_sections")
        self.setHeaderLabel("Report Sections")
        self.itemChanged.connect(self.on_item_changed)

    def build_from_sections(self, section_map, table_map):
        """Populate tree widget from SECTION_MAP and SUBSECTION_TABLE_MAP."""
        self.clear()
        if not isinstance(section_map, dict):
            return

        for section_name, subsections in section_map.items():
            section_item = QTreeWidgetItem(self, [section_name])
            section_item.setFlags(section_item.flags() | Qt.ItemIsUserCheckable)
            section_item.setCheckState(0, Qt.Checked)
            # Store section-level config key
            if section_name == "Introduction":
                section_item.setData(0, Qt.UserRole, KEY_SHOW_INTRODUCTION)
            elif section_name == "LCCA results":
                section_item.setData(0, Qt.UserRole, KEY_SHOW_LCCA_RESULTS)

            if isinstance(subsections, (list, tuple)):
                for subsection in subsections:
                    sub_item = QTreeWidgetItem(section_item, [str(subsection)])
                    sub_item.setFlags(sub_item.flags() | Qt.ItemIsUserCheckable)
                    sub_item.setCheckState(0, Qt.Checked)

                    if subsection in table_map:
                        for label, config_key in table_map[subsection]:
                            table_item = QTreeWidgetItem(sub_item, [label])
                            table_item.setFlags(
                                table_item.flags() | Qt.ItemIsUserCheckable
                            )
                            table_item.setCheckState(0, Qt.Checked)
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
# CLASS: _PdfGenWorker — Background thread for PDF generation
# ==============================================================================


class _PdfGenWorker(QThread):
    """Runs PDF generation on a background thread to avoid freezing the UI."""

    finished = Signal(str)  # emitted with PDF path on success
    errored = Signal(str)  # emitted with error message on failure

    def __init__(self, export_dict, config, output_dir):
        super().__init__()
        self._export_dict = export_dict
        self._config = config
        self._output_dir = output_dir

    def run(self):
        try:
            # Write temp JSON
            tmp_fd, tmp_json = tempfile.mkstemp(
                suffix=".3psLCCAFile", prefix="lcca_report_"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(self._export_dict, f, indent=2, ensure_ascii=False)

                # Import here to avoid blocking UI startup
                from lcca_generate import generate_report

                pdf_path = os.path.join(self._output_dir, "LCCA_Report")
                generate_report(
                    pdf_path, input_json=tmp_json, config_override=self._config,
                    output_dir=self._output_dir,
                )
            finally:
                if os.path.exists(tmp_json):
                    try:
                        os.remove(tmp_json)
                    except OSError:
                        pass

            final_pdf = pdf_path + ".pdf"
            if os.path.exists(final_pdf):
                # Clean up intermediate files
                for ext in [".tex", ".aux", ".log", ".out", ".fls", ".fdb_latexmk"]:
                    f = pdf_path + ext
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                self.finished.emit(final_pdf)
            else:
                # Check if .tex was generated instead
                tex_path = pdf_path + ".tex"
                if os.path.exists(tex_path):
                    self.errored.emit(
                        "PDF compilation failed but .tex file was saved.\n"
                        "Check your LaTeX installation and try compiling manually:\n"
                        f"  pdflatex {tex_path}"
                    )
                else:
                    self.errored.emit("Report generation completed but no output file was found.")

        except Exception as e:
            tb = traceback.format_exc()
            self.errored.emit(f"{type(e).__name__}: {e}\n\n{tb}")


# ==============================================================================
# CLASS: ReportSectionDialog — Modal dialog for section selection + generation
# ==============================================================================


class ReportSectionDialog(QDialog):
    """
    Modal dialog that lets the user select which sections/tables to include
    in the PDF report, then generates it via generate_report().
    """

    def __init__(self, build_export_dict, all_data, lcc_breakdown, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LCCA Report Customization")
        self.setObjectName("report_section_dialog")
        self.resize(650, 750)
        self._build_export_dict = build_export_dict
        self._all_data = all_data
        self._lcc_breakdown = lcc_breakdown
        self._results = results
        self._worker = None
        self._init_ui()

    def _init_ui(self):
        """Build the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # Title
        self.lbl_title = QLabel("Select Report Sections to Include")
        self.lbl_title.setObjectName("lbl_title")
        self.lbl_title.setStyleSheet(
            "font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #285A23;"
        )
        self.lbl_title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.lbl_title)

        # Scroll area for tree
        scroll_area = QScrollArea()
        scroll_area.setObjectName("scroll_sections")
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(
            "QScrollArea { border: 1px solid #E0E0E0; border-radius: 5px; "
            "background-color: #FAFAFA; }"
        )

        # Tree widget
        self.tree_sections = SectionTreeWidget()
        self.tree_sections.setStyleSheet("""
            QTreeWidget {
                font-size: 13px;
                border: none;
                background-color: #FAFAFA;
                color: #333333;
            }
            QTreeWidget::item {
                padding: 4px 0;
                color: #333333;
            }
            QTreeWidget::item:selected {
                background-color: #E8EFC4;
                color: #333333;
            }
            QHeaderView::section {
                background-color: #99A924;
                color: white;
                font-weight: bold;
                padding: 6px;
                border: none;
            }
        """)
        self.tree_sections.build_from_sections(SECTION_MAP, SUBSECTION_TABLE_MAP)
        self.tree_sections.selectionChanged.connect(self.on_selection_changed)

        scroll_area.setWidget(self.tree_sections)
        main_layout.addWidget(scroll_area)

        # Status label
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("lbl_status")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("font-size: 12px; color: #555555;")
        main_layout.addWidget(self.lbl_status)
        self.on_selection_changed()

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_save_as = QPushButton("Save PDF As...")
        self.btn_save_as.setObjectName("btn_save_as")
        self.btn_save_as.clicked.connect(self.generate_report_with_path)
        self.btn_save_as.setMinimumHeight(45)
        self.btn_save_as.setStyleSheet("""
            QPushButton#btn_save_as {
                background-color: #99A924;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                padding: 10px 20px;
            }
            QPushButton#btn_save_as:hover {
                background-color: #88951F;
            }
            QPushButton#btn_save_as:pressed {
                background-color: #285A23;
            }
            QPushButton#btn_save_as:disabled {
                background-color: #d0d0d0;
                color: #888888;
            }
        """)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setMinimumHeight(45)
        self.btn_cancel.setStyleSheet("""
            QPushButton#btn_cancel {
                background-color: #d0d0d0;
                color: #333333;
                font-size: 14px;
                border-radius: 5px;
                padding: 10px 30px;
            }
            QPushButton#btn_cancel:hover {
                background-color: #c0c0c0;
            }
            QPushButton#btn_cancel:disabled {
                background-color: #e0e0e0;
                color: #aaa;
            }
        """)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save_as)
        btn_layout.addStretch()

        main_layout.addLayout(btn_layout)

    def on_selection_changed(self):
        """Update status label when tree selection changes."""
        config = self.tree_sections.get_config()
        selected_count = sum(1 for v in config.values() if v)
        total_count = len(config)
        self.lbl_status.setText(f"{selected_count} of {total_count} tables selected")

    def _set_ui_enabled(self, enabled):
        """Enable/disable UI controls during generation."""
        self.btn_save_as.setEnabled(enabled)
        self.btn_cancel.setEnabled(enabled)
        self.tree_sections.setEnabled(enabled)
        if enabled:
            self.btn_save_as.setText("Save PDF As...")
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
        export = self._build_export_dict(self._all_data, self._lcc_breakdown, self._results)

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

    def _on_pdf_error(self, error_msg):
        """Handle PDF generation error."""
        self._set_ui_enabled(True)
        QMessageBox.critical(self, "Error", error_msg)


