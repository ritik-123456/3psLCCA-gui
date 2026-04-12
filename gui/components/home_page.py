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
import getpass
from datetime import datetime

from PySide6.QtCore import Qt, QSize, QPoint, QPointF, QRect, QRectF, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QPalette, QPolygonF, QPixmap
from PySide6.QtSvg import QSvgRenderer
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
from gui.themes import get_token, theme_manager
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


def get_status_config(status: str) -> dict:
    """Return dynamic status config resolved from the active theme."""
    configs = {
        "ok": {"label": "OK", "token": "success"},
        "crashed": {"label": "Needs recovery", "token": "danger"},
        "locked": {"label": "Open", "token": "info"},
        "corrupted": {"label": "Corrupted", "token": "warning"},
    }
    cfg = configs.get(status, configs["ok"])
    return {"label": cfg["label"], "color": get_token(cfg["token"])}


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
        theme_manager().theme_changed.connect(self.update)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        cx = w // 2

        # Background
        if self._selected:
            p.fillRect(self.rect(), QColor(get_token("primary", "focus")))
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mouse_pos = QPoint(-1, -1)  # viewport-relative; set by _GridList
        self._loading_pid = None
        self._loading_dots = 0  # 0 / 1 / 2 → "." / ".." / "..."

    def _card_h(self, status: str) -> int:
        return CARD_H_WARN if status in ("crashed", "corrupted") else CARD_H_NORM

    def sizeHint(self, option, index):
        data = index.data(Qt.UserRole)
        
        grid = self.parent()
        if isinstance(grid, QAbstractItemView):
            view_w = grid.viewport().width()
            view_h = grid.viewport().height()
            
            # If data is not a dict, it's the empty state item
            if not isinstance(data, dict):
                # Return full viewport height (min 400) so nothing is cut
                return QSize(view_w - 40, max(400, view_h - 40))

            # Regular project cards
            status = data.get("status", "ok")
            cols = min(2, max(1, view_w // 360))
            spacing = grid.spacing()
            margins = grid.viewportMargins()
            net_w = view_w - margins.left() - margins.right() - (spacing * (cols + 1))
            
            card_w = net_w // cols
            return QSize(card_w, self._card_h(status))
            
        return QSize(340, 78)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        data = index.data(Qt.UserRole)
        if not isinstance(data, dict):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Tighter adjustment for "full width" look
        rect = option.rect.adjusted(2, 2, -2, -2)
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

        # ── Computed vertical anchors ──────────────────────────────────────
        cy = rect.top() + card_h // 2 - 4
        y_title = cy - 8
        y_meta = cy + 8
        y_warn = cy + 22

        # ── Background & Border (Solid, no shadow) ──────────────────────────
        painter.setPen(QPen(QColor(get_token("surface_mid")), 1))
        painter.setBrush(QBrush(pal.base().color()))
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # ── Loading state — early exit ──────────────────────────────────────
        if is_loading:
            tint = QColor(muted_col)
            tint.setAlpha(18)
            painter.setBrush(QBrush(tint))
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

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
            painter.restore() # Balanced
            return

        # Semantic surface tint
        tint_token = {
            "locked": "info",
            "crashed": "danger",
            "corrupted": "warning",
        }.get(status)
        
        if tint_token:
            tint = QColor(get_token(tint_token))
            tint.setAlpha(14)
            painter.setBrush(QBrush(tint))
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # Selection / hover tint
        if is_sel:
            tint = QColor(get_token("primary"))
            tint.setAlpha(22)
            painter.setBrush(QBrush(tint))
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)
            painter.setPen(QPen(QColor(get_token("primary")), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)
        elif is_hov:
            tint = QColor(get_token("primary"))
            tint.setAlpha(14)
            painter.setBrush(QBrush(tint))
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)
            painter.setPen(QPen(QColor(get_token("primary")), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # ── Pinned left accent bar ─────────────────────────────────────────
        if is_pinned:
            painter.setPen(Qt.NoPen)
            pin_bar = QColor(get_token("primary"))
            pin_bar.setAlpha(200)
            painter.setBrush(pin_bar)
            painter.drawRoundedRect(
                rect.left() + 1,
                rect.top() + 10,
                3,
                rect.height() - 20,
                RADIUS_SM,
                RADIUS_SM,
            )

        tx = rect.left() + SP4

        # ── ⋮ menu button ─────────────────────────────────────────────────
        menu_col = QColor(get_token("primary")) if is_sel else QColor(muted_col)
        menu_col.setAlpha(200 if is_hov else 150)
        painter.setPen(menu_col)
        painter.setFont(_f(FS_MD, FW_BOLD))
        painter.drawText(
            QRect(R - 28, rect.top(), 24, card_h),
            Qt.AlignCenter,
            "\u22ee",
        )

        # ── Hover controls ────────────────────────────────────────────────
        if is_hov:
            star_rect = QRect(R - 58, rect.top(), 26, card_h)
            star_hov = star_rect.contains(self._mouse_pos)
            
            # Logic: Fill if pinned OR if mouse is specifically over the star
            show_filled = is_pinned or star_hov
            star_icon = "\u2605" if show_filled else "\u2606"
            
            star_col = QColor(get_token("primary"))
            star_col.setAlpha(220 if show_filled else 130)
            
            painter.setPen(star_col)
            painter.setFont(_f(FS_MD + 1, FW_NORMAL))
            painter.drawText(star_rect, Qt.AlignCenter, star_icon)

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
                painter.setPen(QColor(get_token("base")))
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
            dot_token = {
                "locked": "info",
                "crashed": "danger",
                "corrupted": "warning",
            }.get(status)
            
            if dot_token:
                dot_hex = get_token(dot_token)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(dot_hex))
                painter.drawEllipse(
                    right_edge - 8, rect.top() + (card_h - 7) // 2, 7, 7
                )
                right_edge -= 16

            if is_pinned:
                star_c = QColor(get_token("primary"))
                star_c.setAlpha(220)
                painter.setPen(star_c)
                painter.setFont(_f(FS_MD, FW_NORMAL))
                # Shift a bit more to accommodate the glyph width vs a 5px dot
                painter.drawText(
                    QRect(right_edge - 24, rect.top(), 20, card_h),
                    Qt.AlignCenter,
                    "\u2605"
                )
                right_edge -= 28

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

        # ── Warning line ──────────────────────────────────────────────────
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

        painter.restore() # Balanced


class _GridList(QListWidget):
    menu_requested = Signal(str, QPoint)
    open_requested = Signal(str)
    pin_toggled = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(10)
        theme_manager().theme_changed.connect(self.viewport().update)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Force re-layout of items to recalculate width from sizeHint
        self.doItemsLayout()

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
                    # rect = ir.adjusted(2,2,-2,-2), R = rect.right() = ir.right()-2
                    ir = self.visualItemRect(item)
                    R = ir.right() - 2
                    # ⋮ zone: R-28 .. R
                    if QRect(ir.right() - 34, ir.top(), 35, ir.height()).contains(
                        event.pos()
                    ):
                        self.menu_requested.emit(pid, gpos)
                        return
                    # star zone: R-58 .. R-32
                    if QRect(ir.right() - 68, ir.top(), 34, ir.height()).contains(
                        event.pos()
                    ):
                        self.pin_toggled.emit(pid)
                        return
                    # open pill zone: R-118 .. R-66
                    if QRect(ir.right() - 130, ir.top(), 62, ir.height()).contains(
                        event.pos()
                    ):
                        self.open_requested.emit(pid)
                        return
        super().mousePressEvent(event)


# ── Empty state widget ────────────────────────────────────────────────────────


class _EmptyState(QWidget):
    """Designed empty state — logo/icon + heading + subtext + optional CTA."""

    def __init__(
        self,
        heading: str | None,
        subtext: str,
        show_cta: bool = True,
        manager=None,
        parent=None,
    ):
        super().__init__(parent)
        self._manager = manager
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SP10, SP10, SP10, SP10)
        layout.setSpacing(SP4)
        layout.setAlignment(Qt.AlignCenter)

        layout.addStretch()

        if not heading:
            # Show Brand Logo instead of icon/heading
            from gui.themes import is_dark
            logo_file = "logo-3psLCCA-dark.svg" if is_dark() else "logo-3psLCCA-light.svg"
            path = os.path.join("gui", "assets", "logo", logo_file)
            
            logo_lbl = QLabel()
            logo_lbl.setAlignment(Qt.AlignCenter)
            logo_lbl.setStyleSheet("background: transparent; border: none;")
            
            if os.path.exists(path):
                renderer = QSvgRenderer(path)
                if renderer.isValid():
                    h = 160
                    aspect = renderer.defaultSize().width() / max(1, renderer.defaultSize().height())
                    w = int(h * aspect)
                    pixmap = QPixmap(w * 2, h * 2) # High DPI
                    pixmap.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pixmap)
                    renderer.render(painter)
                    painter.end()
                    logo_lbl.setPixmap(pixmap)
                    logo_lbl.setFixedSize(w, h)
                    logo_lbl.setScaledContents(True)
            layout.addWidget(logo_lbl, 0, Qt.AlignCenter)
            layout.addSpacing(SP4)
        else:
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
            cta.setFixedWidth(180)
            cta.setFont(_f(FS_BASE, FW_MEDIUM))
            cta.setStyleSheet(btn_primary())
            cta.setCursor(Qt.PointingHandCursor)
            cta.clicked.connect(lambda: manager.open_project(is_new=True))
            layout.addWidget(cta, 0, Qt.AlignCenter)
        
        layout.addStretch()


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

        self.logo_lbl = QLabel()
        gb.addWidget(self.logo_lbl)

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

        tl.addSpacing(SP4)

        from gui.components.utils.icons import make_icon
        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(make_icon("autorenew"))
        self.refresh_btn.setIconSize(QSize(12, 12))
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.setToolTip("Refresh project list")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_project_list)
        tl.addWidget(self.refresh_btn, 0, Qt.AlignCenter)

        tl.addStretch()

        self._search_text = ""
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search projects...")
        self.search_input.setFixedHeight(BTN_SM)
        self.search_input.setMinimumWidth(160)
        self.search_input.setMaximumWidth(280)
        self.search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search_input.setClearButtonEnabled(True)
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
            btn.clicked.connect(self._on_sort_btn)
            btn.setChecked(key == saved_sort)
            tl.addWidget(btn, alignment=Qt.AlignCenter)
            tl.addSpacing(SP2)
            self._sort_btns.append(btn)

        if not any(b.isChecked() for b in self._sort_btns):
            self._sort_btns[0].setChecked(True)

        layout.addWidget(toolbar)
        layout.addWidget(self._hline())

        # ── Project grid list ─────────────────────────────────────────────
        self.grid_list = _GridList()
        self.grid_list.setItemDelegate(_GridCardDelegate(self.grid_list))
        self.grid_list.setMouseTracking(True)
        self.grid_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.grid_list.setFrameShape(QFrame.NoFrame)
        self.grid_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_list.setViewportMargins(SP8, SP4, SP8, SP4)
        
        self.grid_list.setViewMode(QListWidget.IconMode)
        self.grid_list.setResizeMode(QListWidget.Adjust)
        self.grid_list.setWrapping(True)
        self.grid_list.setSpacing(SP4)
        
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

        # ── Footer: Sponsors Area ──────────────────────────────────────────
        self.footer = QWidget()
        self.footer.setFixedHeight(120)
        layout.addWidget(self.footer)
        
        fl = QHBoxLayout(self.footer)
        fl.setContentsMargins(SP10, SP6, SP10, SP6)
        
        # Developed At Section
        dev_v = QVBoxLayout()
        dev_v.setSpacing(SP3)
        dev_lbl = QLabel("DEVELOPED AT")
        dev_lbl.setFont(_f(FS_XS, FW_BOLD))
        dev_v.addWidget(dev_lbl)
        self.iitb_logo = QLabel()
        dev_v.addWidget(self.iitb_logo, 0, Qt.AlignLeft | Qt.AlignVCenter)
        fl.addLayout(dev_v)
        
        fl.addStretch()
        
        # Supported By Section
        sup_v = QVBoxLayout()
        sup_v.setSpacing(SP3)
        sup_v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sup_lbl = QLabel("SUPPORTED BY")
        sup_lbl.setFont(_f(FS_XS, FW_BOLD))
        sup_lbl.setAlignment(Qt.AlignRight)
        sup_v.addWidget(sup_lbl)
        
        sup_h = QHBoxLayout()
        sup_h.setSpacing(SP8)
        sup_h.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cs_logo = QLabel()
        self.mos_logo = QLabel()
        sup_h.addWidget(self.cs_logo)
        sup_h.addWidget(self.mos_logo)
        sup_v.addLayout(sup_h)
        fl.addLayout(sup_v)

        self._refresh_styles()
        theme_manager().theme_changed.connect(self._refresh_styles)

        return panel

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_svg_logo(self, label: QLabel, path: str, height: int):
        """Helper to render a crisp SVG logo into a QLabel with no background."""
        if not os.path.exists(path):
            label.hide()
            return
        
        label.show()
        label.setStyleSheet("background: transparent; border: none;")
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            return
            
        aspect = renderer.defaultSize().width() / max(1, renderer.defaultSize().height())
        width = int(height * aspect)
        
        pixmap = QPixmap(width * 2, height * 2) # High DPI
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        label.setPixmap(pixmap)
        label.setFixedSize(width, height)
        label.setScaledContents(True)

    def _refresh_styles(self):
        """Update theme-aware logos and dynamic QSS."""
        from gui.themes import is_dark
        is_dk = is_dark()
        
        # 1. Main Logo
        main_logo = "gui/assets/logo/logo-3psLCCA.svg" if is_dk else "gui/assets/logo/logo-3psLCCA.svg"
        self._set_svg_logo(self.logo_lbl, main_logo, 55)
        
        # 2. Footer: Developed At (IITB)
        iitb = "gui/assets/logo/special/IITB_logo_dark.svg" if is_dk else "gui/assets/logo/special/IITB_logo_light.svg"
        self._set_svg_logo(self.iitb_logo, iitb, 50)
        
        # 3. Footer: Supported By (ConstructSteel, MOS)
        cs = "gui/assets/logo/special/ConstructSteel_dark.svg" if is_dk else "gui/assets/logo/special/ConstructSteel_light.svg"
        mos = "gui/assets/logo/special/MOS_dark.svg" if is_dk else "gui/assets/logo/special/MOS_light.svg"
        self._set_svg_logo(self.cs_logo, cs, 20)
        self._set_svg_logo(self.mos_logo, mos, 40)

        # 4. Refresh Button
        self.refresh_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {get_token('surface_mid')}; border-radius: 14px; "
            f"padding: 0; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; background: transparent; }} "
            f"QPushButton:hover {{ border-color: {get_token('primary')}; background: {get_token('surface')}; }} "
            f"QPushButton:pressed {{ background: {get_token('surface_pressed')}; }}"
        )
        
        # 5. Text colors
        muted = f"color: {get_token('text_disabled')}; letter-spacing: 1px;"
        for lbl in self.footer.findChildren(QLabel):
            if lbl.text() in ("DEVELOPED AT", "SUPPORTED BY"):
                lbl.setStyleSheet(muted)
        
        self.grid_section_lbl.setStyleSheet(f"color: {get_token('text_disabled')}; letter-spacing: 2px;")
        
        self.search_input.setStyleSheet(
            f"QLineEdit {{ border-radius: {RADIUS_MD}px; border: 1px solid palette(mid); padding: 0 8px; }}"
            f"QLineEdit:focus {{ border: 1px solid {get_token('primary')}; }}"
        )
        
        for btn in self._sort_btns:
            btn.setStyleSheet(btn_ghost_checkable(radius=RADIUS_MD))
            
        self.footer.setStyleSheet(f"background: {get_token('surface')}; border: none;")
        self._update_greeting()

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
        if not name:
            try:
                name = getpass.getuser()
            except Exception:
                name = "User"
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
        if hasattr(self, "_loading_timer"):
            self._loading_timer.stop()
        delegate = self.grid_list.itemDelegate()
        delegate._loading_pid = None
        delegate._loading_dots = 0
        self.grid_list.viewport().update()

    def set_active_project(self, project_id: str | None):
        self._active_project_id = project_id

    def refresh_project_list(self):
        engine_projects = SafeChunkEngine.list_all_projects()
        by_id: dict[str, dict] = {p["project_id"]: dict(p) for p in engine_projects}
        open_windows = {win.project_id: win for win in self.manager.windows if win.project_id is not None}
        for pid, win in open_windows.items():
            if pid in by_id:
                by_id[pid]["status"] = "locked"
                mem_name = win.controller.active_display_name
                if mem_name: by_id[pid]["display_name"] = mem_name
        for pid, proj in by_id.items():
            if proj.get("status") == "locked" and pid not in open_windows: proj["status"] = "ok"
        recent_map = {r["project_id"]: r for r in sm.get_recent()}
        for pid, rdata in recent_map.items():
            if pid in by_id:
                by_id[pid]["open_count"] = rdata["open_count"]
                by_id[pid]["last_opened_at"] = rdata["last_opened_at"]
        pinned_ids = set(sm.get_pinned())
        for pid in by_id: by_id[pid]["pinned"] = pid in pinned_ids
        self._all_projects = list(by_id.values())
        
        # Explicitly re-apply current sort and filter
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
            # Sort by the most recent of either last_opened_at or last_modified
            def get_latest_time(p):
                # We want the highest (most recent) timestamp
                t1 = p.get("last_opened_at") or ""
                t2 = p.get("last_modified") or ""
                return max(t1, t2)
            
            projects.sort(key=lambda p: (get_latest_time(p), (p.get("display_name") or "").lower()), reverse=True)
            self.grid_section_lbl.setText("RECENT PROJECTS")
        q = getattr(self, "_search_text", "").strip().lower()
        if q:
            projects = [p for p in projects if q in (p.get("display_name") or p.get("project_id", "")).lower()]
            self.grid_section_lbl.setText(f"RESULTS FOR \u201c{q.upper()}\u201d")
        # ── Handle Empty States ──────────────────────────────────────────
        if not projects:
            item = QListWidgetItem()
            item.setFlags(Qt.NoItemFlags)
            
            # Use viewport dimensions for the empty state item
            vw = self.grid_list.viewport().width()
            vh = self.grid_list.viewport().height()
            
            # Use a larger minimum height (450px) to ensure no clipping
            item.setSizeHint(QSize(max(300, vw - 40), max(450, vh - 40)))
            self.grid_list.addItem(item)

            has_any = len(self._all_projects) > 0
            
            # Logic: Only show the center CTA if we are in 'Recent' view and have 0 projects total
            if q:
                head = "No matches found"
                sub = f'We couldn\'t find any projects matching "{q}". Try adjusting your search.'
                show_cta = False
            elif sort_key == "pinned":
                head = "Keep your favorites close"
                sub = "Click the star icon \u2606 on any project card to pin it for quick access."
                show_cta = False
            elif sort_key == "name":
                head = "No projects found"
                sub = "There are no projects in your database yet."
                show_cta = has_any == False
            else:
                # This is the default 'Recent' view
                if has_any:
                    head = "No recent projects"
                    sub = "Your most recently opened projects will appear here."
                    show_cta = False
                else:
                    head = None # Triggers Logo display in _EmptyState
                    sub = "Start your first bridge life-cycle cost analysis by creating a new project."
                    show_cta = True

            empty = _EmptyState(head, sub, show_cta=show_cta, manager=self.manager)
            self.grid_list.setItemWidget(item, empty)
            return

        for p in projects:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, p)
            item.setSizeHint(QSize(0, 78)) # Placeholder, delegate handles real size
            self.grid_list.addItem(item)

    def _selected_pid_grid(self) -> str | None:
        item = self.grid_list.currentItem()
        data = item.data(Qt.UserRole) if item else None
        return data.get("project_id") if isinstance(data, dict) else None

    def _open_from_grid(self):
        pid = self._selected_pid_grid()
        if pid: self.manager.open_project(project_id=pid)

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
        if is_pin: menu.addAction("Unpin", lambda: self._toggle_pin(pid, False))
        else: menu.addAction("📌 Pin to top", lambda: self._toggle_pin(pid, True))
        menu.addSeparator()
        menu.addAction("Copy Name", lambda: QApplication.clipboard().setText(display))
        menu.addAction("Share / Export...", lambda: self._share_project(pid, display))
        menu.addAction("Rename", lambda: self._rename_by_pid(pid, display))
        menu.addAction("Duplicate", lambda: self._duplicate_project(pid, display))
        menu.addAction("Info", lambda: self._show_project_info(pid))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self._delete_pid(pid, display))
        menu.exec(pos)

    def _toggle_pin(self, pid: str, pin: bool):
        if pin: sm.pin(pid)
        else: sm.unpin(pid)
        self.manager.refresh_all_home_screens()

    def _toggle_pin_by_id(self, pid: str):
        if sm.is_pinned(pid): sm.unpin(pid)
        else: sm.pin(pid)
        self.manager.refresh_all_home_screens()

    def _delete_pid(self, pid: str, display: str):
        if self.manager.is_project_open(pid):
            QMessageBox.warning(self, "Cannot Delete", "Close project first.")
            return
        if QMessageBox.warning(self, "Delete Project", f"Delete '{display}'?", QMessageBox.Ok | QMessageBox.Cancel) == QMessageBox.Ok:
            engine, _ = SafeChunkEngine.open(pid)
            if engine: engine.delete_project(confirmed=True)
            sm.unpin(pid)
            self.manager.refresh_all_home_screens()

    def _rename_by_pid(self, pid: str, current_name: str):
        if self.manager.is_project_open(pid):
            QMessageBox.warning(self, "Cannot Rename", "Close project first.")
            return
        new_name, ok = QInputDialog.getText(self, "Rename Project", "New name:", text=current_name)
        if not ok or not new_name.strip() or new_name == current_name: return
        engine, status = SafeChunkEngine.open(pid)
        if status == "SUCCESS" and engine:
            engine.rename(new_name.strip())
            engine.detach()
            self.manager.refresh_all_home_screens()

    def _duplicate_project(self, pid: str, current_name: str):
        """Create a clone of the project with ' - Copy' appended to name."""
        if self.manager.is_project_open(pid):
            QMessageBox.warning(self, "Cannot Duplicate", "Please close the project before duplicating.")
            return
            
        new_display_name = f"{current_name} - Copy"
        # Generate a unique ID based on the new name
        timestamp = datetime.now().strftime("%H%M%S")
        new_pid = re.sub(r"[^\w\-]", "_", new_display_name)[:30].strip("_") + f"_{timestamp}"
        
        # 1. Open source to get all data
        src_engine, status = SafeChunkEngine.open(pid)
        if status != "SUCCESS" or not src_engine:
            QMessageBox.warning(self, "Duplicate Failed", "Could not read source project.")
            return
            
        try:
            # 2. Create target project
            dest_engine, d_status = SafeChunkEngine.new(project_id=new_pid, display_name=new_display_name)
            if d_status != "SUCCESS" or not dest_engine:
                QMessageBox.warning(self, "Duplicate Failed", "Could not create new project entry.")
                src_engine.detach()
                return
                
            # 3. Clone all chunks and blobs
            # We use the internal engine structures to copy files safely
            src_dir = src_engine.project_path
            dest_dir = dest_engine.project_path
            
            # Copy chunks and blobs folders
            for sub in ["chunks", "blobs"]:
                s = src_dir / sub
                d = dest_dir / sub
                if s.exists():
                    shutil.copytree(s, d, dirs_exist_ok=True)
            
            # Finalize: detach both
            src_engine.detach()
            dest_engine.detach()
            
            # 4. Briefly open the NEW one to update its last_modified timestamp
            # and register it in the recent list so it appears at the top.
            final_engine, _ = SafeChunkEngine.open(new_pid)
            if final_engine:
                sm.record_open(new_pid)
                final_engine.detach()
            
            self.manager.refresh_all_home_screens()
            QMessageBox.information(self, "Success", f"Project duplicated as:\n{new_display_name}")
            
        except Exception as e:
            QMessageBox.warning(self, "Duplicate Failed", f"Error during copy: {str(e)}")
            if 'src_engine' in locals(): src_engine.detach()

    def _share_project(self, pid: str, display: str):
        if self.manager.is_project_open(pid):
            QMessageBox.warning(self, "Cannot Export", "Close project first.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export Project", f"{display}.3psLCCA", "3psLCCA Archive (*.3psLCCA)")
        if not dest: return
        engine, status = SafeChunkEngine.open(pid)
        if status == "SUCCESS" and engine:
            zip_name = engine.create_checkpoint(label="export", include_blobs=True)
            if zip_name:
                shutil.copy2(str(engine.checkpoint_manual / zip_name), dest)
                QMessageBox.information(self, "Export Complete", f"Exported to:\n{dest}")
            engine.detach()

    def _load_shared_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "3psLCCA Archive (*.3psLCCA)")
        if not path: return
        try:
            with zipfile.ZipFile(path, "r") as zf:
                meta = json.loads(zf.read("checkpoint_meta.json").decode("utf-8"))
                display_name = meta.get("display_name", "Imported Project")
                project_id = re.sub(r"[^\w\-]", "_", display_name)[:40].strip("_")
                engine, status = SafeChunkEngine.new(project_id=project_id, display_name=display_name)
                if engine:
                    shutil.copy2(path, engine.checkpoint_manual / os.path.basename(path))
                    engine.restore_checkpoint(os.path.basename(path))
                    engine.detach()
                    self.manager.refresh_all_home_screens()
        except Exception as e:
            QMessageBox.warning(self, "Load Failed", str(e))

    def _show_project_info(self, pid: str):
        info = SafeChunkEngine.get_project_info(pid)
        if not info: return
        dlg = QDialog(self); dlg.setWindowTitle("Project Info"); dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg); form = QFormLayout()
        for k, v in [("ID", info.get("project_id")), ("Name", info.get("display_name")), ("Status", info.get("status")), 
                     ("Created", info.get("created_at")), ("Modified", info.get("last_modified")), ("Size", f"{info.get('size_kb')} KB")]:
            lbl = QLabel(str(v)); lbl.setTextInteractionFlags(Qt.TextSelectableByMouse); form.addRow(f"{k}:", lbl)
        layout.addLayout(form); btn = QPushButton("Close"); btn.clicked.connect(dlg.accept); layout.addWidget(btn); dlg.exec()
