"""
gui/components/outputs/lcc_plot.py

Creates an interactive matplotlib chart from LCC analysis results.
Use LCCChartWidget(results) to get a QWidget ready to embed in Qt.
"""

from .plots_helper.Pie import COLORS
from .lcc_data import (
    M, sci_label, _get,
    build_chart_data,
    STAGE_DEFS, stage_totals,
    BREAKDOWN_STAGES,
    CATEGORY_COLORS,
)
from .plots_helper.bar_chart import create_bar_chart

import matplotlib
matplotlib.use("QtAgg")

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QHeaderView, QLabel, QScrollArea,
    QSizePolicy, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
except ImportError:
    from matplotlib.backends.backend_qt import FigureCanvasQTAgg, NavigationToolbar2QT



class LCCDetailsTable(QWidget):
    """Stage × category summary of LCC costs."""

    def __init__(self, results: dict, currency: str = "INR", parent=None):
        super().__init__(parent)
        self._build(results, currency)

    def _build(self, results: dict, currency: str = "INR"):
        # Compute per-stage totals
        stage_rows = []
        for stage_label, result_key, cat_keys in STAGE_DEFS:
            totals = stage_totals(results, result_key, cat_keys)
            if not totals:
                continue  # stage not applicable
            eco  = totals.get("Economic",      0.0)
            env  = totals.get("Environmental", 0.0)
            soc  = totals.get("Social",        0.0)
            # change - store result_key for stage color lookup per row
            stage_rows.append((stage_label, result_key, eco, env, soc, eco + env + soc))

        n_rows = len(stage_rows) + 1  # +1 grand total

        table = QTableWidget(n_rows, 5, self)
        table.setHorizontalHeaderLabels([
            "Stage", f"Economic\n(M {currency})", f"Environmental\n(M {currency})",
            f"Social\n(M {currency})", f"Stage Total\n(M {currency})",
        ])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in range(1, 5):
            table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        # table.setAlternatingRowColors(True)
        table.setAlternatingRowColors(False)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # change - map result_key → stage name for color lookups
        _result_key_to_stage = {
            "initial_stage":  "Initial",
            "use_stage":      "Use",
            "reconstruction": "Reconstruction",
            "end_of_life":    "End-of-Life",
        }

        # change - custom header paints section colors directly, bypassing unreliable QSS nth-child
        _header_colors = [
            COLORS["summary_neutral"]["stage_col"],    # col 0: Stage
            COLORS["pillars"]["Economic"],             # col 1: Economic
            COLORS["pillars"]["Environmental"],        # col 2: Environmental
            COLORS["pillars"]["Social"],               # col 3: Social
            COLORS["summary_neutral"]["total_col"],    # col 4: Stage Total
        ]

        class _ColoredHeader(QHeaderView):
            """Paints each header section with its designated pillar/neutral color."""
            def __init__(self, orientation, parent=None):
                super().__init__(orientation, parent)
                self.setSectionsClickable(False)

            def paintSection(self, painter, rect, logical_index):
                painter.save()
                # Fill with designated color
                if logical_index < len(_header_colors):
                    painter.fillRect(rect, QColor(_header_colors[logical_index]))
                else:
                    painter.fillRect(rect, self.palette().button().color())
                # Draw border
                painter.setPen(QColor("#aaaaaa"))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
                # Draw text bold black
                bold_font = self.font()
                bold_font.setBold(True)
                painter.setFont(bold_font)
                painter.setPen(QColor("#000000"))
                painter.drawText(rect.adjusted(4, 0, -4, 0),
                                 Qt.AlignCenter | Qt.TextWordWrap,
                                 self.model().headerData(logical_index, Qt.Horizontal) or "")
                painter.restore()

        colored_header = _ColoredHeader(Qt.Horizontal, table)
        table.setHorizontalHeader(colored_header)
        # Re-apply labels and resize modes after replacing header
        table.setHorizontalHeaderLabels([
            "Stage", f"Economic\n(M {currency})", f"Environmental\n(M {currency})",
            f"Social\n(M {currency})", f"Stage Total\n(M {currency})",
        ])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in range(1, 5):
            table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)

        table.setStyleSheet("QTableWidget { gridline-color: #aaaaaa; }")

        bold = QFont()
        bold.setBold(True)

        from PySide6.QtGui import QBrush

        # change - _item sets BackgroundRole as QBrush so _ColorDelegate paints correctly
        def _item(text, align=Qt.AlignLeft | Qt.AlignVCenter, font=None,
                  green=False, bg: QColor = None):
            it = QTableWidgetItem(text)
            it.setTextAlignment(align)
            if font:
                it.setFont(font)
            if bg:
                it.setData(Qt.BackgroundRole, QBrush(bg))
                it.setData(Qt.ForegroundRole, QBrush(QColor("#000000")))
            if green:
                it.setData(Qt.ForegroundRole, QBrush(QColor("#2e7d32")))
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            return it

        def _val(v, bold_font=None, bg: QColor = None):
            text = f"{v:.4f}"
            return _item(text, Qt.AlignRight | Qt.AlignVCenter, bold_font,
                         green=(v < 0), bg=bg)

        grand_eco = grand_env = grand_soc = grand_total = 0.0

        for row_idx, (label, result_key, eco, env, soc, total) in enumerate(stage_rows):
            grand_eco   += eco
            grand_env   += env
            grand_soc   += soc
            grand_total += total

            # change - col 0 gets stage strip color, cols 1-4 get white
            stage_name  = _result_key_to_stage.get(result_key, "")
            strip_color = QColor(COLORS["stages"].get(stage_name, "#DDDDDD"))
            white       = QColor("#FFFFFF")

            # col 0: stage strip color (same as LCC Breakdown left sidebar)
            table.setItem(row_idx, 0, _item(label, font=bold, bg=strip_color))
            # cols 1-4: white data cells - color identity lives in the headers
            table.setItem(row_idx, 1, _val(eco,   bold_font=bold, bg=white))
            table.setItem(row_idx, 2, _val(env,   bold_font=bold, bg=white))
            table.setItem(row_idx, 3, _val(soc,   bold_font=bold, bg=white))
            table.setItem(row_idx, 4, _val(total, bold_font=bold, bg=white))

        # change - Grand Total: col 0 silver-grey, cols 1-4 white
        tr = len(stage_rows)
        grand_stage_bg = QColor(COLORS["summary_neutral"]["stage_col"])
        white          = QColor("#FFFFFF")

        table.setItem(tr, 0, _item("Grand Total", font=bold, bg=grand_stage_bg))
        for col, val in enumerate([grand_eco, grand_env, grand_soc], start=1):
            table.setItem(tr, col, _val(val, bold_font=bold, bg=white))
        table.setItem(tr, 4, _val(grand_total, bold_font=bold, bg=white))

        # change - _ColorDelegate on all 5 cols to bypass dark-theme QSS
        for col in range(5):
            table.setItemDelegateForColumn(col, _ColorDelegate(table))

        # change - fix row height to 32px for compact summary table
        for row in range(n_rows):
            table.setRowHeight(row, 32)
        table.setSizeAdjustPolicy(QTableWidget.AdjustToContents)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        lbl = QLabel("<b>LCC Summary</b>")
        lbl.setContentsMargins(0, 12, 0, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(lbl)
        layout.addWidget(table)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)


# ---------------------------------------------------------------------------
# Detailed breakdown table
# ---------------------------------------------------------------------------

class _VerticalTextDelegate(QStyledItemDelegate):
    """Renders cell text rotated 90° counter-clockwise for the stage column."""

    def paint(self, painter, option, index):
        painter.save()
        bg = index.data(Qt.BackgroundRole)
        if bg:
            c = bg.color() if hasattr(bg, "color") else QColor(bg)
            painter.fillRect(option.rect, c)

        painter.translate(
            option.rect.x() + option.rect.width() / 2,
            option.rect.y() + option.rect.height() / 2,
        )
        painter.rotate(-90)

        text_rect = QRect(
            -option.rect.height() // 2,
            -option.rect.width() // 2,
            option.rect.height(),
            option.rect.width(),
        )
        text = (index.data(Qt.DisplayRole) or "").replace("\n", " ")
        font = index.data(Qt.FontRole)
        if font:
            painter.setFont(font)
        fg = index.data(Qt.ForegroundRole)
        painter.setPen(fg.color() if fg and hasattr(fg, "color") else option.palette.text().color())
        painter.drawText(text_rect, Qt.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(64, 80)



class _ColorDelegate(QStyledItemDelegate):
    """Paints cell background from BackgroundRole brush, ignoring QSS overrides.
    This is the only reliable way to force per-item colors in a dark-themed Qt app."""

    def paint(self, painter, option, index):
        painter.save()
        # Fill background from the item's BackgroundRole brush
        bg = index.data(Qt.BackgroundRole)
        if bg:
            color = bg.color() if hasattr(bg, 'color') else QColor(bg)
            painter.fillRect(option.rect, color)
        else:
            painter.fillRect(option.rect, option.palette.base())

        # Draw text with ForegroundRole color
        fg = index.data(Qt.ForegroundRole)
        text_color = fg.color() if fg and hasattr(fg, 'color') else QColor("#000000")
        painter.setPen(text_color)

        text = index.data(Qt.DisplayRole) or ""
        align = index.data(Qt.TextAlignmentRole)
        if align is None:
            align = Qt.AlignLeft | Qt.AlignVCenter

        padding = 6
        text_rect = option.rect.adjusted(padding, 0, -padding, 0)
        painter.drawText(text_rect, int(align), text)
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        return base


class LCCBreakdownTable(QWidget):
    """Detailed row-by-row LCC cost breakdown with stage-coloured groups."""

    def __init__(self, results: dict, currency: str = "INR", parent=None):
        super().__init__(parent)
        self._build(results, currency)

    def _build(self, results: dict, currency: str = "INR"):
        # Collect applicable stages - keep cat for row colouring
        active_stages = []
        for stage_def in BREAKDOWN_STAGES:
            stage_data = results.get(stage_def["result_key"], {})
            if stage_def.get("optional") and not isinstance(stage_data.get("economic"), dict):
                continue
            rows = [
                (label, float(stage_data.get(cat, {}).get(key, 0.0)), cat)
                for cat, key, label in stage_def["rows"]
                if stage_data.get(cat, {}).get(key) is not None
            ]
            if rows:
                active_stages.append((stage_def, rows))

        total_rows = sum(len(r) for _, r in active_stages)

        table = QTableWidget(total_rows, 3, self)
        table.setStyleSheet("QTableWidget { gridline-color: #aaaaaa; }")
        table.setHorizontalHeaderLabels(["", "Costs", f"Cost in Present Time ({currency})"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        table.setColumnWidth(0, 64)
        table.setColumnWidth(2, 190)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setShowGrid(True)
        table.setWordWrap(True)

        # change - custom header paints col colors directly: grey, steel blue, warm orange
        _breakdown_header_colors = [
            COLORS["summary_neutral"]["stage_col"],   # col 0: stage strip (empty label)
            "#B0C4DE",                                 # col 1: Costs - steel blue
            COLORS["summary_neutral"]["total_col"],   # col 2: Cost in Present Time - warm orange
        ]

        class _BreakdownHeader(QHeaderView):
            """Paints LCCBreakdownTable header sections with designated colors."""
            def __init__(self, orientation, parent=None):
                super().__init__(orientation, parent)
                self.setSectionsClickable(False)

            def paintSection(self, painter, rect, logical_index):
                painter.save()
                if logical_index < len(_breakdown_header_colors):
                    painter.fillRect(rect, QColor(_breakdown_header_colors[logical_index]))
                else:
                    painter.fillRect(rect, self.palette().button().color())
                painter.setPen(QColor("#aaaaaa"))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
                bold_font = self.font()
                bold_font.setBold(True)
                painter.setFont(bold_font)
                painter.setPen(QColor("#000000"))
                label = self.model().headerData(logical_index, Qt.Horizontal) or ""
                painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignCenter, label)
                painter.restore()

        breakdown_header = _BreakdownHeader(Qt.Horizontal, table)
        table.setHorizontalHeader(breakdown_header)
        # Re-apply labels and column widths after replacing header
        table.setHorizontalHeaderLabels(["", "Costs", f"Cost in Present Time ({currency})"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        table.setColumnWidth(0, 64)
        table.setColumnWidth(2, 190)

        table.setItemDelegateForColumn(0, _VerticalTextDelegate(table))
        # change - _ColorDelegate on cols 1 & 2 to bypass dark-theme QSS overrides
        table.setItemDelegateForColumn(1, _ColorDelegate(table))
        table.setItemDelegateForColumn(2, _ColorDelegate(table))

        bold = QFont()
        bold.setBold(True)

        from PySide6.QtGui import QBrush

        def _cell(text, bg: QColor, align=Qt.AlignCenter | Qt.AlignVCenter, font=None):
            it = QTableWidgetItem(text)
            it.setTextAlignment(align)
            # Use QBrush so BackgroundRole is set correctly regardless of QSS
            it.setData(Qt.BackgroundRole, QBrush(bg))
            it.setData(Qt.ForegroundRole, QBrush(QColor("#000000")))
            if font:
                it.setFont(font)
            it.setFlags(Qt.ItemIsEnabled)
            return it

        row_idx = 0
        for stage_def, stage_rows in active_stages:
            stage_bg = QColor(stage_def["stage_color"])
            n        = len(stage_rows)

            # change - resolve stage tint color for "Cost in Present Time" col
            _result_key_to_stage = {
                "initial_stage":  "Initial",
                "use_stage":      "Use",
                "reconstruction": "Reconstruction",
                "end_of_life":    "End-of-Life",
            }
            _stage_name = _result_key_to_stage.get(stage_def["result_key"], "")
            stage_tint_bg = QColor(
                COLORS["stage_cost_tints"].get(_stage_name, "#EEEEEE")
            )

            # Stage label cell - spans all rows in this stage
            table.setItem(row_idx, 0, _cell(stage_def["label"], stage_bg, font=bold))
            if n > 1:
                table.setSpan(row_idx, 0, n, 1)

            for i, (desc, val, cat) in enumerate(stage_rows):
                r      = row_idx + i
                cat_str = ""

                # handle enum or object safely
                if hasattr(cat, "name"):
                    cat_str = cat.name.lower()
                else:
                    cat_str = str(cat).lower()

                # mapping
                if "economic" in cat_str:
                    row_bg = QColor(CATEGORY_COLORS["economic"])
                elif "environmental" in cat_str or "emission" in cat_str:
                    row_bg = QColor(CATEGORY_COLORS["environmental"])
                elif "social" in cat_str or "user" in cat_str or "time" in cat_str:
                    row_bg = QColor(CATEGORY_COLORS["social"])
                else:
                    print("⚠️ UNKNOWN CATEGORY:", cat)
                    row_bg = QColor("#FF0000")  # debug)

                
                # table.setItem(r, 1, _cell(desc, row_bg, align=Qt.AlignLeft | Qt.AlignVCenter))
                # cost_item = _cell(
                #     f"INR \u20b9{val:,.2f}", row_bg,
                #     align=Qt.AlignRight | Qt.AlignVCenter,
                # )
                # if val < 0:
                #     cost_item.setForeground(QColor("#2e7d32"))
                # table.setItem(r, 2, cost_item)


                # --- column 1: pillar color (Economic / Environmental / Social) ---
                desc_item = _cell(desc, row_bg, align=Qt.AlignLeft | Qt.AlignVCenter)
                table.setItem(r, 1, desc_item)

                # --- column 2: white background ─────────────────────────────────────────
                # change - white background for uniform "Cost in Present Time" col
                cost_item = _cell(
                    f"{val:,.2f}", QColor("#FFFFFF"),
                    align=Qt.AlignRight | Qt.AlignVCenter,
                )
                if val < 0:
                    cost_item.setData(Qt.ForegroundRole, QBrush(QColor("#2e7d32")))
                table.setItem(r, 2, cost_item)

            row_idx += n

        # change - fix row height to 32px instead of resizeRowsToContents which was too tall
        for row in range(total_rows):
            table.setRowHeight(row, 32)
        table.setSizeAdjustPolicy(QTableWidget.AdjustToContents)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        lbl = QLabel("<b>LCC Breakdown</b>")
        lbl.setContentsMargins(0, 16, 0, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(lbl)
        layout.addWidget(table)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)


# ---------------------------------------------------------------------------
# Public widget
# ---------------------------------------------------------------------------

class _ScrollForwarder(QObject):
    """Forward wheel events from the canvas to the nearest parent QScrollArea."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            parent = obj.parent()
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    QApplication.sendEvent(parent.verticalScrollBar(), event)
                    return True
                parent = parent.parent()
        return False


class LCCChartWidget(QWidget):
    """
    Interactive LCC bar chart widget.
    Includes a navigation toolbar (zoom / pan / save) and hover tooltips.
    """

    def __init__(self, results: dict, currency: str = "INR", parent=None):
        super().__init__(parent)
        self._currency = currency

        # Force white background and dark text for the graph
        text_color = "#000000"
        bg_color   = "#FFFFFF"

        self._values, self._labels, stage_info = build_chart_data(results)
        fig, self._bars = create_bar_chart(
            self._values, self._labels, stage_info, text_color, bg_color, currency=currency
        )

        self._canvas = FigureCanvasQTAgg(fig)
        self._canvas.setMinimumHeight(480)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._scroll_forwarder = _ScrollForwarder(self)
        self._canvas.installEventFilter(self._scroll_forwarder)
        toolbar = NavigationToolbar2QT(self._canvas, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(self._canvas)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # ── Hover annotation ──────────────────────────────────────────────
        ax = fig.axes[0]
        self._annot = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(14, 14),
            textcoords="offset points",
            bbox=dict(
                boxstyle="round,pad=0.5",
                fc=bg_color,
                ec="#aaaaaa",
                alpha=0.95,
                linewidth=1,
            ),
            fontsize=8,
            color=text_color,
            zorder=10,
        )
        self._annot.set_visible(False)

        self._canvas.mpl_connect("motion_notify_event", self._on_hover)
        self._canvas.mpl_connect("axes_leave_event",    self._on_leave)

    def sizeHint(self):
        # toolbar ≈ 36px + canvas minimum 480px
        return QSize(super().sizeHint().width(), 520)

    # ── Hover handlers ────────────────────────────────────────────────────

    def _on_hover(self, event):
        if event.inaxes is None:
            self._set_annot_visible(False)
            return

        for bar, label, val in zip(self._bars, self._labels, self._values):
            if bar.contains(event)[0]:
                x = bar.get_x() + bar.get_width() / 2
                self._annot.xy = (x, val)
                inr = val * 1_000_000
                sign = "−" if val < 0 else ""
                self._annot.set_text(
                    f"{label}\n"
                    f"{self._currency} {sign}{abs(inr):,.0f}\n"
                    f"({sign}{abs(val):.4f} M {self._currency})"
                )
                self._set_annot_visible(True)
                return

        self._set_annot_visible(False)

    def _on_leave(self, event):
        self._set_annot_visible(False)

    def _set_annot_visible(self, visible: bool):
        if self._annot.get_visible() != visible:
            self._annot.set_visible(visible)
            self._canvas.draw_idle()


# Keep backward-compatible alias for any existing call sites
def create_lcc_figure(results: dict):
    palette = QApplication.instance().palette()
    text_color = palette.windowText().color().name()
    bg_color   = palette.window().color().name()
    values, labels, stage_info = build_chart_data(results)
    fig, _ = create_bar_chart(values, labels, stage_info, text_color, bg_color)
    return fig
