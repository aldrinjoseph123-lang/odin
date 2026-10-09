"""The Calendar view on the Flow page: a month of what is due, what moved
and what is waiting, for the projects the session may see.

Days are the workspace's local dates for due and target dates; a stage move
or a decision is placed on the UTC day of its timestamp. The range is padded
a week either side of the month's six-week grid, so the page can show the
grey days at its edges without a second request.
"""
from datetime import date, timedelta

from db import PROJECT_OPEN_SQL, get_db
from policies import local_date, local_today
from services.alerts import project_states


def month_range(month, today):
    """(first of the month, range start, range end) for "YYYY-MM"; a bad or
    missing month means the current one."""
    try:
        y, m = (int(x) for x in month.split("-"))
        first = date(y, m, 1)
        if not 2000 <= y <= 2100:   # the grid pads weeks either side: year 1 or 9999 would overflow
            raise ValueError(month)
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
    states = project_states(projects)
    state = lambda p: states[p["id"]]   # noqa: E731
    starts = lambda p: p["start_date"] or (local_date(p["created_at"]) or today).isoformat()   # noqa: E731
    spans = [{"id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"], "start_date": starts(p),
              "target_end_date": p["target_end_date"], "state": state(p)}
             for p in projects if starts(p) <= e and (p["target_end_date"] or "9999") >= s]
    targets = [{"id": p["id"], "name": p["name"], "client": p["client"], "day": p["target_end_date"], "state": state(p)}
               for p in projects if p["target_end_date"] and s <= p["target_end_date"] <= e]
    tasks = [dict(r) for r in db.execute(
        "SELECT t.id, t.project_id, t.title, t.due_date AS day, t.done, p.name AS project, u.name AS who FROM tasks t "
        "JOIN projects p ON p.id = t.project_id LEFT JOIN users u ON u.id = t.assignee_id "
        f"WHERE t.due_date BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} ORDER BY t.due_date, t.done, t.id", (s, e, *scope_params))]
    sw = (date.fromisoformat(s) - timedelta(days=1)).isoformat()   # a UTC day earlier: local mornings sit on the previous UTC date
    moves = [dict(r) for r in db.execute(
        "SELECT n.project_id, p.name AS project, n.created_at AS day, n.prev_stage, n.stage, n.author AS who FROM status_notes n "
        f"JOIN projects p ON p.id = n.project_id WHERE n.prev_stage IS NOT NULL AND substr(n.created_at, 1, 10) BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} "
        "ORDER BY n.created_at", (sw, e, *scope_params))]
    approvals = [dict(r) for r in db.execute(
        "SELECT a.project_id, p.name AS project, a.stage, a.requested_at AS day, 'asked' AS kind, a.status, a.requested_by AS who FROM stage_approvals a "
        f"JOIN projects p ON p.id = a.project_id WHERE substr(a.requested_at, 1, 10) BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} "
        "UNION ALL "
        "SELECT a.project_id, p.name, a.stage, a.decided_at, 'decided', a.status, a.decided_by FROM stage_approvals a "
        f"JOIN projects p ON p.id = a.project_id WHERE a.decided_at IS NOT NULL AND substr(a.decided_at, 1, 10) BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} "
        "ORDER BY 4", (sw, e, *scope_params, sw, e, *scope_params))]
    # stored times are UTC: place each on its workspace-local day (01:30 in Dubai is the previous UTC day)
    def local_days(rows):
        out = []
        for r in rows:
            r["day"] = local_date(r["day"]).isoformat()
            if s <= r["day"] <= e:
                out.append(r)
        return out
    moves, approvals = local_days(moves), local_days(approvals)
    return {"month": first.strftime("%Y-%m"), "today": today.isoformat(), "from": s, "to": e,
            "spans": spans, "targets": targets, "tasks": tasks, "moves": moves, "approvals": approvals}
