import os
from PySide6.QtWidgets import QApplication
from gui.project_controller import ProjectController


class ProjectManager:
    def __init__(self):
        self.windows = []

    # --------------------------------------------------------------------------
    # WINDOW HELPERS
    # --------------------------------------------------------------------------

    def _create_window(self):
        from gui.project_window import ProjectWindow

        new_controller = ProjectController()
        win = ProjectWindow(manager=self, controller=new_controller)
        self.windows.append(win)
        return win

    def _find_empty_window(self):
        for win in self.windows:
            if not win.has_project_loaded():
                return win
        return None

    def _find_window_for_project(self, project_id: str):
        for win in self.windows:
            if win.project_id == project_id:
                return win
        return None

    # --------------------------------------------------------------------------
    # PUBLIC API
    # --------------------------------------------------------------------------

    def open_project(self, project_id=None, is_new=False):
        # No project specified — show home screen
        if not project_id and not is_new:
            target = self._find_empty_window() or self._create_window()
            target.show_home()
            target.show()
            target.activateWindow()
            return

        # Project already open — just focus it
        if project_id:
            existing = self._find_window_for_project(project_id)
            if existing:
                existing.show_project_view()
                existing.raise_()
                existing.activateWindow()
                return

        # Ask for details if new
        display_name = None
        country = None
        currency = None
        if is_new:
            from gui.components.new_project_dialog import NewProjectDialog

            dialog = NewProjectDialog()
            if dialog.exec() != NewProjectDialog.Accepted:
                return
            display_name = dialog.get_name()
            country = dialog.get_country()
            currency = dialog.get_currency()

        # Find or create a window
        target = self._find_empty_window() or self._create_window()
        if not target.isVisible():
            target.show()

        # Init project
        success = False
        if is_new:
            new_id = f"proj_{os.urandom(4).hex()}"
            success = target.controller.init_project(
                new_id, is_new=True, display_name=display_name
            )
            if success:
                engine = target.controller.engine
                # Write locked fields into their respective chunks
                engine.stage_update(
                    {
                        "project_name": display_name,
                        "project_country": country,
                        "project_currency": currency,
                    },
                    "general_info",
                )
                engine.stage_update(
                    {"project_country": country},
                    "bridge_data",
                )
                # Force flush to disk NOW — project_loaded fires on the next
                # event loop tick (QTimer.singleShot 0) and refresh_from_engine
                # calls fetch_chunk. Without this the chunks aren't written yet
                # and the widgets load empty.
                engine.force_sync()
        elif project_id:
            success = target.controller.init_project(project_id, is_new=False)

        if success:
            target.project_id = target.controller.active_project_id
            target.show_project_view()
            self.refresh_all_home_screens()
        else:
            target.show_home()

        target.show()
        target.activateWindow()

    def is_project_open(self, project_id: str) -> bool:
        return self._find_window_for_project(project_id) is not None

    def remove_window(self, win):
        if win in self.windows:
            self.windows.remove(win)
        if not self.windows:
            QApplication.quit()

    def refresh_all_home_screens(self):
        for win in self.windows:
            win.home_widget.refresh_project_list()
