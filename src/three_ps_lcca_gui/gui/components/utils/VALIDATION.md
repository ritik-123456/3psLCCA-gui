# Validation Guide

How to add errors and warnings to any data-entry page.

---

## Concepts

| Concept | Purpose | Shown as |
|---|---|---|
| **Error** | Field is required and left blank (text fields only) | Red border + blocks calculation |
| **Warning** | Value is filled but looks unusual | Orange border + allows proceed |

> Numeric fields (`QSpinBox`, `QDoubleSpinBox`) are **never** considered "missing" -
> `0` is a valid value. Use `warn_rules` to catch unusual numeric values including `0`.

---

## Step 1 - Mark required fields

Set `required=True` on a `FieldDef` to make it mandatory.
Only applies to `QLineEdit` fields (text input).

```python
FieldDef(
    "project_name",
    "Project Name",
    "Name of the project.",
    "text",
    required=True,       # blank string → Error
)
```

---

## Step 2 - Define warn_rules

`warn_rules` is a dict that maps a field key to a tuple:

```python
warn_rules = {
    "field_key": (low, high, low_msg, high_msg),
}
```

| Element | Type | Meaning |
|---|---|---|
| `low` | `float \| None` | Warn if value is **below** this |
| `high` | `float \| None` | Warn if value is **above** this |
| `low_msg` | `str` (optional) | Message shown when value is too low |
| `high_msg` | `str` (optional) | Message shown when value is too high |

All elements after `high` are optional. If a message is omitted, a generic one is auto-generated.
Use `None` to skip one side of the range check:

```python
# No messages - generic fallback for both
"rate": (0.01, 40.0)

# One message - used for both low and high violations
"rate": (0.01, 40.0, "Rate looks unusual")

# Two messages - separate message per direction
"rate": (0.01, 40.0, "Rate cannot be 0", "Rate seems too high")

# Only low bound
"cost": (0.01, None, "Cost cannot be 0")
```

### Example - Demolition

```python
WARNING_RULES = {
    "demolition_disposal_cost": (0.01, 40.0,
        "Demolition & Disposal Cost is 0 - cost will not be included",
        "Demolition & Disposal Cost exceeds 40% - please verify"),
    "time_required": (1, 36,
        "Time Required is 0 - duration will not be included",
        "Time Required exceeds 36 months - please verify"),
}
```

---

## Step 3 - Call validate_form

```python
from gui.components.utils.validation_helpers import validate_form

FIELDS = [...]          # your FieldDef / Section list
WARNING_RULES = {...}   # optional

def validate(self) -> dict:
    return validate_form(
        fields=FIELDS,
        widget_owner=self,
        warn_rules=WARNING_RULES,   # omit if no warnings needed
    )
```

`validate_form` returns:

```python
{"errors": ["Missing: Project Name", ...], "warnings": ["Cost looks unusual", ...]}
```

---

## Step 4 - Custom cross-field checks

For checks that span multiple fields (e.g. "severity must sum to 100%"), extend the result manually after calling `validate_form`:

```python
def validate(self) -> dict:
    result = validate_form(FIELDS, self, warn_rules=WARNING_RULES)
    errors   = result["errors"]
    warnings = result["warnings"]

    # Custom error example
    total = self.field_a.value() + self.field_b.value()
    if total != 100.0:
        errors.append("Field A and B must sum to 100%")

    # Custom warning example
    if self.some_field.value() == 0:
        warnings.append("Some Field is 0 - this may affect results")

    return {"errors": errors, "warnings": warnings}
```

---

## Rules at a glance

```
QLineEdit,  required=True,  empty            → Error
QLineEdit,  required=False, empty            → OK (ignored)
Any field,  value in warn range              → OK
Any field,  value outside warn range         → Warning
Any field,  already has Error                → Warning skipped (stays red)
```
