"""
gui/components/outputs/plots_helper/Pie.py

Interactive nested pie chart - LCC cost distribution by stage (inner ring)
and pillar (outer ring).  Embeds as a Qt widget via LCCPieWidget(results).
"""

import os
import matplotlib

matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Wedge
from matplotlib.widgets import Button, CheckButtons, RadioButtons
from matplotlib import font_manager as _fm

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
except ImportError:
    from matplotlib.backends.backend_qt import FigureCanvasQTAgg

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# change - import FS_* tokens from theme.py for consistent font sizes
from gui.theme import (
    FONT_FAMILY,
    FS_SM, FS_BASE, FS_LG, FS_XL,
)

# change - register Ubuntu .ttf files with matplotlib so it finds the font
_UBUNTU_FONT_DIR = os.path.join("gui", "assets", "themes", "Ubuntu_font")
for _ttf in [
    "Ubuntu-Light.ttf", "Ubuntu-LightItalic.ttf",
    "Ubuntu-Regular.ttf", "Ubuntu-Italic.ttf",
    "Ubuntu-Medium.ttf", "Ubuntu-MediumItalic.ttf",
    "Ubuntu-Bold.ttf",   "Ubuntu-BoldItalic.ttf",
]:
    _path = os.path.join(_UBUNTU_FONT_DIR, _ttf)
    if os.path.exists(_path):
        _fm.fontManager.addfont(_path)

# change - set Ubuntu as default matplotlib font family for all pie chart text
matplotlib.rcParams["font.family"] = FONT_FAMILY




# ── Constants ─────────────────────────────────────────────────────────────────

# ── Centralized Color System ─────────────────────────────────────
# changes made here for cetralized color management across the app.
COLORS = {
    "stages": {
        "Initial":        "#CCCCCC",  # light grey
        "Use":            "#00C49A",  # teal green
        "Reconstruction": "#F5B041",  # orange
        "End-of-Life":    "#EA9E9E",  # soft pink
    },
    "pillars": {
        "Economic":      "#9e9eff",   # periwinkle blue
        "Environmental": "#89E88B",   # pastel green
        "Social":        "#FF9800",   # amber orange
    },
    # change - stage_cost_tints: mirrors stages colors (same palette, used for cost-in-time col)
    "stage_cost_tints": {
        "Initial":        "#CCCCCC",   # light grey - same as stages
        "Use":            "#00C49A",   # teal green - same as stages
        "Reconstruction": "#F5B041",   # orange - same as stages
        "End-of-Life":    "#EA9E9E",   # soft pink - same as stages
    },
    # change - summary_neutral: colors for Stage col, Stage Total col, and Grand Total row
    "summary_neutral": {
        "stage_col":        "#BDC3C7",   # silver grey
        "total_col":        "#F0B27A",   # warm orange
        "grand_total_cells":"#AED6F1",   # calm blue
    },
    "ui": {
        "view": "#DBEAFE",
        "background": "#2b2d42",
        "text": "#222",
    }
}

_NEG_COLOR = "#333333"  # negative offset overlay color
_PILLARS = list(COLORS["pillars"].keys())


# ── Accessors for centralized color system ───────────────────────

def get_pillars():
    return list(COLORS["pillars"].keys())

def get_pillar_color(p):
    return COLORS["pillars"].get(p, "#CCCCCC")

def get_stages():
    return list(COLORS["stages"].keys())

def get_stage_color(s):
    return COLORS["stages"].get(s, "#AAAAAA")




# ── Helpers ───────────────────────────────────────────────────────────────────


def _pv(pos, neg=0.0):
    return {"positive": float(pos), "negative": abs(float(neg))}


def _M(x):
    """Raw Currency → Million Units."""
    return float(x) / 1_000_000


def _sum_M(stage_data: dict, cat: str, keys: list) -> float:
    d = stage_data.get(cat, {})
    return _M(sum(float(d.get(k, 0.0)) for k in keys))


# ── Data extraction ───────────────────────────────────────────────────────────


def _build_pie_data(results: dict) -> dict:
    """
    Build {stage_label: {pillar: {"positive": float, "negative": float}}}
    in M units from a run_full_lcc_analysis results dict.
    """
    data = {}

    # Initial Stage
    s = results.get("initial_stage", {})
    if isinstance(s.get("economic"), dict):
        data["Initial"] = {
            "Economic": _pv(
                _sum_M(
                    s, "economic", ["initial_construction_cost", "time_cost_of_loan"]
                ),
            ),
            "Environmental": _pv(
                _sum_M(
                    s,
                    "environmental",
                    [
                        "initial_material_carbon_emission_cost",
                        "initial_vehicular_emission_cost",
                    ],
                ),
            ),
            "Social": _pv(
                _sum_M(s, "social", ["initial_road_user_cost"]),
            ),
        }

    # Use Stage
    s = results.get("use_stage", {})
    if isinstance(s.get("economic"), dict):
        data["Use"] = {
            "Economic": _pv(
                _sum_M(
                    s,
                    "economic",
                    [
                        "routine_inspection_costs",
                        "periodic_maintenance",
                        "major_inspection_costs",
                        "major_repair_cost",
                        "replacement_costs_for_bearing_and_expansion_joint",
                    ],
                ),
            ),
            "Environmental": _pv(
                _sum_M(
                    s,
                    "environmental",
                    [
                        "periodic_carbon_costs",
                        "major_repair_material_carbon_emission_costs",
                        "major_repair_vehicular_emission_costs",
                        "vehicular_emission_costs_for_replacement_of_bearing_and_expansion_joint",
                    ],
                ),
            ),
            "Social": _pv(
                _sum_M(
                    s,
                    "social",
                    [
                        "major_repair_road_user_costs",
                        "road_user_costs_for_replacement_of_bearing_and_expansion_joint",
                    ],
                ),
            ),
        }

    # Reconstruction (optional)
    s = results.get("reconstruction", {})
    if isinstance(s.get("economic"), dict):
        data["Reconstruction"] = {
            "Economic": _pv(
                _sum_M(
                    s,
                    "economic",
                    [
                        "cost_of_reconstruction_after_demolition",
                        "time_cost_of_loan",
                        "total_demolition_and_disposal_costs",
                    ],
                ),
                _M(s.get("economic", {}).get("total_scrap_value", 0.0)),
            ),
            "Environmental": _pv(
                _sum_M(
                    s,
                    "environmental",
                    [
                        "carbon_cost_of_reconstruction_after_demolition",
                        "carbon_costs_demolition_and_disposal",
                        "demolition_vehicular_emission_cost",
                        "reconstruction_vehicular_emission_cost",
                    ],
                ),
            ),
            "Social": _pv(
                _sum_M(s, "social", ["ruc_demolition", "ruc_reconstruction"]),
            ),
        }

    # End-of-Life
    s = results.get("end_of_life", {})
    if isinstance(s.get("economic"), dict):
        data["End-of-Life"] = {
            "Economic": _pv(
                _sum_M(s, "economic", ["total_demolition_and_disposal_costs"]),
                _M(s.get("economic", {}).get("total_scrap_value", 0.0)),
            ),
            "Environmental": _pv(
                _sum_M(
                    s,
                    "environmental",
                    [
                        "carbon_costs_demolition_and_disposal",
                        "demolition_vehicular_emission_cost",
                    ],
                ),
            ),
            "Social": _pv(
                _sum_M(s, "social", ["ruc_demolition"]),
            ),
        }

    return data


# ── Figure builder ────────────────────────────────────────────────────────────


def _label_center(ax, wedge, value, r):
    ang = np.deg2rad((wedge.theta1 + wedge.theta2) / 2)
    ax.text(
        r * np.cos(ang),
        r * np.sin(ang),
        f"{value:.2f}",
        ha="center",
        va="center",
        fontsize=FS_SM,     # change - use FS_SM token instead of hardcoded 8
        fontweight="bold",
    )


def _label_arrow(ax, theta1, theta2, text):
    ang = np.deg2rad((theta1 + theta2) / 2)
    ax.annotate(
        text,
        xy=(0.92 * np.cos(ang), 0.92 * np.sin(ang)),
        xytext=(1.28 * np.cos(ang), 1.28 * np.sin(ang)),
        arrowprops=dict(arrowstyle="-", lw=0.8),
        fontsize=FS_SM,     # change - use FS_SM token instead of hardcoded 8
        ha="center",
        va="center",
    )


def _build_pie_figure(data: dict, currency: str = "INR"):
    """Build and return an interactive matplotlib Figure from LCC data."""
    stages_list = list(data.keys())

    state = {
        "view": "Combined",
        "active_stages": set(stages_list),
        "active_pillars": set(get_pillars()),
        "show_negative": False,
    }

    # Shared mutable hover state - rebuilt on every _draw()
    _hover = {"annot": None, "items": []}  # items: [(wedge, title, value_M_unit)]

    # Force white background and dark text for the graph
    bg = "#FFFFFF"
    fg = "#000000"

    fig = plt.figure(figsize=(10, 8))
    fig.patch.set_facecolor(bg)
    fig.subplots_adjust(left=0.26, right=0.96, top=0.90, bottom=0.05)
    ax = fig.add_subplot(111)
    ax.set_facecolor(bg)

    def _draw():
        ax.clear()
        ax.set_facecolor(bg)
        _hover["items"].clear()

        inner_vals, inner_cols = [], []
        outer_vals, outer_cols = [], []
        active_inner = []  # (stage_label, net_value)
        active_outer = []  # (stage_label, pillar_label, net_value)
        neg_overlays = []
        total = 0.0

        for s in stages_list:
            if s not in state["active_stages"]:
                continue
            stage_net = 0.0
            for p in get_pillars():
                if p not in state["active_pillars"]:
                    continue
                d = data[s][p]
                pos, neg = d["positive"], d["negative"]
                actual_net = pos - neg
                display_val = pos if state["show_negative"] else max(actual_net, 0.0)
                stage_net += actual_net
                total += actual_net

                if state["view"] != "Only Internal" and display_val > 0:
                    outer_vals.append(display_val)
                    outer_cols.append(get_pillar_color(p))
                    active_outer.append((s, p, actual_net))
                    if state["show_negative"] and neg > 0:
                        neg_overlays.append((len(outer_vals) - 1, neg, pos))

            if stage_net != 0 and state["view"] != "Only External":
                inner_vals.append(stage_net)
                inner_cols.append(get_stage_color(s))
                active_inner.append((s, stage_net))

        if inner_vals:
            wi, _ = ax.pie(
                inner_vals,
                radius=0.65,
                colors=inner_cols,
                wedgeprops=dict(width=0.30, edgecolor="white"),
            )
            for w, (s, v) in zip(wi, active_inner):
                _label_center(ax, w, v, 0.45)
                _hover["items"].append((w, f"{s} Stage", v))

        if outer_vals:
            wo, _ = ax.pie(
                outer_vals,
                radius=1.0,
                colors=outer_cols,
                wedgeprops=dict(width=0.32, edgecolor="white"),
            )
            for w, (s, p, net), dv in zip(wo, active_outer, outer_vals):
                _label_center(ax, w, dv, 0.88)
                _hover["items"].append((w, f"{s}  ·  {p}", net))

            if state["show_negative"]:
                for idx, neg, pos in neg_overlays:
                    w = wo[idx]
                    frac = min(neg / pos, 1.0) if pos > 0 else 0
                    t2 = w.theta1 + frac * (w.theta2 - w.theta1)
                    overlay = Wedge(
                        (0, 0),
                        1.0,
                        w.theta1,
                        t2,
                        width=0.32,
                        facecolor=_NEG_COLOR,
                        hatch="///",
                        alpha=0.35,
                    )
                    ax.add_patch(overlay)
                    _label_arrow(ax, w.theta1, t2, f"−{neg:.2f}")

        ax.text(
            0,
            0,
            f"Net Total\n{total:.2f} M {currency}",
            ha="center",
            va="center",
            fontsize=FS_LG,     # change - use FS_LG token instead of hardcoded 11
            fontweight="bold",
            color=fg,
        )
        ax.set_title(f"LCC Cost Distribution (M {currency})", fontsize=FS_XL, color=fg)  # change - use FS_XL token instead of hardcoded 12
        ax.axis("off")

        # Recreate annotation - ax.clear() destroys it
        _hover["annot"] = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(18, 18),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.45", fc=bg, ec="#888888", alpha=0.95, lw=1),
            fontsize=FS_BASE,   # change - use FS_BASE token instead of hardcoded 9
            color=fg,
            zorder=10,
        )
        _hover["annot"].set_visible(False)

        fig.canvas.draw_idle()

    # ── Hover handlers ─────────────────────────────────────────────────────────

    def _on_hover(event):
        if event.inaxes != ax:
            _set_annot_visible(False)
            return
        for wedge, title, value in _hover["items"]:
            if wedge.contains(event)[0]:
                ang = np.deg2rad((wedge.theta1 + wedge.theta2) / 2)
                r = 0.55 if wedge.r <= 0.65 else 0.85  # inner vs outer ring
                _hover["annot"].xy = (r * np.cos(ang), r * np.sin(ang))
                _hover["annot"].set_text(
                    f"{title}\n{value:.4f} M {currency}\n({currency} {value * 1e6:,.0f})"
                )
                _set_annot_visible(True)
                return
        _set_annot_visible(False)

    def _on_leave(_event):
        _set_annot_visible(False)

    def _set_annot_visible(visible: bool):
        annot = _hover["annot"]
        if annot and annot.get_visible() != visible:
            annot.set_visible(visible)
            fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", _on_hover)
    fig.canvas.mpl_connect("axes_leave_event", _on_leave)

    # ── Interactive controls ───────────────────────────────────────────────────
    ax_view = fig.add_axes([0.01, 0.65, 0.21, 0.21])
    ax_stage = fig.add_axes([0.01, 0.37, 0.21, len(stages_list) * 0.06 + 0.04])
    ax_pillar = fig.add_axes([0.01, 0.13, 0.21, 0.21])
    ax_neg = fig.add_axes([0.01, 0.04, 0.21, 0.07])

    for a, title in [(ax_view, "View"), (ax_stage, "Stages"), (ax_pillar, "Pillars")]:
        a.set_facecolor(bg)
        a.set_title(title, fontsize=FS_BASE, color=fg)  # change - use FS_BASE token instead of hardcoded 9

    radio_view = RadioButtons(ax_view, ["Combined", "Only Internal", "Only External"])
    check_stage = CheckButtons(ax_stage, stages_list, [True] * len(stages_list))
    pillars = get_pillars()
    check_pillar = CheckButtons(ax_pillar, pillars, [True] * len(pillars))
    btn_neg = Button(ax_neg, "Show Negative Offset")

    ax_view.set_facecolor(COLORS["ui"]["view"])
    ax_stage.set_facecolor(COLORS["stages"]["Use"])
    ax_pillar.set_facecolor(COLORS["pillars"]["Environmental"])

    # ── Improve text visibility ────────────────────────
    for widget in [radio_view, check_stage, check_pillar]:
        for label in widget.labels:
            label.set_color("black")

    # Button text color
    btn_neg.label.set_color("black")

    # ── Optional: panel borders ────────────────────────
    for a in [ax_view, ax_stage, ax_pillar, ax_neg]:
        for spine in a.spines.values():
            spine.set_edgecolor("#444")
            spine.set_linewidth(1.2)

    def on_view(label):
        state["view"] = label
        _draw()

    def on_stage(label):
        state["active_stages"].symmetric_difference_update([label])
        _draw()

    def on_pillar(label):
        state["active_pillars"].symmetric_difference_update([label])
        _draw()

    def toggle_negative(_=None):
        state["show_negative"] = not state["show_negative"]
        btn_neg.label.set_text(
            "Hide Negative" if state["show_negative"] else "Show Negative Offset"
        )
        _draw()

    radio_view.on_clicked(on_view)
    check_stage.on_clicked(on_stage)
    check_pillar.on_clicked(on_pillar)
    btn_neg.on_clicked(toggle_negative)

    # Keep widget references alive - matplotlib won't keep them otherwise
    fig._lcca_controls = (radio_view, check_stage, check_pillar, btn_neg)

    _draw()
    return fig


# ── Qt widget ─────────────────────────────────────────────────────────────────


class _WheelForwarder(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            parent = obj.parent()
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    QApplication.sendEvent(parent.verticalScrollBar(), event)
                    return True
                parent = parent.parent()
        return False


class LCCPieWidget(QWidget):
    """Interactive nested pie chart - inner ring = stage, outer ring = pillar."""

    def __init__(self, results: dict, currency: str = "INR", parent=None):
        super().__init__(parent)
        data = _build_pie_data(results)
        if not data:
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("No data available for pie chart."))
            return

        # Check for any negative net values - pie chart cannot represent them.
        negative_items = [
            (stage, pillar, d["positive"] - d["negative"])
            for stage, pillars in data.items()
            for pillar, d in pillars.items()
            if d["positive"] - d["negative"] < 0
        ]
        if negative_items:
            for stage, pillar, net in negative_items:
                print(
                    f"[LCCPieWidget] skipping pie chart: "
                    f"stage='{stage}' pillar='{pillar}' net={net:.4f} M {currency} is negative"
                )
            layout = QVBoxLayout(self)
            layout.addWidget(
                QLabel(
                    "⚠  Pie chart unavailable: one or more cost values are negative.\n"
                    "Check console for details."
                )
            )
            return

        fig = _build_pie_figure(data, currency=currency)
        canvas = FigureCanvasQTAgg(fig)
        canvas.setMinimumHeight(520)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._forwarder = _WheelForwarder(self)
        canvas.installEventFilter(self._forwarder)

        lbl = QLabel("<b>LCC Cost Distribution</b>")
        lbl.setContentsMargins(0, 16, 0, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(lbl)
        layout.addWidget(canvas)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
