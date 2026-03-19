"""
devtools/launcher.py

3psLCCA Developer Tools — master launcher window.

Displays every dev tool as a card.  Click a card to open its window/dialog.
DevToolsWindow is kept as a single instance (raise if already open).
WPI + SOR dialogs open fresh each time (modeless).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Style palette (Catppuccin Mocha — same as devtools_window.py)
# ---------------------------------------------------------------------------

_BG      = "#1e1e2e"
_BG2     = "#252535"
_BG3     = "#313244"
_SURFACE = "#181825"
_TEXT    = "#cdd6f4"
_DIM     = "#585b70"
_BLUE    = "#89b4fa"
_GREEN   = "#a6e3a1"
_MAUVE   = "#cba6f7"
_PEACH   = "#fab387"
_YELLOW  = "#f9e2af"
_TEAL    = "#94e2d5"
_BORDER  = "#2a2a3e"


# ---------------------------------------------------------------------------
# Tool registry — add new tools here only
# ---------------------------------------------------------------------------

def _get_tools() -> list[dict]:
    """
    Returns list of tool descriptors.
    Imported lazily so a broken tool doesn't crash the launcher.
    """
    tools = []

    # ── Project Inspector ──────────────────────────────────────────────────
    try:
        from devtools_window import DevToolsWindow
        tools.append({
            "key":   "project_inspector",
            "icon":  "🔬",
            "name":  "Project Inspector",
            "desc":  (
                "Open, inspect, and repair .3psLCCA project archives.\n"
                "View chunks, metadata and blobs. Edit JSON directly,\n"
                "run integrity checks, and export a fixed archive."
            ),
            "accent": _BLUE,
            "open":  lambda parent, _ref={}: _open_main_window(DevToolsWindow, _ref, parent),
        })
    except ImportError as e:
        tools.append(_error_card("Project Inspector", str(e)))

    # ── WPI Database ───────────────────────────────────────────────────────
    try:
        from wpi_tool import WpiDatabaseDialog
        tools.append({
            "key":   "wpi_database",
            "icon":  "🗃",
            "name":  "WPI Database",
            "desc":  (
                "Create, edit, and verify WPI index entries.\n"
                "Rehash and save wpi_db.json from a folder\n"
                "or the default project database path."
            ),
            "accent": _GREEN,
            "open":  lambda parent: _open_dialog(WpiDatabaseDialog, parent),
        })
    except ImportError as e:
        tools.append(_error_card("WPI Database", str(e)))

    # ── SOR Generator ──────────────────────────────────────────────────────
    try:
        from sor_generator_gui import SorGeneratorDialog
        tools.append({
            "key":   "sor_generator",
            "icon":  "📋",
            "name":  "SOR Generator",
            "desc":  (
                "Convert CID#-formatted SOR Excel files (.xlsx) to\n"
                "the MumbaiSOR.json schema used by the material\n"
                "database. Preview sections before writing."
            ),
            "accent": _MAUVE,
            "open":  lambda parent: _open_dialog(SorGeneratorDialog, parent),
        })
    except ImportError as e:
        tools.append(_error_card("SOR Generator", str(e)))

    # ── Registry Builder ───────────────────────────────────────────────────
    try:
        from registry_builder_gui import RegistryBuilderDialog
        tools.append({
            "key":   "registry_builder",
            "icon":  "🗂",
            "name":  "Registry Builder",
            "desc":  (
                "Inspect, validate, and rebuild db_registry.json.\n"
                "Crawls the material_database/ folder, runs integrity\n"
                "checks, and refreshes the search-engine index."
            ),
            "accent": _TEAL,
            "open":  lambda parent: _open_dialog(RegistryBuilderDialog, parent),
        })
    except ImportError as e:
        tools.append(_error_card("Registry Builder", str(e)))

    return tools


def _error_card(name: str, reason: str) -> dict:
    return {
        "key":    f"error_{name}",
        "icon":   "⚠",
        "name":   name,
        "desc":   f"Failed to load:\n{reason}",
        "accent": "#f38ba8",
        "open":   None,
    }


# ── Open helpers ──────────────────────────────────────────────────────────────


def _open_main_window(cls, ref: dict, parent):
    """Open a QMainWindow tool; keep single instance, raise if already open."""
    existing = ref.get("win")
    if existing is not None and not existing.isHidden():
        existing.raise_()
        existing.activateWindow()
        return
    win = cls()
    ref["win"] = win
    win.show()


def _open_dialog(cls, parent):
    """Open a QDialog tool modeless so the launcher stays accessible."""
    dlg = cls(parent)
    dlg.setWindowModality(Qt.NonModal)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    # Keep a reference so it isn't GC'd
    if not hasattr(parent, "_open_dialogs"):
        parent._open_dialogs = []
    parent._open_dialogs.append(dlg)
    # Clean up reference when dialog closes
    dlg.finished.connect(lambda: parent._open_dialogs.remove(dlg)
                         if dlg in parent._open_dialogs else None)


# ---------------------------------------------------------------------------
# ToolCard widget
# ---------------------------------------------------------------------------


class ToolCard(QFrame):
    """
    A single tool card: coloured left accent bar, icon + name + description,
    and an Open button.
    """

    _CARD_BG      = "#252535"
    _CARD_BG_HOV  = "#2a2a45"
    _CARD_RADIUS  = 8
    _ACCENT_W     = 4

    def __init__(self, descriptor: dict, parent=None):
        super().__init__(parent)
        self._desc   = descriptor
        self._accent = descriptor.get("accent", _BLUE)
        self._can_open = descriptor.get("open") is not None

        self.setFixedSize(310, 170)
        self.setCursor(Qt.PointingHandCursor if self._can_open else Qt.ArrowCursor)
        self._apply_style(hovered=False)
        self._build()

    # -- build ----------------------------------------------------------------

    def _build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Coloured left accent bar
        accent_bar = QWidget()
        accent_bar.setFixedWidth(self._ACCENT_W)
        accent_bar.setStyleSheet(
            f"background:{self._accent}; border-radius:{self._ACCENT_W // 2}px;"
        )
        outer.addWidget(accent_bar)

        # Content area
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(6)
        outer.addWidget(content, stretch=1)

        # Icon + name row
        name_row = QHBoxLayout()
        name_row.setSpacing(8)

        icon_lbl = QLabel(self._desc.get("icon", ""))
        icon_lbl.setStyleSheet("font-size:22px;")
        icon_lbl.setFixedWidth(32)
        name_row.addWidget(icon_lbl)

        name_lbl = QLabel(self._desc["name"])
        nf = QFont(); nf.setPointSize(11); nf.setBold(True)
        name_lbl.setFont(nf)
        name_lbl.setStyleSheet(f"color:{_TEXT};")
        name_row.addWidget(name_lbl, stretch=1)

        cl.addLayout(name_row)

        # Description
        desc_lbl = QLabel(self._desc["desc"])
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color:{_DIM}; font-size:11px;")
        desc_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cl.addWidget(desc_lbl, stretch=1)

        # Open button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn = QPushButton("Open")
        self._btn.setFixedHeight(28)
        self._btn.setFixedWidth(80)
        self._btn.setEnabled(self._can_open)
        self._btn.setStyleSheet(
            f"QPushButton {{ background:{self._accent}; color:{_SURFACE}; border:none;"
            f" border-radius:4px; font-weight:bold; font-size:11px; }}"
            f"QPushButton:hover:enabled {{ opacity:0.85; }}"
            f"QPushButton:disabled {{ background:{_BG3}; color:{_DIM}; }}"
        )
        self._btn.clicked.connect(self._on_open)
        btn_row.addWidget(self._btn)
        cl.addLayout(btn_row)

    # -- interaction ----------------------------------------------------------

    def _on_open(self):
        opener = self._desc.get("open")
        if opener:
            # Find the launcher window to pass as parent
            w = self.window()
            opener(w)

    def enterEvent(self, event):
        if self._can_open:
            self._apply_style(hovered=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(hovered=False)
        super().leaveEvent(event)

    def _apply_style(self, hovered: bool):
        bg = self._CARD_BG_HOV if hovered else self._CARD_BG
        self.setStyleSheet(
            f"ToolCard {{ background:{bg}; border:1px solid {_BORDER};"
            f" border-radius:{self._CARD_RADIUS}px; }}"
        )


# ---------------------------------------------------------------------------
# Launcher window
# ---------------------------------------------------------------------------


class LauncherWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("3psLCCA Developer Tools")
        self.setMinimumSize(700, 400)
        self.setStyleSheet(f"QMainWindow {{ background:{_BG}; }}")
        self._open_dialogs: list = []
        self._build_ui()

    # -- build ----------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background:{_BG};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_card_area(), stretch=1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(72)
        hdr.setStyleSheet(
            f"background:{_BG2}; border-bottom:1px solid {_BORDER};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 0, 24, 0)
        hl.setSpacing(12)

        # Title block
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("3psLCCA Developer Tools")
        tf = QFont(); tf.setPointSize(13); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet(f"color:{_TEXT};")
        title_col.addWidget(title)

        subtitle = QLabel("Internal tooling for project inspection, data authoring, and format conversion")
        subtitle.setStyleSheet(f"color:{_DIM}; font-size:11px;")
        title_col.addWidget(subtitle)

        hl.addLayout(title_col)
        hl.addStretch()

        # Version badge
        badge = QLabel("devtools")
        badge.setStyleSheet(
            f"background:{_BG3}; color:{_DIM}; font-size:10px;"
            f" border-radius:3px; padding:2px 8px;"
        )
        hl.addWidget(badge)

        return hdr

    def _build_card_area(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background:{_BG}; border:none; }}"
            f"QScrollBar:vertical {{ background:{_BG2}; width:8px; border:none; }}"
            f"QScrollBar::handle:vertical {{ background:{_BG3}; border-radius:4px; }}"
        )

        container = QWidget()
        container.setStyleSheet(f"background:{_BG};")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(24, 24, 24, 24)
        cl.setSpacing(20)

        tools = _get_tools()

        # Section label
        section_lbl = QLabel("Available Tools")
        section_lbl.setStyleSheet(
            f"color:{_DIM}; font-size:10px; font-weight:bold; letter-spacing:1px;"
        )
        cl.addWidget(section_lbl)

        # Cards in rows of up to 3
        ROW_SIZE = 3
        for i in range(0, len(tools), ROW_SIZE):
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(16)

            for tool in tools[i : i + ROW_SIZE]:
                rl.addWidget(ToolCard(tool))

            # Pad remaining slots so cards don't stretch
            remaining = ROW_SIZE - len(tools[i : i + ROW_SIZE])
            for _ in range(remaining):
                spacer = QWidget()
                spacer.setFixedSize(310, 170)
                spacer.setStyleSheet("background:transparent;")
                rl.addWidget(spacer)

            rl.addStretch()
            cl.addWidget(row_w)

        cl.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setFixedHeight(36)
        footer.setStyleSheet(
            f"background:{_BG2}; border-top:1px solid {_BORDER};"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(24, 0, 24, 0)

        tip = QLabel("Tip: tools open as separate windows — the launcher stays open.")
        tip.setStyleSheet(f"color:{_DIM}; font-size:11px;")
        fl.addWidget(tip)
        fl.addStretch()

        count_lbl = QLabel(f"{len(_get_tools())} tool(s) available")
        count_lbl.setStyleSheet(f"color:{_DIM}; font-size:11px;")
        fl.addWidget(count_lbl)

        return footer
