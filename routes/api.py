"""JSON API for the React front end. Same session cookie, same CSRF token
(sent as X-CSRF-Token), same decorators and audit trail as the HTML routes —
the API is a second door into the same rooms, not a second house.
"""
from flask import abort, jsonify, request, session

from core import app, login_required
from db import get_db
from routes.auth import attempt_login
from security import csrf_token
from services.audit import audit_log
from spa import spa_asset


def _permissions_for(role):
    return [
        row["permission"]
        for row in get_db().execute(
            "SELECT permission FROM role_permissions WHERE role = ? AND allowed = 1 ORDER BY permission", (role,)
        )
    ]


def _current_user():
    if "user_id" not in session:
        return None
    return {
        "id": session["user_id"],
        "name": session.get("user_name"),
        "role": session.get("role"),
        "must_change_password": bool(session.get("must_change_password")),
        "permissions": _permissions_for(session.get("role")),
    }


@app.route("/api/session")
def api_session():
    """Who am I, what may I do, and the CSRF token every mutation must carry.
    Anonymous callers get the token too — the login form needs it."""
    return jsonify({"csrf": csrf_token(), "user": _current_user()})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    ok, message = attempt_login((data.get("username") or "").strip(), data.get("password") or "")
    if not ok:
        # attempt_login audits every outcome; 429 when it is the lockout talking.
        return jsonify({"error": message}), (429 if message.startswith("Too many") else 401)
    # attempt_login cleared the session (fixation defence), so the token rotated.
    return jsonify({"user": _current_user(), "csrf": csrf_token()})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    if "user_id" in session:
        audit_log("logout", "user", session["user_id"], session.get("user_name"))
    session.clear()
    return jsonify({"ok": True, "csrf": csrf_token()})


@app.route("/assets/<path:filename>")
def spa_assets(filename):
    return spa_asset(filename)
