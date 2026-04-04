import sys
import os
import time

from PySide6.QtWidgets import (
    QApplication,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QLineEdit,
    QProxyStyle,
    QStyle,
    QTableView,
)
from PySide6.QtCore import QObject, QEvent, Qt, QTimer, QCoreApplication
from PySide6.QtGui import QFontDatabase, QIcon

# Custom UI Components and Managers
from gui.components.splash_screen import SplashScreen
from gui.project_manager import ProjectManager
from gui.themes import get_light_theme, get_dark_theme, resolve_is_dark, track_mode

_QSS_PATH = os.path.join("gui", "assets", "themes", "main.qss")


def _is_dark(scheme=None) -> bool:
    """Return True if the OS is in dark mode."""
    try:
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    except AttributeError:
        pass

    # Windows registry fallback
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return val == 0
    except Exception:
        pass

    return False


def _apply_theme(scheme=None, app: QApplication = None) -> None:
    if app is None:
        app = QApplication.instance()
    raw_dark = _is_dark(scheme)
    is_dark = resolve_is_dark(raw_dark)

    # Update global tracking
    track_mode(is_dark)
    palette, tokens = get_dark_theme() if is_dark else get_light_theme()
    app.setPalette(palette)

    if os.path.exists(_QSS_PATH):
        try:
            with open(_QSS_PATH) as f:
                qss = f.read()
            for token, value in tokens.items():
                qss = qss.replace(token, value)
            app.setStyleSheet(qss)
        except Exception as e:
            print(f"Warning: Could not reload stylesheet: {e}")


# ── Global UI Behavior Overrides ──────────────────────────────────────────────


class _ComboItemStyle(QProxyStyle):
    """Enforces minimum item height in combo popups for Windows."""

    _MIN_H = 36

    def sizeFromContents(self, ct, opt, sz, widget=None):
        size = super().sizeFromContents(ct, opt, sz, widget)
        if ct == QStyle.ContentsType.CT_ItemViewItem and size.height() < self._MIN_H:
            size.setHeight(self._MIN_H)
        return size


class _TableRowSelectFilter(QObject):
    """Enforces row selection and hover tracking on all TableViews."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Polish and isinstance(obj, QTableView):
            obj.setSelectionMode(QTableView.SingleSelection)
            obj.setSelectionBehavior(QTableView.SelectRows)
            obj.setMouseTracking(True)
        return super().eventFilter(obj, event)


class DisableSpinBoxScroll(QObject):
    """Prevents mouse wheel from changing values in SpinBoxes/Combos."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if isinstance(obj, (QSpinBox, QDoubleSpinBox, QComboBox)):
                if obj.parent():
                    QApplication.instance().sendEvent(obj.parent(), event)
                return True
        return super().eventFilter(obj, event)


class SelectTextOnFocus(QObject):
    """Selects all text when a QLineEdit is clicked."""

    watching = None

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonRelease and isinstance(obj, QLineEdit):
            if self.watching != obj and obj.isEnabled():
                self.watching = obj
                obj.selectAll()
        return super().eventFilter(obj, event)


# ── Main Entry Point ──────────────────────────────────────────────────────────


def main():
    # Configure High DPI and Scaling
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR"] = "1"
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar)

    app = QApplication(sys.argv)
    app.setApplicationName("OS Bridge LCCA")
    app.setOrganizationName("OSBridge")

    # Set Window Icon
    _ICON_PATH = os.path.join("gui", "assets", "logo", "logo-3psLCCA.png")
    if os.path.exists(_ICON_PATH):
        app.setWindowIcon(QIcon(_ICON_PATH))

    # Initialize Style and Theme before showing Splash
    app.setStyle(_ComboItemStyle("Fusion"))
    _apply_theme(app.styleHints().colorScheme(), app)

    # Show Custom Splash Screen
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    # Load Bundled Fonts
    _font_dir = os.path.join("gui", "assets", "themes", "Ubuntu_font")
    if os.path.exists(_font_dir):
        for _ttf in [
            "Ubuntu-Light.ttf",
            "Ubuntu-LightItalic.ttf",
            "Ubuntu-Regular.ttf",
            "Ubuntu-Italic.ttf",
            "Ubuntu-Medium.ttf",
            "Ubuntu-MediumItalic.ttf",
            "Ubuntu-Bold.ttf",
            "Ubuntu-BoldItalic.ttf",
        ]:
            QFontDatabase.addApplicationFont(os.path.join(_font_dir, _ttf))

    # Load Custom Units (deferred to start of event loop)
    def _load_custom_units():
        try:
            from gui.components.utils.unit_resolver import load_custom_units

            load_custom_units()
        except Exception as _e:
            print(f"Warning: Could not load custom units: {_e}")

    QTimer.singleShot(0, _load_custom_units)

    # Install Global Event Filters
    app.installEventFilter(DisableSpinBoxScroll())
    app.installEventFilter(_TableRowSelectFilter())
    app.installEventFilter(SelectTextOnFocus())

    # Runtime Theme Switching (Qt 6.5+)
    try:
        app.styleHints().colorSchemeChanged.connect(lambda s: _apply_theme(s, app))
    except AttributeError:
        pass

    # Handle First Launch Dialog
    import core.start_manager as sm

    if sm.is_first_launch():
        from gui.components.first_launch_dialog import FirstLaunchDialog

        dlg = FirstLaunchDialog()
        if dlg.exec() == FirstLaunchDialog.Accepted:
            sm.set_name(dlg.get_name())
        else:
            sm.set_name("")  # Mark as seen

    # Initialize Project Manager and Close Splash
    manager = ProjectManager()

    # splash.finish() handles the minimum display duration internally
    splash.finish()

    manager.open_project()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
