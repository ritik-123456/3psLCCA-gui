"""
gui/components/utils/display_format.py

Global numeric display formatting for 3psLCCA.

Change DECIMAL_PLACES once here — it propagates to every table cell,
result label, formula preview, and input field across the app.
"""

DECIMAL_PLACES: int = 3


def fmt(val) -> str:
    """Plain float with global decimal places.  e.g. 1234.5 → '1234.500'"""
    try:
        return f"{float(val):.{DECIMAL_PLACES}f}"
    except (TypeError, ValueError):
        return str(val)


def fmt_comma(val) -> str:
    """Float with thousands separator and global decimal places.  e.g. 12345.6 → '12,345.600'"""
    try:
        return f"{float(val):,.{DECIMAL_PLACES}f}"
    except (TypeError, ValueError):
        return str(val)


def fmt_pct(val) -> str:
    """Percentage — always 1 decimal place regardless of DECIMAL_PLACES."""
    try:
        return f"{float(val):.1f}"
    except (TypeError, ValueError):
        return str(val)


