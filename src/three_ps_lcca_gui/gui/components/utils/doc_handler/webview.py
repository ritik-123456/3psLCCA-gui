# """
# webview.py - Offline docs viewer using PySide6 WebEngine.

# Loads site/ over file:// with the WebEngine flags needed for local XHR/fetch
# (mkdocs search, JSON loading) to work without a server.

# Usage (embedded inside a running Qt app):
#     from webview import navigate

#     navigate("about/index.html")
#     navigate("guide/getting-started.html")   # same window, no new window

# Usage (standalone entry point):
#     from webview import navigate
#     navigate("about/index.html", run_loop=True)

# CLI:
#     python webview.py about/index.html
#     python webview.py guide/getting-started.html

# Config:
#     DOCS_DIR  - base directory to serve (default: site/ next to webview.py)
# """

# import sys
# from pathlib import Path
# from typing import cast

# from PySide6.QtWidgets import QApplication
# from PySide6.QtCore import QUrl, Qt

# try:
#     from PySide6.QtWebEngineWidgets import QWebEngineView
#     from PySide6.QtWebEngineCore import (
#         QWebEngineSettings,
#         QWebEngineProfile,
#     )
# except ImportError as _e:
#     raise ImportError(
#         "PySide6-WebEngine is not installed.\n"
#         "Fix: pip install PySide6-WebEngine\n"
#         f"Original error: {_e}"
#     ) from _e


# # ── Configuration ──────────────────────────────────────────────────────────────

# DOCS_DIR = Path(__file__).parent / "site"   # always relative to webview.py, not cwd


# # ── Internal singleton state ───────────────────────────────────────────────────

# _app:     QApplication       | None = None
# _view:    QWebEngineView     | None = None
# _profile: QWebEngineProfile  | None = None


# # ── App / window bootstrap ─────────────────────────────────────────────────────

# def _ensure_app() -> QApplication:
#     """Return the existing QApplication or create one (exactly once)."""
#     global _app
#     if _app is None:
#         # Allow file:// pages to make XHR/fetch calls - same as Chrome's behaviour
#         # when opening local files. Must be set before QApplication is created.
#         if "--allow-file-access-from-files" not in sys.argv:
#             sys.argv.append("--allow-file-access-from-files")
#         _app = cast(QApplication, QApplication.instance()) or QApplication(sys.argv)
#         _app.setApplicationName("Docs Viewer")
#         _app.setOrganizationName("OSBridge")
#     return _app


# def _ensure_view() -> QWebEngineView:
#     """Return the singleton QWebEngineView, creating it on first call."""
#     global _view, _profile
#     if _view is None:
#         _ensure_app()

#         # Off-the-record profile - no cache/cookie bleed between sessions
#         _profile = QWebEngineProfile(parent=None)
#         settings = _profile.settings()

#         # Required for mkdocs search and any JS that fetches local JSON/assets
#         settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled,                True)
#         settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,    True)
#         settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,  True)
#         settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent,      True)

#         _view = QWebEngineView()
#         _view.setWindowTitle("Docs Viewer")
#         _view.resize(1100, 760)

#         # Release the singleton ref when user closes the window manually
#         _view.destroyed.connect(_on_view_destroyed)

#     return _view


# def _on_view_destroyed() -> None:
#     global _view
#     _view = None


# # ── Public API ─────────────────────────────────────────────────────────────────

# def navigate(
#     relative_path: str,
#     *,
#     docs_dir: str | Path | None = None,
#     title: str | None = None,
#     run_loop: bool = False,
# ) -> None:
#     """
#     Load *relative_path* in the singleton viewer window via file://.

#     Parameters
#     ----------
#     relative_path : str
#         Path relative to docs_dir, e.g. ``"about/index.html"``.
#     docs_dir : str | Path, optional
#         Override the module-level DOCS_DIR for this call.
#     title : str, optional
#         Custom window title; defaults to the filename.
#     run_loop : bool
#         Start the Qt event loop after showing the window.
#         Default False - for use inside an already-running Qt app.
#         Set True only at your application entry point.
#     """
#     base      = Path(docs_dir).resolve() if docs_dir is not None else DOCS_DIR.resolve()
#     html_path = (base / relative_path).resolve()

#     if not html_path.exists():
#         fallback = (base / "404.html").resolve()
#         if fallback.exists():
#             html_path = fallback
#         else:
#             raise FileNotFoundError(
#                 f"[webview] File not found: {html_path}\n"
#                 f"  base  = {base}\n"
#                 f"  given = {relative_path}"
#             )

#     view = _ensure_view()
#     view.load(QUrl.fromLocalFile(str(html_path)))
#     view.setWindowTitle(title or Path(relative_path).name)

#     # Bring window to front reliably across platforms
#     view.show()
#     view.setWindowState(view.windowState() & ~Qt.WindowState.WindowMinimized)
#     view.raise_()
#     view.activateWindow()

#     if run_loop:
#         _ensure_app().exec()


# # ── CLI convenience ────────────────────────────────────────────────────────────

# if __name__ == "__main__":
#     import argparse

#     parser = argparse.ArgumentParser(description="Offline docs viewer")
#     parser.add_argument("path", help='Relative path, e.g. "about/index.html"')
#     parser.add_argument(
#         "--docs-dir", default=str(DOCS_DIR),
#         help=f"Base directory to serve (default: {DOCS_DIR})"
#     )
#     args = parser.parse_args()

#     navigate(args.path, docs_dir=args.docs_dir, run_loop=True)


