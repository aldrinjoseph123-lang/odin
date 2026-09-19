"""Stage-list operations, shared by templates (Settings) and single projects.

Names are the key everywhere — projects.stage and status_notes.stage hold
names — so a rename on a project cascades into that project's rows and its
history keeps whatever the stage was called when each note was written.
Every function returns an error message for the user, or None on success.
"""
from db import get_db

SCOPES = {
    "template": ("stage_template_stages", "template_id"),
    "project": ("project_stages", "project_id"),
}


def _table(scope):
    return SCOPES[scope]


def list_stages(scope, scope_id):
    table, col = _table(scope)
    return get_db().execute(f"SELECT * FROM {table} WHERE {col} = ? ORDER BY position", (scope_id,)).fetchall()


def add_stage(scope, scope_id, name):
    """Insert *before* the terminal stage. The last stage means "closed"
    everywhere, so appending would silently reopen finished work."""
    table, col = _table(scope)
    name = (name or "").strip()[:80]
    if not name:
        return "Stage name required"
    db = get_db()
    if db.execute(f"SELECT 1 FROM {table} WHERE {col} = ? AND name = ?", (scope_id, name)).fetchone():
        return "Stage already exists"
    last = db.execute(f"SELECT MAX(position) FROM {table} WHERE {col} = ?", (scope_id,)).fetchone()[0]
    if last is None:
        db.execute(f"INSERT INTO {table} ({col}, name, position) VALUES (?, ?, 0)", (scope_id, name))
    else:
        db.execute(f"UPDATE {table} SET position = position + 1 WHERE {col} = ? AND position = ?", (scope_id, last))
        db.execute(f"INSERT INTO {table} ({col}, name, position) VALUES (?, ?, ?)", (scope_id, name, last))
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
    if scope == "project":
        db.execute("UPDATE projects SET stage = ? WHERE id = ? AND stage = ?", (new_name, scope_id, row["name"]))
        db.execute("UPDATE status_notes SET stage = ? WHERE project_id = ? AND stage = ?", (new_name, scope_id, row["name"]))
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
    if db.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (scope_id,)).fetchone()[0] <= 1:
        return "Cannot delete the last remaining stage"
    if scope == "project":
        current = db.execute("SELECT stage FROM projects WHERE id = ?", (scope_id,)).fetchone()
        if current and current["stage"] == row["name"]:
            return f"Cannot delete '{row['name']}' — the project is in it"
    db.execute(f"DELETE FROM {table} WHERE id = ?", (stage_id,))
    db.commit()
    return None


def set_slas(scope, scope_id, form):
    """Expected days per stage from a form of sla::<id> fields. Blank clears —
    an unmeasured stage, not a zero-day target."""
    table, col = _table(scope)
    db = get_db()
    updates = []
    for stage in list_stages(scope, scope_id):
        raw = (form.get(f"sla::{stage['id']}", "") or "").strip()
        if not raw:
            updates.append((None, stage["id"]))
            continue
        try:
            days = int(raw)
        except ValueError:
            return f"SLA for {stage['name']} must be a whole number of days"
        if days < 1:
            return f"SLA for {stage['name']} must be at least 1 day"
        updates.append((days, stage["id"]))
    for days, stage_id in updates:
        db.execute(f"UPDATE {table} SET sla_days = ? WHERE id = ?", (days, stage_id))
    db.commit()
    return None
