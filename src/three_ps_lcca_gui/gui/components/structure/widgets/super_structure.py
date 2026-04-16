from .manager import StructureManagerWidget


class SuperStructureWidget(StructureManagerWidget):
    def __init__(self, controller):
        super().__init__(
            controller=controller,
            chunk_name="str_super_structure",
            default_components=["Girder", "Deck Slab", "Diaphragm", "Cross Bracings"],
        )


