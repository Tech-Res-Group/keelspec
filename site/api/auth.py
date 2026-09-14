"""Admin authentication.

The password is a weak, human-chosen one, so the compensating controls matter more
than usual: bcrypt at cost 12, per-IP lockout after repeated failures, signed
session cookies with a short lifetime, and constant-time comparison on the username.
The hash lives in the server's .env and never in the repository.
"""
from __future__ import annotations

import hmac
import os
import time

import bcrypt
from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from store import cursor, now

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")

COOKIE = "keelspec_admin"
SESSION_MAX_AGE = 12 * 3600          # re-login twice a day
LOCKOUT_FAILS = 5
LOCKOUT_SECONDS = 15 * 60

_serializer = URLSafeTimedSerializer(SESSION_SECRET or "unset", salt="keelspec-admin")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "")


def locked_out(ip: str) -> int:
    """Seconds remaining on a lockout, or 0."""
    with cursor() as conn:
        row = conn.execute("SELECT fails, last FROM login_attempts WHERE ip = ?", (ip,)).fetchone()
    if not row or row["fails"] < LOCKOUT_FAILS:
        return 0
    remaining = LOCKOUT_SECONDS - (now() - row["last"])
    return max(0, remaining)


def _record_failure(ip: str) -> None:
    with cursor() as conn:
        conn.execute(
            "INSERT INTO login_attempts (ip, fails, last) VALUES (?, 1, ?)"
            " ON CONFLICT(ip) DO UPDATE SET fails = fails + 1, last = excluded.last",
            (ip, now()),
        )


def _clear_failures(ip: str) -> None:
    with cursor() as conn:
        conn.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))


def verify(username: str, password: str, request: Request) -> bool:
    """Check credentials, applying per-IP lockout. Raises 429 while locked out."""
    ip = _client_ip(request)

    remaining = locked_out(ip)
    if remaining:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {remaining // 60 + 1} minutes.",
        )

    if not ADMIN_PASSWORD_HASH:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD_HASH is not configured")

    user_ok = hmac.compare_digest(username.strip(), ADMIN_USER)
    try:
        pass_ok = bcrypt.checkpw(password.encode(), ADMIN_PASSWORD_HASH.encode())
    except ValueError:
        pass_ok = False

    # Always evaluate both so a wrong username is not faster than a wrong password.
    if user_ok and pass_ok:
        _clear_failures(ip)
        return True

    _record_failure(ip)
    time.sleep(0.4)          # blunt the rate of online guessing
    return False


def issue_session(response: Response) -> None:
    token = _serializer.dumps({"u": ADMIN_USER})
    response.set_cookie(
        COOKIE, token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def current_admin(request: Request) -> str:
    """FastAPI dependency: the logged-in admin, or 401."""
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not signed in")
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="session expired")
    except BadSignature:
        raise HTTPException(status_code=401, detail="invalid session")
    return data.get("u", "")


def hash_password(plain: str) -> str:
    """Helper for generating the value that goes in ADMIN_PASSWORD_HASH."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


if __name__ == "__main__":       # python auth.py 'somepassword'
    import sys
    print(hash_password(sys.argv[1]))
