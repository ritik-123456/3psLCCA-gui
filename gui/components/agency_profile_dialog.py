"""
gui/components/agency_profile_dialog.py
"""

import os
import json
from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QInputDialog, QMessageBox
from core import start_manager as sm

from gui.components.base_widget import ScrollableForm
from gui.components.global_info.main import AGENCY_FIELDS, BASE_DOCS_URL
from gui.components.utils.form_builder.form_builder import build_form
from gui.components.utils.form_builder.form_definitions import Section


class AgencyProfileForm(ScrollableForm):
    """
    A standalone form for the Agency evaluating fields that
    saves profiles into data/user_db/profile.json to support multiple profiles.
    """
    def __init__(self):
        super().__init__(controller=None, chunk_name="agency_profile")
        
        # Remove the heading section since the tab itself serves as the heading
        fields_no_heading = [f for f in AGENCY_FIELDS if not isinstance(f, Section)]
        self.required_keys = build_form(self, fields_no_heading, BASE_DOCS_URL)
        
        # Try to load latest saved from preferences soform isn't empty if opened repeatedly
        saved = sm.get_pref("agency_profile", "{}")
        try:
            data = json.loads(saved)
            if data:
                self.load_data_dict(data)
        except Exception:
            pass

    def save_to_json(self, profile_name: str):
        data = self.get_data_dict()
        
        dir_path = os.path.join("data", "user_db")
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, "profile.json")
        
        profiles = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():
                        profiles = json.loads(content)
            except Exception:
                pass
        
        profiles[profile_name] = data
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=4)
            
        # Also store the latest one as default for auto-populating new projects
        sm.set_pref("agency_profile", json.dumps(data))

    def get_available_profiles(self) -> dict:
        file_path = os.path.join("data", "user_db", "profile.json")
        if not os.path.exists(file_path):
            return {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    return json.loads(content)
        except Exception:
            pass
        return {}

    def delete_from_json(self, profile_name: str) -> bool:
        profiles = self.get_available_profiles()
        if profile_name in profiles:
            del profiles[profile_name]
            file_path = os.path.join("data", "user_db", "profile.json")
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(profiles, f, indent=4)
                return True
            except Exception:
                pass
        return False


class AgencyProfileDialog(QDialog):
    """
    Popup dialog to let users save an Agency Profile.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Agency Profile")
        self.setFixedWidth(500)
        self.setFixedHeight(650)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self.profile_form = AgencyProfileForm()
        layout.addWidget(self.profile_form)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.save_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def save_and_accept(self):
        profile_name, ok = QInputDialog.getText(
            self, "Profile Name", "Enter a name for this profile:"
        )
        if ok and profile_name.strip():
            self.profile_form.save_to_json(profile_name.strip())
            self.accept()
        elif ok:
            QMessageBox.warning(self, "Invalid Name", "Profile name cannot be empty.")
