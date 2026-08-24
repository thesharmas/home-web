#!/usr/bin/env python3
"""Generate per-entry share pages for the reading log.

reading.html renders entirely on the client from data/reading.json, so a
`reading.html#<entry-id>` permalink unfurls as the generic site card — the
fragment never reaches the server and crawlers do not run the JS that would
fill in the entry. This writes one thin HTML file per entry under r/ whose
<head> carries that entry's Open Graph tags, so a shared link previews as the
article it points at. Browsers are redirected straight into the log at the
matching card; crawlers just read the meta tags and stop.

Usage:
    python3 scripts/build_share_pages.py [--check] [--prune] [--quiet]

    --check   Report what would change and exit 1 if anything would, without
              writing. Intended for CI drift checks.
    --prune   Delete share pages whose entry is no longer in reading.json.
              Off by default: a stale page still redirects into the log, which
              beats breaking a link someone already shared.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "reading.json"
OUT_DIR = REPO / "r"

SITE = "https://thesharmas.org"
SITE_NAME = "Rohit's Web"
LOG_PAGE = "reading.html"
BOOKS_PAGE = "books.html"

# Entry ids become filenames, so they must not be able to escape OUT_DIR.
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")

# Open Graph descriptions get truncated by every platform anyway; keep them
# short enough that the cut is ours and lands on a word.
MAX_DESC = 200


def truncate(text: str, limit: int = MAX_DESC) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.—-")
    return (cut or text[:limit].rstrip()) + "…"


def meta(prop: str, content: str, *, name: bool = False) -> str:
    attr = "name" if name else "property"
    return f'    <meta {attr}="{prop}" content="{html.escape(content, quote=True)}">'


def render(*, share_url: str, target: str, title: str, description: str,
           source_url: str | None, source_label: str, back_label: str) -> str:
    """One share page: meta tags for crawlers, an instant redirect for browsers.

    The redirect runs in <head> before the body paints, so there is no flash of
    the fallback. The fallback below it is what no-JS clients and crawlers see.
    """
    esc = lambda s: html.escape(s, quote=True)
    head_desc = truncate(description) if description else (
        f"{title} — from the reading log at {SITE_NAME}.")

    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '    <meta charset="UTF-8">',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"    <title>{esc(title)} — {SITE_NAME}</title>",
        meta("description", head_desc, name=True),
        # These pages are share shims, not content — keep them out of the index
        # and let the log itself be the canonical destination.
        meta("robots", "noindex, follow", name=True),
        f'    <link rel="canonical" href="{SITE}/{LOG_PAGE}">',
        meta("og:type", "article"),
        meta("og:url", share_url),
        meta("og:site_name", SITE_NAME),
        meta("og:title", title),
        meta("og:description", head_desc),
        meta("twitter:card", "summary", name=True),
        meta("twitter:title", title, name=True),
        meta("twitter:description", head_desc, name=True),
        f'    <link rel="icon" href="/favicon.ico" sizes="32x32">',
        f'    <link rel="icon" type="image/svg+xml" href="/favicon.svg">',
        "    <script>",
        f"        location.replace({json.dumps('../' + target)});",
        "    </script>",
        f'    <noscript><meta http-equiv="refresh" content="0; url=../{esc(target)}"></noscript>',
        "    <style>",
        '        body { font-family: "IBM Plex Mono", ui-monospace, monospace;',
        "               background: #050806; color: #c8f5c8;",
        "               margin: 0; padding: 3rem 1.5rem; line-height: 1.6; }",
        "        main { max-width: 42rem; margin: 0 auto; }",
        "        h1 { font-size: 1.25rem; line-height: 1.4; margin: 0 0 0.75rem; }",
        "        p { color: #a7d7bb; font-size: 0.875rem; }",
        "        a { color: #6ee7b7; }",
        "    </style>",
        "</head>",
        "<body>",
        "    <main>",
        f"        <h1>{esc(title)}</h1>",
    ]
    if description:
        lines.append(f"        <p>{esc(truncate(description, 600))}</p>")
    lines.append("        <p>")
    if source_url:
        lines.append(
            f'            <a href="{esc(source_url)}" rel="noopener noreferrer">{esc(source_label)}</a><br>')
    lines.append(f'            <a href="../{esc(target)}">{esc(back_label)}</a>')
    lines.extend([
        "        </p>",
        "    </main>",
        "</body>",
        "</html>",
        "",
    ])
    return "\n".join(lines)


def pages_for(data: dict) -> dict[str, str]:
    """Map of filename -> rendered HTML, one per shareable entry."""
    pages: dict[str, str] = {}

    for entry in data.get("entries") or []:
        eid = str(entry.get("id") or "")
        if not SAFE_ID.match(eid):
            print(f"  skipping entry with unsafe id: {eid!r}", file=sys.stderr)
            continue
        title = (entry.get("title") or "").strip() or "Untitled"
        publication = (entry.get("publication") or "").strip()
        author = (entry.get("author") or "").strip()
        byline = " · ".join(x for x in (publication, author) if x)
        description = (entry.get("summary") or "").strip()
        if not description and byline:
            description = byline
        pages[f"{eid}.html"] = render(
            share_url=f"{SITE}/r/{eid}.html",
            target=f"{LOG_PAGE}#{eid}",
            title=title,
            description=description,
            source_url=entry.get("url"),
            source_label=f"Read it at {publication}" if publication else "Read the original",
            back_label="See it in the reading log",
        )

    for book in data.get("books") or []:
        bid = str(book.get("id") or "")
        if not SAFE_ID.match(bid):
            print(f"  skipping book with unsafe id: {bid!r}", file=sys.stderr)
            continue
        title = (book.get("title") or "").strip() or "Untitled"
        author = (book.get("author") or "").strip()
        pages[f"book-{bid}.html"] = render(
            share_url=f"{SITE}/r/book-{bid}.html",
            target=f"{BOOKS_PAGE}#book-{bid}",
            title=f"{title} — {author}" if author else title,
            description=(book.get("summary") or "").strip(),
            source_url=book.get("link"),
            source_label="Find the book",
            back_label="See the highlights",
        )

    return pages


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1 instead of writing")
    ap.add_argument("--prune", action="store_true",
                    help="delete share pages with no matching entry")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not DATA.exists():
        print(f"error: {DATA} not found", file=sys.stderr)
        return 1
    data = json.loads(DATA.read_text(encoding="utf-8"))
    pages = pages_for(data)
    if not pages:
        print("error: reading.json produced no share pages — refusing to run",
              file=sys.stderr)
        return 1

    OUT_DIR.mkdir(exist_ok=True)
    existing = {p.name for p in OUT_DIR.glob("*.html")}

    written, unchanged = [], 0
    for name, body in sorted(pages.items()):
        path = OUT_DIR / name
        if path.exists() and path.read_text(encoding="utf-8") == body:
            unchanged += 1
            continue
        written.append(name)
        if not args.check:
            path.write_text(body, encoding="utf-8")

    orphans = sorted(existing - set(pages))
    pruned = []
    if args.prune:
        pruned = orphans
        if not args.check:
            for name in pruned:
                (OUT_DIR / name).unlink()

    if not args.quiet:
        verb = "would write" if args.check else "wrote"
        print(f"{verb} {len(written)}, unchanged {unchanged}, total {len(pages)}")
        if orphans:
            note = "pruned" if args.prune else "orphaned (use --prune to remove)"
            print(f"{note}: {len(orphans)}")

    if args.check and (written or pruned):
        print("share pages are out of date — run scripts/build_share_pages.py",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
