"""Cross-cutting security controls, wired into the app in core.py.

Covers the layers the framework does not give us for free:

  transport/browser — security response headers, hardened session cookies
  request           — CSRF validation on every state-changing request
  authentication    — brute-force lockout on the login route
  data              — identifier allowlist for the few dynamic-table queries
  files             — upload extension allowlist

Depends only on constants + db, so it sits beside the other low-level modules
and never imports routes or core (core imports it, not the reverse).
"""
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import abort, request, session

from db import get_db

# --- authentication: brute-force lockout -----------------------------------

IDLE_SESSION_MINUTES = 60   # no request for this long → sign in again
ABSOLUTE_SESSION_HOURS = 12 # sign in again after this, however active

MAX_LOGIN_FAILURES = 5      # failures per username+IP within the window
LOGIN_WINDOW_MINUTES = 15   # rolling window
LOGIN_LOCKOUT_MINUTES = 15  # how long the block lasts once tripped

# --- files: upload allowlist ------------------------------------------------
# Business documents only. Deliberately excludes anything the browser will
# execute or render as active content (.html, .svg, .js) — those become stored
# XSS the moment a document is opened inline instead of downloaded.
ALLOWED_UPLOAD_EXTENSIONS = {
    "pdf", "png", "jpg", "jpeg", "gif", "webp",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "csv", "txt", "msg", "eml", "zip",
}

# The data-layer identifier allowlist lives in db.assert_safe_table — it has to
# sit there rather than here, because security.py imports db and the reverse
# would be an import cycle.


def allowed_upload(filename):
    """True if the filename carries an allowed document extension."""
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


# --- authentication ---------------------------------------------------------


def _login_window_start():
    return (datetime.utcnow() - timedelta(minutes=LOGIN_WINDOW_MINUTES)).isoformat()


def login_is_blocked(username):
    """True when this username+IP pair has burned through its attempts."""
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS failures FROM login_attempts "
        "WHERE username = ? AND ip_address IS ? AND success = 0 AND attempted_at > ?",
        (username, request.remote_addr, _login_window_start()),
    ).fetchone()
    return row["failures"] >= MAX_LOGIN_FAILURES


def record_login_attempt(username, success):
    """Log an attempt; a success clears the failure streak for that pair."""
    db = get_db()
    db.execute(
        "INSERT INTO login_attempts (username, ip_address, attempted_at, success) VALUES (?, ?, ?, ?)",
        (username, request.remote_addr, datetime.utcnow().isoformat(), 1 if success else 0),
    )
    if success:
        db.execute(
            "DELETE FROM login_attempts WHERE username = ? AND ip_address IS ? AND success = 0",
            (username, request.remote_addr),
        )
    # opportunistic cleanup so the table cannot grow without bound
    db.execute(
        "DELETE FROM login_attempts WHERE attempted_at < ?",
        ((datetime.utcnow() - timedelta(days=7)).isoformat(),),
    )
    db.commit()


def rate_limited(key, limit, window_minutes):
    """Generic per-key+IP throttle, riding on the login_attempts table so it
    needs no schema of its own. Returns True (and records nothing) once the
    limit is hit; otherwise records this hit and returns False. Used for the
    guest-link write endpoints, which are reachable without a login."""
    db = get_db()
    since = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()
    hits = db.execute(
        "SELECT COUNT(*) AS n FROM login_attempts "
        "WHERE username = ? AND ip_address IS ? AND success = 0 AND attempted_at > ?",
        (key, request.remote_addr, since),
    ).fetchone()["n"]
    if hits >= limit:
        return True
    record_login_attempt(key, success=False)
    return False


# Leading bytes each allowed type must start with. Types absent here (txt, csv,
# eml) have no reliable signature and are accepted on extension alone.
FILE_SIGNATURES = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG",),
    "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "webp": (b"RIFF",),
    "docx": (b"PK\x03\x04",), "xlsx": (b"PK\x03\x04",), "pptx": (b"PK\x03\x04",), "zip": (b"PK\x03\x04",),
    "doc": (b"\xd0\xcf\x11\xe0",), "xls": (b"\xd0\xcf\x11\xe0",), "ppt": (b"\xd0\xcf\x11\xe0",), "msg": (b"\xd0\xcf\x11\xe0",),
}


def content_matches_extension(file):
    """True if the upload's first bytes match what its extension claims.

    The extension allowlist stops .html; this stops an HTML document renamed
    to .pdf. Neither is antivirus — a clamd sidecar is the next layer up.
    """
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    signatures = FILE_SIGNATURES.get(ext)
    if not signatures:
        return True
    head = file.stream.read(8)
    file.stream.seek(0)
    return any(head.startswith(sig) for sig in signatures)


# --- authentication: email sign-in links for external accounts --------------
#
# The link is a bearer credential travelling through email, so: 256 bits of
# entropy, only its SHA-256 stored, one use, a short life, and every issue and
# use lands in the audit trail (done by the routes).

LINK_TTL_MINUTES = 30


def issue_login_link(user_id, created_by=None):
    """Mint a single-use sign-in link for a user; returns the raw token, which
    exists only in the email (and the inviter's fallback flash)."""
    import hashlib
    raw = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    get_db().execute(
        "INSERT INTO login_links (user_id, token_hash, created_at, expires_at, created_by, ip_address) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, hashlib.sha256(raw.encode()).hexdigest(), now.isoformat(),
         (now + timedelta(minutes=LINK_TTL_MINUTES)).isoformat(), created_by, request.remote_addr),
    )
    get_db().commit()
    return raw


def consume_login_link(raw):
    """The user for a valid, unexpired, unused link — marking it used — or
    None. Invalid for internal accounts: they sign in with a password."""
    import hashlib
    db = get_db()
    row = db.execute(
        "SELECT l.*, u.active, u.kind FROM login_links l JOIN users u ON u.id = l.user_id WHERE l.token_hash = ?",
        (hashlib.sha256((raw or "").encode()).hexdigest(),),
    ).fetchone()
    if row is None or row["used_at"] or row["expires_at"] < datetime.utcnow().isoformat():
        return None
    if not row["active"] or row["kind"] != "external":
        return None
    db.execute("UPDATE login_links SET used_at = ? WHERE id = ?", (datetime.utcnow().isoformat(), row["id"]))
    db.commit()
    return db.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()


# Deliberately loose — one @, a dot in the domain, no whitespace. Enough to
# catch fat-finger input; real deliverability is proven by the test-email button.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email):
    """True for a plausibly-formatted address. Empty is caller's call."""
    return bool(_EMAIL_RE.match(email))


# Substrings that make a password guessable regardless of what surrounds them.
WEAK_PASSWORD_TERMS = ("password", "changeme", "letmein", "qwerty", "odin", "projectlifecycle")


def password_problem(password):
    """Return a human-readable reason the password is unacceptable, else None."""
    if len(password) < 12:
        return "Password must be at least 12 characters"
    if password.isdigit() or password.isalpha():
        return "Password must mix letters with numbers or symbols"
    # Substring, not equality: the exact-match version happily accepted
    # "changeme1234", which is the app's own default with digits stapled on —
    # the single most predictable thing a user rotating off the seed will type.
    lowered = password.lower()
    if any(term in lowered for term in WEAK_PASSWORD_TERMS):
        return "That password is too common — pick something else"
    return None


# --- request: CSRF ----------------------------------------------------------

CSRF_FIELD = "_csrf"
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def csrf_token():
    """Per-session CSRF token, minted on first use. Exposed to Jinja."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _validate_csrf():
    """before_request hook: every state-changing request must carry the token."""
    if request.method in CSRF_SAFE_METHODS:
        return None
    submitted = request.form.get(CSRF_FIELD) or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf_token", "")
    # compare_digest keeps the check constant-time; the empty-expected case
    # still fails closed because compare_digest("", "") is only reached when
    # neither side has a token, which we reject explicitly first.
    if not expected or not submitted or not secrets.compare_digest(submitted, expected):
        abort(400, description="CSRF token missing or invalid — reload the page and try again.")
    return None


# --- transport/browser: response headers ------------------------------------

# 'unsafe-inline' is required for now: the templates carry ~30 inline event
# handlers (onchange/onclick/onsubmit) and ~145 inline style attributes.
# Everything else is locked down — no third-party scripts, no framing, no
# plugins, and forms can only post back to this origin.
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)


def _security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")          # legacy clickjacking guard
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
    )
    # Only meaningful over TLS; harmless otherwise, and correct once nginx
    # terminates HTTPS in front of the app.
    if request.is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


# --- wiring -----------------------------------------------------------------


def init_security(app):
    """Apply cookie hardening and register the CSRF + headers hooks."""
    # Behind nginx every request arrives from 127.0.0.1, which would make the
    # audit log useless and — worse — collapse the login rate limiter into a
    # single shared bucket, letting one attacker lock out every user. Trust the
    # X-Forwarded-* headers only when PMS_TRUST_PROXY=1 says a proxy is really
    # in front (trusting them otherwise would let clients spoof their own IP).
    if os.environ.get("PMS_TRUST_PROXY") == "1":
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,   # JS cannot read the session cookie
        SESSION_COOKIE_SAMESITE="Lax",  # blocks cross-site POST cookie attachment
        # Set PMS_HTTPS=1 in production (behind TLS) so the cookie is never
        # sent over plaintext. Left off by default so local HTTP dev works.
        SESSION_COOKIE_SECURE=os.environ.get("PMS_HTTPS") == "1",
        # Idle cap. The absolute cap (ABSOLUTE_SESSION_HOURS) is enforced in
        # core._auth_gate, since Flask only refreshes the idle one.
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=IDLE_SESSION_MINUTES),
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,  # 25 MB per upload
    )
    app.before_request(_validate_csrf)
    app.after_request(_security_headers)
    app.jinja_env.globals["csrf_token"] = csrf_token
    return app
