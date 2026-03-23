"""
gui/styles.py — Component-level style helpers (single source of truth).

All functions read from gui/theme.py tokens — change a token there and
every widget that calls these helpers picks it up automatically.

Font helper
-----------
    from gui.styles import font
    widget.setFont(font(FS_LG, FW_SEMIBOLD))

Button QSS builders
-------------------
    from gui.styles import btn_primary, btn_outline, ...
    button.setStyleSheet(btn_primary())
"""

from PySide6.QtGui import QFont

from gui.theme import (
    FONT_FAMILY,
    PRIMARY, PRIMARY_HOVER, PRIMARY_ACTIVE,
    DANGER, DANGER_BG, DANGER_BG_PRESSED,
    BORDER,
    RADIUS_MD,
    FW_NORMAL,
)


# ── Font helper ────────────────────────────────────────────────────────────────

def font(size: int, weight: int = FW_NORMAL, italic: bool = False) -> QFont:
    """Return a QFont using the app font family with the given size/weight/style."""
    f = QFont(FONT_FAMILY)
    f.setPointSize(size)
    f.setWeight(QFont.Weight(weight))
    f.setItalic(italic)
    return f


# ── Button QSS builders ────────────────────────────────────────────────────────
#
# Each function returns a complete QSS string for QPushButton.
# Pass `radius` to override the default border-radius per instance.

def btn_primary(radius: int = RADIUS_MD) -> str:
    """Filled PRIMARY button — main CTA."""
    return (
        f"QPushButton {{ background: {PRIMARY}; color: white; border: none;"
        f"  border-radius: {radius}px; padding: 0 16px; }}"
        f"QPushButton:hover   {{ background: {PRIMARY_HOVER}; }}"
        f"QPushButton:pressed {{ background: {PRIMARY_ACTIVE}; }}"
    )


def btn_outline(radius: int = RADIUS_MD) -> str:
    """Neutral outlined button — secondary action."""
    return (
        f"QPushButton {{ background: transparent; border: 1px solid palette(mid);"
        f"  border-radius: {radius}px; padding: 0 16px; color: palette(windowText); }}"
        f"QPushButton:hover   {{ border-color: {PRIMARY}; color: {PRIMARY}; }}"
        f"QPushButton:pressed {{ background: palette(midlight); }}"
    )


def btn_outline_primary(radius: int = RADIUS_MD) -> str:
    """Outlined PRIMARY button — confirmatory action (Open, etc.)."""
    return (
        f"QPushButton {{ border: 1px solid {PRIMARY}; color: {PRIMARY};"
        f"  border-radius: {radius}px; padding: 0 20px; background: transparent; }}"
        f"QPushButton:hover   {{ background: {PRIMARY}; color: white; }}"
        f"QPushButton:pressed {{ background: {PRIMARY_ACTIVE}; color: white;"
        f"  border-color: {PRIMARY_ACTIVE}; }}"
    )


def btn_outline_danger(radius: int = RADIUS_MD) -> str:
    """Outlined danger button — destructive action (Delete, etc.)."""
    return (
        f"QPushButton {{ border: 1px solid {DANGER}; color: {DANGER};"
        f"  border-radius: {radius}px; padding: 0 20px; background: transparent; }}"
        f"QPushButton:hover   {{ background: {DANGER_BG}; }}"
        f"QPushButton:pressed {{ background: {DANGER_BG_PRESSED}; }}"
    )


def btn_text_primary(radius: int = RADIUS_MD) -> str:
    """Text-only PRIMARY button, left-aligned — nav/return links."""
    return (
        f"QPushButton {{ color: {PRIMARY}; border: none; background: transparent;"
        f"  text-align: left; padding-left: 16px; border-radius: {radius}px; }}"
        f"QPushButton:hover {{ background: palette(midlight); }}"
    )


def btn_ghost(radius: int = RADIUS_MD) -> str:
    """Subtle outlined button — toolbar/secondary small actions (Refresh, sort tabs)."""
    return (
        f"QPushButton {{ border: 1px solid palette(mid); border-radius: {radius}px;"
        f"  padding: 0 12px; background: transparent; color: palette(windowText); }}"
        f"QPushButton:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}"
    )


def btn_ghost_checkable(radius: int = RADIUS_MD) -> str:
    """Ghost button that can be checked — sort/filter toggle tabs."""
    return (
        f"QPushButton {{ border: 1px solid palette(mid); border-radius: {radius}px;"
        f"  padding: 0 10px; background: transparent; color: palette(windowText); }}"
        f"QPushButton:hover   {{ border-color: {PRIMARY}; color: {PRIMARY}; }}"
        f"QPushButton:checked {{ background: {PRIMARY}; color: white;"
        f"  border-color: {PRIMARY}; }}"
    )


def btn_banner(radius: int = RADIUS_MD) -> str:
    """White-outlined button for use on a PRIMARY-coloured banner."""
    return (
        f"QPushButton {{ color: white; border: 1px solid rgba(255,255,255,0.6);"
        f"  border-radius: {radius}px; padding: 0 14px; background: transparent; }}"
        f"QPushButton:hover   {{ background: rgba(255,255,255,0.15); }}"
        f"QPushButton:pressed {{ background: rgba(255,255,255,0.25); }}"
    )
