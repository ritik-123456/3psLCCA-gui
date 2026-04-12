"""
gui/components/outputs/lcc_plot.py

Creates an interactive matplotlib chart from LCC analysis results.
Use LCCChartWidget(results) to get a QWidget ready to embed in Qt.
"""

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt

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


def M(x):
    """Convert to Million INR."""
    return x / 1e6


def sci_label(x):
    if x == 0:
        return "0"
    exp = int(np.floor(np.log10(abs(x))))
    coeff = x / (10 ** exp)
    return rf"${coeff:.0f}\cdot10^{{{exp}}}$"


def _get(d, *keys, default=0.0):
    """Safe nested dict access."""
    node = d
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
    return node if node is not None else default


def _build_chart_data(results: dict):
    """
    Build values, labels, and stage_info from results.
    Returns (values, labels, stage_info).
    Stage order: Initial → Use → Reconstruction (optional) → End-of-Life
    """
    values = []
    labels = []

    # ── Initial stage (0-4) ────────────────────────────────────────────────
    values += [
        M(_get(results, "initial_stage", "economic",     "initial_construction_cost")),
        M(_get(results, "initial_stage", "environmental","initial_material_carbon_emission_cost")),
        M(_get(results, "initial_stage", "economic",     "time_cost_of_loan")),
        M(_get(results, "initial_stage", "social",       "initial_road_user_cost")),
        M(_get(results, "initial_stage", "environmental","initial_vehicular_emission_cost")),
    ]
    labels += [
        "Initial construction cost",
        "Initial carbon emission cost",
        "Time-related cost",
        "Road user cost (construction)",
        "Vehicular emission (rerouting)",
    ]

    # ── Use stage (5-15) ───────────────────────────────────────────────────
    values += [
        M(_get(results, "use_stage", "economic",     "routine_inspection_costs")),
        M(_get(results, "use_stage", "economic",     "periodic_maintenance")),
        M(_get(results, "use_stage", "environmental","periodic_carbon_costs")),
        M(_get(results, "use_stage", "economic",     "major_inspection_costs")),
        M(_get(results, "use_stage", "economic",     "major_repair_cost")),
        M(_get(results, "use_stage", "environmental","major_repair_material_carbon_emission_costs")),
        M(_get(results, "use_stage", "environmental","major_repair_vehicular_emission_costs")),
        M(_get(results, "use_stage", "social",       "major_repair_road_user_costs")),
        M(_get(results, "use_stage", "economic",     "replacement_costs_for_bearing_and_expansion_joint")),
        M(_get(results, "use_stage", "environmental","vehicular_emission_costs_for_replacement_of_bearing_and_expansion_joint")),
        M(_get(results, "use_stage", "social",       "road_user_costs_for_replacement_of_bearing_and_expansion_joint")),
    ]
    labels += [
        "Routine inspection cost",
        "Periodic maintenance cost",
        "Maintenance carbon cost",
        "Major inspection cost",
        "Major repair cost",
        "Repair carbon emission cost",
        "Repair vehicular emission cost",
        "Road user cost (repairs)",
        "Bearing & joint replacement cost",
        "Vehicular emission (replacement)",
        "Road user cost (replacement)",
    ]

    stage_info = [
        {"start": 0,  "end": 4,  "color": "#cfd9e8", "title": "Initial Stage",      "tick_color": "#2c4a75"},
        {"start": 5,  "end": 15, "color": "#cfe8e2", "title": "Use Stage",           "tick_color": "#1f6f66"},
    ]

    # ── Reconstruction stage (optional) ────────────────────────────────────
    if bool(results.get("reconstruction")):
        recon_start = len(values)
        values += [
            M(_get(results, "reconstruction", "economic",     "cost_of_reconstruction_after_demolition")),
            M(_get(results, "reconstruction", "environmental","carbon_cost_of_reconstruction_after_demolition")),
            M(_get(results, "reconstruction", "economic",     "time_cost_of_loan")),
            M(_get(results, "reconstruction", "economic",     "total_demolition_and_disposal_costs")),
            M(_get(results, "reconstruction", "environmental","carbon_costs_demolition_and_disposal")),
            M(_get(results, "reconstruction", "environmental","demolition_vehicular_emission_cost")),
            M(_get(results, "reconstruction", "environmental","reconstruction_vehicular_emission_cost")),
            M(_get(results, "reconstruction", "social",       "ruc_demolition")),
            M(_get(results, "reconstruction", "social",       "ruc_reconstruction")),
            -M(_get(results, "reconstruction", "economic",    "total_scrap_value")),
        ]
        labels += [
            "Reconstruction cost",
            "Reconstruction carbon cost",
            "Time-related cost (recon.)",
            "Demolition & disposal (recon.)",
            "Demolition carbon cost (recon.)",
            "Vehicular emission (demo. recon.)",
            "Vehicular emission (reconstruction)",
            "Road user cost (demo. recon.)",
            "Road user cost (reconstruction)",
            "Scrap value credit (recon.)",
        ]
        stage_info.append({
            "start": recon_start, "end": len(values) - 1,
            "color": "#e8d5f0", "title": "Reconstruction Stage", "tick_color": "#5a3270",
        })

    # ── End-of-life stage ──────────────────────────────────────────────────
    eol_start = len(values)
    values += [
        M(_get(results, "end_of_life", "economic",     "total_demolition_and_disposal_costs")),
        M(_get(results, "end_of_life", "environmental","carbon_costs_demolition_and_disposal")),
        M(_get(results, "end_of_life", "environmental","demolition_vehicular_emission_cost")),
        M(_get(results, "end_of_life", "social",       "ruc_demolition")),
        -M(_get(results, "end_of_life", "economic",    "total_scrap_value")),
    ]
    labels += [
        "Demolition & disposal cost",
        "Demolition carbon cost",
        "Vehicular emission (demolition)",
        "Road user cost (demolition)",
        "Scrap value credit",
    ]
    stage_info.append({
        "start": eol_start, "end": len(values) - 1,
        "color": "#edd5d5", "title": "End-of-Life Stage", "tick_color": "#7a3b3b",
    })

    return values, labels, stage_info


def _create_figure(values, labels, stage_info, text_color, bg_color):
    """Build and return (fig, bars) from pre-computed chart data."""
    _N = len(labels)
    x = np.arange(_N)

    fig_width = max(14, _N * 0.65)
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)
    ax.tick_params(colors=text_color)
    ax.yaxis.label.set_color(text_color)
    for spine in ax.spines.values():
        spine.set_edgecolor(text_color)

    # Stage panels
    for stage in stage_info:
        ax.axvspan(stage["start"] - 0.5, stage["end"] + 0.5,
                   color=stage["color"], alpha=0.9)

    # Bars
    bar_colors = ["#8b1a1a" if v >= 0 else "#2e7d32" for v in values]
    bars = ax.bar(x, values, 0.50, color=bar_colors)

    # Stage dividers and titles
    for stage in stage_info[1:]:
        ax.axvline(stage["start"] - 0.5, color="black", linewidth=1.5)
    ax.axhline(0, color="black", linewidth=0.8)

    for stage in stage_info:
        center = (stage["start"] + stage["end"]) / 2
        ax.text(center, 1.02, stage["title"],
                transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=8, fontweight="bold",
                color=text_color)

    # Y limits and bar value labels
    max_val = max(values)
    min_val = min(values)
    ylim_top = max(max_val * 1.3 if max_val > 0 else max_val * 0.7, 1.0)
    ylim_bot = min(min_val * 1.3 if min_val < 0 else 0.0, -0.5)
    ax.set_ylim(ylim_bot, ylim_top)

    # Offset is proportional to total range; when positive bars dominate,
    # the offset can push negative labels below ylim_bot — extend it if needed.
    offset = (ylim_top - ylim_bot) * 0.02
    if min_val < 0 and (min_val - offset) < ylim_bot:
        ylim_bot = (min_val - offset) * 1.05
        ax.set_ylim(ylim_bot, ylim_top)

    for bar, val in zip(bars, values):
        lbl = sci_label(val) if abs(val) < 0.1 else f"{val:.2f}"
        y_pos = val + offset if val >= 0 else val - offset
        ax.text(
            bar.get_x() + bar.get_width() / 2, y_pos, lbl,
            ha="center", va="bottom" if val >= 0 else "top",
            rotation=90, fontsize=7, color=bar.get_facecolor(),
        )

    # Axes styling
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xticks(x)

    # Wrap labels for x-axis (two lines)
    wrapped = [lbl.replace(" (", "\n(") if len(lbl) > 22 else lbl for lbl in labels]
    ax.set_xticklabels(wrapped, rotation=90, fontsize=6, color=text_color)
    ax.set_ylabel("Cost (Million INR)", fontsize=8, color=text_color)
    ax.tick_params(axis='y', labelsize=7, colors=text_color)
    ax.tick_params(axis='x', colors=text_color)
    ax.axhline(0, color=text_color, linewidth=0.8)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_xlim(-0.5, _N - 0.5)

    tick_color_map = {i: s["tick_color"] for s in stage_info for i in range(s["start"], s["end"] + 1)}
    for i, lbl in enumerate(ax.get_xticklabels()):
        lbl.set_color(tick_color_map.get(i, text_color))

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.40, top=0.88)
    return fig, bars


# ---------------------------------------------------------------------------
# Summary table — stage × category
# ---------------------------------------------------------------------------

# Each entry: (stage_label, result_key, {category: [keys...]} )
# Prefix a key with "-" to subtract it (scrap value credits).
_STAGE_DEFS = [
    ("Initial Stage", "initial_stage", {
        "Economic":      ["initial_construction_cost", "time_cost_of_loan"],
        "Environmental": ["initial_material_carbon_emission_cost", "initial_vehicular_emission_cost"],
        "Social":        ["initial_road_user_cost"],
    }),
    ("Use Stage", "use_stage", {
        "Economic":      ["routine_inspection_costs", "periodic_maintenance",
                          "major_inspection_costs", "major_repair_cost",
                          "replacement_costs_for_bearing_and_expansion_joint"],
        "Environmental": ["periodic_carbon_costs",
                          "major_repair_material_carbon_emission_costs",
                          "major_repair_vehicular_emission_costs",
                          "vehicular_emission_costs_for_replacement_of_bearing_and_expansion_joint"],
        "Social":        ["major_repair_road_user_costs",
                          "road_user_costs_for_replacement_of_bearing_and_expansion_joint"],
    }),
    ("Reconstruction Stage", "reconstruction", {
        "Economic":      ["cost_of_reconstruction_after_demolition", "time_cost_of_loan",
                          "total_demolition_and_disposal_costs", "-total_scrap_value"],
        "Environmental": ["carbon_cost_of_reconstruction_after_demolition",
                          "carbon_costs_demolition_and_disposal",
                          "demolition_vehicular_emission_cost",
                          "reconstruction_vehicular_emission_cost"],
        "Social":        ["ruc_demolition", "ruc_reconstruction"],
    }),
    ("End-of-Life Stage", "end_of_life", {
        "Economic":      ["total_demolition_and_disposal_costs", "-total_scrap_value"],
        "Environmental": ["carbon_costs_demolition_and_disposal", "demolition_vehicular_emission_cost"],
        "Social":        ["ruc_demolition"],
    }),
]


def _stage_totals(results: dict, result_key: str, cat_keys: dict) -> dict:
    """Return {category: total_M_INR} for one stage."""
    stage_data = results.get(result_key, {})
    # Skip if the stage has no numeric data (e.g. reconstruction not applicable)
    if not isinstance(stage_data.get("economic", None), dict):
        return {}
    totals = {}
    for cat, keys in cat_keys.items():
        cat_key = cat.lower()
        cat_data = stage_data.get(cat_key, {})
        total = 0.0
        for k in keys:
            if k.startswith("-"):
                total -= M(cat_data.get(k[1:], 0.0))
            else:
                total += M(cat_data.get(k, 0.0))
        totals[cat] = total
    return totals


class LCCDetailsTable(QWidget):
    """Stage × category summary of LCC costs."""

    def __init__(self, results: dict, parent=None):
        super().__init__(parent)
        self._build(results)

    def _build(self, results: dict):
        # Compute per-stage totals
        stage_rows = []
        for stage_label, result_key, cat_keys in _STAGE_DEFS:
            totals = _stage_totals(results, result_key, cat_keys)
            if not totals:
                continue  # stage not applicable
            eco  = totals.get("Economic",      0.0)
            env  = totals.get("Environmental", 0.0)
            soc  = totals.get("Social",        0.0)
            stage_rows.append((stage_label, eco, env, soc, eco + env + soc))

        n_rows = len(stage_rows) + 1  # +1 grand total

        table = QTableWidget(n_rows, 5, self)
        table.setHorizontalHeaderLabels([
            "Stage", "Economic\n(M INR)", "Environmental\n(M INR)",
            "Social\n(M INR)", "Stage Total\n(M INR)",
        ])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in range(1, 5):
            table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        bold = QFont()
        bold.setBold(True)

        def _item(text, align=Qt.AlignLeft | Qt.AlignVCenter, font=None, green=False):
            it = QTableWidgetItem(text)
            it.setTextAlignment(align)
            if font:
                it.setFont(font)
            if green:
                it.setForeground(QColor("#2e7d32"))
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            return it

        def _val(v, bold_font=None):
            text = f"{v:.4f}"
            return _item(text, Qt.AlignRight | Qt.AlignVCenter, bold_font, green=(v < 0))

        grand_eco = grand_env = grand_soc = grand_total = 0.0

        for row_idx, (label, eco, env, soc, total) in enumerate(stage_rows):
            grand_eco   += eco
            grand_env   += env
            grand_soc   += soc
            grand_total += total
            table.setItem(row_idx, 0, _item(label))
            table.setItem(row_idx, 1, _val(eco))
            table.setItem(row_idx, 2, _val(env))
            table.setItem(row_idx, 3, _val(soc))
            table.setItem(row_idx, 4, _val(total))

        # Grand total row
        tr = len(stage_rows)
        table.setItem(tr, 0, _item("Grand Total", font=bold))
        for col, val in enumerate([grand_eco, grand_env, grand_soc, grand_total], start=1):
            table.setItem(tr, col, _val(val, bold_font=bold))

        table.resizeRowsToContents()
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

_CATEGORY_COLORS = {
    "economic":     "#DBEAFE",   # soft blue
    "environmental":"#DCFCE7",   # soft green
    "social":       "#FEF3C7",   # soft amber
}

_BREAKDOWN_STAGES = [
    {
        "label": "Initial Stage\nCosts",
        "stage_color": "#F9C74F",
        "result_key": "initial_stage",
        "optional": False,
        "rows": [
            ("economic",     "initial_construction_cost",
             "Initial construction costs"),
            ("environmental","initial_material_carbon_emission_cost",
             "Initial carbon emissions (material)"),
            ("environmental","initial_vehicular_emission_cost",
             "Carbon emissions due to rerouting during initial construction (vehicles)"),
            ("economic",     "time_cost_of_loan",
             "Time costs"),
            ("social",       "initial_road_user_cost",
             "Road user costs during initial construction"),
        ],
    },
    {
        "label": "Use Stage\nCosts",
        "stage_color": "#82E0AA",
        "result_key": "use_stage",
        "optional": False,
        "rows": [
            ("economic",     "routine_inspection_costs",
             "Routine inspection costs"),
            ("economic",     "periodic_maintenance",
             "Periodic maintenance costs"),
            ("environmental","periodic_carbon_costs",
             "Periodic maintenance carbon emissions (material)"),
            ("economic",     "major_inspection_costs",
             "Major inspection costs"),
            ("economic",     "major_repair_cost",
             "Major repair costs"),
            ("environmental","major_repair_material_carbon_emission_costs",
             "Major repair related carbon emissions (materials)"),
            ("environmental","major_repair_vehicular_emission_costs",
             "Carbon emissions due to rerouting during major repairs (vehicles)"),
            ("social",       "major_repair_road_user_costs",
             "Road user costs during major repairs"),
            ("economic",     "replacement_costs_for_bearing_and_expansion_joint",
             "Replacement cost of bearing and expansion joint"),
            ("social",       "road_user_costs_for_replacement_of_bearing_and_expansion_joint",
             "Road user costs during replacement"),
            ("environmental","vehicular_emission_costs_for_replacement_of_bearing_and_expansion_joint",
             "Carbon emissions due to rerouting during replacement (vehicles)"),
        ],
    },
    {
        "label": "Reconstruction\nStage",
        "stage_color": "#F5B041",
        "result_key": "reconstruction",
        "optional": True,
        "rows": [
            ("economic",     "cost_of_reconstruction_after_demolition",
             "Cost of reconstruction after demolition"),
            ("environmental","carbon_cost_of_reconstruction_after_demolition",
             "Carbon cost of reconstruction after demolition"),
            ("economic",     "time_cost_of_loan",
             "Time costs"),
            ("economic",     "total_demolition_and_disposal_costs",
             "Demolition and disposal costs"),
            ("environmental","carbon_costs_demolition_and_disposal",
             "Carbon emissions from demolition and disposal (materials)"),
            ("environmental","demolition_vehicular_emission_cost",
             "Carbon emissions due to rerouting during demolition (vehicles)"),
            ("environmental","reconstruction_vehicular_emission_cost",
             "Carbon emissions due to rerouting during reconstruction (vehicles)"),
            ("social",       "ruc_demolition",
             "Road user costs during demolition"),
            ("social",       "ruc_reconstruction",
             "Road user costs during reconstruction"),
        ],
    },
    {
        "label": "End-of-Life\nStage",
        "stage_color": "#E59866",
        "result_key": "end_of_life",
        "optional": False,
        "rows": [
            ("economic",     "total_demolition_and_disposal_costs",
             "Demolition and disposal costs of existing bridge"),
            ("environmental","carbon_costs_demolition_and_disposal",
             "Demolition and disposal related carbon emissions (materials) of existing bridge"),
            ("environmental","demolition_vehicular_emission_cost",
             "Carbon emissions due to rerouting during demolition (vehicles)"),
            ("social",       "ruc_demolition",
             "Road user costs during demolition and disposal of existing bridge"),
        ],
    },
]


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


class LCCBreakdownTable(QWidget):
    """Detailed row-by-row LCC cost breakdown with stage-coloured groups."""

    def __init__(self, results: dict, parent=None):
        super().__init__(parent)
        self._build(results)

    def _build(self, results: dict):
        # Collect applicable stages — keep cat for row colouring
        active_stages = []
        for stage_def in _BREAKDOWN_STAGES:
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
        table.setHorizontalHeaderLabels(["", "Costs", "Cost in Present Time"])
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
        table.setItemDelegateForColumn(0, _VerticalTextDelegate(table))

        bold = QFont()
        bold.setBold(True)

        def _cell(text, bg: QColor, align=Qt.AlignCenter | Qt.AlignVCenter, font=None):
            it = QTableWidgetItem(text)
            it.setTextAlignment(align)
            it.setBackground(bg)
            if font:
                it.setFont(font)
            it.setFlags(Qt.ItemIsEnabled)
            return it

        row_idx = 0
        for stage_def, stage_rows in active_stages:
            stage_bg = QColor(stage_def["stage_color"])
            n        = len(stage_rows)

            # Stage label cell — spans all rows in this stage
            table.setItem(row_idx, 0, _cell(stage_def["label"], stage_bg, font=bold))
            if n > 1:
                table.setSpan(row_idx, 0, n, 1)

            for i, (desc, val, cat) in enumerate(stage_rows):
                r      = row_idx + i
                row_bg = QColor(_CATEGORY_COLORS.get(cat, "#FFFFFF"))
                table.setItem(r, 1, _cell(desc, row_bg, align=Qt.AlignLeft | Qt.AlignVCenter))
                cost_item = _cell(
                    f"INR \u20b9{val:,.2f}", row_bg,
                    align=Qt.AlignRight | Qt.AlignVCenter,
                )
                if val < 0:
                    cost_item.setForeground(QColor("#2e7d32"))
                table.setItem(r, 2, cost_item)

            row_idx += n

        table.resizeRowsToContents()
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

    def __init__(self, results: dict, parent=None):
        super().__init__(parent)

        palette = QApplication.instance().palette()
        text_color = palette.windowText().color().name()
        bg_color   = palette.window().color().name()

        self._values, self._labels, stage_info = _build_chart_data(results)
        fig, self._bars = _create_figure(
            self._values, self._labels, stage_info, text_color, bg_color
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
                    f"₹ {sign}{abs(inr):,.0f}\n"
                    f"({sign}{abs(val):.4f} M INR)"
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
    values, labels, stage_info = _build_chart_data(results)
    fig, _ = _create_figure(values, labels, stage_info, text_color, bg_color)
    return fig


