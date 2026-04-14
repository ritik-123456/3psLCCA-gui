from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QGroupBox,
    QInputDialog,
    QMessageBox,
    QLabel,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer
import time
import uuid
import datetime
import traceback

from .base_table import StructureTableWidget
from .material_dialog import MaterialDialog
from ...utils.validation_helpers import freeze_widgets
from ...utils.display_format import fmt_comma


# ---------------------------------------------------------------------------
# StructureManagerWidget
# ---------------------------------------------------------------------------


class StructureManagerWidget(QWidget):
    def __init__(self, controller, chunk_name, default_components):
        super().__init__()
        self.controller = controller
        self.chunk_name = chunk_name
        self.default_components = default_components
        self.sections = {}
        self.data = {}

        self._frozen = False
        self._add_material_btns = []

        self.main_layout = QVBoxLayout(self)

        # ── Summary bar ──────────────────────────────────────────────────
        summary_bar = QWidget()
        summary_layout = QHBoxLayout(summary_bar)
        summary_layout.setContentsMargins(4, 4, 4, 4)
        self.total_lbl = QLabel("Total: -")
        self.count_lbl = QLabel("Items: -")
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        summary_layout.addWidget(self.total_lbl)
        summary_layout.addWidget(sep)
        summary_layout.addWidget(self.count_lbl)
        summary_layout.addStretch()
        self.main_layout.addWidget(summary_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; }")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.scroll.setWidget(self.container)
        self.main_layout.addWidget(self.scroll)

        btn_layout = QHBoxLayout()
        self.add_comp_btn = QPushButton("+ Add Component Section")
        self.add_comp_btn.clicked.connect(self.add_new_component)
        btn_layout.addWidget(self.add_comp_btn)
        btn_layout.addStretch()
        self.main_layout.addLayout(btn_layout)

    def on_refresh(self):
        try:
            if not self.controller or not getattr(self.controller, "engine", None):
                return

            data = self.controller.engine.fetch_chunk(self.chunk_name) or {}

            if not data and self.default_components:
                for comp in self.default_components:
                    data[comp] = []
                self.controller.engine.stage_update(
                    chunk_name=self.chunk_name, data=data
                )

            info = self.controller.engine.fetch_chunk("general_info") or {}
            self._currency = str(info.get("project_currency", ""))
            self.data = data
            self.refresh_ui()
        except Exception as e:

            print(f"[ERROR] on_refresh crashed: {e}")
            traceback.print_exc()

    def refresh_ui(self):
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        self.sections = {}
        self._add_material_btns = []
        currency = getattr(self, "_currency", "")

        for comp_name, items in self.data.items():
            self.create_section(comp_name)
            table = self.sections.get(comp_name)
            if table:
                table.set_currency(currency)
                for original_index, item in enumerate(items):
                    if not item.get("state", {}).get("in_trash", False):
                        table.add_row(item, original_index)

        self.container_layout.addStretch()
        self.container.adjustSize()
        self._update_summary()

        if getattr(self, "_frozen", False):
            self.freeze(True)

    def _update_summary(self):
        total = 0.0
        count = 0
        for items in self.data.values():
            for item in items:
                if not item.get("state", {}).get("in_trash", False):
                    v = item.get("values", {})
                    total += float(v.get("quantity", 0) or 0) * float(
                        v.get("rate", 0) or 0
                    )
                    count += 1
        currency = getattr(self, "_currency", "")
        suffix = f" ({currency})" if currency else ""
        self.total_lbl.setText(f"Total{suffix}: {fmt_comma(total)}")
        self.count_lbl.setText(f"{count} item{'s' if count != 1 else ''}")

    def create_section(self, name):
        group = QGroupBox(name)
        g_layout = QVBoxLayout(group)

        table = StructureTableWidget(self, name)
        self.sections[name] = table

        add_row_btn = QPushButton(f"Add Material to {name}")
        add_row_btn.clicked.connect(lambda checked=False, n=name: self.open_dialog(n))
        freeze_widgets(self._frozen, add_row_btn)
        self._add_material_btns.append(add_row_btn)

        g_layout.addWidget(table)
        g_layout.addWidget(add_row_btn)
        self.container_layout.addWidget(group)

    def add_material(self, comp_name, values_dict, is_trash=False):
        now = datetime.datetime.now().isoformat()

        included_carbon = values_dict.pop("_included_in_carbon_emission", True)
        included_recycling = values_dict.pop("_included_in_recyclability", True)
        allow_edit_checked = values_dict.pop("_allow_edit_checked", False)
        from_sor = values_dict.pop("_from_sor", False)
        sor_db_key = values_dict.pop("_sor_db_key", "")
        is_excel = values_dict.pop("_is_excel_import", False)
        values_dict.pop("_is_customized", None)
        db_original = values_dict.pop("_db_original", {})
        # `id` may come from an Excel CID#ID column - store it as a reference, not a value field
        _excel_ref_id = values_dict.pop("id", None)
        if _excel_ref_id and "sor_ref_id" not in db_original:
            db_original = dict(db_original)
            db_original["sor_ref_id"] = str(_excel_ref_id)

        # Compute source + source_db_key
        if is_excel:
            source = "excel"
            source_db_key = ""
        elif from_sor:
            is_custom = sor_db_key.startswith("custom::")
            clean_key = sor_db_key.removeprefix("custom::")
            source = "custom_db" if is_custom else "db"
            source_db_key = clean_key
        else:
            source = "manual"
            source_db_key = ""

        new_entry = {
            "id": str(uuid.uuid4()),
            "values": values_dict,
            "meta": {
                "created_on": now,
                "modified_on": now,
                "source": source,
                "source_db_key": source_db_key,
                "db_original": db_original,
            },
            "state": {
                "in_trash": is_trash,
                "included_in_carbon_emission": included_carbon,
                "included_in_recyclability": included_recycling,
                "allow_edit_checked": allow_edit_checked,
            },
        }

        current_data = self.controller.engine.fetch_chunk(self.chunk_name) or {}
        if comp_name not in current_data:
            current_data[comp_name] = []

        current_data[comp_name].append(new_entry)
        self.controller.engine.stage_update(
            chunk_name=self.chunk_name, data=current_data
        )
        self.save_current_state()
        self.on_refresh()

    def _get_project_country(self) -> str:
        try:
            return (
                self.controller.get_chunk("general_info").get("project_country", "")
                or ""
            )
        except Exception:
            return ""

    def _get_project_sor_db(self) -> str:
        try:
            return (
                self.controller.get_chunk("general_info").get("sor_database", "") or ""
            )
        except Exception:
            return ""

    def _existing_names(self, comp_name) -> set:
        """Return lowercased active material names for comp_name."""
        data = self.controller.engine.fetch_chunk(self.chunk_name) or {}
        return {
            item.get("values", {}).get("material_name", "").strip().lower()
            for item in data.get(comp_name, [])
            if not item.get("state", {}).get("in_trash", False)
        }

    def open_dialog(self, comp_name):
        dialog = MaterialDialog(
            comp_name,
            self,
            country=self._get_project_country(),
            sor_db_key=self._get_project_sor_db(),
        )
        if dialog.exec():
            values = dialog.get_values()
            name = values.get("material_name", "").strip()
            if name.lower() in self._existing_names(comp_name):
                QMessageBox.warning(
                    self,
                    "Duplicate Name",
                    f'A material named "{name}" already exists in "{comp_name}".\n'
                    "Use a different name.",
                )
                return
            self.add_material(comp_name, values)

    def open_edit_dialog(self, comp_name, table_row_index):
        try:
            current_data = self.controller.engine.fetch_chunk(self.chunk_name) or {}
            items = current_data.get(comp_name, [])

            active_indices = [
                i
                for i, item in enumerate(items)
                if not item.get("state", {}).get("in_trash", False)
            ]

            if table_row_index < len(active_indices):
                original_idx = active_indices[table_row_index]
                item_to_edit = items[original_idx]

                dialog = MaterialDialog(
                    comp_name,
                    self,
                    data=item_to_edit,
                    country=self._get_project_country(),
                    sor_db_key=self._get_project_sor_db(),
                )
                if dialog.exec():
                    new_values = dialog.get_values()

                    included_carbon = new_values.pop(
                        "_included_in_carbon_emission", True
                    )
                    included_recycling = new_values.pop(
                        "_included_in_recyclability", True
                    )
                    allow_edit_checked = new_values.pop("_allow_edit_checked", False)
                    new_values.pop("_from_sor", None)
                    new_values.pop("_sor_db_key", None)
                    new_values.pop("_is_customized", None)
                    new_values.pop("_is_excel_import", None)
                    # _db_original is the encoded snapshot from get_values()
                    new_db_original = new_values.pop("_db_original", None)

                    item_to_edit["values"] = new_values
                    now = datetime.datetime.now().isoformat()
                    item_to_edit["meta"]["modified_on"] = now
                    # Always overwrite snapshot — dialog rebuilds it fresh on each suggestion.
                    # Keep the existing encoded value when nothing changed (empty string
                    # means no DB source was involved this edit).
                    if new_db_original is not None:
                        item_to_edit["meta"]["db_original"] = new_db_original
                    item_to_edit["state"][
                        "included_in_carbon_emission"
                    ] = included_carbon
                    item_to_edit["state"][
                        "included_in_recyclability"
                    ] = included_recycling
                    item_to_edit["state"]["allow_edit_checked"] = allow_edit_checked

                    self.controller.engine.stage_update(
                        chunk_name=self.chunk_name, data=current_data
                    )
                    self.save_current_state()
                    QTimer.singleShot(0, self.on_refresh)
        except Exception as e:

            print(f"[ERROR] open_edit_dialog crashed: {e}")
            traceback.print_exc()

    def toggle_trash_status(self, comp_name, data_index, should_trash):
        data = self.controller.engine.fetch_chunk(self.chunk_name) or {}
        if comp_name in data and len(data[comp_name]) > data_index:
            if "state" not in data[comp_name][data_index]:
                data[comp_name][data_index]["state"] = {}
            data[comp_name][data_index]["state"]["in_trash"] = should_trash

            self.controller.engine.stage_update(chunk_name=self.chunk_name, data=data)
            self.save_current_state()
            self.on_refresh()

            main_view = self.window().findChild(QWidget, "StructureTabView")
            if main_view and hasattr(main_view, "on_refresh"):
                main_view.on_refresh()

    def add_new_component(self):
        name, ok = QInputDialog.getText(self, "New Component", "Enter Component Name:")
        if ok and name.strip():
            clean_name = name.strip()
            self.create_section(clean_name)
            current_data = self.controller.engine.fetch_chunk(self.chunk_name) or {}
            if clean_name not in current_data:
                current_data[clean_name] = []
                self.controller.engine.stage_update(
                    chunk_name=self.chunk_name, data=current_data
                )
                self.save_current_state()

    def freeze(self, frozen: bool = True):
        self._frozen = frozen
        freeze_widgets(frozen, self.add_comp_btn, *self._add_material_btns)
        for table in self.sections.values():
            table.freeze(frozen)

    def save_current_state(self):
        if self.controller and self.controller.engine:
            eng = self.controller.engine
            eng._last_keystroke_time = time.time()
            eng._has_unsaved_changes = True
            try:
                eng.on_dirty(True)
            except Exception:
                pass


