############# Palette Roles #############
# Window          -> Primary Background color
# AlternateBase   -> Secondary Background color (for sidebar, modals, etc)
# Mid             -> Borders
# Highlight       -> Highlight on select
# Light           -> Highlight on Hover
# Button          -> Button color
# Base            -> Input field background color
# Text            -> Text color
# ButtonText      -> Button text color
# HighlightedText -> Text color for selected elements

from PySide6.QtGui import QPalette, QColor
from gui.theme import PRIMARY, WHITE, BODY_BG, BODY_COLOR, SECONDARY, BORDER, BORDER_SUBTLE

curr_theme = "auto"

accent_dark  = QColor("#6B7D20")
accent_light = QColor(PRIMARY)

##################### DARK THEME PALETTE #####################
dark = QPalette()

dark.setColor(QPalette.Accent, accent_dark)
dark.setColor(QPalette.Window, QColor("#282828"))
dark.setColor(QPalette.AlternateBase, QColor("#333333"))
dark.setColor(QPalette.Midlight, QColor("#484848"))
dark.setColor(QPalette.Mid, QColor("#505050"))
dark.setColor(QPalette.Highlight, accent_dark)
dark.setColor(QPalette.Light, QColor("#555555"))
dark.setColor(QPalette.Button, QColor("#3a3a3a"))
dark.setColor(QPalette.Base, QColor("#3a3a3a"))
dark.setColor(QPalette.Text, QColor("#e2e2e2"))
dark.setColor(QPalette.WindowText, QColor("#e2e2e2"))
dark.setColor(QPalette.ButtonText, QColor("#e2e2e2"))
dark.setColor(QPalette.HighlightedText, QColor("#ffffff"))
dark.setColor(QPalette.PlaceholderText, QColor("#888888"))

##################### LIGHT THEME PALETTE #####################
light = QPalette()

light.setColor(QPalette.Accent, accent_light)
light.setColor(QPalette.Window, QColor(BODY_BG))
light.setColor(QPalette.AlternateBase, QColor(WHITE))
light.setColor(QPalette.Base, QColor(WHITE))
light.setColor(QPalette.Text, QColor(BODY_COLOR))
light.setColor(QPalette.Highlight, accent_light)
light.setColor(QPalette.HighlightedText, QColor("#000000"))
light.setColor(QPalette.Light, QColor(BORDER))
light.setColor(QPalette.Mid, QColor(BORDER_SUBTLE))
light.setColor(QPalette.Button, QColor(WHITE))
light.setColor(QPalette.ButtonText, QColor(BODY_COLOR))
light.setColor(QPalette.PlaceholderText, QColor(SECONDARY))
