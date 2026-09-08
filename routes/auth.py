"""Authentication + self-service account routes: login, logout, root redirect,
password change, email update. Imported for route registration side effects.
"""
from datetime import datetime

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core import app, login_required
from db import get_db
from security import (
    LOGIN_WINDOW_MINUTES,
    login_is_blocked,
    password_problem,
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
    if not (user and check_password_hash(user["password_hash"], password)):
        record_login_attempt(username, success=False)
        # Failed attempts are evidence too — login_attempts is purged after
        # a week, the audit trail is not.
        audit_log("login_failure", "user", user["id"] if user else None, username, actor=username)
        return False, "Bad username or password"
    record_login_attempt(username, success=True)
    # New session id on privilege change defeats session fixation:
    # anything an attacker planted pre-login is discarded here.
    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["role"] = user["role"]
    session["dismissed_alerts"] = {}  # fresh login = every real alert shows again
    session["must_change_password"] = bool(user["must_change_password"])
    session["login_at"] = datetime.utcnow().isoformat()
    session["epoch"] = user["session_epoch"]
    session.permanent = True  # opt into the idle cap; the absolute cap is checked per request
    get_db().execute("UPDATE users SET last_login_at = ? WHERE id = ?", (session["login_at"], user["id"]))
    get_db().commit()
    audit_log("login_success", "user", user["id"], username, actor=username)
    return True, None


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
    if request.method == "POST":
        current = request.form["current_password"]
        new_password = request.form["new_password"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        problem = password_problem(new_password)
        if not check_password_hash(user["password_hash"], current):
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
