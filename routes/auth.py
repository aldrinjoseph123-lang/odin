"""Authentication + self-service account routes: login, logout, root redirect,
password change, email update. Imported for route registration side effects.
"""
from datetime import datetime

from markupsafe import escape
from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core import app, login_required
from db import get_db
from security import (
    LOGIN_WINDOW_MINUTES,
    consume_login_link,
    issue_login_link,
    login_is_blocked,
    password_problem,
    rate_limited,
    record_login_attempt,
    valid_email,
)
from services.audit import audit_log
from spa import spa_index, spa_serves


def attempt_login(username, password):
    """The one login path, shared by the HTML form and /api/login.

    Lockout, deactivation, session setup, last-login stamp and audit rows all
    happen here so the two front ends cannot drift. Returns (ok, message);
    message is the user-facing reason on failure and never reveals whether
    the account exists.
    """
    if login_is_blocked(username):
        return False, f"Too many failed attempts. Try again in {LOGIN_WINDOW_MINUTES} minutes."
    user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user and not user["active"]:
        record_login_attempt(username, success=False)
        audit_log("login_failure", "user", user["id"], username, "account deactivated", actor=username)
        return False, "This account has been deactivated"
    if user and user["kind"] == "external":
        # External accounts have no password. Same message as a bad password
        # so the form never confirms an address exists; the trail says why.
        record_login_attempt(username, success=False)
        audit_log("login_failure", "user", user["id"], username, "external account: sign-in links only", actor=username)
        return False, "Bad username or password"
    if not (user and check_password_hash(user["password_hash"], password)):
        record_login_attempt(username, success=False)
        # Failed attempts are evidence too — login_attempts is purged after
        # a week, the audit trail is not.
        audit_log("login_failure", "user", user["id"] if user else None, username, actor=username)
        return False, "Bad username or password"
    record_login_attempt(username, success=True)
    start_session(user)
    audit_log("login_success", "user", user["id"], username, actor=username)
    return True, None


def start_session(user):
    """A fresh session for an authenticated user — shared by password and
    link sign-in. session.clear() first: a new id on privilege change defeats
    session fixation, discarding anything planted before login."""
    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["role"] = user["role"]
    session["kind"] = user["kind"]
    session["dismissed_alerts"] = {}  # fresh login = every real alert shows again
    session["must_change_password"] = bool(user["must_change_password"])
    session["login_at"] = datetime.utcnow().isoformat()
    session["epoch"] = user["session_epoch"]
    session.permanent = True  # opt into the idle cap; the absolute cap is checked per request
    get_db().execute("UPDATE users SET last_login_at = ? WHERE id = ?", (session["login_at"], user["id"]))
    get_db().commit()


def send_login_link(user, raw_token, invited_by=None, project_name=None):
    """Email the link; returns (ok, error). Never raises."""
    import graph
    link = url_for("auth_link_consume", token=raw_token, _external=True)
    # Names come from the users table and the project form: escape them, this
    # is HTML going into a mail client.
    intro = (f"{escape(invited_by)} added you to the project <b>{escape(project_name)}</b> in Odin." if project_name
             else "Here is your Odin sign-in link.")
    html = (f"<p>{intro}</p><p><a href=\"{link}\">Sign in to Odin</a></p>"
            f"<p>The link works once and expires in 30 minutes. If it has expired, request a new one from the sign-in page.</p>")
    try:
        return graph.send_mail(user["email"], "Your Odin sign-in link", html)
    except Exception as exc:  # network / token errors must not break the invite
        return False, str(exc)


@app.route("/auth/link", methods=["GET", "POST"])
def auth_link_request():
    """External accounts ask for a sign-in link here. The reply is the same
    whether or not the address is known — no enumeration — and requests are
    rate limited per address and IP."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not valid_email(email):
            flash("Enter the email address you were invited with")
        elif rate_limited(f"link:{email}", 3, 15):
            flash("Too many requests for that address — wait a few minutes and try again")
        else:
            user = get_db().execute(
                "SELECT * FROM users WHERE lower(email) = ? AND kind = 'external' AND active = 1", (email,)
            ).fetchone()
            if user:
                send_login_link(user, issue_login_link(user["id"]))
            audit_log("login_link_requested", "user", user["id"] if user else None, email, actor=email)
            flash("If that address is on a project, a sign-in link is on its way")
        return redirect(url_for("auth_link_request"))
    return render_template("auth_link.html")


@app.route("/auth/link/<token>")
def auth_link_consume(token):
    user = consume_login_link(token)
    if user is None:
        audit_log("login_link_rejected", details="invalid, expired, used, or account inactive", actor="link")
        flash("That sign-in link is invalid or has expired — request a new one")
        return redirect(url_for("auth_link_request"))
    start_session(user)
    audit_log("login_success", "user", user["id"], user["username"], "sign-in link", actor=user["username"])
    return redirect(url_for("board"))


def safe_next_url():
    """Only relative redirects — an absolute ?next= would be an open redirect
    straight off the login page."""
    next_url = request.args.get("next", "")
    return next_url if next_url.startswith("/") and not next_url.startswith("//") else None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ok, message = attempt_login(request.form["username"].strip(), request.form["password"])
        if ok:
            return redirect(safe_next_url() or url_for("board"))
        flash(message)
        return render_template("login.html")
    if spa_serves("login"):
        return spa_index()
    return render_template("login.html")


@app.route("/healthz")
def healthz():
    """Liveness for Docker and the Cloudflare health monitor: proves the
    process is up and the database answers. No auth, no data."""
    get_db().execute("SELECT 1")
    return "ok", 200, {"Content-Type": "text/plain", "Cache-Control": "no-store"}


@app.route("/robots.txt")
def robots():
    """Nothing here is for search engines — least of all a guest link that
    leaked into a crawl."""
    return "User-agent: *\nDisallow: /\n", 200, {"Content-Type": "text/plain"}


@app.route("/logout")
def logout():
    if "user_id" in session:
        audit_log("logout", "user", session["user_id"], session.get("user_name"))
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return redirect(url_for("board"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "GET" and spa_serves("account"):
        return spa_index()
    if request.method == "POST":
        current = request.form["current_password"]
        new_password = request.form["new_password"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        problem = password_problem(new_password)
        if user["kind"] == "external":
            flash("External accounts sign in by email link and have no password")
        elif not check_password_hash(user["password_hash"], current):
            flash("Current password is wrong")
        elif problem:
            flash(problem)
        else:
            db.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                (generate_password_hash(new_password, method="pbkdf2:sha256"), session["user_id"]),
            )
            db.commit()
            session["must_change_password"] = False
            audit_log("change_own_password", "user", session["user_id"], session.get("user_name"))
            flash("Password updated")
        return redirect(url_for("account"))
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return render_template("account.html", user=user)


@app.route("/account/email", methods=["POST"])
@login_required
def account_email():
    email = request.form.get("email", "").strip()
    if email and not valid_email(email):
        flash("Enter a valid email address")
        return redirect(url_for("account"))
    db = get_db()
    db.execute("UPDATE users SET email = ? WHERE id = ?", (email or None, session["user_id"]))
    db.commit()
    audit_log("change_own_email", "user", session["user_id"], session.get("user_name"))
    flash("Email updated")
    return redirect(url_for("account"))
