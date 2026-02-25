import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QLabel,
    QPushButton,
    QStatusBar,
    QMenuBar,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QSplitter,
)
from PySide6.QtGui import QAction

from gui.components.save_status_bar import SaveStatusBar
from gui.components.logs import Logs
from gui.components.global_info.main import GeneralInfo
from gui.components.bridge_data.main import BridgeData
from gui.components.structure.main import StructureTabView
from gui.components.traffic_data.main import TrafficData
from gui.components.financial_data.main import FinancialData
from gui.components.carbon_emission.main import CarbonEmissionTabView
from gui.components.maintenance.main import Maintenance
from gui.components.recycling.main import Recycling
from gui.components.demolition.main import Demolition
from gui.components.home_page import HomePage


class ProjectWindow(QMainWindow):
    def __init__(self, manager, controller=None):
        super().__init__()
        self.manager = manager

        if controller is not None:
            self.controller = controller
        else:
            from gui.project_controller import ProjectController

            self.controller = ProjectController()

        self.project_id = None

        self.setWindowTitle("LCCA - Home")
        self.resize(1100, 750)

        self.main_stack = QStackedWidget()
        self.setCentralWidget(self.main_stack)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._setup_home_ui()  # index 0
        self._setup_project_ui()  # index 1

        # Wire controller signals
        self.controller.fault_occurred.connect(self._on_fault)
        self.controller.project_loaded.connect(self._on_project_loaded)
        self.controller.sync_completed.connect(
            lambda: self.status_bar.showMessage("All changes saved.", 3000)
        )
        self.controller.dirty_changed.connect(
            lambda d: self.status_bar.showMessage("Unsaved changes...") if d else None
        )

        self.show_home()

    # --------------------------------------------------------------------------
    # HOME SCREEN
    # --------------------------------------------------------------------------

    def _setup_home_ui(self):
        self.home_widget = HomePage(manager=self.manager)
        self.main_stack.addWidget(self.home_widget)  # index 0

    # --------------------------------------------------------------------------
    # PROJECT VIEW
    # --------------------------------------------------------------------------

    def _setup_project_ui(self):
        self.project_widget = QWidget()
        master_layout = QVBoxLayout(self.project_widget)
        master_layout.setContentsMargins(0, 0, 0, 0)
        master_layout.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(4, 2, 4, 2)
        top_bar_layout.setSpacing(6)

        self.menubar = QMenuBar()

        # File menu
        self.menuFile = QMenu("&File", self.menubar)

        for label in ["New", "Open"]:
            self.menuFile.addAction(QAction(label, self))

        self.menuFile.addSeparator()

        self.actionSave = QAction("Save", self)
        self.menuFile.addAction(self.actionSave)

        for label in ["Save As...", "Create a Copy", "Print"]:
            self.menuFile.addAction(QAction(label, self))

        self.menuFile.addSeparator()

        for label in ["Rename", "Export", "Version History", "Info"]:
            self.menuFile.addAction(QAction(label, self))

        # Help menu
        self.menuHelp = QMenu("&Help", self.menubar)
        for label in ["Contact us", "Feedback"]:
            self.menuHelp.addAction(QAction(label, self))
        self.menuHelp.addSeparator()
        for label in ["Video Tutorials", "Join our Community"]:
            self.menuHelp.addAction(QAction(label, self))

        home_action = QAction("Home", self)
        home_action.triggered.connect(self.show_home)

        self.log_action = QAction("Logs", self)

        self.menubar.addAction(home_action)
        self.menubar.addMenu(self.menuFile)
        self.menubar.addMenu(self.menuHelp)
        self.menubar.addAction(QAction("Tutorials", self))
        self.menubar.addAction(self.log_action)

        top_bar_layout.addWidget(self.menubar)
        top_bar_layout.addStretch()

        self.save_status_bar = SaveStatusBar(controller=self.controller)
        top_bar_layout.addWidget(self.save_status_bar)
        top_bar_layout.addWidget(QPushButton("Calculate"))
        top_bar_layout.addWidget(QPushButton("Lock"))

        master_layout.setMenuBar(top_bar)

        # ── Sidebar + content stack ───────────────────────────────────────────
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.sidebar = QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setMinimumWidth(80)

        sidebar_info = {
            "General Information": {},
            "Bridge Data": {},
            "Input Parameters": {
                "Construction Work Data": [
                    "Foundation",
                    "Super Structure",
                    "Sub Structure",
                    "Miscellaneous",
                ],
                "Traffic Data": [],
                "Financial Data": [],
                "Carbon Emission Data": [
                    "Material Emissions",
                    "Transportation Emissions",
                    "Machinery Emissions",
                    "Traffic Diversion Emissions",
                    "Social Cost of Carbon",
                ],
                "Maintenance and Repair": [],
                "Recycling": [],
                "Demolition": [],
            },
            "Outputs": {},
        }

        for header, subheaders in sidebar_info.items():
            top_item = QTreeWidgetItem(self.sidebar)
            top_item.setText(0, header)
            for subheader, subitems in subheaders.items():
                sub_item = QTreeWidgetItem(top_item)
                sub_item.setText(0, subheader)
                for subitem in subitems:
                    leaf = QTreeWidgetItem(sub_item)
                    leaf.setText(0, subitem)

        self.sidebar.expandAll()

        self.content_stack = QStackedWidget()

        self.metadata_page = QLabel()
        self.metadata_page.setAlignment(Qt.AlignCenter)

        self.logs_page = Logs(controller=self.controller)

        self.widget_map = {
            "General Information": GeneralInfo(controller=self.controller),
            "Bridge Data": BridgeData(controller=self.controller),
            "Construction Work Data": StructureTabView(controller=self.controller),
            "Traffic Data": TrafficData(controller=self.controller),
            "Financial Data": FinancialData(controller=self.controller),
            "Carbon Emission Data": CarbonEmissionTabView(controller=self.controller),
            "Maintenance and Repair": Maintenance(controller=self.controller),
            "Recycling": Recycling(controller=self.controller),
            "Demolition": Demolition(controller=self.controller),
            "Outputs": self.metadata_page,
        }

        for widget in self.widget_map.values():
            self.content_stack.addWidget(widget)
        self.content_stack.addWidget(self.logs_page)

        self.log_action.triggered.connect(
            lambda: self.content_stack.setCurrentWidget(self.logs_page)
        )
        self.sidebar.itemPressed.connect(self._select_sidebar)

        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.content_stack)
        self.splitter.setSizes([220, 880])

        master_layout.addWidget(self.splitter, stretch=1)
        self.main_stack.addWidget(self.project_widget)  # index 1

    def _select_sidebar(self, item: QTreeWidgetItem):
        header = item.text(0)
        parent = item.parent()
        item.setExpanded(True)

        if header in self.widget_map:
            self.content_stack.setCurrentWidget(self.widget_map[header])
        elif parent:
            parent_header = parent.text(0)
            if parent_header == "Construction Work Data":
                self.content_stack.setCurrentWidget(
                    self.widget_map["Construction Work Data"]
                )
                self.widget_map["Construction Work Data"].select_tab(header)
            elif parent_header == "Carbon Emission Data":
                self.content_stack.setCurrentWidget(
                    self.widget_map["Carbon Emission Data"]
                )
                self.widget_map["Carbon Emission Data"].select_tab(header)

    # --------------------------------------------------------------------------
    # VIEW SWITCHING
    # --------------------------------------------------------------------------

    def show_home(self):
        self.setWindowTitle("LCCA - Home")
        self.home_widget.set_active_project(
            self.project_id if self.has_project_loaded() else None
        )
        self.home_widget.refresh_project_list()
        self.main_stack.setCurrentWidget(self.home_widget)
        self.manager.refresh_all_home_screens()

    def show_project_view(self):
        if self.has_project_loaded():
            display = self.controller.active_display_name or self.project_id
            self.setWindowTitle(f"LCCA - {display}")
            self.main_stack.setCurrentWidget(self.project_widget)
            self.content_stack.setCurrentWidget(self.widget_map["General Information"])
            items = self.sidebar.findItems("General Information", Qt.MatchExactly)
            if items:
                self.sidebar.setCurrentItem(items[0])

    def has_project_loaded(self):
        return self.project_id is not None

    # --------------------------------------------------------------------------
    # CONTROLLER SIGNALS
    # --------------------------------------------------------------------------

    def _on_project_loaded(self):
        if self.controller.active_project_id:
            self.project_id = self.controller.active_project_id
            display = self.controller.active_display_name or self.project_id
            self.setWindowTitle(f"LCCA - {display}")
            self.metadata_page.setText(
                f"<h2>{display}</h2>" f"<p><b>Internal ID:</b> {self.project_id}</p>"
            )
            self.status_bar.showMessage(f"Project: {display}")
            self.show_project_view()

    def _on_fault(self, error_message: str):
        QMessageBox.critical(
            self,
            "Engine Error — Data may not be saved",
            f"A critical storage error occurred:\n\n{error_message}\n\n"
            "Save a checkpoint immediately if possible, then restart.",
        )

    # --------------------------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------------------------

    def closeEvent(self, event):
        if self.controller.engine:
            self.controller.close_project()
        self.project_id = None
        self.manager.remove_window(self)
        self.manager.refresh_all_home_screens()
        event.accept()
