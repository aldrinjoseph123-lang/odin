"""Milestones and repeating tasks (Odin 2.0).

A milestone is a dated commitment of a rollout: a name, a day, optionally the
stage it belongs to, and whether the customer may see it. It is done when
someone marks it reached (done_at). Everything that draws milestones (the
calendar, the dashboard timeline, both report cuts, the sign-off draft)
reads them here, and the customer cut is made here: `items(..., customer=True)`
returns only the ones marked for the customer, and every outsider (a partner
as much as the customer) gets that cut.

A repeating task carries `recurrence` (weekly / fortnightly / monthly) and
`recur_until` (a last day, or 'stage': until the task's stage is done). When
it is ticked, or its due day passes, the next occurrence is made: once, ever
(`recur_spawned` is claimed before the row is added, and `recur_from` is
unique). The tick route calls `spawn_next` at once; the scheduler's nightly
housekeeping calls `run_recurring` for the ones nobody ticked.
"""
import calendar
from datetime import date, datetime, timedelta

from db import PROJECT_OPEN_SQL, get_db, stage_rows
from policies import local_today

RECURRENCES = {"weekly": 7, "fortnightly": 14, "monthly": None}
EVERY = {"weekly": "every week", "fortnightly": "every two weeks", "monthly": "every month"}


# ---- milestones ----------------------------------------------------------------

def _row(r, today):
    d = dict(r)
    d["customer_visible"] = bool(r["customer_visible"])
    d["done"] = r["done_at"] is not None
    d["missed"] = r["done_at"] is None and r["date"] < today
    return d


def items(project_id, customer=False, today=None):
    """A rollout's milestones, open ones first by date, then the done ones.
    `customer`: only those marked for the customer."""
    today = today or local_today().isoformat()
    rows = get_db().execute(
        "SELECT * FROM milestones WHERE project_id = ? " + ("AND customer_visible = 1 " if customer else "")
        + "ORDER BY done_at IS NOT NULL, date, id", (project_id,)).fetchall()
    return [_row(r, today) for r in rows]


def items_for(project_ids, customer=False, today=None):
    """{project id: [milestones]} for many rollouts, in one query."""
    today = today or local_today().isoformat()
    ids = list(project_ids)
    out = {i: [] for i in ids}
    if not ids:
        return out
    marks = ",".join("?" * len(ids))
    for r in get_db().execute(
            f"SELECT * FROM milestones WHERE project_id IN ({marks}) " + ("AND customer_visible = 1 " if customer else "")
            + "ORDER BY done_at IS NOT NULL, date, id", ids):
        out[r["project_id"]].append(_row(r, today))
    return out


def between(start, end, scope, customer=False):
    """The calendar's milestones: those dated start..end (ISO days) on the
    rollouts in `scope` (core.project_scope: SQL and params, aliased `p`)."""
    scope_sql, scope_params = scope
    return [{"id": r["id"], "project_id": r["project_id"], "project": r["project"], "name": r["name"], "day": r["date"], "stage": r["stage"],
             "done": 1 if r["done_at"] else 0, "customer_visible": bool(r["customer_visible"])}
            for r in get_db().execute(
                "SELECT m.*, p.name AS project FROM milestones m JOIN projects p ON p.id = m.project_id "
                f"WHERE m.date BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} " + ("AND m.customer_visible = 1 " if customer else "")
                + "ORDER BY m.date, m.id", (start, end, *scope_params))]


def clean(body, project_id, existing=None):
    """A validated dict of fields from a posted body, or raise ValueError."""
    from core import as_bool, parse_date, text_field
    from db import get_stage_names
    name = text_field(body.get("name", existing["name"] if existing else ""), 200, "Name")   # too long is said, never cut
    if not name:
        raise ValueError("Give the milestone a name")
    try:
        day = parse_date(body.get("date", existing["date"] if existing else None))
    except ValueError as exc:
        raise ValueError(f"Date: {exc}") from None
    if not day:
        raise ValueError("Pick the milestone's date")
    stage = body.get("stage", existing["stage"] if existing else None) or None
    if stage is not None and (not isinstance(stage, str) or stage not in get_stage_names(project_id)):
        raise ValueError("Pick one of this rollout's stages, or none")
    visible = body.get("customer_visible", bool(existing["customer_visible"]) if existing else False)
    if as_bool(visible) is None:
        raise ValueError("Send customer_visible as true or false")
    out = {"name": name, "date": day, "stage": stage, "customer_visible": 1 if as_bool(visible) else 0}
    if "done" in body:
        done = as_bool(body.get("done"))
        if done is None:
            raise ValueError("Send done as true or false")
        out["done"] = done
    return out


def create(project_id, fields, author):
    db = get_db()
    now = datetime.utcnow().isoformat()
    cur = db.execute(
        "INSERT INTO milestones (project_id, name, date, stage, customer_visible, done_at, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, fields["name"], fields["date"], fields["stage"], fields["customer_visible"], now if fields.get("done") else None, author, now))
    db.commit()
    return cur.lastrowid


def update(item, fields):
    """Save the fields; `done` (when sent) marks it reached now, or open again.
    Staying done keeps the first time it was reached."""
    db = get_db()
    done_at = item["done_at"]
    if "done" in fields:
        done_at = (done_at or datetime.utcnow().isoformat()) if fields["done"] else None
    db.execute("UPDATE milestones SET name = ?, date = ?, stage = ?, customer_visible = ?, done_at = ? WHERE id = ?",
               (fields["name"], fields["date"], fields["stage"], fields["customer_visible"], done_at, item["id"]))
    db.commit()


def missed_projects(project_ids, grace_days=0, today=None):
    """The rollouts (of those given) with a milestone whose day passed `grace_days`
    ago and which is not done: the alert's condition, in one query."""
    ids = list(project_ids)
    if not ids:
        return set()
    today = today or local_today()
    marks = ",".join("?" * len(ids))
    cutoff = (today - timedelta(days=grace_days or 0)).isoformat()
    return {r[0] for r in get_db().execute(
        f"SELECT DISTINCT project_id FROM milestones WHERE done_at IS NULL AND date < ? AND project_id IN ({marks})", (cutoff, *ids))}


def delivered_lines(project_id):
    """Sign-off words for the milestones reached that the customer may see
    (the sign-off is the customer's document), oldest first."""
    from policies import local_date
    from services.report_pdf import _fmt
    return [f"Milestone reached: {m['name']} ({_fmt(local_date(m['done_at']).isoformat())})"
            for m in sorted(items(project_id, customer=True), key=lambda m: m["done_at"] or "") if m["done"]]


def summary_of(list_, today=None):
    """What one row of the portfolio report says: counts, and the next open one."""
    today = today or local_today().isoformat()
    open_ = sorted((m for m in list_ if not m["done"]), key=lambda m: m["date"])
    nxt = next((m for m in open_ if m["date"] >= today), None)
    return {"total": len(list_), "done": sum(1 for m in list_ if m["done"]), "missed": sum(1 for m in open_ if m["date"] < today),
            "next": {"name": nxt["name"], "date": nxt["date"]} if nxt else None}


# ---- repeating tasks -----------------------------------------------------------

def add_months(day, n):
    """The same day-of-month n months on, clamped to the month's end (31 Jan + 1 month = 28/29 Feb)."""
    y, m = divmod(day.year * 12 + day.month - 1 + n, 12)
    return date(y, m + 1, min(day.day, calendar.monthrange(y, m + 1)[1]))


def next_due(due, recurrence, today=None):
    """The first occurrence after `due` that is not in the past: a task ticked
    weeks late (or a pass that did not run) does not leave a trail of
    already-late copies. Monthly steps count from `due`'s own day of the month."""
    today = today or local_today()
    k = 1
    while True:
        nxt = due + timedelta(days=RECURRENCES[recurrence] * k) if RECURRENCES[recurrence] else add_months(due, k)
        if nxt >= today:
            return nxt
        k += 1


def clean_repeat(form, due, stage, project_stage, existing=None):
    """(recurrence, recur_until, stage) from a posted task, or raise ValueError.
    Only the keys sent change; 'stage' for recur_until pins the task to the
    stage it is in, so 'until the stage is done' names a stage."""
    from core import parse_date
    recurrence = form.get("recurrence", existing["recurrence"] if existing else None) or None
    until = form.get("recur_until", existing["recur_until"] if existing else None) or None
    if any(v is not None and not isinstance(v, str) for v in (recurrence, until)):
        raise ValueError("Send Repeats and Repeat until as text")
    if recurrence is None:
        return None, None, stage
    if recurrence not in RECURRENCES:
        raise ValueError("A task repeats weekly, fortnightly or monthly")
    if not due:
        raise ValueError("A repeating task needs a due date")
    if until == "stage":
        return recurrence, until, stage or project_stage
    if until is not None:
        try:
            until = parse_date(until)
        except ValueError as exc:
            raise ValueError(f"Repeat until: {exc}") from None
        if until and until < due:
            raise ValueError("Repeat until must be on or after the due date")
    return recurrence, until, stage


def _stage_done(db, project_id, stage, current):
    """The task's stage is behind the rollout's current one (or no longer in its list)."""
    names = [r["name"] for r in stage_rows(project_id)]
    if stage not in names:
        return stage is not None   # a stage taken off the list is over; none named is never done
    return current in names and names.index(stage) < names.index(current)


def spawn_next(db, task_id, today=None, actor=None):
    """Make the next occurrence of a repeating task, once. Returns its id, or
    None: not repeating, already made, the rollout is closed or gone, the last
    day has passed, or the stage is done. The first call claims the task, so a
    tick and the nightly pass racing each other make one copy between them."""
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None or not task["recurrence"] or task["recurrence"] not in RECURRENCES or not task["due_date"]:
        return None
    if db.execute("UPDATE tasks SET recur_spawned = 1 WHERE id = ? AND recur_spawned = 0", (task_id,)).rowcount == 0:
        return None
    project = db.execute(f"SELECT p.* FROM projects p WHERE p.id = ? AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}", (task["project_id"],)).fetchone()
    if project is None:
        db.commit()
        return None
    today = today or local_today(db)
    nxt = next_due(date.fromisoformat(task["due_date"]), task["recurrence"], today)
    until = task["recur_until"]
    if (until == "stage" and _stage_done(db, project["id"], task["stage"], project["stage"])) or (until and until != "stage" and nxt.isoformat() > until):
        db.commit()
        return None
    assignee = task["assignee_id"] if task["assignee_id"] and db.execute("SELECT 1 FROM users WHERE id = ? AND active = 1", (task["assignee_id"],)).fetchone() else None
    cur = db.execute(
        "INSERT OR IGNORE INTO tasks (project_id, title, assignee_id, due_date, created_at, created_by, stage, done, estimate_hours, recurrence, recur_until, recur_from) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
        (task["project_id"], task["title"], assignee, nxt.isoformat(), datetime.utcnow().isoformat(), "Odin (repeats)", task["stage"],
         task["estimate_hours"], task["recurrence"], until, task_id))
    db.commit()
    if cur.rowcount == 0:
        return None
    from services.audit import audit_log
    audit_log("repeat_task", "project", project["id"], project["name"], f"{task['title'][:80]}: next due {nxt.isoformat()}", actor=actor, db=db)
    return cur.lastrowid


def run_recurring(db=None, today=None):
    """The nightly pass: the next occurrence of every repeating task that is done
    or past its due day and has none yet. Returns how many were made."""
    db = db or get_db()
    today = today or local_today(db)
    due = [r[0] for r in db.execute(
        "SELECT t.id FROM tasks t JOIN projects p ON p.id = t.project_id WHERE t.recurrence IS NOT NULL AND t.recur_spawned = 0 AND t.due_date IS NOT NULL "
        f"AND (t.done = 1 OR t.due_date < ?) AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} ORDER BY t.id", (today.isoformat(),))]
    return sum(1 for tid in due if spawn_next(db, tid, today, actor="scheduler"))
