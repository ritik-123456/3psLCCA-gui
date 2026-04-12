"""
devtools/custom_db_viewer_gui.py

Custom DB Viewer — browse all user-created custom material databases (SOR).
Reads directly from data/user.db via sqlite3.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# data/user.db is two levels above devtools/
_DB_PATH = Path(__file__).parent.parent / "data" / "user.db"

_COLUMNS = [
    ("name",                         "Name"),
    ("unit",                         "Unit"),
    ("rate",                         "Rate"),
    ("rate_src",                     "Rate Source"),
    ("carbon_emission",              "Emission Factor"),
    ("carbon_emission_units_den",    "Emission Unit"),
    ("carbon_emission_src",          "Emission Source"),
    ("conversion_factor",            "Conv. Factor"),
    ("scrap_rate",                   "Scrap Rate"),
    ("post_demolition_recovery_pct", "Recovery %"),
    ("recycleable",                  "Recyclability"),
    ("material_type",                "Type"),
    ("grade",                        "Grade"),
    ("created_at",                   "Created"),
    ("updated_at",                   "Updated"),
]

_BG      = "#1e1e2e"
_BG2     = "#252535"
_BG3     = "#313244"
_TEXT    = "#cdd6f4"
_DIM     = "#585b70"
_BORDER  = "#2a2a3e"
_GREEN   = "#a6e3a1"


class CustomDbViewerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom DB Viewer (SOR)")
        self.setMinimumSize(1100, 560)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setStyleSheet(f"QDialog {{ background:{_BG}; color:{_TEXT}; }}")
        self._build_ui()
        self._load_db_names()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_table(), stretch=1)
        root.addWidget(self._build_footer())

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"background:{_BG2}; border-bottom:1px solid {_BORDER};"
        )
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(10)

        lbl = QLabel("Database:")
        lbl.setStyleSheet(f"color:{_DIM}; font-size:12px;")
        hl.addWidget(lbl)

        self._db_combo = QComboBox()
        self._db_combo.setMinimumWidth(220)
        self._db_combo.setFixedHeight(30)
        self._db_combo.setStyleSheet(
            f"QComboBox {{ background:{_BG3}; color:{_TEXT}; border:1px solid {_BORDER};"
            f" border-radius:4px; padding:0 8px; font-size:12px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
            f"QComboBox QAbstractItemView {{ background:{_BG3}; color:{_TEXT}; "
            f"selection-background-color:#45475a; }}"
        )
        self._db_combo.currentIndexChanged.connect(self._on_db_changed)
        hl.addWidget(self._db_combo)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(f"color:{_DIM}; font-size:11px;")
        hl.addWidget(self._count_lbl)

        hl.addStretch()

        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_TEXT}; border:1px solid {_BORDER};"
            f" border-radius:4px; padding:0 12px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#45475a; }}"
        )
        refresh_btn.clicked.connect(self._refresh)
        hl.addWidget(refresh_btn)

        explore_btn = QPushButton("📂  Explore Location")
        explore_btn.setFixedHeight(30)
        explore_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_TEXT}; border:1px solid {_BORDER};"
            f" border-radius:4px; padding:0 12px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#45475a; }}"
        )
        explore_btn.clicked.connect(self._explore_location)
        hl.addWidget(explore_btn)

        self._del_btn = QPushButton("🗑  Delete Selected")
        self._del_btn.setFixedHeight(30)
        self._del_btn.setEnabled(False)
        self._del_btn.setStyleSheet(
            f"QPushButton {{ background:#3d1a1a; color:#f38ba8; border:1px solid #5a2020;"
            f" border-radius:4px; padding:0 12px; font-size:11px; }}"
            f"QPushButton:hover:enabled {{ background:#5a2020; }}"
            f"QPushButton:disabled {{ background:{_BG3}; color:{_DIM}; border-color:{_BORDER}; }}"
        )
        self._del_btn.clicked.connect(self._delete_selected)
        hl.addWidget(self._del_btn)

        return bar

    def _build_table(self) -> QWidget:
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels([h for _, h in _COLUMNS])
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        # Name column stretches
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.setStyleSheet(
            f"QTableWidget {{ background:{_BG}; color:{_TEXT}; border:none;"
            f" gridline-color:{_BORDER}; font-size:11px; }}"
            f"QTableWidget::item {{ padding:4px 8px; }}"
            f"QTableWidget::item:selected {{ background:#313244; color:{_TEXT}; }}"
            f"QTableWidget::item:alternate {{ background:{_BG2}; }}"
            f"QHeaderView::section {{ background:{_BG2}; color:{_DIM}; border:none;"
            f" border-right:1px solid {_BORDER}; border-bottom:1px solid {_BORDER};"
            f" padding:4px 8px; font-size:10px; font-weight:bold; }}"
        )
        f = QFont("Consolas", 10)
        f.setStyleHint(QFont.Monospace)
        self._table.setFont(f)
        return self._table

    def _build_footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            f"background:{_BG2}; border-top:1px solid {_BORDER};"
        )
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(16, 0, 16, 0)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color:{_DIM}; font-size:11px;")
        hl.addWidget(self._status_lbl, stretch=1)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(30)
        close_btn.setFixedWidth(80)
        close_btn.setStyleSheet(
            f"QPushButton {{ background:{_BG3}; color:{_TEXT}; border:1px solid {_BORDER};"
            f" border-radius:4px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#45475a; }}"
        )
        close_btn.clicked.connect(self.accept)
        hl.addWidget(close_btn)

        return bar

    # ── Data loading ──────────────────────────────────────────────────────

    def _connect(self):
        if not _DB_PATH.exists():
            return None
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_db_names(self):
        self._db_combo.blockSignals(True)
        self._db_combo.clear()
        conn = self._connect()
        if conn is None:
            self._set_status("user.db not found — no custom databases yet.")
            self._db_combo.blockSignals(False)
            return
        try:
            rows = conn.execute(
                "SELECT DISTINCT db_name FROM custom_materials ORDER BY db_name"
            ).fetchall()
            for r in rows:
                self._db_combo.addItem(r["db_name"], r["db_name"])
        except Exception as e:
            self._set_status(f"Error reading databases: {e}")
        finally:
            conn.close()
        self._db_combo.blockSignals(False)

        if self._db_combo.count():
            self._db_combo.setCurrentIndex(0)
            self._load_items(self._db_combo.currentData())
        else:
            self._set_status("No custom databases found.")

    def _load_items(self, db_name: str):
        self._table.setRowCount(0)
        if not db_name:
            return

        conn = self._connect()
        if conn is None:
            self._set_status("user.db not found.")
            return

        cols = ", ".join(col for col, _ in _COLUMNS)
        try:
            rows = conn.execute(
                f"SELECT {cols} FROM custom_materials WHERE db_name = ? ORDER BY name",
                (db_name,),
            ).fetchall()
        except Exception as e:
            self._set_status(f"Error: {e}")
            conn.close()
            return
        finally:
            conn.close()

        self._table.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx, (col, _) in enumerate(_COLUMNS):
                val = row[col]
                text = "" if val is None else str(val)
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                # Dim "not_available" values
                if text in ("not_available", ""):
                    item.setForeground(QColor(_DIM))
                self._table.setItem(r_idx, c_idx, item)

        self._count_lbl.setText(f"{len(rows)} item(s)")
        self._set_status(
            f"Loaded {len(rows)} material(s) from '{db_name}'  —  {_DB_PATH}"
        )

    # ── Slots ─────────────────────────────────────────────────────────────

    def _explore_location(self):
        import subprocess, sys
        if _DB_PATH.exists():
            target = _DB_PATH
        else:
            target = _DB_PATH.parent
            target.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            # Select the file itself in Explorer if it exists, else open the folder
            if _DB_PATH.exists():
                subprocess.run(["explorer", "/select,", str(_DB_PATH)])
            else:
                subprocess.run(["explorer", str(target)])
        else:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _on_db_changed(self, _idx: int):
        self._load_items(self._db_combo.currentData())

    def _on_selection_changed(self):
        self._del_btn.setEnabled(bool(self._table.selectedItems()))

    def _show_context_menu(self, pos):
        rows = self._selected_names()
        if not rows:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{_BG3}; color:{_TEXT}; border:1px solid {_BORDER}; }}"
            f"QMenu::item:selected {{ background:#45475a; }}"
        )
        act = menu.addAction(f"🗑  Delete {len(rows)} selected item(s)")
        act.triggered.connect(self._delete_selected)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _selected_names(self) -> list[str]:
        """Return material names for all selected rows (deduplicated, preserving order)."""
        seen, names = set(), []
        for idx in self._table.selectionModel().selectedRows():
            item = self._table.item(idx.row(), 0)  # column 0 = name
            if item and item.text() not in seen:
                seen.add(item.text())
                names.append(item.text())
        return names

    def _delete_selected(self):
        db_name = self._db_combo.currentData()
        names = self._selected_names()
        if not db_name or not names:
            return

        reply = QMessageBox.warning(
            self,
            "Confirm Delete",
            f"Delete {len(names)} item(s) from '{db_name}'?\n\n"
            + "\n".join(f"  • {n}" for n in names[:10])
            + ("\n  …" if len(names) > 10 else "")
            + "\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return

        conn = self._connect()
        if conn is None:
            self._set_status("user.db not found.")
            return
        try:
            with conn:
                conn.executemany(
                    "DELETE FROM custom_materials WHERE db_name=? AND name=?",
                    [(db_name, n) for n in names],
                )
        except Exception as e:
            QMessageBox.critical(self, "Delete Failed", str(e))
            return
        finally:
            conn.close()

        self._set_status(f"Deleted {len(names)} item(s) from '{db_name}'.")
        self._load_items(db_name)
        # Remove db from combo if now empty
        self._refresh()

    def _refresh(self):
        current = self._db_combo.currentData()
        self._load_db_names()
        # Re-select the previously selected database if it still exists
        if current:
            idx = self._db_combo.findData(current)
            if idx >= 0:
                self._db_combo.setCurrentIndex(idx)
                self._load_items(current)

    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)


