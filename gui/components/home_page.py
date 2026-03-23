"""
gui/components/home_page.py

Home screen for the LCCA application.
"""

import os
import re
import json
import shutil
import hashlib
import zipfile
from PySide6.QtCore import Qt, QSize, QPoint, QRect, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QSizePolicy,
    QMessageBox,
    QInputDialog,
    QFileDialog,
    QDialog,
    QFormLayout,
    QMenu,
    QApplication,
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
)
from core.safechunk_engine import SafeChunkEngine


# ── Status config ─────────────────────────────────────────────────────────────

STATUS_CONFIG = {
    "ok": {"label": "OK", "color": "#22c55e"},
    "crashed": {"label": "Crashed", "color": "#ef4444"},
    "locked": {"label": "Open", "color": "#3b82f6"},
    "corrupted": {"label": "Corrupted", "color": "#f97316"},
}


# ── Custom delegate ───────────────────────────────────────────────────────────


class ProjectCardDelegate(QStyledItemDelegate):
    """
    Renders each project as a card:
      - Display name (bold)
      - Modified / Created dates (muted)
      - Status badge (coloured pill, top-right)
      - ⋮ button at far right
    """

    CARD_HEIGHT = 72
    PADDING_H = 14
    PADDING_V = 10
    BADGE_PADDING = 6
    BADGE_H = 18
    RADIUS = 6
    DOT_SIZE = 20

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.CARD_HEIGHT)

    @staticmethod
    def _dot_rect(card_rect: QRect) -> QRect:
        size = ProjectCardDelegate.DOT_SIZE
        x = card_rect.right() - size - 6
        y = card_rect.top() + (card_rect.height() - size) // 2
        return QRect(x, y, size, size)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):

        data = index.data(Qt.UserRole)
        if not isinstance(data, dict):
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(6, 3, -6, -3)

        # ── Background ────────────────────────────────────────────────────────
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)

        palette = option.palette
        if is_selected:
            bg = palette.highlight().color()
        elif is_hovered:
            bg = palette.light().color()
        else:
            bg = palette.base().color()

        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        # ── Status badge (shifted left to make room for ⋮ button) ─────────────
        status = data.get("status", "ok") if data else "ok"
        cfg = STATUS_CONFIG.get(status, STATUS_CONFIG["ok"])
        badge_text = cfg["label"]
        badge_col = QColor(cfg["color"])

        badge_font = QFont()
        badge_font.setPointSize(7)
        badge_font.setBold(True)
        painter.setFont(badge_font)

        fm = painter.fontMetrics()
        badge_w = fm.horizontalAdvance(badge_text) + self.BADGE_PADDING * 2
        badge_rect = QRect(
            rect.right() - badge_w - self.PADDING_H - self.DOT_SIZE - 4,
            rect.top() + self.PADDING_V,
            badge_w,
            self.BADGE_H,
        )

        pill_bg = QColor(badge_col)
        pill_bg.setAlpha(30)
        painter.setBrush(QBrush(pill_bg))
        painter.setPen(QPen(badge_col, 1))
        painter.drawRoundedRect(badge_rect, self.BADGE_H / 2, self.BADGE_H / 2)
        painter.setPen(badge_col)
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        # ── Text colours ──────────────────────────────────────────────────────
        text_col = (
            palette.highlightedText().color() if is_selected else palette.text().color()
        )
        muted_col = (
            palette.highlightedText().color()
            if is_selected
            else palette.placeholderText().color()
        )

        text_x = rect.left() + self.PADDING_H
        text_maxw = badge_rect.left() - text_x - 8

        # Display name
        name_font = QFont()
        name_font.setPointSize(10)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(text_col)
        name = (data.get("display_name") or "Unnamed") if data else "Unnamed"
        name_fm = painter.fontMetrics()
        name_text = name_fm.elidedText(name, Qt.ElideRight, text_maxw)
        name_y = rect.top() + self.PADDING_V + name_fm.ascent()
        painter.drawText(QPoint(text_x, name_y), name_text)

        # Sub-labels
        sub_font = QFont()
        sub_font.setPointSize(8)
        painter.setFont(sub_font)
        painter.setPen(muted_col)

        sub_fm = painter.fontMetrics()
        sub_y = name_y + name_fm.descent() + 3 + sub_fm.ascent()

        parts = []
        if data:
            if data.get("last_modified"):
                parts.append(f"Modified {data['last_modified']}")
            if data.get("created_at"):
                parts.append(f"Created {data['created_at']}")

        if parts:
            painter.drawText(QPoint(text_x, sub_y), "   ·   ".join(parts))

        # ── Three-dot button ──────────────────────────────────────────────────
        dot_rect = self._dot_rect(rect)
        dot_font = QFont()
        dot_font.setPointSize(11)
        painter.setFont(dot_font)
        painter.setPen(muted_col)
        painter.drawText(dot_rect, Qt.AlignCenter, "⋮")

        painter.restore()


# ── List item ─────────────────────────────────────────────────────────────────


class ProjectListItem(QListWidgetItem):
    def __init__(self, project_info: dict):
        super().__init__()
        self.project_id = project_info["project_id"]
        self.display_name = project_info.get("display_name", self.project_id)
        self.setData(Qt.UserRole, project_info)
        self.setSizeHint(QSize(0, ProjectCardDelegate.CARD_HEIGHT))


# ── List widget with ⋮ click detection ───────────────────────────────────────


class ProjectListWidget(QListWidget):
    """QListWidget that detects clicks on the ⋮ button of each card."""

    menu_requested = Signal(str, QPoint)  # project_id, global pos

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            index = self.indexAt(event.pos())
            if index.isValid():
                item = self.item(index.row())
                if isinstance(item, ProjectListItem):
                    item_rect = self.visualRect(index)
                    card_rect = item_rect.adjusted(6, 3, -6, -3)
                    dot_rect = ProjectCardDelegate._dot_rect(card_rect)
                    if dot_rect.contains(event.pos()):
                        global_pos = self.viewport().mapToGlobal(event.pos())
                        self.menu_requested.emit(item.project_id, global_pos)
                        return
        super().mousePressEvent(event)


# ── Home page ─────────────────────────────────────────────────────────────────


class HomePage(QWidget):

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._active_project_id = None
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_header())

        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.addStretch(1)
        body_row.addWidget(self._make_body(), stretch=0)
        body_row.addStretch(1)

        body_wrapper = QWidget()
        body_wrapper.setLayout(body_row)
        body_wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(body_wrapper, stretch=1)

        root.addWidget(self._make_footer())

    def _make_header(self, special_effect: bool = True) -> QWidget:
        bar = QFrame()
        bar.setFrameShape(QFrame.StyledPanel)
        bar.setFixedHeight(64)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(28, 0, 28, 0)

        # ── Title ───────────────────────────────────────────────
        title = QLabel("✨ 3psLCCA")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)
        layout.addStretch()

        # ── Subtitle ────────────────────────────────────────────
        if special_effect:
            quotes = [
                "💡 Small steps today lead to big savings tomorrow.",
                "📊 Measure twice, cut once and track the cost.",
                "⚙️ Efficiency is doing things right; effectiveness is doing the right things.",
                "🧭 Data is the compass, cost is the path.",
                "📖 Every project tells a story make yours count.",
            ]

            subtitle = QLabel(quotes[0])
            sub_f = QFont()
            sub_f.setPointSize(8)
            subtitle.setFont(sub_f)
            subtitle.setEnabled(True)
            subtitle.setWordWrap(True)
            subtitle.setFixedWidth(250)
            subtitle.setSizePolicy(
                subtitle.sizePolicy().horizontalPolicy(),
                subtitle.sizePolicy().verticalPolicy(),
            )
            layout.addWidget(subtitle)

            index = {"value": 0}

            def update_quote():
                index["value"] = (index["value"] + 1) % len(quotes)
                subtitle.setText(quotes[index["value"]])

            timer = QTimer(subtitle)
            timer.timeout.connect(update_quote)
            timer.start(5000)
        else:
            subtitle = QLabel("Life Cycle Cost Analysis")
            sub_f = QFont()
            sub_f.setPointSize(10)
            subtitle.setFont(sub_f)
            subtitle.setEnabled(False)
            layout.addWidget(subtitle)

        return bar

    def _make_body(self) -> QWidget:
        card = QWidget()
        card.setFixedWidth(500)
        card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 40, 0, 40)
        layout.setSpacing(0)

        # New project
        layout.addWidget(self._section_label("Start"))
        layout.addSpacing(8)

        self.btn_new = QPushButton("＋  New Project")
        self.btn_new.setFixedHeight(40)
        self.btn_new.setDefault(True)
        self.btn_new.clicked.connect(lambda: self.manager.open_project(is_new=True))
        layout.addWidget(self.btn_new)

        layout.addSpacing(8)

        self.btn_load = QPushButton("📂  Load Shared Project...")
        self.btn_load.setFixedHeight(36)
        self.btn_load.setToolTip("Import a .3psLCCA archive shared by someone else")
        self.btn_load.clicked.connect(self._load_shared_project)
        layout.addWidget(self.btn_load)

        layout.addSpacing(24)
        layout.addWidget(self._divider())
        layout.addSpacing(24)

        # Project list header
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._section_label("Projects"))
        row.addStretch()
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setToolTip("Refresh list")
        refresh_btn.clicked.connect(self.refresh_project_list)
        row.addWidget(refresh_btn)
        layout.addLayout(row)
        layout.addSpacing(8)

        # Project list with card delegate and ⋮ detection
        self.project_list = ProjectListWidget()
        self.project_list.setMinimumHeight(240)
        self.project_list.setItemDelegate(ProjectCardDelegate())
        self.project_list.setMouseTracking(True)
        self.project_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.project_list.itemDoubleClicked.connect(self._open_selected)
        self.project_list.menu_requested.connect(self._show_card_menu)
        layout.addWidget(self.project_list)

        layout.addSpacing(10)

        # Open / Delete buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_open = QPushButton("Open")
        self.btn_open.setFixedHeight(34)
        self.btn_open.clicked.connect(self._open_selected)
        btn_row.addWidget(self.btn_open)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setFixedHeight(34)
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_delete)

        layout.addLayout(btn_row)

        layout.addSpacing(32)
        layout.addWidget(self._divider())
        layout.addSpacing(24)

        # Return to active project
        self.btn_return = QPushButton("← Return to Active Project")
        self.btn_return.setFixedHeight(36)
        self.btn_return.hide()
        self.btn_return.clicked.connect(
            lambda: self.manager.open_project(project_id=self._active_project_id)
        )
        layout.addWidget(self.btn_return)

        return card

    def _make_footer(self) -> QWidget:
        bar = QFrame()
        bar.setFrameShape(QFrame.StyledPanel)
        bar.setFixedHeight(32)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        lbl = QLabel("3psLCCA  •  0.1.0-dev")
        lbl.setEnabled(False)
        f = QFont()
        f.setPointSize(9)
        lbl.setFont(f)
        layout.addWidget(lbl)
        layout.addStretch()

        return bar

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text.upper())
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        lbl.setFont(f)
        lbl.setEnabled(False)
        return lbl

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def _item_for_pid(self, pid: str) -> "ProjectListItem | None":
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            if isinstance(item, ProjectListItem) and item.project_id == pid:
                return item
        return None

    # ── Public API ────────────────────────────────────────────────────────────

    def set_active_project(self, project_id: str | None):
        self._active_project_id = project_id
        if project_id:
            display = project_id
            for win in self.manager.windows:
                if win.project_id == project_id:
                    display = win.controller.active_display_name or project_id
                    break
            self.btn_return.show()
            self.btn_return.setText(f"← Return to  {display}")
        else:
            self.btn_return.hide()

    def refresh_project_list(self):
        self.project_list.clear()
        projects = sorted(
            SafeChunkEngine.list_all_projects(),
            key=lambda p: p.get("last_modified") or "",
            reverse=True,
        )

        open_windows = {
            win.project_id: win
            for win in self.manager.windows
            if win.project_id is not None
        }

        if not projects:
            placeholder = QListWidgetItem(
                "✨ Click '+ New Project' above to create your first project.\n"
                "Your projects will appear here once you create them."
            )
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
            placeholder.setForeground(QColor("#888888"))
            placeholder.setTextAlignment(Qt.AlignCenter)
            self.project_list.addItem(placeholder)
        else:
            for p in projects:
                pid = p["project_id"]
                if pid in open_windows:
                    p["status"] = "locked"
                    mem_name = open_windows[pid].controller.active_display_name
                    if mem_name:
                        p["display_name"] = mem_name
                elif p["status"] == "locked":
                    p["status"] = "ok"

                self.project_list.addItem(ProjectListItem(p))

    # ── Internal slots ────────────────────────────────────────────────────────

    def _selected_pid(self) -> str | None:
        item = self.project_list.currentItem()
        if isinstance(item, ProjectListItem):
            return item.project_id
        return None

    def _open_selected(self):
        pid = self._selected_pid()
        if pid:
            self.manager.open_project(project_id=pid)

    # ── Three-dot menu ────────────────────────────────────────────────────────

    def _show_card_menu(self, pid: str, global_pos: QPoint):
        item = self._item_for_pid(pid)
        display = item.display_name if item else pid

        menu = QMenu(self)
        menu.addAction("Copy Name", lambda: self._copy_name(display))
        menu.addAction("Share / Export...", lambda: self._share_project(pid, display))
        menu.addSeparator()
        menu.addAction("Rename", lambda: self._rename_by_pid(pid, display))
        menu.addAction("Info", lambda: self._show_project_info(pid))
        menu.exec(global_pos)

    def _copy_name(self, display: str):
        QApplication.clipboard().setText(display)

    def _share_project(self, pid: str, display: str):
        if self.manager.is_project_open(pid):
            QMessageBox.warning(
                self,
                "Cannot Export",
                "This project is currently open in a window.\n\n"
                "Close it first, then export it.",
            )
            return

        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Export Project",
            f"{display}.3psLCCA",
            "3psLCCA Archive (*.3psLCCA)",
        )
        if not dest:
            return

        engine, status = SafeChunkEngine.open(pid)
        if status != "SUCCESS" or engine is None:
            QMessageBox.warning(
                self,
                "Export Failed",
                f"Could not open project for export.\n\n{status}",
            )
            return

        zip_name = engine.create_checkpoint(
            label="export",
            notes=f"Exported from 3psLCCA",
            include_blobs=True,
        )
        if zip_name is None:
            engine.detach()
            QMessageBox.warning(
                self,
                "Export Failed",
                "Could not create the export archive.",
            )
            return

        src = engine.checkpoint_manual / zip_name
        engine.detach()

        try:
            shutil.copy2(str(src), dest)
            QMessageBox.information(
                self,
                "Export Complete",
                f"Project exported to:\n{dest}",
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Export Failed",
                f"Could not save archive to destination:\n{e}",
            )

    def _rename_by_pid(self, pid: str, current_name: str):
        if self.manager.is_project_open(pid):
            QMessageBox.warning(
                self,
                "Cannot Rename",
                "This project is currently open in a window.\n\n"
                "Close it first, then rename it.",
            )
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Project",
            "New name:",
            text=current_name,
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == current_name:
            return

        engine, status = SafeChunkEngine.open(pid)
        if status != "SUCCESS" or engine is None:
            QMessageBox.warning(
                self,
                "Rename Failed",
                f"Could not open project to rename it.\n\n{status}",
            )
            return

        engine.rename(new_name)
        engine.detach()
        self.manager.refresh_all_home_screens()

    def _load_shared_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Shared Project",
            "",
            "3psLCCA Archive (*.3psLCCA)",
        )
        if not path:
            return

        # ── Validate archive ──────────────────────────────────────────────
        if not zipfile.is_zipfile(path):
            QMessageBox.warning(
                self,
                "Invalid File",
                "The selected file is not a valid 3psLCCA archive.\n\n"
                "Make sure you are opening a file exported from 3psLCCA.",
            )
            return

        # ── Read metadata from archive ────────────────────────────────────
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()

                # ── Authenticate as genuine 3psLCCA archive ───────────────
                # checkpoint_meta.json is always written by the engine and
                # contains our engine-specific fields.  A random ZIP renamed
                # to .3psLCCA will lack these.
                if "checkpoint_meta.json" not in names:
                    QMessageBox.warning(
                        self,
                        "Invalid Archive",
                        "This file does not appear to be a valid 3psLCCA project archive.\n\n"
                        "It is missing the required checkpoint metadata.",
                    )
                    return

                meta = json.loads(zf.read("checkpoint_meta.json").decode("utf-8"))

                # engine_ver is written by SafeChunkEngine — must be present
                if not meta.get("engine_ver"):
                    QMessageBox.warning(
                        self,
                        "Invalid Archive",
                        "This file does not appear to be a valid 3psLCCA project archive.\n\n"
                        "The checkpoint metadata is missing the engine signature.",
                    )
                    return

                # project_id must be a non-empty string
                archive_pid = meta.get("project_id", "")
                if not isinstance(archive_pid, str) or not archive_pid.strip():
                    QMessageBox.warning(
                        self,
                        "Invalid Archive",
                        "This file does not appear to be a valid 3psLCCA project archive.\n\n"
                        "The checkpoint metadata does not contain a valid project ID.",
                    )
                    return

                # ── Binary chunk magic check ──────────────────────────────
                # Every .lcca chunk file starts with MAGIC b"\x4c\x43\x43\x41"
                # ("LCCA") followed by zlib-compressed JSON.  Readable mode is
                # disabled in production, so any genuine archive must have this.
                LCCA_MAGIC = b"\x4c\x43\x43\x41"
                chunk_entries = [n for n in names if n.startswith("chunks/") and n.endswith(".lcca")]
                if chunk_entries:
                    first_chunk = zf.read(chunk_entries[0])
                    if first_chunk[:4] != LCCA_MAGIC:
                        QMessageBox.warning(
                            self,
                            "Invalid Archive",
                            "This file does not appear to be a valid 3psLCCA project archive.\n\n"
                            "The chunk data does not match the expected binary format.",
                        )
                        return

                display_name = None
                if "version.json" in names:
                    data = json.loads(zf.read("version.json").decode("utf-8"))
                    # version.json must also carry engine_version to be genuine
                    if not data.get("engine_version"):
                        QMessageBox.warning(
                            self,
                            "Invalid Archive",
                            "This file does not appear to be a valid 3psLCCA project archive.\n\n"
                            "The project metadata is missing the engine version.",
                        )
                        return
                    display_name = (data.get("display_name") or data.get("project_id") or "").strip()
                if not display_name:
                    display_name = archive_pid.strip()

        except zipfile.BadZipFile:
            QMessageBox.warning(
                self,
                "Invalid File",
                "The selected file could not be opened as a 3psLCCA archive.\n\n"
                "The file may be corrupted or was not exported from 3psLCCA.",
            )
            return
        except Exception as e:
            QMessageBox.warning(self, "Load Failed", f"Unexpected error reading archive:\n{e}")
            return

        display_name = display_name or "Imported Project"
        project_id = re.sub(r"[^\w\-]", "_", display_name)[:40].strip("_") or "imported_project"

        # ── Create blank project ──────────────────────────────────────────
        engine, status = SafeChunkEngine.new(
            project_id=project_id,
            display_name=display_name,
        )
        if status != "SUCCESS" or engine is None:
            QMessageBox.warning(self, "Load Failed", f"Could not create project:\n{status}")
            return

        pid = engine.project_id

        # ── Copy archive into project's checkpoint_manual folder ──────────
        zip_name = os.path.basename(path)
        dest_zip = engine.checkpoint_manual / zip_name
        try:
            shutil.copy2(path, dest_zip)
            sha = hashlib.sha256(dest_zip.read_bytes()).hexdigest()
            (engine.checkpoint_manual / f"{zip_name}.sha256").write_text(sha)
        except Exception as e:
            engine.detach()
            QMessageBox.warning(self, "Load Failed", f"Could not copy archive:\n{e}")
            return

        # ── Restore from checkpoint ───────────────────────────────────────
        success = engine.restore_checkpoint(zip_name)
        engine.detach()

        if not success:
            QMessageBox.warning(
                self, "Load Failed",
                "Archive could not be restored. It may be corrupt or incompatible."
            )
            return

        self.manager.refresh_all_home_screens()

        result = QMessageBox.question(
            self,
            "Project Loaded",
            f"'{display_name}' loaded successfully.\n\nOpen it now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if result == QMessageBox.Yes:
            self.manager.open_project(project_id=pid)

    def _show_project_info(self, pid: str):
        info = SafeChunkEngine.get_project_info(pid)
        if not info:
            QMessageBox.warning(self, "Info", "Could not read project info.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Project Info — {info.get('display_name', pid)}")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(6)
        rows = [
            ("Project ID",       info.get("project_id", "")),
            ("Display Name",     info.get("display_name", "")),
            ("Status",           info.get("status", "").capitalize()),
            ("Created",          info.get("created_at", "—")),
            ("Last Modified",    info.get("last_modified", "—")),
            ("Chunks",           str(info.get("chunk_count", 0))),
            ("Checkpoints",      str(info.get("checkpoint_count", 0))),
            ("Last Checkpoint",  info.get("last_checkpoint_date") or "—"),
            ("Size",             f"{info.get('size_kb', 0)} KB"),
            ("Clean Close",      "Yes" if info.get("clean_close") else "No"),
            ("Engine Version",   info.get("engine_version", "—")),
        ]
        for label, value in rows:
            lbl = QLabel(value)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(f"{label}:", lbl)

        layout.addLayout(form)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        dlg.exec()

    def _delete_selected(self):
        pid = self._selected_pid()
        if not pid:
            QMessageBox.information(self, "Delete", "Select a project first.")
            return

        if self.manager.is_project_open(pid):
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "This project is currently open in a window.\n\n"
                "Close it first, then delete it.",
            )
            return

        item = self.project_list.currentItem()
        display = item.display_name if isinstance(item, ProjectListItem) else pid

        result = QMessageBox.warning(
            self,
            "Delete Project",
            f"Permanently delete '{display}'?\n\nThis cannot be undone.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if result == QMessageBox.Ok:
            engine, _ = SafeChunkEngine.open(pid)
            if engine:
                engine.delete_project(confirmed=True)
            self.manager.refresh_all_home_screens()
