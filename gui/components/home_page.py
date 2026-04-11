"""
gui/components/home_page.py

Home screen — Word 2024-inspired two-panel layout.
Left sidebar: nav + recent/pinned list.
Right panel: greeting, CTA cards, project grid.
"""

import os
import re
import json
import shutil
import hashlib
import zipfile
from datetime import datetime

from PySide6.QtCore import Qt, QSize, QPoint, QPointF, QRect, QRectF, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QPalette, QPolygonF
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QLineEdit,
    QMessageBox,
    QInputDialog,
    QFileDialog,
    QMenu,
    QApplication,
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
    QDialog,
    QFormLayout,
    QSizePolicy,
)
from core.safechunk_engine import SafeChunkEngine
import core.start_manager as sm
from gui.theme import (
    SP2,
    SP3,
    SP4,
    SP5,
    SP6,
    SP8,
    SP10,
    RADIUS_SM,
    RADIUS_MD,
    RADIUS_LG,
    BTN_SM,
    BTN_MD,
    BTN_LG,
    FS_XS,
    FS_SM,
    FS_BASE,
    FS_MD,
    FS_LG,
    FS_XL,
    FS_DISP,
    FW_LIGHT,
    FW_NORMAL,
    FW_MEDIUM,
    FW_SEMIBOLD,
    FW_BOLD,
)
from gui.themes import get_token
from gui.styles import (
    font as _f,
    btn_primary,
    btn_ghost,
    btn_ghost_checkable,
)
from gui.components.settings_dialog import SettingsDialog


# ── Layout constants ──────────────────────────────────────────────────────────
SIDEBAR_W = 76  # fixed sidebar width
CARD_H_NORM = 78  # card height — normal projects
CARD_H_WARN = 90  # card height — crashed / corrupted (extra line)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _relative_time(dt_str: str) -> str:
    """Return a human-friendly relative date string like Word's recent list."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str[:19])
    except ValueError:
        return dt_str[:10]
    now = datetime.now()
    diff = now - dt
    secs = int(diff.total_seconds())
    if secs < 60:
        return "Just now"
    if secs < 3600:
        m = secs // 60
        return f"{m} min ago" if m > 1 else "1 min ago"
    if secs < 86400:
        h = secs // 3600
        return f"{h} hrs ago" if h > 1 else "1 hr ago"
    if secs < 172800:
        return "Yesterday"
    if secs < 604800:
        d = secs // 86400
        return f"{d} days ago"
    if secs < 2592000:
        w = secs // 604800
        return f"{w} wks ago" if w > 1 else "1 wk ago"
    # Older: show "Mon DD" or "Mon DD, YYYY" if not current year
    fmt = "%b %d" if dt.year == now.year else "%b %d, %Y"
    return dt.strftime(fmt)


from datetime import datetime


def _greeting() -> str:
    """Returns a time-based greeting string (no name)."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good Morning"
    elif 12 <= hour < 17:
        return "Good Afternoon"
    elif 17 <= hour < 21:
        return "Good Evening"
    else:
        return "Hello"


STATUS_CONFIG = {
    "ok": {"label": "OK", "color": get_token("success")},
    "crashed": {"label": "Needs recovery", "color": get_token("danger")},
    "locked": {
        "label": "Open",
        "color": get_token("info"),
    },  # blue — distinct from brand green
    "corrupted": {"label": "Corrupted", "color": get_token("warning")},
}


# ── Sidebar icon nav button ────────────────────────────────────────────────────


class _NavButton(QWidget):
    """Custom-painted sidebar nav button — icon drawn with QPainter for crisp results."""

    clicked = Signal()

    HOME = "home"
    NEW = "new"
    OPEN = "open"
    SETTINGS = "settings"

    def __init__(
        self, icon_type: str, label: str = "", selected: bool = False, parent=None
    ):
        super().__init__(parent)
        self._icon_type = icon_type
        self._label = label
        self._selected = selected
        self._hover = False
        self.setFixedHeight(60)
        self.setCursor(Qt.PointingHandCursor)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        cx = w // 2

        # Background
        if self._selected:
            bg = QColor(get_token("primary"))
            bg.setAlpha(28)
            p.fillRect(self.rect(), bg)
        elif self._hover:
            p.fillRect(self.rect(), self.palette().midlight())

        # Icon & text colour
        if self._selected:
            col = QColor(get_token("primary"))
        elif self._hover:
            col = QColor(get_token("text"))
        else:
            col = QColor(get_token("text_secondary"))

        # Left accent bar for selected
        if self._selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(get_token("primary")))
            p.drawRoundedRect(0, 10, 3, 40, RADIUS_SM, RADIUS_SM)

        pen = QPen(col, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        iy = 22  # icon vertical centre
        if self._icon_type == self.HOME:
            self._draw_home(p, cx, iy)
        elif self._icon_type == self.NEW:
            self._draw_new(p, cx, iy)
        elif self._icon_type == self.OPEN:
            self._draw_open(p, cx, iy)
        elif self._icon_type == self.SETTINGS:
            self._draw_settings(p, cx, iy)

        # Label
        if self._label:
            p.setPen(col)
            weight = FW_SEMIBOLD if self._selected else FW_MEDIUM
            p.setFont(_f(FS_XS, weight))
            p.drawText(QRect(0, 42, w, 14), Qt.AlignCenter, self._label)

        p.end()

    @staticmethod
    def _draw_home(p: QPainter, cx: int, cy: int):
        # Roof
        p.drawPolyline(
            QPolygonF(
                [
                    QPointF(cx - 11, cy + 1),
                    QPointF(cx, cy - 10),
                    QPointF(cx + 11, cy + 1),
                ]
            )
        )
        # Left wall
        p.drawLine(QPointF(cx - 9, cy + 1), QPointF(cx - 9, cy + 12))
        # Right wall
        p.drawLine(QPointF(cx + 9, cy + 1), QPointF(cx + 9, cy + 12))
        # Floor
        p.drawLine(QPointF(cx - 9, cy + 12), QPointF(cx + 9, cy + 12))
        # Door
        p.drawRect(QRectF(cx - 3.5, cy + 5, 7, 7))

    @staticmethod
    def _draw_new(p: QPainter, cx: int, cy: int):
        # Page with folded top-right corner
        p.drawPolyline(
            QPolygonF(
                [
                    QPointF(cx - 8, cy - 11),
                    QPointF(cx + 3, cy - 11),  # fold notch
                    QPointF(cx + 9, cy - 5),
                    QPointF(cx + 9, cy + 11),
                    QPointF(cx - 8, cy + 11),
                    QPointF(cx - 8, cy - 11),
                ]
            )
        )
        # Fold crease
        p.drawLine(QPointF(cx + 3, cy - 11), QPointF(cx + 3, cy - 5))
        p.drawLine(QPointF(cx + 3, cy - 5), QPointF(cx + 9, cy - 5))

    @staticmethod
    def _draw_open(p: QPainter, cx: int, cy: int):
        # Folder body
        p.drawRect(QRectF(cx - 11, cy - 2, 22, 13))
        # Folder tab (top-left)
        p.drawPolyline(
            QPolygonF(
                [
                    QPointF(cx - 11, cy - 2),
                    QPointF(cx - 11, cy - 7),
                    QPointF(cx - 3, cy - 7),
                    QPointF(cx, cy - 2),
                ]
            )
        )

    @staticmethod
    def _draw_settings(p: QPainter, cx: int, cy: int):
        import math

        # Gear: 8 rectangular teeth + centre hole
        N = 8  # number of teeth
        r_out = 9.0  # tooth tip radius
        r_in = 6.5  # tooth root (valley) radius
        r_hole = 3.5  # centre hole radius
        half_t = math.radians(8)  # half tooth angular width

        pts = []
        for i in range(N):
            base = math.radians(i * 360 / N) - math.pi / 2
            for ang, r in [
                (base - half_t, r_in),
                (base - half_t, r_out),
                (base + half_t, r_out),
                (base + half_t, r_in),
            ]:
                pts.append(QPointF(cx + r * math.cos(ang), cy + r * math.sin(ang)))

        p.drawPolygon(QPolygonF(pts))
        p.drawEllipse(QRectF(cx - r_hole, cy - r_hole, r_hole * 2, r_hole * 2))

    # ── Events ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if not self._selected:
            self._hover = True
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._selected:
            self._hover = False
            self.update()
        super().leaveEvent(event)


# ── Right-panel grid card delegate ────────────────────────────────────────────


class _GridCardDelegate(QStyledItemDelegate):
    RADIUS = RADIUS_LG

    # Status semantic tint colors (ARGB alpha applied at paint time)
    _STATUS_TINT = {
        "locked": (59, 130, 246),  # blue
        "crashed": (239, 68, 68),  # red
        "corrupted": (249, 115, 22),  # orange
    }
    _STATUS_DOT = {
        "locked": get_token("info"),
        "crashed": get_token("danger"),
        "corrupted": get_token("warning"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mouse_pos = QPoint(-1, -1)  # viewport-relative; set by _GridList
        self._loading_pid = None
        self._loading_dots = 0  # 0 / 1 / 2 → "." / ".." / "..."

    def _card_h(self, status: str) -> int:
        return CARD_H_WARN if status in ("crashed", "corrupted") else CARD_H_NORM

    def sizeHint(self, option, index):
        data = index.data(Qt.UserRole)
        status = data.get("status", "ok") if isinstance(data, dict) else "ok"
        return QSize(option.rect.width(), self._card_h(status))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        data = index.data(Qt.UserRole)
        if not isinstance(data, dict):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(6, 4, -6, -4)
        pal = option.palette

        is_sel = bool(option.state & QStyle.State_Selected)
        is_hov = bool(option.state & QStyle.State_MouseOver)

        # ── Data ───────────────────────────────────────────────────────────
        name = data.get("display_name") or data.get("project_id") or "Unnamed"
        status = data.get("status", "ok")
        is_pinned = data.get("pinned", False)
        size_kb = data.get("size_kb")
        chunks = data.get("chunk_count")
        text_col = pal.text().color()
        muted_col = pal.placeholderText().color()
        R = rect.right()
        card_h = self._card_h(status)
        is_loading = (
            self._loading_pid is not None
            and data.get("project_id") == self._loading_pid
        )

        # ── Computed vertical anchors (relative to rect.top()) ─────────────
        # Three content lines centred within the card, evenly distributed
        cy = rect.top() + card_h // 2 - 4  # visual centre offset
        y_title = cy - 8  # title baseline
        y_meta = cy + 8  # meta baseline
        y_warn = cy + 22  # warning baseline (warn cards only)

        # ── Background ─────────────────────────────────────────────────────
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(pal.base().color()))
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # ── Loading state — early exit ──────────────────────────────────────
        if is_loading:
            # Muted overlay tint
            tint = QColor(muted_col)
            tint.setAlpha(18)
            painter.setBrush(QBrush(tint))
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

            # Separator
            sep_col = pal.mid().color()
            sep_col.setAlpha(35)
            painter.setPen(QPen(sep_col, 1))
            painter.drawLine(
                rect.left() + 16,
                option.rect.bottom(),
                rect.right() - 16,
                option.rect.bottom(),
            )

            # "Opening ." / ".." / "..." pill (always visible, not just hover)
            dots = "." * (self._loading_dots + 1)
            pill_label = f"Opening{dots}"
            pill_h, pill_w = 22, 72
            pill_x = R - 32 - SP2 - pill_w
            pill_y = rect.top() + (card_h - pill_h) // 2
            pill_rect = QRect(pill_x, pill_y, pill_w, pill_h)
            m = QColor(muted_col)
            m.setAlpha(160)
            painter.setPen(QPen(m, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(pill_rect, pill_h // 2, pill_h // 2)
            painter.setFont(_f(FS_SM, FW_MEDIUM))
            painter.drawText(pill_rect, Qt.AlignCenter, pill_label)

            # Title (dimmed)
            painter.setFont(_f(FS_LG, FW_MEDIUM))
            dim = QColor(text_col)
            dim.setAlpha(100)
            painter.setPen(dim)
            nfm = painter.fontMetrics()
            title_x = rect.left() + SP4
            painter.drawText(
                QPoint(title_x, y_title),
                nfm.elidedText(name, Qt.ElideRight, pill_x - title_x - SP4),
            )

            painter.restore()
            return

        # Semantic surface tint for non-ok statuses
        tint_rgb = self._STATUS_TINT.get(status)
        if tint_rgb:
            tint = QColor(*tint_rgb)
            tint.setAlpha(14)
            painter.setBrush(QBrush(tint))
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # Selection / hover tint (on top of semantic tint)
        if is_sel:
            tint = QColor(get_token("primary"))
            tint.setAlpha(22)
            painter.setBrush(QBrush(tint))
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)
        elif is_hov:
            tint = QColor(get_token("primary"))
            tint.setAlpha(14)
            painter.setBrush(QBrush(tint))
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # ── Pinned left accent bar (visible at rest, mirrors _NavButton) ───
        if is_pinned:
            painter.setPen(Qt.NoPen)
            pin_bar = QColor(get_token("primary"))
            pin_bar.setAlpha(200)
            painter.setBrush(pin_bar)
            painter.drawRoundedRect(
                rect.left(),
                rect.top() + 10,
                3,
                rect.height() - 20,
                RADIUS_SM,
                RADIUS_SM,
            )

        # ── Locked project outline border ──────────────────────────────────
        if status == "locked":
            lock_col = QColor(get_token("info"))
            lock_col.setAlpha(160)
            painter.setPen(QPen(lock_col, 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                rect.adjusted(1, 1, -1, -1), self.RADIUS, self.RADIUS
            )

        # ── Subtle card separator ──────────────────────────────────────────
        sep_col = pal.mid().color()
        sep_col.setAlpha(35)
        painter.setPen(QPen(sep_col, 1))
        painter.drawLine(
            rect.left() + 16,
            option.rect.bottom(),
            rect.right() - 16,
            option.rect.bottom(),
        )

        # Text left indent
        tx = rect.left() + SP4

        # ── ⋮ menu button (always visible) ────────────────────────────────
        menu_col = QColor(get_token("primary")) if is_sel else QColor(muted_col)
        menu_col.setAlpha(200 if is_hov else 150)
        painter.setPen(menu_col)
        painter.setFont(_f(FS_MD, FW_BOLD))
        painter.drawText(
            QRect(R - 28, rect.top(), 24, card_h),
            Qt.AlignCenter,
            "\u22ee",
        )

        # ── Hover controls: star + Open pill ──────────────────────────────
        if is_hov:
            # Star toggle
            star_rect = QRect(R - 58, rect.top(), 26, card_h)
            star_col = QColor(get_token("primary")) if is_pinned else QColor(muted_col)
            star_col.setAlpha(220 if is_pinned else 150)
            painter.setPen(star_col)
            painter.setFont(_f(FS_MD + 1, FW_NORMAL))
            painter.drawText(
                star_rect, Qt.AlignCenter, "\u2605" if is_pinned else "\u2606"
            )

            # Open / Return pill
            pill_label = "Return \u203a" if status == "locked" else "Open"
            pill_h, pill_w = 22, 56
            pill_x = R - 58 - SP2 - pill_w
            pill_y = rect.top() + (card_h - pill_h) // 2
            pill_rect = QRect(pill_x, pill_y, pill_w, pill_h)
            prim = QColor(get_token("primary"))
            pill_hov = pill_rect.contains(self._mouse_pos)
            if pill_hov:
                painter.setBrush(QBrush(prim))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(pill_rect, pill_h // 2, pill_h // 2)
                painter.setPen(QColor("white"))
            else:
                painter.setPen(QPen(prim, 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(pill_rect, pill_h // 2, pill_h // 2)
                painter.setPen(prim)
            painter.setFont(_f(FS_SM, FW_MEDIUM))
            painter.drawText(pill_rect, Qt.AlignCenter, pill_label)

            right_edge = pill_x - SP2
        else:
            right_edge = R - 32

            # Status dot (hidden on hover — pill takes priority)
            dot_hex = self._STATUS_DOT.get(status)
            if dot_hex:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(dot_hex))
                painter.drawEllipse(
                    right_edge - 8, rect.top() + (card_h - 7) // 2, 7, 7
                )
                right_edge -= 16

            # Pin dot (hidden on hover — star takes priority, bar shows at rest)
            if is_pinned:
                painter.setPen(Qt.NoPen)
                pin_c = QColor(get_token("primary"))
                pin_c.setAlpha(180)
                painter.setBrush(pin_c)
                painter.drawEllipse(
                    right_edge - 7, rect.top() + (card_h - 5) // 2, 5, 5
                )
                right_edge -= 13

        # ── Title ──────────────────────────────────────────────────────────
        painter.setFont(_f(FS_LG, FW_MEDIUM))
        painter.setPen(text_col)
        nfm = painter.fontMetrics()
        painter.drawText(
            QPoint(tx, y_title),
            nfm.elidedText(name, Qt.ElideRight, right_edge - tx - 4),
        )

        # ── Meta line ─────────────────────────────────────────────────────
        painter.setFont(_f(FS_SM))
        painter.setPen(muted_col)
        meta = []
        if data.get("last_modified"):
            meta.append(_relative_time(data["last_modified"]))
        if size_kb:
            meta.append(f"{size_kb} KB")
        elif chunks:
            meta.append(f"{chunks} chunks")
        painter.drawText(
            QPoint(tx, y_meta),
            "   \u00b7   ".join(m for m in meta if m),
        )

        # ── Warning line (crashed / corrupted only) ────────────────────────
        if status == "crashed":
            warn_col = QColor(get_token("danger"))
            warn_col.setAlpha(210)
            painter.setPen(warn_col)
            painter.setFont(_f(FS_XS, FW_MEDIUM))
            painter.drawText(
                QPoint(tx, y_warn), "Needs recovery — last save may be incomplete"
            )
        elif status == "corrupted":
            warn_col = QColor(get_token("warning"))
            warn_col.setAlpha(210)
            painter.setPen(warn_col)
            painter.setFont(_f(FS_XS, FW_MEDIUM))
            painter.drawText(
                QPoint(tx, y_warn), "File may be damaged — restore from a checkpoint"
            )

        painter.restore()


class _GridList(QListWidget):
    menu_requested = Signal(str, QPoint)
    open_requested = Signal(str)
    pin_toggled = Signal(str)

    def mouseMoveEvent(self, event):
        d = self.itemDelegate()
        if hasattr(d, "_mouse_pos"):
            d._mouse_pos = event.pos()
        super().mouseMoveEvent(event)
        index = self.indexAt(event.pos())
        if index.isValid():
            self.update(index)

    def leaveEvent(self, event):
        d = self.itemDelegate()
        if hasattr(d, "_mouse_pos"):
            d._mouse_pos = QPoint(-1, -1)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() in (Qt.RightButton, Qt.LeftButton):
            index = self.indexAt(event.pos())
            if index.isValid():
                item = self.item(index.row())
                data = item.data(Qt.UserRole) if item else None
                if isinstance(data, dict):
                    pid = data["project_id"]
                    # Swallow all clicks on a card that is currently loading
                    delegate = self.itemDelegate()
                    if getattr(delegate, "_loading_pid", None) == pid:
                        return
                    gpos = self.viewport().mapToGlobal(event.pos())
                    if event.button() == Qt.RightButton:
                        self.menu_requested.emit(pid, gpos)
                        return
                    # left-click: check hit zones right-to-left
                    # rect = ir.adjusted(6,4,-6,-4), R = rect.right() = ir.right()-6
                    ir = self.visualItemRect(item)
                    R = ir.right() - 6  # matches rect.right() in delegate
                    # ⋮ zone: R-28 .. R (+ 6px padding) → ir.right()-34 .. ir.right()
                    if QRect(ir.right() - 34, ir.top(), 35, ir.height()).contains(
                        event.pos()
                    ):
                        self.menu_requested.emit(pid, gpos)
                        return
                    # star zone: R-58 .. R-32 → ir.right()-64 .. ir.right()-38, padded ±4
                    if QRect(ir.right() - 68, ir.top(), 34, ir.height()).contains(
                        event.pos()
                    ):
                        self.pin_toggled.emit(pid)
                        return
                    # open pill zone: R-118 .. R-66 → ir.right()-124 .. ir.right()-72, padded
                    if QRect(ir.right() - 130, ir.top(), 62, ir.height()).contains(
                        event.pos()
                    ):
                        self.open_requested.emit(pid)
                        return
        super().mousePressEvent(event)


# ── Empty state widget ────────────────────────────────────────────────────────


class _EmptyState(QWidget):
    """Designed empty state — icon + heading + subtext + optional CTA."""

    def __init__(
        self,
        heading: str,
        subtext: str,
        show_cta: bool = True,
        manager=None,
        parent=None,
    ):
        super().__init__(parent)
        self._manager = manager
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SP10, SP10, SP10, SP10)
        layout.setSpacing(SP3)
        layout.setAlignment(Qt.AlignCenter)

        # Icon (folder glyph via unicode, drawn large)
        icon_lbl = QLabel("🗂")
        icon_lbl.setFont(_f(FS_DISP + 10, FW_NORMAL))
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(f"color: {get_token('text_disabled')};")
        layout.addWidget(icon_lbl)

        # Heading
        head_lbl = QLabel(heading)
        head_lbl.setFont(_f(FS_LG, FW_SEMIBOLD))
        head_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(head_lbl)

        # Subtext
        sub_lbl = QLabel(subtext)
        sub_lbl.setFont(_f(FS_BASE))
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setStyleSheet(f"color: {get_token('text_disabled')};")
        layout.addWidget(sub_lbl)

        # CTA button
        if show_cta and manager:
            layout.addSpacing(SP2)
            cta = QPushButton("+ New Project")
            cta.setFixedHeight(BTN_MD)
            cta.setFont(_f(FS_BASE, FW_MEDIUM))
            cta.setStyleSheet(btn_primary())
            cta.setCursor(Qt.PointingHandCursor)
            cta.clicked.connect(lambda: manager.open_project(is_new=True))
            cta_wrap = QHBoxLayout()
            cta_wrap.setAlignment(Qt.AlignCenter)
            cta_wrap.addWidget(cta)
            layout.addLayout(cta_wrap)


# ── Home page ─────────────────────────────────────────────────────────────────


class HomePage(QWidget):

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._active_project_id = None
        self._all_projects: list[dict] = []  # merged engine + recent + pinned
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_sidebar())
        root.addWidget(self._make_divider_v())
        root.addWidget(self._make_right_panel(), stretch=1)

    # ── Left sidebar ──────────────────────────────────────────────────────────

    def _make_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_W)
        sidebar.setObjectName("homeSidebar")
        sidebar.setStyleSheet("#homeSidebar { background: palette(window); }")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, SP4, 0, SP4)
        layout.setSpacing(0)

        # ── Home (always selected) ─────────────────────────────────────────
        home_btn = _NavButton(_NavButton.HOME, "Home", selected=True)
        home_btn.setToolTip("Home")
        layout.addWidget(home_btn)

        # ── New ───────────────────────────────────────────────────────────
        new_btn = _NavButton(_NavButton.NEW, "New")
        new_btn.setToolTip("New Project")
        new_btn.clicked.connect(lambda: self.manager.open_project(is_new=True))
        layout.addWidget(new_btn)

        # ── Open ──────────────────────────────────────────────────────────
        open_btn = _NavButton(_NavButton.OPEN, "Open")
        open_btn.setToolTip("Open / Import a project file")
        open_btn.clicked.connect(self._load_shared_project)
        layout.addWidget(open_btn)

        layout.addStretch()

        # ── Settings (bottom anchor) ───────────────────────────────────────
        settings_btn = _NavButton(_NavButton.SETTINGS, "Settings")
        settings_btn.setToolTip("Settings & Preferences")
        settings_btn.clicked.connect(lambda: self._open_settings())
        layout.addWidget(settings_btn)

        return sidebar

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._update_greeting()

    # ── Right panel ───────────────────────────────────────────────────────────

    def _make_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Greeting bar ──────────────────────────────────────────────────
        greet_bar = QWidget()
        greet_bar.setFixedHeight(96)
        gb = QHBoxLayout(greet_bar)
        gb.setContentsMargins(SP10, 0, SP10, 0)

        self.greeting_lbl = QLabel()
        self.greeting_lbl.setTextFormat(Qt.RichText)
        self._update_greeting()

        self._greet_timer = QTimer(self)
        self._greet_timer.timeout.connect(self._update_greeting)
        self._greet_timer.start(60_000)

        gb.addWidget(self.greeting_lbl)
        gb.addStretch()

        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setFixedHeight(BTN_SM)
        refresh_btn.setFont(_f(FS_SM))
        refresh_btn.setToolTip("Refresh project list")
        refresh_btn.setStyleSheet(btn_ghost())
        refresh_btn.clicked.connect(self.refresh_project_list)
        gb.addWidget(refresh_btn)

        layout.addWidget(greet_bar)
        layout.addWidget(self._hline())

        # ── Toolbar: section label + search + sort ────────────────────────
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(SP10, 0, SP10, 0)
        tl.setSpacing(SP2)

        self.grid_section_lbl = QLabel("RECENT PROJECTS")
        self.grid_section_lbl.setFont(_f(FS_SM, FW_SEMIBOLD))
        self.grid_section_lbl.setStyleSheet(
            f"color: {get_token('text_disabled')}; letter-spacing: 2px;"
        )
        tl.addWidget(self.grid_section_lbl)
        tl.addStretch()

        self._search_text = ""
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search projects...")
        self.search_input.setFixedHeight(BTN_SM)
        self.search_input.setMinimumWidth(160)
        self.search_input.setMaximumWidth(280)
        self.search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet(
            f"QLineEdit {{ min-height: 0; padding: 0 8px;"
            f"  border-radius: {RADIUS_MD}px; border: 1px solid palette(mid); }}"
            f"QLineEdit:focus {{ border: 1px solid {get_token('primary')}; padding: 0 7px; }}"
        )
        self.search_input.textChanged.connect(self._on_search)
        tl.addWidget(self.search_input)

        tl.addSpacing(SP4)

        self._sort_btns = []
        saved_sort = sm.get_pref("sort_order") or "recent"
        for label, key in [
            ("Recent", "recent"),
            ("Name", "name"),
            ("Pinned", "pinned"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(BTN_SM)
            btn.setFont(_f(FS_SM, FW_MEDIUM))
            btn.setCheckable(True)
            btn.setProperty("sort_key", key)
            btn.setStyleSheet(btn_ghost_checkable(radius=RADIUS_MD))
            btn.clicked.connect(self._on_sort_btn)
            btn.setChecked(key == saved_sort)
            tl.addWidget(btn, alignment=Qt.AlignCenter)
            tl.addSpacing(SP2)
            self._sort_btns.append(btn)

        # Ensure exactly one is checked (fallback if saved pref is stale)
        if not any(b.isChecked() for b in self._sort_btns):
            self._sort_btns[0].setChecked(True)

        layout.addWidget(toolbar)
        layout.addWidget(self._hline())

        # ── Project grid list (fills all remaining space) ─────────────────
        self.grid_list = _GridList()
        self.grid_list.setItemDelegate(_GridCardDelegate())
        self.grid_list.setMouseTracking(True)
        self.grid_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.grid_list.setFrameShape(QFrame.NoFrame)
        self.grid_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_list.setViewportMargins(SP8, SP4, SP8, SP4)
        self.grid_list.setStyleSheet(
            "QListWidget { background: palette(window); border: none; }"
        )
        self.grid_list.itemDoubleClicked.connect(self._open_from_grid)
        self.grid_list.menu_requested.connect(self._show_grid_menu)
        self.grid_list.open_requested.connect(
            lambda pid: self.manager.open_project(project_id=pid)
        )
        self.grid_list.pin_toggled.connect(self._toggle_pin_by_id)
        layout.addWidget(self.grid_list, stretch=1)

        return panel

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setStyleSheet("color: palette(mid);")
        line.setFixedHeight(1)
        return line

    @staticmethod
    def _make_divider_v() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Plain)
        line.setStyleSheet("color: palette(mid);")
        line.setFixedWidth(1)
        return line

    def _update_greeting(self):
        profile = sm.get_profile()
        name = profile.get("display_name", "").strip()

        # Fallback to system username if no name provided
        if not name:
            # Get system username (fallback to 'User')
            try:
                name = getpass.getuser()
            except Exception:
                name = "User"

            # Clean formatting
            name = name.strip().title() if name else "User"

        greet = _greeting()

        self.greeting_lbl.setText(
            f"<span style='font-size:{FS_MD}pt; font-weight:{FW_LIGHT};'>{greet},&nbsp;</span>"
            f"<span style='font-size:{FS_DISP}pt; font-weight:{FW_BOLD}; color:{get_token('primary')};'>{name}!</span>"
        )

    def _current_sort(self) -> str:
        for btn in self._sort_btns:
            if btn.isChecked():
                return btn.property("sort_key")
        return "recent"

    def _on_sort_btn(self):
        sender = self.sender()
        for btn in self._sort_btns:
            btn.setChecked(btn is sender)
        sm.set_pref("sort_order", self._current_sort())
        self._render_grid()

    def _on_search(self, text: str):
        self._search_text = text
        self._render_grid()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_card_loading(self, pid: str):
        """Mark a project card as loading — shows animated 'Opening…' pill."""
        delegate = self.grid_list.itemDelegate()
        delegate._loading_pid = pid
        delegate._loading_dots = 0
        if not hasattr(self, "_loading_timer"):
            self._loading_timer = QTimer(self)
            self._loading_timer.setInterval(600)
            self._loading_timer.timeout.connect(self._tick_loading_dots)
        self._loading_timer.start()
        self.grid_list.viewport().update()

    def _tick_loading_dots(self):
        delegate = self.grid_list.itemDelegate()
        delegate._loading_dots = (delegate._loading_dots + 1) % 3
        self.grid_list.viewport().update()

    def clear_card_loading(self):
        """Remove the loading state from any card."""
        if hasattr(self, "_loading_timer"):
            self._loading_timer.stop()
        delegate = self.grid_list.itemDelegate()
        delegate._loading_pid = None
        delegate._loading_dots = 0
        self.grid_list.viewport().update()

    def set_active_project(self, project_id: str | None):
        self._active_project_id = project_id

    def refresh_project_list(self):
        """Merge engine list + recent + pinned, then render both sidebar and grid."""
        engine_projects = SafeChunkEngine.list_all_projects()

        # Build lookup by project_id
        by_id: dict[str, dict] = {p["project_id"]: dict(p) for p in engine_projects}

        # Overlay open-window status
        open_windows = {
            win.project_id: win
            for win in self.manager.windows
            if win.project_id is not None
        }
        for pid, win in open_windows.items():
            if pid in by_id:
                by_id[pid]["status"] = "locked"
                mem_name = win.controller.active_display_name
                if mem_name:
                    by_id[pid]["display_name"] = mem_name
        for pid, proj in by_id.items():
            if proj.get("status") == "locked" and pid not in open_windows:
                proj["status"] = "ok"

        # Merge recent open_count
        recent_map = {r["project_id"]: r for r in sm.get_recent()}
        for pid, rdata in recent_map.items():
            if pid in by_id:
                by_id[pid]["open_count"] = rdata["open_count"]
                by_id[pid]["last_opened_at"] = rdata["last_opened_at"]

        # Mark pinned
        pinned_ids = set(sm.get_pinned())
        for pid in by_id:
            by_id[pid]["pinned"] = pid in pinned_ids

        self._all_projects = list(by_id.values())
        self._render_grid()

    def _render_grid(self):
        self.grid_list.clear()
        sort_key = self._current_sort()
        projects = list(self._all_projects)

        if sort_key == "pinned":
            projects = [p for p in projects if p.get("pinned")]
            self.grid_section_lbl.setText("PINNED PROJECTS")
        elif sort_key == "name":
            projects.sort(key=lambda p: (p.get("display_name") or "").lower())
            self.grid_section_lbl.setText("ALL PROJECTS — A–Z")
        else:
            recent_map = {r["project_id"]: r["last_opened_at"] for r in sm.get_recent()}
            projects.sort(
                key=lambda p: recent_map.get(p["project_id"])
                or p.get("last_modified")
                or "",
                reverse=True,
            )
            self.grid_section_lbl.setText("RECENT PROJECTS")

        # Search filter
        q = getattr(self, "_search_text", "").strip().lower()
        if q:
            projects = [
                p
                for p in projects
                if q in (p.get("display_name") or p.get("project_id", "")).lower()
            ]
            self.grid_section_lbl.setText(f"RESULTS FOR \u201c{q.upper()}\u201d")

        if not projects:
            item = QListWidgetItem()
            item.setFlags(Qt.NoItemFlags)
            item.setSizeHint(QSize(0, 220))
            self.grid_list.addItem(item)
            empty = _EmptyState(
                "No Projects Yet" if not q else f'No results for "{q}"',
                (
                    "Click  + New Project  to get started."
                    if not q
                    else "Try a different search term."
                ),
                show_cta=not q,
                manager=self.manager,
            )
            self.grid_list.setItemWidget(item, empty)
            return

        delegate = self.grid_list.itemDelegate()
        for p in projects:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, p)
            h = (
                delegate._card_h(p.get("status", "ok"))
                if hasattr(delegate, "_card_h")
                else CARD_H_NORM
            )
            item.setSizeHint(QSize(0, h))
            self.grid_list.addItem(item)

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _selected_pid_grid(self) -> str | None:
        item = self.grid_list.currentItem()
        data = item.data(Qt.UserRole) if item else None
        return data.get("project_id") if isinstance(data, dict) else None

    def _open_from_grid(self):
        pid = self._selected_pid_grid()
        if pid:
            self.manager.open_project(project_id=pid)

    # ── Context menus ─────────────────────────────────────────────────────────

    def _show_grid_menu(self, pid: str, pos: QPoint):
        self._show_project_menu(pid, pos)

    def _show_project_menu(self, pid: str, pos: QPoint):
        by_id = {p["project_id"]: p for p in self._all_projects}
        proj = by_id.get(pid, {})
        display = proj.get("display_name") or pid
        is_pin = sm.is_pinned(pid)

        menu = QMenu(self)
        menu.addAction("Open", lambda: self.manager.open_project(project_id=pid))
        menu.addSeparator()

        if is_pin:
            menu.addAction("Unpin", lambda: self._toggle_pin(pid, False))
        else:
            menu.addAction("📌 Pin to top", lambda: self._toggle_pin(pid, True))

        menu.addSeparator()
        menu.addAction("Copy Name", lambda: QApplication.clipboard().setText(display))
        menu.addAction("Share / Export...", lambda: self._share_project(pid, display))
        menu.addAction("Rename", lambda: self._rename_by_pid(pid, display))
        menu.addAction("Info", lambda: self._show_project_info(pid))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self._delete_pid(pid, display))
        menu.exec(pos)

    def _toggle_pin(self, pid: str, pin: bool):
        if pin:
            sm.pin(pid)
        else:
            sm.unpin(pid)
        self.manager.refresh_all_home_screens()

    def _toggle_pin_by_id(self, pid: str):
        if sm.is_pinned(pid):
            sm.unpin(pid)
        else:
            sm.pin(pid)
        self.manager.refresh_all_home_screens()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_selected(self):
        pid = self._selected_pid_grid()
        if pid:
            self.manager.open_project(project_id=pid)

    def _delete_selected(self):
        pid = self._selected_pid_grid()
        if not pid:
            QMessageBox.information(self, "Delete", "Select a project first.")
            return
        by_id = {p["project_id"]: p for p in self._all_projects}
        display = by_id.get(pid, {}).get("display_name") or pid
        self._delete_pid(pid, display)

    def _delete_pid(self, pid: str, display: str):
        if self.manager.is_project_open(pid):
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "This project is currently open.\nClose it first, then delete it.",
            )
            return
        result = QMessageBox.warning(
            self,
            "Delete Project",
            f"Permanently delete '{display}'?\n\nThis cannot be undone.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if result == QMessageBox.Ok:
            engine, _ = SafeChunkEngine.open(pid)
            if engine:
                engine.delete_project(confirmed=True)
            sm.unpin(pid)
            self.manager.refresh_all_home_screens()

    def _rename_by_pid(self, pid: str, current_name: str):
        if self.manager.is_project_open(pid):
            QMessageBox.warning(
                self,
                "Cannot Rename",
                "This project is currently open.\nClose it first, then rename it.",
            )
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename Project", "New name:", text=current_name
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == current_name:
            return
        engine, status = SafeChunkEngine.open(pid)
        if status != "SUCCESS" or engine is None:
            QMessageBox.warning(
                self, "Rename Failed", f"Could not open project.\n\n{status}"
            )
            return
        engine.rename(new_name)
        engine.detach()
        self.manager.refresh_all_home_screens()

    def _share_project(self, pid: str, display: str):
        if self.manager.is_project_open(pid):
            QMessageBox.warning(
                self,
                "Cannot Export",
                "This project is currently open.\nClose it first, then export it.",
            )
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export Project", f"{display}.3psLCCA", "3psLCCA Archive (*.3psLCCA)"
        )
        if not dest:
            return
        engine, status = SafeChunkEngine.open(pid)
        if status != "SUCCESS" or engine is None:
            QMessageBox.warning(
                self, "Export Failed", f"Could not open project.\n\n{status}"
            )
            return
        zip_name = engine.create_checkpoint(
            label="export", notes="Exported from 3psLCCA", include_blobs=True
        )
        if zip_name is None:
            engine.detach()
            QMessageBox.warning(
                self, "Export Failed", "Could not create export archive."
            )
            return
        src = engine.checkpoint_manual / zip_name
        engine.detach()
        try:
            shutil.copy2(str(src), dest)
            QMessageBox.information(
                self, "Export Complete", f"Project exported to:\n{dest}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    def _load_shared_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Shared Project", "", "3psLCCA Archive (*.3psLCCA)"
        )
        if not path:
            return
        if not zipfile.is_zipfile(path):
            QMessageBox.warning(self, "Invalid File", "Not a valid 3psLCCA archive.")
            return
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                if "checkpoint_meta.json" not in names:
                    QMessageBox.warning(
                        self, "Invalid Archive", "Missing checkpoint metadata."
                    )
                    return
                meta = json.loads(zf.read("checkpoint_meta.json").decode("utf-8"))
                if not meta.get("engine_ver"):
                    QMessageBox.warning(
                        self, "Invalid Archive", "Missing engine signature."
                    )
                    return
                archive_pid = meta.get("project_id", "")
                if not isinstance(archive_pid, str) or not archive_pid.strip():
                    QMessageBox.warning(
                        self, "Invalid Archive", "Invalid project ID in archive."
                    )
                    return
                LCCA_MAGIC = b"\x4c\x43\x43\x41"
                chunk_entries = [
                    n for n in names if n.startswith("chunks/") and n.endswith(".lcca")
                ]
                if chunk_entries:
                    first_chunk = zf.read(chunk_entries[0])
                    if first_chunk[:4] != LCCA_MAGIC:
                        QMessageBox.warning(
                            self, "Invalid Archive", "Chunk data format mismatch."
                        )
                        return
                display_name = None
                if "version.json" in names:
                    data = json.loads(zf.read("version.json").decode("utf-8"))
                    if not data.get("engine_version"):
                        QMessageBox.warning(
                            self, "Invalid Archive", "Missing engine version."
                        )
                        return
                    display_name = (
                        data.get("display_name") or data.get("project_id") or ""
                    ).strip()
                if not display_name:
                    display_name = archive_pid.strip()
        except zipfile.BadZipFile:
            QMessageBox.warning(
                self, "Invalid File", "File could not be opened as a 3psLCCA archive."
            )
            return
        except Exception as e:
            QMessageBox.warning(self, "Load Failed", f"Unexpected error:\n{e}")
            return

        display_name = display_name or "Imported Project"
        project_id = (
            re.sub(r"[^\w\-]", "_", display_name)[:40].strip("_") or "imported_project"
        )
        engine, status = SafeChunkEngine.new(
            project_id=project_id, display_name=display_name
        )
        if status != "SUCCESS" or engine is None:
            QMessageBox.warning(
                self, "Load Failed", f"Could not create project:\n{status}"
            )
            return
        pid = engine.project_id
        zip_name = os.path.basename(path)
        dest_zip = engine.checkpoint_manual / zip_name
        try:
            shutil.copy2(path, dest_zip)
            sha = hashlib.sha256(dest_zip.read_bytes()).hexdigest()
            (engine.checkpoint_manual / f"{zip_name}.sha256").write_text(sha)
        except Exception as e:
            engine.detach()
            QMessageBox.warning(self, "Load Failed", f"Could not copy archive:\n{e}")
            return
        success = engine.restore_checkpoint(zip_name)
        engine.detach()
        if not success:
            QMessageBox.warning(self, "Load Failed", "Archive could not be restored.")
            return
        self.manager.refresh_all_home_screens()
        result = QMessageBox.question(
            self,
            "Project Loaded",
            f"'{display_name}' loaded successfully.\n\nOpen it now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if result == QMessageBox.Yes:
            self.manager.open_project(project_id=pid)

    def _show_project_info(self, pid: str):
        info = SafeChunkEngine.get_project_info(pid)
        if not info:
            QMessageBox.warning(self, "Info", "Could not read project info.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Project Info — {info.get('display_name', pid)}")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(6)
        rows = [
            ("Project ID", info.get("project_id", "")),
            ("Display Name", info.get("display_name", "")),
            ("Status", info.get("status", "").capitalize()),
            ("Created", info.get("created_at", "—")),
            ("Last Modified", info.get("last_modified", "—")),
            ("Chunks", str(info.get("chunk_count", 0))),
            ("Checkpoints", str(info.get("checkpoint_count", 0))),
            ("Last Checkpoint", info.get("last_checkpoint_date") or "—"),
            ("Size", f"{info.get('size_kb', 0)} KB"),
            ("Clean Close", "Yes" if info.get("clean_close") else "No"),
            ("Engine Version", info.get("engine_version", "—")),
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


