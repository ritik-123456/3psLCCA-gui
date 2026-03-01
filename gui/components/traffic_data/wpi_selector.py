"""
gui/components/traffic_data/wpi_selector.py

_WPISelector — profile selector bar for WPI adjustment ratio profiles.

Layout:
    [Profile: ▾ combo] [✅/⚠/❌] [+ New] [✎ Save As] [🗑 Delete]

Signals:
    profile_selected(WPIProfile)   — user picked a profile from combo
    profile_saved(WPIProfile)      — user saved a custom profile
    profile_deleted(str)           — user deleted a profile (id)
    edit_requested()               — user wants to edit current profile
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..utils.wpi_manager import WPIManager, WPIProfile, IntegrityState, empty_data


# ── Integrity badge ───────────────────────────────────────────────────────────

_BADGE = {
    IntegrityState.OK:       ("✅", "#2e7d32", "Integrity verified"),
    IntegrityState.MISMATCH: ("⚠",  "#b71c1c", "Hash mismatch — data may be tampered"),
    IntegrityState.MISSING:  ("❓", "#e65100", "No hash — unverified profile"),
}


# ── Save-As dialog ────────────────────────────────────────────────────────────

class _SaveAsDialog(QDialog):
    def __init__(self, suggested_name: str, suggested_year: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Profile As")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name = QLineEdit(suggested_name)
        self._name.setPlaceholderText("e.g. 2024-user")
        form.addRow("Profile Name:", self._name)

        self._year = QSpinBox()
        self._year.setRange(1900, 2200)
        self._year.setValue(suggested_year)
        form.addRow("Year:", self._year)

        self._remark = QTextEdit()
        self._remark.setPlaceholderText("Optional remarks...")
        self._remark.setFixedHeight(72)
        form.addRow("Remark:", self._remark)

        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    @property
    def name(self) -> str:
        return self._name.text().strip()

    @property
    def year(self) -> int:
        return self._year.value()

    @property
    def remark(self) -> str:
        return self._remark.toPlainText().strip()


# ── _WPISelector ──────────────────────────────────────────────────────────────


class _WPISelector(QWidget):
    profile_selected = Signal(object)   # WPIProfile
    profile_saved    = Signal(object)   # WPIProfile
    profile_deleted  = Signal(str)      # profile id
    edit_requested   = Signal()

    def __init__(self, manager: WPIManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._current: Optional[WPIProfile] = None
        self._build_ui()
        self._populate_combo()
        self._select_first()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Label
        lbl = QLabel("WPI Profile:")
        lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(lbl)

        # Combo
        self._combo = QComboBox()
        self._combo.setMinimumWidth(180)
        self._combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._combo)

        # Integrity badge
        self._badge = QLabel("—")
        self._badge.setFixedWidth(24)
        self._badge.setAlignment(Qt.AlignCenter)
        self._badge.setToolTip("")
        layout.addWidget(self._badge)

        # Buttons
        self._btn_new     = QPushButton("+ New")
        self._btn_save_as = QPushButton("✎ Save As")
        self._btn_delete  = QPushButton("🗑 Delete")

        for btn in (self._btn_new, self._btn_save_as, self._btn_delete):
            btn.setFixedHeight(28)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            layout.addWidget(btn)

        layout.addStretch()

        self._btn_new.clicked.connect(self._on_new)
        self._btn_save_as.clicked.connect(self._on_save_as)
        self._btn_delete.clicked.connect(self._on_delete)

    # ── Combo management ──────────────────────────────────────────────────────

    def _populate_combo(self, select_id: Optional[str] = None):
        self._combo.blockSignals(True)
        self._combo.clear()

        bold = QFont()
        bold.setBold(True)

        for profile in self._manager.all_listed():
            label = profile.name if not profile.is_custom else f"★ {profile.name}"
            self._combo.addItem(label, userData=profile.id)
            idx = self._combo.count() - 1
            if not profile.is_custom:
                self._combo.setItemData(idx, bold, Qt.FontRole)

        self._combo.blockSignals(False)

        # Restore selection
        if select_id:
            for i in range(self._combo.count()):
                if self._combo.itemData(i) == select_id:
                    self._combo.setCurrentIndex(i)
                    break
        elif self._combo.count() > 0:
            self._combo.setCurrentIndex(0)

    def _on_combo_changed(self, idx: int):
        profile_id = self._combo.itemData(idx)
        if not profile_id:
            return
        profile = self._manager.get_by_id(profile_id)
        if profile:
            self._current = profile
            self._update_badge(profile)
            self._update_buttons(profile)
            self.profile_selected.emit(profile)

    def _select_first(self):
        if self._combo.count() > 0:
            self._combo.setCurrentIndex(0)
            self._on_combo_changed(0)

    # ── Badge + button state ──────────────────────────────────────────────────

    def _update_badge(self, profile: WPIProfile):
        icon, color, tip = _BADGE[profile.integrity]
        self._badge.setText(icon)
        self._badge.setToolTip(f"{tip}\n({'DB' if not profile.is_custom else 'Custom'})")
        self._badge.setStyleSheet(f"color: {color}; font-size: 14px;")

    def _update_buttons(self, profile: WPIProfile):
        # Save As — always available (copies current into new custom)
        self._btn_save_as.setEnabled(True)
        self._btn_save_as.setToolTip(
            "Save current table values as a new custom profile"
            if not profile.is_custom
            else "Save changes to this custom profile under a new name"
        )
        # Delete — only for custom
        self._btn_delete.setEnabled(profile.is_custom)
        self._btn_delete.setToolTip(
            "Delete this custom profile"
            if profile.is_custom
            else "DB profiles cannot be deleted"
        )

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def _on_new(self):
        """Create a blank custom profile from scratch."""
        suggested = self._manager.suggest_custom_name("custom")
        dlg = _SaveAsDialog(suggested, 2024, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        name = dlg.name
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Profile name cannot be empty.")
            return

        if self._manager.is_name_taken(name):
            QMessageBox.warning(
                self, "Name Taken",
                f"A profile named '{name}' already exists.\nPlease choose a different name."
            )
            return


        profile = WPIProfile(
            id=f"wpi_custom_{name.replace(' ', '_').lower()}_{dlg.year}",
            name=name,
            year=dlg.year,
            is_custom=True,
            remark=dlg.remark,
            hash="",
            data=empty_data(),
        )
        profile.stamp_hash()
        self._manager.add_custom(profile)
        self._populate_combo(select_id=profile.id)
        self._current = profile
        self._update_badge(profile)
        self._update_buttons(profile)
        self.profile_saved.emit(profile)

    def _on_save_as(self):
        """Save current table state as a new custom profile (or update existing)."""
        if not self._current:
            return

        suggested = self._manager.suggest_custom_name(
            self._current.name if not self._current.is_custom else self._current.name
        )
        dlg = _SaveAsDialog(suggested, self._current.year, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        name = dlg.name
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Profile name cannot be empty.")
            return

        if self._manager.is_name_taken(name, exclude_id=self._current.id):
            QMessageBox.warning(
                self, "Name Taken",
                f"A profile named '{name}' already exists.\nPlease choose a different name."
            )
            return

        # Signal back to parent to collect current table data
        # Parent will call save_profile_data(profile, data) after this signal
        self.edit_requested.emit()

        # Build new profile shell — parent fills data via collect_and_save()
        self._pending_save_meta = {
            "name": name,
            "year": dlg.year,
            "remark": dlg.remark,
        }

    def collect_and_save(self, data: dict):
        """
        Called by parent after edit_requested signal to provide table data.
        Completes the save-as operation.
        """
        if not hasattr(self, "_pending_save_meta") or not self._current:
            return

        meta = self._pending_save_meta
        del self._pending_save_meta

        copy = self._current.make_custom_copy(meta["name"])
        copy.year   = meta["year"]
        copy.remark = meta["remark"]
        copy.data   = data
        copy.stamp_hash()

        self._manager.add_custom(copy)
        self._populate_combo(select_id=copy.id)
        self._current = copy
        self._update_badge(copy)
        self._update_buttons(copy)
        self.profile_saved.emit(copy)

    def _on_delete(self):
        if not self._current or not self._current.is_custom:
            return

        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete custom profile '{self._current.name}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        deleted_id = self._current.id
        self._manager.delete_custom(deleted_id)
        self._current = None
        self._populate_combo()
        self._select_first()
        self.profile_deleted.emit(deleted_id)

    # ── Public API ────────────────────────────────────────────────────────────

    def current_profile(self) -> Optional[WPIProfile]:
        return self._current

    def current_is_custom(self) -> bool:
        return self._current is not None and self._current.is_custom

    def refresh(self, select_id: Optional[str] = None):
        """Repopulate combo, e.g. after external profile changes."""
        self._populate_combo(select_id=select_id or (self._current.id if self._current else None))

    def select_by_id(self, profile_id: str):
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == profile_id:
                self._combo.setCurrentIndex(i)
                return

    def unlisted_warning(self) -> Optional[str]:
        """Return a warning string if any DB profiles were unlisted, else None."""
        if not self._manager.unlisted:
            return None
        names = ", ".join(p.name for p in self._manager.unlisted)
        return (
            f"⚠ The following WPI profiles failed integrity check and were unlisted: {names}. "
            f"The WPI database file may have been tampered with."
        )