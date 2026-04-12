"""
devtools/docs_viewer_example.py — Launcher for every built page in site/.

Auto-discovers all HTML files in site/ and renders a button for each.
Click any button to load that page in the singleton offline WebView.

Run:
    python docs_viewer_example.py
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QPushButton, QLabel, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt

# webview.py lives in doc_handler — add it to path
_DOC_HANDLER_DIR = Path(__file__).parent.parent / "gui" / "components" / "utils" / "doc_handler"
if str(_DOC_HANDLER_DIR) not in sys.path:
    sys.path.insert(0, str(_DOC_HANDLER_DIR))

from webview import navigate, _ensure_app, DOCS_DIR


# ── Auto-discover pages ────────────────────────────────────────────────────────

def _discover_pages() -> list[tuple[str, str]]:
    """Walk site/ and return (label, relative_path) for every .html file."""
    pages = []
    for html_path in sorted(DOCS_DIR.rglob("*.html")):
        rel   = html_path.relative_to(DOCS_DIR)
        parts = rel.with_suffix("").parts
        label = " · ".join(p.replace("-", " ").title() for p in parts)
        pages.append((label, rel.as_posix()))
    return pages


# ── Launcher window ────────────────────────────────────────────────────────────

class Launcher(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Docs Viewer · Page Launcher")
        self.setFixedWidth(320)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QLabel("📄 Site Pages")
        header.setStyleSheet("font-size: 15px; font-weight: 600;")
        root.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        from PySide6.QtWidgets import QVBoxLayout as VBox
        col = VBox(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        pages = _discover_pages()

        if not pages:
            col.addWidget(QLabel("No HTML files found in site/.\nRun: python docs_build.py"))
        else:
            for label, path in pages:
                btn = QPushButton(label)
                btn.setFixedHeight(32)
                btn.setStyleSheet("text-align: left; padding-left: 8px;")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda checked, p=path: navigate(p))
                col.addWidget(btn)

        col.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)

        self._status = QLabel(f"{len(pages)} pages found.")
        self._status.setStyleSheet("color: grey; font-size: 11px;")
        root.addWidget(self._status)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = _ensure_app()
    launcher = Launcher()
    launcher.show()

    home = DOCS_DIR / "index.html"
    if home.exists():
        navigate("index.html")

    sys.exit(app.exec())


