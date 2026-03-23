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
# Light           -> Text color for elements, highlighted on hover


from PySide6.QtGui import QPalette, QColor

curr_theme = "auto"

accent_dark = QColor("#6B7D20")
accent_light = QColor("#91b014")

##################### DARK THEME PALETTE #####################
dark = QPalette()

dark.setColor(QPalette.Accent, accent_dark)
dark.setColor(QPalette.Window, QColor("#282828"))
dark.setColor(QPalette.AlternateBase, QColor("#333333"))
dark.setColor(QPalette.Mid, QColor("#d6d8d2"))
dark.setColor(QPalette.Highlight, accent_dark)
dark.setColor(QPalette.Light, QColor("#4d4d4d"))
dark.setColor(QPalette.Button, QColor("#282828"))
dark.setColor(QPalette.Base, QColor("#404040"))
dark.setColor(QPalette.Text, QColor("#ffffff"))
dark.setColor(QPalette.HighlightedText, QColor("#000000"))
dark.setColor(QPalette.ButtonText, QColor("#ffffff"))

##################### LIGHT THEME PALETTE #####################
light = QPalette()

light.setColor(QPalette.Accent, accent_light)
light.setColor(QPalette.Window, QColor("#f4f4f4"))
light.setColor(QPalette.AlternateBase, QColor("#fcfcfc"))
light.setColor(QPalette.Mid, accent_light)
light.setColor(QPalette.Highlight, accent_light)
light.setColor(QPalette.Light, QColor("#cccccc"))
light.setColor(QPalette.Button, QColor("#ffffff"))
light.setColor(QPalette.Base, QColor("#ffffff"))
light.setColor(QPalette.Text, QColor("#000000"))
light.setColor(QPalette.HighlightedText, QColor("#000000"))
light.setColor(QPalette.ButtonText, QColor("#000000"))