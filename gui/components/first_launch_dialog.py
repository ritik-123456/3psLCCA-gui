"""
gui/components/first_launch_dialog.py

First-launch welcome dialog — asks for the user's name.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
)
from gui.theme import PRIMARY, SP2, SP3, SP4, SP6, SP8, SP10, BTN_MD, FS_BASE, FS_MD, FS_DISP, FW_BOLD, FW_MEDIUM
from gui.styles import font, btn_primary, btn_outline


class FirstLaunchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to 3psLCCA")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SP10, SP10, SP10, SP8)
        layout.setSpacing(0)

        # Brand accent bar at top
        accent = QFrame()
        accent.setFixedHeight(4)
        accent.setStyleSheet(f"background: {PRIMARY}; border-radius: 2px;")
        layout.addWidget(accent)
        layout.addSpacing(SP8 - SP2)

        # Title
        title = QLabel("Welcome to 3psLCCA")
        title.setFont(font(FS_DISP - 2, FW_BOLD))
        layout.addWidget(title)
        layout.addSpacing(SP2)

        # Subtitle
        sub = QLabel("Life Cycle Cost Analysis for bridge projects.")
        sub.setFont(font(FS_BASE))
        sub.setEnabled(False)
        layout.addWidget(sub)
        layout.addSpacing(SP8 - SP2)

        # Name field label
        name_lbl = QLabel("What should we call you?")
        name_lbl.setFont(font(FS_BASE, FW_MEDIUM))
        layout.addWidget(name_lbl)
        layout.addSpacing(SP2)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter your name...")
        self.name_edit.setFixedHeight(BTN_MD)
        self.name_edit.returnPressed.connect(self._accept)
        layout.addWidget(self.name_edit)
        layout.addSpacing(SP8)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(SP2)
        btn_row.addStretch()

        self.btn_skip = QPushButton("Skip")
        self.btn_skip.setFixedHeight(BTN_MD)
        self.btn_skip.setFont(font(FS_BASE))
        self.btn_skip.setStyleSheet(btn_outline())
        self.btn_skip.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_skip)

        self.btn_ok = QPushButton("Get Started")
        self.btn_ok.setFixedHeight(BTN_MD)
        self.btn_ok.setFont(font(FS_BASE, FW_MEDIUM))
        self.btn_ok.setDefault(True)
        self.btn_ok.setStyleSheet(btn_primary())
        self.btn_ok.clicked.connect(self._accept)
        btn_row.addWidget(self.btn_ok)

        layout.addLayout(btn_row)

    def _accept(self):
        if self.name_edit.text().strip():
            self.accept()
        else:
            self.reject()

    def get_name(self) -> str:
        return self.name_edit.text().strip()
