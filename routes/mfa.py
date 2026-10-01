"""Two-step sign-in (services/mfa.py): the code after the password, setting
it up and turning it off on the Account page, and an admin's reset for
someone who lost their phone and their recovery codes."""
from datetime import datetime, timedelta

from flask import abort, flash, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash

from core import app, login_required, permission_required
from db import get_db
from routes.auth import finish_login
from security import csrf_token, login_is_blocked, record_login_attempt
from services import mfa
from services.audit import audit_log


def _me():
    return get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()


@app.route("/api/login/code", methods=["POST"])
def api_login_code():
    """The second step: the password was right a moment ago (session mfa_user)."""
    from routes.api import _current_user
    uid, at = session.get("mfa_user"), session.get("mfa_at")
    if not uid or not at or datetime.fromisoformat(at) < datetime.utcnow() - timedelta(minutes=mfa.PENDING_MINUTES):
        session.clear()
        return jsonify(error="That took too long — sign in again"), 410   # 410/429: back to the password
    user = get_db().execute("SELECT * FROM users WHERE id = ? AND active = 1", (uid,)).fetchone()
    if user is None or login_is_blocked(user["username"]):
        session.clear()
        return jsonify(error="Too many failed attempts. Sign in again later."), 429
    how = mfa.check(user, (request.get_json(silent=True) or {}).get("code"))
    if how is None:
        record_login_attempt(user["username"], success=False)
        audit_log("login_failure", "user", user["id"], user["username"], "wrong two-step code", actor=user["username"])
        session["mfa_tries"] = session.get("mfa_tries", 0) + 1
        if session["mfa_tries"] >= mfa.PENDING_TRIES:
            session.clear()
            return jsonify(error="Too many wrong codes — sign in again"), 410
        return jsonify(error="That code is not right. Codes change every 30 seconds; check the time on your phone."), 401
    finish_login(user, "two-step: recovery code" if how == "recovery" else "two-step: authenticator code")
    if how == "recovery" and mfa.recovery_left(get_db().execute("SELECT recovery_codes FROM users WHERE id = ?", (uid,)).fetchone()) <= 2:
        flash("You are running out of recovery codes: make new ones on your Account page")
    return jsonify({"user": _current_user(), "csrf": csrf_token()})


@app.route("/api/account/two-step")
@login_required
def api_two_step():
    u = _me()
    return jsonify(enabled=mfa.enabled(u), enabled_at=u["totp_enabled_at"], required=mfa.required(u),
                   recovery_left=mfa.recovery_left(u) if mfa.enabled(u) else 0, password=bool(u["password_hash"] and "$" in u["password_hash"]))


@app.route("/api/account/two-step/setup", methods=["POST"])
@login_required
def api_two_step_setup():
    if session.get("kind") == "external":
        abort(403)
    u = _me()
    # someone holding only the session must not be able to bind their own authenticator
    if not (u["password_hash"] and "$" in u["password_hash"] and check_password_hash(u["password_hash"], (request.get_json(silent=True) or {}).get("password") or "")):
        return jsonify(error="Your password is not right"), 400
    audit_log("mfa_setup_started", "user", session["user_id"], session.get("user_name"))
    return jsonify(mfa.start_setup(session["user_id"]))


@app.route("/api/account/two-step/confirm", methods=["POST"])
@login_required
def api_two_step_confirm():
    codes = mfa.confirm_setup(session["user_id"], (request.get_json(silent=True) or {}).get("code"))
    if codes is None:
        return jsonify(error="That code is not right. Scan the code again, or check the time on your phone."), 400
    session["must_enroll_mfa"] = False
    audit_log("mfa_enable", "user", session["user_id"], session.get("user_name"))
    return jsonify(ok=True, recovery_codes=codes)


def _proof(u, body):
    """Password and a current code: what turning off or new codes need."""
    if not (u["password_hash"] and "$" in u["password_hash"] and check_password_hash(u["password_hash"], body.get("password") or "")):
        return "Your password is not right"
    if mfa.check(u, body.get("code")) is None:
        return "That code is not right"
    return None


@app.route("/api/account/two-step/off", methods=["POST"])
@login_required
def api_two_step_off():
    u, body = _me(), request.get_json(silent=True) or {}
    if mfa.required(u):
        return jsonify(error="Two-step sign-in is required for your account"), 400
    problem = _proof(u, body)
    if problem:
        audit_log("mfa_disable_refused", "user", u["id"], u["username"], problem)
        return jsonify(error=problem), 400
    mfa.turn_off(u["id"])
    audit_log("mfa_disable", "user", u["id"], u["username"])
    return jsonify(ok=True)


@app.route("/api/account/two-step/recovery-codes", methods=["POST"])
@login_required
def api_two_step_codes():
    u, body = _me(), request.get_json(silent=True) or {}
    if not mfa.enabled(u):
        abort(400)
    problem = _proof(u, body)
    if problem:
        return jsonify(error=problem), 400
    audit_log("mfa_recovery_codes", "user", u["id"], u["username"], "new set; the old ones stop working")
    return jsonify(ok=True, recovery_codes=mfa.regenerate_codes(u["id"]))


@app.route("/users/<int:user_id>/two-step-reset", methods=["POST"])
@permission_required("manage_users")
def user_two_step_reset(user_id):
    """Lost phone and recovery codes: an admin clears it; the person sets it up again."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ? AND kind = 'internal'", (user_id,)).fetchone()
    if user is None:
        abort(404)
    mfa.turn_off(user_id)
    # their live sessions end too: whoever holds the phone should not stay in
    db.execute("UPDATE users SET session_epoch = session_epoch + 1 WHERE id = ?", (user_id,))
    db.commit()
    audit_log("mfa_reset", "user", user_id, user["username"], "by an admin")
    flash(f"Two-step sign-in reset for {user['name']}: they set it up again at their next sign-in" if mfa.required(user)
          else f"Two-step sign-in turned off for {user['name']}")
    return redirect(url_for("users"))
