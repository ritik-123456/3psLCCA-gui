from PySide6.QtWidgets import (
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QStackedWidget,
)
from PySide6.QtGui import QPalette
from .widgets.foundation import FoundationWidget
from .widgets.super_structure import SuperStructureWidget
from .widgets.substructure import SubStructureWidget
from .widgets.misc_widget import MiscWidget
from .widgets.trash_tab import TrashTabWidget


class StructureTabView(QWidget):
    def __init__(self, controller=None):
        super().__init__()
        self.setObjectName("StructureTabView")  # For identification in Manager
        self.controller = controller

        self.main_layout = QVBoxLayout(self)

        # --- TOP AREA ---
        top_area = QWidget()
        top_layout = QHBoxLayout(top_area)

        region_info = QVBoxLayout()
        region_info.addWidget(QLabel("<b>Structure Management</b>"))
        region_info.addWidget(QLabel("Project: Active Analysis"))
        top_layout.addLayout(region_info)

        top_layout.addStretch()

        # Action Buttons
        self.excel_btn = QPushButton("Upload Excel")
        self.trash_btn = QPushButton("Trash")

        top_layout.addWidget(self.excel_btn)
        top_layout.addWidget(self.trash_btn)

        self.main_layout.addWidget(top_area)

        # --- CONTENT AREA (Tabs + Trash View) ---
        self.content_stack = QStackedWidget()

        # 1. Active Tabs
        self.tab_view = QTabWidget()

        # QTabWidget's content pane paints using Base palette role, which differs
        # from Window in dark mode. Copy Window → Base so both are identical.
        palette = self.tab_view.palette()
        palette.setColor(QPalette.Base, palette.color(QPalette.Window))
        self.tab_view.setPalette(palette)

        self.foundation_tab = FoundationWidget(controller=controller)
        self.substructure_tab = SubStructureWidget(controller=controller)
        self.superstructure_tab = SuperStructureWidget(controller=controller)
        self.misc_tab = MiscWidget(controller=controller)

        self.tab_view.addTab(self.foundation_tab, "Foundation")
        self.tab_view.addTab(self.substructure_tab, "Sub Structure")
        self.tab_view.addTab(self.superstructure_tab, "Super Structure")
        self.tab_view.addTab(self.misc_tab, "Miscellaneous")

        # 2. Trash View
        self.trash_view = TrashTabWidget(controller=controller)

        self.content_stack.addWidget(self.tab_view)  # Index 0
        self.content_stack.addWidget(self.trash_view)  # Index 1

        self.main_layout.addWidget(self.content_stack)

        # --- CONNECTIONS ---
        self.trash_btn.clicked.connect(self.toggle_trash_view)

    def on_refresh(self):
        """Refreshes all active tabs and updates the global trash count."""
        # SAFETY GUARD: Ensure controller and engine are ready before fetching
        if (
            not self.controller
            or not hasattr(self.controller, "engine")
            or not self.controller.engine
        ):
            return

        # Refresh all nested managers (this triggers their fetch_chunk calls)
        self.foundation_tab.on_refresh()
        self.substructure_tab.on_refresh()
        self.superstructure_tab.on_refresh()
        self.misc_tab.on_refresh()

        # Update the counter whenever the main view refreshes
        self.update_trash_count()

        # If we are looking at the trash stack, refresh that too
        if self.content_stack.currentIndex() == 1:
            self.trash_view.on_refresh()

    def showEvent(self, event):
        """Qt event triggered when the widget is shown."""
        super().showEvent(event)
        self.on_refresh()

    def toggle_trash_view(self):
        """Swaps between normal tabs and the Trash list."""
        if self.content_stack.currentIndex() == 0:
            # Entering Trash View
            self.trash_view.on_refresh()
            self.content_stack.setCurrentIndex(1)
            self.update_trash_count()
            self.trash_btn.setStyleSheet("font-weight: bold; color: #2ecc71;")
        else:
            # Returning to Work View
            self.content_stack.setCurrentIndex(0)
            self.trash_btn.setStyleSheet("")
            self.on_refresh()

    def update_trash_count(self):
        """Calculates total trashed items and updates the button text."""
        if not self.controller or not self.controller.engine:
            return

        # Change button text if we are currently inside the trash view
        if self.content_stack.currentIndex() == 1:
            self.trash_btn.setText("Back to Work")
            return

        total_count = 0
        chunks = [
            "str_foundation",
            "str_sub_structure",
            "str_super_structure",
            "str_misc",
        ]

        for chunk_id in chunks:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            for group_name, items in data.items():
                for item in items:
                    if item.get("state", {}).get("in_trash"):
                        total_count += 1

        if total_count > 0:
            self.trash_btn.setText(f"Trash ({total_count})")
        else:
            self.trash_btn.setText("Trash")

    def select_tab(self, name: str):
        """External helper to switch tabs (e.g., from a Sidebar)."""
        mapping = {
            "Foundation": 0,
            "Sub Structure": 1,
            "Super Structure": 2,
            "Miscellaneous": 3,
        }
        idx = mapping.get(name)
        if idx is not None:
            self.content_stack.setCurrentIndex(0)
            self.tab_view.setCurrentIndex(idx)
            self.on_refresh()
