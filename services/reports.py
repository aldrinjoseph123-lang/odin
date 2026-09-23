"""Project reports: drafted from what the tracker already knows, then owned
by the project manager as plain text and kept as numbered versions.

The body is plain text with two conventions the page renders: a line
starting with "# " is a heading, a line starting with "- " is a list item.
Everything else is a paragraph. No markup library — a report that can be
pasted into an email must survive as text.
"""
from datetime import datetime

from db import get_db, get_stage_names
from services.analytics import _parse, stage_timeline


def draft_report(project):
    """A fresh report body from the project's current state."""
    db = get_db()
    pid = project["id"]
    stages = get_stage_names(pid)
    notes = db.execute("SELECT * FROM status_notes WHERE project_id = ? ORDER BY created_at", (pid,)).fetchall()
    tasks = db.execute(
        "SELECT t.*, u.name AS assignee_name FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id "
        "WHERE t.project_id = ? ORDER BY t.done, t.due_date IS NULL, t.due_date, t.id", (pid,)
    ).fetchall()
    documents = db.execute(
        "SELECT category, filename, uploaded_at FROM documents WHERE project_id = ? AND deleted_at IS NULL ORDER BY category", (pid,)
    ).fetchall()
    now = datetime.utcnow()
    lines = [
        f"# {project['name']}",
        f"Client: {project['client']} · Project manager: {project['owner_name']} · Stage: {project['stage']}"
        + (f" · Target: {project['target_end_date']}" if project["target_end_date"] else ""),
        "",
        "# Summary",
        "(Write two or three lines on where the project stands and what happens next.)",
        "",
        "# Timeline",
    ]
    timeline = stage_timeline(project, notes, stages[0] if stages else project["stage"])
    for i, (stage, entered) in enumerate(timeline):
        left = timeline[i + 1][1] if i + 1 < len(timeline) else now
        span = round((left - entered).total_seconds() / 86400)
        lines.append(f"- {entered.date().isoformat()}  {stage}  ({span} d{'' if i + 1 < len(timeline) else ', current'})")
    remaining = stages[stages.index(project["stage"]) + 1:] if project["stage"] in stages else []
    if remaining:
        lines.append(f"- Next: {' → '.join(remaining)}")
    open_tasks = [t for t in tasks if not t["done"]]
    lines += ["", f"# Work ({len(tasks) - len(open_tasks)} of {len(tasks)} tasks done)"]
    for t in tasks:
        who = f" — {t['assignee_name']}" if t["assignee_name"] else ""
        due = f", due {t['due_date']}" if t["due_date"] and not t["done"] else ""
        lines.append(f"- [{'x' if t['done'] else ' '}] {t['title']}{who}{due}")
    if not tasks:
        lines.append("- No tasks recorded.")
    lines += ["", "# Progress notes"]
    for n in reversed(notes):
        lines.append(f"- {(_parse(n['created_at']) or now).date().isoformat()}  {n['stage']} · {n['author']}: {n['note']}")
    if not notes:
        lines.append("- No notes yet.")
    lines += ["", "# Documents"]
    for d in documents:
        lines.append(f"- {d['category']}: {d['filename']} ({d['uploaded_at'][:10]})")
    if not documents:
        lines.append("- No documents.")
    return "\n".join(lines)


def report_versions(project_id):
    return get_db().execute(
        "SELECT id, version, created_by, created_at, length(body) AS size FROM project_reports "
        "WHERE project_id = ? ORDER BY version DESC", (project_id,)
    ).fetchall()


def save_report(project_id, body, author):
    """Append a new version; the previous ones stay readable."""
    db = get_db()
    version = (db.execute("SELECT MAX(version) FROM project_reports WHERE project_id = ?", (project_id,)).fetchone()[0] or 0) + 1
    db.execute(
        "INSERT INTO project_reports (project_id, version, body, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (project_id, version, body, author, datetime.utcnow().isoformat()),
    )
    db.commit()
    return version


def render_blocks(body):
    """Plain text -> [(kind, text)] for the template: 'h', 'li', 'p'."""
    blocks = []
    for line in (body or "").splitlines():
        if line.startswith("# "):
            blocks.append(("h", line[2:].strip()))
        elif line.startswith("- "):
            blocks.append(("li", line[2:]))
        elif line.strip():
            blocks.append(("p", line))
    return blocks
