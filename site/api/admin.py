"""The admin panel: dashboard, analytics, newsletters, SEO.

Server-rendered HTML in the site's own visual language. No build step, no SPA --
this is an internal tool with one user, and every dependency here would be a
dependency that has to be kept patched on a public-facing box.
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

import newsletter as nl
import seo as seo_mod
from auth import clear_session, current_admin, issue_session, verify
from store import cursor, now

router = APIRouter()

CSS = """
:root{--ink:#191919;--paper:#fff;--grid:#e5e5e5;--muted:#6b6b6b;--yellow:#fbcc00;
--green:#00b67a;--orange:#ff6b4a;--blue:#4a90e2;--purple:#b47cff;--red:#e5384f;--cream:#fff9e6;
--bd:3px solid var(--ink);--r:12px;--sh:4px 4px 0 var(--ink);--sh-sm:2px 2px 0 var(--ink);
--mono:'IBM Plex Mono',ui-monospace,Menlo,monospace}
*{box-sizing:border-box;margin:0}
body{font-family:'IBM Plex Sans',-apple-system,Segoe UI,sans-serif;background:#fff;color:var(--ink);
background-image:radial-gradient(var(--grid) 1.6px,transparent 1.6px);background-size:26px 26px;line-height:1.6}
h1,h2,h3{font-family:'Anton','Arial Narrow',Impact,sans-serif;font-weight:400;letter-spacing:.4px;line-height:1}
a{color:inherit}
.wrap{max-width:1100px;margin:0 auto;padding:0 1.5rem}
.top{background:var(--ink);color:#fff;border-bottom:var(--bd);padding:.9rem 0;margin-bottom:2.2rem}
.top .wrap{display:flex;align-items:center;gap:1.4rem;flex-wrap:wrap}
.top .brand{font-family:'Anton',Impact,sans-serif;font-size:1.2rem;background:#fff;color:var(--ink);
padding:.3rem .6rem;border-radius:10px;text-decoration:none}
.top nav{display:flex;gap:1.1rem;margin-left:auto;flex-wrap:wrap}
.top nav a{text-decoration:none;font-weight:600;font-size:.9rem;text-transform:uppercase;
letter-spacing:.3px;padding-bottom:2px;border-bottom:3px solid transparent}
.top nav a:hover,.top nav a.on{border-bottom-color:var(--yellow)}
.card{background:#fff;border:var(--bd);border-radius:var(--r);box-shadow:var(--sh);padding:1.5rem;margin-bottom:1.5rem}
.grid{display:grid;gap:1.2rem}
.g4{grid-template-columns:repeat(4,1fr)}.g2{grid-template-columns:1fr 1fr}
@media(max-width:820px){.g4,.g2{grid-template-columns:1fr 1fr}}
@media(max-width:520px){.g4,.g2{grid-template-columns:1fr}}
.stat{padding:1.2rem;background:#fff;border:var(--bd);border-radius:var(--r);box-shadow:var(--sh)}
.stat b{display:block;font-family:'Anton',Impact,sans-serif;font-size:2.4rem;line-height:1}
.stat span{font-size:.88rem;font-weight:600;color:#444}
.btn{display:inline-flex;align-items:center;gap:.5rem;padding:.7rem 1.2rem;font-weight:700;
font-size:.92rem;text-transform:uppercase;letter-spacing:.4px;text-decoration:none;cursor:pointer;
background:#fff;border:var(--bd);border-radius:10px;box-shadow:var(--sh-sm)}
.btn:active{transform:translate(2px,2px);box-shadow:none}
.btn-primary{background:var(--yellow)}
.btn-danger{background:var(--red);color:#fff}
.btn-sm{padding:.4rem .7rem;font-size:.78rem}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th,td{text-align:left;padding:.65rem .5rem;border-bottom:2px solid var(--grid)}
th{font-family:var(--mono);font-size:.74rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.pill{display:inline-block;padding:.15rem .5rem;border-radius:6px;border:2px solid var(--ink);
font-family:var(--mono);font-size:.72rem;font-weight:600}
.pill.sent{background:var(--green);color:#fff}.pill.draft{background:var(--yellow)}
.pill.failed{background:var(--red);color:#fff}
.pill.error{background:var(--red);color:#fff}.pill.warn{background:var(--yellow)}
.pill.on{background:var(--green);color:#fff}.pill.off{background:var(--grid)}
input,textarea,select{font:inherit;width:100%;padding:.75rem .9rem;background:#fff;
border:var(--bd);border-radius:10px;box-shadow:var(--sh-sm)}
label{display:block;font-weight:600;margin:.9rem 0 .35rem}
.bar{height:10px;background:var(--grid);border-radius:99px;overflow:hidden;margin-top:.35rem}
.bar i{display:block;height:100%;background:var(--blue)}
.flash{padding:.9rem 1.1rem;border:var(--bd);border-radius:var(--r);box-shadow:var(--sh-sm);
margin-bottom:1.4rem;font-weight:600}
.flash.ok{background:#dff5ec}.flash.err{background:#ffe4e4}
.muted{color:var(--muted)}
code{font-family:var(--mono);font-size:.88em;background:var(--cream);border:1px solid #e2d6a8;
border-radius:5px;padding:.05em .35em}
.login{max-width:26rem;margin:8vh auto}
"""


def shell(title: str, body: str, tab: str = "") -> HTMLResponse:
    def cls(name: str) -> str:
        return ' class="on"' if name == tab else ""
    return HTMLResponse(f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{html.escape(title)} · KeelSpec admin</title>
<link rel="stylesheet" href="/fonts/fonts.css">
<style>{CSS}</style></head><body>
<div class="top"><div class="wrap">
  <a class="brand" href="/admin/"><svg viewBox="0 0 40 40" width="22" height="22" style="vertical-align:-4px;margin-right:6px"><rect x="1.6" y="1.6" width="36.8" height="36.8" rx="9" fill="#191919"/><path d="M10.5 21.5 L17 28 L29.5 12.5" fill="none" stroke="#fbcc00" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="10.5" cy="21.5" r="3.6" fill="#fff"/><circle cx="29.5" cy="12.5" r="3.6" fill="#00b67a"/></svg>KeelSpec</a>
  <nav>
    <a href="/admin/"{cls('home')}>Dashboard</a>
    <a href="/admin/analytics"{cls('analytics')}>Analytics</a>
    <a href="/admin/newsletters"{cls('news')}>Newsletters</a>
    <a href="/admin/seo"{cls('seo')}>SEO</a>
    <a href="/admin/subscribers"{cls('subs')}>Subscribers</a>
    <a href="/admin/logout">Sign out</a>
  </nav>
</div></div>
<div class="wrap">{body}</div></body></html>""")


def when(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d %b %Y %H:%M UTC")


# ── login ────────────────────────────────────────────────────────────────────
LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Sign in · KeelSpec admin</title>
<link rel="stylesheet" href="/fonts/fonts.css">
<style>%s</style></head><body><div class="wrap login">
<div class="card">
  <h1 style="font-size:2rem">Admin</h1>
  <p class="muted" style="margin-top:.6rem;font-size:.92rem">Restricted. All attempts are logged.</p>
  %s
  <form method="post" action="/admin/login" style="margin-top:1.2rem">
    <label for="u">Username</label>
    <input id="u" name="username" autocomplete="username" required autofocus>
    <label for="p">Password</label>
    <input id="p" name="password" type="password" autocomplete="current-password" required>
    <button class="btn btn-primary" style="margin-top:1.3rem;width:100%%;justify-content:center">Sign in</button>
  </form>
</div></div></body></html>"""


@router.get("/admin/login", response_class=HTMLResponse)
def login_form(error: str = ""):
    banner = f'<div class="flash err">{html.escape(error)}</div>' if error else ""
    return HTMLResponse(LOGIN_PAGE % (CSS, banner))


@router.post("/admin/login")
def login(request: Request, username: str = Form(""), password: str = Form("")):
    if not verify(username, password, request):
        return RedirectResponse("/admin/login?error=Incorrect+username+or+password", 303)
    response = RedirectResponse("/admin/", 303)
    issue_session(response)
    return response


@router.get("/admin/logout")
def logout():
    response = RedirectResponse("/admin/login", 303)
    clear_session(response)
    return response


# ── dashboard ────────────────────────────────────────────────────────────────
@router.get("/admin/", response_class=HTMLResponse)
def dashboard(admin: str = Depends(current_admin)):
    day = now() - 86400
    week = now() - 7 * 86400
    with cursor() as conn:
        subs = conn.execute(
            "SELECT COUNT(*) c FROM leads WHERE email NOT IN (SELECT email FROM unsubscribes)"
        ).fetchone()["c"]
        views_24 = conn.execute("SELECT COUNT(*) c FROM pageviews WHERE created > ?", (day,)).fetchone()["c"]
        views_7 = conn.execute("SELECT COUNT(*) c FROM pageviews WHERE created > ?", (week,)).fetchone()["c"]
        issues = conn.execute("SELECT COUNT(*) c FROM newsletters WHERE status='sent'").fetchone()["c"]
        last_issue = conn.execute(
            "SELECT subject, created, status FROM newsletters ORDER BY created DESC LIMIT 1").fetchone()
        msgs = conn.execute("SELECT COUNT(*) c FROM contact_messages WHERE handled=0").fetchone()["c"]

    report = seo_mod.latest()
    autosend = nl.AUTOSEND
    postmark = bool(nl.POSTMARK_TOKEN)
    anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))

    def flag(ok: bool, on="on", off="off"):
        return f'<span class="pill {"on" if ok else "off"}">{on if ok else off}</span>'

    body = f"""
<h1 style="font-size:2.4rem;margin-bottom:1.4rem">Dashboard</h1>
<div class="grid g4" style="margin-bottom:1.5rem">
  <div class="stat"><b style="color:var(--green)">{subs}</b><span>subscribers</span></div>
  <div class="stat"><b style="color:var(--blue)">{views_24}</b><span>views, 24h</span></div>
  <div class="stat"><b style="color:var(--purple)">{views_7}</b><span>views, 7d</span></div>
  <div class="stat"><b style="color:var(--orange)">{issues}</b><span>issues sent</span></div>
</div>

<div class="grid g2">
  <div class="card">
    <h2>Automation</h2>
    <table style="margin-top:.9rem">
      <tr><td>Newsletter auto-send</td><td style="text-align:right">{flag(autosend, "armed", "disarmed")}</td></tr>
      <tr><td>Schedule</td><td style="text-align:right"><code>Tue &amp; Fri 09:00 UTC</code></td></tr>
      <tr><td>Postmark token</td><td style="text-align:right">{flag(postmark, "set", "missing")}</td></tr>
      <tr><td>Anthropic key</td><td style="text-align:right">{flag(anthropic_key, "set", "missing")}</td></tr>
      <tr><td>SEO auto-fix</td><td style="text-align:right">{flag(seo_mod.AUTOFIX)}</td></tr>
      <tr><td>Recipient cap</td><td style="text-align:right"><code>{nl.MAX_RECIPIENTS}</code></td></tr>
    </table>
    <p class="muted" style="margin-top:1rem;font-size:.86rem">Auto-send is controlled by
      <code>NEWSLETTER_AUTOSEND</code> in the server's <code>.env</code>. Set it to
      <code>off</code> and restart to stop all automatic sending immediately.</p>
  </div>

  <div class="card">
    <h2>Latest</h2>
    <p style="margin-top:.9rem"><strong>Newsletter:</strong><br>
      {html.escape(last_issue["subject"]) if last_issue else "none yet"}
      {f'<span class="pill {last_issue["status"]}">{last_issue["status"]}</span>' if last_issue else ''}<br>
      <span class="muted" style="font-size:.86rem">{when(last_issue["created"]) if last_issue else ""}</span></p>
    <p style="margin-top:1.1rem"><strong>SEO audit:</strong><br>
      {f'{report["pages"]} pages, {report["issues"]} issues, {report["fixed"]} auto-fixed' if report else 'not run yet'}<br>
      <span class="muted" style="font-size:.86rem">{when(report["created"]) if report else ""}</span></p>
    <p style="margin-top:1.1rem"><strong>Unread contact messages:</strong> {msgs}</p>
  </div>
</div>

<div class="card">
  <h2>Actions</h2>
  <div style="display:flex;gap:.8rem;flex-wrap:wrap;margin-top:1rem">
    <form method="post" action="/admin/newsletters/generate"><button class="btn btn-primary">Generate a draft now</button></form>
    <form method="post" action="/admin/seo/run"><button class="btn">Run SEO audit now</button></form>
    <a class="btn" href="/admin/subscribers/export">Export subscribers</a>
  </div>
</div>"""
    return shell("Dashboard", body, "home")


# ── analytics ────────────────────────────────────────────────────────────────
@router.get("/admin/analytics", response_class=HTMLResponse)
def analytics(days: int = 7, admin: str = Depends(current_admin)):
    days = max(1, min(days, 90))
    since = now() - days * 86400
    with cursor() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM pageviews WHERE created > ?", (since,)).fetchone()["c"]
        uniq = conn.execute(
            "SELECT COUNT(DISTINCT visitor) c FROM pageviews WHERE created > ? AND visitor <> ''",
            (since,)).fetchone()["c"]
        pages = conn.execute(
            "SELECT path, COUNT(*) c FROM pageviews WHERE created > ? GROUP BY path"
            " ORDER BY c DESC LIMIT 25", (since,)).fetchall()
        refs = conn.execute(
            "SELECT referrer, COUNT(*) c FROM pageviews WHERE created > ? AND referrer <> ''"
            " GROUP BY referrer ORDER BY c DESC LIMIT 15", (since,)).fetchall()
        daily = conn.execute(
            "SELECT date(created,'unixepoch') d, COUNT(*) c FROM pageviews"
            " WHERE created > ? GROUP BY d ORDER BY d", (since,)).fetchall()

    peak = max([r["c"] for r in daily], default=1) or 1
    top = max([r["c"] for r in pages], default=1) or 1

    day_rows = "".join(
        f'<tr><td><code>{r["d"]}</code></td><td style="width:70%">'
        f'<div class="bar"><i style="width:{r["c"]/peak*100:.0f}%"></i></div></td>'
        f'<td style="text-align:right">{r["c"]}</td></tr>' for r in daily) or \
        '<tr><td colspan="3" class="muted">No data yet.</td></tr>'

    page_rows = "".join(
        f'<tr><td><a href="{html.escape(r["path"])}">{html.escape(r["path"])}</a></td>'
        f'<td style="width:55%"><div class="bar"><i style="width:{r["c"]/top*100:.0f}%;background:var(--green)"></i></div></td>'
        f'<td style="text-align:right">{r["c"]}</td></tr>' for r in pages) or \
        '<tr><td colspan="3" class="muted">No data yet.</td></tr>'

    ref_rows = "".join(
        f'<tr><td>{html.escape(r["referrer"][:70])}</td>'
        f'<td style="text-align:right">{r["c"]}</td></tr>' for r in refs) or \
        '<tr><td colspan="2" class="muted">No external referrers yet.</td></tr>'

    body = f"""
<h1 style="font-size:2.4rem">Analytics</h1>
<p class="muted" style="margin:.6rem 0 1.4rem">First-party, cookieless. No IP addresses are stored —
  the visitor column is a hash that rotates daily, so it counts uniques without identifying anyone.</p>

<div style="display:flex;gap:.6rem;margin-bottom:1.4rem;flex-wrap:wrap">
  <a class="btn btn-sm" href="?days=1">24h</a><a class="btn btn-sm" href="?days=7">7d</a>
  <a class="btn btn-sm" href="?days=30">30d</a><a class="btn btn-sm" href="?days=90">90d</a>
</div>

<div class="grid g2" style="margin-bottom:1.5rem">
  <div class="stat"><b style="color:var(--blue)">{total}</b><span>page views, last {days}d</span></div>
  <div class="stat"><b style="color:var(--green)">{uniq}</b><span>unique visitors (approx.)</span></div>
</div>

<div class="card"><h2>By day</h2><table style="margin-top:.9rem">{day_rows}</table></div>
<div class="card"><h2>Top pages</h2><table style="margin-top:.9rem">{page_rows}</table></div>
<div class="card"><h2>Referrers</h2><table style="margin-top:.9rem">{ref_rows}</table></div>"""
    return shell("Analytics", body, "analytics")


# ── newsletters ──────────────────────────────────────────────────────────────
@router.get("/admin/newsletters", response_class=HTMLResponse)
def newsletters(msg: str = "", err: str = "", admin: str = Depends(current_admin)):
    with cursor() as conn:
        rows = conn.execute("SELECT * FROM newsletters ORDER BY created DESC LIMIT 60").fetchall()

    items = "".join(f"""<tr>
      <td><strong>{html.escape(r["subject"])}</strong><br>
          <span class="muted" style="font-size:.82rem">{when(r["created"])}</span></td>
      <td><span class="pill {r["status"]}">{r["status"]}</span></td>
      <td style="text-align:right">{r["recipients"] or "—"}</td>
      <td style="text-align:right;white-space:nowrap">
        <a class="btn btn-sm" href="/admin/newsletters/{r["id"]}">Open</a>
        {'<a class="btn btn-sm" href="/newsletters/' + html.escape(r["slug"]) + '.html">View</a>' if r["status"] == "sent" else ""}
      </td></tr>""" for r in rows) or '<tr><td colspan="4" class="muted">No issues yet.</td></tr>'

    banner = ""
    if msg:
        banner = f'<div class="flash ok">{html.escape(msg)}</div>'
    if err:
        banner = f'<div class="flash err">{html.escape(err)}</div>'

    body = f"""
{banner}
<h1 style="font-size:2.4rem">Newsletters</h1>
<p class="muted" style="margin:.6rem 0 1.4rem">Generated by Claude and sent automatically
  on <code>Tue &amp; Fri 09:00 UTC</code>. Auto-send is
  <span class="pill {'on' if nl.AUTOSEND else 'off'}">{'armed' if nl.AUTOSEND else 'disarmed'}</span>
  — a draft sitting here when its window arrives will go out to every subscriber.
  Delete it before then if it is wrong.</p>

<div class="card">
  <h2>Generate a draft</h2>
  <form method="post" action="/admin/newsletters/generate">
    <label for="topic">Steer it (optional)</label>
    <input id="topic" name="topic" placeholder="e.g. why committing the generated bundle is worth it">
    <button class="btn btn-primary" style="margin-top:1rem">Generate</button>
  </form>
</div>

<div class="card"><h2>All issues</h2>
  <table style="margin-top:.9rem">
    <tr><th>Subject</th><th>Status</th><th style="text-align:right">Sent to</th><th></th></tr>
    {items}
  </table>
</div>"""
    return shell("Newsletters", body, "news")


@router.post("/admin/newsletters/generate")
def generate(topic: str = Form(""), admin: str = Depends(current_admin)):
    try:
        subject, body_md = nl.generate(topic)
        nl.save_draft(subject, body_md)
        return RedirectResponse("/admin/newsletters?msg=Draft+generated", 303)
    except Exception as exc:  # surfaced to the operator rather than swallowed
        return RedirectResponse(f"/admin/newsletters?err={html.escape(str(exc)[:200])}", 303)


@router.get("/admin/newsletters/{issue_id}", response_class=HTMLResponse)
def view_issue(issue_id: int, admin: str = Depends(current_admin)):
    with cursor() as conn:
        r = conn.execute("SELECT * FROM newsletters WHERE id = ?", (issue_id,)).fetchone()
    if not r:
        return shell("Not found", "<div class='card'><h2>No such issue.</h2></div>", "news")

    actions = ""
    if r["status"] != "sent":
        actions = f"""
    <form method="post" action="/admin/newsletters/{issue_id}/send" style="display:inline">
      <button class="btn btn-primary">Send now to all subscribers</button></form>
    <form method="post" action="/admin/newsletters/{issue_id}/delete" style="display:inline">
      <button class="btn btn-danger">Delete draft</button></form>"""

    error = f'<div class="flash err">{html.escape(r["error"])}</div>' if r["error"] else ""

    body = f"""
{error}
<a class="btn btn-sm" href="/admin/newsletters">&larr; All issues</a>
<h1 style="font-size:2.2rem;margin-top:1rem">{html.escape(r["subject"])}</h1>
<p class="muted" style="margin:.5rem 0 1.4rem">
  <span class="pill {r["status"]}">{r["status"]}</span> &nbsp; created {when(r["created"])}
  {" &nbsp; sent " + when(r["sent_at"]) if r["sent_at"] else ""}
  {" &nbsp; to " + str(r["recipients"]) + " recipients" if r["recipients"] else ""}</p>
<div class="card">{r["body_html"]}</div>
<div style="display:flex;gap:.8rem;flex-wrap:wrap">{actions}</div>"""
    return shell(r["subject"], body, "news")


@router.post("/admin/newsletters/{issue_id}/send")
def send_issue(issue_id: int, admin: str = Depends(current_admin)):
    result = nl.send(issue_id)
    if result.get("ok"):
        return RedirectResponse(
            f"/admin/newsletters?msg=Sent+to+{result.get('recipients', 0)}+subscribers", 303)
    return RedirectResponse(
        f"/admin/newsletters?err={html.escape(str(result.get('error', 'send failed'))[:200])}", 303)


@router.post("/admin/newsletters/{issue_id}/delete")
def delete_issue(issue_id: int, admin: str = Depends(current_admin)):
    with cursor() as conn:
        conn.execute("DELETE FROM newsletters WHERE id = ? AND status <> 'sent'", (issue_id,))
    return RedirectResponse("/admin/newsletters?msg=Draft+deleted", 303)


# ── seo ──────────────────────────────────────────────────────────────────────
@router.get("/admin/seo", response_class=HTMLResponse)
def seo_page(admin: str = Depends(current_admin)):
    report = seo_mod.latest()
    if not report:
        rows, summary = '<tr><td colspan="4" class="muted">No audit has run yet.</td></tr>', ""
    else:
        rows = "".join(f"""<tr>
          <td><a href="{html.escape(i["page"])}"><code>{html.escape(i["page"])}</code></a></td>
          <td><code>{html.escape(i["code"])}</code></td>
          <td>{html.escape(i["detail"])}</td>
          <td style="text-align:right">
            {'<span class="pill on">auto-fixed</span>' if i.get("autofixed") else f'<span class="pill {i["severity"]}">{i["severity"]}</span>'}
          </td></tr>""" for i in report["detail"]) or \
            '<tr><td colspan="4" class="muted">No issues found.</td></tr>'
        summary = f"""<div class="grid g4" style="margin-bottom:1.5rem">
          <div class="stat"><b>{report["pages"]}</b><span>pages audited</span></div>
          <div class="stat"><b style="color:var(--orange)">{report["issues"]}</b><span>findings</span></div>
          <div class="stat"><b style="color:var(--green)">{report["fixed"]}</b><span>auto-fixed</span></div>
          <div class="stat"><b style="color:var(--muted);font-size:1.1rem">{when(report["created"])}</b><span>last run</span></div>
        </div>"""

    body = f"""
<h1 style="font-size:2.4rem">SEO</h1>
<p class="muted" style="margin:.6rem 0 1.4rem">Runs daily at <code>03:00 UTC</code>.
  Auto-fix is limited to metadata derived from the page's own content — missing
  descriptions, canonicals, <code>og:title</code>, and over-length tags. Headings, body copy
  and link text are reported and never rewritten.</p>
{summary}
<div class="card">
  <form method="post" action="/admin/seo/run"><button class="btn btn-primary">Run audit now</button></form>
</div>
<div class="card"><h2>Findings</h2>
  <table style="margin-top:.9rem">
    <tr><th>Page</th><th>Code</th><th>Detail</th><th style="text-align:right">Status</th></tr>
    {rows}
  </table>
</div>"""
    return shell("SEO", body, "seo")


@router.post("/admin/seo/run")
def seo_run(admin: str = Depends(current_admin)):
    seo_mod.run()
    return RedirectResponse("/admin/seo", 303)


# ── subscribers ──────────────────────────────────────────────────────────────
@router.get("/admin/subscribers", response_class=HTMLResponse)
def subscribers(admin: str = Depends(current_admin)):
    with cursor() as conn:
        rows = conn.execute(
            "SELECT l.email, l.source, l.created,"
            " (SELECT 1 FROM unsubscribes u WHERE u.email = l.email) gone"
            " FROM leads l ORDER BY l.created DESC LIMIT 500").fetchall()
        msgs = conn.execute(
            "SELECT * FROM contact_messages ORDER BY created DESC LIMIT 50").fetchall()

    def status_pill(gone) -> str:
        return ('<span class="pill off">unsubscribed</span>' if gone
                else '<span class="pill on">active</span>')

    sub_rows = "".join(
        f'<tr><td>{html.escape(r["email"])}</td><td><code>{html.escape(r["source"])}</code></td>'
        f'<td>{when(r["created"])}</td>'
        f'<td style="text-align:right">{status_pill(r["gone"])}</td></tr>'
        for r in rows) or '<tr><td colspan="4" class="muted">Nobody yet.</td></tr>'

    msg_rows = "".join(f"""<tr>
      <td><strong>{html.escape(m["name"])}</strong><br>
        <span class="muted" style="font-size:.84rem">{html.escape(m["email"])} · {when(m["created"])}</span></td>
      <td><code>{html.escape(m["subject"])}</code></td>
      <td>{html.escape(m["message"][:280])}</td></tr>""" for m in msgs) or \
        '<tr><td colspan="3" class="muted">No messages.</td></tr>'

    body = f"""
<h1 style="font-size:2.4rem">Subscribers</h1>
<div class="card" style="margin-top:1.2rem">
  <a class="btn" href="/admin/subscribers/export">Export CSV</a>
</div>
<div class="card"><h2>List</h2><table style="margin-top:.9rem">
  <tr><th>Email</th><th>Source</th><th>Joined</th><th style="text-align:right">Status</th></tr>
  {sub_rows}</table></div>
<div class="card"><h2>Contact messages</h2><table style="margin-top:.9rem">
  <tr><th>From</th><th>Subject</th><th>Message</th></tr>{msg_rows}</table></div>"""
    return shell("Subscribers", body, "subs")


@router.get("/admin/subscribers/export")
def export(admin: str = Depends(current_admin)):
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "source", "joined_utc", "status"])
    with cursor() as conn:
        for r in conn.execute(
            "SELECT l.email, l.source, l.created,"
            " (SELECT 1 FROM unsubscribes u WHERE u.email = l.email) gone"
            " FROM leads l ORDER BY l.created"
        ):
            w.writerow([r["email"], r["source"],
                        datetime.fromtimestamp(r["created"], timezone.utc).isoformat(),
                        "unsubscribed" if r["gone"] else "active"])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="subscribers.csv"'})
