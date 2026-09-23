"""JSON API for the React front end. Same session cookie, same CSRF token
(sent as X-CSRF-Token), same decorators and audit trail as the HTML routes —
the API is a second door into the same rooms, not a second house.
"""
from flask import abort, jsonify, request, session

from datetime import date, datetime

from constants import ALERT_TYPE_TITLES, DELIVERY_MODES
from core import app, login_required, nav_counts, permission_required, project_scope, role_has_permission
from db import PROJECT_OPEN_SQL, current_approval, get_db, get_stage_names, get_terminal_stage, is_customer_on, my_project_ids, participants_for, sla_for_project, stages_for_projects
from routes.auth import attempt_login
from routes.board import BANNER_NAMES, COLUMN_CARDS, board_data, dismiss_alert
from routes.projects import change_stage, decide_approval, load_project
from security import csrf_token
from services.alerts import schedule_status
from services.analytics import _parse, sla_by_stage, stage_sla_state, stage_timeline
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
        "kind": session.get("kind", "internal"),
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


@app.route("/api/projects/<int:project_id>/approvals/<int:approval_id>", methods=["POST"])
@login_required
def api_approval_decide(project_id, approval_id):
    body = request.get_json(silent=True) or {}
    error = decide_approval(project_id, approval_id, body.get("decision"), body.get("comment"))
    if error:
        return jsonify(error=error), 400
    return jsonify(ok=True)


@app.route("/api/projects/<int:project_id>/stage", methods=["POST"])
@permission_required("edit_project_stage")
def api_project_stage(project_id):
    load_project(project_id)
    data = request.get_json(silent=True) or {}
    # change_stage audits and notifies; this is the same door the form uses.
    error = change_stage(project_id, data.get("stage", ""), (data.get("note") or "").strip()[:5000])
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/alerts/<int:project_id>/dismiss/<alert_type>", methods=["POST"])
@login_required
def api_alert_dismiss(project_id, alert_type):
    load_project(project_id)
    dismiss_alert(project_id, alert_type)
    audit_log("dismiss_alert", "project", project_id, None, alert_type)
    return jsonify({"ok": True})


# ---- Flow: the first screen. Every active rollout, stuck first; then one
# rollout's stage flow with tasks, next action, ETA and timeline. -------------

STATE_RANK = {"overdue": 0, "over_sla": 1, "due_soon": 2, "on_track": 3}


def _flow_state(project, sla, schedule):
    if schedule == "overdue":
        return "overdue"
    if sla and sla["breached"]:
        return "over_sla"
    if schedule == "at_risk":
        return "due_soon"
    return "on_track"


def _days_since(iso, now):
    parsed = _parse(iso) if iso else None
    return round((now - parsed).total_seconds() / 86400, 1) if parsed else None


@app.route("/api/flow")
@permission_required("view_board")
def api_flow():
    db = get_db()
    now = datetime.utcnow()
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.done = 0) AS open_tasks, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id) AS total_tasks "
        "FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{project_scope()[0]} ORDER BY p.updated_at DESC",
        project_scope()[1],
    ).fetchall()
    stage_lists = stages_for_projects([p["id"] for p in projects])
    mine = my_project_ids(session["user_id"])
    # latest approval per project, only meaningful for the current stage
    approvals = {}
    for r in db.execute(
        "SELECT a.project_id, a.stage, a.status FROM stage_approvals a "
        "WHERE a.id = (SELECT MAX(id) FROM stage_approvals WHERE project_id = a.project_id)"
    ):
        approvals[r["project_id"]] = r
    team = {}   # project_id -> participant names, PM first (avatars on the row)
    for r in db.execute(
        "SELECT pp.project_id, u.name FROM project_participants pp JOIN users u ON u.id = pp.user_id "
        "WHERE u.active = 1 ORDER BY CASE pp.role WHEN 'Project manager' THEN 0 ELSE 1 END, u.name"
    ):
        team.setdefault(r["project_id"], []).append(r["name"])
    # Earliest-due open task per project = the next actionable item.
    next_task = {}
    for t in db.execute(
        "SELECT t.project_id, t.title, t.due_date, u.name AS assignee_name FROM tasks t "
        "LEFT JOIN users u ON u.id = t.assignee_id WHERE t.done = 0 "
        "ORDER BY t.due_date IS NULL, t.due_date, t.id"
    ):
        next_task.setdefault(t["project_id"], {"title": t["title"], "due_date": t["due_date"], "assignee": t["assignee_name"]})
    rows = []
    for p in projects:
        own = stage_lists.get(p["id"]) or []
        stages = [r["name"] for r in own]
        terminal = stages[-1] if stages else None
        slas = sla_by_stage(own)
        sla = stage_sla_state(p, slas, terminal, now)
        schedule = schedule_status(p, terminal_stage=terminal)
        state = _flow_state(p, sla, schedule)
        rows.append({
            "id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"],
            "stages": stages, "mine": p["id"] in mine, "team": team.get(p["id"], [p["owner_name"]]),
            "approval": (approvals[p["id"]]["status"] if p["id"] in approvals and approvals[p["id"]]["stage"] == p["stage"] else None),
            "stage_index": stages.index(p["stage"]) if p["stage"] in stages else 0,
            "owner_name": p["owner_name"], "delivery_mode": p["delivery_mode"],
            "target_end_date": p["target_end_date"], "days_in_stage": _days_since(p["stage_entered_at"], now),
            "sla_days": slas.get(p["stage"]), "over_by": round(sla["over_by"], 1) if sla else None,
            "state": state, "open_tasks": p["open_tasks"], "total_tasks": p["total_tasks"],
            "next_task": next_task.get(p["id"]), "updated_at": p["updated_at"],
        })
    rows.sort(key=lambda r: (STATE_RANK[r["state"]], r["updated_at"] or ""), reverse=False)
    # inside each state, most recently touched first
    rows.sort(key=lambda r: (STATE_RANK[r["state"]], -(_parse(r["updated_at"]) or now).timestamp()))
    counts = {k: sum(1 for r in rows if r["state"] == k) for k in STATE_RANK}
    return jsonify({"stages": get_stage_names(), "rows": rows, "counts": counts,
                    "can_move": role_has_permission(session.get("role"), "edit_project_stage")})


@app.route("/api/projects/<int:project_id>/flow")
@permission_required("view_project_detail")
def api_project_flow(project_id):
    db = get_db()
    project = load_project(project_id)
    stages, terminal = get_stage_names(project_id), get_terminal_stage(project_id)
    slas = sla_for_project(project_id)
    now = datetime.utcnow()
    notes = db.execute("SELECT * FROM status_notes WHERE project_id = ? ORDER BY created_at", (project_id,)).fetchall()
    timeline = stage_timeline(project, notes, stages[0])
    # Dwell per stage: the last visit's span (a stage can be revisited; the
    # latest visit is what the current SLA measures).
    visits = {}
    for i, (stage, entered) in enumerate(timeline):
        left = timeline[i + 1][1] if i + 1 < len(timeline) else now
        visits[stage] = {"entered_at": entered.isoformat(), "days": round((left - entered).total_seconds() / 86400, 1)}
    current = stages.index(project["stage"]) if project["stage"] in stages else 0
    stage_rows = []
    for i, name in enumerate(stages):
        status = "done" if i < current else "current" if i == current else "next"
        stage_rows.append({"name": name, "status": status, "sla_days": slas.get(name),
                           **(visits.get(name) or {"entered_at": None, "days": None})})
    tasks = db.execute(
        "SELECT t.*, u.name AS assignee_name FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id "
        "WHERE t.project_id = ? ORDER BY t.done, t.due_date IS NULL, t.due_date, t.id", (project_id,),
    ).fetchall()
    sla = stage_sla_state(project, slas, terminal, now)
    schedule = schedule_status(project, terminal_stage=terminal)
    target = date.fromisoformat(project["target_end_date"]) if project["target_end_date"] else None
    start = project["start_date"] or project["created_at"][:10]
    return jsonify({
        "id": project["id"], "name": project["name"], "client": project["client"],
        "vendor_name": project["vendor_name"], "product_name": project["product_name"],
        "delivery_mode": project["delivery_mode"], "outsourcer_name": project["outsourcer_name"],
        "owner_name": project["owner_name"], "stage": project["stage"], "stage_index": current,
        "next_stage": stages[current + 1] if current + 1 < len(stages) else None,
        "state": _flow_state(project, sla, schedule), "over_by": round(sla["over_by"], 1) if sla else None,
        "start_date": start, "target_end_date": project["target_end_date"],
        "days_left": (target - date.today()).days if target else None,
        "today": date.today().isoformat(),
        "stages": stage_rows,
        # a task without a stage belongs to whatever stage the project is in
        "tasks": [{"id": t["id"], "title": t["title"], "done": bool(t["done"]), "due_date": t["due_date"],
                   "assignee": t["assignee_name"], "assignee_id": t["assignee_id"],
                   "stage": t["stage"] if t["stage"] in stages else project["stage"]} for t in tasks],
        "assignable": [{"id": r["user_id"], "name": r["name"]} for r in participants_for(project_id) if r["active"]],
        "can_edit": role_has_permission(session.get("role"), "edit_project"),
        "me": session["user_id"],
        "documents": db.execute("SELECT COUNT(*) AS c FROM documents WHERE project_id = ? AND deleted_at IS NULL", (project_id,)).fetchone()["c"],
        "recent_notes": [{"author": n["author"], "note": n["note"], "stage": n["stage"], "created_at": n["created_at"]} for n in notes[-4:][::-1]],
        "participants": [{"id": r["id"], "user_id": r["user_id"], "name": r["name"], "role": r["role"]} for r in participants_for(project_id)],
        "can_move": role_has_permission(session.get("role"), "edit_project_stage"),
        "customer_approval": bool(project["customer_approval"]),
        "approval": ({"id": a["id"], "stage": a["stage"], "status": a["status"], "decided_by": a["decided_by"], "comment": a["comment"]}
                     if (a := current_approval(project_id)) else None),
        "can_approve": is_customer_on(project_id, session["user_id"]),
    })


@app.route("/assets/<path:filename>")
def spa_assets(filename):
    return spa_asset(filename)
