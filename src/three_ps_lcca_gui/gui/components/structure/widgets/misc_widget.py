from .manager import StructureManagerWidget


class MiscWidget(StructureManagerWidget):
    def __init__(self, controller):
        super().__init__(
            controller=controller,
            chunk_name="str_misc",
            default_components=[
                "Railing  & Crash Barrier & Median",
                "Drainage",
                "Asphalt, Utilities and Other Materials",
                "Waterproofing"
            ],
        )


