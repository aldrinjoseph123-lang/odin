"""The Calendar view on the Flow page: a month of what is due, what moved
and what is waiting, for the projects the session may see.

Days are the workspace's local dates for due and target dates; a stage move
or a decision is placed on the UTC day of its timestamp. The range is padded
a week either side of the month's six-week grid, so the page can show the
grey days at its edges without a second request.
"""
from datetime import date, timedelta

from db import PROJECT_OPEN_SQL, get_db
from policies import local_today
from services.alerts import build_alerts


def month_range(month, today):
    """(first of the month, range start, range end) for "YYYY-MM"; a bad or
    missing month means the current one."""
    try:
        y, m = (int(x) for x in month.split("-"))
        first = date(y, m, 1)
    except (ValueError, AttributeError):
        first = today.replace(day=1)
    start = first - timedelta(days=first.weekday() + 7)     # the Monday a week before the grid starts
    return first, start, start + timedelta(days=7 * 8)


def build(month, scope):
    db = get_db()
    today = local_today()
    first, start, end = month_range(month, today)
    s, e = start.isoformat(), end.isoformat()
    scope_sql, scope_params = scope
    projects = db.execute(
        f"SELECT p.* FROM projects p WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql} ORDER BY p.name", scope_params).fetchall()
    alerts = build_alerts(projects)
    stuck = {"overdue": {p["id"] for p in alerts["project_overdue"]}, "over_sla": {p["id"] for p in alerts["stage_sla_breach"]},
             "due_soon": {p["id"] for p in alerts["project_due_soon"]}}
    state = lambda p: next((k for k in ("overdue", "over_sla", "due_soon") if p["id"] in stuck[k]), "on_track")   # noqa: E731
    starts = lambda p: p["start_date"] or (p["created_at"] or "")[:10]   # noqa: E731
    spans = [{"id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"], "start_date": starts(p),
              "target_end_date": p["target_end_date"], "state": state(p)}
             for p in projects if starts(p) <= e and (p["target_end_date"] or "9999") >= s]
    targets = [{"id": p["id"], "name": p["name"], "client": p["client"], "day": p["target_end_date"], "state": state(p)}
               for p in projects if p["target_end_date"] and s <= p["target_end_date"] <= e]
    tasks = [dict(r) for r in db.execute(
        "SELECT t.id, t.project_id, t.title, t.due_date AS day, t.done, p.name AS project, u.name AS who FROM tasks t "
        "JOIN projects p ON p.id = t.project_id LEFT JOIN users u ON u.id = t.assignee_id "
        f"WHERE t.due_date BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} ORDER BY t.due_date, t.done, t.id", (s, e, *scope_params))]
    moves = [dict(r) for r in db.execute(
        "SELECT n.project_id, p.name AS project, substr(n.created_at, 1, 10) AS day, n.prev_stage, n.stage, n.author AS who FROM status_notes n "
        f"JOIN projects p ON p.id = n.project_id WHERE n.prev_stage IS NOT NULL AND substr(n.created_at, 1, 10) BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} "
        "ORDER BY n.created_at", (s, e, *scope_params))]
    approvals = [dict(r) for r in db.execute(
        "SELECT a.project_id, p.name AS project, a.stage, substr(a.requested_at, 1, 10) AS day, 'asked' AS kind, a.status, a.requested_by AS who FROM stage_approvals a "
        f"JOIN projects p ON p.id = a.project_id WHERE substr(a.requested_at, 1, 10) BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} "
        "UNION ALL "
        "SELECT a.project_id, p.name, a.stage, substr(a.decided_at, 1, 10), 'decided', a.status, a.decided_by FROM stage_approvals a "
        f"JOIN projects p ON p.id = a.project_id WHERE a.decided_at IS NOT NULL AND substr(a.decided_at, 1, 10) BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} "
        "ORDER BY 4", (s, e, *scope_params, s, e, *scope_params))]
    return {"month": first.strftime("%Y-%m"), "today": today.isoformat(), "from": s, "to": e,
            "spans": spans, "targets": targets, "tasks": tasks, "moves": moves, "approvals": approvals}
