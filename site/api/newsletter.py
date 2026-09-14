"""Newsletter: generate with Claude, send with Postmark, archive as static HTML.

Sending is fully automatic on a schedule, which is what was asked for. Because there
is no human in the loop, the safety rails are structural rather than procedural:

  * NEWSLETTER_AUTOSEND must be "on" -- a kill switch that stops the scheduler dead
  * MAX_RECIPIENTS caps the blast radius of any single send
  * a generation that fails validation is stored as a draft and never sent
  * every issue is archived before sending, so there is always a record

A draft that looks wrong can be deleted from the admin panel before its send window.
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import re
import textwrap
from datetime import datetime, timezone

import httpx

from store import active_subscribers, cursor, now

MODEL = "claude-opus-5"
FROM_EMAIL = os.getenv("NEWSLETTER_FROM", "marketing@keelspec.com")
POSTMARK_TOKEN = os.getenv("POSTMARK_TOKEN", "")
AUTOSEND = os.getenv("NEWSLETTER_AUTOSEND", "off").lower() == "on"
MAX_RECIPIENTS = int(os.getenv("NEWSLETTER_MAX_RECIPIENTS", "2000"))
SITE = "https://keelspec.com"

PUBLIC = pathlib.Path(os.getenv("PUBLIC_DIR", "/srv/public"))
BUNDLE = pathlib.Path(os.getenv("BLOG_BUNDLE", "/srv/content/build/blog.generated.json"))

# ── the CLI surface, generated from argparse rather than retyped ─────────────
# site/tools/gen_cli_surface.py writes cli_surface.json from the real parser, and a
# test fails when the committed manifest drifts. Both the prompt below and the guard
# in generate() read from here, so adding a subcommand cannot leave the newsletter
# rejecting true statements about our own tool.
_SURFACE_PATH = pathlib.Path(__file__).with_name("cli_surface.json")


def _load_surface() -> dict:
    try:
        return json.loads(_SURFACE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Degrade to the core two rather than block generation entirely; a missing
        # manifest should cost accuracy, not availability.
        return {"global_flags": ["--config", "--plugin", "--root"],
                "subcommands": {"build": {"flags": [], "help": ""},
                                "validate": {"flags": [], "help": ""}}}


SURFACE = _load_surface()
CLI_VERBS = set(SURFACE["subcommands"])
CLI_FLAGS = set(SURFACE.get("global_flags", [])) | {
    f for meta in SURFACE["subcommands"].values() for f in meta.get("flags", [])
}


def _cli_surface_block() -> str:
    lines = []
    for name, meta in sorted(SURFACE["subcommands"].items()):
        help_text = meta.get("help", "")
        lines.append(f"      keelspec {name:<10} {help_text}")
        if meta.get("flags"):
            lines.append(f"        flags: {', '.join(sorted(meta['flags']))}")
    lines.append(f"      global flags: {', '.join(sorted(SURFACE.get('global_flags', [])))}")
    return "\n".join(lines)


SYSTEM = f"""\
You write the KeelSpec newsletter.

KeelSpec is a Python tool that turns product intent -- glossaries, business rules,
features, decisions -- into typed artifacts, validates them as a reference graph,
compiles a JSON bundle, and fails CI when the committed bundle drifts from its
sources. Diagnostics carry stable codes (PAC-001 required field, PAC-020 dangling
reference, PAC-060 staleness). It was extracted from the pharthing / KibiPay
payments platform.

Audience: staff engineers, engineering managers and technical product people. They
are sceptical of marketing and allergic to hype.

Rules:
- Lead with one concrete idea. No throat-clearing, no "in today's fast-paced world".
- Be specific: name diagnostic codes, show a config snippet or a CLI line where it helps.
- 250-400 words. Shorter is better than padded.
- No emoji. No exclamation marks. No "we're excited to announce".
- Do not invent features, customers, metrics, or version numbers. If you are unsure
  whether something exists, write about the idea instead of the feature.
- THE ENTIRE CLI SURFACE IS:
{_cli_surface_block()}
  There are no other subcommands and no other flags. Never write `--check`,
  `--strict`, `--fix`, `keelspec lint`, or anything else. Staleness is checked by
  `keelspec validate` -- it is not a separate command.
- The config file is `product.config.yaml` and it is YAML. There is no TOML, JSON
  or INI config. Do not invent filenames or extensions for it.
- Artifacts are markdown with YAML frontmatter under the configured `product_dir`.
  The compiled output is a single JSON bundle at the configured `output` path.
- Plain markdown: ## for the one subheading if you need it, - for lists, ` for code.
  No images, no HTML, no front matter.
"""


def _client():
    """Imported lazily: generation is optional, and the site must still serve pages
    (and capture leads) if the SDK or the key is missing."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    try:
        import anthropic
    except ModuleNotFoundError as exc:
        raise RuntimeError("the anthropic package is not installed") from exc
    return anthropic.Anthropic()


def _recent_posts(limit: int = 8) -> list[dict]:
    if not BUNDLE.exists():
        return []
    posts = json.loads(BUNDLE.read_text(encoding="utf-8")).get("posts", [])
    posts.sort(key=lambda p: str(p.get("date", "")), reverse=True)
    return posts[:limit]


def _previous_subjects(limit: int = 12) -> list[str]:
    with cursor() as conn:
        rows = conn.execute(
            "SELECT subject FROM newsletters ORDER BY created DESC LIMIT ?", (limit,)
        ).fetchall()
    return [r["subject"] for r in rows]


def generate(topic: str = "") -> tuple[str, str]:
    """Return (subject, markdown_body). Raises on API failure."""
    posts = _recent_posts()
    catalogue = "\n".join(
        f"- {p['title']} ({SITE}/blog/{p['slug']}.html): {p['summary']}" for p in posts
    ) or "- (no posts available)"

    avoid = _previous_subjects()
    avoid_block = ("\nSubjects already used -- pick a genuinely different angle:\n"
                   + "\n".join(f"- {s}" for s in avoid)) if avoid else ""

    ask = topic.strip() or "Pick the most useful single idea for this audience."

    prompt = f"""Write this week's issue.

{ask}

Blog posts you may reference and link (use the real URLs, do not invent others):
{catalogue}
{avoid_block}

Return JSON only, matching this shape:
{{"subject": "...", "body": "..."}}

subject: under 60 characters, specific, no colon-prefixed labels.
body: the newsletter in plain markdown, 250-400 words."""

    client = _client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["subject", "body"],
                    "additionalProperties": False,
                },
            },
        },
        messages=[{"role": "user", "content": prompt}],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("generation refused by safety classifier")

    text = "".join(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    subject, body = data["subject"].strip(), data["body"].strip()

    # Structural validation. A generation that fails this is never sent.
    if not 10 <= len(subject) <= 120:
        raise ValueError(f"subject length {len(subject)} out of range")
    words = len(body.split())
    if not 120 <= words <= 900:
        raise ValueError(f"body word count {words} out of range")
    if "<script" in body.lower():
        raise ValueError("body contains markup that should not be there")

    # Guard against invented CLI surface. An unattended send has no reviewer to
    # notice that `keelspec build --check` is not a real command, and a reader who
    # copies it gets an argparse error and concludes the tool is broken.
    for verb in re.findall(r"keelspec\s+(?:-\w+\s+\S+\s+)*([a-z][a-z-]*)", body):
        if verb not in CLI_VERBS:
            raise ValueError(f"invented CLI subcommand: keelspec {verb}")
    for line in body.splitlines():
        for flag in re.findall(r"keelspec.*?(--[a-z-]+)", line):
            if flag not in CLI_FLAGS:
                raise ValueError(f"invented CLI flag: {flag}")

    return subject, body


# ── rendering ────────────────────────────────────────────────────────────────
def md_to_html(src: str) -> str:
    out, lines, i = [], src.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            i, buf = i + 1, []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(buf))}</code></pre>")
            continue
        if line.startswith("## "):
            out.append(f"<h2>{_inline(line[3:])}</h2>"); i += 1; continue
        if re.match(r"^[-*] ", line):
            items = []
            while i < len(lines) and re.match(r"^[-*] ", lines[i]):
                items.append(f"<li>{_inline(lines[i][2:])}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>"); continue
        if not line.strip():
            i += 1; continue
        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "```", "- ", "* ")):
            para.append(lines[i].strip()); i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out)


def _inline(text: str) -> str:
    text = html.escape(text.strip())
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def email_html(subject: str, body_md: str, unsubscribe_url: str) -> str:
    """Inline styles only -- email clients discard <style> blocks."""
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#ffffff">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff">
<tr><td align="center" style="padding:32px 16px">
<table width="100%" style="max-width:560px" cellpadding="0" cellspacing="0">
  <tr><td style="padding-bottom:24px">
    <span style="display:inline-block;background:#191919;color:#ffffff;padding:8px 14px;
                 border-radius:10px;font-family:Arial Black,Arial,sans-serif;
                 font-size:18px;letter-spacing:0.5px">KeelSpec</span>
  </td></tr>
  <tr><td style="font-family:Helvetica,Arial,sans-serif;color:#191919;
                 font-size:24px;font-weight:bold;line-height:1.25;padding-bottom:18px;
                 border-bottom:3px solid #191919">{html.escape(subject)}</td></tr>
  <tr><td style="font-family:Helvetica,Arial,sans-serif;color:#333333;font-size:16px;
                 line-height:1.65;padding-top:22px">{md_to_html(body_md)}</td></tr>
  <tr><td style="padding-top:30px">
    <a href="{SITE}/blog/" style="display:inline-block;background:#fbcc00;color:#191919;
       text-decoration:none;font-family:Helvetica,Arial,sans-serif;font-weight:bold;
       font-size:15px;padding:12px 22px;border:3px solid #191919;border-radius:10px">Read the blog</a>
  </td></tr>
  <tr><td style="padding-top:34px;border-top:2px solid #e5e5e5;margin-top:20px;
                 font-family:Helvetica,Arial,sans-serif;color:#6b6b6b;font-size:12px;
                 line-height:1.6">
    You are receiving this because you subscribed at keelspec.com.<br>
    <a href="{unsubscribe_url}" style="color:#6b6b6b">Unsubscribe</a> &middot;
    <a href="{SITE}/privacy.html" style="color:#6b6b6b">Privacy</a>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def send_test(issue_id: int, to: str) -> dict:
    """Send one issue to a single address, touching nothing else.

    Deliberately separate from send(): it does not read the subscriber list, does
    not mark the issue sent, and does not write the archive. Use it to prove
    deliverability and rendering before arming unattended sending.
    """
    with cursor() as conn:
        row = conn.execute("SELECT * FROM newsletters WHERE id = ?", (issue_id,)).fetchone()
    if not row:
        raise ValueError(f"no newsletter {issue_id}")
    if not POSTMARK_TOKEN:
        raise RuntimeError("POSTMARK_TOKEN is not configured")

    payload = {
        "From": FROM_EMAIL,
        "To": to,
        "Subject": f"[test] {row['subject']}",
        "HtmlBody": email_html(row["subject"], row["body_md"],
                               f"{SITE}/api/unsubscribe?e={to}"),
        "TextBody": row["body_md"],
        "MessageStream": "broadcast",
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            "https://api.postmarkapp.com/email",
            headers={"X-Postmark-Server-Token": POSTMARK_TOKEN,
                     "Accept": "application/json"},
            json=payload,
        )
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text[:300]}
    return {"http": resp.status_code, "from": FROM_EMAIL, "to": to, "response": data}


def _slug(subject: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:60] or "issue"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{stamp}-{base}"


def save_draft(subject: str, body_md: str) -> int:
    slug = _slug(subject)
    with cursor() as conn:
        row = conn.execute("SELECT 1 FROM newsletters WHERE slug = ?", (slug,)).fetchone()
        if row:
            slug = f"{slug}-{now()}"
        cur = conn.execute(
            "INSERT INTO newsletters (slug, subject, body_md, body_html, status, created)"
            " VALUES (?, ?, ?, ?, 'draft', ?)",
            (slug, subject, body_md, md_to_html(body_md), now()),
        )
        return cur.lastrowid


# ── sending ──────────────────────────────────────────────────────────────────
def send(issue_id: int) -> dict:
    """Send one issue via Postmark. Returns a summary dict."""
    with cursor() as conn:
        row = conn.execute("SELECT * FROM newsletters WHERE id = ?", (issue_id,)).fetchone()
    if not row:
        raise ValueError(f"no newsletter {issue_id}")
    if row["status"] == "sent":
        return {"ok": True, "already_sent": True, "recipients": row["recipients"]}

    if not POSTMARK_TOKEN:
        _fail(issue_id, "POSTMARK_TOKEN is not configured")
        return {"ok": False, "error": "POSTMARK_TOKEN is not configured"}

    recipients = active_subscribers()
    if len(recipients) > MAX_RECIPIENTS:
        _fail(issue_id, f"{len(recipients)} recipients exceeds cap of {MAX_RECIPIENTS}")
        return {"ok": False, "error": "recipient cap exceeded"}
    if not recipients:
        _fail(issue_id, "no active subscribers")
        return {"ok": False, "error": "no active subscribers"}

    archive(issue_id)          # archive before sending, so the link in the email works

    sent, errors = 0, []
    with httpx.Client(timeout=30) as client:
        for batch in _chunks(recipients, 500):
            payload = [{
                "From": FROM_EMAIL,
                "To": email,
                "Subject": row["subject"],
                "HtmlBody": email_html(
                    row["subject"], row["body_md"],
                    f"{SITE}/api/unsubscribe?e={email}"),
                "TextBody": row["body_md"],
                "MessageStream": "broadcast",
            } for email in batch]

            resp = client.post(
                "https://api.postmarkapp.com/email/batch",
                headers={"X-Postmark-Server-Token": POSTMARK_TOKEN,
                         "Accept": "application/json"},
                json=payload,
            )
            if resp.status_code != 200:
                errors.append(f"HTTP {resp.status_code}: {resp.text[:200]}")
                continue
            for result in resp.json():
                if result.get("ErrorCode") == 0:
                    sent += 1
                else:
                    errors.append(f"{result.get('To')}: {result.get('Message')}")

    with cursor() as conn:
        conn.execute(
            "UPDATE newsletters SET status = ?, recipients = ?, sent_at = ?, error = ?"
            " WHERE id = ?",
            ("sent" if sent else "failed", sent, now(), " | ".join(errors[:5]), issue_id),
        )
    return {"ok": bool(sent), "recipients": sent, "errors": errors[:5]}


def _fail(issue_id: int, message: str) -> None:
    with cursor() as conn:
        conn.execute("UPDATE newsletters SET status = 'failed', error = ? WHERE id = ?",
                     (message, issue_id))


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# ── archive pages ────────────────────────────────────────────────────────────
def archive(issue_id: int | None = None) -> None:
    """(Re)write the static newsletter archive into the public webroot."""
    out = PUBLIC / "newsletters"
    out.mkdir(parents=True, exist_ok=True)

    with cursor() as conn:
        issues = conn.execute(
            "SELECT * FROM newsletters WHERE status = 'sent' ORDER BY created DESC"
        ).fetchall()
        if issue_id is not None:
            one = conn.execute("SELECT * FROM newsletters WHERE id = ?", (issue_id,)).fetchone()
            if one and one["status"] != "sent":
                issues = [one] + list(issues)

    for issue in issues:
        when = datetime.fromtimestamp(issue["created"], timezone.utc).strftime("%d %B %Y")
        (out / f"{issue['slug']}.html").write_text(_page(
            f"{issue['subject']} — KeelSpec newsletter",
            f"""<main class="section"><div class="wrap prose">
  <a class="back-link" href="/newsletters/">&larr; All issues</a>
  <span class="eyebrow">Newsletter</span>
  <h1>{html.escape(issue['subject'])}</h1>
  <p class="updated">{when}</p>
  <div class="post-body">{issue['body_html']}</div>
  <p style="margin-top:2.6rem"><a class="btn btn-primary" href="/#start">Get started with KeelSpec</a></p>
</div></main>"""), encoding="utf-8", newline="\n")

    rows = "".join(
        f"""<a class="issue" href="/newsletters/{html.escape(i['slug'])}.html">
  <span class="issue-num">#{n:02d}</span>
  <span><h3>{html.escape(i['subject'])}</h3>
    <div class="post-meta">{datetime.fromtimestamp(i['created'], timezone.utc).strftime('%d %B %Y')}</div>
  </span></a>"""
        for n, i in enumerate(reversed(list(issues)), start=1)
    ) or '<p class="lede">No issues yet. The first one is on its way.</p>'

    (out / "index.html").write_text(_page(
        "Newsletter archive — KeelSpec",
        f"""<main class="section"><div class="wrap">
  <div class="section-head">
    <span class="eyebrow">Newsletter</span>
    <h1 style="font-size:clamp(2.4rem,5vw,3.5rem);margin-top:0.7rem">Every issue, archived.</h1>
    <p class="lede">Short notes on product-as-code, twice a week. Nothing is deleted &mdash;
      if we sent it, it is here.</p>
  </div>
  <div class="issue-list">{rows}</div>
</div></main>"""), encoding="utf-8", newline="\n")


def _page(title: str, body: str) -> str:
    """Import lazily so the API container does not need the site tooling on the path."""
    favicon = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
               "<rect width='100' height='100' rx='18' fill='%23191919'/><text x='50' y='72' "
               "font-family='Arial Narrow,Impact,sans-serif' font-size='62' font-weight='900' "
               "fill='%23fbcc00' text-anchor='middle'>F</text></svg>")
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="icon" href="{favicon}">
<link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/blog.css">
</head><body>
<header class="nav"><div class="wrap nav-inner">
  <a class="logo" href="/"><svg class="logo-glyph" viewBox="0 0 40 40" aria-hidden="true"><rect x="1.6" y="1.6" width="36.8" height="36.8" rx="9" fill="#191919"/><path d="M10.5 21.5 L17 28 L29.5 12.5" fill="none" stroke="#fbcc00" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="10.5" cy="21.5" r="3.6" fill="#fff"/><circle cx="29.5" cy="12.5" r="3.6" fill="#00b67a"/></svg><span class="logo-word">KeelSpec</span></a>
  <nav class="nav-links">
    <a href="/#how">How it works</a><a href="/blog/">Blog</a>
    <a href="/newsletters/">Newsletters</a>
    <a href="https://github.com/tarvitave/keelspec">GitHub</a>
  </nav>
</div></header>
{body}
<footer class="footer"><div class="wrap"><div class="footer-base" style="border:0;margin:0">
  <span>&copy; 2026 KeelSpec</span>
  <span><a href="/privacy.html">Privacy</a> &middot; <a href="/terms.html">Terms</a></span>
</div></div></footer>
</body></html>"""
