import sys
import os
from PySide6.QtWidgets import QApplication, QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtGui import QFocusEvent, QMouseEvent
from gui.project_manager import ProjectManager
from gui.palette_manager import dark, light


def _apply_theme(scheme: Qt.ColorScheme, app: QApplication) -> None:
    """
    Take the current OS palette exactly as-is and only override the
    interaction roles with the green accent. Nothing else is touched —
    surfaces, text, borders all stay native.
    """
    if scheme == Qt.ColorScheme.Light:
        app.setPalette(light)
    else:
        app.setPalette(dark)
    app.setStyleSheet(app.styleSheet())
    


# ── Wheel blocker ─────────────────────────────────────────────────────────────
class DisableSpinBoxScroll(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if isinstance(obj, (QSpinBox, QDoubleSpinBox, QComboBox)):
                if obj.parent():
                    QApplication.instance().sendEvent(obj.parent(), event)
                return True
        return super().eventFilter(obj, event)

# Select text when a QLineEdit is pressed
class SelectTextOnFocus(QObject):
    watching = None
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonRelease and isinstance(obj, QLineEdit):
            if self.watching != obj:
                self.watching = obj
                obj.selectAll()
        return super().eventFilter(obj, event)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR"] = "1.1"

    app = QApplication(sys.argv)

    # Load user-defined custom units from DB into the global cache
    try:
        from gui.components.utils.unit_resolver import load_custom_units
        load_custom_units()
    except Exception as _e:
        print(f"Warning: Could not load custom units: {_e}")

    wheel_filter = DisableSpinBoxScroll()
    app.installEventFilter(wheel_filter)
    
    focus_filter = SelectTextOnFocus()
    app.installEventFilter(focus_filter)

    app.setApplicationName("OS Bridge LCCA")
    app.setOrganizationName("OSBridge")

    qss_path = os.path.join("gui", "assets", "themes", "main.qss")
    if os.path.exists(qss_path):
        try:
            with open(qss_path, "r") as f:
                app.setStyleSheet(f.read())
        except Exception as e:
            print(f"Warning: Could not load stylesheet: {e}")

    # Stamp accent onto whatever palette the OS is currently using
    _apply_theme(app.styleHints().colorScheme, app)
    app.setStyle("Fusion")

    # Re-apply when OS switches dark ↔ light (Qt 6.5+)
    try:
        app.styleHints().colorSchemeChanged.connect(lambda scheme: _apply_theme(scheme, app))
    except AttributeError:
        pass

    manager = ProjectManager()
    manager.open_project()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()