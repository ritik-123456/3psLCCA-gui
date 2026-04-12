import os

from PySide6.QtCore import Qt, QRect, QSize, QEvent, QPoint, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSplitterHandle,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPalette

from gui.components.utils.icons import make_icon, make_icon_btn
from gui.theme import (
    FS_SM, FS_BASE, FS_MD,
    FW_NORMAL, FW_MEDIUM, FW_SEMIBOLD,
    SP4,
)
from gui.styles import font as _f
from PySide6.QtWidgets import QToolTip
from gui.project_controller import ProjectController
from gui.themes import get_token, theme_manager
from gui.components.home_page import HomePage
from gui.components.save_status_bar import SaveStatusBar
from gui.components.logs import Logs
from gui.components.outputs.outputs_page import OutputsPage
from gui.components.global_info.main import GeneralInfo
from gui.components.bridge_data.main import BridgeData
from gui.components.structure.main import StructureTabView
from gui.components.traffic_data.main import TrafficData
from gui.components.financial_data.main import FinancialData
from gui.components.carbon_emission.main import CarbonEmissionTabView
from gui.components.maintenance.main import Maintenance
from gui.components.recycling.main import Recycling
from gui.components.demolition.main import Demolition
from gui.components.utils.validation_helpers import set_lock_tooltip_target
from gui.components.utils.definitions import set_active_unit_system
from core.safechunk_engine import SafeChunkEngine
from PySide6.QtWidgets import QDialog, QFormLayout, QVBoxLayout, QLabel, QPushButton
from gui.components.rollback_dialog import RollbackDialog
from gui.components.blob_manager import BlobManagerDialog
import shutil


# ── Sidebar tree definition ───────────────────────────────────────────────────

SIDEBAR_TREE = {
    "General Information": {},
    "Bridge Data": {},
    "Input Parameters": {
        "Construction Work Data": [
            "Foundation",
            "Sub Structure",
            "Super Structure",
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


# ── Sidebar tree ──────────────────────────────────────────────────────────────

_V_PAD    = 1   # vertical padding per side
_H_PAD    = 10  # left text indent
_ACCENT_W = 3   # width of the left accent bar in px
_ICON_SIZE = 16
_ICON_GAP  = 6

# Material icon name for each sidebar item (top-level and section-level only)
_SIDEBAR_ICONS: dict[str, str] = {
    "General Information":    "info",
    "Bridge Data":            "layers",
    "Input Parameters":       "folder",
    "Construction Work Data": "build",
    "Traffic Data":           "truck",
    "Financial Data":         "cash",
    "Carbon Emission Data":   "cloud",
    "Maintenance and Repair": "settings",
    "Recycling":              "autorenew",
    "Demolition":             "delete",
    "Outputs":                "bar-chart",
}


class _SidebarDelegate(QStyledItemDelegate):
    """Owns text-column painting: padding, text color. Background is handled
    by _SidebarTree.drawRow so we only need to paint text here."""

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        depth = 0
        p = index.parent()
        while p.isValid():
            depth += 1
            p = p.parent()
        pad = _V_PAD if depth < 2 else _V_PAD + 3
        return QSize(base.width(), base.height() + pad * 2)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # Query tree directly — option.state may be stripped by drawRow
        tree = self.parent()
        item = tree.itemFromIndex(index) if tree else None
        is_sel = bool(item and item in tree.selectedItems())

        option.state &= ~(
            QStyle.State_Selected | QStyle.State_MouseOver | QStyle.State_HasFocus
        )

        painter.save()

        depth = 0
        p = index.parent()
        while p.isValid():
            depth += 1
            p = p.parent()

        # Font by depth — size stays at FS_MD; weight carries the hierarchy
        # Bump weight if selected
        if depth == 0:
            painter.setFont(_f(FS_MD, FW_SEMIBOLD if is_sel else FW_MEDIUM))
        elif depth == 1:
            painter.setFont(_f(FS_MD, FW_SEMIBOLD if is_sel else FW_MEDIUM))
        else:
            painter.setFont(_f(FS_BASE, FW_MEDIUM if is_sel else FW_NORMAL))

        # Text colour — PRIMARY on selected, normal otherwise
        text_col = QColor(get_token("primary")) if is_sel else option.palette.windowText().color()
        painter.setPen(text_col)

        extra = 28 if depth >= 2 else 0
        x = option.rect.left() + _H_PAD + extra + (_ACCENT_W if is_sel else 0)

        # Icon
        icon: QIcon = index.data(Qt.DecorationRole)
        if icon and not icon.isNull():
            iy = option.rect.top() + (option.rect.height() - _ICON_SIZE) // 2
            icon.paint(painter, QRect(x, iy, _ICON_SIZE, _ICON_SIZE), Qt.AlignCenter)
            x += _ICON_SIZE + _ICON_GAP

        # Text
        text = index.data(Qt.DisplayRole)
        if text:
            text_rect = QRect(x, option.rect.top() + _V_PAD,
                              option.rect.right() - x - SP4,
                              option.rect.height() - _V_PAD * 2)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

        painter.restore()


class _SidebarTree(QTreeWidget):
    """
    QTreeWidget subclass that overrides drawRow() and drawBranches() —
    the only two methods that own the full row width including the
    indentation/branch zone. The delegate only handles text after we've
    painted the correct background across the entire row.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setItemDelegate(_SidebarDelegate(self))
        self.setRootIsDecorated(True)
        self.setIndentation(16)
        self._refresh_theme()
        theme_manager().theme_changed.connect(self._refresh_theme)

    def _refresh_theme(self):
        # Sync Base/AlternateBase → Window so the viewport background matches
        p = self.palette()
        p.setColor(QPalette.Base, p.color(QPalette.Window))
        p.setColor(QPalette.AlternateBase, p.color(QPalette.Window))
        # Keep Highlight neutral — we paint selection ourselves
        p.setColor(QPalette.Highlight, p.color(QPalette.Window))
        p.setColor(QPalette.HighlightedText, p.color(QPalette.WindowText))
        self.setPalette(p)
        self.viewport().update()

    def _row_state(self, index):
        """Return (is_selected, is_hovered) for a model index."""
        item = self.itemFromIndex(index)
        is_sel = item in self.selectedItems()
        is_hovered = index == self.indexAt(
            self.viewport().mapFromGlobal(self.cursor().pos())
        )
        return is_sel, is_hovered

    def drawRow(self, painter: QPainter, option, index):
        """Pre-paint full-width background, strip Qt states, then let Qt draw
        content on top. Accent bar is drawn last so it's never overwritten."""
        is_sel, is_hovered = self._row_state(index)
        full = option.rect

        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.palette().window())
        painter.drawRect(full)
        if is_hovered and not is_sel:
            tint = QColor(get_token("primary")); tint.setAlpha(11)
            painter.setBrush(tint); painter.drawRect(full)
        if is_sel:
            tint = QColor(get_token("primary")); tint.setAlpha(22)
            painter.setBrush(tint); painter.drawRect(full)
        painter.restore()

        # Strip selection/hover so Qt doesn't repaint with its own highlight
        option.state &= ~(QStyle.State_Selected | QStyle.State_MouseOver | QStyle.State_HasFocus)
        super().drawRow(painter, option, index)

        if is_sel:
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(get_token("primary")))
            painter.drawRect(full.left(), full.top(), _ACCENT_W, full.height())
            painter.restore()

    def drawBranches(self, painter: QPainter, rect: QRect, index):
        """Background already painted by drawRow; just draw the expand arrows."""
        super().drawBranches(painter, rect, index)


# ── Hover-highlight splitter ──────────────────────────────────────────────────


class _HoverHandle(QSplitterHandle):
    """
    Splitter handle that draws a 2px green accent line on hover/drag —
    identical visual language to VS Code's panel resize handles.
    No QSS used; painting is done entirely via QPainter + QPalette.
    """

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self._hovered = False

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        r = self.rect()
        # Clear background to match window
        painter.fillRect(r, self.palette().window())

        painter.setPen(Qt.NoPen)
        if self._hovered:
            # Theme-consistent highlight: 2px primary @ 'focus' alpha (18%)
            painter.setBrush(QColor(get_token("primary", "focus")))
            if self.orientation() == Qt.Horizontal:
                painter.drawRect((r.width() - 2) // 2, 0, 2, r.height())
            else:
                painter.drawRect(0, (r.height() - 2) // 2, r.width(), 2)
        else:
            # Very dim idle line: 1px divider @ 'hover' alpha (6%)
            painter.setBrush(QColor(get_token("primary", "hover")))
            if self.orientation() == Qt.Horizontal:
                painter.drawRect(r.width() // 2, 0, 1, r.height())
            else:
                painter.drawRect(0, r.height() // 2, r.width(), 1)
        painter.end()


class _HoverSplitter(QSplitter):
    """QSplitter that uses _HoverHandle for all its handles."""

    def createHandle(self):
        return _HoverHandle(self.orientation(), self)


# ── Main window ───────────────────────────────────────────────────────────────


class ProjectWindow(QMainWindow):
    def __init__(self, manager, controller=None):
        super().__init__()
        self.manager = manager

        if controller is not None:
            self.controller = controller
        else:
            self.controller = ProjectController()

        self.project_id = None

        self.setWindowTitle("LCCA - Home")
        _icon_path = os.path.join("gui", "assets", "logo", "logo-3psLCCA.ico")
        if os.path.exists(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))
        self.resize(1100, 750)

        self.main_stack = QStackedWidget()
        self.setCentralWidget(self.main_stack)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._project_ui_ready = False
        self._setup_home_ui()  # index 0
        # _setup_project_ui() deferred to first show_project_view()

        # ── Controller signals ────────────────────────────────────────────
        self.controller.fault_occurred.connect(self._on_fault)
        self.controller.project_loaded.connect(self._on_project_loaded)
        self.controller.sync_completed.connect(
            lambda: self.status_bar.showMessage("All changes saved.", 3000)
        )
        self.controller.dirty_changed.connect(
            lambda d: self.status_bar.showMessage("Unsaved changes...") if d else None
        )

        self.show_home()

    # ── Home screen ───────────────────────────────────────────────────────────

    def _setup_home_ui(self):
        self.home_widget = HomePage(manager=self.manager)
        self.main_stack.addWidget(self.home_widget)  # index 0

    # ── Project view ──────────────────────────────────────────────────────────

    def _setup_project_ui(self):

        self.project_widget = QWidget()
        master_layout = QVBoxLayout(self.project_widget)
        master_layout.setContentsMargins(0, 0, 0, 0)
        master_layout.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(8, 4, 8, 4)
        top_bar_layout.setSpacing(8)
        top_bar.setObjectName("top_bar")

        self.menubar = QMenuBar()

        # ── File menu ─────────────────────────────────────────────────────
        self.menuFile = QMenu("&File", self.menubar)

        action_new = QAction("New Project", self)
        action_new.triggered.connect(lambda: self.manager.open_project(is_new=True))
        self.menuFile.addAction(action_new)

        action_open = QAction("Open Project", self)
        action_open.triggered.connect(self.show_home)
        self.menuFile.addAction(action_open)

        self.menuFile.addSeparator()

        self.actionSave = QAction("Save Now", self)
        self.actionSave.triggered.connect(self._save_now)
        self.menuFile.addAction(self.actionSave)

        self.menuFile.addSeparator()

        action_rename = QAction("Rename", self)
        action_rename.triggered.connect(self._rename_project)
        self.menuFile.addAction(action_rename)

        action_export = QAction("Export...", self)
        action_export.triggered.connect(self._export_project)
        self.menuFile.addAction(action_export)

        self.menuFile.addSeparator()

        self.actionVersionHistory = QAction("Version History", self)
        self.actionVersionHistory.triggered.connect(self._open_rollback_dialog)
        self.menuFile.addAction(self.actionVersionHistory)

        self.actionBlobManager = QAction("Blob Manager", self)
        self.actionBlobManager.triggered.connect(self._open_blob_manager)
        self.menuFile.addAction(self.actionBlobManager)

        self.menuFile.addSeparator()

        action_info = QAction("Info", self)
        action_info.triggered.connect(self._show_project_info)
        self.menuFile.addAction(action_info)

        self.menuFile.addSeparator()

        action_close = QAction("Close Project", self)
        action_close.triggered.connect(self._close_project)
        self.menuFile.addAction(action_close)

        # ── Help menu ─────────────────────────────────────────────────────
        self.menuHelp = QMenu("&Help", self.menubar)

        action_contact = QAction("Contact Us", self)
        action_contact.triggered.connect(
            lambda: QMessageBox.information(
                self, "Contact Us",
                "For support or enquiries, please email:\nsupport@3pslcca.com"
            )
        )
        self.menuHelp.addAction(action_contact)

        action_feedback = QAction("Feedback", self)
        action_feedback.triggered.connect(
            lambda: QMessageBox.information(
                self, "Feedback",
                "We'd love to hear from you!\nSend feedback to:\nfeedback@3pslcca.com"
            )
        )
        self.menuHelp.addAction(action_feedback)

        # ── Menubar ───────────────────────────────────────────────────────
        home_action = QAction("Home", self)
        home_action.setIcon(make_icon("home"))
        home_action.triggered.connect(self.show_home)

        self.log_action = QAction("Logs", self)

        self.menubar.addAction(home_action)
        self.menubar.addMenu(self.menuFile)
        self.menubar.addMenu(self.menuHelp)
        self.menubar.addAction(self.log_action)

        top_bar_layout.addWidget(self.menubar, alignment=Qt.AlignmentFlag.AlignCenter)
        top_bar_layout.addStretch()
        self.save_status_bar = SaveStatusBar(controller=self.controller)
        top_bar_layout.addWidget(self.save_status_bar)

        self.btn_calculate = QPushButton("Calculate")
        self.btn_calculate.clicked.connect(self._run_calculate)
        top_bar_layout.addWidget(self.btn_calculate)

        self._frozen = False
        self._lock_tooltip = "Click to lock this project and prevent accidental edits."
        self.btn_lock = make_icon_btn("lock-open", tooltip=self._lock_tooltip, size=30)
        self.btn_lock.setStyleSheet(
            "QPushButton               { border-radius:15px; padding:0px; border:none; background:transparent; }"
            "QPushButton:hover         { border-radius:15px; padding:0px; background:palette(midlight); }"
            "QPushButton:pressed       { border-radius:15px; padding:0px; background:palette(mid); }"
            f"QPushButton:checked       {{ border-radius:15px; padding:0px; background:{get_token('primary')}; }}"
            f"QPushButton:checked:hover {{ border-radius:15px; padding:0px; background:{get_token('primary')}; }}"
        )
        self.btn_lock.setCheckable(True)
        self.btn_lock.installEventFilter(self)
        self.btn_lock.clicked.connect(self._on_lock_toggled)
        top_bar_layout.addWidget(self.btn_lock)

        master_layout.setMenuBar(top_bar)

        # ── Sidebar ───────────────────────────────────────────────────────
        self.sidebar = _SidebarTree()
        self.sidebar.setMinimumWidth(80)

        for header, subheaders in SIDEBAR_TREE.items():
            top_item = QTreeWidgetItem(self.sidebar)
            top_item.setText(0, header)
            if header in _SIDEBAR_ICONS:
                top_item.setIcon(0, make_icon(_SIDEBAR_ICONS[header]))
            for subheader, subitems in subheaders.items():
                sub_item = QTreeWidgetItem(top_item)
                sub_item.setText(0, subheader)
                if subheader in _SIDEBAR_ICONS:
                    sub_item.setIcon(0, make_icon(_SIDEBAR_ICONS[subheader]))
                for subitem in subitems:
                    leaf = QTreeWidgetItem(sub_item)
                    leaf.setText(0, subitem)
                    if subitem in _SIDEBAR_ICONS:
                        leaf.setIcon(0, make_icon(_SIDEBAR_ICONS[subitem]))

        self.sidebar.expandAll()

        # Find out the minimum width of the sidebar
        self.sidebar.resizeColumnToContents(0)
        self.sidebar.header().setStretchLastSection(False)

        min_width = int((self.sidebar.header().sectionSize(0) + _H_PAD + _ACCENT_W) * 0.9)
        self.sidebar.header().setStretchLastSection(True)
        self.sidebar.setMinimumWidth(min_width)

        self.sidebar.itemPressed.connect(self._select_sidebar)

        # ── Content stack ─────────────────────────────────────────────────
        self.content_stack = QStackedWidget()

        self.metadata_page = QLabel()
        self.metadata_page.setAlignment(Qt.AlignCenter)

        self.logs_page = Logs(controller=self.controller)

        self.outputs_page = OutputsPage(controller=self.controller)
        self.outputs_page.navigate_requested.connect(self._navigate_to_page)
        self.outputs_page.calculation_completed.connect(self._on_calculation_done)
        self.outputs_page.validate_requested.connect(self._run_calculate)

        # Page widgets are built lazily on first sidebar click via _get_or_create_widget
        self.widget_map = {"Outputs": self.outputs_page}
        self._page_names = [
            "General Information", "Bridge Data", "Construction Work Data",
            "Traffic Data", "Financial Data", "Carbon Emission Data",
            "Maintenance and Repair", "Recycling", "Demolition",
        ]

        self.content_stack.addWidget(self.outputs_page)
        self.content_stack.addWidget(self.logs_page)

        self.log_action.triggered.connect(
            lambda: self.content_stack.setCurrentWidget(self.logs_page)
        )

        # ── Splitter ──────────────────────────────────────────────────────
        self.splitter = _HoverSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.sidebar)
        self.splitter.setHandleWidth(8)
        self.splitter.addWidget(self.content_stack)
        self.splitter.setSizes([min_width, 880])

        master_layout.addWidget(self.splitter, stretch=1)
        self.main_stack.addWidget(self.project_widget)  # index 1

    def _get_or_create_widget(self, name: str):
        """Return the page widget for *name*, creating it on first access."""
        if name in self.widget_map:
            return self.widget_map[name]
        if name not in self._page_names:
            return None

        if name == "General Information":
            widget = GeneralInfo(controller=self.controller)
        elif name == "Bridge Data":
            widget = BridgeData(controller=self.controller)
        elif name == "Construction Work Data":
            widget = StructureTabView(controller=self.controller)
        elif name == "Traffic Data":
            widget = TrafficData(controller=self.controller)
        elif name == "Financial Data":
            widget = FinancialData(controller=self.controller)
        elif name == "Carbon Emission Data":
            widget = CarbonEmissionTabView(controller=self.controller)
        elif name == "Maintenance and Repair":
            widget = Maintenance(controller=self.controller)
        elif name == "Recycling":
            widget = Recycling(controller=self.controller)
        elif name == "Demolition":
            widget = Demolition(controller=self.controller)
        else:
            return None

        self.widget_map[name] = widget
        self.content_stack.addWidget(widget)

        if name == "Construction Work Data":
            widget.tab_changed.connect(self._sync_sidebar_from_tab)
        elif name == "Carbon Emission Data":
            widget.tab_changed.connect(self._sync_sidebar_from_tab)

        if self._frozen and hasattr(widget, "freeze"):
            widget.freeze(True)

        return widget

    def _select_sidebar(self, item: QTreeWidgetItem):
        header = item.text(0)
        parent = item.parent()

        # Direct page item — show it
        widget = self._get_or_create_widget(header)
        if widget:
            # If we are navigating AWAY from Construction Work Data or TO it directly, 
            # ensure Trash view is reset.
            for w in self.widget_map.values():
                if isinstance(w, StructureTabView):
                    w.reset_view()
            
            self.content_stack.setCurrentWidget(widget)
            return

        # Leaf item under a tabbed page — show parent page and select tab
        if parent is not None:
            parent_name = parent.text(0)
            w = self._get_or_create_widget(parent_name)
            if w and hasattr(w, "select_tab"):
                # If this is Structure, reset the trash view before showing the tab
                if isinstance(w, StructureTabView):
                    w.reset_view()
                
                self.content_stack.setCurrentWidget(w)
                w.select_tab(header)

    # ── View switching ────────────────────────────────────────────────────────

    def show_home(self):
        self.setWindowTitle("LCCA - Home")
        self.home_widget.set_active_project(
            self.project_id if self.has_project_loaded() else None
        )
        self.home_widget.refresh_project_list()
        self.main_stack.setCurrentWidget(self.home_widget)
        self.manager.refresh_all_home_screens()

    def show_project_view(self):
        if not self.has_project_loaded():
            return
        if not self._project_ui_ready:
            self._setup_project_ui()
            self._project_ui_ready = True
        display = self.controller.active_display_name or self.project_id
        self.setWindowTitle(f"LCCA - {display}")
        self.main_stack.setCurrentWidget(self.project_widget)
        self.content_stack.setCurrentWidget(self._get_or_create_widget("General Information"))
        items = self.sidebar.findItems("General Information", Qt.MatchExactly)
        if items:
            self.sidebar.setCurrentItem(items[0])

    def preload_all(self, on_complete):
        """Setup project UI if needed, then build every page widget one per
        event-loop tick (non-blocking), then call on_complete."""
        if not self._project_ui_ready:
            self._setup_project_ui()
            self._project_ui_ready = True
        _order = [
            "General Information",
            "Construction Work Data", "Carbon Emission Data",
            "Bridge Data", "Traffic Data", "Financial Data",
            "Maintenance and Repair", "Recycling", "Demolition",
        ]
        QTimer.singleShot(0, lambda: self._do_preload(_order, 0, on_complete))

    def _do_preload(self, order, index, on_complete):
        """Build one unbuilt widget, yield to event loop, then continue."""
        while index < len(order):
            name = order[index]
            index += 1
            if name not in self.widget_map:
                self._get_or_create_widget(name)
                QTimer.singleShot(0, lambda i=index: self._do_preload(order, i, on_complete))
                return
        on_complete()

    def has_project_loaded(self):
        return self.project_id is not None

    # ── Calculate ─────────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.btn_lock:
            if event.type() == QEvent.Type.Enter:
                pos = self.btn_lock.mapToGlobal(
                    QPoint(self.btn_lock.width() // 2, self.btn_lock.height() + 4)
                )
                QToolTip.showText(pos, self._lock_tooltip, None, QRect(), 3000)
            elif event.type() == QEvent.Type.Leave:
                QToolTip.hideText()
        return super().eventFilter(obj, event)

    def _on_calculation_done(self):
        """Auto-lock the project after a successful calculation."""
        self.btn_lock.setChecked(True)
        self._on_lock_toggled(True)

    def _on_lock_toggled(self, checked: bool):
        if not checked and self.outputs_page._has_results:
            reply = QMessageBox.warning(
                self,
                "Unlock Project",
                "Unlocking will clear the current results and reset all inputs.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self.btn_lock.blockSignals(True)
                self.btn_lock.setChecked(True)
                self.btn_lock.blockSignals(False)
                return
            self.outputs_page.reset_for_edit()

        self._frozen = checked
        self.btn_lock.setIcon(make_icon("lock" if checked else "lock-open"))
        self._lock_tooltip = (
            "This project is locked.\nClick here to unlock and enable editing."
            if checked else
            "Click to lock this project and prevent accidental edits."
        )
        set_lock_tooltip_target(self.btn_lock if checked else None)
        for page in self.widget_map.values():
            if hasattr(page, "freeze"):
                page.freeze(checked)

    def _run_calculate(self):
        # Ensure all pages exist — needed for full validation and calculation
        for name in self._page_names:
            self._get_or_create_widget(name)
        self.outputs_page.register_pages(self.widget_map)
        self.outputs_page.run_validation()
        self.content_stack.setCurrentWidget(self.outputs_page)
        items = self.sidebar.findItems("Outputs", Qt.MatchExactly)
        if items:
            self.sidebar.setCurrentItem(items[0])

    def _sync_sidebar_from_tab(self, tab_name: str):
        """Highlight the sidebar item matching the active tab (no content switch)."""
        items = self.sidebar.findItems(tab_name, Qt.MatchExactly | Qt.MatchRecursive)
        if items:
            self.sidebar.setCurrentItem(items[0])

    def _navigate_to_page(self, page_name: str):
        """Navigate sidebar + content stack to a named page."""
        widget = self._get_or_create_widget(page_name)
        if widget:
            self.content_stack.setCurrentWidget(widget)
        items = self.sidebar.findItems(page_name, Qt.MatchExactly | Qt.MatchRecursive)
        if items:
            self.sidebar.setCurrentItem(items[0])

    # ── Controller signals ────────────────────────────────────────────────────

    def _on_project_loaded(self):
        if not self.controller.active_project_id:
            return
        self.project_id = self.controller.active_project_id
        display = self.controller.active_display_name or self.project_id
        self.setWindowTitle(f"LCCA - {display}")
        self.status_bar.showMessage(f"Project: {display}")

        # Apply project's unit system to the unit dropdowns
        try:
            info = self.controller.engine.fetch_chunk("general_info") or {}
            unit_system = info.get("unit_system", "metric")
            set_active_unit_system(unit_system)
        except Exception:
            pass

    def _on_fault(self, error_message: str):
        QMessageBox.critical(
            self,
            "Engine Error — Data may not be saved",
            f"Storage error:\n\n{error_message}\n\nSave a checkpoint now if possible, then restart.",
        )

    def _close_project(self):
        if not self.controller.engine or not self.controller.engine.is_active():
            self.show_home()
            return
        self.controller.close_project()
        self.project_id = None
        self.setWindowTitle("LCCA - Home")
        self.show_home()

    def _save_now(self):
        if self.controller.engine and self.controller.engine.is_active():
            self.controller.engine.force_sync()
            self.status_bar.showMessage("Saved.", 3000)

    def _rename_project(self):
        if not self.controller.engine or not self.controller.engine.is_active():
            return
        current = self.controller.active_display_name or self.project_id
        new_name, ok = QInputDialog.getText(
            self, "Rename Project", "New name:", text=current
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == current:
            return
        self.controller.engine.rename(new_name)
        self.controller.active_display_name = new_name
        self.setWindowTitle(f"LCCA - {new_name}")
        self.manager.refresh_all_home_screens()

    def _export_project(self):
        if not self.controller.engine or not self.controller.engine.is_active():
            return
        display = self.controller.active_display_name or self.project_id
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export Project", f"{display}.3psLCCA", "3psLCCA Archive (*.3psLCCA)"
        )
        if not dest:
            return
        zip_name = self.controller.engine.create_checkpoint(
            label="export", notes="Exported from 3psLCCA", include_blobs=True
        )
        if not zip_name:
            QMessageBox.warning(self, "Export Failed", "Could not create export archive.")
            return
        src = self.controller.engine.checkpoint_manual / zip_name
        try:
            shutil.copy2(str(src), dest)
            QMessageBox.information(self, "Export Complete", f"Project exported to:\n{dest}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    def _show_project_info(self):
        if not self.project_id:
            return
        info = SafeChunkEngine.get_project_info(self.project_id)
        if not info:
            return
        # Overlay live data from running engine
        report = self.controller.get_health_report()
        if report:
            info["pending_syncs"] = report.get("pending_syncs", 0)
            info["wal_exists"] = report.get("wal_exists", False)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Project Info — {info.get('display_name', self.project_id)}")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(6)
        rows = [
            ("Project ID",       info.get("project_id", "")),
            ("Display Name",     info.get("display_name", "")),
            ("Status",           info.get("status", "").capitalize()),
            ("Created",          info.get("created_at", "—")),
            ("Last Modified",    info.get("last_modified", "—")),
            ("Chunks",           str(info.get("chunk_count", 0))),
            ("Checkpoints",      str(info.get("checkpoint_count", 0))),
            ("Last Checkpoint",  info.get("last_checkpoint_date") or "—"),
            ("Size",             f"{info.get('size_kb', 0)} KB"),
            ("Engine Version",   info.get("engine_version", "—")),
            ("Pending Syncs",    str(info.get("pending_syncs", 0))),
            ("WAL Active",       "Yes" if info.get("wal_exists") else "No"),
        ]
        for label, value in rows:
            lbl = QLabel(value)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(f"{label}:", lbl)
        layout.addLayout(form)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.exec()

    def _open_rollback_dialog(self):
        if not self.controller.engine or not self.controller.engine.is_active():
            return
        dlg = RollbackDialog(self.controller, parent=self)
        dlg.exec()

    def _open_blob_manager(self):
        if not self.controller.engine or not self.controller.engine.is_active():
            return
        dlg = BlobManagerDialog(self.controller, parent=self)
        dlg.exec()

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self.controller.engine:
            self.controller.close_project()
        self.project_id = None
        self.manager.remove_window(self)
        self.manager.refresh_all_home_screens()
        event.accept()


