from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from gui.components.carbon_emission.widgets.material_emissions import MaterialEmissions
from gui.components.carbon_emission.widgets.transport_emissions import (
    TransportEmissions,
)
from gui.components.carbon_emission.widgets.machinery_emissions import (
    MachineryEmissions,
)
from gui.components.carbon_emission.widgets.traffic_emissions import TrafficEmissions
from gui.components.carbon_emission.widgets.social_cost import SocialCost


class CarbonEmissionTabView(QWidget):
    def __init__(self, controller=None):
        super().__init__()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.tab_view = QTabWidget()

        # QTabWidget's content pane paints using the Base palette role, which
        # differs from Window in dark mode (gray vs black).
        # Fix: copy the Window color into the Base role so both paint identically,
        # no QSS needed — this follows the active theme automatically.
        palette = self.tab_view.palette()
        palette.setColor(QPalette.Base, palette.color(QPalette.Window))
        self.tab_view.setPalette(palette)

        self.tab_view.addTab(
            MaterialEmissions(controller=controller), "Material Emissions"
        )
        self.tab_view.addTab(
            TransportEmissions(controller=controller), "Transportation Emissions"
        )
        self.tab_view.addTab(
            MachineryEmissions(controller=controller), "Machinery Emissions"
        )
        self.tab_view.addTab(
            TrafficEmissions(controller=controller), "Traffic Diversion Emissions"
        )
        self.tab_view.addTab(SocialCost(controller=controller), "Social Cost of Carbon")

        main_layout.addWidget(self.tab_view)

    def select_tab(self, name):
        tabs = [
            "Material Emissions",
            "Transportation Emissions",
            "Machinery Emissions",
            "Traffic Diversion Emissions",
            "Social Cost of Carbon",
        ]
        if name in tabs:
            self.tab_view.setCurrentIndex(tabs.index(name))
