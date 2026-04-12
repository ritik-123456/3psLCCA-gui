"""
devtools/wpi_tool.py

WPI Database Tool — create, edit, verify, and rehash wpi_db.json entries.

Workflow:
  1. Open wpi_db.json (auto-loaded from default path) or browse a folder
  2. Select an entry to view its data block
  3. New Entry → simple name + year dialog → skeleton with 0.0 values
  4. Edit the JSON in the viewer → Apply → schema check with suggestions
  5. Rehash All → Save
"""

import hashlib
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_DEFAULT_WPI_PATH = Path(__file__).parent.parent / "data" / "wpi_db.json"

ICON_OK       = "✓"
ICON_MISMATCH = "⚠"
ICON_MISSING  = "·"
ICON_EDITING  = "●"

VEHICLES  = ["small_cars", "big_cars", "two_wheelers", "o_buses",
             "d_buses", "lcv", "hcv", "mcv"]

COST_KEYS = [
    "petrol", "diesel", "engine_oil", "other_oil", "grease",
    "property_damage", "tyre_cost", "spare_parts", "fixed_depreciation",
    "commodity_holding_cost",
    "passenger_cost", "crew_cost",
    "fatal", "major", "minor",
    "vot_cost",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _compute_hash(data: dict) -> str:
    """Must match gui/components/utils/wpi_hash.py → compute_hash exactly."""
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()


def _hash_status(entry: dict) -> str:
    stored = entry.get("metadata", {}).get("hash", "")
    if not stored:
        return "missing"
    return "ok" if _compute_hash(entry.get("data", {})) == stored else "mismatch"


def _make_skeleton(name: str, year: int) -> dict:
    """Create a new entry with all data values set to 0.0."""
    data = {v: {k: 0.0 for k in COST_KEYS} for v in VEHICLES}
    return {
        "metadata": {
            "id":        f"wpi_custom_{year}",
            "name":      name,
            "year":      year,
            "is_custom": True,
            "remark":    f"Custom WPI entry for {year}",
            "hash":      "",
        },
        "data": data,
    }


def _validate_schema(data: dict) -> tuple[list[str], list[str]]:
    """
    Validate a data block against the flat vehicle-grouped schema.
    Returns (errors, warnings).
      errors   — missing required keys (blocks hashing)
      warnings — present but zero values (suggest updating)
    """
    errors: list[str] = []
    warnings: list[str] = []

    for vk in VEHICLES:
        if vk not in data:
            errors.append(f"Missing vehicle: '{vk}'")
            continue
        block = data[vk]
        for ck in COST_KEYS:
            if ck not in block:
                errors.append(f"Missing key: {vk}.{ck}")
            elif block[ck] == 0:
                warnings.append(f"{vk}.{ck} is 0")

    return errors, warnings


# ── Simple "New Entry" dialog ─────────────────────────────────────────────────

class _NewEntryDialog(QDialog):
    def __init__(self, existing_years: set[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("New WPI Entry")
        self.setFixedWidth(340)
        self._existing_years = existing_years
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g.  2026  or  Custom 2026")
        form.addRow("Name *", self._name)

        self._year = QSpinBox()
        self._year.setRange(2000, 2100)
        self._year.setValue(2026)
        form.addRow("Year *", self._year)

        layout.addLayout(form)

        self._warning = QLabel("")
        self._warning.setStyleSheet("color:#fab387; font-size:11px;")
        self._warning.setWordWrap(True)
        self._warning.hide()
        layout.addWidget(self._warning)

        note = QLabel(
            "A skeleton entry with all values set to <b>0.0</b> will be created.\n"
            "Edit the values in the viewer and click Apply."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(note)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Create")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        name = self._name.text().strip()
        year = self._year.value()

        if not name:
            self._warning.setText("Name is required.")
            self._warning.show()
            return

        if year in self._existing_years:
            self._warning.setText(
                f"Year {year} already exists in this database.\n"
                "Choose a different year."
            )
            self._warning.show()
            return

        self.accept()

    def get_name(self) -> str:
        return self._name.text().strip()

    def get_year(self) -> int:
        return self._year.value()


# ── Schema suggestions dialog ─────────────────────────────────────────────────

class _SuggestionsDialog(QDialog):
    """Shows schema errors and warnings after Apply. User can proceed or go back."""

    def __init__(self, errors: list[str], warnings: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schema Check")
        self.setMinimumWidth(420)
        self._build_ui(errors, warnings)

    def _build_ui(self, errors: list[str], warnings: list[str]):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        if errors:
            err_hdr = QLabel(f"❌  {len(errors)} error(s) — required fields missing:")
            err_hdr.setStyleSheet("color:#f38ba8; font-weight:bold;")
            layout.addWidget(err_hdr)

            scroll = QScrollArea()
            scroll.setMaximumHeight(160)
            scroll.setWidgetResizable(True)
            inner = QWidget()
            vbox = QVBoxLayout(inner)
            vbox.setContentsMargins(6, 4, 6, 4)
            vbox.setSpacing(2)
            for e in errors:
                lbl = QLabel(f"  • {e}")
                lbl.setStyleSheet("color:#f38ba8; font-size:11px; font-family:Consolas;")
                vbox.addWidget(lbl)
            vbox.addStretch()
            scroll.setWidget(inner)
            layout.addWidget(scroll)

        if warnings:
            warn_hdr = QLabel(f"⚠  {len(warnings)} warning(s) — values are still 0:")
            warn_hdr.setStyleSheet("color:#f9e2af; font-weight:bold;")
            layout.addWidget(warn_hdr)

            scroll2 = QScrollArea()
            scroll2.setMaximumHeight(160)
            scroll2.setWidgetResizable(True)
            inner2 = QWidget()
            vbox2 = QVBoxLayout(inner2)
            vbox2.setContentsMargins(6, 4, 6, 4)
            vbox2.setSpacing(2)
            for w in warnings:
                lbl = QLabel(f"  • {w}")
                lbl.setStyleSheet("color:#f9e2af; font-size:11px; font-family:Consolas;")
                vbox2.addWidget(lbl)
            vbox2.addStretch()
            scroll2.setWidget(inner2)
            layout.addWidget(scroll2)

        if not errors and not warnings:
            ok = QLabel("✓  Schema looks good — all fields present and non-zero.")
            ok.setStyleSheet("color:#a6e3a1;")
            layout.addWidget(ok)

        # Buttons
        btn_row = QHBoxLayout()
        if errors:
            back = QPushButton("Go Back and Fix")
            back.setFixedHeight(32)
            back.clicked.connect(self.reject)
            btn_row.addWidget(back)

        proceed = QPushButton("Save Anyway" if (errors or warnings) else "OK")
        proceed.setFixedHeight(32)
        proceed.setDefault(True)
        if errors:
            proceed.setStyleSheet(
                "QPushButton { background:#f38ba8; color:#1e1e2e; border:none;"
                " border-radius:4px; font-weight:bold; }"
                "QPushButton:hover { background:#f7a8b8; }"
            )
        proceed.clicked.connect(self.accept)
        btn_row.addWidget(proceed)
        layout.addLayout(btn_row)


# ── Main WPI dialog ────────────────────────────────────────────────────────────

class WpiDatabaseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("WPI Database Tool")
        self.setMinimumSize(940, 560)

        self._db_path: Path | None = None
        self._entries: list[dict] = []
        self._db_meta: dict = {}
        self._dirty    = False
        self._editing  = False   # viewer is in edit mode

        self._build_ui()
        self._try_load_default()

    # ── UI build ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_viewer_panel())
        splitter.setSizes([220, 700])
        root.addWidget(splitter, stretch=1)

        root.addWidget(self._build_status_bar())

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#252535; border-bottom:1px solid #333;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        layout.addWidget(self._tbtn("📂  Open File",     self._open_file))
        layout.addWidget(self._tbtn("📁  Browse Folder", self._browse_folder))
        layout.addWidget(self._sep())

        self._path_label = QLabel("No file loaded")
        self._path_label.setStyleSheet("color:#585b70; font-size:11px;")
        layout.addWidget(self._path_label, stretch=1)

        layout.addWidget(self._sep())

        self._btn_new = self._tbtn("➕  New Entry", self._create_new)
        self._btn_new.setEnabled(False)
        layout.addWidget(self._btn_new)

        self._btn_rehash = self._tbtn("🔄  Rehash All", self._rehash_all)
        self._btn_rehash.setEnabled(False)
        layout.addWidget(self._btn_rehash)

        self._btn_save = QPushButton("💾  Save")
        self._btn_save.setFixedHeight(30)
        self._btn_save.setEnabled(False)
        self._btn_save.setStyleSheet(
            "QPushButton { background:#89b4fa; color:#1e1e2e; border:1px solid #444;"
            " border-radius:4px; padding:0 10px; font-weight:bold; }"
            "QPushButton:hover:enabled { background:#b4d0f7; }"
            "QPushButton:disabled { background:#313244; color:#555; border-color:#333; }"
        )
        self._btn_save.clicked.connect(self._save_file)
        layout.addWidget(self._btn_save)
        return bar

    def _build_list_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(180)
        panel.setMaximumWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hdr = QLabel("  ENTRIES")
        hdr.setFixedHeight(22)
        hdr.setStyleSheet(
            "background:#252535; color:#585b70; font-size:10px;"
            " font-weight:bold; border-bottom:1px solid #2a2a3e;"
        )
        layout.addWidget(hdr)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background:#1e1e2e; color:#cdd6f4; border:none; font-size:12px; }"
            "QListWidget::item { padding:3px 0; }"
            "QListWidget::item:selected { background:#313244; }"
            "QListWidget::item:hover { background:#252535; }"
        )
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list, stretch=1)

        self._btn_delete = QPushButton("🗑  Delete Entry")
        self._btn_delete.setFixedHeight(28)
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet(
            "QPushButton { background:#313244; color:#f38ba8; border:none;"
            " border-top:1px solid #333; font-size:11px; }"
            "QPushButton:hover:enabled { background:#45475a; }"
            "QPushButton:disabled { color:#555; }"
        )
        self._btn_delete.clicked.connect(self._delete_entry)
        layout.addWidget(self._btn_delete)
        return panel

    def _build_viewer_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar with title + Edit/Apply/Revert buttons
        hdr = QWidget()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet("background:#252535; border-bottom:1px solid #333;")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(10, 0, 8, 0)
        hdr_layout.setSpacing(6)

        self._viewer_title = QLabel("No entry selected")
        self._viewer_title.setStyleSheet("color:#888; font-size:12px;")
        hdr_layout.addWidget(self._viewer_title, stretch=1)

        self._hash_label = QLabel("")
        self._hash_label.setStyleSheet("font-size:11px;")
        hdr_layout.addWidget(self._hash_label)

        # self._btn_edit   = self._small_btn("Edit",   self._start_edit)
        self._btn_edit   = self._small_btn("✏️",   self._start_edit)
        self._btn_revert = self._small_btn("Revert", self._revert_edit)
        self._btn_apply  = self._small_btn("Apply",  self._apply_edit)
        for b in (self._btn_edit, self._btn_revert, self._btn_apply):
            b.setEnabled(False)
            hdr_layout.addWidget(b)

        layout.addWidget(hdr)

        self._viewer = QPlainTextEdit()
        self._viewer.setReadOnly(True)
        vf = QFont("Consolas", 10)
        vf.setStyleHint(QFont.Monospace)
        self._viewer.setFont(vf)
        self._viewer.setStyleSheet(
            "QPlainTextEdit { background:#1a1a2e; color:#cdd6f4; border:none; }"
        )
        layout.addWidget(self._viewer)
        return panel

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet("background:#1e1e2e; border-top:1px solid #333;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        self._status = QLabel("")
        self._status.setStyleSheet("color:#585b70; font-size:11px;")
        layout.addWidget(self._status)
        return bar

    # ── Widget helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _tbtn(label: str, slot) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(30)
        btn.setStyleSheet(
            "QPushButton { background:#313244; color:#cdd6f4; border:1px solid #444;"
            " border-radius:4px; padding:0 10px; }"
            "QPushButton:hover:enabled { background:#45475a; }"
            "QPushButton:disabled { color:#555; border-color:#333; background:#252535; }"
        )
        btn.clicked.connect(slot)
        return btn

    @staticmethod
    def _small_btn(label: str, slot) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(26)
        btn.setFixedWidth(64)
        btn.setStyleSheet(
            "QPushButton { background:#313244; color:#cdd6f4; border:1px solid #444;"
            " border-radius:3px; font-size:11px; }"
            "QPushButton:hover:enabled { background:#45475a; }"
            "QPushButton:disabled { color:#555; border-color:#333; background:#252535; }"
        )
        btn.clicked.connect(slot)
        return btn

    @staticmethod
    def _sep() -> QLabel:
        s = QLabel("|")
        s.setStyleSheet("color:#444; padding:0 2px;")
        return s

    # ── Load / Save ────────────────────────────────────────────────────────────

    def _try_load_default(self):
        if _DEFAULT_WPI_PATH.exists():
            self._load(_DEFAULT_WPI_PATH)

    def _open_file(self):
        start = str(self._db_path.parent if self._db_path else _DEFAULT_WPI_PATH.parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Open wpi_db.json", start,
            "WPI Database (wpi_db.json);;JSON Files (*.json)",
        )
        if path:
            self._load(Path(path))

    def _browse_folder(self):
        start = str(self._db_path.parent if self._db_path else _DEFAULT_WPI_PATH.parent)
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder Containing wpi_db.json", start
        )
        if not folder:
            return
        candidate = Path(folder) / "wpi_db.json"
        if candidate.exists():
            self._load(candidate)
        else:
            resp = QMessageBox.question(
                self, "Not Found",
                f"wpi_db.json not found in:\n{folder}\n\nCreate a new empty one there?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if resp == QMessageBox.Yes:
                self._create_empty_db(candidate)

    def _create_empty_db(self, path: Path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "entries": []}, f, indent=4)
            self._load(path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not create file:\n{e}")

    def _load(self, path: Path):
        try:
            with open(path, encoding="utf-8") as f:
                db = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Load Failed", f"Could not read file:\n{e}")
            return

        self._db_path = path
        self._entries = db.get("entries", [])
        self._db_meta = {k: v for k, v in db.items() if k != "entries"}
        self._dirty   = False
        self._editing = False

        self._path_label.setText(str(path))
        self._btn_new.setEnabled(True)
        self._btn_rehash.setEnabled(True)
        self._btn_save.setEnabled(False)
        self._refresh_list()
        self._update_status()

    def _save_file(self):
        if not self._db_path:
            return
        try:
            db = {**self._db_meta, "entries": self._entries}
            with open(self._db_path, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=4)
            self._dirty = False
            self._btn_save.setEnabled(False)
            self._set_status(f"Saved → {self._db_path.name}")
        except Exception as e:
            QMessageBox.warning(self, "Save Failed", f"Could not write file:\n{e}")

    # ── Entry list ─────────────────────────────────────────────────────────────

    def _existing_years(self) -> set[int]:
        return {e.get("metadata", {}).get("year") for e in self._entries}

    def _refresh_list(self):
        self._list.blockSignals(True)
        cur = self._list.currentRow()
        self._list.clear()

        for entry in self._entries:
            meta   = entry.get("metadata", {})
            name   = meta.get("name", "?")
            custom = meta.get("is_custom", False)
            status = _hash_status(entry)

            if status == "ok":
                icon, color = ICON_OK, "#a6e3a1"
            elif status == "mismatch":
                icon, color = ICON_MISMATCH, "#fab387"
            else:
                icon, color = ICON_MISSING, "#585b70"

            tag  = " [custom]" if custom else ""
            item = QListWidgetItem(f"  {icon} {name}{tag}")
            item.setForeground(QColor(color))
            self._list.addItem(item)

        self._list.blockSignals(False)
        if 0 <= cur < self._list.count():
            self._list.setCurrentRow(cur)
        elif self._list.count():
            self._list.setCurrentRow(0)

    def _on_row_changed(self, row: int):
        # If switching away while editing, discard silently
        if self._editing:
            self._stop_edit()

        has = 0 <= row < len(self._entries)
        self._btn_delete.setEnabled(has)

        if not has:
            self._viewer.clear()
            self._viewer.setReadOnly(True)
            self._viewer_title.setText("No entry selected")
            self._hash_label.setText("")
            for b in (self._btn_edit, self._btn_revert, self._btn_apply):
                b.setEnabled(False)
            return

        self._show_entry(row)

    def _show_entry(self, row: int):
        entry  = self._entries[row]
        meta   = entry.get("metadata", {})
        status = _hash_status(entry)

        self._viewer_title.setText(
            f"{meta.get('name', '?')}  "
            f"[id: {meta.get('id', '?')}]  "
            f"[year: {meta.get('year', '?')}]"
            + ("  [custom]" if meta.get("is_custom") else "")
        )

        if status == "ok":
            self._hash_label.setText("✓ hash OK")
            self._hash_label.setStyleSheet("color:#a6e3a1; font-size:11px;")
        elif status == "mismatch":
            self._hash_label.setText("⚠ hash mismatch")
            self._hash_label.setStyleSheet("color:#fab387; font-size:11px;")
        else:
            self._hash_label.setText("· no hash")
            self._hash_label.setStyleSheet("color:#585b70; font-size:11px;")

        self._viewer.setPlainText(
            json.dumps(entry.get("data", {}), indent=4, ensure_ascii=False)
        )
        self._viewer.setReadOnly(True)
        self._viewer.setStyleSheet(
            "QPlainTextEdit { background:#1a1a2e; color:#cdd6f4; border:none; }"
        )
        self._btn_edit.setEnabled(True)
        self._btn_revert.setEnabled(False)
        self._btn_apply.setEnabled(False)
        self._editing = False

    # ── Edit / Apply / Revert ──────────────────────────────────────────────────

    def _start_edit(self):
        self._viewer.setReadOnly(False)
        self._viewer.setStyleSheet(
            "QPlainTextEdit { background:#1a1a2e; color:#cdd6f4; border:none;"
            " border-left:2px solid #f9e2af; }"
        )
        self._btn_edit.setEnabled(False)
        self._btn_revert.setEnabled(True)
        self._btn_apply.setEnabled(True)
        self._editing = True

        row = self._list.currentRow()
        name = self._entries[row].get("metadata", {}).get("name", "?")
        self._viewer_title.setText(f"{name}  [editing…]")

    def _stop_edit(self):
        self._viewer.setReadOnly(True)
        self._viewer.setStyleSheet(
            "QPlainTextEdit { background:#1a1a2e; color:#cdd6f4; border:none; }"
        )
        self._editing = False

    def _revert_edit(self):
        row = self._list.currentRow()
        if 0 <= row < len(self._entries):
            self._show_entry(row)

    def _apply_edit(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._entries):
            return

        # Parse JSON
        try:
            new_data = json.loads(self._viewer.toPlainText())
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", f"Fix the error before applying:\n\n{e}")
            return

        if not isinstance(new_data, dict):
            QMessageBox.warning(self, "Invalid JSON",
                                "Root value must be a JSON object {…}.")
            return

        # Schema check
        errors, warnings = _validate_schema(new_data)

        if errors or warnings:
            dlg = _SuggestionsDialog(errors, warnings, self)
            if dlg.exec() != QDialog.Accepted:
                return   # user chose "Go Back and Fix"

        # Commit
        self._entries[row]["data"] = new_data
        self._entries[row]["metadata"]["hash"] = ""   # stale until rehash
        self._dirty = True
        self._btn_save.setEnabled(True)
        self._stop_edit()
        self._refresh_list()
        self._list.setCurrentRow(row)
        self._show_entry(row)
        self._update_status()
        self._set_status(
            f"Data updated for '{self._entries[row]['metadata'].get('name', '?')}' "
            "— hash cleared, click Rehash All then Save."
        )

    # ── Actions ────────────────────────────────────────────────────────────────

    def _create_new(self):
        dlg = _NewEntryDialog(self._existing_years(), self)
        if dlg.exec() != QDialog.Accepted:
            return

        entry = _make_skeleton(dlg.get_name(), dlg.get_year())
        self._entries.append(entry)
        self._dirty = True
        self._btn_save.setEnabled(True)
        self._refresh_list()
        new_row = len(self._entries) - 1
        self._list.setCurrentRow(new_row)
        self._show_entry(new_row)
        # Auto-start edit so user can fill in values immediately
        self._start_edit()
        self._update_status()
        self._set_status(
            f"Created '{entry['metadata']['name']}' with 0.0 values — "
            "edit the JSON and click Apply."
        )

    def _rehash_all(self):
        if not self._entries:
            return
        updated = unchanged = 0
        for entry in self._entries:
            new_hash = _compute_hash(entry.get("data", {}))
            if new_hash != entry.get("metadata", {}).get("hash", ""):
                entry["metadata"]["hash"] = new_hash
                updated += 1
            else:
                unchanged += 1

        self._dirty = True
        self._btn_save.setEnabled(True)
        self._refresh_list()
        row = self._list.currentRow()
        if 0 <= row < len(self._entries):
            self._show_entry(row)
        self._set_status(
            f"Rehashed: {updated} updated, {unchanged} already correct — click Save to write."
        )

    def _delete_entry(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._entries):
            return
        name = self._entries[row].get("metadata", {}).get("name", "this entry")
        resp = QMessageBox.question(
            self, "Delete Entry",
            f"Delete '{name}'?  This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        self._entries.pop(row)
        self._dirty = True
        self._editing = False
        self._btn_save.setEnabled(True)
        self._refresh_list()
        self._update_status()

    # ── Status ─────────────────────────────────────────────────────────────────

    def _update_status(self):
        total    = len(self._entries)
        ok       = sum(1 for e in self._entries if _hash_status(e) == "ok")
        mismatch = sum(1 for e in self._entries if _hash_status(e) == "mismatch")
        missing  = sum(1 for e in self._entries if _hash_status(e) == "missing")
        parts = [f"{total} entries"]
        if ok:       parts.append(f"{ok} OK")
        if mismatch: parts.append(f"{mismatch} mismatch")
        if missing:  parts.append(f"{missing} no hash")
        self._set_status("  •  ".join(parts))

    def _set_status(self, msg: str):
        self._status.setText(msg)


