"""Structural gate for the generated site.

The homepage broke because a generator ran twice and left orphaned `<article>` tags
outside the rail. The markup stayed well-formed enough for Caddy to serve and the
browser to render — it just rendered wrong. Every other artifact here is gated; the
site was not, so the break shipped silently until someone looked at it.

This is that gate. Findings carry stable `SITE-NNN` codes, for the same reason the
product's do: a code is matchable forever, prose is not.

    python tools/check_site.py          # from site/
"""
from __future__ import annotations

import html.parser
import pathlib
import re
import sys
from collections import Counter

PUBLIC = pathlib.Path(__file__).resolve().parent.parent / "public"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stations import STATIONS  # noqa: E402  (the roster the rail is built from)

# Tags that never close, so an unbalanced-tag check must not expect them to.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

SKIP = {"carousel.html", "og.html"}          # print sheets, not pages

CODES = {
    "SITE-001": "mismatched or unclosed tag",
    "SITE-010": "a station card is outside the marquee rail",
    "SITE-011": "unexpected number of station cards",
    "SITE-020": "duplicate link in the navigation",
    "SITE-030": "internal link points at a file that does not exist",
    "SITE-031": "referenced local asset does not exist",
    "SITE-040": "page has no <title>",
    "SITE-041": "page does not have exactly one <h1>",
    "SITE-050": "page has no markdown rendition for agents",
}


class Structure(html.parser.HTMLParser):
    """Tracks the open-tag stack so we can ask *where* an element sits."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.stations_in_rail = 0
        self.stations_loose = 0
        self.nav_links: list[str] = []
        self.h1 = 0
        self.title = False
        # Depth-tracked, not a flag: a counter that only increments means every
        # element after the rail looks like it is inside the rail, and SITE-010
        # can never fire. Record the stack depth on entry and compare on exit.
        self._rail_depth: int | None = None
        self._nav_depth: int | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()

        if tag == "title":
            self.title = True
        if tag == "h1":
            self.h1 += 1
        if a.get("id") == "railTrack" and self._rail_depth is None:
            self._rail_depth = len(self.stack)
        if "nav-links" in classes and self._nav_depth is None:
            self._nav_depth = len(self.stack)
        if tag == "a" and self._nav_depth is not None:
            self.nav_links.append(a.get("href", ""))
        if "station" in classes:
            if self._rail_depth is not None:
                self.stations_in_rail += 1
            else:
                self.stations_loose += 1

        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass                                    # self-closing: nothing to track

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f"stray closing </{tag}>")
            return
        if self.stack[-1] != tag:
            # tolerate optional-close tags the browser forgives
            if tag in self.stack:
                while self.stack and self.stack[-1] != tag:
                    self.errors.append(
                        f"<{self.stack[-1]}> was never closed (found </{tag}>)")
                    self.stack.pop()
            else:
                self.errors.append(f"stray closing </{tag}>")
                return
        self.stack.pop()
        # left the rail / nav when the stack unwinds back to the entry depth
        if self._rail_depth is not None and len(self.stack) <= self._rail_depth:
            self._rail_depth = None
        if self._nav_depth is not None and len(self.stack) <= self._nav_depth:
            self._nav_depth = None


def check_page(path: pathlib.Path) -> list[tuple[str, str]]:
    rel = "/" + path.relative_to(PUBLIC).as_posix()
    src = path.read_text(encoding="utf-8")
    out: list[tuple[str, str]] = []

    parser = Structure()
    parser.feed(src)
    # `nav-links` closes with </nav>; anything still open at EOF is a real leak.
    for err in parser.errors:
        out.append(("SITE-001", f"{rel}: {err}"))
    if parser.stack:
        out.append(("SITE-001", f"{rel}: never closed: {', '.join(parser.stack[-5:])}"))

    if not parser.title:
        out.append(("SITE-040", rel))
    if parser.h1 != 1:
        out.append(("SITE-041", f"{rel}: found {parser.h1}"))

    if parser.stations_loose:
        out.append(("SITE-010",
                    f"{rel}: {parser.stations_loose} station card(s) outside #railTrack"))

    # The homepage rail holds the roster twice only at runtime (JS clones it for the
    # loop); the served HTML must contain exactly one set.
    if rel == "/index.html" and parser.stations_in_rail != len(STATIONS):
        out.append(("SITE-011",
                    f"{rel}: {parser.stations_in_rail} station cards in the rail, "
                    f"expected {len(STATIONS)}"))

    dupes = [href for href, n in Counter(parser.nav_links).items() if n > 1 and href]
    for href in dupes:
        out.append(("SITE-020", f"{rel}: {href} appears more than once in the nav"))

    # internal links and local assets must resolve
    for m in re.finditer(r'(?:href|src)="(/[^"#?]*)(?:\?[^"]*)?"', src):
        target = m.group(1)
        if target.startswith(("/api/", "/admin")):
            continue
        candidate = PUBLIC / target.lstrip("/")
        if target.endswith("/"):
            candidate = candidate / "index.html"
        if candidate.exists():
            continue
        code = "SITE-031" if candidate.suffix in {".css", ".js", ".png", ".woff2"} else "SITE-030"
        out.append((code, f"{rel}: {target}"))

    # Every page should have a .md beside it: agents asking for text/markdown get
    # served that file, and a missing one silently falls back to HTML chrome.
    if path.name != "404.html" and not path.with_suffix(".md").exists():
        out.append(("SITE-050", rel))

    return out


def main() -> int:
    pages = [p for p in sorted(PUBLIC.rglob("*.html")) if p.name not in SKIP]
    findings: list[tuple[str, str]] = []
    for page in pages:
        findings += check_page(page)

    if findings:
        print(f"SITE CHECK FAILED — {len(findings)} finding(s) across {len(pages)} page(s)\n")
        for code, detail in findings:
            print(f"  {code}  {CODES[code]}")
            print(f"           {detail}")
        return 1

    print(f"site check: clean ({len(pages)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
