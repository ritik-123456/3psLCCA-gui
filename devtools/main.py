"""
devtools/main.py

Entry point for the 3psLCCA Developer Tools standalone app.

Run:
    cd devtools
    python main.py
"""

import sys
from pathlib import Path

# Allow running from inside devtools/ without installing
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from launcher import LauncherWindow


def apply_dark_palette(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor("#1e1e2e"))
    pal.setColor(QPalette.WindowText,      QColor("#cdd6f4"))
    pal.setColor(QPalette.Base,            QColor("#181825"))
    pal.setColor(QPalette.AlternateBase,   QColor("#1e1e2e"))
    pal.setColor(QPalette.ToolTipBase,     QColor("#313244"))
    pal.setColor(QPalette.ToolTipText,     QColor("#cdd6f4"))
    pal.setColor(QPalette.Text,            QColor("#cdd6f4"))
    pal.setColor(QPalette.Button,          QColor("#313244"))
    pal.setColor(QPalette.ButtonText,      QColor("#cdd6f4"))
    pal.setColor(QPalette.BrightText,      QColor("#f38ba8"))
    pal.setColor(QPalette.Highlight,       QColor("#89b4fa"))
    pal.setColor(QPalette.HighlightedText, QColor("#1e1e2e"))
    pal.setColor(QPalette.Link,            QColor("#89dceb"))
    pal.setColor(QPalette.Disabled, QPalette.Text,       QColor("#585b70"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#585b70"))
    app.setPalette(pal)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("3psLCCA Developer Tools")
    apply_dark_palette(app)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


