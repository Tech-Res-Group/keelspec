"""keelspec.com API: lead capture, contact, first-party analytics, and the admin panel.

Public endpoints are deliberately few and boring. Everything interesting lives behind
/admin, which requires a session cookie.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import (HTMLResponse, JSONResponse, RedirectResponse,
                               StreamingResponse)
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field

import newsletter as nl
import seo as seo_mod
import store
from admin import router as admin_router

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
IP_SALT = os.getenv("IP_SALT", "change-me")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

scheduler = BackgroundScheduler(timezone="UTC")


# ── scheduled jobs ───────────────────────────────────────────────────────────
def scheduled_newsletter() -> None:
    """Generate and send. Runs unattended, so every failure path ends in a stored
    record rather than an exception nobody sees."""
    if not nl.AUTOSEND:
        print("[newsletter] auto-send disarmed; skipping", flush=True)
        return
    try:
        subject, body_md = nl.generate()
    except Exception as exc:
        print(f"[newsletter] generation failed: {exc}", flush=True)
        return
    issue_id = nl.save_draft(subject, body_md)
    try:
        result = nl.send(issue_id)
        print(f"[newsletter] issue {issue_id}: {result}", flush=True)
    except Exception as exc:
        print(f"[newsletter] send failed: {exc}", flush=True)


def scheduled_seo() -> None:
    try:
        summary = seo_mod.run()
        print(f"[seo] {summary['pages']} pages, {summary['issues']} issues, "
              f"{summary['fixed']} auto-fixed", flush=True)
    except Exception as exc:
        print(f"[seo] audit failed: {exc}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init()
    try:
        nl.archive()
    except Exception as exc:
        print(f"[archive] {exc}", flush=True)

    scheduler.add_job(scheduled_newsletter, CronTrigger(day_of_week="tue,fri", hour=9, minute=0),
                      id="newsletter", replace_existing=True, misfire_grace_time=3600)
    scheduler.add_job(scheduled_seo, CronTrigger(hour=3, minute=0),
                      id="seo", replace_existing=True, misfire_grace_time=3600)
    scheduler.start()
    print(f"[boot] autosend={nl.AUTOSEND} seo_autofix={seo_mod.AUTOFIX}", flush=True)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="keelspec.com", docs_url=None, redoc_url=None, lifespan=lifespan)
app.include_router(admin_router)


@app.exception_handler(StarletteHTTPException)
async def _unauthenticated_browsers_get_the_login_page(request: Request, exc):
    """A browser asking for /admin should be shown the sign-in form, not a JSON 401.

    The auth dependency raises 401 because that is the correct status; the mistake
    was letting FastAPI render it as `{"detail": "not signed in"}` for someone who
    typed a URL. API clients still get the JSON — the distinction is the Accept
    header, not the path.
    """
    if (exc.status_code == 401
            and request.url.path.startswith("/admin")
            and "text/html" in request.headers.get("accept", "")):
        return RedirectResponse("/admin/login", status_code=303)
    return await http_exception_handler(request, exc)


# ── helpers ──────────────────────────────────────────────────────────────────
_hits: dict[str, list[float]] = {}


def _rate_limited(key: str, limit: int = 12, window: float = 3600.0) -> bool:
    now_ts = time.time()
    seen = [t for t in _hits.get(key, []) if now_ts - t < window]
    seen.append(now_ts)
    _hits[key] = seen
    if len(_hits) > 10_000:
        for k in list(_hits)[:5_000]:
            _hits.pop(k, None)
    return len(seen) > limit


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "")


def _daily_visitor_hash(ip: str, ua: str) -> str:
    """A visitor id that cannot be linked across days and never stores the IP."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return hashlib.sha256(f"{IP_SALT}{day}{ip}{ua}".encode()).hexdigest()[:16]


# ── public API ───────────────────────────────────────────────────────────────
class Subscribe(BaseModel):
    email: str = Field(max_length=254)
    company: str = Field(default="", max_length=200)   # honeypot
    source: str = Field(default="landing", max_length=40)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/subscribe")
def subscribe(body: Subscribe, request: Request) -> JSONResponse:
    ip = _client_ip(request)
    if body.company.strip():
        return JSONResponse({"ok": True})          # bot: look successful, store nothing
    if _rate_limited(f"sub:{ip}"):
        raise HTTPException(status_code=429, detail="too many requests")

    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="that address does not look right")

    ip_hash = hashlib.sha256((IP_SALT + ip).encode()).hexdigest()[:16]
    with store.cursor() as conn:
        conn.execute(
            "INSERT INTO leads (email, source, ip_hash, created) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(email) DO UPDATE SET source = excluded.source",
            (email, body.source[:40], ip_hash, store.now()),
        )
        conn.execute("DELETE FROM unsubscribes WHERE email = ?", (email,))
    return JSONResponse({"ok": True})


class Contact(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(max_length=254)
    subject: str = Field(default="", max_length=120)
    message: str = Field(max_length=8000)
    website: str = Field(default="", max_length=200)   # honeypot


@app.post("/api/contact")
def contact(body: Contact, request: Request) -> JSONResponse:
    ip = _client_ip(request)
    if body.website.strip():
        return JSONResponse({"ok": True})
    if _rate_limited(f"contact:{ip}", limit=6):
        raise HTTPException(status_code=429, detail="too many requests")

    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="that address does not look right")
    if not body.message.strip() or not body.name.strip():
        raise HTTPException(status_code=422, detail="name and message are required")

    with store.cursor() as conn:
        conn.execute(
            "INSERT INTO contact_messages (name, email, subject, message, created)"
            " VALUES (?, ?, ?, ?, ?)",
            (body.name.strip()[:200], email, body.subject.strip()[:120],
             body.message.strip()[:8000], store.now()),
        )
    return JSONResponse({"ok": True})


class Track(BaseModel):
    path: str = Field(default="/", max_length=300)
    referrer: str = Field(default="", max_length=300)


@app.post("/api/track")
def track(body: Track, request: Request) -> JSONResponse:
    """First-party analytics. No cookies, no stored IP, no cross-site anything."""
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")
    if _rate_limited(f"trk:{ip}", limit=400):
        return JSONResponse({"ok": True})

    ref = body.referrer.strip()
    if "keelspec.com" in ref or ref.startswith("http://localhost"):
        ref = ""                                    # internal navigation is not a referrer

    with store.cursor() as conn:
        conn.execute(
            "INSERT INTO pageviews (path, referrer, visitor, created) VALUES (?, ?, ?, ?)",
            (body.path[:300], ref[:300], _daily_visitor_hash(ip, ua), store.now()),
        )
    return JSONResponse({"ok": True})


@app.get("/api/unsubscribe", response_class=HTMLResponse)
def unsubscribe(e: str = "") -> HTMLResponse:
    email = e.strip().lower()
    if EMAIL_RE.match(email):
        store.unsubscribe(email)
        headline, detail = "Unsubscribed.", "You will not receive any more email from us."
    else:
        headline, detail = "Nothing to do.", "That link did not contain a valid address."

    return HTMLResponse(f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{headline} · KeelSpec</title>
<link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/blog.css"></head>
<body><main class="section"><div class="wrap prose" style="text-align:center">
<h1>{headline}</h1><p class="lede" style="margin-top:1rem">{detail}</p>
<p style="margin-top:2rem"><a class="btn btn-primary" href="/">Back to the site</a></p>
</div></main></body></html>""")


@app.get("/api/leads.csv")
def export_leads(authorization: str = Header(default="")) -> StreamingResponse:
    if not ADMIN_TOKEN or authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "source", "created_utc"])
    with store.cursor() as conn:
        for email, source, created in conn.execute(
            "SELECT email, source, created FROM leads ORDER BY created"
        ):
            writer.writerow([email, source,
                             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created))])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="leads.csv"'})
