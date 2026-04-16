"""
search_engine.py
================
Loads material databases from the catalog (material_catalog.json) and
provides category-wise listing and full-text search across one or
more regional SOR files.

Key public API
--------------
engine = MaterialSearchEngine()                    # loads all OK databases
engine = MaterialSearchEngine(region="Maharashtra")# filter by region
engine = MaterialSearchEngine(db_keys=["MumbaiSOR"])

engine.list_categories()                          # all sheetName values
engine.list_by_category("Foundation")            # all records in category
engine.list_by_category("Foundation", "Pile")    # filter to type too
engine.search("steel rebar")                      # full-text across all
engine.search("steel rebar", category="Foundation")
engine.search("PVC", region="Delhi")
"""

import json
import re
from three_ps_lcca_gui.gui.components.structure.registry.material_catalog import get_registry, get_path, list_databases


# ─────────────────────────────────────────────────────────────────────────────
#  LOW-LEVEL TEXT UTILITIES  (original AdvancedSearchEngine logic, extended)
# ─────────────────────────────────────────────────────────────────────────────

class AdvancedSearchEngine:
    @staticmethod
    def normalize(text: str) -> str:
        """Lowercase, strip special chars, collapse spaces."""
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'[(),\-/]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Split normalized text into word tokens."""
        normalized = AdvancedSearchEngine.normalize(text)
        return normalized.split() if normalized else []

    @staticmethod
    def _token_matches(tok: str, item: str) -> bool:
        """
        Check if a single query token matches within the item text.

        Normalizes both inputs internally, so callers need not pre-process.

        Handles two cases:
          1. Direct substring:  "m35"   in "concrete 500 mm m35"   → True
          2. Concatenated unit: "500mm" → split to ["500", "mm"],
             both substrings present in "concrete 500 mm m35"       → True
        """
        tok  = AdvancedSearchEngine.normalize(tok)
        item = AdvancedSearchEngine.normalize(item)
        # Fast path – direct substring
        if tok in item:
            return True
        # Split on digit↔letter boundaries (e.g. "500mm" → ["500","mm"],
        # "m35" → ["m","35"]) and require every part to be present.
        parts = re.findall(r'[a-z]+|\d+', tok)
        if len(parts) > 1:
            return all(p in item for p in parts)
        return False

    @staticmethod
    def is_match(query: str, item_name: str) -> bool:
        """
        True if every query token appears somewhere in the item name.
        Order-independent, partial-word and concatenated-unit aware.

        Examples that all return True
        ─────────────────────────────
        query "m35 500 mm"  →  item "Concrete 500 mm (m35)"
        query "500mm m35"   →  item "Concrete 500 mm (m35)"
        query "concrete m35"→  item "Concrete 500 mm (m35)"
        """
        tokens          = AdvancedSearchEngine.tokenize(query)
        normalized_item = AdvancedSearchEngine.normalize(item_name)
        return all(
            AdvancedSearchEngine._token_matches(tok, normalized_item)
            for tok in tokens
        )


# ─────────────────────────────────────────────────────────────────────────────
#  MATERIAL SEARCH ENGINE  (registry-aware)
# ─────────────────────────────────────────────────────────────────────────────

class MaterialSearchEngine:
    """
    Loads validated SOR databases from the registry and exposes
    category-wise listing and full-text search.

    Parameters
    ----------
    db_keys : list[str] | None
        Explicit list of db_keys to load.  If None, loads all OK databases
        (optionally filtered by country / region).
    country : str | None
        Filter by country folder name (e.g. "INDIA").
    region  : str | None
        Filter by region sub-folder (e.g. "Maharashtra").
    """

    def __init__(self,
                 db_keys: list[str] | None = None,
                 country: str | None = None,
                 region:  str | None = None):

        self._registry = get_registry()
        self._data: dict[str, list[dict]] = {}   # db_key → raw JSON list

        # Determine which db_keys to load
        if db_keys:
            keys_to_load = [k for k in db_keys if k in self._registry]
        else:
            entries      = list_databases(country=country, region=region)
            keys_to_load = [e["db_key"] for e in entries
                            if e["status"] == "OK"]

        for key in keys_to_load:
            try:
                path = get_path(key)
                with open(path, "r", encoding="utf-8") as f:
                    self._data[key] = json.load(f)
            except Exception as e:
                print(f"[search_engine] Skipping '{key}': {e}")

        if not self._data:
            print("[search_engine] Warning: no databases loaded.")

    # ── internal helpers ───────────────────────────────────────────────────

    def _iter_items(self,
                    db_key:   str | None = None,
                    category: str | None = None,
                    mat_type: str | None = None):
        """
        Yield flat dicts: every item enriched with db_key, region,
        sheetName (= category), and type.
        """
        registry = self._registry
        sources  = {db_key: self._data[db_key]} if db_key else self._data

        for key, records in sources.items():
            meta   = registry.get(key, {})
            region = meta.get("region", "")

            for record in records:
                sheet = record.get("sheetName", "")
                rtype = record.get("type", "")

                if category and sheet.lower() != category.lower():
                    continue
                if mat_type and rtype.lower() != mat_type.lower():
                    continue

                for item in record.get("data", []):
                    yield {
                        "db_key":   key,
                        "region":   region,
                        "category": sheet,
                        "type":     rtype,
                        **item,
                    }

    # ── PUBLIC API ─────────────────────────────────────────────────────────

    def loaded_databases(self) -> list[str]:
        """Return list of currently loaded db_keys."""
        return list(self._data.keys())

    def list_categories(self) -> dict[str, list[str]]:
        """
        Return all available categories (sheetName values) and their
        types, grouped by db_key.

        Returns
        -------
        dict  { db_key: { category: [type, ...] } }
        """
        result: dict[str, dict[str, list[str]]] = {}
        for key, records in self._data.items():
            cat_map: dict[str, list[str]] = {}
            for record in records:
                sheet = record.get("sheetName", "")
                rtype = record.get("type", "")
                cat_map.setdefault(sheet, [])
                if rtype and rtype not in cat_map[sheet]:
                    cat_map[sheet].append(rtype)
            result[key] = cat_map
        return result

    def list_by_category(self,
                         category: str,
                         mat_type: str | None = None,
                         db_key:   str | None = None) -> list[dict]:
        """
        Return all material items in a given category (sheetName),
        optionally filtered by type and / or db_key.

        Parameters
        ----------
        category : str   e.g. "Foundation", "Super Structure"
        mat_type : str   e.g. "Pile", "Girder"  (optional)
        db_key   : str   restrict to one database (optional)
        """
        return list(self._iter_items(db_key=db_key,
                                     category=category,
                                     mat_type=mat_type))

    def search(self,
               query:    str,
               category: str | None = None,
               mat_type: str | None = None,
               db_key:   str | None = None,
               region:   str | None = None) -> list[dict]:
        """
        Full-text search across material names.

        Parameters
        ----------
        query    : str   tokens to match against item 'name'
        category : str   restrict to sheetName  (optional)
        mat_type : str   restrict to type        (optional)
        db_key   : str   restrict to one db_key  (optional)
        region   : str   restrict to a region    (optional, e.g. "Maharashtra")
        """
        results = []
        for item in self._iter_items(db_key=db_key,
                                     category=category,
                                     mat_type=mat_type):
            if region and item.get("region", "").lower() != region.lower():
                continue
            if AdvancedSearchEngine.is_match(query, item.get("name", "")):
                results.append(item)
        return results

    def summary(self) -> None:
        """Print a human-readable category summary of loaded databases."""
        cats = self.list_categories()
        print("\n" + "═" * 64)
        print("  MATERIAL DATABASE – CATEGORY SUMMARY")
        print("═" * 64)
        for db_key, cat_map in cats.items():
            meta   = self._registry.get(db_key, {})
            region = meta.get("region", "?")
            print(f"\n  [{db_key}]  ({region})")
            print(f"  {'CATEGORY':<25} TYPES")
            print("  " + "─" * 55)
            for sheet, types in sorted(cat_map.items()):
                types_str = ", ".join(types)
                print(f"  {sheet:<25} {types_str}")


# # ─────────────────────────────────────────────────────────────────────────────
# #  CLI demo  – python search_engine.py
# # ─────────────────────────────────────────────────────────────────────────────

# if __name__ == "__main__":
#     engine = MaterialSearchEngine()
#     engine.summary()

#     print("\n" + "═" * 64)
#     print("  CATEGORY LISTING – Foundation (all regions)")
#     print("═" * 64)
#     items = engine.list_by_category("Foundation")
#     for it in items:
#         print(f"  [{it['db_key']:12}] {it['type']:15} | "
#               f"{it['name']:<40} {it['unit']:6} {it['rate']}")

#     print("\n" + "═" * 64)
#     print("  SEARCH – 'steel rebar'")
#     print("═" * 64)
#     results = engine.search("steel rebar")
#     for r in results:
#         print(f"  [{r['db_key']:12}] {r['category']:15} › {r['type']:15} | "
#               f"{r['name']:<35} {r['rate']}")

#     print("\n" + "═" * 64)
#     print("  SEARCH – 'PVC' in Maharashtra only")
#     print("═" * 64)
#     results = engine.search("PVC", region="Maharashtra")
#     if results:
#         for r in results:
#             print(f"  [{r['db_key']:12}] {r['name']:<40} {r['rate']}")
#     else:
#         print("  No results.")


