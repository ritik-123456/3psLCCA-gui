"""
devtools/docs_builder_gui.py
"""

from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import ModuleType

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)
import webbrowser

# ── Paths ───────────────────────────────────────────────────────────

_DEVTOOLS_DIR = Path(__file__).parent
_PROJECT_ROOT = _DEVTOOLS_DIR.parent
_DOC_HANDLER_DIR = _PROJECT_ROOT / "gui" / "components" / "utils" / "doc_handler"

_DEFAULT_DOCS_DIR = _PROJECT_ROOT / "docs"
_DEFAULT_SITE_DIR = _DOC_HANDLER_DIR / "site"

# ── Colors ──────────────────────────────────────────────────────────

_BG = "#1e1e2e"
_BG2 = "#252535"
_BG3 = "#313244"
_TEXT = "#cdd6f4"
_DIM = "#585b70"
_GREEN = "#a6e3a1"
_RED = "#f38ba8"
_YELLOW = "#f9e2af"
_BLUE = "#89b4fa"
_BORDER = "#2a2a3e"
_SURFACE = "#181825"

# ── Loader ──────────────────────────────────────────────────────────


def _load_build_module() -> ModuleType:
    build_path = _DEVTOOLS_DIR / "docs_build.py"
    spec = importlib.util.spec_from_file_location("doc_builder", build_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# ── Worker ──────────────────────────────────────────────────────────


class _BuildWorker(QThread):

    log_line = Signal(str)
    finished = Signal(bool)

    def __init__(
        self, docs_dir, site_dir, run_link_check=False, clean=True, fix_links=False
    ):
        super().__init__()
        self.docs_dir = docs_dir
        self.site_dir = site_dir
        self.run_link_check = run_link_check
        self.clean = clean
        self.fix_links = fix_links

    def _emit(self, text):
        for l in text.splitlines():
            self.log_line.emit(l)

    def _capture(self, fn, *a):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            fn(*a)
        self._emit(buf.getvalue())

    def run(self):
        try:
            m = _load_build_module()
        except Exception as e:
            self.log_line.emit(f"ERROR {e}")
            self.finished.emit(False)
            return

        self.log_line.emit(f"docs → {self.docs_dir}")
        self.log_line.emit(f"site → {self.site_dir}\n")

        # Clean
        if self.clean:
            self.log_line.emit("Cleaning site...")
            self._capture(m.clean_site, self.site_dir)

        # Build
        try:
            self._capture(m.build, self.docs_dir, self.site_dir)
        except Exception as e:
            self.log_line.emit(f"ERROR build failed: {e}")
            self.finished.emit(False)
            return

        # 404
        try:
            self._capture(m.copy_404_page, self.site_dir)
        except Exception as e:
            self.log_line.emit(f"WARN 404 failed: {e}")

        # Sitemap + links
        self._capture(m._generate_sitemap, self.site_dir)
        self._capture(m.export_links_txt, self.site_dir)

        # Link check
        if self.run_link_check:
            self.log_line.emit("\nChecking links...")
            checked, broken = m.check_links(self.site_dir, fix=self.fix_links)
            self.log_line.emit(f"Checked {checked}")

            if broken:
                self.log_line.emit(f"{len(broken)} broken:")
                for s, l in broken:
                    self.log_line.emit(f"[{s.name}] -> {l}")
            else:
                self.log_line.emit("OK")

        self.log_line.emit("\nDone.")
        self.finished.emit(True)


# ── Dialog ──────────────────────────────────────────────────────────


class DocsBuilderDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent) 
        self.setWindowTitle("Docs Builder")
        self.resize(700, 520)
        self.setStyleSheet(f"background:{_BG}; color:{_TEXT};")

        self._worker = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)

        v.addWidget(self._path("Docs", str(_DEFAULT_DOCS_DIR), "docs_in"))
        v.addWidget(self._path("Site", str(_DEFAULT_SITE_DIR), "site_in"))

        self.fix_cb = QCheckBox("Auto-fix broken links → 404")
        self.fix_cb.setStyleSheet(f"color:{_DIM}")
        v.addWidget(self.fix_cb)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 10))
        self.log.setStyleSheet(f"background:{_SURFACE};")
        v.addWidget(self.log, 1)

        h = QHBoxLayout()
        self.btn_build = self._btn("Build", self.build)
        self.btn_check = self._btn("Build + Check", self.build_check)
        self.btn_open = self._btn("Open", self.open)
        self.btn_open.setEnabled(False)

        h.addWidget(self.btn_build)
        h.addWidget(self.btn_check)
        h.addStretch()
        h.addWidget(self.btn_open)
        v.addLayout(h)

    def _path(self, label, default, attr):
        w = QWidget()
        h = QHBoxLayout(w)
        h.addWidget(QLabel(label))
        e = QLineEdit(default)
        setattr(self, attr, e)
        h.addWidget(e, 1)
        b = QPushButton("Browse")
        b.clicked.connect(lambda: self._browse(e))
        h.addWidget(b)
        return w

    def _btn(self, t, fn):
        b = QPushButton(t)
        b.clicked.connect(fn)
        return b

    def _browse(self, edit):
        d = QFileDialog.getExistingDirectory(self, "Select", edit.text())
        if d:
            edit.setText(d)

    def _start(self, check):
        d = Path(self.docs_in.text())
        s = Path(self.site_in.text())

        self.log.clear()

        self._worker = _BuildWorker(
            d, s, run_link_check=check, clean=True, fix_links=self.fix_cb.isChecked()
        )
        self._worker.log_line.connect(self.log.appendPlainText)
        self._worker.finished.connect(self._done)
        self._worker.start()

    def build(self):
        self._start(False)

    def build_check(self):
        self._start(True)

    def _done(self, ok):
        self.btn_open.setEnabled(ok)

    def open(self):
        p = Path(self.site_in.text()) / "index.html"
        if p.exists():
            

            webbrowser.open(p.as_uri())
        else:
            QMessageBox.warning(self, "Error", "index.html not found")


