from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QSizePolicy,
    QWidget,
    QHBoxLayout,
    QMessageBox,
)
from PySide6.QtCore import Qt, QSize
from ...utils.definitions import UNIT_DISPLAY


class StructureTableWidget(QTableWidget):
    def __init__(self, parent_manager, component_name, is_trash_view=False):
        super().__init__()
        self.manager = parent_manager
        self.component_name = component_name
        self.is_trash_view = is_trash_view
        self._frozen = False

        # Setup 6 columns: Work Name, Rate, Qty, Source, Total, Action
        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(
            ["Work Name", "Rate", "Qty", "Source", "Total", "Action"]
        )
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setMinimumSectionSize(100)

        # Set proportional default widths
        self.setColumnWidth(0, 220)  # Work Name
        self.setColumnWidth(1, 80)  # Rate
        self.setColumnWidth(2, 65)  # Qty
        self.setColumnWidth(3, 110)  # Source
        self.setColumnWidth(4, 90)  # Total
        self.setColumnWidth(5, 140)  # Actions
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Disable direct typing in cells (Double-click logic handles editing)
        self.setEditTriggers(QTableWidget.NoEditTriggers)

        self.verticalHeader().setDefaultSectionSize(35)

        # Connect Double Click for Editing (only if not in trash)
        if not self.is_trash_view:
            self.cellDoubleClicked.connect(self._on_cell_double_clicked)

        self.update_height()

    def _confirm_permanent_delete(self, original_index):
        reply = QMessageBox.warning(
            self, "Permanent Delete",
            "This will permanently remove the item. This cannot be undone.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.manager.permanent_delete(self.component_name, original_index)

    def _on_cell_double_clicked(self, row, column):
        """Pass the visual row index to the manager to find the data and open the edit dialog."""
        if self._frozen:
            return
        self.manager.open_edit_dialog(self.component_name, row)

    def sizeHint(self):
        header_h = self.horizontalHeader().height() or 35
        rows_h = self.rowCount() * self.verticalHeader().defaultSectionSize()
        return QSize(super().sizeHint().width(), max(150, header_h + rows_h + 15))

    def minimumSizeHint(self):
        return self.sizeHint()

    def update_height(self):
        """Notifies the layout that the size hint changed — no fixed height needed."""
        self.updateGeometry()

    def add_row(self, item_data, original_index):
        """
        Adds a row to the table reading from the 'values' nested block.
        original_index links the visual row back to the full list in the JSON engine.
        """
        self.blockSignals(True)
        row = self.rowCount()
        self.insertRow(row)

        # Access the nested 'values' block from your new schema
        v = item_data.get("values", {})

        # 0. Work Name (Mapped to material_name)
        self.setItem(row, 0, QTableWidgetItem(v.get("material_name", "New Item")))

        # 1. Rate
        rate_item = QTableWidgetItem(str(v.get("rate", 0)))
        rate_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 1, rate_item)

        # 2. Qty
        unit = v.get("unit", "")
        unit = UNIT_DISPLAY.get(unit.lower(), unit) if unit else unit
        qty_text = f"{v.get('quantity', 0)} {unit}".strip()
        qty_item = QTableWidgetItem(qty_text)
        qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 2, qty_item)

        # 3. Source (Mapped to rate_source)
        self.setItem(row, 3, QTableWidgetItem(v.get("rate_source", "Manual")))

        # 4. Total Calculation
        try:
            rate = float(v.get("rate", 0) or 0)
            qty = float(v.get("quantity", 0) or 0)
            total = rate * qty
        except (ValueError, TypeError):
            total = 0.0

        total_item = QTableWidgetItem(f"{total:.2f}")
        total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)  # Read-only
        total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 4, total_item)

        # 5. Actions (Edit + Trash / Restore)
        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(2, 2, 2, 2)
        actions_layout.setSpacing(4)

        if not self.is_trash_view:
            edit_btn = QPushButton("Edit")
            edit_btn.setFocusPolicy(Qt.NoFocus)
            edit_btn.clicked.connect(
                lambda checked=False, r=row: self.manager.open_edit_dialog(
                    self.component_name, r
                )
            )
            actions_layout.addWidget(edit_btn)

        trash_btn = QPushButton("Restore" if self.is_trash_view else "Trash")
        trash_btn.setFocusPolicy(Qt.NoFocus)
        trash_btn.clicked.connect(
            lambda checked=False, idx=original_index: self.manager.toggle_trash_status(
                self.component_name, idx, not self.is_trash_view
            )
        )
        actions_layout.addWidget(trash_btn)

        if self.is_trash_view:
            delete_btn = QPushButton("Delete")
            delete_btn.setFocusPolicy(Qt.NoFocus)
            delete_btn.setStyleSheet("color: #c0392b;")
            delete_btn.clicked.connect(
                lambda checked=False, idx=original_index: self._confirm_permanent_delete(idx)
            )
            actions_layout.addWidget(delete_btn)

        if self._frozen:
            for btn in actions_widget.findChildren(QPushButton):
                btn.setEnabled(False)
        self.setCellWidget(row, 5, actions_widget)

        self.blockSignals(False)
        self.update_height()

    def freeze(self, frozen: bool = True):
        """Disable/enable action buttons in every row."""
        self._frozen = frozen
        for row in range(self.rowCount()):
            container = self.cellWidget(row, 5)
            if container:
                for btn in container.findChildren(QPushButton):
                    btn.setEnabled(not frozen)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        total = self.viewport().width()
        min_w = 100

        # Proportional widths (must all be >= min_w)
        widths = {
            0: max(min_w, int(total * 0.32)),  # Work Name
            1: max(min_w, int(total * 0.12)),  # Rate
            2: max(min_w, int(total * 0.10)),  # Qty
            3: max(min_w, int(total * 0.16)),  # Source
            4: max(min_w, int(total * 0.12)),  # Total
            5: max(min_w, int(total * 0.18)),  # Actions
        }

        for col, width in widths.items():
            self.setColumnWidth(col, width)
