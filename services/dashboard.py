"""The Dashboard page: the portfolio this week, in numbers that already exist.

Every figure here is one the flow, the alerts or the weekly report already
compute — the page only gathers them: how many rollouts are active and how
many are stuck (overdue, over their stage SLA, due soon, waiting on a customer,
idle), every active rollout on one time axis, how many sit in each stage,
tasks ticked per day, what falls due in the next seven days, and who carries
the open work.

The week-over-week deltas need history, which nothing kept until now: a row
per day in `portfolio_snapshots`, written by the nightly housekeeping job and,
so the first week is not blank, by the page itself the first time it is
opened on a day. Snapshots are staff-wide; an external account's narrower
view gets no deltas.
"""
from collections import Counter
from datetime import datetime, timedelta

from db import PROJECT_OPEN_SQL, avatar_url, get_db, get_stage_names
from policies import local_today
from services.alerts import build_alerts

COUNT_KEYS = ("active", "overdue", "over_sla", "due_soon", "awaiting", "idle")
TIMELINE_LIMIT = 200   # ponytail: one flat list; page it if a portfolio ever grows past this


def tasks_due_by(db, until, scope=("", ()), limit=40):
    """Open tasks due on or before `until` (YYYY-MM-DD) on active rollouts,
    soonest first. Shared with the weekly report."""
    scope_sql, scope_params = scope
    return db.execute(
        "SELECT t.id, t.project_id, t.title, t.due_date, p.name AS project, u.name AS who, u.id AS who_id, u.avatar "
        "FROM tasks t JOIN projects p ON p.id = t.project_id LEFT JOIN users u ON u.id = t.assignee_id "
        f"WHERE t.done = 0 AND t.due_date IS NOT NULL AND t.due_date <= ? AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql} "
        "ORDER BY t.due_date, t.id LIMIT ?", (until, *scope_params, limit)).fetchall()


def _counts(db, projects, alerts, scope):
    scope_sql, scope_params = scope
    # waiting on the customer: the latest approval is pending and is for the stage the project is in now
    awaiting = db.execute(
        "SELECT COUNT(*) FROM stage_approvals a JOIN projects p ON p.id = a.project_id "
        "WHERE a.status = 'pending' AND a.stage = p.stage AND a.id = (SELECT MAX(id) FROM stage_approvals WHERE project_id = a.project_id) "
        f"AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql}", scope_params).fetchone()[0]
    return {"active": len(projects), "overdue": len(alerts["project_overdue"]), "over_sla": len(alerts["stage_sla_breach"]),
            "due_soon": len(alerts["project_due_soon"]), "awaiting": awaiting, "idle": len(alerts["stale"])}


def _active(db, scope):
    scope_sql, scope_params = scope
    return db.execute(
        f"SELECT p.* FROM projects p WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql} ORDER BY p.name", scope_params).fetchall()


def record_snapshot(day=None):
    """Write today's staff-wide counts (once per day; a later write for the
    same day replaces the earlier one, so the nightly job has the last word)."""
    db = get_db()
    day = (day or local_today()).isoformat()
    projects = _active(db, ("", ()))
    c = _counts(db, projects, build_alerts(projects), ("", ()))
    db.execute(
        "INSERT INTO portfolio_snapshots (day, active, overdue, over_sla, due_soon, awaiting, idle) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(day) DO UPDATE SET active = excluded.active, overdue = excluded.overdue, over_sla = excluded.over_sla, "
        "due_soon = excluded.due_soon, awaiting = excluded.awaiting, idle = excluded.idle",
        (day, *(c[k] for k in COUNT_KEYS)))
    db.commit()
    return c


def build(scope):
    """Everything the page draws, for the projects this session may see."""
    db = get_db()
    today = local_today()
    scope_sql, scope_params = scope
    projects = _active(db, scope)
    alerts = build_alerts(projects)
    counts = _counts(db, projects, alerts, scope)

    # deltas: against the nearest snapshot at least a week old; staff-wide, so only for an unrestricted view
    before, since = None, None
    if not scope_sql:
        if not db.execute("SELECT 1 FROM portfolio_snapshots WHERE day = ?", (today.isoformat(),)).fetchone():
            record_snapshot(today)
        row = db.execute("SELECT * FROM portfolio_snapshots WHERE day <= ? ORDER BY day DESC LIMIT 1",
                         ((today - timedelta(days=7)).isoformat(),)).fetchone()
        if row:
            before, since = {k: row[k] for k in COUNT_KEYS}, row["day"]

    stuck = {"overdue": {p["id"] for p in alerts["project_overdue"]}, "over_sla": {p["id"] for p in alerts["stage_sla_breach"]},
             "due_soon": {p["id"] for p in alerts["project_due_soon"]}}
    state = lambda p: next((k for k in ("overdue", "over_sla", "due_soon") if p["id"] in stuck[k]), "on_track")   # noqa: E731
    timeline = sorted(
        [{"id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"], "start_date": p["start_date"] or (p["created_at"] or "")[:10],
          "target_end_date": p["target_end_date"], "state": state(p)} for p in projects],
        key=lambda r: (r["target_end_date"] or "9999", r["name"]))[:TIMELINE_LIMIT]

    per_stage = Counter(p["stage"] for p in projects)
    order = list(get_stage_names()) + sorted(s for s in per_stage if s not in get_stage_names())
    stages = [{"stage": s, "count": per_stage[s]} for s in order if per_stage[s]]

    week_ago = datetime.utcnow() - timedelta(days=7)
    moved = db.execute(
        "SELECT COUNT(*) FROM status_notes n JOIN projects p ON p.id = n.project_id "
        f"WHERE n.prev_stage IS NOT NULL AND n.created_at >= ? AND p.deleted_at IS NULL{scope_sql}",
        (week_ago.isoformat(), *scope_params)).fetchone()[0]

    # ponytail: done_at is stored in UTC and bucketed by its UTC date; a tick late in the evening east of Greenwich lands on the next bar
    days = [(today - timedelta(days=6 - i)).isoformat() for i in range(7)]
    ticked = dict(db.execute(
        "SELECT substr(t.done_at, 1, 10) AS d, COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id "
        f"WHERE t.done = 1 AND t.done_at >= ? AND p.deleted_at IS NULL{scope_sql} GROUP BY d",
        (days[0], *scope_params)).fetchall())
    done_per_day = [{"day": d, "count": ticked.get(d, 0)} for d in days]

    due = [{"id": t["id"], "project_id": t["project_id"], "title": t["title"], "due_date": t["due_date"], "project": t["project"],
            "who": t["who"], "avatar_url": avatar_url({"id": t["who_id"], "avatar": t["avatar"]}) if t["who_id"] else None}
           for t in tasks_due_by(db, (today + timedelta(days=7)).isoformat(), scope)]

    load = [{"id": r["id"], "name": r["name"], "avatar_url": avatar_url(r), "open": r["open"], "late": r["late"]} for r in db.execute(
        "SELECT u.id, u.name, u.avatar, COUNT(*) AS open, SUM(CASE WHEN t.due_date IS NOT NULL AND t.due_date < ? THEN 1 ELSE 0 END) AS late "
        "FROM tasks t JOIN users u ON u.id = t.assignee_id JOIN projects p ON p.id = t.project_id "
        f"WHERE t.done = 0 AND u.active = 1 AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql} "
        "GROUP BY u.id ORDER BY late DESC, open DESC, u.name LIMIT 10", (today.isoformat(), *scope_params))]
    unassigned = db.execute(
        "SELECT COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id "
        f"WHERE t.done = 0 AND t.assignee_id IS NULL AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql}", scope_params).fetchone()[0]

    return {"today": today.isoformat(), "counts": counts, "before": before, "since": since, "moved_this_week": moved,
            "timeline": timeline, "stages": stages, "done_per_day": done_per_day, "due": due,
            "load": load, "unassigned": unassigned}
