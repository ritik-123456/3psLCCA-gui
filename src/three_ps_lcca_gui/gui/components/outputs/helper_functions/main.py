"""
gui/components/outputs/helper_functions/main.py

Table-style horizontal bar chart for LCCA cost breakdown.
Pure PySide6 QPainter widget — no matplotlib dependency.

Usage:
    widget = LCCABreakdownChart(data)
    # or wrap in a scroll area:
    widget = LCCABreakdownChart.in_scroll(data)
"""

from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
)


# ── palette ──────────────────────────────────────────────────────────────────
_PILLAR_COLORS = {
    "economic":      QColor("#2c5f8a"),
    "environmental": QColor("#2e7d32"),
    "social":        QColor("#9c5a00"),
}

_STAGE_BG = {
    "initial_stage":  QColor("#dce8f5"),
    "use_stage":      QColor("#dff0d8"),
    "reconstruction": QColor("#fff3cd"),
    "end_of_life":    QColor("#f5dce8"),
}

_STAGE_LABELS = {
    "initial_stage":  "Initial Stage",
    "use_stage":      "Use Stage",
    "reconstruction": "Reconstruction",
    "end_of_life":    "End of Life",
}

_STAGE_ORDER = ["initial_stage", "use_stage", "reconstruction", "end_of_life"]

# column widths as fractions of total widget width
_W_STAGE  = 0.13
_W_ITEM   = 0.36
_W_BAR    = 0.38   # bar fills this fraction at max value
_W_VAL    = 0.13

_ROW_H    = 24      # px per data row
_HEADER_H = 28      # px for header row
_PAD_X    = 8       # horizontal text padding
_PAD_TOP  = 36      # space above header for title


# ── helpers ──────────────────────────────────────────────────────────────────
def _fmt(v: float) -> str:
    if v == 0:
        return "0"
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.3f} M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.2f} K"
    return f"{v:.0f}"


def _pretty(key: str, max_chars: int = 38) -> str:
    label = key.replace("_", " ").title()
    return label if len(label) <= max_chars else label[:max_chars - 1] + "…"


def _flatten(data: dict) -> list:
    """Return list of (stage_key, pillar, item_label, value) in display order."""
    rows = []
    for stage_key in _STAGE_ORDER:
        stage_data = data.get(stage_key)
        if not isinstance(stage_data, dict):
            continue
        for pillar in ("economic", "environmental", "social"):
            pillar_data = stage_data.get(pillar, {})
            if not isinstance(pillar_data, dict):
                continue
            for item_key, value in pillar_data.items():
                rows.append((stage_key, pillar, _pretty(item_key), float(value)))
    return rows


# ── widget ────────────────────────────────────────────────────────────────────
class LCCABreakdownChart(QWidget):
    """
    Paints a table-style horizontal bar chart for all LCCA cost line items.

    Columns:  Stage | Pillar | Cost Item | ████ Bar ████ | Value
    """

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._rows = _flatten(data)
        self._max_val = max((r[3] for r in self._rows), default=1.0) or 1.0
        n = len(self._rows)
        total_h = _PAD_TOP + _HEADER_H + n * _ROW_H + 16
        self.setMinimumHeight(total_h)
        self.setMinimumWidth(780)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(total_h)

    # ── painting ──────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        W = self.width()

        # column x positions
        x_stage  = 0
        x_item   = int(W * _W_STAGE)
        x_bar    = x_item + int(W * _W_ITEM)
        x_val    = x_bar  + int(W * _W_BAR)
        bar_max  = int(W * _W_BAR) - _PAD_X * 2

        col_xs   = [x_stage, x_item, x_bar, x_val, W]
        col_ws   = [col_xs[i+1] - col_xs[i] for i in range(4)]

        # ── title ─────────────────────────────────────────────────────────────
        title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(QColor("#1a1a1a"))
        p.drawText(QRect(0, 4, W, _PAD_TOP - 4),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   "LCCA Cost Breakdown — All Stages")

        # ── header ────────────────────────────────────────────────────────────
        hdr_y = _PAD_TOP
        p.fillRect(0, hdr_y, W, _HEADER_H, QColor("#2c3e50"))
        hdr_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(hdr_font)
        p.setPen(QColor("#ffffff"))
        headers = ["Stage", "Cost Item", "Relative Cost", "Value"]
        for i, txt in enumerate(headers):
            align = (Qt.AlignmentFlag.AlignHCenter if i in (0, 2)
                     else Qt.AlignmentFlag.AlignLeft)
            lpad = 0 if i in (0, 2) else _PAD_X
            p.drawText(
                QRect(col_xs[i] + lpad, hdr_y, col_ws[i] - lpad, _HEADER_H),
                align | Qt.AlignmentFlag.AlignVCenter, txt
            )

        # ── rows ──────────────────────────────────────────────────────────────
        row_font   = QFont("Segoe UI", 7)
        label_font = QFont("Segoe UI", 7, QFont.Weight.Medium)
        val_font   = QFont("Segoe UI", 7)

        prev_stage = None
        for idx, (stage_key, pillar, item_label, value) in enumerate(self._rows):
            ry = _PAD_TOP + _HEADER_H + idx * _ROW_H

            # row background
            if stage_key != prev_stage:
                bg = _STAGE_BG.get(stage_key, QColor("#f0f0f0"))
            else:
                bg = QColor("#ffffff") if idx % 2 else _STAGE_BG.get(stage_key, QColor("#f5f5f5"))
            p.fillRect(0, ry, W, _ROW_H, bg)

            # stage label (only first row of each stage block)
            if stage_key != prev_stage:
                p.setFont(label_font)
                p.setPen(QColor("#1a3a5c"))
                p.drawText(
                    QRect(col_xs[0] + 2, ry, col_ws[0] - 4, _ROW_H),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    _STAGE_LABELS.get(stage_key, stage_key),
                )
                prev_stage = stage_key

            # item label
            p.setFont(row_font)
            p.setPen(QColor("#222222"))
            p.drawText(
                QRect(col_xs[1] + _PAD_X, ry, col_ws[1] - _PAD_X, _ROW_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                item_label,
            )

            # bar
            bar_w = int((value / self._max_val) * bar_max)
            bar_color = _PILLAR_COLORS.get(pillar, QColor("#555555"))
            bar_color_fill = QColor(bar_color)
            bar_color_fill.setAlpha(200)
            bar_x = x_bar + _PAD_X
            bar_y = ry + 5
            bar_h = _ROW_H - 10
            p.fillRect(bar_x, bar_y, bar_w, bar_h, bar_color_fill)

            # value label
            p.setFont(val_font)
            p.setPen(QColor("#111111"))
            p.drawText(
                QRect(col_xs[3] + _PAD_X, ry, col_ws[3] - _PAD_X, _ROW_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                _fmt(value),
            )

        # ── column dividers ───────────────────────────────────────────────────
        total_h = _PAD_TOP + _HEADER_H + len(self._rows) * _ROW_H
        p.setPen(QPen(QColor("#cccccc"), 1))
        for x in (x_item, x_bar, x_val):
            p.drawLine(x, _PAD_TOP, x, total_h)

        # ── legend ────────────────────────────────────────────────────────────
        legend_y = total_h + 4
        lx = _PAD_X
        p.setFont(QFont("Segoe UI", 7))
        for pillar, color in _PILLAR_COLORS.items():
            c = QColor(color)
            c.setAlpha(200)
            p.fillRect(lx, legend_y + 3, 12, 10, c)
            p.setPen(QColor("#333333"))
            p.drawText(lx + 15, legend_y, 100, 16,
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       pillar.capitalize())
            lx += 110

        p.end()

    @classmethod
    def in_scroll(cls, data: dict, parent=None) -> QScrollArea:
        """Wrap the chart in a QScrollArea for use in layouts."""
        chart = cls(data)
        scroll = QScrollArea(parent)
        scroll.setWidgetResizable(True)
        scroll.setWidget(chart)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return scroll


# ── standalone test ───────────────────────────────────────────────────────────
sample_input = {
    "initial_stage": {
        "economic": {
            "initial_construction_cost": 13510517.107590165,
            "time_cost_of_loan": 226864.09976495153,
        },
        "environmental": {
            "initial_material_carbon_emission_cost": 362252.33909257106,
            "initial_vehicular_emission_cost": 7687.78,
        },
        "social": {"initial_road_user_cost": 133646.6},
    },
    "use_stage": {
        "economic": {
            "routine_inspection_costs": 691806.0284941545,
            "periodic_maintenance": 769450.9703114751,
            "major_inspection_costs": 641209.1419262293,
            "major_repair_cost": 557984.3565434739,
            "replacement_costs_for_bearing_and_expansion_joint": 1391899.311934074,
        },
        "environmental": {
            "periodic_carbon_costs": 18911.74561466677,
            "major_repair_material_carbon_emission_costs": 822.8561882487752,
            "major_repair_vehicular_emission_costs": 1831.76,
            "vehicular_emission_costs_for_replacement_of_bearing_and_expansion_joint": 115.02,
        },
        "social": {
            "major_repair_road_user_costs": 31843.87,
            "road_user_costs_for_replacement_of_bearing_and_expansion_joint": 1999.56,
        },
    },
    "reconstruction": {
        "economic": {
            "total_demolition_and_disposal_costs": 447198.11626123457,
            "cost_of_reconstruction_after_demolition": 4471981.162612345,
            "total_scrap_value": 0.0,
            "time_cost_of_loan": 75092.01702219897,
        },
        "environmental": {
            "carbon_costs_demolition_and_disposal": 11990.552423964102,
            "carbon_cost_of_reconstruction_after_demolition": 119905.52423964103,
            "demolition_vehicular_emission_cost": 489.36,
            "reconstruction_vehicular_emission_cost": 2544.66,
        },
        "social": {"ruc_demolition": 8507.12, "ruc_reconstruction": 44237.03},
    },
    "end_of_life": {
        "economic": {
            "total_demolition_and_disposal_costs": 312092.94518533285,
            "total_scrap_value": 0.0,
        },
        "environmental": {
            "carbon_costs_demolition_and_disposal": 8368.029033038392,
            "demolition_vehicular_emission_cost": 341.51,
        },
        "social": {"ruc_demolition": 5936.99},
    },
    "warnings": [],
    "notes": [],
}

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    scroll = LCCABreakdownChart.in_scroll(sample_input)
    scroll.setWindowTitle("LCCA Breakdown Chart")
    scroll.resize(900, 700)
    scroll.show()
    sys.exit(app.exec())
