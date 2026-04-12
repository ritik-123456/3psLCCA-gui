"""
devtools/country_manager_gui.py

Country Manager — create and remove material_database country folders.

Purpose:
  Each country folder under material_database/ acts as a container where
  users can place SOR Excel files and generate a SOR JSON database for
  that country. This tool manages those top-level folders.

Can be opened:
  - Standalone from the launcher (loads its own registry module)
  - As a child of CatalogBuilderDialog (receives mod + db_root, no duplication)

Signals:
  folders_changed — emitted after any add/remove so the parent can reload.

Workflow:
  1. Browse the full country list:
       green  ✓  = folder exists and has content  (safe, do not delete)
       yellow ✓  = folder exists but is empty     (can remove)
       dim    ·  = no folder yet                  (can add)
       red    ⚠  = folder exists but NOT in country list (orphaned)
  2. Select a country → Add or Remove
  3. Rebuild Registry after changes (or let CatalogBuilderDialog do it)
"""

from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType

from PySide6.QtCore import Qt, QSortFilterProxyModel, QThread, Signal
from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Style palette (Catppuccin Mocha — matches all other devtools)
# ---------------------------------------------------------------------------

_BG      = "#1e1e2e"
_BG2     = "#252535"
_BG3     = "#313244"
_SURFACE = "#1a1a2e"
_TEXT    = "#cdd6f4"
_DIM     = "#585b70"
_GREEN   = "#a6e3a1"
_YELLOW  = "#f9e2af"
_ORANGE  = "#fab387"
_RED     = "#f38ba8"
_BLUE    = "#89b4fa"
_MAUVE   = "#cba6f7"
_BORDER  = "#333"

_BTN = (
    f"QPushButton {{ background:{_BG3}; color:{_TEXT}; border:1px solid #444;"
    f" border-radius:4px; padding:0 14px; }}"
    f"QPushButton:hover:enabled {{ background:#45475a; }}"
    f"QPushButton:disabled {{ color:{_DIM}; border-color:{_BORDER}; background:{_BG2}; }}"
)
_BTN_GREEN = (
    f"QPushButton {{ background:{_GREEN}; color:{_BG}; border:none;"
    f" border-radius:4px; padding:0 18px; font-weight:bold; }}"
    f"QPushButton:hover:enabled {{ background:#c0f0bc; }}"
    f"QPushButton:disabled {{ background:{_BG3}; color:{_DIM}; }}"
)
_BTN_RED = (
    f"QPushButton {{ background:{_RED}; color:{_BG}; border:none;"
    f" border-radius:4px; padding:0 18px; font-weight:bold; }}"
    f"QPushButton:hover:enabled {{ background:#f8a0b8; }}"
    f"QPushButton:disabled {{ background:{_BG3}; color:{_DIM}; }}"
)
_BTN_MAUVE = (
    f"QPushButton {{ background:{_MAUVE}; color:{_BG}; border:none;"
    f" border-radius:4px; padding:0 18px; font-weight:bold; }}"
    f"QPushButton:hover:enabled {{ background:#dbb6ff; }}"
    f"QPushButton:disabled {{ background:{_BG3}; color:{_DIM}; }}"
)
_INPUT = (
    f"QLineEdit {{ background:{_SURFACE}; color:{_TEXT}; border:1px solid #444;"
    f" border-radius:3px; padding:4px 8px; }}"
    f"QLineEdit:focus {{ border-color:{_BLUE}; }}"
)
_LIST = (
    f"QListView {{ background:{_SURFACE}; color:{_TEXT}; border:1px solid {_BORDER};"
    f" font-size:12px; outline:none; }}"
    f"QListView::item {{ padding:4px 8px; }}"
    f"QListView::item:selected {{ background:{_BG3}; color:{_TEXT}; }}"
    f"QListView::item:hover {{ background:{_BG2}; }}"
)
_LOG = (
    f"QPlainTextEdit {{ background:{_SURFACE}; color:{_DIM}; border:1px solid {_BORDER};"
    f" font-family:Consolas,monospace; font-size:11px; }}"
)

# Sentinel stored in item data to mark orphaned folders
_ORPHAN = "__orphan__"


# ---------------------------------------------------------------------------
# Path helpers (used in standalone mode)
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_db_root() -> Path:
    return (
        _project_root()
        / "gui" / "components" / "structure" / "registry" / "material_database"
    )


def _default_registry_py() -> Path:
    return (
        _project_root()
        / "gui" / "components" / "structure" / "registry" / "material_catalog.py"
    )


def _default_countries_data_py() -> Path:
    return _project_root() / "gui" / "components" / "utils" / "countries_data.py"


def _load_module(path: Path, name: str) -> ModuleType | None:
    try:
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Background worker — registry rebuild (only used in standalone mode)
# ---------------------------------------------------------------------------

class _RebuildWorker(QThread):
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, mod: ModuleType):
        super().__init__()
        self._mod = mod

    def run(self):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                manifest = self._mod.build_registry()
            self.finished.emit(manifest)
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class CountryManagerDialog(QDialog):
    """
    Country folder manager.

    Parameters
    ----------
    parent : QWidget, optional
    mod    : ModuleType, optional
        Pre-loaded material_catalog module from CatalogBuilderDialog.
        If None, loaded automatically (standalone mode).
    db_root : Path, optional
        Path to material_database/.
        If None, auto-detected from project structure.
    """

    folders_changed = Signal()   # emitted after any add / remove
    rebuild_needed  = Signal()   # emitted when registry may have stale entries

    def __init__(self, parent=None, mod: ModuleType | None = None,
                 db_root: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle("Country Manager")
        self.setMinimumSize(600, 580)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
            & ~Qt.WindowContextHelpButtonHint
        )
        self.setStyleSheet(f"QDialog {{ background:{_BG}; color:{_TEXT}; }}")

        self._db_root          = db_root or _default_db_root()
        self._reg_mod          = mod
        self._standalone       = mod is None   # True  → manage own rebuild
        self._worker: QThread | None = None

        # country name → FOLDER_NAME  (from countries_data)
        self._country_to_folder: dict[str, str] = {}
        # FOLDER_NAME → country name  (reverse)
        self._folder_to_country: dict[str, str] = {}

        self._build_ui()
        self._load_data()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel("Country Manager")
        tf = QFont(); tf.setPointSize(12); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet(f"color:{_TEXT};")
        root.addWidget(title)

        desc = QLabel(
            "Manage top-level country folders inside material_database/.\n"
            "Drop SOR Excel files into a country folder, generate a SOR JSON,\n"
            "then rebuild the registry so suggestions appear in the material dialog."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{_DIM}; font-size:11px;")
        root.addWidget(desc)

        root.addWidget(self._sep())

        # Legend
        legend = QLabel(
            f'<span style="color:{_GREEN};">✓ green</span> = has content &nbsp;&nbsp;'
            f'<span style="color:{_DIM};">· dim</span> = no folder / empty &nbsp;&nbsp;'
            f'<span style="color:{_RED};">⚠ red</span> = orphaned (not in country list)'
        )
        legend.setStyleSheet("font-size:11px;")
        root.addWidget(legend)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter countries…")
        self._search.setStyleSheet(_INPUT)
        self._search.textChanged.connect(self._on_search)
        root.addWidget(self._search)

        # List
        self._model = QStandardItemModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(0)

        self._list = QListView()
        self._list.setModel(self._proxy)
        self._list.setStyleSheet(_LIST)
        self._list.setEditTriggers(QListView.NoEditTriggers)
        self._list.setSelectionMode(QListView.ExtendedSelection)
        self._list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._list.selectionModel().selectionChanged.connect(self._on_selection)
        root.addWidget(self._list, stretch=1)

        root.addWidget(self._sep())

        # Buttons
        btn_row = QHBoxLayout()

        self._select_all_btn = QPushButton("Select All Unregistered")
        self._select_all_btn.setFixedHeight(34)
        self._select_all_btn.setStyleSheet(_BTN)
        self._select_all_btn.setToolTip("Select all countries that don't have a folder yet")
        self._select_all_btn.clicked.connect(self._select_all_unregistered)
        btn_row.addWidget(self._select_all_btn)

        self._add_btn = QPushButton("Add Folder")
        self._add_btn.setFixedHeight(34)
        self._add_btn.setEnabled(False)
        self._add_btn.setStyleSheet(_BTN_GREEN)
        self._add_btn.clicked.connect(self._add_folder)
        btn_row.addWidget(self._add_btn)

        self._remove_btn = QPushButton("Remove Folder")
        self._remove_btn.setFixedHeight(34)
        self._remove_btn.setEnabled(False)
        self._remove_btn.setStyleSheet(_BTN_RED)
        self._remove_btn.clicked.connect(self._remove_folder)
        btn_row.addWidget(self._remove_btn)

        btn_row.addStretch()

        # Rebuild only shown in standalone mode — when opened from
        # CatalogBuilderDialog the parent handles rebuilding.
        if self._standalone:
            self._rebuild_btn = QPushButton("Rebuild Registry")
            self._rebuild_btn.setFixedHeight(34)
            self._rebuild_btn.setEnabled(False)
            self._rebuild_btn.setStyleSheet(_BTN_MAUVE)
            self._rebuild_btn.clicked.connect(self._rebuild_registry)
            btn_row.addWidget(self._rebuild_btn)
        else:
            self._rebuild_btn = None

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(_BTN)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

        root.addWidget(self._sep())

        root.addWidget(self._lbl("Log"))
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(100)
        self._log.setStyleSheet(_LOG)
        root.addWidget(self._log)

    # ── Widget helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _sep() -> QWidget:
        w = QWidget(); w.setFixedHeight(1)
        w.setStyleSheet(f"background:{_BORDER};")
        return w

    @staticmethod
    def _lbl(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color:{_DIM}; font-size:11px; font-weight:bold;")
        return l

    def _log_line(self, text: str, color: str = _DIM):
        self._log.appendHtml(f'<span style="color:{color};">{text}</span>')
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_busy(self, busy: bool):
        if self._rebuild_btn:
            self._rebuild_btn.setEnabled(not busy and self._reg_mod is not None)
        if not busy:
            self._on_selection()

    # ── Load data ──────────────────────────────────────────────────────────

    def _load_data(self):
        # Load countries_data
        cd_mod = _load_module(_default_countries_data_py(), "_countries_data_tool")
        if cd_mod is None:
            self._log_line("Could not load countries_data.py", color=_RED)
        else:
            for item in cd_mod.data:
                country = item.get("COUNTRY", "")
                folder  = item.get("FOLDER_NAME", "")
                if country and folder:
                    self._country_to_folder[country] = folder
                    self._folder_to_country[folder]  = country

        # In standalone mode, load the registry module ourselves
        if self._standalone:
            reg_py = _default_registry_py()
            if reg_py.exists():
                self._reg_mod = _load_module(reg_py, "_material_catalog_tool")
                if self._reg_mod:
                    if self._rebuild_btn:
                        self._rebuild_btn.setEnabled(True)
                    self._log_line("Registry module loaded.", color=_DIM)
                else:
                    self._log_line("Could not load material_catalog.py", color=_ORANGE)
            else:
                self._log_line("material_catalog.py not found.", color=_ORANGE)

        self._populate_list()

    def _populate_list(self):
        self._model.clear()

        # ── Known countries from countries_data ────────────────────────────
        for country in sorted(
            self._country_to_folder.keys(), key=lambda x: (x != "INDIA", x)
        ):
            folder_name = self._country_to_folder[country]
            folder_path = self._db_root / folder_name
            self._model.appendRow(self._make_item(country, folder_name, folder_path))

        # ── Orphaned folders (on disk but not in countries_data) ───────────
        if self._db_root.exists():
            known_folders = set(self._country_to_folder.values())
            for child in sorted(self._db_root.iterdir()):
                if not child.is_dir():
                    continue
                if child.name not in known_folders:
                    item = QStandardItem()
                    item.setData(_ORPHAN, Qt.UserRole)          # flag as orphan
                    item.setData(child.name, Qt.UserRole + 1)   # folder name
                    n = len(list(child.iterdir()))
                    item.setText(
                        f"⚠  {child.name}  — orphaned"
                        + (f"  ({n} item(s))" if n else "  (empty)")
                    )
                    item.setForeground(QColor(_RED))
                    item.setEditable(False)
                    self._model.appendRow(item)

        # Summary
        total   = len(self._country_to_folder)
        present = sum(
            1 for f in self._country_to_folder.values()
            if (self._db_root / f).exists()
        )
        orphans = self._model.rowCount() - total
        msg = f"Loaded {total} countries — {present} folder(s) exist"
        if orphans:
            msg += f" — {orphans} orphaned folder(s) detected"
        self._log_line(msg, color=_DIM)

    def _make_item(self, country: str, folder_name: str,
                   folder_path: Path) -> QStandardItem:
        item = QStandardItem()
        item.setData(country, Qt.UserRole)
        item.setEditable(False)

        if folder_path.exists():
            children = list(folder_path.iterdir())
            if children:
                item.setText(f"✓  {country}  ({folder_name})")
                item.setForeground(QColor(_GREEN))
            else:
                item.setText(f"·  {country}  ({folder_name})  — empty")
                item.setForeground(QColor(_DIM))
        else:
            item.setText(f"·  {country}  ({folder_name})")
            item.setForeground(QColor(_DIM))

        return item

    # ── Search ─────────────────────────────────────────────────────────────

    def _on_search(self, text: str):
        self._proxy.setFilterFixedString(text)

    # ── Selection ──────────────────────────────────────────────────────────

    def _selected_items(self) -> list[tuple[str, bool]]:
        """Return list of (country_or_folder_name, is_orphan) for all selected rows."""
        result = []
        for index in self._list.selectionModel().selectedIndexes():
            kind = self._proxy.data(index, Qt.UserRole)
            if kind == _ORPHAN:
                result.append((self._proxy.data(index, Qt.UserRole + 1), True))
            elif kind:
                result.append((kind, False))
        return result

    def _on_selection(self):
        items = self._selected_items()
        if not items:
            self._add_btn.setEnabled(False)
            self._remove_btn.setEnabled(False)
            return

        can_add    = False
        can_remove = False
        for country, is_orphan in items:
            if is_orphan:
                can_remove = True
            else:
                folder_path = self._db_root / self._country_to_folder[country]
                if not folder_path.exists():
                    can_add = True
                else:
                    can_remove = True

        self._add_btn.setEnabled(can_add)
        self._remove_btn.setEnabled(can_remove)

    def _select_all_unregistered(self):
        """Select all visible items that don't have a folder yet (dim ones)."""
        sel_model = self._list.selectionModel()
        sel_model.clearSelection()
        for row in range(self._proxy.rowCount()):
            index  = self._proxy.index(row, 0)
            kind   = self._proxy.data(index, Qt.UserRole)
            if kind == _ORPHAN:
                continue
            country = kind
            folder_path = self._db_root / self._country_to_folder.get(country, "")
            if not folder_path.exists():
                from PySide6.QtCore import QItemSelectionModel
                sel_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)

    # ── Add folder (bulk) ──────────────────────────────────────────────────

    def _add_folder(self):
        to_add = [
            country for country, is_orphan in self._selected_items()
            if not is_orphan
            and not (self._db_root / self._country_to_folder[country]).exists()
        ]
        if not to_add:
            return

        created = []
        for country in to_add:
            folder_name = self._country_to_folder[country]
            folder_path = self._db_root / folder_name
            try:
                folder_path.mkdir(parents=True, exist_ok=False)
                created.append(folder_name)
                self._refresh_item(country)
            except Exception as exc:
                self._log_line(f"Failed to create {folder_name}: {exc}", color=_RED)

        if created:
            self._log_line(
                f"Created {len(created)} folder(s): {', '.join(created)}", color=_GREEN
            )
            self._on_selection()
            self.folders_changed.emit()
            if self._standalone and self._rebuild_btn:
                self._rebuild_btn.setEnabled(self._reg_mod is not None)
                self._log_line("Folders added — rebuild registry to update suggestions.", color=_DIM)

    # ── Remove folder (bulk) ───────────────────────────────────────────────

    def _remove_folder(self):
        items = self._selected_items()

        # Split into orphans and regular empty folders; block content folders
        orphans       = [name    for name, is_orphan in items if is_orphan]
        has_content   = []
        empty_folders = []

        for country, is_orphan in items:
            if is_orphan:
                continue
            folder_path = self._db_root / self._country_to_folder[country]
            if not folder_path.exists():
                continue
            if list(folder_path.iterdir()):
                has_content.append(country)
            else:
                empty_folders.append(country)

        # Warn about folders with content — never remove them
        if has_content:
            names = "\n".join(
                f"  • {self._country_to_folder[c]}  ({len(list((self._db_root / self._country_to_folder[c]).iterdir()))} item(s))"
                for c in has_content
            )
            QMessageBox.warning(
                self, "Some Folders Have Content",
                f"The following folder(s) contain files and will be skipped:\n\n"
                f"{names}\n\n"
                "Move or delete their contents manually first."
            )

        # Handle orphans individually (they may have content)
        for folder_name in orphans:
            self._remove_orphan(folder_name)

        # Bulk-confirm empty regular folders
        if empty_folders:
            names_str = "\n".join(
                f"  • {self._country_to_folder[c]}" for c in empty_folders
            )
            confirm = QMessageBox.question(
                self, "Remove Empty Folders",
                f"Remove {len(empty_folders)} empty folder(s)?\n\n{names_str}",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if confirm == QMessageBox.Yes:
                removed = []
                for country in empty_folders:
                    folder_name = self._country_to_folder[country]
                    folder_path = self._db_root / folder_name
                    try:
                        folder_path.rmdir()
                        removed.append(folder_name)
                        self._refresh_item(country)
                    except Exception as exc:
                        self._log_line(f"Failed to remove {folder_name}: {exc}", color=_RED)

                if removed:
                    self._log_line(
                        f"Removed {len(removed)} folder(s): {', '.join(removed)}", color=_ORANGE
                    )
                    self._on_selection()
                    self.folders_changed.emit()
                    if self._standalone and self._rebuild_btn:
                        self._rebuild_btn.setEnabled(self._reg_mod is not None)
                        self._log_line("Folders removed — rebuild registry to update suggestions.", color=_DIM)

    def _remove_orphan(self, folder_name: str):
        folder_path = self._db_root / folder_name
        children    = list(folder_path.iterdir()) if folder_path.exists() else []

        msg = (
            f"This folder is not mapped to any country in the country list\n"
            f"and will never appear in material suggestions.\n\n"
            f"  material_database/{folder_name}\n"
        )
        if children:
            msg += (
                f"\n  Contains {len(children)} item(s) — removing will delete all content.\n"
                f"  This action cannot be undone."
            )
        else:
            msg += "\n  The folder is empty."

        confirm = QMessageBox.question(
            self, "Remove Orphaned Folder", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            if children:
                import shutil
                shutil.rmtree(folder_path)
            else:
                folder_path.rmdir()
            self._log_line(
                f"Removed orphaned folder: material_database/{folder_name}", color=_ORANGE
            )
        except Exception as exc:
            self._log_line(f"Failed to remove orphaned folder: {exc}", color=_RED)
            return

        # Remove from list model
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if (item.data(Qt.UserRole) == _ORPHAN
                    and item.data(Qt.UserRole + 1) == folder_name):
                self._model.removeRow(row)
                break

        self._on_selection()
        self.folders_changed.emit()
        if children:
            self.rebuild_needed.emit()
            if self._standalone and self._rebuild_btn:
                self._rebuild_btn.setEnabled(self._reg_mod is not None)
                self._log_line(
                    "Orphan with content removed — rebuild registry to clear stale entries.",
                    color=_YELLOW,
                )

    # ── Refresh single list item ────────────────────────────────────────────

    def _refresh_item(self, country: str):
        folder_name = self._country_to_folder[country]
        folder_path = self._db_root / folder_name

        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item.data(Qt.UserRole) == country:
                new = self._make_item(country, folder_name, folder_path)
                item.setText(new.text())
                item.setForeground(new.foreground())
                break

    # ── Rebuild registry (standalone only) ────────────────────────────────

    def _rebuild_registry(self):
        if self._reg_mod is None:
            QMessageBox.warning(self, "Not Ready", "Registry module not loaded.")
            return

        self._log_line("--- Rebuilding registry ---", color=_DIM)
        self._set_busy(True)
        self._rebuild_btn.setText("Rebuilding…")

        self._worker = _RebuildWorker(self._reg_mod)
        self._worker.finished.connect(self._on_rebuild_done)
        self._worker.error.connect(self._on_rebuild_error)
        self._worker.start()

    def _on_rebuild_done(self, manifest: dict):
        self._rebuild_btn.setText("Rebuild Registry")
        self._set_busy(False)
        self._worker = None
        meta   = manifest.get("_meta", {})
        total  = meta.get("total_files", "?")
        ok     = meta.get("ok", "?")
        failed = meta.get("failed", 0)
        self._log_line(
            f"Registry rebuilt: {total} file(s), {ok} OK, {failed} failed",
            color=_GREEN if not failed else _YELLOW,
        )

    def _on_rebuild_error(self, msg: str):
        self._rebuild_btn.setText("Rebuild Registry")
        self._set_busy(False)
        self._worker = None
        self._log_line(f"Rebuild failed: {msg}", color=_RED)
        QMessageBox.critical(self, "Rebuild Failed", msg)


