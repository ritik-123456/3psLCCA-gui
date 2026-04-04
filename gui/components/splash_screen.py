"""
gui/components/splash_screen.py
────────────────────────────────────────────────────────────────────────────────
Theme-aware Splash Screen.
Strictly uses gui.themes.get_token to match the active UI palette.
"""

from __future__ import annotations
import time
import os

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, 
    QRect, Qt, QTimer
)
from PySide6.QtGui import (QColor, QPainter, QPixmap)
from PySide6.QtWidgets import QApplication, QWidget

# Pulling live tokens and styles
from gui.themes import get_token
from gui.theme import PRIMARY, SP4, SP8, SP10, FS_DISP, FS_BASE, FW_BOLD
from gui.styles import font

MIN_DISPLAY_MS = 2000 
SPLASH_W       = 520 
SPLASH_H       = 300
_ICON_PATH = os.path.join("gui", "assets", "logo", "logo-3psLCCA.png")

class _Bar(QWidget):
    """Progress bar using the live $primary token."""
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._v: float = 0.0
        self.setFixedHeight(3)

    progress = Property(float, fget=lambda self: self._v, 
                       fset=lambda self, v: [setattr(self, '_v', max(0.0, min(1.0, v))), self.update()])

    def paintEvent(self, _):
        p = QPainter(self)
        # Track: Subtle alpha of the body color
        p.setOpacity(0.1)
        p.setBrush(QColor(get_token("$body-color", "#888888")))
        p.setPen(Qt.NoPen)
        p.drawRect(0, 0, self.width(), self.height())
        
        # Fill: Live Primary
        p.setOpacity(1.0)
        fill_w = int(self.width() * self._v)
        if fill_w > 0:
            p.setBrush(QColor(get_token("$primary", "#90af13")))
            p.drawRect(0, 0, fill_w, self.height())
        p.end()

class SplashScreen(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(SPLASH_W, SPLASH_H)
        self._center()

        self._bar = _Bar(self)
        self._bar.setGeometry(0, SPLASH_H - 3, SPLASH_W, 3)

        self._anim = QPropertyAnimation(self._bar, b"progress", self)
        self._anim.setDuration(MIN_DISPLAY_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(0.85)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._show_ts = 0.0

    def show(self) -> None:
        self._show_ts = time.monotonic()
        super().show()
        self._anim.start()

    def finish(self, _widget=None) -> None:
        delay = max(0, MIN_DISPLAY_MS - (time.monotonic() - self._show_ts) * 1000)
        QTimer.singleShot(int(delay), self._do_close)

    def _do_close(self) -> None:
        self._bar.progress = 1.0
        QTimer.singleShot(150, self.close)

    def _center(self) -> None:
        geo = QApplication.primaryScreen().availableGeometry()
        self.move(geo.center() - self.rect().center())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # 1. Background: Explicitly uses the $splash-bg token 
        # This falls back to #0d1117 (Dark) or #f8f9fa (Light) automatically
        bg_hex = get_token("$splash-bg", get_token("$body-bg", "#0d1117"))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(bg_hex)) 
        p.drawRoundedRect(self.rect(), 12, 12)

        # 2. Top Accent: Uses live $primary brand green
        p.setBrush(QColor(get_token("$primary", "#90af13")))
        p.drawRoundedRect(QRect(0, 0, SPLASH_W, 4), 2, 2)

        # 3. Branding
        margin = SP10
        logo_size = 64
        if os.path.exists(_ICON_PATH):
            p.drawPixmap(margin, margin + SP8, QPixmap(_ICON_PATH).scaled(logo_size, logo_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        # 4. Text: Uses live $body-color 
        p.setPen(QColor(get_token("$body-color", "#FFFFFF")))
        p.setFont(font(FS_DISP, FW_BOLD))
        p.drawText(QRect(margin + logo_size + SP4, margin + SP8, 300, logo_size), Qt.AlignVCenter, "3psLCCA")

        # 5. Subtitle: Uses $secondary
        p.setPen(QColor(get_token("$secondary", "#8b949e")))
        p.setFont(font(FS_BASE))
        p.drawText(margin, margin + logo_size + SP8 + SP4, SPLASH_W - (2*margin), 30, 
                   Qt.AlignLeft, "Life Cycle Cost Analysis \u00b7 Bridge Infrastructure")
        
        p.end()