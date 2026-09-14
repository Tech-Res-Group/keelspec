"""Render the compiled blog bundle to static HTML.

The renderer is deliberately dumb: it loops over `blog.generated.json` and fills a
template. All structural guarantees -- ids, categories, resolving `related` links --
were already enforced by `fastpdlc validate`, so nothing here needs to check anything.

    python tools/render_blog.py
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "content" / "build" / "blog.generated.json"
OUT = ROOT / "public" / "blog"

NAV = """<header class="nav">
  <div class="wrap nav-inner">
    <a class="logo" href="/" aria-label="FastPDLC home"><svg class="logo-glyph" viewBox="0 0 40 40" aria-hidden="true"><rect x="1.6" y="1.6" width="36.8" height="36.8" rx="9" fill="#191919"/><path d="M10.5 21.5 L17 28 L29.5 12.5" fill="none" stroke="#fbcc00" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="10.5" cy="21.5" r="3.6" fill="#fff"/><circle cx="29.5" cy="12.5" r="3.6" fill="#00b67a"/></svg><span class="logo-word">FastPDLC</span></a>
    <button class="nav-toggle" id="navToggle" aria-label="Menu" aria-expanded="false" aria-controls="navLinks"><span></span></button>
    <nav class="nav-links" id="navLinks">
      <a href="/#how">How it works</a>
      <a href="/lifecycle.html">Lifecycle</a>
      <a href="/#diagnostics">Diagnostics</a>
      <a href="/blog/">Blog</a>
      <a href="/#faq">FAQ</a>
      <a href="https://github.com/tarvitave/fastpdlc">GitHub</a>
      <a class="btn btn-primary nav-cta" href="/#start">Get started</a>
    </nav>
  </div>
</header>"""

FOOTER = """<footer class="footer">
  <div class="wrap">
    <div class="footer-grid">
      <div>
        <a class="logo" href="/" aria-label="FastPDLC home"><svg class="logo-glyph" viewBox="0 0 40 40" aria-hidden="true"><rect x="1.6" y="1.6" width="36.8" height="36.8" rx="9" fill="#191919"/><path d="M10.5 21.5 L17 28 L29.5 12.5" fill="none" stroke="#fbcc00" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="10.5" cy="21.5" r="3.6" fill="#fff"/><circle cx="29.5" cy="12.5" r="3.6" fill="#00b67a"/></svg><span class="logo-word">FastPDLC</span></a>
        <p class="footer-blurb">Product-as-code as a validated graph &mdash; for any project.
          Typed artifacts in, a compiled bundle out, and a CI gate in between.</p>
      </div>
      <div>
        <h4>Product</h4>
        <ul>
          <li><a href="/#how">How it works</a></li>
          <li><a href="/lifecycle.html">Lifecycle</a></li>
          <li><a href="/#diagnostics">Diagnostic codes</a></li>
          <li><a href="/blog/">Blog</a></li>
          <li><a href="/newsletters/">Newsletters</a></li>
        </ul>
      </div>
      <div>
        <h4>Company</h4>
        <ul>
          <li><a href="/who-we-are.html">Who we are</a></li>
          <li><a href="/contact.html">Contact us</a></li>
          <li><a href="https://github.com/tarvitave/fastpdlc">GitHub</a></li>
          <li><a href="https://pypi.org/project/fastpdlc/">PyPI</a></li>
        </ul>
      </div>
      <div>
        <h4>Legal</h4>
        <ul>
          <li><a href="/privacy.html">Privacy policy</a></li>
          <li><a href="/terms.html">Terms of use</a></li>
          <li><a href="/sms-opt-in.html">SMS opt-in</a></li>
          <li><a href="https://github.com/tarvitave/fastpdlc/blob/main/LICENSE">Apache-2.0</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-base">
      <span>&copy; <span id="year">2026</span> FastPDLC. This blog is compiled and validated by FastPDLC itself.</span>
      <span><code style="font-family:var(--mono)">pip install fastpdlc</code></span>
    </div>
  </div>
</footer>"""

FAVICON = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'><rect width='40' height='40' rx='9' fill='%23191919'/><path d='M10.5 21.5 L17 28 L29.5 12.5' fill='none' stroke='%23fbcc00' stroke-width='4.6' stroke-linecap='round' stroke-linejoin='round'/><circle cx='10.5' cy='21.5' r='3.6' fill='%23fff'/><circle cx='29.5' cy='12.5' r='3.6' fill='%2300b67a'/></svg>")

SUBSCRIBE = """<section class="section band-cream">
  <div class="wrap cta">
    <span class="eyebrow">Newsletter</span>
    <h2 style="margin-top:0.8rem">Get the next one by email.</h2>
    <p class="lede" style="max-width:38rem;margin:1rem auto 0">Short notes on product-as-code,
      new diagnostic codes, and what breaks in real repositories. Twice a week, unsubscribe in one click.</p>
    <form class="signup" id="signupForm" novalidate>
      <div class="signup-row">
        <label class="hp" for="company">Company (leave blank)</label>
        <input class="hp" type="text" id="company" name="company" tabindex="-1" autocomplete="off">
        <label class="hp" for="email">Email address</label>
        <input type="email" id="email" name="email" placeholder="you@company.com" required autocomplete="email">
        <button class="btn btn-primary" type="submit">Subscribe</button>
      </div>
      <p class="msg" id="signupMsg" role="status" aria-live="polite"></p>
    </form>
  </div>
</section>"""

CAT_COLOR = {
    "concept": "#4a90e2",
    "practice": "#00b67a",
    "reference": "#ff6b4a",
    "case-study": "#b47cff",
}


# ── a deliberately small markdown subset: what these posts actually use ────────
def md_to_html(src: str) -> str:
    out, lines, i = [], src.split("\n"), 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):                       # fenced code
            lang, i, buf = line[3:].strip(), i + 1, []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            out.append(f'<pre><code>{html.escape(chr(10).join(buf))}</code></pre>')
            continue

        if line.startswith("## "):
            out.append(f"<h2>{inline(line[3:].strip())}</h2>"); i += 1; continue
        if line.startswith("### "):
            out.append(f"<h3>{inline(line[4:].strip())}</h3>"); i += 1; continue

        if re.match(r"^[-*] ", line):                    # unordered list
            items = []
            while i < len(lines) and re.match(r"^[-*] ", lines[i]):
                items.append(f"<li>{inline(lines[i][2:].strip())}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        if not line.strip():
            i += 1; continue

        para = []                                        # paragraph
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "```", "- ", "* ")):
            para.append(lines[i].strip()); i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")

    return "\n".join(out)


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def page(title: str, desc: str, body: str, canonical: str, extra_head: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="https://fastpdlc.com{canonical}">
<meta property="og:type" content="article">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="https://fastpdlc.com{canonical}">
<meta name="twitter:card" content="summary_large_image">
<meta property="og:image" content="https://fastpdlc.com/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<link rel="icon" href="{FAVICON}">
<link rel="stylesheet" href="/styles.css">
<link rel="stylesheet" href="/blog.css">
{extra_head}
</head>
<body>
{NAV}
{body}
{FOOTER}
<script src="/main.js" defer></script>
</body>
</html>
"""


def fmt_date(value: str) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d %B %Y").lstrip("0")
    except ValueError:
        return str(value)


def main() -> int:
    if not BUNDLE.exists():
        print(f"error: {BUNDLE} not found -- run `fastpdlc build` in site/content first",
              file=sys.stderr)
        return 1

    posts = json.loads(BUNDLE.read_text(encoding="utf-8"))["posts"]
    posts.sort(key=lambda p: str(p["date"]), reverse=True)
    by_id = {p["id"]: p for p in posts}
    OUT.mkdir(parents=True, exist_ok=True)

    # ── index ────────────────────────────────────────────────────────────────
    cards = []
    for p in posts:
        colour = CAT_COLOR.get(p.get("category"), "#4a90e2")
        tags = " ".join(f'<span class="tag-chip">{html.escape(t)}</span>'
                        for t in (p.get("tags") or []))
        cards.append(f"""<article class="post-card">
  <a class="post-card-link" href="/blog/{html.escape(p['slug'])}.html">
    <span class="badge" style="background:{colour};color:#fff">{html.escape(p.get('category',''))}</span>
    <h3>{html.escape(p['title'])}</h3>
    <p>{html.escape(p['summary'])}</p>
    <div class="post-meta">{fmt_date(p['date'])} &middot; {p.get('reading_minutes', 4)} min read</div>
    <div class="post-tags">{tags}</div>
  </a>
</article>""")

    index_body = f"""<main>
<section class="section" style="padding-bottom:2rem">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Blog</span>
      <h1 style="font-size:clamp(2.6rem,6vw,4rem);margin-top:0.7rem">Notes on product-as-code.</h1>
      <p class="lede">Why specs rot, what a validated graph buys you, and what breaks in real
        repositories. Every post on this page is a typed artifact &mdash; ids, categories and
        cross-links are validated by <code style="font-family:var(--mono)">fastpdlc</code> in CI.</p>
    </div>
    <div class="post-grid">
      {''.join(cards)}
    </div>
  </div>
</section>
{SUBSCRIBE}
</main>"""

    (OUT / "index.html").write_text(
        page("Blog — FastPDLC",
             "Notes on product-as-code: why specs rot, what a validated graph buys you, "
             "and what breaks in real repositories.",
             index_body, "/blog/"),
        encoding="utf-8", newline="\n")

    # ── individual posts ─────────────────────────────────────────────────────
    for p in posts:
        colour = CAT_COLOR.get(p.get("category"), "#4a90e2")
        related = []
        for rid in (p.get("related") or []):
            r = by_id.get(rid)
            if r:
                related.append(
                    f'<li><a href="/blog/{html.escape(r["slug"])}.html">'
                    f'{html.escape(r["title"])}</a></li>')
        related_html = (f'<div class="related"><h3>Related</h3><ul>{"".join(related)}</ul></div>'
                        if related else "")

        ld = json.dumps({
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": p["title"],
            "description": p["summary"],
            "datePublished": str(p["date"])[:10],
            "author": {"@type": "Organization", "name": p.get("author", "FastPDLC")},
            "url": f"https://fastpdlc.com/blog/{p['slug']}.html",
        })

        body = f"""<main>
<article class="section post">
  <div class="wrap post-wrap">
    <a class="back-link" href="/blog/">&larr; All posts</a>
    <span class="badge" style="background:{colour};color:#fff">{html.escape(p.get('category',''))}</span>
    <h1>{html.escape(p['title'])}</h1>
    <p class="lede post-summary">{html.escape(p['summary'])}</p>
    <div class="post-meta">{fmt_date(p['date'])} &middot; {p.get('reading_minutes', 4)} min read
      &middot; {html.escape(p.get('author', 'FastPDLC'))}</div>
    <div class="post-body">
      {md_to_html(p.get('body') or '')}
    </div>
    {related_html}
  </div>
</article>
{SUBSCRIBE}
</main>"""

        (OUT / f"{p['slug']}.html").write_text(
            page(f"{p['title']} — FastPDLC", p["summary"], body,
                 f"/blog/{p['slug']}.html",
                 f'<script type="application/ld+json">{ld}</script>'),
            encoding="utf-8", newline="\n")

    print(f"rendered {len(posts)} posts + index into {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
