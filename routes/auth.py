"""Authentication + self-service account routes: login, logout, root redirect,
password change, email update. Imported for route registration side effects.
"""
from datetime import datetime

from markupsafe import escape
import os
import secrets as _secrets

from flask import abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core import app, login_required
from constants import ACCENTS, AVATAR_EXTENSIONS, AVATAR_MAX_BYTES, NOTIFICATION_KINDS, THEMES
from db import AVATAR_DIR, get_db
from security import (
    consume_login_link,
    reset_link_row,
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
        from policies import policy
        return False, f"Too many failed attempts. Try again in {policy('login_window_minutes')} minutes."
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
    # A Microsoft-created account has no password hash at all ("microsoft:no-password").
    if not (user and "$" in user["password_hash"] and check_password_hash(user["password_hash"], password)):
        record_login_attempt(username, success=False)
        # Failed attempts are evidence too — login_attempts is purged after
        # a week, the audit trail is not.
        audit_log("login_failure", "user", user["id"] if user else None, username, actor=username)
        return False, "Bad username or password"
    from routes.sso import sso_enforced
    if sso_enforced() and not user["password_login"]:
        # Staff use Microsoft; only accounts an admin flagged keep a password.
        record_login_attempt(username, success=False)
        audit_log("login_failure", "user", user["id"], username, "password sign-in not allowed: Microsoft only", actor=username)
        return False, "Staff sign in with Microsoft — use the Microsoft button"
    record_login_attempt(username, success=True)
    start_session(user)
    if sso_enforced():
        # The emergency way in: always on the record, and the admins hear of it.
        from services.notifications import notify_users
        audit_log("break_glass_login", "user", user["id"], username, f"password sign-in while Microsoft is required, from {request.remote_addr}", actor=username)
        admins = [r["id"] for r in get_db().execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
        notify_users(admins, "access", None, f"{escape(user['name'])} signed in with a password",
                     f"{escape(user['name'])} used the emergency password sign-in from {escape(request.remote_addr or 'an unknown address')}. If that wasn't expected, deactivate the account on the Users page.",
                     link="/audit-logs")
    else:
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


def send_login_link(user, raw_token, invited_by=None, project_name=None, project_id=None):
    """Email the link; returns (ok, error). Never raises."""
    import graph
    from core import external_url
    from policies import policy
    link = external_url("auth_link_consume", token=raw_token,
                        **({"next": url_for("project_detail", project_id=project_id)} if project_id else {}))
    # Names come from the users table and the project form: escape them, this
    # is HTML going into a mail client.
    intro = (f"{escape(invited_by)} added you to the project <b>{escape(project_name)}</b> in Odin." if project_name
             else "Here is your Odin sign-in link.")
    html = (f"<p>{intro}</p><p><a href=\"{link}\">Sign in to Odin</a></p>"
            f"<p>The link works once and expires in {policy('link_minutes')} minutes. If it has expired, request a new one from the sign-in page.</p>")
    try:
        return graph.send_mail(user["email"], "Your Odin sign-in link", html)
    except Exception as exc:  # network / token errors must not break the invite
        return False, str(exc)


def _mail_off():
    """Mail is not connected: say so honestly instead of promising a link (the
    reply is the same for every address, so nothing is revealed)."""
    from db import get_setting
    return get_setting("notify_email_enabled") != "1"


@app.route("/auth/link", methods=["GET", "POST"])
def auth_link_request():
    """External accounts ask for a sign-in link here. The reply is the same
    whether or not the address is known — no enumeration — and requests are
    rate limited per address and IP."""
    if session.get("user_id") and request.method == "GET":
        return redirect(home_url())     # already in; a stale link just lands them home
    if request.method == "GET" and spa_serves("auth_link_request"):
        return spa_index()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not valid_email(email):
            flash("Enter the email address you were invited with")
        elif _mail_off():
            flash("This workspace does not send email yet — ask your project manager for a sign-in link")
        elif rate_limited(f"link:{email}", 3, 15):
            flash("Too many requests for that address — wait a few minutes and try again")
        else:
            from policies import email_domain_allowed
            user = get_db().execute(
                "SELECT * FROM users WHERE lower(email) = ? AND kind = 'external' AND active = 1", (email,)
            ).fetchone()
            if user and email_domain_allowed(email):
                send_login_link(user, issue_login_link(user["id"]))
            audit_log("login_link_requested", "user", user["id"] if user else None, email, actor=email)
            flash("If that address is on a project, a sign-in link is on its way")
        return redirect(url_for("auth_link_request"))
    return render_template("auth_link.html")


@app.route("/auth/reset", methods=["GET", "POST"])
def auth_reset_request():
    """Staff who forgot their password ask for a reset link. The reply is the
    same whether or not the address is known, and requests are limited per
    address. Partner accounts have no password: they use the sign-in link."""
    if request.method == "GET":
        return spa_index() if spa_serves("auth_reset_request") else redirect(url_for("login"))
    email = request.form.get("email", "").strip().lower()
    if not valid_email(email):
        flash("Enter the email address on your account")
    elif _mail_off():
        flash("This workspace does not send email yet — ask an admin to reset your password")
    elif rate_limited(f"reset:{email}", 3, 15):
        flash("Too many requests for that address — wait a few minutes and try again")
    else:
        from routes.sso import sso_enforced
        user = get_db().execute(
            "SELECT * FROM users WHERE lower(email) = ? AND kind = 'internal' AND active = 1", (email,)
        ).fetchone()
        if user and sso_enforced() and not user["password_login"]:
            user = None   # no password to reset: they sign in with Microsoft (the reply stays neutral)
        if user:
            import graph
            raw = issue_login_link(user["id"], purpose="reset")
            from core import external_url
            from policies import policy
            link = external_url("auth_reset_form", token=raw)
            html = (f"<p>Someone asked to reset the password for <b>{escape(user['username'])}</b> in Odin.</p>"
                    f'<p><a href="{link}">Choose a new password</a></p>'
                    f"<p>The link works once and expires in {policy('link_minutes')} minutes. If this was not you, ignore this mail: nothing changes.</p>")
            try:
                graph.send_mail(user["email"], "Reset your Odin password", html)
            except Exception as exc:   # delivery failure must not reveal anything
                print(f"[auth_reset_request] mail failed: {exc}")
        audit_log("password_reset_requested", "user", user["id"] if user else None, email, actor=email)
        flash("If that address belongs to an account, a reset link is on its way")
    return redirect(url_for("auth_reset_request"))


@app.route("/auth/reset/<token>", methods=["GET", "POST"])
def auth_reset_form(token):
    """Set a new password from a reset link. The link stays usable until a
    password is actually accepted, then dies; every existing session of the
    account ends, as after an admin reset."""
    if request.method == "GET":
        return spa_index() if spa_serves("auth_reset_form") else redirect(url_for("login"))
    row = reset_link_row(token)
    if row is None:
        audit_log("password_reset_rejected", details="invalid, expired, used or wrong kind of link", actor="link")
        flash("That reset link is invalid or has expired — request a new one")
        return redirect(url_for("auth_reset_request"))
    new_password = request.form.get("new_password", "")
    problem = password_problem(new_password)
    if problem:
        flash(problem)
        return redirect(url_for("auth_reset_form", token=token))
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0, session_epoch = session_epoch + 1 WHERE id = ?",
        (generate_password_hash(new_password, method="pbkdf2:sha256"), row["user_id"]),
    )
    db.execute("UPDATE login_links SET used_at = ? WHERE id = ?", (now, row["id"]))
    db.commit()
    user = db.execute("SELECT username FROM users WHERE id = ?", (row["user_id"],)).fetchone()
    audit_log("password_reset_by_link", "user", row["user_id"], user["username"], actor=user["username"])
    flash("Password changed — sign in with the new one")
    return redirect(url_for("login"))


@app.route("/auth/link/<token>", methods=["GET", "POST"])
def auth_link_consume(token):
    """GET only shows a "Continue to Odin" button: mail security scanners open
    links, and a GET that signed in would burn the one-time link before the
    person ever clicked it. The button's POST is what signs in."""
    if request.method == "GET":
        if spa_serves("auth_link_consume"):
            return spa_index()
        from flask import render_template_string
        return render_template_string(
            '<!doctype html><title>Sign in · Odin</title><form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}">'
            '<button type="submit">Continue to Odin</button></form>')
    user = consume_login_link(token)
    if user is None:
        audit_log("login_link_rejected", details="invalid, expired, used, or account inactive", actor="link")
        flash("That sign-in link is invalid or has expired — request a new one")
        return redirect(url_for("auth_link_request", expired=1))   # the React page reads ?expired
    start_session(user)
    audit_log("login_success", "user", user["id"], user["username"], "sign-in link", actor=user["username"])
    # a link minted for a notification lands on the project it was about
    return redirect(safe_next_url() or home_url())


def safe_next_url():
    """Only relative redirects — an absolute ?next= would be an open redirect
    straight off the login page."""
    next_url = request.args.get("next", "")
    return next_url if is_local_path(next_url) else None


def is_local_path(url):
    """A path on this site: one leading slash, then no second slash or backslash
    (browsers read "/\\evil.com" as "//evil.com"), no scheme or host, no control
    characters (a tab or newline inside "/\t/evil.com" is dropped by browsers)."""
    from urllib.parse import urlsplit
    if not url.startswith("/") or url[1:2] in ("/", "\\") or "\\" in url or any(ord(ch) < 32 or ord(ch) == 127 for ch in url):
        return False
    parts = urlsplit(url)
    return not parts.scheme and not parts.netloc


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ok, message = attempt_login(request.form["username"].strip(), request.form["password"])
        if ok:
            return redirect(safe_next_url() or home_url())
        flash(message)
        return render_template("login.html")
    if spa_serves("login"):
        return spa_index()
    return render_template("login.html")


@app.route("/login/password")
def login_password():
    """The emergency password form, for accounts an admin flagged, once staff
    must use Microsoft. Same POST as /login; this address just shows the form."""
    if spa_serves("login_password"):
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


HOME_PAGES = {"dashboard": "dashboard", "board": "board"}   # the user's choice -> endpoint


def home_url():
    """Where sign-in and the logo land: the dashboard, or the flow when the
    user chose it on their Account page. Partners always get the flow — the
    dashboard is a staff view."""
    if session.get("kind") == "external":
        return url_for("board")
    row = get_db().execute("SELECT home FROM users WHERE id = ?", (session["user_id"],)).fetchone() if session.get("user_id") else None
    return url_for(HOME_PAGES.get(row["home"] if row else "", "dashboard"))


@app.route("/")
@login_required
def index():
    return redirect(home_url())


@app.route("/account/home", methods=["POST"])
@login_required
def account_home():
    home = request.form.get("home", "")
    if home not in HOME_PAGES:
        flash("Pick a home page from the list")
        return redirect(url_for("account"))
    db = get_db()
    db.execute("UPDATE users SET home = ? WHERE id = ?", (home, session["user_id"]))
    db.commit()
    audit_log("change_own_home", "user", session["user_id"], session.get("user_name"), home)
    flash("Home page saved")
    return redirect(url_for("account"))


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
                "UPDATE users SET password_hash = ?, must_change_password = 0, session_epoch = session_epoch + 1 WHERE id = ?",
                (generate_password_hash(new_password, method="pbkdf2:sha256"), session["user_id"]),
            )
            db.commit()
            # every other device is signed out; this one carries on
            session["epoch"] = db.execute("SELECT session_epoch FROM users WHERE id = ?", (session["user_id"],)).fetchone()[0]
            session["must_change_password"] = False
            audit_log("change_own_password", "user", session["user_id"], session.get("user_name"))
            flash("Password updated")
        return redirect(url_for("account"))
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return render_template("account.html", user=user)


@app.route("/account/name", methods=["POST"])
@login_required
def account_name():
    """The name others see. Past notes keep the name they were written
    under — they are a record, not a live label."""
    name = request.form.get("name", "").strip()[:80]
    if not name:
        flash("Enter your name")
        return redirect(url_for("account"))
    db = get_db()
    db.execute("UPDATE users SET name = ? WHERE id = ?", (name, session["user_id"]))
    db.commit()
    audit_log("change_own_name", "user", session["user_id"], session.get("user_name"), f"-> {name}")
    session["user_name"] = name
    flash("Name updated")
    return redirect(url_for("account"))


@app.route("/account/sign-out-others", methods=["POST"])
@login_required
def account_sign_out_others():
    """End every other session this account has (a lost laptop, a shared
    machine). Same mechanism as an admin deactivation: bump the epoch, then
    carry this session over to the new one."""
    db = get_db()
    db.execute("UPDATE users SET session_epoch = session_epoch + 1 WHERE id = ?", (session["user_id"],))
    db.commit()
    session["epoch"] = db.execute("SELECT session_epoch FROM users WHERE id = ?", (session["user_id"],)).fetchone()[0]
    audit_log("sign_out_other_sessions", "user", session["user_id"], session.get("user_name"))
    flash("Signed out of every other device")
    return redirect(url_for("account"))


@app.route("/account/notifications", methods=["POST"])
@login_required
def account_notifications():
    """Which kinds this user wants by email. Ticked = on; the form sends only
    the ticked ones. In-app notifications always arrive."""
    off = [k for k in NOTIFICATION_KINDS if request.form.get(k) != "on" and (k != "access" or session.get("role") == "Admin")]
    db = get_db()
    db.execute("UPDATE users SET email_off = ? WHERE id = ?", (",".join(off), session["user_id"]))
    db.commit()
    audit_log("change_own_notification_prefs", "user", session["user_id"], session.get("user_name"), f"email off: {','.join(off) or 'none'}")
    flash("Notification settings saved")
    return redirect(url_for("account"))


@app.route("/account/appearance", methods=["POST"])
@login_required
def account_appearance():
    theme = request.form.get("theme", "")
    accent = request.form.get("accent", "")
    if theme not in THEMES or accent not in ACCENTS:
        flash("Pick a theme and an accent from the list")
        return redirect(url_for("account"))
    db = get_db()
    db.execute("UPDATE users SET theme = ?, accent = ? WHERE id = ?", (theme, accent, session["user_id"]))
    db.commit()
    audit_log("change_own_appearance", "user", session["user_id"], session.get("user_name"), f"{theme}/{accent}")
    flash("Appearance saved")
    return redirect(url_for("account"))


def _store_avatar(user_id, file):
    """Validate and store a picture; returns the new filename or an error.
    Extension allowlist, magic bytes and a 2 MB cap — an avatar is the one
    upload every signed-in user can make, so it gets the strictest check."""
    from security import content_matches_extension
    name = file.filename or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in AVATAR_EXTENSIONS:
        return None, "Use a PNG, JPG, GIF or WebP image"
    if not content_matches_extension(file):
        return None, "That file's contents don't match its extension"
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > AVATAR_MAX_BYTES:
        return None, "Keep the picture under 2 MB"
    os.makedirs(AVATAR_DIR, exist_ok=True)
    stored = f"{user_id}-{_secrets.token_urlsafe(6)}.{ext}"
    file.save(os.path.join(AVATAR_DIR, stored))
    db = get_db()
    old = db.execute("SELECT avatar FROM users WHERE id = ?", (user_id,)).fetchone()["avatar"]
    db.execute("UPDATE users SET avatar = ? WHERE id = ?", (stored, user_id))
    db.commit()
    if old:
        try:
            os.remove(os.path.join(AVATAR_DIR, old))
        except OSError:
            pass
    return stored, None


@app.route("/account/avatar", methods=["POST"])
@login_required
def account_avatar():
    file = request.files.get("avatar")
    if not file or not file.filename:
        flash("Choose a picture first")
        return redirect(url_for("account"))
    stored, error = _store_avatar(session["user_id"], file)
    if error:
        flash(error)
    else:
        audit_log("change_own_avatar", "user", session["user_id"], session.get("user_name"))
        flash("Picture updated")
    return redirect(url_for("account"))


@app.route("/account/avatar/remove", methods=["POST"])
@login_required
def account_avatar_remove():
    db = get_db()
    old = db.execute("SELECT avatar FROM users WHERE id = ?", (session["user_id"],)).fetchone()["avatar"]
    db.execute("UPDATE users SET avatar = NULL WHERE id = ?", (session["user_id"],))
    db.commit()
    if old:
        try:
            os.remove(os.path.join(AVATAR_DIR, old))
        except OSError:
            pass
    audit_log("remove_own_avatar", "user", session["user_id"], session.get("user_name"))
    flash("Picture removed")
    return redirect(url_for("account"))


@app.route("/users/<int:user_id>/avatar/<path:stored>")
@login_required
def user_avatar(user_id, stored):
    """Anyone signed in may see anyone's picture (it appears wherever their
    name does); the stored name must match the record, so an old URL dies
    when the picture is replaced. Served inline, cached hard: the URL is
    unique per upload."""
    row = get_db().execute("SELECT avatar FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or not row["avatar"] or row["avatar"] != stored:
        abort(404)
    response = send_from_directory(AVATAR_DIR, stored, as_attachment=False, max_age=31536000)
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return response


@app.route("/account/email", methods=["POST"])
@login_required
def account_email():
    email = request.form.get("email", "").strip()
    if email and not valid_email(email):
        flash("Enter a valid email address")
        return redirect(url_for("account"))
    db = get_db()
    if session.get("kind") == "external":
        flash("Your email address is how you sign in; ask the project manager to change it")
        return redirect(url_for("account"))
    if email and db.execute("SELECT 1 FROM users WHERE lower(email) = ? AND id != ?", (email.lower(), session["user_id"])).fetchone():
        flash("That address belongs to another account")
        return redirect(url_for("account"))
    db.execute("UPDATE users SET email = ? WHERE id = ?", (email or None, session["user_id"]))
    db.commit()
    audit_log("change_own_email", "user", session["user_id"], session.get("user_name"))
    flash("Email updated")
    return redirect(url_for("account"))
