"""Task dependencies: finish-to-start links between tasks of one rollout.

`task_links` (task_id, depends_on_task_id) says "task_id waits on
depends_on_task_id". A task with an open predecessor is *blocked*: it cannot
be ticked (an Admin may, audited as an override), the flow shows what it
waits on and how late that is, and the plan's forecast follows the chain
(services/plan.py). Links stay inside one rollout and never loop; both are
checked on save. A link dies with either of its tasks, and with the project.
"""
from datetime import date

from db import get_db
from policies import local_today


def parse_day(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def links_for(project_id, db=None):
    """{task id: [the task ids it waits on]} for one rollout."""
    out = {}
    for task_id, dep in (db or get_db()).execute(
            "SELECT task_id, depends_on_task_id FROM task_links WHERE project_id = ? ORDER BY id", (project_id,)):
        out.setdefault(task_id, []).append(dep)
    return out


def clean_ids(raw):
    """The posted waits_on as a list of distinct ints, or ValueError."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list) or any(isinstance(x, bool) or not isinstance(x, (int, str)) or not str(x).isdigit() for x in raw):
        raise ValueError("Send waits_on as a list of task ids")
    return list(dict.fromkeys(int(x) for x in raw))


def check(db, project_id, task_id, deps):
    """Refuse a link that leaves the rollout, points at itself or makes a loop.
    task_id None: a task not saved yet (nothing waits on it, so no loop)."""
    if not deps:
        return
    if task_id in deps:
        raise ValueError("A task cannot wait on itself")
    marks = ",".join("?" for _ in deps)
    titles = {r[0]: r[1] for r in db.execute(f"SELECT id, title FROM tasks WHERE project_id = ? AND id IN ({marks})", (project_id, *deps))}
    if len(titles) != len(deps):
        raise ValueError("A task can only wait on tasks of the same rollout")
    if task_id is None:
        return
    graph = links_for(project_id, db)
    graph.pop(task_id, None)   # its own links are being replaced
    for dep in deps:
        seen, stack = set(), [dep]
        while stack:
            at = stack.pop()
            if at == task_id:
                raise ValueError(f"{titles[dep]} already waits on this task, directly or through others: that would be a loop")
            if at not in seen:
                seen.add(at)
                stack.extend(graph.get(at, ()))


def replace(db, project_id, task_id, deps):
    """Set what a task waits on (check() first). The caller commits."""
    db.execute("DELETE FROM task_links WHERE task_id = ?", (task_id,))
    db.executemany("INSERT INTO task_links (project_id, task_id, depends_on_task_id) VALUES (?, ?, ?)",
                   [(project_id, task_id, d) for d in deps])


def add_successors(db, project_id, task_id, successors):
    """Make each of `successors` (tasks of this rollout) wait on task_id too, keeping
    what they already wait on: the undo of a deleted task gives back the links of
    the tasks that waited on it. Raises ValueError (nothing written for that one)
    on a task of another rollout or a loop. The caller commits, or rolls back."""
    if not successors:
        return
    marks = ",".join("?" for _ in successors)
    if db.execute(f"SELECT COUNT(*) FROM tasks WHERE project_id = ? AND id IN ({marks})", (project_id, *successors)).fetchone()[0] != len(successors):
        raise ValueError("Only tasks of the same rollout can wait on this one")
    for b in successors:
        deps = list(dict.fromkeys(links_for(project_id, db).get(b, []) + [task_id]))
        check(db, project_id, b, deps)
        replace(db, project_id, b, deps)


def forget(db, task_id):
    """A deleted task's links, both ways: what waited on it is free."""
    db.execute("DELETE FROM task_links WHERE task_id = ? OR depends_on_task_id = ?", (task_id, task_id))


def open_predecessors(db, task_id):
    """The open tasks this one waits on: [{id, title, due_date}]."""
    return [dict(r) for r in db.execute(
        "SELECT t.id, t.title, t.due_date FROM task_links l JOIN tasks t ON t.id = l.depends_on_task_id "
        "WHERE l.task_id = ? AND t.done = 0 ORDER BY t.id", (task_id,))]


def blocked_by(tasks, links, today=None):
    """{task id: [{id, title, late_by}]}: each open task's open predecessors,
    with how many days past its date each one is (0 when not late)."""
    today = today or local_today()
    by_id = {t["id"]: t for t in tasks}
    out = {}
    for tid, deps in links.items():
        t = by_id.get(tid)
        if not t or t["done"]:
            continue
        waits = []
        for d in deps:
            p = by_id.get(d)
            if p and not p["done"]:
                due = parse_day(p["due_date"])
                waits.append({"id": p["id"], "title": p["title"], "late_by": max(0, (today - due).days) if due else 0})
        if waits:
            out[tid] = waits
    return out


# An outsider (partner or customer) sees only their own tasks: what else holds one
# of theirs is said without its title, so an internal task's name never reaches them.
HIDDEN_WAIT = "work the team has not finished yet"


def outsider_cut(waits, visible):
    """`waits` (a blocked_by list) as an outsider reads it: the predecessors in
    `visible` (their own task ids) by name, every other one as one nameless line."""
    shown = [w for w in waits if w["id"] in visible]
    if len(shown) < len(waits):
        shown.append({"id": 0, "title": HIDDEN_WAIT, "late_by": 0})
    return shown


def chained_finish(tasks, links, today=None):
    """{open task id: (earliest finish, the late task at the root of its chain
    or None)}. A late task finishes today at the earliest; a task finishes no
    sooner than each open predecessor's finish plus the gap their dates had,
    so a predecessor's slip carries down the chain. Undated tasks pass a
    predecessor's finish on unchanged."""
    today = today or local_today()
    by_id = {t["id"]: t for t in tasks}
    memo = {}

    def finish(tid, path):
        if tid in memo:
            return memo[tid]
        t = by_id[tid]
        due = parse_day(t["due_date"])
        best, root = (max(due, today), t if due < today else None) if due else (None, None)
        for d in links.get(tid, ()):
            p = by_id.get(d)
            if not p or p["done"] or d in path:   # a loop saved before the check existed is cut, never followed
                continue
            p_end, p_root = finish(d, path | {tid})
            if p_end is None:
                continue
            p_due = parse_day(p["due_date"])
            cand = date.fromordinal(p_end.toordinal() + max(0, (due - p_due).days)) if due and p_due else p_end
            if best is None or cand > best:
                best, root = cand, p_root or root
        memo[tid] = (best, root)
        return memo[tid]

    return {t["id"]: finish(t["id"], frozenset()) for t in tasks if not t["done"]}
