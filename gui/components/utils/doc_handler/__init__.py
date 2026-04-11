"""
gui/components/utils/doc_handler/__init__.py

Public API for the offline documentation system.

Usage in form_builder callers
------------------------------
    from ..utils.doc_handler import make_doc_opener

    _DOC_OPENER = make_doc_opener("bridge")   # section = subfolder under site/

    self.required_keys = build_form(self, FIELDS, _DOC_OPENER)

The section maps doc_slug values to site/<section>/<slug>.html.
For example, FieldDef(doc_slug="span") + make_doc_opener("bridge")
opens  site/bridge/span.html  in the singleton offline viewer.
"""

from __future__ import annotations

from typing import Callable


def make_doc_opener(section: str) -> Callable[[str], None]:
    """
    Return a doc_opener callable for use with build_form().

    Parameters
    ----------
    section : str
        Subfolder inside site/ that contains this module's HTML pages.
        Examples: "bridge", "maintenance", "carbon/machinery"

    Returns
    -------
    Callable[[str], None]
        Accepts a doc_slug string and opens site/<section>/<slug>.html
        in the singleton offline WebEngine viewer.
        Import errors (WebEngine not installed) are caught and silently ignored.
    """
    def _open(slug: str) -> None:
        try:
            from .webview import navigate
            navigate(f"{section}/{slug}.html")
        except Exception:
            pass

    return _open


