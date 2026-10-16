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
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import abort, request, session

from db import get_db

# --- authentication: brute-force lockout -----------------------------------

# Session lengths, the failure limit and its window are admin policy now
# (policies.py: session_idle_minutes, session_max_hours, login_max_attempts,
# login_window_minutes). The failure window is also the pause: failures
# older than it stop counting.
UPLOAD_CEILING_MB = 100     # the server never reads more, whatever the policy
# Browser crash reports (routes/client.py), per person or address: in memory, never the database.
CLIENT_REPORTS_PER_WINDOW, CLIENT_REPORT_WINDOW_SECONDS = 10, 600

# POSTs that skip the CSRF check, each answering or logging and changing nothing: Teams'
# calls to the Odin PMS app (answered, never read) and browser crash reports (one log
# line each). /api/v1/ is Bearer-token only. The meta-tests read this list.
CSRF_EXEMPT = ("/api/teams/messages", "/api/client-errors")

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


def upload_problem(file):
    """Why this upload is refused under the admin's policy (type, then size),
    or None. The fixed allowlist above still applies underneath."""
    from policies import policy
    allowed = policy("upload_types")
    ext = file.filename.rsplit(".", 1)[1].lower() if file.filename and "." in file.filename else ""
    if not allowed_upload(file.filename) or ext not in allowed:
        return f"That file type isn't allowed. Accepted: {', '.join(allowed)}"
    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)
    limit = policy("upload_max_mb")
    if size > limit * 1024 * 1024:
        return f"That file is larger than {limit} MB"
    return None


# --- exports ------------------------------------------------------------------


class _SafeCSV:
    """csv.writer that defuses spreadsheet formulas: a cell a user can influence
    (a name, a failed-login username, a note) starting with = + - @ tab or CR is
    prefixed with ' so Excel shows it as text instead of running it."""
    def __init__(self, stream):
        import csv
        self._w = csv.writer(stream)

    def writerow(self, row):
        return self._w.writerow([("'" + c) if isinstance(c, str) and c[:1] in ("=", "+", "-", "@", "\t", "\r") else c for c in row])

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def safe_csv_writer(stream):
    return _SafeCSV(stream)


# --- authentication ---------------------------------------------------------


def _login_window_start():
    from policies import policy
    return (datetime.utcnow() - timedelta(minutes=policy("login_window_minutes"))).isoformat()


def login_is_blocked(username):
    """True when this username+IP pair has burned through its attempts, or this
    address has failed too often across every username (spraying one password
    over many accounts, review P3-3): the hard stop, checked before the
    password. Throttle keys (link:, mfa:, nudge-from: ...) hold a colon, which
    no username does, so only sign-ins count. The address limit counts the
    usernames that failed from it, so a shared office is never paused by its
    own typos."""
    from policies import policy
    db, since = get_db(), _login_window_start()
    pair = db.execute("SELECT COUNT(*) FROM login_attempts WHERE username = ? AND ip_address IS ? AND success = 0 AND attempted_at > ?",
                      (username, request.remote_addr, since)).fetchone()[0]
    # distinct usernames, not failures: an office behind one NAT mistyping its own passwords
    # counts one per person, a spray one per account it tries
    spray = db.execute("SELECT COUNT(DISTINCT username) FROM login_attempts WHERE ip_address IS ? AND success = 0 AND attempted_at > ? AND username NOT LIKE '%:%'",
                       (request.remote_addr, since)).fetchone()[0]
    return pair >= policy("login_max_attempts") or spray >= policy("login_ip_max")


def failed_attempts(key):
    """Failures for this key (a username, or mfa:<id>) inside the window, from every address."""
    return get_db().execute("SELECT COUNT(*) FROM login_attempts WHERE username = ? AND success = 0 AND attempted_at > ?",
                            (key, _login_window_start())).fetchone()[0]


def login_account_paused(username):
    """True when the account has had too many failures counted across every
    address (guessing from many machines). It only changes what a WRONG
    password hears; a correct one still signs in, or anyone could lock any
    account out by failing on purpose."""
    from policies import policy
    return failed_attempts(username) >= policy("login_account_max")


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


def _hits(key, window_minutes, any_ip=False):
    since = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()
    return get_db().execute(
        "SELECT COUNT(*) AS n FROM login_attempts WHERE username = ? AND success = 0 AND attempted_at > ?"
        + ("" if any_ip else " AND ip_address IS ?"),
        (key, since) if any_ip else (key, since, request.remote_addr),
    ).fetchone()["n"]


def rate_limited(key, limit, window_minutes, any_ip=False):
    """Generic per-key+IP throttle, riding on the login_attempts table so it
    needs no schema of its own. Returns True (and records nothing) once the
    limit is hit; otherwise records this hit and returns False. Used for the
    guest-link write endpoints, which are reachable without a login. any_ip:
    count the key from every address (a per-account or per-target limit)."""
    if _hits(key, window_minutes, any_ip) >= limit:
        return True
    record_login_attempt(key, success=False)
    return False


def mail_flooded(email, anonymous=True):
    """Emailed links (sign-in, reset, address check) to one address, from
    every network address together: at most mail_link_max an hour, so nobody
    can fill a colleague's inbox from many machines (review P3-3). Requests
    from the sign-in page (anonymous) and from the signed-in person count
    apart, so strangers using up the first never stop the second; links staff
    send (invites, Send link, a resend) are not counted at all, so the person
    can always get one from their project manager."""
    from policies import policy
    return rate_limited(f"mail-{'anon' if anonymous else 'to'}:{email.lower()}", policy("mail_link_max"), 60, any_ip=True)


def nudge_limited(sender_id, target_id):
    """Notes to colleagues (POST /api/people/<id>/notify): at most nudge_max an
    hour from one person, and nudge_pair_max from one person to one colleague
    (review P3-3). Per pair, not per colleague: one sender cannot use up what
    everyone else may send them. A refused note counts nowhere. The words to
    show, or None."""
    from policies import policy
    if _hits(f"nudge-from:{sender_id}", 60, any_ip=True) >= policy("nudge_max"):
        return "You have sent a lot of notes this hour. Try again later."
    if _hits(f"nudge-to:{sender_id}:{target_id}", 60, any_ip=True) >= policy("nudge_pair_max"):
        return "You have sent them a lot of notes this hour. Try again later."
    record_login_attempt(f"nudge-from:{sender_id}", success=False)
    record_login_attempt(f"nudge-to:{sender_id}:{target_id}", success=False)
    return None


def recheck_password(user, password, wrong):
    """The current password on an account change (password, email, two-step).
    Wrong ones count per account from every address; at login_max_attempts
    the session ends, so a stolen session cannot guess the password (review
    P3-3). None when right; else `wrong`, or why the session ended."""
    from werkzeug.security import check_password_hash
    from policies import policy
    key = f"reauth:{user['id']}"
    stored = user["password_hash"] or ""
    if failed_attempts(key) < policy("login_max_attempts") and "$" in stored and check_password_hash(stored, password or ""):
        get_db().execute("DELETE FROM login_attempts WHERE username = ?", (key,))
        get_db().commit()
        return None
    record_login_attempt(key, success=False)
    if failed_attempts(key) < policy("login_max_attempts"):
        return wrong
    from core import end_session
    from services.audit import audit_log
    audit_log("session_ended", "user", user["id"], user["username"], "too many wrong current passwords")
    end_session()
    return "Too many wrong passwords: you have been signed out. Sign in again."


def clean_text(value, limit=200):
    """Outside text (a Microsoft callback, an exception) for the audit trail
    or a page: printable characters only, capped (review P3-4)."""
    return "".join(ch for ch in str(value or "") if ch.isprintable())[:limit]


def unknown_name(typed):
    """How a sign-in for no known account is recorded: a short keyed hash, never
    what was typed (often a password in the username box) (review P3-4). The
    same text gives the same mark, so repeated guesses still count together."""
    import hmac
    from flask import current_app
    return "unknown#" + hmac.new(str(current_app.secret_key).encode(), typed.encode(), hashlib.sha256).hexdigest()[:12]


# Usernames: ASCII only, so no look-alike of an existing name (a Cyrillic "а")
# can be made by an admin or through a sign-up link (review P3-13).
_USERNAME_RE = re.compile(r"[A-Za-z0-9._@-]{1,64}")


def valid_username(name):
    return isinstance(name, str) and bool(_USERNAME_RE.fullmatch(name))


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



def token_hash(raw):
    """How a one-time link or API token is stored: its SHA-256, never the token."""
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_login_link(user_id, created_by=None, purpose="signin"):
    """Mint a single-use sign-in link for a user; returns the raw token, which
    exists only in the email (and the inviter's fallback flash)."""
    raw = secrets.token_urlsafe(32)
    from policies import policy
    now = datetime.utcnow()
    # housekeeping on the way in: a link a week past expiry has no evidential
    # value the audit trail does not already hold
    get_db().execute("DELETE FROM login_links WHERE expires_at < ?", ((now - timedelta(days=7)).isoformat(),))
    get_db().execute(
        "INSERT INTO login_links (user_id, token_hash, created_at, expires_at, created_by, ip_address, purpose, epoch) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT session_epoch FROM users WHERE id = ?))",
        (user_id, token_hash(raw), now.isoformat(),
         (now + timedelta(minutes=policy("link_minutes"))).isoformat(), created_by, request.remote_addr, purpose, user_id),
    )
    get_db().commit()
    return raw


def _live_link(raw, purpose):
    """The unused, unexpired link of this purpose for this token, with its
    account's state, or None."""
    row = get_db().execute(
        "SELECT l.*, u.active, u.kind, u.session_epoch, u.username, u.email FROM login_links l JOIN users u ON u.id = l.user_id WHERE l.token_hash = ?",
        (token_hash(raw or ""),),
    ).fetchone()
    if row is None or row["used_at"] or row["expires_at"] < datetime.utcnow().isoformat() or row["epoch"] != row["session_epoch"]:
        return None   # epoch: the password, email, role or active state changed since the link was issued
    return row if row["purpose"] == purpose else None


def take_link(row):
    """Spend a link: the guarded UPDATE lets only one of two requests racing
    with the same link win (review P3-2). The caller commits."""
    return get_db().execute("UPDATE login_links SET used_at = ? WHERE id = ? AND used_at IS NULL",
                            (datetime.utcnow().isoformat(), row["id"])).rowcount == 1


def consume_login_link(raw):
    """The user for a valid, unexpired, unused link — marking it used — or
    None. Invalid for internal accounts: they sign in with a password."""
    db = get_db()
    row = _live_link(raw, "signin")
    if row is None or not row["active"] or row["kind"] != "external" or not take_link(row):
        return None
    db.commit()
    return db.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()


def reset_link_row(raw):
    """The live password-reset link for this token, or None: unused,
    unexpired, purpose 'reset', for an active staff account."""
    row = _live_link(raw, "reset")
    return row if row and row["active"] and row["kind"] == "internal" else None


def verify_link_row(raw):
    """The live address-check link for this token (review P2-3), or None. A
    pending sign-up may use it before approval; the epoch ties it to the
    address it was sent to (every email change bumps it)."""
    row = _live_link(raw, "verify")
    return row if row and row["email"] else None


def file_stem(name, fallback="project"):
    """A project name as a download file name: ASCII letters, digits, - and _
    only (HTTP headers carry Latin-1 at most; a Chinese or Arabic name hung the
    download), at most 60 characters."""
    stem = re.sub(r"-{2,}", "-", "".join(ch if ch.isascii() and (ch.isalnum() or ch in "-_") else "-" for ch in name or "")).strip("-")[:60]
    return stem or fallback


# Deliberately loose — one @, a dot in the domain, no whitespace. Enough to
# catch fat-finger input; real deliverability is proven by the test-email button.
# No control characters, quotes, angle brackets, commas or semicolons: an
# address lands in mail headers and HTML.
_EMAIL_RE = re.compile(r"[^@\s<>\"',;\x00-\x1f\x7f]+@[^@\s<>\"',;\x00-\x1f\x7f]+\.[^@\s<>\"',;\x00-\x1f\x7f]+")


def valid_email(email):
    """True for a plausibly-formatted address. Empty is caller's call."""
    return isinstance(email, str) and len(email) <= 254 and bool(_EMAIL_RE.fullmatch(email))


# Substrings that make a password guessable regardless of what surrounds them.
WEAK_PASSWORD_TERMS = ("password", "changeme", "letmein", "qwerty", "odin", "projectlifecycle")


def password_problem(password):
    """Return a human-readable reason the password is unacceptable, else None."""
    from flask import has_app_context
    minimum = 12
    if has_app_context():
        from policies import policy
        minimum = policy("password_min_length")
    if len(password) < minimum:
        return f"Password must be at least {minimum} characters"
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
    if request.method in CSRF_SAFE_METHODS or request.path in CSRF_EXEMPT:
        return None
    if request.path.startswith("/api/v1/"):
        return None   # Bearer tokens only, never the session cookie (routes/tokens.token_required): nothing to forge
    expected = session.get("_csrf_token", "")
    # the header first; a form body is parsed only when there is a token to
    # compare it with, so an anonymous multipart post is refused unread (review P3-10)
    submitted = request.headers.get("X-CSRF-Token") or (expected and request.form.get(CSRF_FIELD)) or ""
    # compare_digest keeps the check constant-time; the empty-expected case
    # still fails closed because compare_digest("", "") is only reached when
    # neither side has a token, which we reject explicitly first.
    # bytes: compare_digest raises on a non-ASCII str, and the header is the caller's
    if not expected or not submitted or not secrets.compare_digest(submitted.encode(), expected.encode()):
        from flask import g
        g.csrf_failed = True   # a fetch caller's 400 carries a fresh token (core._error_page)
        abort(400, description="CSRF token missing or invalid — reload the page and try again.")
    return None


# --- transport/browser: response headers ------------------------------------

# Scripts run from this origin, or inline with this response's nonce (system
# map #19): the React shell's theme snippet and the last Jinja pages' small
# scripts carry it. The 'unsafe-inline' below is replaced by the nonce in
# _csp(); only the self-contained system map page (Settings → System map)
# keeps it. Styles keep 'unsafe-inline' (React style attributes). No
# third-party scripts, no framing, no plugins, and forms post back to this
# origin only.
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "   # fonts are served by Odin (static/fonts)
    "img-src 'self' data:; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    # blob: frames are PDFs this app renders in the page (the document template preview)
    "frame-src 'self' blob:"
)


def csp_nonce():
    """This response's script nonce (made on first use)."""
    from flask import g
    if "csp_nonce" not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


def _csp():
    """The policy above with this response's nonce instead of 'unsafe-inline'."""
    from flask import g
    return CSP.replace("script-src 'self' 'unsafe-inline'; ", "script-src 'self'%s; " % (f" 'nonce-{g.csp_nonce}'" if "csp_nonce" in g else ""))


def _security_headers(response):
    response.headers.setdefault("Content-Security-Policy", _csp())
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")          # legacy clickjacking guard
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
    )
    # JSON, PDF and CSV carry account data; PDF and CSV are on Cloudflare's
    # default cache list (review P3-11). Pictures and the app's files keep their own.
    if response.mimetype in ("application/json", "application/pdf", "text/csv"):
        response.headers["Cache-Control"] = "private, no-store"
    # Only meaningful over TLS; harmless otherwise, and correct once nginx
    # terminates HTTPS in front of the app.
    if request.is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    if response.status_code == 429:   # every throttle's reply says when to come back; a route may name its own wait
        response.headers.setdefault("Retry-After", "60")
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

        # x_host=0: the host comes from the Host header nginx passes on, never
        # from a client-supplied X-Forwarded-Host (links in mail are built from it
        # when no public address is set).
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0)

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,   # JS cannot read the session cookie
        SESSION_COOKIE_SAMESITE="Lax",  # blocks cross-site POST cookie attachment
        # Set PMS_HTTPS=1 in production (behind TLS) so the cookie is never
        # sent over plaintext. Left off by default so local HTTP dev works.
        SESSION_COOKIE_SECURE=os.environ.get("PMS_HTTPS") == "1",
        # Idle cap: set from policy on every request (core._auth_gate); the
        # absolute cap is checked there too, since Flask only refreshes this one.
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),
        MAX_CONTENT_LENGTH=(UPLOAD_CEILING_MB + 1) * 1024 * 1024,  # +1 MB for the multipart framing (a file of exactly the ceiling was refused); the per-file policy is checked by upload_problem
    )
    app.before_request(_validate_csrf)
    app.after_request(_security_headers)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["csp_nonce"] = csp_nonce
    return app
