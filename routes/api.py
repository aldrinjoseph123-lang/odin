"""JSON API for the React front end. Same session cookie, same CSRF token
(sent as X-CSRF-Token), same decorators and audit trail as the HTML routes —
the API is a second door into the same rooms, not a second house.
"""
from flask import abort, jsonify, request, session

from constants import ALERT_TYPE_TITLES, DELIVERY_MODES
from core import app, login_required, nav_counts, permission_required, role_has_permission
from db import get_db, get_stage_names, get_terminal_stage
from routes.auth import attempt_login
from routes.board import BANNER_NAMES, COLUMN_CARDS, board_data, dismiss_alert
from routes.projects import change_stage
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
        "nav": nav_counts(),
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


def _card(p):
    return {
        "id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"],
        "owner_name": p["owner_name"], "delivery_mode": p["delivery_mode"],
        "task_total": p["task_total"], "task_done": p["task_done"], "updated_at": p["updated_at"],
    }


@app.route("/api/board")
@permission_required("view_board")
def api_board():
    data = board_data()
    return jsonify({
        "stages": get_stage_names(),
        "terminal": get_terminal_stage(),
        "delivery_modes": list(DELIVERY_MODES),
        "alert_titles": ALERT_TYPE_TITLES,
        "columns": {stage: [_card(p) for p in cards] for stage, cards in data["columns"].items()},
        "alerts": {key: [{"id": p["id"], "name": p["name"]} for p in items] for key, items in data["alerts"].items()},
        "real_alerts": {key: len(items) for key, items in data["real_alerts"].items()},
        "dashboard": data["dashboard"],
        "recent_notes": [
            {"id": n["id"], "author": n["author"], "project_id": n["project_id"], "project_name": n["project_name"],
             "stage": n["stage"], "created_at": n["created_at"], "note": n["note"]}
            for n in data["recent_notes"]
        ],
        "banner_names": BANNER_NAMES,
        "column_cards": COLUMN_CARDS,
        "can_move": role_has_permission(session.get("role"), "edit_project_stage"),
    })


@app.route("/api/projects/<int:project_id>/stage", methods=["POST"])
@permission_required("edit_project_stage")
def api_project_stage(project_id):
    data = request.get_json(silent=True) or {}
    # change_stage audits and notifies; this is the same door the form uses.
    error = change_stage(project_id, data.get("stage", ""), (data.get("note") or "").strip()[:5000])
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/alerts/<int:project_id>/dismiss/<alert_type>", methods=["POST"])
@login_required
def api_alert_dismiss(project_id, alert_type):
    dismiss_alert(project_id, alert_type)
    audit_log("dismiss_alert", "project", project_id, None, alert_type)
    return jsonify({"ok": True})


@app.route("/assets/<path:filename>")
def spa_assets(filename):
    return spa_asset(filename)
