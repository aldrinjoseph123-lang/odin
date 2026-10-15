"""The page routes behind the React app's dashboard, people, my-work, flow,
analytics and alerts pages, plus the alert list the alerts API serves.
Imported for route registration side effects.
"""
from flask import abort, request, session

from constants import ALERT_TYPES, ALERT_TYPE_TITLES
from core import app, as_id, permission_required
from db import PROJECT_OPEN_SQL, get_db
from spa import spa_index

ALERTS_PER_PAGE = 50


@app.route("/dashboard")
@permission_required("view_board")
def dashboard():
    return spa_index()


@app.route("/people")
@permission_required("view_board")
def people():
    if session.get("kind") == "external":
        abort(403)
    return spa_index()


@app.route("/people/<int:user_id>")
@permission_required("view_board")
def person(user_id):
    if session.get("kind") == "external":
        abort(403)
    return spa_index()


@app.route("/my-work")
@permission_required("view_board")
def my_work():
    return spa_index()


@app.route("/board")
@permission_required("view_board")
def board():
    return spa_index()


@app.route("/analytics")
@permission_required("view_reports")
def analytics():
    """Where projects actually get stuck: internal cycle times across every rollout."""
    if session.get("kind") == "external":
        abort(403)
    return spa_index()


@app.route("/alerts")
@permission_required("view_board")
def alerts_log_view():
    if session.get("kind") == "external":   # alerts are an internal judgement (as the API)
        abort(403)
    return spa_index()


def alerts_page_data():
    """The alert list the alerts API serves. Staff only: an alert is an
    internal judgement (over SLA, stale, overdue) partners do not read."""
    if session.get("kind") == "external":
        abort(403)
    db = get_db()
    show_resolved = request.args.get("resolved") == "1"
    alert_type = request.args.get("type", "")
    if alert_type not in ALERT_TYPES:
        alert_type = ""
    page = max(1, request.args.get("page", type=as_id) or 1)

    where, params = ["p.deleted_at IS NULL"], []   # a deleted project's alerts went with it (the nav badge counts the same)
    if not show_resolved:
        where.append(f"a.resolved = 0 AND {PROJECT_OPEN_SQL}")
    if alert_type:
        where.append("a.alert_type = ?")
        params.append(alert_type)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    order = ("a.resolved ASC, " if show_resolved else "") + \
            "CASE a.severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, a.created_at DESC"

    total = db.execute(f"SELECT COUNT(*) AS c FROM alerts a JOIN projects p ON p.id = a.project_id{clause}", params).fetchone()["c"]
    total_pages = max(1, (total + ALERTS_PER_PAGE - 1) // ALERTS_PER_PAGE)
    page = min(page, total_pages)
    rows = db.execute(
        f"SELECT a.*, p.name AS project_name FROM alerts a "
        f"JOIN projects p ON p.id = a.project_id{clause} "
        f"ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, ALERTS_PER_PAGE, (page - 1) * ALERTS_PER_PAGE),
    ).fetchall()

    return dict(alerts=rows, show_resolved=show_resolved, alert_type=alert_type, alert_type_titles=ALERT_TYPE_TITLES,
                page=page, total_pages=total_pages, total=total)
