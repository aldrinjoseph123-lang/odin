"""Tasks that come with a template's stages (Settings › Rollouts & workflow).

Each `template_tasks` row hangs off a template stage: a title, the project
role it lands on (Project manager = the owner; Coordinator = the rollout's
first coordinator; Customer = its first customer contact; none or nobody in
that role = unassigned), a due offset in days from the stage's start (working
days when the workspace counts them, as stage lengths do), an optional
estimate, and at most one other template task it waits on. A rollout created
from the template gets real tasks and task_links from them (instantiate);
editing the template later never touches rollouts already created.
"""
from datetime import date

from db import get_db, insert_task, role_holders
from policies import local_date, local_today
from services import task_links, workdays

ROLES = ("Project manager", "Coordinator", "Customer")
MAX_OFFSET = 365


def for_template(template_id, db=None):
    """The template's tasks, in stage order then their own."""
    return [dict(r) for r in (db or get_db()).execute(
        "SELECT tt.id, tt.stage_id, tt.title, tt.role, tt.offset_days, tt.waits_on_id, tt.estimate_hours FROM template_tasks tt "
        "JOIN stage_template_stages s ON s.id = tt.stage_id WHERE s.template_id = ? ORDER BY s.position, tt.position, tt.id", (template_id,))]


def _hours(raw, title):
    if raw in (None, ""):
        return None
    try:
        h = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{title}: estimate hours must be a number") from None
    if isinstance(raw, bool) or not 0 < h <= 999:
        raise ValueError(f"{title}: estimate hours between 0 and 999")
    return round(h, 1)


def clean_hours(raw):
    """A task's estimate in hours (None for none), or ValueError."""
    return _hours(raw, "Estimate")


def validate(template_id, items, db=None):
    """Clean rows from the editor's list, or ValueError. Each item: key (any
    text, unique), stage_id (one of this template's stages), title, role,
    offset_days, waits_on (another item's key or null), estimate_hours."""
    db = db or get_db()
    stages = {r[0] for r in db.execute("SELECT id FROM stage_template_stages WHERE template_id = ?", (template_id,))}
    if not isinstance(items, list):
        raise ValueError("Send the tasks as a list")
    if len(items) > 200:
        raise ValueError("At most 200 tasks per template")
    out, keys = [], set()
    for it in items:
        if not isinstance(it, dict):
            raise ValueError("Send each task as an object")
        key = str(it.get("key") or "")
        title = it.get("title")
        if not key or key in keys:
            raise ValueError("Each task needs its own key; reload and try again")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Every task needs a title")
        title = title.strip()
        if len(title) > 200:
            raise ValueError(f"{title[:40]}…: at most 200 characters")
        stage = it.get("stage_id")
        if isinstance(stage, bool) or stage not in stages:
            raise ValueError(f"{title}: pick one of this template's stages")
        role = it.get("role") or None
        if role is not None and role not in ROLES:
            raise ValueError(f"{title}: the role is the project manager, a coordinator, the customer or nobody")
        offset = it.get("offset_days") or 0
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= MAX_OFFSET:
            raise ValueError(f"{title}: offset days from 0 to {MAX_OFFSET}")
        waits = it.get("waits_on")
        keys.add(key)
        out.append({"key": key, "stage_id": stage, "title": title, "role": role, "offset_days": offset,
                    "waits_on": str(waits) if waits not in (None, "") else None, "estimate_hours": _hours(it.get("estimate_hours"), title)})
    by_key = {r["key"]: r for r in out}
    for r in out:
        if r["waits_on"] is None:
            continue
        if r["waits_on"] not in by_key or r["waits_on"] == r["key"]:
            raise ValueError(f"{r['title']}: it can wait on another task of this template only")
        seen, at = {r["key"]}, r["waits_on"]   # one predecessor each: the chain is a line, a loop comes back round
        while at is not None:
            if at in seen:
                raise ValueError(f"{r['title']}: that would make a loop of tasks waiting on each other")
            seen.add(at)
            at = by_key[at]["waits_on"]
    return out


def save(template_id, items):
    """Make the template's tasks the editor's list. A row whose key is the id of
    one of this template's tasks keeps that id (rules point at it: services/rules.py
    add_task); the others are added, and tasks left out are deleted. Returns the count."""
    db = get_db()
    rows = validate(template_id, items, db)
    have = {t["id"] for t in for_template(template_id, db)}
    db.execute("UPDATE template_tasks SET waits_on_id = NULL WHERE id IN (SELECT tt.id FROM template_tasks tt "
               "JOIN stage_template_stages s ON s.id = tt.stage_id WHERE s.template_id = ?)", (template_id,))
    ids = {}
    for position, r in enumerate(rows):
        vals = (r["stage_id"], r["title"], r["role"], r["offset_days"], r["estimate_hours"], position)
        old = int(r["key"]) if r["key"].isdigit() and int(r["key"]) in have else None
        if old is not None and old not in ids.values():
            db.execute("UPDATE template_tasks SET stage_id = ?, title = ?, role = ?, offset_days = ?, estimate_hours = ?, position = ? WHERE id = ?", (*vals, old))
            ids[r["key"]] = old
        else:
            ids[r["key"]] = db.execute(
                "INSERT INTO template_tasks (stage_id, title, role, offset_days, estimate_hours, position) VALUES (?, ?, ?, ?, ?, ?)", vals).lastrowid
    gone = have - set(ids.values())
    if gone:
        db.execute(f"DELETE FROM template_tasks WHERE id IN ({','.join('?' * len(gone))})", tuple(gone))
    for r in rows:
        if r["waits_on"]:
            db.execute("UPDATE template_tasks SET waits_on_id = ? WHERE id = ?", (ids[r["waits_on"]], ids[r["key"]]))
    db.commit()
    return len(rows)


def make_task(db, project, tt, stage, start, created_by, customer=True, created_at=None):
    """One real task from a template task: due `offset_days` after `start` (working days when the
    workspace counts them), on whoever holds its role. `customer=False` leaves a task meant for the
    customer unassigned (a rule never reaches the customer). The caller commits. Returns (task id, due date)."""
    role = tt["role"]
    if role == "Project manager":
        who = project["owner_id"]
    elif role == "Coordinator" or (role == "Customer" and customer):
        who = next(iter(role_holders(project["id"], role, db, active=True)), None)
    else:
        who = None
    due = workdays.add(start, tt["offset_days"], workdays.calendar(db)).isoformat()
    return insert_task(db, project["id"], tt["title"], created_by, created_at, assignee_id=who, due_date=due, stage=stage, estimate_hours=tt["estimate_hours"]), due


def instantiate(db, template_id, project_id, created_by):
    """Give a new rollout the template's tasks and links. Due dates run from
    each stage's planned start, else the rollout's start (else today), plus
    the offset. The caller commits. Returns the number of tasks made."""
    project = db.execute("SELECT id, owner_id, start_date, created_at FROM projects WHERE id = ?", (project_id,)).fetchone()
    tasks = for_template(template_id, db)
    if not project or not tasks:
        return 0
    names = {r[0]: r[1] for r in db.execute("SELECT id, name FROM stage_template_stages WHERE template_id = ?", (template_id,))}
    starts = {r[0]: r[1] for r in db.execute("SELECT name, plan_start FROM project_stages WHERE project_id = ?", (project_id,))}
    begin = local_date(project["start_date"]) or local_date(project["created_at"]) or local_today()
    made = {}
    for t in tasks:
        stage = names[t["stage_id"]]
        made[t["id"]] = make_task(db, project, t, stage, date.fromisoformat(starts[stage]) if starts.get(stage) else begin, created_by)[0]
    for t in tasks:
        if t["waits_on_id"] in made:
            task_links.replace(db, project_id, made[t["id"]], [made[t["waits_on_id"]]])
    return len(made)
