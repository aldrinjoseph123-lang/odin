"""The Flask app object plus request-lifecycle glue shared by every route module.

Owns app creation/config, the connection teardown, the auth decorators, and the
template context processor. Imports only constants + db, so route modules can
`from core import app, login_required, ...` without an import cycle (core never
imports routes or app.py).
"""
import os
from functools import wraps

from flask import Flask, abort, flash, g, redirect, request, session, url_for
from markupsafe import Markup, escape

from datetime import datetime, timedelta

from constants import (
    DELIVERY_MODES,
    PERMISSIONS,
    VIA_OPTIONS,
)
from db import get_db, get_doc_category_names, get_stage_names, project_role_of
from security import ABSOLUTE_SESSION_HOURS, csrf_token, init_security

DEV_SECRET = "dev-secret-change-me"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", DEV_SECRET)
# wsgi.py refuses to boot on this flag — a predictable signing key lets anyone
# forge a session cookie, so production must supply a real SECRET_KEY.
app.config["USING_DEV_SECRET"] = app.secret_key == DEV_SECRET

# cookie hardening + CSRF + security response headers (see security.py)
init_security(app)


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


def undo_button(label, endpoint, **values):
    """Render an inline POST form styled as a link — used inside flash messages
    so 'undo' is a state-changing POST (CSRF-protected), not a bare GET link a
    cross-site <img> could trigger."""
    return Markup(
        f"<form method='post' action='{escape(url_for(endpoint, **values))}' style='display:inline'>"
        f"<input type='hidden' name='_csrf' value='{escape(csrf_token())}'>"
        f"<button type='submit' class='link-btn' style='font-weight:600'>{escape(label)}</button>"
        f"</form>"
    )


ERROR_COPY = {
    403: ("No access", "Your account doesn't have permission for that."),
    404: ("Page not found", "The link may be old, or the item was deleted."),
    413: ("File too large", "Uploads are limited to 25 MB per file."),
    429: ("Too many requests", "Slow down a little and try again in a minute."),
    500: ("Something went wrong", "The error has been logged. Try again, or tell an admin if it persists."),
}


def _error_page(error):
    from flask import render_template
    code = getattr(error, "code", 500)
    title, hint = ERROR_COPY.get(code, ERROR_COPY[500])
    return render_template("error.html", code=code, title=title, hint=hint), code


for _code in ERROR_COPY:
    app.register_error_handler(_code, _error_page)


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Endpoints a user may still reach while a password change is pending.
PASSWORD_CHANGE_ALLOWED = {"account", "account_email", "logout", "static"}


def _auth_gate():
    """Shared front half of every auth decorator: not logged in → login page;
    logged in with a forced password change pending → account page. Returns
    the redirect to send, or None to let the view run."""
    if "user_id" not in session:
        return redirect(url_for("login", next=request.path))
    if not _session_still_valid():
        session.clear()
        flash("Your session has ended — please sign in again")
        return redirect(url_for("login", next=request.path))
    if session.get("must_change_password") and request.endpoint not in PASSWORD_CHANGE_ALLOWED:
        flash("Set a new password before continuing")
        return redirect(url_for("account"))
    return None


def _session_still_valid():
    """Absolute lifetime, plus a per-user epoch so deactivating an account or
    resetting its password ends every live session it has, not just the next
    login. One indexed primary-key lookup per request."""
    login_at = session.get("login_at")
    if not login_at or datetime.fromisoformat(login_at) < datetime.utcnow() - timedelta(hours=ABSOLUTE_SESSION_HOURS):
        return False
    row = get_db().execute(
        "SELECT active, session_epoch FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    return bool(row) and bool(row["active"]) and row["session_epoch"] == session.get("epoch", 0)


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


def write_required(view):
    """Blocks the Viewer (read-only) role from mutating routes."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        gate = _auth_gate()
        if gate:
            return gate
        if session.get("role") == "Viewer":
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
        return {"active_alert_count": 0, "my_open_task_count": 0, "projects_nav_url": url_for("projects_list")}
    db = get_db()
    scope_sql, scope_params = project_scope()
    return {
        "active_alert_count": db.execute(
            f"SELECT COUNT(*) AS count FROM alerts a JOIN projects p ON p.id = a.project_id WHERE a.resolved = 0{scope_sql}",
            scope_params,
        ).fetchone()["count"],
        "my_open_task_count": db.execute(
            "SELECT COUNT(*) AS count FROM tasks t JOIN projects p ON p.id = t.project_id "
            f"WHERE t.assignee_id = ? AND t.done = 0 AND p.deleted_at IS NULL{scope_sql}",
            (session.get("user_id"), *scope_params),
        ).fetchone()["count"],
        # Nav link back into the project list restores the last filter/sort the
        # user had applied, rather than dumping them on an unfiltered list.
        "projects_nav_url": url_for("projects_list", **session.get("projects_query", {})),
    }


@app.context_processor
def inject_globals():
    return {
        **nav_counts(),
        "STAGES": get_stage_names(),
        "DOC_CATEGORIES": get_doc_category_names(),
        "DELIVERY_MODES": DELIVERY_MODES,
        "VIA_OPTIONS": VIA_OPTIONS,
        "current_user": session.get("user_name"),
        "is_admin": session.get("role") == "Admin",
        # is_viewer = "hide every edit control": Viewers, and external
        # partners, who only read and comment. The routes enforce the same.
        "is_viewer": session.get("role") == "Viewer" or session.get("kind") == "external",
        "is_external": session.get("kind") == "external",
        "can_note": role_has_permission(session.get("role"), "add_project_note"),
        "session_user_id": session.get("user_id"),
    }
