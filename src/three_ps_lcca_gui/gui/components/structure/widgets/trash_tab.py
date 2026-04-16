from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QScrollArea,
    QGroupBox,
    QSizePolicy,
    QMessageBox,
)
from three_ps_lcca_gui.gui.themes import get_token
from .base_table import StructureTableWidget


class TrashTabWidget(QWidget):
    """
    Scans all structural chunks for items where state['in_trash'] is True
    and displays them in categorized tables for restoration.
    """

    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "<b>Trash Bin</b><br>Items here are excluded from all calculations."
        )
        header.setStyleSheet(f"color: {get_token('text_secondary')}; margin-bottom: 10px;")
        self.layout.addWidget(header)

        # Scroll Area for multiple group boxes
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.scroll.setWidget(self.container)
        self.layout.addWidget(self.scroll)

        # Define the chunks to scan
        self.chunks = [
            "str_foundation",
            "str_sub_structure",
            "str_super_structure",
            "str_misc",
        ]

    def on_refresh(self):
        """Clears the view and re-populates based on nested state['in_trash']."""
        # Clear existing widgets
        for i in reversed(range(self.container_layout.count())):
            widget = self.container_layout.takeAt(i).widget()
            if widget:
                widget.deleteLater()

        if not self.controller or not self.controller.engine:
            return

        has_content = False

        for chunk_id in self.chunks:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}

            for comp_name, items in data.items():
                # Filter for trashed items using the NEW schema path
                trashed_items = [
                    (idx, item)
                    for idx, item in enumerate(items)
                    if item.get("state", {}).get("in_trash", False)
                ]

                if trashed_items:
                    has_content = True
                    group = QGroupBox(f"Deleted from: {comp_name}")
                    g_layout = QVBoxLayout(group)

                    # Create a table in 'trash mode' (shows Restore button)
                    table = StructureTableWidget(self, comp_name, is_trash_view=True)
                    for original_idx, item in trashed_items:
                        table.add_row(item, original_idx)

                    g_layout.addWidget(table)
                    self.container_layout.addWidget(group)

        if not has_content:
            empty_lbl = QLabel("No items in Trash Bin.")
            empty_lbl.setStyleSheet(f"color: {get_token('text_disabled')}; font-style: italic;")
            self.container_layout.addWidget(empty_lbl)

        # Force items to the top
        self.container_layout.addStretch()

    def permanent_delete(self, comp_name, data_index):
        """Permanently remove an item from the data store."""
        for chunk_id in self.chunks:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}
            if comp_name in data and data_index < len(data[comp_name]):
                del data[comp_name][data_index]
                self.controller.engine.stage_update(chunk_name=chunk_id, data=data)
                
                main_view = self.window().findChild(QWidget, "StructureTabView")
                if main_view:
                    # Lightweight update for Trash view and badge
                    main_view.refresh_trash_only()
                return

    def toggle_trash_status(self, comp_name, data_index, should_trash):
        """
        Restores an item by setting state['in_trash'] to False.
        Then triggers a global refresh to update the Trash badge count.
        """
        for chunk_id in self.chunks:
            data = self.controller.engine.fetch_chunk(chunk_id) or {}

            if comp_name in data and data_index < len(data[comp_name]):
                # Update nested state
                item = data[comp_name][data_index]
                if "state" not in item:
                    item["state"] = {}

                item["state"]["in_trash"] = should_trash

                # Save to engine
                self.controller.engine.stage_update(chunk_name=chunk_id, data=data)

                # Find the main view to trigger a targeted sync
                main_view = self.window().findChild(QWidget, "StructureTabView")
                if main_view:
                    if should_trash:
                        # If we just trashed something, refresh the source tab and trash badge
                        main_view.refresh_tab_by_chunk(chunk_id)
                    else:
                        # If we restored something, refresh the source tab, trash view, and badge
                        main_view.refresh_tab_by_chunk(chunk_id)
                        main_view.refresh_trash_only()
                return


