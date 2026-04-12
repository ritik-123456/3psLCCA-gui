"""
devtools/docs_build.py — Convert docs/*.md → site/*.html using pandoc.

Also:
- Inlines classless CSS (offline)
- Generates sitemap.json
- Exports links.txt
- Validates internal links
- Generates 404 page
- Optional clean + auto-fix broken links

Run:
    python docs_build.py
    python docs_build.py --clean
    python docs_build.py --clean --fix-links
"""

import subprocess
import argparse
import tempfile
import os
import urllib.request
import sys
import shutil
from pathlib import Path
import json
from datetime import date
import re
from urllib.parse import urlparse


# ── PATHS ─────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.parent
_DOC_HANDLER_DIR = _PROJECT_ROOT / "gui" / "components" / "utils" / "doc_handler"

DOCS_DIR = _PROJECT_ROOT / "docs"
SITE_DIR = _DOC_HANDLER_DIR / "site"
ASSETS_DIR = Path(__file__).parent / "assets"

CSS_SOURCES = {
    "classless.css": "https://classless.de/classless.css",
    "themes.css": "https://classless.de/addons/themes.css",
}


# ── CLEAN ─────────────────────────────────────────────────────────────────────


def clean_site(site_dir: Path) -> None:
    if site_dir.exists():
        print(f"Cleaning {site_dir}...")
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)


# ── CSS ───────────────────────────────────────────────────────────────────────


def _fetch_css() -> str:
    ASSETS_DIR.mkdir(exist_ok=True)
    blocks = []

    for filename, url in CSS_SOURCES.items():
        local = ASSETS_DIR / filename
        if not local.exists():
            print(f"  DL  {url}")
            try:
                urllib.request.urlretrieve(url, local)
            except Exception as e:
                print(f" WARN  Could not download {filename}: {e}")
                continue
        blocks.append(f"<style>\n{local.read_text(encoding='utf-8')}\n</style>")

    return "\n".join(blocks)


# ── BUILD ─────────────────────────────────────────────────────────────────────


def build(docs_dir: Path, site_dir: Path) -> None:
    md_files = list(docs_dir.rglob("*.md"))

    if not md_files:
        print(f"No .md files found in {docs_dir}")
        return

    css_block = _fetch_css()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(css_block)
        header_file = tmp.name

    ok = fail = 0

    try:
        for md_path in sorted(md_files):
            rel = md_path.relative_to(docs_dir)
            html_path = site_dir / rel.with_suffix(".html")
            html_path.parent.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    "pandoc",
                    str(md_path),
                    "--standalone",
                    "-H",
                    header_file,
                    "--output",
                    str(html_path),
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                print(f"  OK  {rel}")
                ok += 1
            else:
                print(f"FAIL  {rel}\n      {result.stderr.strip()}")
                fail += 1
    finally:
        os.unlink(header_file)

    print(f"\nDone — {ok} built, {fail} failed.")


# ── 404 PAGE ──────────────────────────────────────────────────────────────────


def copy_404_page(site_dir: Path) -> None:
    """
    Copy the existing 404.html from devtools/assets/ to the site directory.
    """
    src = Path(__file__).parent / "assets" / "404.html"
    dst = site_dir / "404.html"

    if not src.exists():
        print(f"ERROR: {src} not found")
        return

    shutil.copy(src, dst)
    print(f"404.html copied to {dst}")


# ── SITEMAP ───────────────────────────────────────────────────────────────────


def _generate_sitemap(site_dir: Path) -> None:

    def _clean(html):
        return re.sub(r"<[^>]+>", "", html).strip()

    today = date.today().isoformat()
    site_name = site_dir.parent.name

    html_files = sorted(p for p in site_dir.rglob("*.html") if p.name != "404.html")

    pages = []
    for html_path in html_files:
        rel = html_path.relative_to(site_dir).as_posix()
        content = html_path.read_text(encoding="utf-8")

        title_tag = re.search(r"<title>([^<]+)</title>", content)
        title = title_tag.group(1).strip() if title_tag else rel

        pages.append(
            {
                "title": title,
                "url": rel,
                "lastmod": today,
            }
        )

    out_path = site_dir / "sitemap.json"
    out_path.write_text(
        json.dumps(
            {
                "generated": today,
                "pages": pages,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"sitemap.json — {len(pages)} pages")


# ── LINKS.TXT ─────────────────────────────────────────────────────────────────


def export_links_txt(site_dir: Path) -> None:
    html_files = sorted(p for p in site_dir.rglob("*.html"))

    out_file = site_dir / "links.txt"

    lines = [f'open("{p.relative_to(site_dir).as_posix()}")' for p in html_files]

    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"links.txt — {len(lines)} entries")


# ── LINK CHECKER ──────────────────────────────────────────────────────────────


def check_links(site_dir: Path, fix: bool = False):

    def extract_links(html: str):
        return re.findall(r'href=["\'](.*?)["\']', html, re.IGNORECASE)

    def is_external(link: str) -> bool:
        return link.startswith(("http://", "https://", "mailto:", "tel:"))

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
            target = (file.parent / parsed.path).resolve()

            if target.is_dir():
                target = target / "index.html"

            checked += 1

            if not target.exists():
                broken.append((file, link))

                if fix:
                    content = content.replace(link, "/404.html")

        if fix:
            file.write_text(content, encoding="utf-8")

    return checked, broken


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build docs → site")
    parser.add_argument("--docs", default=str(DOCS_DIR))
    parser.add_argument("--site", default=str(SITE_DIR))
    parser.add_argument("--clean", action="store_true", help="Clean site folder")
    parser.add_argument("--fix-links", action="store_true", help="Fix broken links")

    args = parser.parse_args()

    site_path = Path(args.site)

    if args.clean:
        clean_site(site_path)

    build(Path(args.docs), site_path)
    copy_404_page(site_path)
    _generate_sitemap(site_path)
    export_links_txt(site_path)

    print("\nChecking links...")
    checked, broken = check_links(site_path, fix=args.fix_links)

    print(f"Checked {checked} links")

    if broken:
        print(f"\n❌ {len(broken)} broken links:\n")
        for src, link in broken:
            rel = src.relative_to(site_path)
            print(f"[{rel}] -> {link}")

        if not args.fix_links:
            sys.exit(1)
    else:
        print("✅ All links are valid!")


