"""
devtools/devtools_window.py

3psLCCA Developer Tools — focused inspection and repair tool.

Purpose:
  Something broke. Open the project, find the bad chunk,
  fix it, export a new .3psLCCA, reshare.

Workflow:
  1. Open  — project folder or .3psLCCA archive
  2. Inspect — view chunks / metadata / blobs; run integrity check
  3. Fix   — edit chunk JSON directly in the tool, validate, save
  4. Share — create a binary .3psLCCA (with or without blobs)
"""

import hashlib
import json
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from lcca_codec import decode_bytes, decode_lcca, encode_dict, encode_json_str, is_binary
from wpi_tool import WpiDatabaseDialog

LCCA_EXT = ".lcca"
META_FILES = ("version.json", "manifest.json", "checkpoint_meta.json", "blob_manifest.json")

# Status icons shown in the chunk list
ICON_CLEAN    = "✓"
ICON_MISMATCH = "⚠"
ICON_CORRUPT  = "✕"
ICON_MODIFIED = "●"


class DevToolsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3psLCCA Developer Tools")
        self.setMinimumSize(960, 600)

        # ── Source state ──────────────────────────────────────────────────────
        self._source_label: str = ""
        self._temp_dir: str | None = None

        # chunk name → original raw bytes (as loaded)
        self._chunk_raw: dict[str, bytes] = {}
        # chunk name → modified dict (only present if user saved edits)
        self._chunk_modified: dict[str, dict] = {}
        # chunk name → integrity status: "clean" | "mismatch" | "corrupt" | "unknown"
        self._chunk_status: dict[str, str] = {}

        # metadata file name → raw text
        self._meta_raw: dict[str, str] = {}
        # blob name → Path
        self._blob_paths: dict[str, Path] = {}

        # currently viewed item
        self._active_kind: str = ""   # "chunk" | "meta" | "blob"
        self._active_name: str = ""
        self._editing: bool = False

        self._build_ui()
        self._set_status("Open a project folder or .3psLCCA archive to begin.")

    # ── UI build ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([260, 700])
        root.addWidget(splitter, stretch=1)

        root.addWidget(self._build_bottom_bar())

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet("background:#1e1e2e; border-bottom:1px solid #333;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        title = QLabel("3psLCCA Developer Tools")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#cdd6f4;")
        layout.addWidget(title)
        layout.addStretch()

        layout.addWidget(self._tbtn("📁  Open Folder", self._open_folder))
        layout.addWidget(self._tbtn("📦  Open Archive (.3psLCCA)", self._open_archive))

        sep = QLabel("|")
        sep.setStyleSheet("color:#444; padding:0 4px;")
        layout.addWidget(sep)

        return bar

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.chunk_list = self._side_list("CHUNKS")
        self.meta_list  = self._side_list("METADATA")
        self.blob_list  = self._side_list("BLOBS")

        layout.addWidget(self._section_header("CHUNKS"))
        layout.addWidget(self.chunk_list)
        layout.addWidget(self._section_header("METADATA"))
        layout.addWidget(self.meta_list)
        layout.addWidget(self._section_header("BLOBS"))
        layout.addWidget(self.blob_list)

        for lst in (self.chunk_list, self.meta_list, self.blob_list):
            lst.currentItemChanged.connect(self._on_item_selected)

        # Integrity check button
        self.btn_integrity = QPushButton("  Run Integrity Check")
        self.btn_integrity.setFixedHeight(32)
        self.btn_integrity.setEnabled(False)
        self.btn_integrity.setStyleSheet(
            "QPushButton { background:#313244; color:#cdd6f4; border:none;"
            " border-top:1px solid #333; text-align:left; padding-left:12px; font-size:12px; }"
            "QPushButton:hover:enabled { background:#45475a; }"
            "QPushButton:disabled { color:#555; }"
        )
        self.btn_integrity.clicked.connect(self._run_integrity_check)
        layout.addWidget(self.btn_integrity)
        layout.addStretch()
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        hdr = QWidget()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet("background:#252535; border-bottom:1px solid #333;")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(10, 0, 8, 0)
        hdr_layout.setSpacing(6)

        self.viewer_title = QLabel("No file selected")
        self.viewer_title.setStyleSheet("color:#888; font-size:12px;")
        hdr_layout.addWidget(self.viewer_title, stretch=1)

        # self.btn_edit   = self._small_btn("Edit",   self._start_edit)
        self.btn_edit   = self._small_btn("✏️",   self._start_edit)
        self.btn_revert = self._small_btn("Revert", self._revert_chunk)
        self.btn_save   = self._small_btn("Save",   self._save_chunk)
        for b in (self.btn_edit, self.btn_revert, self.btn_save):
            b.setEnabled(False)
            hdr_layout.addWidget(b)

        layout.addWidget(hdr)

        # JSON viewer / editor
        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        vf = QFont("Consolas", 10)
        vf.setStyleHint(QFont.Monospace)
        self.viewer.setFont(vf)
        self.viewer.setStyleSheet(
            "QPlainTextEdit { background:#1a1a2e; color:#cdd6f4; border:none; }"
        )
        layout.addWidget(self.viewer)
        return panel

    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet("background:#1e1e2e; border-top:1px solid #333;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        self.btn_share = QPushButton("📤  Create .3psLCCA...")
        self.btn_share.setFixedHeight(34)
        self.btn_share.setEnabled(False)
        self.btn_share.setStyleSheet(
            "QPushButton { background:#89b4fa; color:#1e1e2e; border:none;"
            " border-radius:4px; padding:0 16px; font-weight:bold; }"
            "QPushButton:hover:enabled { background:#b4d0f7; }"
            "QPushButton:disabled { background:#313244; color:#555; }"
        )
        self.btn_share.clicked.connect(self._create_archive)
        layout.addWidget(self.btn_share)

        self.chk_blobs = QCheckBox("Include blobs")
        self.chk_blobs.setChecked(True)
        self.chk_blobs.setStyleSheet("color:#888; font-size:12px;")
        layout.addWidget(self.chk_blobs)

        self.chk_integrity = QCheckBox("Recreate integrity hashes")
        self.chk_integrity.setChecked(True)
        self.chk_integrity.setToolTip(
            "Rebuild manifest.json with fresh SHA256 hashes for all chunks.\n"
            "Always recommended when chunks have been modified."
        )
        self.chk_integrity.setStyleSheet("color:#888; font-size:12px;")
        layout.addWidget(self.chk_integrity)

        self.chk_readable = QCheckBox("Readable chunks")
        self.chk_readable.setChecked(False)
        self.chk_readable.setToolTip(
            "Store chunk files as plain JSON instead of binary (MAGIC + zlib).\n"
            "Useful for manual inspection. Note: main app requires binary format."
        )
        self.chk_readable.setStyleSheet("color:#888; font-size:12px;")
        layout.addWidget(self.chk_readable)

        layout.addStretch()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#585b70; font-size:11px;")
        layout.addWidget(self.status_label)
        return bar

    # ── Widget helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _tbtn(label: str, slot) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(32)
        btn.setStyleSheet(
            "QPushButton { background:#313244; color:#cdd6f4; border:1px solid #444;"
            " border-radius:4px; padding:0 10px; }"
            "QPushButton:hover { background:#45475a; }"
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
    def _section_header(title: str) -> QLabel:
        lbl = QLabel(f"  {title}")
        lbl.setFixedHeight(22)
        lbl.setStyleSheet(
            "background:#252535; color:#585b70; font-size:10px;"
            " font-weight:bold; border-bottom:1px solid #2a2a3e;"
        )
        return lbl

    @staticmethod
    def _side_list() -> QListWidget:
        lst = QListWidget()
        lst.setStyleSheet(
            "QListWidget { background:#1e1e2e; color:#cdd6f4; border:none; font-size:12px; }"
            "QListWidget::item { padding:2px 0; }"
            "QListWidget::item:selected { background:#313244; }"
            "QListWidget::item:hover { background:#252535; }"
        )
        lst.setMaximumHeight(140)
        return lst

    # Fix: _side_list used as instance method accidentally — use static pattern
    def _side_list(self, _title: str = "") -> QListWidget:  # noqa: F811
        lst = QListWidget()
        lst.setStyleSheet(
            "QListWidget { background:#1e1e2e; color:#cdd6f4; border:none; font-size:12px; }"
            "QListWidget::item { padding:2px 0; }"
            "QListWidget::item:selected { background:#313244; }"
            "QListWidget::item:hover { background:#252535; }"
        )
        lst.setMaximumHeight(140)
        return lst

    # ── Open ───────────────────────────────────────────────────────────────────

    def _open_wpi_tool(self):
        dlg = WpiDatabaseDialog(self)
        dlg.exec()

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Project Folder")
        if not folder:
            return
        self._cleanup_temp()
        self._load_from_dir(Path(folder), label=Path(folder).name)

    def _open_archive(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Archive", "", "3psLCCA Archive (*.3psLCCA);;All Files (*)"
        )
        if not path:
            return

        if not zipfile.is_zipfile(path):
            self._warn("Invalid File", "Not a valid .3psLCCA archive.")
            return

        self._cleanup_temp()
        tmp = tempfile.mkdtemp(prefix="3pslcca_dev_")
        self._temp_dir = tmp

        try:
            with zipfile.ZipFile(path, "r") as zf:
                tmp_resolved = Path(tmp).resolve()
                for member in zf.infolist():
                    target = (Path(tmp) / member.filename).resolve()
                    if not str(target).startswith(str(tmp_resolved)):
                        raise ValueError(f"Unsafe path in archive: '{member.filename}'")
                    zf.extract(member, tmp)
        except Exception as e:
            shutil.rmtree(tmp, ignore_errors=True)
            self._temp_dir = None
            self._warn("Open Failed", f"Could not extract archive:\n{e}")
            return

        self._load_from_dir(Path(tmp), label=Path(path).name)

    def _load_from_dir(self, directory: Path, label: str):
        # Reset state
        self._chunk_raw.clear()
        self._chunk_modified.clear()
        self._chunk_status.clear()
        self._meta_raw.clear()
        self._blob_paths.clear()
        self._source_label = label
        self._editing = False

        # Load chunks
        chunks_dir = directory / "chunks"
        if chunks_dir.exists():
            for f in sorted(chunks_dir.glob(f"*{LCCA_EXT}")):
                self._chunk_raw[f.stem] = f.read_bytes()
                self._chunk_status[f.stem] = "unknown"

        # Load metadata
        for name in META_FILES:
            p = directory / name
            if p.exists():
                try:
                    self._meta_raw[name] = p.read_text(encoding="utf-8")
                except Exception:
                    pass

        # Load blobs
        blobs_dir = directory / "blobs"
        if blobs_dir.exists():
            for f in sorted(blobs_dir.iterdir()):
                if f.is_file() and not f.name.endswith(".sha256"):
                    self._blob_paths[f.name] = f

        self._refresh_lists()
        self._clear_viewer()
        self.btn_integrity.setEnabled(bool(self._chunk_raw))
        self.btn_share.setEnabled(bool(self._chunk_raw or self._meta_raw))

        self._set_status(
            f"{label}  —  {len(self._chunk_raw)} chunk(s), "
            f"{len(self._meta_raw)} metadata file(s), {len(self._blob_paths)} blob(s)"
        )

    # ── Left panel list ────────────────────────────────────────────────────────

    def _refresh_lists(self):
        for lst in (self.chunk_list, self.meta_list, self.blob_list):
            lst.blockSignals(True)
            lst.clear()
            lst.blockSignals(False)

        for name in self._chunk_raw:
            self.chunk_list.addItem(self._chunk_item(name))

        for name in self._meta_raw:
            item = QListWidgetItem(f"  {name}")
            item.setData(Qt.UserRole, ("meta", name))
            item.setForeground(QColor("#a6e3a1"))
            self.meta_list.addItem(item)

        for name in self._blob_paths:
            item = QListWidgetItem(f"  {name}")
            item.setData(Qt.UserRole, ("blob", name))
            item.setForeground(QColor("#fab387"))
            self.blob_list.addItem(item)

    def _chunk_item(self, name: str) -> QListWidgetItem:
        status = self._chunk_status.get(name, "unknown")
        modified = name in self._chunk_modified

        if modified:
            icon = ICON_MODIFIED
            color = "#f9e2af"   # yellow
        elif status == "clean":
            icon = ICON_CLEAN
            color = "#a6e3a1"   # green
        elif status == "mismatch":
            icon = ICON_MISMATCH
            color = "#fab387"   # orange
        elif status == "corrupt":
            icon = ICON_CORRUPT
            color = "#f38ba8"   # red
        else:
            icon = "·"
            color = "#cdd6f4"   # default

        item = QListWidgetItem(f"  {icon} {name}")
        item.setData(Qt.UserRole, ("chunk", name))
        item.setForeground(QColor(color))
        return item

    def _update_chunk_item(self, name: str):
        for i in range(self.chunk_list.count()):
            item = self.chunk_list.item(i)
            if item and item.data(Qt.UserRole) == ("chunk", name):
                new_item = self._chunk_item(name)
                item.setText(new_item.text())
                item.setForeground(new_item.foreground())
                break

    # ── Viewer ─────────────────────────────────────────────────────────────────

    def _on_item_selected(self, current, _previous):
        if not current:
            return

        # Deselect other lists
        sender = self.sender()
        for lst in (self.chunk_list, self.meta_list, self.blob_list):
            if lst is not sender:
                lst.blockSignals(True)
                lst.clearSelection()
                lst.blockSignals(False)

        # If currently editing, ask before switching
        if self._editing:
            resp = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved edits. Discard and switch?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resp == QMessageBox.No:
                return
            self._stop_edit()

        kind, name = current.data(Qt.UserRole)
        self._active_kind = kind
        self._active_name = name

        if kind == "chunk":
            self._show_chunk(name)
        elif kind == "meta":
            self._show_meta(name)
        elif kind == "blob":
            self._show_blob(name)

    def _show_chunk(self, name: str):
        # Use modified dict if available, else decode raw
        if name in self._chunk_modified:
            text = json.dumps(self._chunk_modified[name], indent=4, ensure_ascii=False)
            fmt = "binary (modified)"
        else:
            raw = self._chunk_raw[name]
            try:
                data = decode_bytes(raw)
                text = json.dumps(data, indent=4, ensure_ascii=False)
                fmt = "binary" if raw[:4] == b"\x4c\x43\x43\x41" else "readable"
            except Exception as e:
                text = f"// Cannot decode this chunk:\n// {e}"
                fmt = "corrupt"

        status = self._chunk_status.get(name, "unknown")
        status_str = {"clean": "✓ clean", "mismatch": "⚠ hash mismatch",
                      "corrupt": "✕ corrupt", "unknown": "· not checked"}.get(status, status)

        self.viewer_title.setText(f"{name}.lcca  [{fmt}]  {status_str}")
        self.viewer.setPlainText(text)
        self.viewer.setReadOnly(True)
        self._editing = False

        # Only enable Edit for decodable chunks
        can_edit = "corrupt" not in fmt
        self.btn_edit.setEnabled(can_edit)
        self.btn_revert.setEnabled(name in self._chunk_modified)
        self.btn_save.setEnabled(False)

    def _show_meta(self, name: str):
        raw = self._meta_raw.get(name, "")
        try:
            text = json.dumps(json.loads(raw), indent=4, ensure_ascii=False)
        except Exception:
            text = raw
        self.viewer_title.setText(name)
        self.viewer.setPlainText(text)
        self.viewer.setReadOnly(True)
        self.btn_edit.setEnabled(False)
        self.btn_revert.setEnabled(False)
        self.btn_save.setEnabled(False)

    def _show_blob(self, name: str):
        path = self._blob_paths[name]
        size = path.stat().st_size
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self.viewer_title.setText(f"{name}  [binary blob]")
        self.viewer.setPlainText(
            f"// Binary blob — cannot display content.\n"
            f"//\n"
            f"// Name  : {name}\n"
            f"// Size  : {size:,} bytes  ({size / 1024:.1f} KB)\n"
            f"// SHA256: {sha}\n"
            f"// Path  : {path}"
        )
        self.viewer.setReadOnly(True)
        self.btn_edit.setEnabled(False)
        self.btn_revert.setEnabled(False)
        self.btn_save.setEnabled(False)

    def _clear_viewer(self):
        self.viewer_title.setText("No file selected")
        self.viewer.clear()
        self.viewer.setReadOnly(True)
        for b in (self.btn_edit, self.btn_revert, self.btn_save):
            b.setEnabled(False)
        self._active_kind = ""
        self._active_name = ""
        self._editing = False

    # ── Edit / Save / Revert ───────────────────────────────────────────────────

    def _start_edit(self):
        if self._active_kind != "chunk":
            return
        self.viewer.setReadOnly(False)
        self.viewer.setStyleSheet(
            "QPlainTextEdit { background:#1a1a2e; color:#cdd6f4; border:none;"
            " border-left: 2px solid #f9e2af; }"
        )
        self.btn_edit.setEnabled(False)
        self.btn_save.setEnabled(True)
        self.btn_revert.setEnabled(True)
        self._editing = True
        self.viewer_title.setText(self.viewer_title.text().split("  [")[0] + "  [editing…]")

    def _stop_edit(self):
        self.viewer.setReadOnly(True)
        self.viewer.setStyleSheet(
            "QPlainTextEdit { background:#1a1a2e; color:#cdd6f4; border:none; }"
        )
        self._editing = False

    def _save_chunk(self):
        if self._active_kind != "chunk":
            return
        name = self._active_name
        text = self.viewer.toPlainText()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            self._warn("Invalid JSON", f"Fix the error before saving:\n\n{e}")
            return
        if not isinstance(data, dict):
            self._warn("Invalid JSON", "Root value must be a JSON object {…}, not a list or scalar.")
            return

        self._chunk_modified[name] = data
        self._chunk_status[name] = "unknown"  # hash is now stale
        self._update_chunk_item(name)
        self._stop_edit()
        self._show_chunk(name)
        self._set_status(f"Saved edits to '{name}' — will be encoded to binary on export.")

    def _revert_chunk(self):
        if self._active_kind != "chunk":
            return
        name = self._active_name
        if name in self._chunk_modified:
            del self._chunk_modified[name]
        self._stop_edit()
        self._update_chunk_item(name)
        self._show_chunk(name)
        self._set_status(f"Reverted '{name}' to original.")

    # ── Integrity check ────────────────────────────────────────────────────────

    def _run_integrity_check(self):
        if not self._chunk_raw:
            return

        # Read expected hashes from manifest.json
        expected: dict[str, str] = {}
        manifest_raw = self._meta_raw.get("manifest.json", "")
        if manifest_raw:
            try:
                mf = json.loads(manifest_raw)
                for chunk_name, info in mf.get("chunks", {}).items():
                    if isinstance(info, dict):
                        expected[chunk_name] = info.get("sha256", "")
                    elif isinstance(info, str):
                        expected[chunk_name] = info
            except Exception:
                pass

        clean = mismatch = corrupt = 0

        for name, raw in self._chunk_raw.items():
            # Check decodability first
            try:
                decode_bytes(raw)
            except Exception:
                self._chunk_status[name] = "corrupt"
                corrupt += 1
                self._update_chunk_item(name)
                continue

            # Check hash if manifest has one
            if name in expected and expected[name]:
                actual = hashlib.sha256(raw).hexdigest()
                if actual == expected[name]:
                    self._chunk_status[name] = "clean"
                    clean += 1
                else:
                    self._chunk_status[name] = "mismatch"
                    mismatch += 1
            else:
                # No hash to compare — at least it decodes
                self._chunk_status[name] = "clean"
                clean += 1

            self._update_chunk_item(name)

        # Refresh active chunk viewer if it's a chunk
        if self._active_kind == "chunk" and self._active_name:
            self._show_chunk(self._active_name)

        summary = f"Integrity: {clean} clean"
        if mismatch:
            summary += f", {mismatch} hash mismatch"
        if corrupt:
            summary += f", {corrupt} corrupt"
        if not expected:
            summary += "  (no manifest hashes — checked decodability only)"

        self._set_status(summary)
        QMessageBox.information(self, "Integrity Check Complete", summary)

    # ── Create archive ─────────────────────────────────────────────────────────

    def _create_archive(self):
        if not self._chunk_raw and not self._meta_raw:
            return

        modified_count = len(self._chunk_modified)
        msg = f"{len(self._chunk_raw)} chunk(s)"
        if modified_count:
            msg += f"  ({modified_count} modified)"

        default_name = f"share_{time.strftime('%Y%m%d_%H%M%S')}.3psLCCA"
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save .3psLCCA Archive", default_name,
            "3psLCCA Archive (*.3psLCCA)",
        )
        if not out_path:
            return
        if not out_path.endswith(".3psLCCA"):
            out_path += ".3psLCCA"

        include_blobs = self.chk_blobs.isChecked()
        recreate_integrity = self.chk_integrity.isChecked()
        use_readable = self.chk_readable.isChecked()
        errors = []

        try:
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:

                # Chunks — encode to chosen format; track bytes for hash rebuild
                chunk_encoded: dict[str, bytes] = {}
                for name, raw in self._chunk_raw.items():
                    try:
                        if name in self._chunk_modified:
                            data = self._chunk_modified[name]
                        else:
                            data = decode_bytes(raw)

                        if use_readable:
                            encoded = json.dumps(data, indent=4, ensure_ascii=False).encode("utf-8")
                        else:
                            encoded = encode_dict(data)

                        chunk_encoded[name] = encoded
                        zf.writestr(f"chunks/{name}.lcca", encoded)
                    except Exception as e:
                        errors.append(f"{name}.lcca: {e}")

                # Metadata — copy as-is except manifest and checkpoint_meta
                # (manifest rebuilt below if requested)
                for name, text in self._meta_raw.items():
                    if name in ("checkpoint_meta.json", "manifest.json"):
                        continue
                    if name == "version.json":
                        try:
                            vdata = json.loads(text)
                            vdata["readable"] = use_readable
                            zf.writestr(name, json.dumps(vdata, indent=4))
                        except Exception:
                            zf.writestr(name, text)
                        continue
                    zf.writestr(name, text)

                # Manifest — rebuild with fresh hashes or copy original
                if recreate_integrity and chunk_encoded:
                    orig_manifest = {}
                    try:
                        orig_manifest = json.loads(self._meta_raw.get("manifest.json", "{}"))
                    except Exception:
                        pass

                    new_chunks = {}
                    for name, encoded in chunk_encoded.items():
                        sha = hashlib.sha256(encoded).hexdigest()
                        # Use "hash" key (what SafeChunkEngine._verify_chunks reads).
                        # Strip any stale "hash"/"sha256" from orig_entry — chunks are
                        # re-encoded so those values are no longer valid.
                        orig_entry = orig_manifest.get("chunks", {}).get(name, {})
                        if isinstance(orig_entry, dict):
                            cleaned = {k: v for k, v in orig_entry.items()
                                       if k not in ("hash", "sha256")}
                            new_chunks[name] = {**cleaned, "hash": sha,
                                                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                        else:
                            new_chunks[name] = {"hash": sha,
                                                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}

                    new_manifest = {
                        **orig_manifest,
                        "chunks": new_chunks,
                        "engine_version": orig_manifest.get("engine_version", "3.0.0"),
                        "hashes_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    zf.writestr("manifest.json", json.dumps(new_manifest, indent=4))
                elif "manifest.json" in self._meta_raw:
                    zf.writestr("manifest.json", self._meta_raw["manifest.json"])

                # Regenerate checkpoint_meta.json
                orig_meta = {}
                try:
                    orig_meta = json.loads(self._meta_raw.get("checkpoint_meta.json", "{}"))
                except Exception:
                    pass

                # Resolve project_id: prefer orig_meta, fall back to version.json
                version_data = {}
                try:
                    version_data = json.loads(self._meta_raw.get("version.json", "{}"))
                except Exception:
                    pass
                archive_project_id = (
                    orig_meta.get("project_id")
                    or version_data.get("project_id")
                    or ""
                )

                new_meta = {
                    **orig_meta,
                    "label": orig_meta.get("label", "devtools-share"),
                    "notes": (
                        f"Created by 3psLCCA Developer Tools — "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')}"
                        + (f" — {modified_count} chunk(s) modified" if modified_count else "")
                    ),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "engine_ver": orig_meta.get("engine_ver", "3.0.0"),
                    "project_id": archive_project_id,
                    "readable": use_readable,
                    "type": "manual",
                    "includes_blobs": include_blobs and bool(self._blob_paths),
                }

                # Blobs
                if include_blobs and self._blob_paths:
                    blob_hashes = {}
                    for name, path in self._blob_paths.items():
                        try:
                            zf.write(path, arcname=f"blobs/{name}")
                            blob_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
                        except Exception as e:
                            errors.append(f"blobs/{name}: {e}")
                    new_meta["blob_hashes"] = blob_hashes

                zf.writestr("checkpoint_meta.json", json.dumps(new_meta, indent=4))

        except Exception as e:
            self._warn("Export Failed", f"Could not write archive:\n{e}")
            return

        # SHA256 sidecar
        try:
            sha = hashlib.sha256(Path(out_path).read_bytes()).hexdigest()
            Path(out_path + ".sha256").write_text(sha)
        except Exception:
            pass

        msg_parts = [f"Archive saved to:\n{out_path}"]
        if modified_count:
            msg_parts.append(f"\n{modified_count} chunk(s) contain your fixes.")
        if recreate_integrity:
            msg_parts.append(f"\nIntegrity hashes rebuilt — all chunks will pass verification.")
        if errors:
            msg_parts.append(f"\n\n{len(errors)} error(s):\n" + "\n".join(errors))

        QMessageBox.information(self, "Archive Created", "\n".join(msg_parts))
        fmt_note = " [readable]" if use_readable else " [binary]"
        integrity_note = " + hashes rebuilt" if recreate_integrity else ""
        self._set_status(f"Created: {Path(out_path).name}  ({msg}{fmt_note}{integrity_note})")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self.status_label.setText(msg)

    def _warn(self, title: str, msg: str):
        QMessageBox.warning(self, title, msg)

    def _cleanup_temp(self):
        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def closeEvent(self, event):
        self._cleanup_temp()
        super().closeEvent(event)


