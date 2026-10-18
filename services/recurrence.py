"""Repeating tasks (Odin 2.0).

A repeating task carries `recurrence` (weekly / fortnightly / monthly) and
`recur_until` (a last day, or 'stage': until the task's stage is done). When
it is ticked, or its due day passes, the next occurrence is made: once, ever
(`recur_spawned` is claimed before the row is added, and `recur_from` is
unique), with the same kind of ask. A neglected one does not pile up: while
an earlier occurrence is open, a later one passing makes no further copy. The tick route calls `spawn_next` at once; the scheduler's nightly
housekeeping calls `run_recurring` for the ones nobody ticked.
"""
import calendar
from datetime import date, datetime, timedelta

from db import PROJECT_OPEN_SQL, get_db, stage_rows
from policies import local_today

RECURRENCES = {"weekly": 7, "fortnightly": 14, "monthly": None}


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


def _open_earlier(db, task_id):
    """An earlier occurrence of this repeating task (up its recur_from chain) is still open."""
    return db.execute(
        "WITH RECURSIVE up(id) AS (SELECT recur_from FROM tasks WHERE id = ? "
        "UNION SELECT t.recur_from FROM tasks t JOIN up ON t.id = up.id WHERE t.recur_from IS NOT NULL) "
        "SELECT 1 FROM tasks WHERE id IN (SELECT id FROM up) AND done = 0 LIMIT 1", (task_id,)).fetchone() is not None


def spawn_next(db, task_id, today=None, actor=None):
    """Make the next occurrence of a repeating task, once. Returns its id, or
    None: not repeating, already made, the rollout is closed or gone, the last
    day has passed, or the stage is done. The first call claims the task, so a
    tick and the nightly pass racing each other make one copy between them."""
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None or not task["recurrence"] or task["recurrence"] not in RECURRENCES or not task["due_date"]:
        return None
    if not task["done"] and _open_earlier(db, task_id):
        # neglected: an earlier occurrence is still open, so this one passing makes no third. It is not
        # claimed: once the earlier one is done, this one spawns when it passes or is ticked
        return None
    project = db.execute(f"SELECT p.* FROM projects p WHERE p.id = ? AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}", (task["project_id"],)).fetchone()
    if project is None:   # not claimed: once the rollout reopens, the nightly pass makes it
        return None
    if db.execute("UPDATE tasks SET recur_spawned = 1 WHERE id = ? AND recur_spawned = 0", (task_id,)).rowcount == 0:
        return None
    today = today or local_today(db)
    nxt = next_due(date.fromisoformat(task["due_date"]), task["recurrence"], today)
    until = task["recur_until"]
    if (until == "stage" and _stage_done(db, project["id"], task["stage"], project["stage"])) or (until and until != "stage" and nxt.isoformat() > until):
        db.commit()
        return None
    assignee = task["assignee_id"] if task["assignee_id"] and db.execute("SELECT 1 FROM users WHERE id = ? AND active = 1", (task["assignee_id"],)).fetchone() else None
    cur = db.execute(   # the same ask each time: a tick, an upload of one category, or the same form (services/asks.py)
        "INSERT OR IGNORE INTO tasks (project_id, title, assignee_id, due_date, created_at, created_by, stage, done, estimate_hours, recurrence, recur_until, recur_from, "
        "kind, ask_category, ask_form) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)",
        (task["project_id"], task["title"], assignee, nxt.isoformat(), datetime.utcnow().isoformat(), "Odin (repeats)", task["stage"],
         task["estimate_hours"], task["recurrence"], until, task_id, task["kind"], task["ask_category"], task["ask_form"]))
    if cur.rowcount:   # the next one waits on what this one waited on (services/task_links.py); it has no successors, so no loop
        db.execute("INSERT OR IGNORE INTO task_links (project_id, task_id, depends_on_task_id) "
                   "SELECT project_id, ?, depends_on_task_id FROM task_links WHERE task_id = ?", (cur.lastrowid, task_id))
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
