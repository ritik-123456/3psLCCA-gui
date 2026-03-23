"""
gui/theme.py — Bootstrap-style design tokens (single source of truth).

Usage in QSS:  write  $primary, $border, etc.
               main.py substitutes them at load time via QSS_TOKENS.

Usage in Python:  import the constants directly.

All sizing/spacing/typography tokens are also defined here so that a single
edit propagates to every widget that imports them.
"""

# ── Brand ──────────────────────────────────────────────────────────────────
PRIMARY        = "#90af13"
PRIMARY_HOVER  = "#7c9811"   # ~13 % darker — button hover
PRIMARY_ACTIVE = "#6c830e"   # ~25 % darker — button pressed

# ── Danger ─────────────────────────────────────────────────────────────────
DANGER         = "#ef4444"
DANGER_BG      = "rgba(239,68,68,0.08)"
DANGER_BG_PRESSED = "rgba(239,68,68,0.18)"

# ── Neutrals (Bootstrap 5 tokens) ─────────────────────────────────────────
WHITE          = "#ffffff"
BODY_BG        = "#f8f9fa"   # app window / sidebar background
BODY_COLOR     = "#212529"   # primary text
SECONDARY      = "#6c757d"   # muted / secondary text
BORDER         = "#dee2e6"   # standard border
BORDER_SUBTLE  = "#ced4da"   # slightly darker border (inputs on hover)
MUTED          = "#adb5bd"   # disabled / placeholder elements
SURFACE        = "#e9ecef"   # neutral hover background
SURFACE_ACTIVE = "#dee2e6"   # neutral pressed background
CARD_BG        = "#ffffff"   # card / list-item explicit background

# ── Sidebar states (pre-computed solid — no alpha blending) ───────────────
# PRIMARY at 12% on BODY_BG (#f8f9fa) → fully opaque light green
SIDEBAR_HOVER  = "#ecf0de"
# PRIMARY at 25% on BODY_BG (#f8f9fa) → fully opaque medium green
SIDEBAR_SEL    = "#dee7c0"

# ── Spacing (Bootstrap spacer multiples, in px) ────────────────────────────
# Base spacer = 4px  (Bootstrap uses 1rem = 16px; we use 4px steps)
SP1  =  4
SP2  =  8
SP3  = 12
SP4  = 16
SP5  = 20
SP6  = 24
SP8  = 32
SP10 = 40

# ── Border radius ──────────────────────────────────────────────────────────
RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 8
RADIUS_XL = 12

# ── Button heights ─────────────────────────────────────────────────────────
BTN_SM = 28   # compact / icon-adjacent (refresh, banner)
BTN_MD = 36   # standard (load, open, delete, return)
BTN_LG = 40   # primary CTA (new project)

# ── Typography ─────────────────────────────────────────────────────────────
FONT_FAMILY = "Ubuntu"

# Point sizes
FS_XS   =  7   # badge pill, tertiary hint
FS_SM   =  8   # caption, overline label, sort buttons, refresh
FS_BASE =  9   # body text, standard buttons
FS_MD   = 10   # sidebar row name, banner label
FS_LG   = 11   # grid card title
FS_XL   = 15   # logo / brand mark
FS_DISP = 18   # greeting display heading

# Font weights (match QFont.Weight int values — no Qt import needed here)
FW_LIGHT    = 300
FW_NORMAL   = 400
FW_MEDIUM   = 500
FW_SEMIBOLD = 600
FW_BOLD     = 700

# ── QSS substitution map — light theme ─────────────────────────────────────
# Keys are sorted longest-first so that e.g. "$border-subtle" is replaced
# before "$border" when main.py iterates in insertion order.
QSS_TOKENS: dict[str, str] = {
    "$primary-hover":  PRIMARY_HOVER,
    "$primary-active": PRIMARY_ACTIVE,
    "$border-subtle":  BORDER_SUBTLE,
    "$surface-active": SURFACE_ACTIVE,
    "$body-color":     BODY_COLOR,
    "$secondary":      SECONDARY,
    "$primary":        PRIMARY,
    "$body-bg":        BODY_BG,
    "$border":         BORDER,
    "$surface":        SURFACE,
    "$muted":          MUTED,
    "$white":          WHITE,
}

# ── QSS substitution map — dark theme ──────────────────────────────────────
DARK_QSS_TOKENS: dict[str, str] = {
    "$primary-hover":  PRIMARY_HOVER,    # brand stays the same
    "$primary-active": PRIMARY_ACTIVE,
    "$border-subtle":  "#5a5a5a",
    "$surface-active": "#525252",
    "$body-color":     "#e2e2e2",        # primary text on dark bg
    "$secondary":      "#a0a0a0",
    "$primary":        PRIMARY,
    "$body-bg":        "#282828",        # app window background
    "$border":         "#505050",
    "$surface":        "#4a4a4a",        # hover surface
    "$muted":          "#686868",
    "$white":          "#3a3a3a",        # elevated surface (inputs, cards)
}
