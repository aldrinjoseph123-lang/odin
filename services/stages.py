"""Stage-list operations, shared by templates (Settings) and single projects.

Names are the key everywhere — projects.stage and status_notes.stage hold
names — so a rename on a project cascades into that project's rows and its
history keeps whatever the stage was called when each note was written.
Every function returns an error message for the user, or None on success.
"""
from constants import SIGNOFF_STAGE
from db import get_db

MAX_SLA_DAYS = 365

SCOPES = {
    "template": ("stage_template_stages", "template_id"),
    "project": ("project_stages", "project_id"),
}


def _table(scope):
    return SCOPES[scope]


def _closes_unsigned(scope, scope_id, names):
    """A stage-list edit must not close the project by making its current
    stage the terminal one (system map: sign-off gate) — the same rule a
    stage move obeys."""
    if scope != "project" or not names:
        return None
    from services import signoff
    project = get_db().execute("SELECT * FROM projects WHERE id = ?", (scope_id,)).fetchone()
    if project is None or project["stage"] != names[-1] or names[-1] == list_stages(scope, scope_id)[-1]["name"]:
        return None   # not in the new terminal stage, or the terminal stage is unchanged (closed before)
    return signoff.gate(project, names[-1], terminal=names[-1])


def list_stages(scope, scope_id):
    table, col = _table(scope)
    return get_db().execute(f"SELECT * FROM {table} WHERE {col} = ? ORDER BY position", (scope_id,)).fetchall()


def add_stage(scope, scope_id, name):
    """Insert *before* the terminal stage — and before the Sign-off stage
    that precedes it. The last stage means "closed" everywhere, so appending
    would silently reopen finished work; and the sign-off comes after the work."""
    table, col = _table(scope)
    name = (name or "").strip()[:80]
    if not name:
        return "Stage name required"
    db = get_db()
    if db.execute(f"SELECT 1 FROM {table} WHERE {col} = ? AND name = ?", (scope_id, name)).fetchone():
        return "Stage already exists"
    rows = db.execute(f"SELECT name, position FROM {table} WHERE {col} = ? ORDER BY position", (scope_id,)).fetchall()
    if not rows:
        db.execute(f"INSERT INTO {table} ({col}, name, position) VALUES (?, ?, 0)", (scope_id, name))
    else:
        tail = 2 if len(rows) >= 2 and rows[-2]["name"] == SIGNOFF_STAGE else 1
        at = rows[-tail]["position"]
        db.execute(f"UPDATE {table} SET position = position + 1 WHERE {col} = ? AND position >= ?", (scope_id, at))
        db.execute(f"INSERT INTO {table} ({col}, name, position) VALUES (?, ?, ?)", (scope_id, name, at))
    db.commit()
    return None


def rename_stage(scope, scope_id, stage_id, new_name):
    table, col = _table(scope)
    new_name = (new_name or "").strip()[:80]
    db = get_db()
    row = db.execute(f"SELECT * FROM {table} WHERE id = ? AND {col} = ?", (stage_id, scope_id)).fetchone()
    if row is None:
        return "Stage not found"
    if not new_name:
        return "Stage name required"
    if db.execute(f"SELECT 1 FROM {table} WHERE {col} = ? AND name = ? AND id != ?", (scope_id, new_name, stage_id)).fetchone():
        return "Stage name already in use"
    db.execute(f"UPDATE {table} SET name = ? WHERE id = ?", (new_name, stage_id))
    if scope == "project":   # every row that names the stage (B5)
        db.execute("UPDATE projects SET stage = ? WHERE id = ? AND stage = ?", (new_name, scope_id, row["name"]))
        for named in ("status_notes", "tasks", "stage_approvals", "raid_items", "plan_changes"):
            db.execute(f"UPDATE {named} SET stage = ? WHERE project_id = ? AND stage = ?", (new_name, scope_id, row["name"]))
        db.execute("UPDATE status_notes SET prev_stage = ? WHERE project_id = ? AND prev_stage = ?", (new_name, scope_id, row["name"]))
    db.commit()
    return None


def move_stage(scope, scope_id, stage_id, direction):
    table, col = _table(scope)
    db = get_db()
    stages = list_stages(scope, scope_id)
    index = next((i for i, s in enumerate(stages) if s["id"] == stage_id), None)
    if index is None:
        return "Stage not found"
    swap = index - 1 if direction == "up" else index + 1
    if not 0 <= swap < len(stages):
        return None
    a, b = stages[index], stages[swap]
    names = [s["name"] for s in stages]
    names[index], names[swap] = names[swap], names[index]
    if scope == "project" and names[-1] != stages[-1]["name"]:
        project = db.execute("SELECT stage FROM projects WHERE id = ?", (scope_id,)).fetchone()
        if project and project["stage"] == stages[-1]["name"]:   # closed: a reorder would reopen it with no note or audit (sim L-6)
            return "The project is closed. Move it back to a working stage before changing which stage is last"
    refused = _closes_unsigned(scope, scope_id, names)
    if refused:
        return refused
    db.execute(f"UPDATE {table} SET position = ? WHERE id = ?", (b["position"], a["id"]))
    db.execute(f"UPDATE {table} SET position = ? WHERE id = ?", (a["position"], b["id"]))
    db.commit()
    return None


def delete_stage(scope, scope_id, stage_id):
    table, col = _table(scope)
    db = get_db()
    row = db.execute(f"SELECT * FROM {table} WHERE id = ? AND {col} = ?", (stage_id, scope_id)).fetchone()
    if row is None:
        return "Stage not found"
    if db.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (scope_id,)).fetchone()[0] <= 2:
        # one stage would be the finish line alone: a project born closed, never signed off (D13/R14)
        return "A stage list needs at least two stages: the work and the finish"
    if scope == "project":
        current = db.execute("SELECT stage FROM projects WHERE id = ?", (scope_id,)).fetchone()
        if current and current["stage"] == row["name"]:
            return f"Cannot delete '{row['name']}' — the project is in it"
        refused = _closes_unsigned(scope, scope_id, [s["name"] for s in list_stages(scope, scope_id) if s["id"] != stage_id])
        if refused:
            return refused
    db.execute(f"DELETE FROM {table} WHERE id = ?", (stage_id,))
    if scope == "project":   # its tasks fall back to "current stage" rather than vanish
        db.execute("UPDATE tasks SET stage = NULL WHERE project_id = ? AND stage = ?", (scope_id, row["name"]))
    db.commit()
    return None


def set_slas(scope, scope_id, form):
    """Expected days per stage from a form of sla::<id> fields. Blank clears —
    an unmeasured stage, not a zero-day target. A stage the form does not
    name keeps its SLA."""
    table, col = _table(scope)
    db = get_db()
    updates = []
    for stage in list_stages(scope, scope_id):
        if f"sla::{stage['id']}" not in form:
            continue
        raw = (form.get(f"sla::{stage['id']}", "") or "").strip()
        if not raw:
            updates.append((None, stage["id"]))
            continue
        try:
            days = int(raw)
        except ValueError:
            return f"SLA for {stage['name']} must be a whole number of days"
        if not 1 <= days <= MAX_SLA_DAYS:   # 3,000,000 broke the plan and reports; 2**70 overflowed SQLite (F-H2)
            return f"SLA for {stage['name']} must be between 1 and {MAX_SLA_DAYS} days"
        updates.append((days, stage["id"]))
    for days, stage_id in updates:
        db.execute(f"UPDATE {table} SET sla_days = ? WHERE id = ?", (days, stage_id))
    db.commit()
    return None
