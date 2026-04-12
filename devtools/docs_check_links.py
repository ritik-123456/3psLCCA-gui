"""
devtools/docs_check_links.py — Verify all internal links in site/ are valid.

- Scans all HTML files
- Extracts href links
- Resolves relative paths
- Reports missing targets

Run:
    python docs_check_links.py
"""

import re
from pathlib import Path
from urllib.parse import urlparse

_PROJECT_ROOT    = Path(__file__).parent.parent
_DOC_HANDLER_DIR = _PROJECT_ROOT / "gui" / "components" / "utils" / "doc_handler"

SITE_DIR = _DOC_HANDLER_DIR / "site"


def extract_links(html: str):
    """Return all href links from HTML."""
    return re.findall(r'href=["\'](.*?)["\']', html, re.IGNORECASE)


def is_external(link: str) -> bool:
    return link.startswith(("http://", "https://", "mailto:", "tel:"))


def check_links(site_dir: Path):
    html_files = list(site_dir.rglob("*.html"))

    broken = []
    checked = 0

    for file in html_files:
        content = file.read_text(encoding="utf-8", errors="ignore")
        links = extract_links(content)

        for link in links:
            if not link or link.startswith("#"):
                continue

            if is_external(link):
                continue

            parsed = urlparse(link)
            clean_path = parsed.path

            target = (file.parent / clean_path).resolve()

            if target.is_dir():
                target = target / "index.html"

            checked += 1

            if not target.exists():
                broken.append((file, link))

    return checked, broken


def main():
    checked, broken = check_links(SITE_DIR)

    print(f"Checked {checked} internal links\n")

    if not broken:
        print("✅ All links are valid!")
        return

    print(f"❌ {len(broken)} broken links found:\n")

    for src, link in broken:
        rel = src.relative_to(SITE_DIR)
        print(f"[{rel}] -> {link}")

    print("\nDone.")


if __name__ == "__main__":
    main()


