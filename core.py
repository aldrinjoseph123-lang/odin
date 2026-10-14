"""The Flask app object plus request-lifecycle glue shared by every route module.

Owns app creation/config, the connection teardown, the auth decorators, and the
template context processor. Imports only constants + db, so route modules can
`from core import app, login_required, ...` without an import cycle (core never
imports routes or app.py).
"""
import os
from functools import wraps

from flask import Flask, abort, flash, g, get_flashed_messages, jsonify, redirect, request, session, url_for
from markupsafe import Markup, escape
from werkzeug.routing import IntegerConverter

from datetime import datetime, timedelta

from constants import PERMISSIONS
from db import get_db, project_role_of
from security import csrf_token, init_security

DEV_SECRET = "dev-secret-change-me"

app = Flask(__name__)

MAX_ID = 2 ** 63 - 1   # SQLite's largest integer


class _BoundedInt(IntegerConverter):
    """<int:…> in every route, capped at MAX_ID: a longer number in a URL is
    a 404, not an OverflowError deep in a query."""
    def __init__(self, map, *args, **kwargs):
        kwargs.setdefault("max", MAX_ID)
        super().__init__(map, *args, **kwargs)


app.url_map.converters["int"] = _BoundedInt
app.secret_key = os.environ.get("SECRET_KEY", DEV_SECRET)
# wsgi.py refuses to boot on this flag — a predictable signing key lets anyone
# forge a session cookie, so production must supply a real SECRET_KEY.
app.config["USING_DEV_SECRET"] = app.secret_key == DEV_SECRET

# cookie hardening + CSRF + security response headers (see security.py)
init_security(app)


@app.before_request
def _idle_lifetime_from_policy():
    """The idle cap is admin policy; the signed cookie's max age follows it."""
    if request.endpoint in ("static", "spa_assets", "favicon"):
        return
    from policies import policy
    app.permanent_session_lifetime = timedelta(minutes=policy("session_idle_minutes"))


@app.template_filter("localdt")
def localdt(value, mode="datetime"):
    """Render a stored UTC timestamp as a <time> the browser localises.

    Everything in the database is `datetime.utcnow().isoformat()` — no zone
    marker — so the raw string reads as someone else's clock. The element
    carries a proper UTC `datetime` attribute for the script in base.html to
    rewrite; with JS off the original UTC text still shows, so nothing is lost.
    """
    if not value:
        return "—"
    iso = value if value.endswith("Z") else f"{value}Z"
    fallback = value[:10] if mode == "date" else value[:16].replace("T", " ")
    return Markup(
        f'<time class="localdt" data-mode="{mode}" datetime="{escape(iso)}" '
        f'title="{escape(fallback)} UTC">{escape(fallback)}</time>'
    )


def external_url(endpoint, **values):
    """An absolute link for email and for Microsoft's redirect: built from the
    public address in Settings › General when set, never from the Host
    header of whoever made the request (a forged Host would otherwise put an
    attacker's domain into a sign-in or reset link)."""
    from policies import policy
    base = policy("public_url")
    return f"{base}{url_for(endpoint, **values)}" if base else url_for(endpoint, _external=True, **values)


def undo_note():
    """The "(5 min window)" that follows an Undo button, from policy."""
    from policies import policy
    return f"({policy('undo_minutes')} min window)"


def offer_undo(endpoint, **values):
    """Offer an Undo on this reply: json_for_fetch hands the address to the
    React page, which POSTs there (CSRF-protected, never a GET a cross-site
    <img> could trigger)."""
    g.undo_url = url_for(endpoint, **values)


ERROR_COPY = {
    400: ("Bad request", "Odin could not read that request. Reload the page and try again."),
    403: ("No access", "Your account doesn't have permission for that."),
    404: ("Page not found", "The link may be old, or the item was deleted."),
    409: ("Conflict", "Someone changed this at the same moment. Reload and try again."),
    413: ("File too large", "Uploads are limited to {mb} MB per file."),
    429: ("Too many requests", "Slow down a little and try again in a minute."),
    500: ("Something went wrong", "The error has been logged. Try again, or tell an admin if it persists."),
}


def wants_json():
    """A fetch caller (the React pages, the API) rather than a browser page."""
    return request.path.startswith("/api/") or request.is_json or "application/json" in request.headers.get("Accept", "")


def _error_page(error):
    from flask import render_template
    code = getattr(error, "code", 500)
    title, hint = ERROR_COPY.get(code, ERROR_COPY[500])
    if code == 413:
        try:
            from policies import policy
            mb = policy("upload_max_mb")
        except Exception:   # the error page renders whatever else is broken
            from security import UPLOAD_CEILING_MB as mb
        hint = hint.format(mb=mb)
    # abort(400, description="…") carries words for the person; werkzeug's stock text does not
    said = getattr(error, "description", None)
    if code < 500 and said and said != type(error).description:
        hint = said
    if wants_json():
        body = {"error": hint}
        if g.get("csrf_failed"):
            body["csrf"] = csrf_token()   # the page retries once with the token this session holds
        return jsonify(body), code
    return render_template("error.html", code=code, title=title, hint=hint), code


for _code in ERROR_COPY:
    app.register_error_handler(_code, _error_page)


def json_body():
    """The request's JSON object: {} when there is none, a 400 when it is a
    list, string or number (every caller goes on to .get() from it)."""
    body = request.get_json(silent=True)
    if body is None:
        return {}
    if not isinstance(body, dict):
        abort(400, description="Send a JSON object")
    return body


def as_id(value):
    """A database id from a form field, query string or JSON value: a whole
    number 1..MAX_ID (ASCII digits only, never a bool or a float), else None."""
    if isinstance(value, str):
        value = value.strip()
        if not (value.isascii() and value.isdigit()):
            return None
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 < value <= MAX_ID else None


def text_field(value, limit, label, multiline=False):
    """A text value from a form or JSON body, stripped. Raises ValueError with
    the words to show for a non-string (a list or number is refused, never
    stored as its Python spelling), more than `limit` characters, a NUL, or a
    line break when `multiline` is off."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label}: send text")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{label}: at most {limit} characters")
    if "\x00" in value or (not multiline and ("\n" in value or "\r" in value)):
        raise ValueError(f"{label}: one line of plain text")
    return value


def parse_date(value):
    """'YYYY-MM-DD' for a date in that form (surrounding spaces ignored), None
    for empty; raises ValueError (the words to show after a label) for any
    other form or a year outside 2000-2100. Every stored date goes through
    here, so the pages that do arithmetic on dates can trust them."""
    import re
    from datetime import date
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("a date like 2026-10-31")
    value = value.strip()
    if not value:
        return None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("a date like 2026-10-31")
    try:
        d = date.fromisoformat(value)
    except ValueError:
        raise ValueError("a real calendar date, like 2026-10-31") from None
    if not 2000 <= d.year <= 2100:
        raise ValueError("a date between 2000 and 2100")
    return d.isoformat()


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Endpoints a user may still reach while a password change is pending.
# The React Account page reads /api/account and the header's bell reads
# /api/notifications: without them the forced-change screen never loads.
PASSWORD_CHANGE_ALLOWED = {"account", "account_email", "logout", "static", "api_account", "api_notifications", "api_logout", "api_activity"}
# Two-step sign-in required but not set up yet: the account page and its setup only.
MFA_SETUP_ALLOWED = PASSWORD_CHANGE_ALLOWED | {"api_two_step", "api_two_step_setup", "api_two_step_confirm"}


def _auth_gate():
    """Shared front half of every auth decorator: not logged in → login page;
    logged in with a forced password change pending → account page. Returns
    the redirect to send, or None to let the view run."""
    if "user_id" not in session:
        return _turned_away("Sign in to carry on", url_for("login", next=request.path), signed_out=True)
    if not _session_still_valid():
        session.clear()
        return _turned_away("Your session has ended — please sign in again", url_for("login", next=request.path), signed_out=True)
    if session.get("must_change_password") and request.endpoint not in PASSWORD_CHANGE_ALLOWED:
        return _turned_away("Set a new password before continuing", url_for("account"))
    if session.get("must_enroll_mfa") and request.endpoint not in MFA_SETUP_ALLOWED:
        return _turned_away("Set up two-step sign-in before continuing", url_for("account"))
    return None


def _turned_away(message, to, signed_out=False):
    """A page load is redirected (with the reason flashed); a fetch from the
    React app gets JSON it can act on. Following a redirect, fetch would
    read the sign-in page as a 200 and a lost save as a success."""
    if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
        reply = jsonify(error=message, signed_out=signed_out)
        reply.status_code = 401 if signed_out else 403
        if signed_out:
            reply.headers["X-Odin-Signed-Out"] = "1"   # the client reads it after the body is gone
        return reply
    if message != "Sign in to carry on":   # a plain visit to the sign-in page needs no banner
        flash(message)
    return redirect(to)


def _session_still_valid():
    """Absolute lifetime, plus a per-user epoch so deactivating an account or
    resetting its password ends every live session it has, not just the next
    login. One indexed primary-key lookup per request."""
    login_at = session.get("login_at")
    from policies import policy
    if not login_at or datetime.fromisoformat(login_at) < datetime.utcnow() - timedelta(hours=policy("session_max_hours")):
        return False
    row = get_db().execute(
        "SELECT active, session_epoch FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    if not (bool(row) and bool(row["active"]) and row["session_epoch"] == session.get("epoch", 0)):
        return False
    # signed out: this session (and any copy of its cookie) is over
    return not get_db().execute("SELECT 1 FROM revoked_sessions WHERE user_id = ? AND login_at = ?", (session["user_id"], login_at)).fetchone()


def end_session():
    """Sign out: record this session as ended, so a copied cookie stops working
    too, then clear it. Other sessions of the same person are untouched."""
    from services.audit import audit_log
    if "user_id" in session:
        audit_log("logout", "user", session["user_id"], session.get("user_name"))
        if session.get("login_at"):
            db = get_db()
            now = datetime.utcnow()
            db.execute("INSERT OR IGNORE INTO revoked_sessions (user_id, login_at, revoked_at) VALUES (?, ?, ?)",
                       (session["user_id"], session["login_at"], now.isoformat()))
            db.execute("DELETE FROM revoked_sessions WHERE revoked_at < ?", ((now - timedelta(days=8)).isoformat(),))   # past any session's life
            db.commit()
    session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        gate = _auth_gate()
        if gate:
            return gate
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        gate = _auth_gate()
        if gate:
            return gate
        if session.get("role") != "Admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def role_has_permission(role, permission):
    db = get_db()
    row = db.execute(
        "SELECT allowed FROM role_permissions WHERE permission = ? AND role = ?", (permission, role)
    ).fetchone()
    if row is None:
        return False
    return bool(row["allowed"])


def permission_required(permission):
    """Check if user has a specific permission."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            gate = _auth_gate()
            if gate:
                return gate
            if permission not in PERMISSIONS:
                abort(500)
            user_role = session.get("role", "Viewer")
            if not role_has_permission(user_role, permission):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.after_request
def json_for_fetch(response):
    """The React pages post to the same form routes the Jinja pages do. A
    form route answers with a flash and a redirect; when the caller asked
    for JSON, hand back the flashes as JSON instead so the page can show
    them and refetch. The login redirect is left alone so the client sees
    it for what it is. Nothing about the route changes: same permission,
    same audit row, same validation."""
    if (request.method == "POST" and request.headers.get("Accept") == "application/json"
            and 300 <= response.status_code < 400
            # the auth gate's redirect (always ?next=) stays a redirect, so the
            # client can tell "signed out"; a route that finishes on the
            # sign-in page (a password reset) is an ordinary reply
            and "/login?next=" not in (response.headers.get("Location") or "")):
        messages, errors = [], []
        for category, m in get_flashed_messages(with_categories=True):
            messages.append(str(m))
            if category == "error":
                errors.append(messages[-1])
        if errors:   # a refused form (flash(…, "error")): the page shows it as a failure, not a success
            refused = jsonify(ok=False, error=errors[0], messages=messages)
            refused.status_code = 400   # an after_request hook returns a response, not a (body, code) tuple
            return refused
        return jsonify(ok=True, messages=messages, undo=g.get("undo_url"), location=response.headers.get("Location"))
    return response


def sees_po(project_id):
    """The client's PO is ours and the customer's: staff, and the project's
    Customer contact. Partners and contractors never see it."""
    return session.get("kind") != "external" or project_role_of(project_id, session["user_id"]) == "Customer"


def like_any(text):
    """A LIKE pattern that finds `text` anywhere, with % and _ matching
    themselves (the SQL says ESCAPE '\\')."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def project_allows(project_id, action):
    """May this session do `action` on this project? Global permission first,
    then the project role (Admins skip the role check). One function for the
    routes, the API flags and the templates."""
    from constants import PROJECT_ACTIONS
    permission, roles = PROJECT_ACTIONS[action]
    role = session.get("role", "Viewer")
    if not role_has_permission(role, permission):
        return False
    return role == "Admin" or project_role_of(project_id, session["user_id"]) in roles


def project_role_required(action):
    """Stacks under permission_required on project-scoped mutations."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            gate = _auth_gate()
            if gate:
                return gate
            if not project_allows(kwargs["project_id"], action):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def project_scope():
    """SQL that narrows any `projects p` query to what this session may see:
    nothing extra for staff, only participated projects for an external
    account. Every list/export/board query appends it; load_project applies
    the same rule for single rows."""
    if session.get("kind") != "external":
        return "", []
    return " AND p.id IN (SELECT project_id FROM project_participants WHERE user_id = ?)", [session["user_id"]]


def nav_counts():
    """Badges on the nav bar — the same three numbers whether Jinja or React
    draws the bar."""
    if not session.get("user_id"):
        return {"active_alert_count": 0, "my_open_task_count": 0, "unread_notifications": 0, "projects_nav_url": url_for("projects_list")}
    db = get_db()
    scope_sql, scope_params = project_scope()
    from db import PROJECT_OPEN_SQL
    from services.notifications import visible_clause
    _bell = visible_clause(session.get("user_id"), session.get("kind"))
    return {
        # alerts are internal (the alert list is staff only): an outsider's badge stays empty;
        # staff count the same rows as the Alerts page and My work: live, open projects only
        "active_alert_count": 0 if session.get("kind") == "external" else db.execute(
            f"SELECT COUNT(*) AS count FROM alerts a JOIN projects p ON p.id = a.project_id WHERE a.resolved = 0 AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql}",
            scope_params,
        ).fetchone()["count"],
        "unread_notifications": db.execute(
            "SELECT COUNT(*) FROM notifications n WHERE n.user_id = ? AND n.read_at IS NULL" + _bell[0], (session.get("user_id"), *_bell[1])
        ).fetchone()[0],
        "my_open_task_count": db.execute(
            "SELECT COUNT(*) AS count FROM tasks t JOIN projects p ON p.id = t.project_id "
            f"WHERE t.assignee_id = ? AND t.done = 0 AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql}",
            (session.get("user_id"), *scope_params),
        ).fetchone()["count"],
        # Nav link back into the project list restores the last filter/sort the
        # user had applied, rather than dumping them on an unfiltered list.
        "projects_nav_url": url_for("projects_list", **session.get("projects_query", {})),
    }


@app.context_processor
def inject_globals():
    # the error page offers "Back to the flow" to someone signed in
    return {"current_user": session.get("user_name")}
