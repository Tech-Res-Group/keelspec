"""Daily SEO audit with safe auto-fixes.

"Safe" is a deliberately narrow definition: a fix is applied automatically only when
it adds missing machine-readable metadata or trims an over-long tag. Body copy,
headings and link text are never touched -- those are reported and left alone.

Anything the auditor changes is derived from content already on the page, so it
cannot invent claims. Everything else lands in the report for a human to act on.
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import re

from store import cursor, now

PUBLIC = pathlib.Path(os.getenv("PUBLIC_DIR", "/srv/public"))
AUTOFIX = os.getenv("SEO_AUTOFIX", "on").lower() == "on"

TITLE_MAX = 60
DESC_MIN, DESC_MAX = 70, 160

SKIP = {"og.html"}          # the social card is not a page


def _text_of(match: str) -> str:
    """Strip tags AND decode entities. Without the unescape, text pulled out of the
    page still holds `&#x27;`, and escaping it again on the way into a meta tag
    produces `&amp;#x27;` -- visible mojibake in search results."""
    stripped = re.sub(r"<[^>]+>", " ", match)
    return re.sub(r"\s+", " ", html.unescape(stripped)).strip()


def audit_page(path: pathlib.Path) -> tuple[list[dict], str, int]:
    """Return (issues, possibly-rewritten html, fixes_applied)."""
    src = path.read_text(encoding="utf-8")
    original, issues, fixed = src, [], 0
    rel = "/" + path.relative_to(PUBLIC).as_posix()

    def add(code: str, detail: str, severity: str = "warn", auto: bool = False):
        issues.append({"page": rel, "code": code, "detail": detail,
                       "severity": severity, "autofixed": auto})

    # ── title ────────────────────────────────────────────────────────────────
    m = re.search(r"<title>(.*?)</title>", src, re.S | re.I)
    title = _text_of(m.group(1)) if m else ""
    if not title:
        add("SEO-001", "page has no <title>", "error")
    elif len(title) > TITLE_MAX:
        add("SEO-002", f"title is {len(title)} chars (max {TITLE_MAX})")

    # ── meta description ─────────────────────────────────────────────────────
    dm = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']\s*/?>',
                   src, re.S | re.I)
    if not dm:
        # SAFE FIX: derive one from the page's own first paragraph.
        derived = _derive_description(src)
        if AUTOFIX and derived and "</title>" in src:
            tag = f'\n<meta name="description" content="{html.escape(derived, quote=True)}">'
            src = src.replace("</title>", "</title>" + tag, 1)
            fixed += 1
            add("SEO-010", "added missing meta description from page content", "warn", True)
        else:
            add("SEO-010", "no meta description", "error")
    else:
        # Measure and edit the DECODED text, then re-escape exactly once and replace
        # the whole tag. Trimming the raw attribute and escaping it again double-encodes
        # every entity, and because that lengthens the value it never converges.
        desc = html.unescape(dm.group(1).strip())
        if len(desc) > DESC_MAX:
            if AUTOFIX:
                trimmed = desc[:DESC_MAX].rsplit(" ", 1)[0].rstrip(",.;:") + "."
                src = src.replace(
                    dm.group(0),
                    f'<meta name="description" content="{html.escape(trimmed, quote=True)}">',
                    1)
                fixed += 1
                add("SEO-011", f"trimmed description from {len(desc)} to {len(trimmed)} chars",
                    "warn", True)
            else:
                add("SEO-011", f"description is {len(desc)} chars (max {DESC_MAX})")
        elif len(desc) < DESC_MIN:
            add("SEO-012", f"description is only {len(desc)} chars (aim for {DESC_MIN}+)")

    # ── canonical ────────────────────────────────────────────────────────────
    if not re.search(r'rel=["\']canonical["\']', src, re.I):
        if AUTOFIX and "</title>" in src:
            href = "https://keelspec.com" + (rel[:-len("index.html")] if rel.endswith("/index.html") else rel)
            src = src.replace("</title>", f'</title>\n<link rel="canonical" href="{href}">', 1)
            fixed += 1
            add("SEO-020", "added missing canonical link", "warn", True)
        else:
            add("SEO-020", "no canonical link")

    # ── open graph ───────────────────────────────────────────────────────────
    if not re.search(r'property=["\']og:title["\']', src, re.I):
        if AUTOFIX and title and "</title>" in src:
            src = src.replace(
                "</title>",
                f'</title>\n<meta property="og:title" content="{html.escape(title, quote=True)}">', 1)
            fixed += 1
            add("SEO-021", "added missing og:title from <title>", "warn", True)
        else:
            add("SEO-021", "no og:title")

    # ── headings: reported, never rewritten ──────────────────────────────────
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", src, re.S | re.I)
    if not h1s:
        add("SEO-030", "no <h1> on the page", "error")
    elif len(h1s) > 1:
        add("SEO-031", f"{len(h1s)} <h1> elements; there should be one")

    # ── images without alt ───────────────────────────────────────────────────
    imgs = re.findall(r"<img\b[^>]*>", src, re.I)
    missing_alt = [i for i in imgs if not re.search(r'\balt=', i, re.I)]
    if missing_alt:
        add("SEO-040", f"{len(missing_alt)} image(s) without alt text", "error")

    # ── thin content: reported only ──────────────────────────────────────────
    words = len(_text_of(re.sub(r"(?is)<(script|style|nav|footer)[^>]*>.*?</\1>", " ", src)).split())
    if words < 250:
        add("SEO-050", f"only ~{words} words of visible content")

    return issues, src, fixed


def _derive_description(src: str) -> str:
    """First substantial paragraph, trimmed to a sensible length."""
    for match in re.findall(r"<p[^>]*>(.*?)</p>", src, re.S | re.I):
        text = _text_of(match)
        if len(text) >= 60:
            if len(text) > DESC_MAX:
                text = text[:DESC_MAX].rsplit(" ", 1)[0].rstrip(",.;:") + "."
            return text
    return ""


def run(apply_fixes: bool | None = None) -> dict:
    """Audit every page, apply safe fixes, store a report. Returns the summary."""
    global AUTOFIX
    if apply_fixes is not None:
        AUTOFIX = apply_fixes

    pages = [p for p in sorted(PUBLIC.rglob("*.html")) if p.name not in SKIP]
    all_issues, total_fixed = [], 0

    for page in pages:
        try:
            issues, new_src, fixed = audit_page(page)
        except OSError as exc:
            all_issues.append({"page": str(page), "code": "SEO-000",
                               "detail": f"unreadable: {exc}", "severity": "error",
                               "autofixed": False})
            continue
        if fixed and AUTOFIX:
            page.write_text(new_src, encoding="utf-8", newline="\n")
            total_fixed += fixed
        all_issues.extend(issues)

    summary = {
        "pages": len(pages),
        "issues": len(all_issues),
        "fixed": total_fixed,
        "errors": sum(1 for i in all_issues if i["severity"] == "error"),
        "detail": all_issues,
    }

    with cursor() as conn:
        conn.execute(
            "INSERT INTO seo_reports (created, pages, issues, fixed, detail)"
            " VALUES (?, ?, ?, ?, ?)",
            (now(), summary["pages"], summary["issues"], summary["fixed"],
             json.dumps(all_issues)),
        )
    return summary


def latest() -> dict | None:
    with cursor() as conn:
        row = conn.execute(
            "SELECT * FROM seo_reports ORDER BY created DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {"created": row["created"], "pages": row["pages"], "issues": row["issues"],
            "fixed": row["fixed"], "detail": json.loads(row["detail"])}
