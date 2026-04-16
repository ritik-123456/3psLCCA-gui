"""
gui/components/utils/display_format.py

Global numeric display formatting for 3psLCCA.

Change DECIMAL_PLACES once here - it propagates to every table cell,
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


def fmt_currency(val, currency="INR", decimals=None) -> str:
    """Formats values using Indian numbering system if currency is INR."""
    try:
        v = float(val)
        d = DECIMAL_PLACES if decimals is None else decimals
        
        if currency != "INR":
            return f"{v:,.{d}f}"
            
        # Indian Numbering System: 12,34,567.89
        s = f"{v:.{d}f}"
        parts = s.split(".")
        integer_part = parts[0]
        decimal_part = "." + parts[1] if len(parts) > 1 else ""
        
        if len(integer_part) <= 3:
            return integer_part + decimal_part
            
        last_three = integer_part[-3:]
        rest = integer_part[:-3]
        
        # Group rest by 2
        groups = []
        while rest:
            groups.append(rest[-2:])
            rest = rest[:-2]
        
        return ",".join(reversed(groups)) + "," + last_three + decimal_part
        
    except (TypeError, ValueError):
        return str(val)


def fmt_pct(val) -> str:
    """Percentage - always 1 decimal place regardless of DECIMAL_PLACES."""
    try:
        return f"{float(val):.1f}"
    except (TypeError, ValueError):
        return str(val)
