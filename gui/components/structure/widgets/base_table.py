from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QSizePolicy,
    QWidget,
    QHBoxLayout,
    QMessageBox,
    QStyleOptionHeader,
)
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QPainter, QFont
from ...utils.definitions import UNIT_DISPLAY
from ...utils.display_format import fmt, fmt_comma
from ...utils.icons import make_icon, make_icon_btn
from ...utils.validation_helpers import freeze_widgets
from gui.theme import FS_SM, FW_SEMIBOLD, SECONDARY


# ---------------------------------------------------------------------------
# Two-tier grouped header (shared pattern with CarbonTable)
# ---------------------------------------------------------------------------

_HDR_FONT = QFont("Ubuntu", FS_SM, FW_SEMIBOLD)


class _GroupedHeader(QHeaderView):
    """Horizontal header with spanning group labels on the top tier and
    individual column labels on the bottom tier.

    groups: list of (start_col, span, label)
    Columns NOT in any group span the full height with their label centred.
    """

    def __init__(self, groups=(), parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._groups = list(groups)
        self._col_group: dict[int, tuple] = {}
        for start, span, label in self._groups:
            for c in range(start, start + span):
                self._col_group[c] = (start, span, label)

    def sizeHint(self):
        s = super().sizeHint()
        return QSize(s.width(), s.height() * 2) if self._groups else s

    def paintSection(self, painter, rect, logical_index):
        painter.setFont(_HDR_FONT)
        if not self._groups or logical_index not in self._col_group:
            super().paintSection(painter, rect, logical_index)
            return

        h2 = rect.height() // 2
        bottom = QRect(rect.x(), rect.y() + h2, rect.width(), h2)

        painter.save()
        painter.setClipRect(bottom)
        super().paintSection(painter, bottom, logical_index)
        painter.restore()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._groups:
            return

        painter = QPainter(self.viewport())
        painter.setFont(_HDR_FONT)
        h2 = self.height() // 2

        for start, span, label in self._groups:
            x = self.sectionViewportPosition(start)
            total_w = sum(self.sectionSize(start + i) for i in range(span))
            group_rect = QRect(x, 0, total_w, h2)

            opt = QStyleOptionHeader()
            self.initStyleOption(opt)
            opt.rect = group_rect
            opt.section = start
            opt.text = label
            opt.textAlignment = Qt.AlignCenter | Qt.AlignVCenter
            opt.position = QStyleOptionHeader.Middle
            opt.selectedPosition = QStyleOptionHeader.NotAdjacent
            self.style().drawControl(self.style().ControlElement.CE_Header, opt, painter, self)

        painter.end()


# ---------------------------------------------------------------------------
# Structure table
# ---------------------------------------------------------------------------

_ACTION_W = 72   # fixed Action column width


class StructureTableWidget(QTableWidget):
    # Col 2-3 → "Qty" group (Value + Unit)
    _GROUPS = [(2, 2, "Qty")]

    def __init__(self, parent_manager, component_name, is_trash_view=False):
        super().__init__()
        self.manager = parent_manager
        self.component_name = component_name
        self.is_trash_view = is_trash_view
        self._frozen = False

        # Install grouped header before setting column count
        self.setHorizontalHeader(_GroupedHeader(groups=self._GROUPS))

        # Setup 7 columns: Work Name, Rate, Value, Unit, Source, Total, Action
        self.setColumnCount(7)
        _L = Qt.AlignLeft | Qt.AlignVCenter
        _R = Qt.AlignRight | Qt.AlignVCenter
        _C = Qt.AlignCenter | Qt.AlignVCenter
        _headers = [
            ("Work Name", _L),  # 0
            ("Rate",      _R),  # 1
            ("Value",     _C),  # 2  ┐ Qty group (sub-col → center)
            ("Unit",      _C),  # 3  ┘
            ("Source",    _L),  # 4
            ("Total",     _R),  # 5
            ("Action",    _C),  # 6
        ]
        for col, (label, align) in enumerate(_headers):
            item = QTableWidgetItem(label)
            item.setTextAlignment(align)
            self.setHorizontalHeaderItem(col, item)

        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(40)
        # Action column fixed width, always at right edge; Total stretches to fill
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.Fixed)
        self.setColumnWidth(6, _ACTION_W)

        # Row selection & appearance
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.verticalHeader().setDefaultSectionSize(36)
        self.verticalHeader().setVisible(False)

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

    def set_currency(self, code: str):
        """Update Rate and Total column headers to show the project currency code."""
        suffix = f" ({code})" if code else ""
        for col, base in ((1, "Rate"), (5, "Total")):
            item = self.horizontalHeaderItem(col)
            if item:
                item.setText(base + suffix)

    def sizeHint(self):
        header_h = self.horizontalHeader().height() or 56
        rows_h = self.rowCount() * self.verticalHeader().defaultSectionSize()
        return QSize(super().sizeHint().width(), header_h + rows_h + 2)

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

        v = item_data.get("values", {})

        # 0. Work Name
        self.setItem(row, 0, QTableWidgetItem(v.get("material_name", "New Item")))

        # 1. Rate (right-aligned)
        rate_item = QTableWidgetItem(fmt_comma(v.get("rate", 0)))
        rate_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 1, rate_item)

        # 2. Qty › Value (right-aligned)
        qty_item = QTableWidgetItem(fmt(v.get("quantity", 0)))
        qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 2, qty_item)

        # 3. Qty › Unit (left-aligned)
        unit = v.get("unit", "")
        unit = UNIT_DISPLAY.get(unit.lower(), unit) if unit else unit
        self.setItem(row, 3, QTableWidgetItem(unit))

        # 4. Source
        self.setItem(row, 4, QTableWidgetItem(v.get("rate_source", "Manual")))

        # 5. Total (right-aligned, read-only)
        try:
            rate = float(v.get("rate", 0) or 0)
            qty = float(v.get("quantity", 0) or 0)
            total = rate * qty
        except (ValueError, TypeError):
            total = 0.0

        total_item = QTableWidgetItem(fmt_comma(total))
        total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
        total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 5, total_item)

        # 6. Actions — right-aligned, compact margins
        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 6, 0)
        actions_layout.setSpacing(4)
        actions_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        if not self.is_trash_view:
            edit_btn = make_icon_btn("edit", "Edit")
            edit_btn.setFocusPolicy(Qt.NoFocus)
            edit_btn.clicked.connect(
                lambda checked=False, r=row: self.manager.open_edit_dialog(
                    self.component_name, r
                )
            )
            actions_layout.addWidget(edit_btn)

        if self.is_trash_view:
            trash_btn = make_icon_btn("restore", "Restore")
        else:
            trash_btn = make_icon_btn("trash", "Move to trash", icon_color="#e74c3c", hover_color="231, 76, 60")
        trash_btn.setFocusPolicy(Qt.NoFocus)
        trash_btn.clicked.connect(
            lambda checked=False, idx=original_index: self.manager.toggle_trash_status(
                self.component_name, idx, not self.is_trash_view
            )
        )
        actions_layout.addWidget(trash_btn)

        if self.is_trash_view:
            delete_btn = make_icon_btn("trash", "Delete permanently", icon_color="#e74c3c", hover_color="192, 57, 43")
            delete_btn.setFocusPolicy(Qt.NoFocus)
            delete_btn.clicked.connect(
                lambda checked=False, idx=original_index: self._confirm_permanent_delete(idx)
            )
            actions_layout.addWidget(delete_btn)

        if self._frozen:
            for btn in actions_widget.findChildren(QPushButton):
                btn.setEnabled(False)
        self.setCellWidget(row, 6, actions_widget)

        self.blockSignals(False)
        self.update_height()

    def freeze(self, frozen: bool = True):
        """Freeze/unfreeze action buttons in every row."""
        self._frozen = frozen
        for row in range(self.rowCount()):
            container = self.cellWidget(row, 6)
            if container:
                freeze_widgets(frozen, *container.findChildren(QPushButton))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        total = self.viewport().width()
        rest = max(1, total - _ACTION_W)

        qty_sub = max(45, int(rest * 0.08))

        widths = {
            0: max(150, int(rest * 0.36)),  # Work Name
            1: max(70,  int(rest * 0.13)),  # Rate
            2: qty_sub,                     # Qty › Value
            3: qty_sub,                     # Qty › Unit
            4: max(70,  int(rest * 0.15)),  # Source
            # col 5 (Total) stretches automatically via QHeaderView.Stretch
        }

        for col, width in widths.items():
            self.setColumnWidth(col, width)
