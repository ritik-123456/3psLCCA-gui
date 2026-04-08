"""
gui/components/settings_dialog.py

SettingsPanel  — reusable form widget (name + theme pickers).
                 Embedded by both SettingsDialog and FirstLaunchDialog.

SettingsDialog — sidebar gear-button dialog (Save / Cancel).
"""

import core.start_manager as sm
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QTabWidget,
    QMessageBox,
)
import json
from gui.themes import (
    list_themes,
    get_theme_name,
    set_active_theme,
    set_appearance_mode,
    reapply,
)
import gui.themes as _themes
from gui.styles import btn_outline, font
from gui.theme import FS_SM, FW_MEDIUM
from gui.components.agency_profile_dialog import AgencyProfileForm


# ── Shared form panel ─────────────────────────────────────────────────────────


class SettingsPanel(QWidget):
    """
    The shared settings form — display name + light/dark theme pickers.
    Contains no buttons or title; embed this inside any dialog.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── Display Name ──────────────────────────────────────────────────
        layout.addWidget(QLabel("<b>Display Name</b>"))

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Enter your name…")
        self._name_edit.setFixedHeight(34)
        self._name_edit.setText(sm.get_profile().get("display_name", ""))
        self._name_edit.textChanged.connect(
            lambda: (
                self._name_edit.setStyleSheet("")
                if self._name_edit.text().strip()
                else None
            )
        )
        layout.addWidget(self._name_edit)

        layout.addSpacing(4)

        # ── Appearance Mode ───────────────────────────────────────────────
        layout.addWidget(QLabel("<b>Appearance Mode</b>"))

        self._mode_combo = QComboBox()
        self._mode_combo.setFixedHeight(34)
        for value, label in [
            ("auto", "Auto (follow OS)"),
            ("light", "Light"),
            ("dark", "Dark"),
        ]:
            self._mode_combo.addItem(label, userData=value)
            if value == _themes.APPEARANCE_MODE:
                self._mode_combo.setCurrentIndex(self._mode_combo.count() - 1)
        layout.addWidget(self._mode_combo)

        layout.addSpacing(4)

        # ── Light Theme ───────────────────────────────────────────────────
        layout.addWidget(QLabel("<b>Light Theme</b>"))

        self._light_combo = self._theme_combo("light", _themes.ACTIVE_LIGHT)
        layout.addWidget(self._light_combo)

        layout.addSpacing(4)

        # ── Dark Theme ────────────────────────────────────────────────────
        layout.addWidget(QLabel("<b>Dark Theme</b>"))

        self._dark_combo = self._theme_combo("dark", _themes.ACTIVE_DARK)
        layout.addWidget(self._dark_combo)

        theme_hint = QLabel("Theme changes apply immediately on save.")
        theme_hint.setEnabled(False)
        layout.addWidget(theme_hint)
        
        layout.addStretch()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_name(self) -> str:
        return self._name_edit.text().strip()

    def save(self) -> None:
        """Persist name + theme choices; re-applies theme live if anything changed."""
        sm.set_name(self.get_name())

        mode = self._mode_combo.currentData()
        light_mod = self._light_combo.currentData()
        dark_mod = self._dark_combo.currentData()

        changed = (
            mode != _themes.APPEARANCE_MODE
            or light_mod != _themes.ACTIVE_LIGHT
            or dark_mod != _themes.ACTIVE_DARK
        )

        set_appearance_mode(mode)
        set_active_theme("light", light_mod)
        set_active_theme("dark", dark_mod)

        if changed:
            reapply()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _theme_combo(self, variant: str, current: str) -> QComboBox:
        combo = QComboBox()
        combo.setFixedHeight(34)
        for module_name in list_themes(variant):
            combo.addItem(get_theme_name(variant, module_name), userData=module_name)
            if module_name == current:
                combo.setCurrentIndex(combo.count() - 1)
        return combo


# ── Settings dialog (sidebar gear button) ─────────────────────────────────────


class SettingsDialog(QDialog):
    """
    Settings dialog opened from the sidebar gear button.
    Framing: plain title bar + Save / Cancel.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedWidth(500)
        self.setFixedHeight(650)
        self.setModal(True)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)

        self.tabs = QTabWidget()
        
        self._panel = SettingsPanel(self)
        self.tabs.addTab(self._panel, "General Settings")
        
        # ── Add Profile Tab ──
        self.add_profile_tab = QWidget()
        add_profile_layout = QVBoxLayout(self.add_profile_tab)
        add_profile_layout.setContentsMargins(10, 10, 10, 10)
        add_profile_layout.setSpacing(10)
        
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("<b>Save Profile As:</b>"))
        self.add_profile_name_edit = QLineEdit()
        self.add_profile_name_edit.setPlaceholderText("Enter a new profile name to save...")
        name_layout.addWidget(self.add_profile_name_edit)
        add_profile_layout.addLayout(name_layout)
        
        self.add_profile_form = AgencyProfileForm()
        add_profile_layout.addWidget(self.add_profile_form)
        
        self.tabs.addTab(self.add_profile_tab, "Add Profile")
        
        # ── Edit/Delete Profile Tab ──
        self.edit_profile_tab = QWidget()
        edit_profile_layout = QVBoxLayout(self.edit_profile_tab)
        edit_profile_layout.setContentsMargins(10, 10, 10, 10)
        edit_profile_layout.setSpacing(10)
        
        edit_top_layout = QHBoxLayout()
        edit_top_layout.addWidget(QLabel("<b>Select Profile:</b>"))
        
        self.edit_profile_combo = QComboBox()
        self.btn_delete_profile = QPushButton("🗑️ Delete")
        self.btn_delete_profile.setFixedWidth(80)
        self.btn_delete_profile.clicked.connect(self._delete_profile)
        
        edit_top_layout.addWidget(self.edit_profile_combo)
        edit_top_layout.addWidget(self.btn_delete_profile)
        edit_profile_layout.addLayout(edit_top_layout)
        
        self.edit_profile_form = AgencyProfileForm()
        edit_profile_layout.addWidget(self.edit_profile_form)
        
        self._populate_profiles()
        self.edit_profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        
        self.tabs.addTab(self.edit_profile_tab, "Edit/Delete Profile")
        
        layout.addWidget(self.tabs)

        layout.addSpacing(8)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_accept(self):
        self._panel.save()
        
        current_tab_title = self.tabs.tabText(self.tabs.currentIndex())
        
        if current_tab_title == "Add Profile":
            profile_name = self.add_profile_name_edit.text().strip()
            if profile_name:
                self.add_profile_form.save_to_json(profile_name)
            else:
                data = self.add_profile_form.get_data_dict()
                sm.set_pref("agency_profile", json.dumps(data))
                
        elif current_tab_title == "Edit/Delete Profile" and self.edit_profile_form.isEnabled():
            profile_name = self.edit_profile_combo.currentText().strip()
            if profile_name:
                self.edit_profile_form.save_to_json(profile_name)
            
        self.accept()

    def _populate_profiles(self):
        self.edit_profile_combo.blockSignals(True)
        self.edit_profile_combo.clear()
        
        profiles = self.edit_profile_form.get_available_profiles()
        for name in profiles.keys():
            self.edit_profile_combo.addItem(name)
            
        self.edit_profile_combo.blockSignals(False)
        
        if self.edit_profile_combo.count() > 0:
            self.edit_profile_form.setEnabled(True)
            self.btn_delete_profile.setEnabled(True)
            self._on_profile_selected(self.edit_profile_combo.currentIndex())
        else:
            self.edit_profile_form.setEnabled(False)
            self.btn_delete_profile.setEnabled(False)

    def _on_profile_selected(self, index):
        if index < 0: return
        name = self.edit_profile_combo.itemText(index)
        profiles = self.edit_profile_form.get_available_profiles()
        if name in profiles:
            self.edit_profile_form.load_data_dict(profiles[name])

    def _delete_profile(self):
        name = self.edit_profile_combo.currentText().strip()
        if not name:
            return
            
        profiles = self.edit_profile_form.get_available_profiles()
        if name not in profiles:
            QMessageBox.warning(self, "Delete Profile", f"Profile '{name}' does not exist.")
            return
            
        reply = QMessageBox.question(
            self, "Delete Profile", f"Are you sure you want to delete profile '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.edit_profile_form.delete_from_json(name)
            self._populate_profiles()
