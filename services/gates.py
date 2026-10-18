"""Stage gates: what must be true before a rollout leaves a stage.

Each stage, on a template and on a rollout's own list (project_stages), may
ask that all its tasks are done (`gate_tasks`) and that documents of some
categories are on the rollout (`required_docs`, a JSON list of category
names). A rollout copies them from its template with the stage list
(db.copy_template_stages); its project manager edits them per rollout like
the SLAs (services/stages.set_gates).

`blocked()` is the one check. Every stage-move path goes through
routes/projects.change_stage (the API, the Kanban and Flow moves, the
vendor's guest link), which calls it next to signoff.gate(). Only a move
forward is gated, and a jump answers for every stage it leaves behind. An
Admin, or the project manager while the `gate_override` policy allows it,
may move past a gate with a typed reason; the vendor link never can.
"""
import json
from collections import Counter

from flask import session

from db import get_db
from policies import local_today, policy
from services.fmt import plural

GUEST_MESSAGE = "This stage is not finished yet. The project manager will move the rollout on once its work is done."


def required_docs(row):
    """A stage row's required document categories, as a list."""
    try:
        value = json.loads(row["required_docs"] or "[]")
    except (TypeError, ValueError):
        return []
    return [c for c in value if isinstance(c, str)] if isinstance(value, list) else []


def blocked(project, new_stage, rows=None):
    """What stops `project` moving to `new_stage`: a list of
    {stage, kind: "tasks" | "document", count | category, text}, empty when
    nothing does. `rows` are its project_stages rows when the caller has them."""
    db = get_db()
    pid = project["id"]
    if rows is None:
        rows = db.execute("SELECT * FROM project_stages WHERE project_id = ? ORDER BY position", (pid,)).fetchall()
    names = [r["name"] for r in rows]
    if project["stage"] not in names or new_stage not in names:
        return []
    passed = rows[names.index(project["stage"]):names.index(new_stage)]   # empty for a move back
    out = []
    gated = {r["name"] for r in passed if r["gate_tasks"]}
    if gated:
        # a task with no stage, or a stage since removed, belongs to the current stage (as the Flow shows it).
        # A repeating task (services/recurrence.py) always has its next occurrence open, so it holds the
        # gate only while that occurrence is overdue (its day has passed and it is not done): holds_gate()
        today = local_today(db).isoformat()
        open_in, overdue = Counter(), []
        for t in db.execute("SELECT stage, title, due_date, recurrence FROM tasks WHERE project_id = ? AND done = 0 ORDER BY due_date, id", (pid,)):
            if holds_gate(t, today):
                stage = t["stage"] if t["stage"] in names else project["stage"]
                if t["recurrence"]:
                    overdue.append((stage, t["title"]))
                else:
                    open_in[stage] += 1
        for r in passed:
            if r["name"] not in gated:
                continue
            where = "" if r["name"] == project["stage"] else f" in {r['name']}"
            if n := open_in[r["name"]]:
                out.append({"stage": r["name"], "kind": "tasks", "count": n, "text": f"{n} open {plural(n, 'task')}{where}"})
            out += [{"stage": s, "kind": "tasks", "count": 1, "text": f"{title} is overdue{where}"} for s, title in overdue if s == r["name"]]
    wanted = {}
    for r in passed:
        for c in required_docs(r):
            wanted.setdefault(c, r["name"])
    if wanted:
        # a category since deleted in Settings can never be uploaded: it no longer holds the gate
        known = {r[0] for r in db.execute("SELECT name FROM doc_categories")}
        # an outside upload held for review (services/doc_review.py) does not count until it is accepted
        have, held = set(), set()
        for r in db.execute("SELECT DISTINCT category, review_status FROM documents WHERE project_id = ? AND deleted_at IS NULL", (pid,)):
            if r["review_status"] == "accepted":
                have.add(r["category"])
            else:
                held.add(r["category"])
        out += [{"stage": s, "kind": "document", "category": c, "text": f"{c} {'awaiting review' if c in held else 'missing'}"}
                for c, s in wanted.items() if c in known and c not in have]
    return out


def holds_gate(task, today):
    """Does this open task hold its stage's gate? Yes, unless it repeats: then
    only while it is overdue. `today` is ISO; lib/format.holdsGate counts the
    same on the Flow."""
    return not task["recurrence"] or bool(task["due_date"]) and task["due_date"] < today


def summary(reasons):
    """"2 open tasks · Client PO missing"."""
    return " · ".join(r["text"] for r in reasons)


def may_override(project):
    """Admins always; the project manager while the policy says so."""
    if session.get("role") == "Admin":
        return True
    return policy("gate_override") == "admin_and_pm" and project["owner_id"] == session.get("user_id")


def override_refusal():
    return "Only an admin may move past a stage gate" if policy("gate_override") == "admin" \
        else "Only an admin or the project manager may move past a stage gate"
