import sys
import os
import platform

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
from gui.themes import reapply as _reapply
import ctypes
from gui.components.utils.unit_resolver import load_custom_units



# ── Global UI Behavior Overrides ──────────────────────────────────────────────


class _ComboItemStyle(QProxyStyle):
    """Enforces minimum item height in combo popups and removes the harsh OS drop shadow."""

    _MIN_H = 36

    def sizeFromContents(self, ct, opt, sz, widget=None):
        size = super().sizeFromContents(ct, opt, sz, widget)
        if ct == QStyle.ContentsType.CT_ItemViewItem and size.height() < self._MIN_H:
            size.setHeight(self._MIN_H)
        return size

    def styleHint(self, hint, opt=None, widget=None, returnData=None):
        if hint == QStyle.SH_ComboBox_Popup:
            return 0  # keep combobox-popup: 0 behaviour
        return super().styleHint(hint, opt, widget, returnData)

    def drawComplexControl(self, cc, opt, p, widget=None):
        super().drawComplexControl(cc, opt, p, widget)
        # Remove OS drop shadow from the popup view after it is shown
        if cc == QStyle.CC_ComboBox and widget is not None:
            view = getattr(widget, "view", None)
            if callable(view):
                v = view()
                if v and v.window():
                    w = v.window()
                    flags = w.windowFlags()
                    if not (flags & Qt.NoDropShadowWindowHint):
                        w.setWindowFlags(flags | Qt.NoDropShadowWindowHint)
                        w.show()


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
    # Windows: set AppUserModelID before QApplication so Task Manager
    # shows the app icon instead of the Python interpreter icon.
    if platform.system() == "Windows":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "OSBridge.3psLCCA"
            )
        except Exception:
            pass

    # Configure High DPI and Scaling
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR"] = "1"
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar)

    app = QApplication(sys.argv)
    app.setApplicationName("OS Bridge LCCA")
    app.setOrganizationName("OSBridge")

    # Set Window Icon
    _ICON_PATH = os.path.join("gui", "assets", "logo", "logo-3psLCCA.ico")
    if os.path.exists(_ICON_PATH):
        app.setWindowIcon(QIcon(_ICON_PATH))

    # Linux: link to .desktop file so taskbar/task-manager uses the app icon
    if platform.system() == "Linux":
        app.setDesktopFileName("3psLCCA")

    # Initialize Style and Theme before showing Splash
    app.setStyle(_ComboItemStyle("Fusion"))
    _reapply(app)

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

            load_custom_units()
        except Exception as _e:
            print(f"Warning: Could not load custom units: {_e}")

    QTimer.singleShot(0, _load_custom_units)

    # Install Global Event Filters
    # NOTE: named references required — Python GC will collect anonymous instances
    wheel_filter = DisableSpinBoxScroll()
    table_filter = _TableRowSelectFilter()
    focus_filter = SelectTextOnFocus()
    app.installEventFilter(wheel_filter)
    app.installEventFilter(table_filter)
    app.installEventFilter(focus_filter)

    # Runtime Theme Switching (Qt 6.5+)
    try:
        app.styleHints().colorSchemeChanged.connect(lambda s: _reapply(app))
    except AttributeError:
        pass

    # Handle First Launch Dialog
    import core.start_manager as sm

    if sm.is_first_launch():
        from gui.components.first_launch_dialog import FirstLaunchDialog

        splash.hide()
        dlg = FirstLaunchDialog()
        if dlg.exec() == FirstLaunchDialog.Accepted:
            sm.set_name(dlg.get_name())
        else:
            sm.set_name("")  # Mark as seen

    # Initialize Project Manager and Close Splash
    manager = ProjectManager()

    # Heavy work first — splash stays visible during entire load
    manager.open_project()

    # Pass main window so Qt waits until it's visible AND MIN_DISPLAY_MS has elapsed
    main_win = manager.windows[0] if manager.windows else None
    splash.finish(main_win)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()


