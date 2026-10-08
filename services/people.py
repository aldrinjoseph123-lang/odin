"""People and their work: the My Work page, the People directory and a
person's page. Everything here is about active rollouts the session may see
and the tasks on them; "contribution" is what the person finished, noted
and moved, counted from the same rows the flow keeps.
"""
from collections import Counter
from datetime import date, datetime, timedelta

from db import PROJECT_OPEN_SQL, avatar_url, get_db, stages_for_projects
from policies import local_date, local_today, policy
from services.alerts import project_states as _states
from services.analytics import days_in_stage, sla_by_stage, stage_sla_state

STATE_LABEL = {"overdue": "Overdue", "over_sla": "Over SLA", "due_soon": "Due soon", "on_track": "On track"}


def _since(day):
    """The UTC timestamp of the workspace's midnight starting `day`, to compare
    with stored UTC timestamps (done_at, created_at)."""
    from zoneinfo import ZoneInfo
    from datetime import timezone
    start = datetime.combine(day, datetime.min.time()).replace(tzinfo=ZoneInfo(policy("timezone")))
    return start.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def _projects_of(db, uid, scope):
    """Active rollouts the person owns or is on, with their role on each."""
    scope_sql, scope_params = scope
    return db.execute(
        "SELECT p.*, u.name AS owner_name, COALESCE(pp.role, 'Project manager') AS my_role FROM projects p JOIN users u ON u.id = p.owner_id "
        "LEFT JOIN project_participants pp ON pp.project_id = p.id AND pp.user_id = ? "
        f"WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} AND (p.owner_id = ? OR pp.id IS NOT NULL){scope_sql} ORDER BY p.name",
        (uid, uid, *scope_params)).fetchall()


def _task_rows(db, where, params):
    return [dict(r) for r in db.execute(
        "SELECT t.id, t.project_id, t.title, t.due_date, t.stage, t.done, t.done_at, p.name AS project, p.client, p.stage AS project_stage "
        f"FROM tasks t JOIN projects p ON p.id = t.project_id WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} AND {where} "
        "ORDER BY t.due_date IS NULL, t.due_date, t.id", params)]


def _project_rows(db, projects, states, stage_lists):
    """One row per rollout with the fields the Flow's rows carry for its state text."""
    out, now = [], datetime.utcnow()
    for p in projects:
        own = stage_lists.get(p["id"]) or []
        names = [r["name"] for r in own]
        slas = sla_by_stage(own)
        sla = stage_sla_state(p, slas, names[-1] if names else None, now)
        in_stage = sla["days"] if sla else days_in_stage(p["stage_entered_at"], now)
        out.append({"id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"], "state": states[p["id"]],
                    "stage_index": names.index(p["stage"]) if p["stage"] in names else 0, "stages": len(names),
                    "target_end_date": p["target_end_date"], "role": p["my_role"], "owner_name": p["owner_name"],
                    "days_in_stage": None if in_stage is None else round(in_stage, 1), "sla_days": slas.get(p["stage"]),
                    "over_by": round(sla["over_by"], 1) if sla else None})
    return out


def my_work(uid, scope):
    """The signed-in person's own work: tasks (open, grouped by the page),
    what they finished lately, and the rollouts they are on."""
    db = get_db()
    today = local_today()
    scope_sql, scope_params = scope
    tasks = _task_rows(db, f"t.assignee_id = ? AND t.done = 0{scope_sql}", (uid, *scope_params))
    since = _since(today - timedelta(days=13))
    done = Counter(local_date(r[0]).isoformat() for r in db.execute(
        "SELECT t.done_at FROM tasks t JOIN projects p ON p.id = t.project_id "
        f"WHERE t.assignee_id = ? AND t.done = 1 AND t.done_at >= ? AND p.deleted_at IS NULL{scope_sql}", (uid, since, *scope_params)))
    days = [(today - timedelta(days=13 - i)).isoformat() for i in range(14)]
    projects = _projects_of(db, uid, scope)
    states = _states(projects)
    week = (today + timedelta(days=7)).isoformat()
    t_iso = today.isoformat()
    return {
        "today": t_iso, "tasks": tasks,
        "done_by_day": [{"day": d, "count": done.get(d, 0)} for d in days],
        "projects": _project_rows(db, projects, states, stages_for_projects([p["id"] for p in projects])),
        "counts": {"open": len(tasks), "overdue": sum(1 for t in tasks if t["due_date"] and t["due_date"] < t_iso),
                   "due_week": sum(1 for t in tasks if t["due_date"] and t_iso <= t["due_date"] <= week),
                   "done_week": sum(n for d, n in done.items() if d >= (today - timedelta(days=6)).isoformat()),
                   "rollouts": len(projects), "stuck": sum(1 for s in states.values() if s != "on_track")},
    }


def people(scope):
    """Everyone internal who is on active work: a card each."""
    db = get_db()
    today = local_today().isoformat()
    scope_sql, scope_params = scope
    month_ago = _since(local_today() - timedelta(days=30))
    open_sql = f"p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql}"
    rows = db.execute(
        "SELECT u.id, u.name, u.role, u.avatar, u.last_login_at, u.last_seen_at, "
        f"(SELECT COUNT(DISTINCT p.id) FROM projects p LEFT JOIN project_participants pp ON pp.project_id = p.id AND pp.user_id = u.id WHERE {open_sql} AND (p.owner_id = u.id OR pp.id IS NOT NULL)) AS projects, "
        f"(SELECT COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.assignee_id = u.id AND t.done = 0 AND {open_sql}) AS open, "
        f"(SELECT COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.assignee_id = u.id AND t.done = 0 AND t.due_date < ? AND {open_sql}) AS late, "
        f"(SELECT COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.assignee_id = u.id AND t.done = 1 AND t.done_at >= ? AND p.deleted_at IS NULL{scope_sql}) AS done_30d "
        "FROM users u WHERE u.active = 1 AND u.kind = 'internal' ORDER BY projects DESC, open DESC, u.name",
        (*scope_params, *scope_params, today, *scope_params, month_ago, *scope_params)).fetchall()
    seen = policy("activity_tracking")   # off: Last seen is the last sign-in
    return [{"id": r["id"], "name": r["name"], "role": r["role"], "avatar_url": avatar_url(r), "last_login_at": r["last_login_at"],
             "last_seen_at": (r["last_seen_at"] if seen else None) or r["last_login_at"],
             "projects": r["projects"], "open": r["open"], "late": r["late"], "done_30d": r["done_30d"]}
            for r in rows if r["projects"] or r["open"] or r["done_30d"]]


def person(uid, scope):
    """One person's page, or None: KPIs, their rollouts, pending and upcoming
    tasks, and what they contributed lately."""
    db = get_db()
    u = db.execute("SELECT id, name, role, email, avatar, last_login_at, created_at FROM users WHERE id = ? AND active = 1 AND kind = 'internal'", (uid,)).fetchone()
    if not u:
        return None
    today = local_today()
    t_iso = today.isoformat()
    scope_sql, scope_params = scope
    projects = _projects_of(db, uid, scope)
    states = _states(projects)
    pending = _task_rows(db, f"t.assignee_id = ? AND t.done = 0{scope_sql}", (uid, *scope_params))
    month_ago = _since(today - timedelta(days=30))
    done = _task_rows(db, f"t.assignee_id = ? AND t.done = 1 AND t.done_at >= ?{scope_sql}", (uid, _since(today - timedelta(days=56)), *scope_params))
    dated = [t for t in done if t["due_date"] and t["done_at"] >= month_ago]
    on_time = sum(1 for t in dated if local_date(t["done_at"]).isoformat() <= t["due_date"])
    # contribution by week, the last eight
    weeks = []
    for i in range(7, -1, -1):
        start = today - timedelta(days=today.weekday() + 7 * i)
        end = start + timedelta(days=7)
        weeks.append({"week": start.isoformat(), "done": sum(1 for t in done if start <= local_date(t["done_at"]) < end)})
    notes = db.execute(f"SELECT COUNT(*) FROM status_notes n JOIN projects p ON p.id = n.project_id WHERE n.author_id = ? AND n.prev_stage IS NULL AND n.created_at >= ? AND p.deleted_at IS NULL{scope_sql}",
                       (uid, month_ago, *scope_params)).fetchone()[0]
    moves = db.execute(f"SELECT COUNT(*) FROM status_notes n JOIN projects p ON p.id = n.project_id WHERE (n.author_id = ? OR (n.author_id IS NULL AND n.author = ?)) AND n.prev_stage IS NOT NULL AND n.created_at >= ? AND p.deleted_at IS NULL{scope_sql}",
                       (uid, u["name"], month_ago, *scope_params)).fetchone()[0]
    recent = [dict(r) for r in db.execute(
        "SELECT * FROM (SELECT 'move' AS kind, n.created_at AS at, p.id AS project_id, p.name AS project, n.prev_stage || ' → ' || n.stage AS text FROM status_notes n JOIN projects p ON p.id = n.project_id "
        f"WHERE (n.author_id = ? OR (n.author_id IS NULL AND n.author = ?)) AND n.prev_stage IS NOT NULL AND p.deleted_at IS NULL{scope_sql} "
        "UNION ALL SELECT 'note', n.created_at, p.id, p.name, n.note FROM status_notes n JOIN projects p ON p.id = n.project_id "
        f"WHERE (n.author_id = ? OR (n.author_id IS NULL AND n.author = ?)) AND n.prev_stage IS NULL AND p.deleted_at IS NULL{scope_sql} "
        "UNION ALL SELECT 'task', t.done_at, p.id, p.name, t.title FROM tasks t JOIN projects p ON p.id = t.project_id "
        f"WHERE t.assignee_id = ? AND t.done = 1 AND t.done_at IS NOT NULL AND p.deleted_at IS NULL{scope_sql}) ORDER BY at DESC LIMIT 12",
        (uid, u["name"], *scope_params, uid, u["name"], *scope_params, uid, *scope_params))]
    return {
        "user": {"id": u["id"], "name": u["name"], "role": u["role"], "email": u["email"], "avatar_url": avatar_url(u), "last_login_at": u["last_login_at"], "since": u["created_at"]},
        "today": t_iso,
        "kpis": {"rollouts": len(projects), "stuck": sum(1 for s in states.values() if s != "on_track"), "open": len(pending),
                 "late": sum(1 for t in pending if t["due_date"] and t["due_date"] < t_iso),
                 "done_30d": sum(1 for t in done if t["done_at"] >= month_ago), "on_time_pct": round(100 * on_time / len(dated)) if dated else None},
        "projects": _project_rows(db, projects, states, stages_for_projects([p["id"] for p in projects])),
        "pending": pending,
        "upcoming": [t for t in pending if t["due_date"] and t_iso <= t["due_date"] <= (today + timedelta(days=14)).isoformat()],
        "contribution": {"weeks": weeks, "notes_30d": notes, "moves_30d": moves},
        "recent": recent,
    }
