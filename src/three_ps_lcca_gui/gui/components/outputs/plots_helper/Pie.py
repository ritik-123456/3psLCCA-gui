"""
gui/components/outputs/plots_helper/Pie.py

Two-tab pie widget:
  Tab 0 – Simple pillar donut  (Eco / Env / Social, lifetime totals)
  Tab 1 – Nested stage+pillar donut (existing Sustainability Matrix)
"""

import os
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from matplotlib import font_manager as _fm

matplotlib.use("QtAgg")

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
except ImportError:
    from matplotlib.backends.backend_qt import FigureCanvasQTAgg

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QLabel,
    QSizePolicy,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QFrame,
    QScrollArea,
)

from three_ps_lcca_gui.gui.theme import (
    FONT_FAMILY,
    FS_XS, FS_SM, FS_BASE, FS_LG, FS_SUBHEAD, FS_XL, FS_MD,
    FW_NORMAL, FW_BOLD,
    SP1, SP2, SP3, SP4, SP5, SP6, RADIUS_LG, RADIUS_XL,
)
from three_ps_lcca_gui.gui.themes import get_token
from three_ps_lcca_gui.gui.styles import font as _f
from three_ps_lcca_gui.gui.components.utils.display_format import fmt_currency
from ..helper_functions.lifecycle_summary import compute_all_summaries
from ..helper_functions.lcc_colors import COLORS as LCC_COLORS

# ── Register Ubuntu fonts ────────────────────────────────────────────────────
_UBUNTU_FONT_DIR = os.path.join("gui", "assets", "themes", "Ubuntu_font")
for _ttf in ["Ubuntu-Light.ttf", "Ubuntu-Regular.ttf", "Ubuntu-Medium.ttf", "Ubuntu-Bold.ttf"]:
    _path = os.path.join(_UBUNTU_FONT_DIR, _ttf)
    if os.path.exists(_path):
        _fm.fontManager.addfont(_path)

matplotlib.rcParams["font.family"] = FONT_FAMILY

# ─────────────────────────────────────────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────────────────────────────────────────

COLORS = {
    "stages": {
        "Initial":     "#CCCCCC",
        "Use":         "#00C49A",
        "End-of-Life": "#EA9E9E",
    },
    "pillars": {
        "Economic":      "#9e9eff",
        "Environmental": "#8ad400",
        "Social":        "#ff5a2a",
    },
}

_WEDGE      = {"width": 0.30, "edgecolor": "none", "linewidth": 0}
_WEDGE_SIMP = {"width": 0.42, "edgecolor": "none", "linewidth": 0}

# Per-tab static metadata
_TAB_META = [
    {
        "title": "Pillar Distribution",
        "desc": (
            "Lifetime cost breakdown across the three sustainability pillars — "
            "Economic, Environmental, and Social — aggregated over all lifecycle stages."
        ),
    },
    {
        "title": "Sustainability Matrix",
        "desc": (
            "The inner ring maps total cost per lifecycle stage. "
            "The outer ring dissects each stage into its Economic, "
            "Environmental, and Social pillars."
        ),
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# WHEEL FORWARDER
# ─────────────────────────────────────────────────────────────────────────────

class WheelForwarder(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            parent = obj.parent()
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    QApplication.sendEvent(parent.verticalScrollBar(), event)
                    return True
                parent = parent.parent()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# DATA HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _M(x): return float(x) / 1_000_000


def _build_pillar_data(results: dict):
    """(label, value_M, color) triples from pillar_totals — skips zeros."""
    pt = compute_all_summaries(results).get("pillar_totals", {})
    rows = [
        ("Economic",      pt.get("eco",    0), COLORS["pillars"]["Economic"]),
        ("Environmental", pt.get("env",    0), COLORS["pillars"]["Environmental"]),
        ("Social",        pt.get("social", 0), COLORS["pillars"]["Social"]),
    ]
    return [(l, _M(v), c) for l, v, c in rows if v > 0]


def _build_nested_pie_data(results: dict) -> list:
    pw = compute_all_summaries(results).get("pillar_wise", {})
    mapping = [
        ("initial",            "Initial"),
        ("use_reconstruction", "Use"),
        ("end_of_life",        "End-of-Life"),
    ]
    data = []
    for key, label in mapping:
        p = pw.get(key, {})
        if not p or sum(p.values()) <= 0:
            continue
        data.append({
            "stage": label,
            "pillars": [
                ("Economic",      _M(p.get("eco",    0)), COLORS["pillars"]["Economic"]),
                ("Environmental", _M(p.get("env",    0)), COLORS["pillars"]["Environmental"]),
                ("Social",        _M(p.get("social", 0)), COLORS["pillars"]["Social"]),
            ],
        })
    return data


# ─────────────────────────────────────────────────────────────────────────────
# CHART 0 – Simple pillar donut
# ─────────────────────────────────────────────────────────────────────────────

class SimplePillarPlotter:
    def __init__(self, results: dict, currency: str = "INR"):
        items          = _build_pillar_data(results)
        self.labels    = [i[0] for i in items]
        self.values    = [i[1] for i in items]
        self.colors    = [i[2] for i in items]
        self.total     = sum(self.values)
        self.currency  = currency
        self.mode      = "Value"

        self.fig = plt.figure(figsize=(7, 6))
        self.fig.patch.set_alpha(0.0)
        self.ax  = self.fig.add_subplot(111)
        self.ax.set_facecolor("none")
        self.fig.subplots_adjust(left=0.02, right=0.98, bottom=0.15, top=0.95)
        self.fig.canvas.mpl_connect("motion_notify_event", self._hover)

    def _fmt(self, val: float) -> str:
        if self.mode == "Percentage":
            return f"{val / (self.total or 1.0) * 100:.1f}%"
        return f"{fmt_currency(val, self.currency, decimals=2)} Million {self.currency}"

    def _hover(self, event):
        if event.inaxes != self.ax or not hasattr(self, "annot"):
            return
        found = False
        for i, wedge in enumerate(self.wedges):
            if wedge.contains(event)[0]:
                self.annot.set_text(f"{self.labels[i]}\n{self._fmt(self.values[i])}")
                self.annot.xy = (event.xdata, event.ydata)
                self.annot.set_visible(True)
                found = True
                break
        if not found:
            self.annot.set_visible(False)
        self.fig.canvas.draw_idle()

    def set_mode(self, is_percentage: bool):
        self.mode = "Percentage" if is_percentage else "Value"
        if hasattr(self, "center_text"):
            self.center_text.set_text(f"TOTAL\n{self._fmt(self.total)}")
        self.fig.canvas.draw_idle()

    def setup_plot(self):
        tc = get_token("text")
        self.ax.set(aspect="equal")

        if not self.values:
            self.ax.text(0, 0, "No Data", ha="center", va="center", color=tc)
            self.ax.axis("off")
            return self.fig

        self.wedges, _ = self.ax.pie(
            self.values, radius=1.05, colors=self.colors, wedgeprops=_WEDGE_SIMP,
        )
        self.center_text = self.ax.text(
            0, 0, f"TOTAL\n{self._fmt(self.total)}",
            ha="center", va="center", fontsize=10, fontweight="bold", color=tc,
        )
        self.annot = self.ax.annotate(
            "", xy=(0, 0), xytext=(20, 20), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=get_token("base"),
                      ec=get_token("surface_mid"), alpha=0.9),
            zorder=10, fontweight="bold", color=tc,
        )
        self.annot.set_visible(False)

        legend_els = [Patch(facecolor=c, label=l) for l, c in zip(self.labels, self.colors)]
        self.ax.legend(
            handles=legend_els, loc="upper center", bbox_to_anchor=(0.5, -0.08),
            ncol=3, frameon=False, fontsize=8, labelcolor=tc,
        )
        self.ax.axis("off")
        return self.fig


# ─────────────────────────────────────────────────────────────────────────────
# CHART 1 – Nested stage+pillar donut  (existing Sustainability Matrix)
# ─────────────────────────────────────────────────────────────────────────────

class SustainabilityCircularPlotter:
    def __init__(self, data: list, currency: str = "INR"):
        self.data     = data
        self.currency = currency
        self.mode     = "Value"
        self.fig = plt.figure(figsize=(7, 6))
        self.fig.patch.set_alpha(0.0)
        self.ax  = self.fig.add_subplot(111)
        self.ax.set_facecolor("none")
        self.fig.subplots_adjust(left=0.02, right=0.98, bottom=0.15, top=0.95)
        self._prepare_data()
        self.fig.canvas.mpl_connect("motion_notify_event", self._hover)

    def _prepare_data(self):
        self.total_value = sum(sum(p[1] for p in e["pillars"]) for e in self.data)
        self.inner_vals, self.inner_colors, self.inner_labels = [], [], []
        self.outer_vals, self.outer_colors, self.outer_labels = [], [], []
        for entry in self.data:
            stage_total = sum(p[1] for p in entry["pillars"])
            self.inner_vals.append(stage_total)
            self.inner_labels.append(entry["stage"])
            self.inner_colors.append(COLORS["stages"].get(entry["stage"], "#DDDDDD"))
            for name, val, color in entry["pillars"]:
                self.outer_vals.append(val)
                self.outer_labels.append(f"{entry['stage']} - {name}")
                self.outer_colors.append(color)

    def _fmt(self, val: float) -> str:
        if self.mode == "Percentage":
            total = self.total_value if self.total_value > 0 else 1.0
            return f"{val / total * 100:.1f}%"
        return f"{fmt_currency(val, self.currency, decimals=2)} Million {self.currency}"

    def _hover(self, event):
        if event.inaxes != self.ax or not hasattr(self, "annot"):
            return
        found = False
        all_wedges = list(self.outer_wedges) + list(self.inner_wedges)
        all_labels = self.outer_labels + [f"Stage: {l}" for l in self.inner_labels]
        all_vals   = self.outer_vals   + self.inner_vals
        for i, wedge in enumerate(all_wedges):
            if wedge.contains(event)[0]:
                self.annot.set_text(f"{all_labels[i]}\n{self._fmt(all_vals[i])}")
                self.annot.xy = (event.xdata, event.ydata)
                self.annot.set_visible(True)
                found = True
                break
        if not found:
            self.annot.set_visible(False)
        self.fig.canvas.draw_idle()

    def set_mode(self, is_percentage: bool):
        self.mode = "Percentage" if is_percentage else "Value"
        self.center_text.set_text(f"TOTAL\n{self._fmt(self.total_value)}")
        self.fig.canvas.draw_idle()

    def setup_plot(self):
        tc  = get_token("text")
        sep = get_token("surface_mid")
        self.ax.set(aspect="equal")
        self.inner_wedges, _ = self.ax.pie(
            self.inner_vals, radius=0.8, colors=self.inner_colors, wedgeprops=_WEDGE,
        )
        self.outer_wedges, _ = self.ax.pie(
            self.outer_vals, radius=1.1, colors=self.outer_colors, wedgeprops=_WEDGE,
        )
        if self.total_value > 0:
            angles = np.cumsum(self.inner_vals) / self.total_value * 2 * np.pi
            for angle in angles:
                x = [0.5 * np.cos(angle), 1.1 * np.cos(angle)]
                y = [0.5 * np.sin(angle), 1.1 * np.sin(angle)]
                self.ax.plot(x, y, color=sep, lw=1.5, alpha=0.5)
        self.center_text = self.ax.text(
            0, 0, f"TOTAL\n{self._fmt(self.total_value)}",
            ha="center", va="center", fontsize=10, fontweight="bold", color=tc,
        )
        self.annot = self.ax.annotate(
            "", xy=(0, 0), xytext=(20, 20), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=get_token("base"),
                      ec=get_token("surface_mid"), alpha=0.9),
            zorder=10, fontweight="bold", color=tc,
        )
        self.annot.set_visible(False)
        legend_els  = [Patch(facecolor=COLORS["stages"].get(l, "#AAA"), label=l)
                       for l in self.inner_labels]
        legend_els += [Patch(facecolor=c, label=l) for l, c in COLORS["pillars"].items()]
        self.ax.legend(
            handles=legend_els, loc="upper center", bbox_to_anchor=(0.5, -0.08),
            ncol=3, frameon=False, fontsize=8, labelcolor=tc,
        )
        self.ax.axis("off")
        return self.fig


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET
# ─────────────────────────────────────────────────────────────────────────────

class LCCPieWidget(QWidget):
    def __init__(self, results: dict, currency: str = "INR", parent=None):
        super().__init__(parent)
        self._results  = results
        self._currency = currency
        self._setup_ui()

    # ── build ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self._main_v = QVBoxLayout(self)
        self._main_v.setContentsMargins(0, SP4, 0, SP4)

        self.card = QFrame()
        self.card.setObjectName("pieCard")
        self.card.setStyleSheet(
            f"#pieCard {{"
            f"  background-color: transparent;"
            f"  border: 1.5px solid {get_token('surface_mid')};"
            f"  border-radius: {RADIUS_XL}px;"
            f"}}"
        )
        self.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        card_v = QVBoxLayout(self.card)
        card_v.setContentsMargins(SP6, SP5, SP6, SP6)
        card_v.setSpacing(SP4)

        # ── content row ──────────────────────────────────────────────────────
        content_row = QWidget()
        content_row.setStyleSheet("background: transparent; border: none;")
        self._content_h = QHBoxLayout(content_row)
        self._content_h.setContentsMargins(0, 0, 0, 0)
        self._content_h.setSpacing(SP6)

        # Left panel
        self._left_panel = QWidget()
        self._left_panel.setStyleSheet("background: transparent; border: none;")
        left_v = QVBoxLayout(self._left_panel)
        left_v.setContentsMargins(0, 0, 0, 0)
        left_v.setSpacing(SP4)
        left_v.setAlignment(Qt.AlignCenter)

        title_lbl = QLabel(_TAB_META[1]["title"])
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setWordWrap(True)
        title_lbl.setFont(_f(FS_SUBHEAD, FW_BOLD))
        title_lbl.setStyleSheet(f"color: {get_token('text')}; border: none; letter-spacing: 0.5px;")
        left_v.addWidget(title_lbl)

        desc_lbl = QLabel(_TAB_META[1]["desc"])
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setFont(_f(FS_BASE))
        desc_lbl.setStyleSheet(f"color: {get_token('text_secondary')}; border: none;")
        left_v.addWidget(desc_lbl)

        # Eco : Env : Social ratio box
        summary = compute_all_summaries(self._results)
        pt      = summary.get("pillar_totals", {})
        total_p = sum(pt.values())
        
        c_eco = get_token("eco")
        c_env = get_token("env")
        c_soc = get_token("soc")

        if total_p > 0:
            r_eco = pt.get("eco",    0) / total_p
            r_env = pt.get("env",    0) / total_p
            r_soc = pt.get("social", 0) / total_p
            _min  = min(v for v in (r_eco, r_env, r_soc) if v > 0) or 1.0
            n_eco, n_env, n_soc = r_eco / _min, r_env / _min, r_soc / _min
            
            ratio = (
                f"<b style='color:{c_eco}'>{n_eco:.1f}</b> <span style='color:{get_token('text')}'>:</span> "
                f"<b style='color:{c_env}'>{n_env:.1f}</b> <span style='color:{get_token('text')}'>:</span> "
                f"<b style='color:{c_soc}'>{n_soc:.1f}</b>"
            )
        else:
            ratio = f"<span style='color:{get_token('text')}'>0.0 : 0.0 : 0.0</span>"

        ratio_box = QFrame()
        ratio_box.setStyleSheet(
            f"background: transparent;"
            f"border: 1px solid {get_token('surface_mid')};"
            f"border-radius: {RADIUS_LG}px;"
        )
        ratio_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        rb_v = QVBoxLayout(ratio_box)
        rb_v.setContentsMargins(SP4, SP4, SP4, SP4)
        rb_v.setSpacing(SP2)

        rb_label = QLabel(
            f"<span style='color:{c_eco}'>ECONOMIC</span> <span style='color:{get_token('text')}'>:</span> "
            f"<span style='color:{c_env}'>ENVIRONMENTAL</span> <span style='color:{get_token('text')}'>:</span> "
            f"<span style='color:{c_soc}'>SOCIAL</span>"
        )
        rb_label.setAlignment(Qt.AlignCenter)
        rb_label.setWordWrap(True)
        rb_label.setTextFormat(Qt.RichText)
        rb_label.setFont(_f(FS_SM, FW_BOLD))
        rb_label.setStyleSheet(
            f"color: {get_token('text')}; letter-spacing: 1.2px; border: none;"
        )
        rb_v.addWidget(rb_label)

        rb_val = QLabel(ratio)
        rb_val.setAlignment(Qt.AlignCenter)
        rb_val.setWordWrap(True)
        rb_val.setTextFormat(Qt.RichText)
        rb_val.setFont(QFont("Consolas", FS_LG))
        rb_val.setStyleSheet(f"color: {get_token('text')}; border: none;")
        rb_v.addWidget(rb_val)

        rb_note = QLabel("(expressed as ratio)")
        rb_note.setAlignment(Qt.AlignCenter)
        rb_note.setFont(_f(FS_XS, FW_NORMAL, italic=True))
        rb_note.setStyleSheet(f"color: {get_token('text')}; border: none;")
        rb_v.addWidget(rb_note)
        left_v.addWidget(ratio_box)

        # Percentage mode toggle
        self._mode_cb = QCheckBox("Show Percentage Mode")
        self._mode_cb.setFont(_f(FS_BASE))
        self._mode_cb.setStyleSheet(
            f"color: {get_token('text_secondary')}; background: transparent; border: none;"
        )
        left_v.addWidget(self._mode_cb, 0, Qt.AlignCenter)

        # Stage-wise view toggle
        self._stage_cb = QCheckBox("See stage wise")
        self._stage_cb.setFont(_f(FS_BASE))
        self._stage_cb.setStyleSheet(
            f"color: {get_token('text_secondary')}; background: transparent; border: none;"
        )
        left_v.addWidget(self._stage_cb, 0, Qt.AlignCenter)

        self._content_h.addWidget(self._left_panel, 1)

        # Chart stack
        self._chart_stack = QStackedWidget()
        self._chart_stack.setMaximumHeight(500)
        self._chart_stack.setStyleSheet("background: transparent; border: none;")

        scroller      = WheelForwarder(self)
        self._plotters = []

        # ── Chart 0: simple pillar donut ─────────────────────────
        p0   = SimplePillarPlotter(self._results, currency=self._currency)
        fig0 = p0.setup_plot()
        c0   = FigureCanvasQTAgg(fig0)
        c0.setMinimumHeight(400)
        c0.setMaximumHeight(500)
        c0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        c0.setStyleSheet("background: transparent; border: none;")
        c0.installEventFilter(scroller)
        self._chart_stack.addWidget(c0)
        self._plotters.append(p0)

        # ── Chart 1: nested stage+pillar donut ───────────────────
        data1 = _build_nested_pie_data(self._results)
        if data1:
            p1   = SustainabilityCircularPlotter(data1, currency=self._currency)
            fig1 = p1.setup_plot()
            c1   = FigureCanvasQTAgg(fig1)
            c1.setMinimumHeight(400)
            c1.setMaximumHeight(500)
            c1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            c1.setStyleSheet("background: transparent; border: none;")
            c1.installEventFilter(scroller)
            self._chart_stack.addWidget(c1)
            self._plotters.append(p1)
        else:
            no_data = QLabel("No data available.")
            no_data.setAlignment(Qt.AlignCenter)
            self._chart_stack.addWidget(no_data)
            self._plotters.append(None)

        self._mode_cb.toggled.connect(self._on_mode_change)
        self._stage_cb.toggled.connect(self._on_stage_toggle)

        self._content_h.addWidget(self._chart_stack, 2)
        card_v.addWidget(content_row)
        self._main_v.addWidget(self.card)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_mode_change(self, is_percentage: bool):
        for p in self._plotters:
            if p is not None:
                p.set_mode(is_percentage)

    def _on_stage_toggle(self, checked: bool):
        self._chart_stack.setCurrentIndex(1 if checked else 0)

    # ── responsive layout ─────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        is_narrow = event.size().width() < 850
        if is_narrow:
            self._content_h.setDirection(QBoxLayout.Direction.TopToBottom)
            self._left_panel.setMinimumWidth(0)
            self._left_panel.setMaximumWidth(16777215)
        else:
            self._content_h.setDirection(QBoxLayout.Direction.LeftToRight)
            self._left_panel.setFixedWidth(350)

    def minimumSizeHint(self):
        return QSize(0, 400)
