"""The Dashboard: widgets on a grid, each drawn from numbers Odin already keeps.

A dashboard is a *layout* — an ordered list of `{id, w, settings}` — over the
widget catalogue below. The workspace default lives in the settings table
(`dashboard.layout`, set by an admin from the page itself); a user who
rearranges theirs keeps a copy on their row (`users.dashboard_layout`) until
they reset. Every widget's data is computed on each load, for the projects
the session may see, whatever the layout: the page only decides what to show.

Deltas and sparklines need history: one row a day in `portfolio_snapshots`,
written by nightly housekeeping and, so the first week is not blank, by the
page the first time it is opened on a day. Snapshots are staff-wide; an
external account's narrower view gets none.
"""
import json
from collections import Counter
from datetime import datetime, timedelta

from db import PROJECT_OPEN_SQL, avatar_url, get_db, get_setting, get_stage_names, stages_for_projects
from policies import local_today
from services.alerts import build_alerts

COUNT_KEYS = ("active", "overdue", "over_sla", "due_soon", "awaiting", "idle")
LAYOUT_KEY = "dashboard.layout"
HISTORY_DAYS = 14

# The catalogue. `w` is the default width in thirds of the grid; `settings`
# are per-widget knobs the page applies itself (the server only validates them).
WIDGETS = {
    "kpis":       dict(title="Headline numbers", blurb="Active, overdue, over SLA, due soon, waiting on customer and idle, with the week's change and a 14-day trend.", w=3,
                       settings={"tiles": dict(kind="multi", choices=COUNT_KEYS, default=list(COUNT_KEYS), label="Tiles")}),
    "timeline":   dict(title="Timeline", blurb="Every active rollout from start to target on one axis, its team on the bar.", w=2,
                       settings={"show": dict(kind="choice", choices=("all", "attention"), default="all", label="Show"),
                                 "limit": dict(kind="int", min=5, max=50, default=12, label="Rows")}),
    "progress":   dict(title="Portfolio progress", blurb="How far the portfolio is through its stages: done, in progress, still to come.", w=1, settings={}),
    "schedule":   dict(title="Schedule", blurb="What falls due next and which approvals are waiting on a customer.", w=1,
                       settings={"days": dict(kind="int", min=1, max=30, default=7, label="Days ahead")}),
    "completion": dict(title="Tasks completed", blurb="Tasks ticked off per day, against the week before.", w=1,
                       settings={"days": dict(kind="choice", choices=("7", "14", "28"), default="7", label="Days")}),
    "team":       dict(title="Team", blurb="Who is on what: rollouts, open and late tasks per person.", w=1,
                       settings={"limit": dict(kind="int", min=3, max=20, default=6, label="People")}),
    "stages":     dict(title="Rollouts per stage", blurb="Where the active rollouts sit.", w=1, settings={}),
    "activity":   dict(title="Recent activity", blurb="Stage moves, notes, decisions, tasks done and documents, newest first.", w=1,
                       settings={"limit": dict(kind="int", min=5, max=30, default=10, label="Items")}),
    "alerts":     dict(title="Open alerts", blurb="Overdue, over SLA, due soon and inactive rollouts the daily check raised.", w=1,
                       settings={"limit": dict(kind="int", min=5, max=30, default=8, label="Items")}),
    "mywork":     dict(title="My work", blurb="Your open tasks, soonest first, and the rollouts you own.", w=2, settings={}),
    "cycle":      dict(title="Cycle time", blurb="Lead time and rollouts closed per month for the main stage template.", w=1, settings={}),
}
DEFAULT_LAYOUT = [
    {"id": "kpis", "w": 3}, {"id": "timeline", "w": 2}, {"id": "progress", "w": 1},
    {"id": "schedule", "w": 1}, {"id": "completion", "w": 1}, {"id": "team", "w": 1},
    {"id": "stages", "w": 1}, {"id": "activity", "w": 1}, {"id": "alerts", "w": 1},
    {"id": "mywork", "w": 2}, {"id": "cycle", "w": 1},
]


def catalogue():
    return [{"id": k, "title": v["title"], "blurb": v["blurb"], "w": v["w"],
             "settings": [{"key": sk, **{a: b for a, b in sv.items() if a != "choices"}, **({"choices": list(sv["choices"])} if "choices" in sv else {})}
                          for sk, sv in v["settings"].items()]} for k, v in WIDGETS.items()]


def _setting(schema, raw):
    """One validated setting value, or the default when the value is off."""
    kind, default = schema["kind"], schema["default"]
    try:
        if kind == "int":
            return max(schema["min"], min(schema["max"], int(raw)))
        if kind == "choice":
            return raw if raw in schema["choices"] else default
        if kind == "multi":
            picked = [x for x in raw if x in schema["choices"]] if isinstance(raw, list) else None
            return picked if picked else list(default)
    except (TypeError, ValueError):
        pass
    return default


def normalize_layout(raw):
    """A clean layout from whatever arrived, or None when it is not a list:
    known widgets only, each once, widths 1–3, settings validated."""
    if not isinstance(raw, list):
        return None
    out, seen = [], set()
    for item in raw:
        wid = item.get("id") if isinstance(item, dict) else None
        if wid not in WIDGETS or wid in seen:
            continue
        seen.add(wid)
        try:
            w = max(1, min(3, int(item.get("w", WIDGETS[wid]["w"]))))
        except (TypeError, ValueError):
            w = WIDGETS[wid]["w"]
        given = item.get("settings") if isinstance(item.get("settings"), dict) else {}
        settings = {k: _setting(s, given.get(k, s["default"])) for k, s in WIDGETS[wid]["settings"].items()}
        out.append({"id": wid, "w": w, "settings": settings})
    return out


def default_layout():
    try:
        stored = normalize_layout(json.loads(get_setting(LAYOUT_KEY) or "null"))
    except ValueError:
        stored = None
    return stored if stored is not None else normalize_layout(DEFAULT_LAYOUT)


def user_layout(user_id):
    """(layout, is_custom): the user's own layout when they saved one, else the workspace default."""
    row = get_db().execute("SELECT dashboard_layout FROM users WHERE id = ?", (user_id,)).fetchone()
    if row and row["dashboard_layout"]:
        try:
            own = normalize_layout(json.loads(row["dashboard_layout"]))
            if own is not None:
                return own, True
        except ValueError:
            pass
    return default_layout(), False


# ---- data --------------------------------------------------------------------

def tasks_due_by(db, until, scope=("", ()), limit=40):
    """Open tasks due on or before `until` (YYYY-MM-DD) on active rollouts,
    soonest first. Shared with the weekly report."""
    scope_sql, scope_params = scope
    return db.execute(
        "SELECT t.id, t.project_id, t.title, t.due_date, t.stage, p.name AS project, u.name AS who, u.id AS who_id, u.avatar "
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


def _team_of(db, ids):
    """project_id -> participants, PM first (the avatars on a timeline bar)."""
    marks = ",".join("?" * len(ids)) or "NULL"
    team = {}
    for t in db.execute(
        "SELECT pp.project_id, u.id, u.name, u.avatar FROM project_participants pp JOIN users u ON u.id = pp.user_id "
        f"WHERE u.active = 1 AND pp.project_id IN ({marks}) ORDER BY CASE pp.role WHEN 'Project manager' THEN 0 ELSE 1 END, u.name", ids):
        team.setdefault(t["project_id"], []).append({"id": t["id"], "name": t["name"], "avatar_url": avatar_url(t)})
    return team


def _activity(db, scope, limit=30):
    """Stage moves, notes, decisions, tasks done and documents, newest first."""
    scope_sql, scope_params = scope
    base = f"JOIN projects p ON p.id = x.project_id WHERE p.deleted_at IS NULL{scope_sql}"
    sql = " UNION ALL ".join([
        f"SELECT 'move' AS kind, x.created_at AS at, x.author AS who, p.id AS pid, p.name AS project, x.prev_stage || ' → ' || x.stage AS text FROM status_notes x {base} AND x.prev_stage IS NOT NULL",
        f"SELECT 'note', x.created_at, x.author, p.id, p.name, x.note FROM status_notes x {base} AND x.prev_stage IS NULL",
        f"SELECT 'approval', x.decided_at, x.decided_by, p.id, p.name, x.stage || ' ' || x.status FROM stage_approvals x {base} AND x.decided_at IS NOT NULL",
        f"SELECT 'task', x.done_at, NULL, p.id, p.name, x.title FROM tasks x {base} AND x.done = 1 AND x.done_at IS NOT NULL",
        f"SELECT 'document', x.uploaded_at, x.uploaded_by, p.id, p.name, x.filename FROM documents x {base} AND x.deleted_at IS NULL",
    ]) + " ORDER BY at DESC LIMIT ?"
    return [{"kind": r["kind"], "at": r["at"], "who": r["who"], "project_id": r["pid"], "project": r["project"], "text": r["text"]}
            for r in db.execute(sql, (*scope_params * 5, limit))]


def _cycle(db, scope):
    """Lead time and throughput for the first stage template, as Cycle time shows them."""
    from services.analytics import build_cycle_times
    scope_sql, scope_params = scope
    template = db.execute("SELECT id, name FROM stage_templates ORDER BY id LIMIT 1").fetchone()
    if not template:
        return None
    projects = db.execute(f"SELECT p.* FROM projects p WHERE p.deleted_at IS NULL AND p.stage_template_id IS ?{scope_sql}", (template["id"], *scope_params)).fetchall()
    notes = {}
    for n in db.execute("SELECT project_id, stage, created_at FROM status_notes ORDER BY created_at"):
        notes.setdefault(n["project_id"], []).append(n)
    names = [r["name"] for r in db.execute("SELECT name FROM stage_template_stages WHERE template_id = ? ORDER BY position", (template["id"],))]
    if not names:
        return None
    s = build_cycle_times(projects, notes, names, names[-1])
    return {"template": template["name"], "lead_avg": s["lead_avg"], "lead_median": s["lead_median"], "completed_count": s["completed_count"],
            "throughput": s["throughput"][-6:], "slowest": s["slowest"], "measured_projects": s["measured_projects"]}


def build(scope, user_id):
    """Everything the page draws, for the projects this session may see."""
    db = get_db()
    today = local_today()
    scope_sql, scope_params = scope
    projects = _active(db, scope)
    ids = [p["id"] for p in projects]
    alerts = build_alerts(projects)
    counts = _counts(db, projects, alerts, scope)
    layout, is_custom = user_layout(user_id)

    # history: deltas against the nearest snapshot a week or more old, and a 14-day series per count
    before, since, series = None, None, {k: [] for k in COUNT_KEYS}
    if not scope_sql:
        if not db.execute("SELECT 1 FROM portfolio_snapshots WHERE day = ?", (today.isoformat(),)).fetchone():
            record_snapshot(today)
        row = db.execute("SELECT * FROM portfolio_snapshots WHERE day <= ? ORDER BY day DESC LIMIT 1",
                         ((today - timedelta(days=7)).isoformat(),)).fetchone()
        if row:
            before, since = {k: row[k] for k in COUNT_KEYS}, row["day"]
        for r in db.execute("SELECT * FROM portfolio_snapshots WHERE day > ? ORDER BY day", ((today - timedelta(days=HISTORY_DAYS)).isoformat(),)):
            for k in COUNT_KEYS:
                series[k].append({"day": r["day"], "v": r[k]})

    stuck = {"overdue": {p["id"] for p in alerts["project_overdue"]}, "over_sla": {p["id"] for p in alerts["stage_sla_breach"]},
             "due_soon": {p["id"] for p in alerts["project_due_soon"]}}
    state = lambda p: next((k for k in ("overdue", "over_sla", "due_soon") if p["id"] in stuck[k]), "on_track")   # noqa: E731
    stage_lists = stages_for_projects(ids)
    team = _team_of(db, ids)
    done_steps = current_steps = pending_steps = 0
    timeline = []
    for p in projects:
        names = [r["name"] for r in (stage_lists.get(p["id"]) or [])]
        at = names.index(p["stage"]) if p["stage"] in names else 0
        done_steps += at; current_steps += 1; pending_steps += max(0, len(names) - 1 - at)
        timeline.append({"id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"],
                         "start_date": p["start_date"] or (p["created_at"] or "")[:10], "target_end_date": p["target_end_date"],
                         "state": state(p), "progress": (at / (len(names) - 1)) if len(names) > 1 else 0,
                         "team": team.get(p["id"], [])})
    timeline.sort(key=lambda r: (r["target_end_date"] or "9999", r["name"]))
    total_steps = done_steps + current_steps + pending_steps
    progress = {"done": done_steps, "current": current_steps, "pending": pending_steps,
                "pct": round(100 * done_steps / total_steps) if total_steps else 0}

    per_stage = Counter(p["stage"] for p in projects)
    order = list(get_stage_names()) + sorted(s for s in per_stage if s not in get_stage_names())
    stages = [{"stage": s, "count": per_stage[s]} for s in order if per_stage[s]]

    week_ago = datetime.utcnow() - timedelta(days=7)
    moved = db.execute(
        "SELECT COUNT(*) FROM status_notes n JOIN projects p ON p.id = n.project_id "
        f"WHERE n.prev_stage IS NOT NULL AND n.created_at >= ? AND p.deleted_at IS NULL{scope_sql}",
        (week_ago.isoformat(), *scope_params)).fetchone()[0]

    # ponytail: done_at is stored in UTC and bucketed by its UTC date; a tick late in the evening east of Greenwich lands on the next bar
    days = [(today - timedelta(days=55 - i)).isoformat() for i in range(56)]   # 28 shown at most, plus the 28 before for the comparison
    ticked = dict(db.execute(
        "SELECT substr(t.done_at, 1, 10) AS d, COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id "
        f"WHERE t.done = 1 AND t.done_at >= ? AND p.deleted_at IS NULL{scope_sql} GROUP BY d",
        (days[0], *scope_params)).fetchall())
    completion = [{"day": d, "count": ticked.get(d, 0)} for d in days]

    due = [{"id": t["id"], "project_id": t["project_id"], "title": t["title"], "due_date": t["due_date"], "project": t["project"], "stage": t["stage"],
            "who": t["who"], "avatar_url": avatar_url({"id": t["who_id"], "avatar": t["avatar"]}) if t["who_id"] else None}
           for t in tasks_due_by(db, (today + timedelta(days=30)).isoformat(), scope, limit=60)]
    approvals = [{"project_id": r["project_id"], "project": r["name"], "stage": r["stage"], "requested_at": r["requested_at"]} for r in db.execute(
        "SELECT a.project_id, a.stage, a.requested_at, p.name FROM stage_approvals a JOIN projects p ON p.id = a.project_id "
        "WHERE a.status = 'pending' AND a.stage = p.stage AND a.id = (SELECT MAX(id) FROM stage_approvals WHERE project_id = a.project_id) "
        f"AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql} ORDER BY a.requested_at", scope_params)]

    open_sql = f"p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql}"
    people = [{"id": r["id"], "name": r["name"], "avatar_url": avatar_url(r), "role": r["role"], "projects": r["projects"], "open": r["open"], "late": r["late"]}
              for r in db.execute(
        "SELECT u.id, u.name, u.avatar, u.role, "
        f"(SELECT COUNT(*) FROM project_participants pp JOIN projects p ON p.id = pp.project_id WHERE pp.user_id = u.id AND {open_sql}) AS projects, "
        f"(SELECT COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.assignee_id = u.id AND t.done = 0 AND {open_sql}) AS open, "
        f"(SELECT COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.assignee_id = u.id AND t.done = 0 AND t.due_date < ? AND {open_sql}) AS late "
        "FROM users u WHERE u.active = 1 AND u.kind = 'internal' ORDER BY open DESC, projects DESC, u.name LIMIT 20",
        (*scope_params, *scope_params, today.isoformat(), *scope_params))]
    unassigned = db.execute(
        f"SELECT COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.done = 0 AND t.assignee_id IS NULL AND {open_sql}", scope_params).fetchone()[0]

    open_alerts = [{"id": a["id"], "project_id": a["project_id"], "project": a["project_name"], "type": a["alert_type"], "title": a["title"],
                    "severity": a["severity"], "created_at": a["created_at"]} for a in db.execute(
        "SELECT a.*, p.name AS project_name FROM alerts a JOIN projects p ON p.id = a.project_id "
        f"WHERE a.resolved = 0 AND p.deleted_at IS NULL{scope_sql} "
        "ORDER BY CASE a.severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, a.created_at DESC LIMIT 30", scope_params)]

    mine = {"tasks": [{"id": t["id"], "title": t["title"], "project_id": t["project_id"], "project": t["project_name"], "due_date": t["due_date"], "stage": t["stage"]}
                      for t in db.execute(
        "SELECT t.*, p.name AS project_name FROM tasks t JOIN projects p ON p.id = t.project_id "
        f"WHERE t.assignee_id = ? AND t.done = 0 AND {open_sql} ORDER BY t.due_date IS NULL, t.due_date, t.id LIMIT 12", (user_id, *scope_params))],
            "owned": db.execute(f"SELECT COUNT(*) FROM projects p WHERE p.owner_id = ? AND {open_sql}", (user_id, *scope_params)).fetchone()[0]}

    return {"today": today.isoformat(), "layout": layout, "is_custom": is_custom, "catalogue": catalogue(), "scope_full": not scope_sql,
            "data": {"kpis": {"counts": counts, "before": before, "since": since, "moved_this_week": moved, "series": series},
                     "timeline": timeline, "progress": progress, "stages": stages, "completion": completion,
                     "schedule": {"due": due, "approvals": approvals}, "team": {"people": people, "unassigned": unassigned},
                     "activity": _activity(db, scope), "alerts": open_alerts, "mywork": mine, "cycle": _cycle(db, scope)}}
