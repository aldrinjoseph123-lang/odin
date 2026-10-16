"""Workload: hours per person per week, from the tasks and rollouts Odin already keeps.

A week (Monday to Sunday, in the workspace time zone) loads a person with
their open tasks due in it (the task's estimate, else policy
`default_task_hours`) plus a fixed allowance (`pm_hours_per_rollout`) for each
active rollout they manage. Open work that is already late counts in the
current week: it still has to be done now. Capacity is the person's own
`users.capacity_hours`, else policy `capacity_hours_per_week`. Hours and
counts only, never money. Staff only: partners get a 403 from the routes.
"""
from datetime import date, timedelta

from db import PROJECT_OPEN_SQL, avatar_url, get_db
from policies import local_today, policy

WEEKS = 4   # the people page and the widget look this far ahead


def monday(day):
    return day - timedelta(days=day.weekday())


def level(hours, capacity):
    """ok / warn (amber, from policy workload_warn_pct) / over (red, above 100 %)."""
    if hours > capacity:
        return "over"
    return "warn" if hours * 100 > capacity * policy("workload_warn_pct") else "ok"


def _task_hours(db, first, count):
    """{user_id: [(hours, tasks)] * count} for the weeks starting `first`; late work folds into the current week."""
    default = policy("default_task_hours")
    this_week = monday(local_today())
    out = {}
    for r in db.execute(
        "SELECT t.assignee_id, t.due_date, t.estimate_hours FROM tasks t JOIN projects p ON p.id = t.project_id "
        f"WHERE t.done = 0 AND t.assignee_id IS NOT NULL AND t.due_date IS NOT NULL AND t.due_date < ? AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}",
        ((first + timedelta(days=7 * count)).isoformat(),)):
        due = r["due_date"]
        try:
            i = ((monday(date.fromisoformat(due[:10])) - first).days) // 7
        except ValueError:
            continue   # not a date: no week to put it in
        if i < 0:
            if first != this_week:
                continue   # late work belongs to now, so only the current week's window takes it
            i = 0
        row = out.setdefault(r["assignee_id"], [[0.0, 0] for _ in range(count)])
        row[i][0] += r["estimate_hours"] or default
        row[i][1] += 1
    return out


def _managed(db):
    """{user_id: number of active rollouts they manage}."""
    return {r[0]: r[1] for r in db.execute(
        f"SELECT p.owner_id, COUNT(*) FROM projects p WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} GROUP BY p.owner_id")}


def _staff(db):
    return db.execute("SELECT id, name, role, avatar, capacity_hours FROM users WHERE active = 1 AND kind = 'internal' AND pending = 0 ORDER BY name").fetchall()


def _cell(week, tasks, task_h, pm_h, capacity):
    hours = round(task_h + pm_h, 1)
    return {"week": week, "tasks": tasks, "task_hours": round(task_h, 1), "pm_hours": pm_h, "hours": hours,
            "pct": round(100 * hours / capacity), "level": level(hours, capacity)}


def build(weeks=WEEKS, limit=None):
    """Everyone on staff who can take work, with `weeks` weeks from this one, busiest first."""
    db = get_db()
    first = monday(local_today())
    starts = [(first + timedelta(days=7 * i)).isoformat() for i in range(weeks)]
    tasks, managed = _task_hours(db, first, weeks), _managed(db)
    pm_each, default_cap = policy("pm_hours_per_rollout"), policy("capacity_hours_per_week")
    people = []
    for u in _staff(db):
        mine = tasks.get(u["id"]) or [[0.0, 0]] * weeks
        if u["role"] == "Viewer" and not any(h for h, _ in mine) and not managed.get(u["id"]):
            continue   # a viewer with nothing on their plate is not a person to plan with
        capacity = u["capacity_hours"] or default_cap
        pm_h = pm_each * managed.get(u["id"], 0)
        cells = [_cell(starts[i], mine[i][1], mine[i][0], pm_h, capacity) for i in range(weeks)]
        people.append({"id": u["id"], "name": u["name"], "role": u["role"], "avatar_url": avatar_url(u), "capacity": capacity,
                       "custom_capacity": u["capacity_hours"] is not None, "rollouts": managed.get(u["id"], 0), "weeks": cells,
                       "peak": max(c["pct"] for c in cells)})
    people.sort(key=lambda p: (-p["peak"], p["name"].lower()))
    return {"today": local_today().isoformat(), "weeks": starts, "capacity_default": default_cap, "warn_pct": policy("workload_warn_pct"),
            "over": sum(1 for p in people if any(c["level"] == "over" for c in p["weeks"])),
            "heavy": sum(1 for p in people if any(c["level"] == "warn" for c in p["weeks"]) and not any(c["level"] == "over" for c in p["weeks"])),
            "people": people[:limit] if limit else people}


def week_of(day):
    """{user_id: {hours, capacity, level}} for the week holding `day` (a date): the task picker's "34 h that week"."""
    db = get_db()
    start = monday(day)
    tasks, managed = _task_hours(db, start, 1), _managed(db)
    pm_each, default_cap = policy("pm_hours_per_rollout"), policy("capacity_hours_per_week")
    out = {}
    for u in _staff(db):
        capacity = u["capacity_hours"] or default_cap
        hours, n = (tasks.get(u["id"]) or [[0.0, 0]])[0]
        cell = _cell(start.isoformat(), n, hours, pm_each * managed.get(u["id"], 0), capacity)
        out[u["id"]] = {"hours": cell["hours"], "capacity": capacity, "level": cell["level"]}
    return {"week": start.isoformat(), "people": out}


def holds(db, user_ids):
    """{user_id: {tasks, rollouts, raid}} the open work a person holds: what a hand-over would move."""
    marks = ",".join("?" for _ in user_ids) or "NULL"
    out = {u: {"tasks": 0, "rollouts": 0, "raid": 0} for u in user_ids}
    live = f"p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}"
    for key, sql in (
        ("tasks", f"SELECT t.assignee_id, COUNT(*) FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.done = 0 AND t.assignee_id IN ({marks}) AND {live} GROUP BY 1"),
        ("rollouts", f"SELECT p.owner_id, COUNT(*) FROM projects p WHERE p.owner_id IN ({marks}) AND {live} GROUP BY 1"),
        ("raid", f"SELECT r.owner_id, COUNT(*) FROM raid_items r JOIN projects p ON p.id = r.project_id WHERE r.status NOT IN ('closed', 'decided') AND r.owner_id IN ({marks}) AND {live} GROUP BY 1"),
    ):
        for uid, n in db.execute(sql, list(user_ids)):
            out[uid][key] = n
    return out
