"""
material_catalog.py
===================
Auto-discovers every material database JSON file under a configurable
root folder (default: material_database/), validates each file's
integrity, and writes a single catalog manifest (material_catalog.json)
that downstream tools (search_engine.py, etc.) use to locate and filter
databases by region / city.

Folder convention expected
--------------------------
material_database/
└── <COUNTRY>/                        e.g. INDIA
    ├── <File>.json                   e.g. MumbaiSOR.json        → db_key: INDIA/MumbaiSOR
    └── <REGION>/[<SUB>/...]          e.g. Maharashtra/PWD/
        └── <File>.json               e.g. PWD_SOR.json          → db_key: INDIA/Maharashtra/PWD/PWD_SOR

db_key is the full relative path from the material_database root, without the
.json extension, using forward slashes.  This guarantees uniqueness even when
multiple regions use identically-named JSON files.

Usage
-----
# Build / refresh the registry manifest
python material_catalog.py

# In other modules
from material_catalog import get_registry, get_path, load, check_integrity
"""

import json
import os
import hashlib
import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Root folder that contains <COUNTRY>/<REGION>/ sub-trees
MATERIAL_DB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "material_database")

# Output manifest written by build_registry()
CATALOG_MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "material_catalog.json")

# Schema every SOR JSON file must satisfy
EXPECTED_SCHEMA = {
    "required_top_keys": ["sheetName", "type", "data"],
    "required_item_keys": [
        "name", "unit", "rate", "rate_src",
        "carbon_emission", "carbon_emission_units_den",
        "conversion_factor", "carbon_emission_src",
    ],
    "numeric_item_fields": ["rate", "conversion_factor"],
}


# ─────────────────────────────────────────────────────────────────────────────
#  PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _md5(file_path: str) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_meta(file_path: str) -> dict:
    stat = os.stat(file_path)
    return {
        "size_bytes": stat.st_size,
        "last_modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "md5": _md5(file_path),
    }


def _derive_region_info(json_path: str, root: str) -> dict:
    """
    Walk up the path relative to root and extract:
      country  ← top-level folder under root          (e.g. INDIA)
      region   ← everything between country and file  (e.g. Maharashtra/PWD)
      db_key   ← full relative path without extension   (e.g. INDIA/Maharashtra/PWD/PWD_SOR)

    Using region as a db_key prefix guarantees uniqueness across sub-folders
    even when multiple regions use identically-named JSON files.
    """
    rel          = Path(json_path).relative_to(root)
    parts        = rel.parts   # ('INDIA', 'Maharashtra', 'PWD', 'PWD_SOR.json')

    country      = parts[0]              if len(parts) >= 1 else "UNKNOWN"
    region_parts = list(parts[1:-1])     # everything between country and filename
    stem         = Path(parts[-1]).stem  # drop .json extension

    region = "/".join(region_parts)      # '' when file is directly in country folder
    db_key = "/".join([country] + region_parts + [stem])

    return {"country": country, "region": region, "db_key": db_key}


def _validate_data(data, db_key: str) -> tuple[list[str], list[str]]:
    """
    Returns (errors, warnings) lists for the parsed JSON array.
    Does NOT touch the filesystem.
    """
    errors, warnings = [], []

    if not isinstance(data, list):
        errors.append(f"Top-level must be a JSON array, got {type(data).__name__}.")
        return errors, warnings

    if len(data) == 0:
        warnings.append("File contains an empty array – no records found.")
        return errors, warnings

    required_top  = EXPECTED_SCHEMA["required_top_keys"]
    required_item = EXPECTED_SCHEMA["required_item_keys"]
    numeric_item  = set(EXPECTED_SCHEMA["numeric_item_fields"])

    for idx, record in enumerate(data):
        ref = (f"Record[{idx}] "
               f"(sheetName='{record.get('sheetName','?')}', "
               f"type='{record.get('type','?')}')")

        # Top-level keys
        for key in required_top:
            if key not in record:
                errors.append(f"{ref}: missing top-level key '{key}'.")

        items = record.get("data", [])
        if not isinstance(items, list):
            errors.append(f"{ref}: 'data' field is not a list.")
            continue

        if len(items) == 0:
            warnings.append(f"{ref}: 'data' array is empty.")

        for i_idx, item in enumerate(items):
            iref = f"{ref} › Item[{i_idx}] ('{item.get('name','?')}')"

            for key in required_item:
                if key not in item:
                    errors.append(f"{iref}: missing key '{key}'.")

            for field in numeric_item:
                val = item.get(field)
                if val is None:
                    continue
                if val != "not_available" and not isinstance(val, (int, float)):
                    errors.append(
                        f"{iref}: '{field}' must be numeric or 'not_available', "
                        f"got {type(val).__name__} ({val!r})."
                    )

            if item.get("carbon_emission") == "not_available":
                warnings.append(f"{iref}: carbon_emission is 'not_available'.")

    return errors, warnings


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC – INTEGRITY CHECK (single file, by path OR db_key)
# ─────────────────────────────────────────────────────────────────────────────

def check_integrity_by_path(file_path: str) -> dict:
    """
    Run a full integrity check on any SOR JSON path (no registry required).
    Returns a report dict.
    """
    checked_at = datetime.datetime.now().isoformat()
    result = {
        "path": file_path,
        "status": "OK",
        "errors": [],
        "warnings": [],
        "record_count": 0,
        "file_meta": {},
        "checked_at": checked_at,
    }

    if not os.path.isfile(file_path):
        result["status"] = "FAILED"
        result["errors"].append(f"File not found: {file_path}")
        return result

    result["file_meta"] = _file_meta(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result["status"] = "FAILED"
        result["errors"].append(f"JSON parse error: {e}")
        return result

    errors, warnings = _validate_data(data, Path(file_path).stem)
    result["errors"]   = errors
    result["warnings"] = warnings
    result["record_count"] = len(data) if isinstance(data, list) else 0

    if errors:
        result["status"] = "FAILED"

    return result


def check_integrity(db_key: str) -> dict:
    """
    Run integrity check by db_key (requires registry manifest to exist).
    """
    registry = get_registry()
    if db_key not in registry:
        return {
            "db_key": db_key, "path": None, "status": "FAILED",
            "errors": [f"'{db_key}' not found in registry."],
            "warnings": [], "record_count": 0, "file_meta": {},
            "checked_at": datetime.datetime.now().isoformat(),
        }
    entry    = registry[db_key]
    abs_path = str((Path(CATALOG_MANIFEST_PATH).parent / entry["path"]).resolve())
    report   = check_integrity_by_path(abs_path)
    report["db_key"]  = db_key
    report["country"] = entry.get("country")
    report["region"]  = entry.get("region")
    return report


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC – REGISTRY MANIFEST BUILD  (the core crawler)
# ─────────────────────────────────────────────────────────────────────────────

def build_registry(root: str = MATERIAL_DB_ROOT,
                   manifest_path: str = CATALOG_MANIFEST_PATH) -> dict:
    """
    Crawl `root` recursively, validate every *.json file, and write
    `manifest_path` (material_catalog.json).

    Manifest structure
    ------------------
    {
      "_meta": { "built_at": "...", "root": "...", "total": N, "ok": N, "failed": N },
      "INDIA/Maharashtra/PWD/PWD_SOR": {
          "db_key":   "INDIA/Maharashtra/PWD/PWD_SOR",
          "path":     "/abs/path/to/MumbaiSOR.json",
          "country":  "INDIA",
          "region":   "Maharashtra",
          "status":   "OK" | "FAILED",
          "record_count": 15,
          "sheets":   ["Foundation", "Sub Structure", ...],   ← category list
          "types":    ["Excavation", "Pile", ...],            ← type list
          "errors":   [],
          "warnings": [...],
          "file_meta": { "size_bytes": ..., "last_modified": ..., "md5": ... }
      },
      ...
    }

    Returns the manifest dict.
    """
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Material database root not found: {root}")

    manifest = {}
    json_files = sorted(Path(root).rglob("*.json"))

    for jf in json_files:
        jf_str = str(jf)
        info   = _derive_region_info(jf_str, root)
        db_key = info["db_key"]

        report = check_integrity_by_path(jf_str)

        # Collect sheet / type index for the search engine
        sheets, types = [], []
        if report["status"] == "OK" and report["record_count"] > 0:
            try:
                with open(jf_str, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                sheets = sorted({r.get("sheetName", "") for r in raw if r.get("sheetName")})
                types  = sorted({r.get("type", "")      for r in raw if r.get("type")})
            except Exception:
                pass

        manifest_dir = Path(manifest_path).parent
        rel_path = str(jf.relative_to(manifest_dir))

        manifest[db_key] = {
            "db_key":       db_key,
            "path":         rel_path,
            "country":      info["country"],
            "region":       info["region"],
            "status":       report["status"],
            "record_count": report["record_count"],
            "sheets":       sheets,   # unique sheetName values  → categories
            "types":        types,    # unique type values        → sub-categories
            "errors":       report["errors"],
            "warnings":     report["warnings"],
            "file_meta":    report["file_meta"],
        }

    ok_count     = sum(1 for v in manifest.values() if v["status"] == "OK")
    failed_count = sum(1 for v in manifest.values() if v["status"] == "FAILED")

    manifest_dir = Path(manifest_path).parent
    manifest["_meta"] = {
        "built_at":    datetime.datetime.now().isoformat(),
        "root":        str(Path(root).relative_to(manifest_dir)),
        "total_files": len(json_files),
        "ok":          ok_count,
        "failed":      failed_count,
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[material_catalog] Registry written → {manifest_path}")
    print(f"[material_catalog] Scanned {len(json_files)} file(s): "
          f"{ok_count} OK, {failed_count} FAILED")
    return manifest


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC – REGISTRY ACCESSORS
# ─────────────────────────────────────────────────────────────────────────────

def get_registry(manifest_path: str = CATALOG_MANIFEST_PATH) -> dict:
    """
    Load and return the registry manifest (minus the _meta key).
    Auto-builds the registry if the manifest file does not exist.
    """
    if not os.path.isfile(manifest_path):
        print("[material_catalog] Manifest not found – building now …")
        build_registry()

    with open(manifest_path, "r", encoding="utf-8") as f:
        full = json.load(f)

    return {k: v for k, v in full.items() if k != "_meta"}


def get_path(db_key: str, manifest_path: str = CATALOG_MANIFEST_PATH) -> str:
    """Return absolute path for a registered db_key."""
    registry = get_registry(manifest_path)
    if db_key not in registry:
        raise KeyError(f"'{db_key}' not in registry. "
                       f"Available: {list(registry.keys())}")
    rel_path = registry[db_key]["path"]
    abs_path = str((Path(manifest_path).parent / rel_path).resolve())
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"File for '{db_key}' missing on disk: {abs_path}")
    return abs_path


def list_databases(country: str = None, region: str = None) -> list[dict]:
    """
    Return all registered databases, optionally filtered by country / region.
    Each entry includes db_key, path, country, region, status, sheets, types.
    """
    registry = get_registry()
    result = []
    for entry in registry.values():
        if country and entry.get("country", "").upper() != country.upper():
            continue
        if region and entry.get("region", "").upper() != region.upper():
            continue
        result.append(entry)
    return result


def load(db_key: str, strict: bool = True) -> list[dict]:
    """
    Integrity-check then return parsed JSON for `db_key`.
    Raises RuntimeError on failure when strict=True.
    """
    report = check_integrity(db_key)

    if report["status"] != "OK":
        msg = (f"Integrity check FAILED for '{db_key}':\n"
               + "\n".join(f"  ✗ {e}" for e in report["errors"]))
        if strict:
            raise RuntimeError(msg)
        print(f"[material_catalog WARNING] {msg}")

    for w in report.get("warnings", []):
        print(f"[material_catalog WARNING] {w}")

    path = get_path(db_key)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI  – python material_catalog.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═" * 64)
    print("  DB REGISTRY – BUILD & INTEGRITY REPORT")
    print("═" * 64)

    manifest = build_registry()

    print()
    meta = manifest.get("_meta", {})
    print(f"  Built at   : {meta.get('built_at')}")
    print(f"  Root       : {meta.get('root')}")
    print(f"  Total      : {meta.get('total_files')}  "
          f"( OK: {meta.get('ok')}  FAILED: {meta.get('failed')} )")

    print("\n" + "─" * 64)
    print(f"  {'DB KEY':<20} {'REGION':<20} {'STATUS':<8} {'RECORDS'}")
    print("─" * 64)

    for key, entry in manifest.items():
        if key == "_meta":
            continue
        status_icon = "✓" if entry["status"] == "OK" else "✗"
        print(f"  {key:<20} "
              f"{entry.get('region','?'):<20} "
              f"{status_icon} {entry['status']:<6} "
              f"{entry['record_count']}")
        if entry["errors"]:
            for e in entry["errors"]:
                print(f"      ✗ {e}")
        if entry["warnings"]:
            for w in entry["warnings"]:
                print(f"      ⚠ {w}")


