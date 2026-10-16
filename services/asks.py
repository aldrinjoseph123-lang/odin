"""Customer self-service: the asks (Odin 2.0, workstream 4).

A task has a `kind`: a plain *task* (ticked), an *upload* (done when a
document of `tasks.ask_category` is uploaded for it) or a *form* (a few
questions in `tasks.ask_form`, JSON; done when they are answered, the answers
in `task_answers`). An *ask* is any task assigned to an external participant
(a Customer, Reseller or Contractor on the rollout): it is theirs alone. An
external sees and acts on only their own asks, never another's, never an
internal task; staff see them all, with the answers, on the rollout page and
in the internal report.

The customer may also rate the rollout when they sign the sign-off: one
question, 1 to 5, an optional comment, once per sign-off version (`csat`).
The averages are internal: People and the portfolio report, never a customer
cut.
"""
import json
import math
from datetime import datetime

from db import get_db
from policies import policy

KINDS = ("task", "upload", "form")
QUESTION_KINDS = ("text", "number", "date", "choice", "yesno")
FILE_KEY = "file"   # an upload ask's answer: the document id


# ---- the spec staff write -----------------------------------------------------------

def _text(value, limit, label):
    from core import text_field
    return text_field(value, limit, label)


def clean_questions(raw):
    """The posted questions as a clean list, or ValueError: each a label, a
    kind, choices for a choice, a required flag, and a stable key (q1, q2, …;
    a key sent back on an edit is kept, so earlier answers still match)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except ValueError:
            raise ValueError("Send the questions as a list") from None
    if not isinstance(raw, list) or not raw:
        raise ValueError("A form needs at least one question")
    cap = policy("ask_form_max_questions")
    if len(raw) > cap:
        raise ValueError(f"A form has at most {cap} questions")
    out, keys = [], set()
    for i, q in enumerate(raw, 1):
        if not isinstance(q, dict):
            raise ValueError("Send each question as an object")
        label = _text(q.get("label"), 200, f"Question {i}")
        if not label:
            raise ValueError(f"Question {i} needs its words")
        kind = q.get("kind")
        if kind not in QUESTION_KINDS:
            raise ValueError(f"Question {i}: the answer is one of {', '.join(QUESTION_KINDS)}")
        item = {"label": label, "kind": kind, "required": q.get("required") is not False}
        if kind == "choice":
            choices = q.get("choices")
            if isinstance(choices, str):
                choices = [c for c in choices.split("\n")]
            if not isinstance(choices, list):
                raise ValueError(f"Question {i}: list the choices")
            choices = list(dict.fromkeys(c for c in (_text(c, 100, f"Question {i} choice") for c in choices) if c))
            if not 2 <= len(choices) <= 20:
                raise ValueError(f"Question {i}: between 2 and 20 choices")
            item["choices"] = choices
        key = q.get("key")
        item["key"] = key if isinstance(key, str) and key.startswith("q") and key[1:].isdigit() and key not in keys else None
        keys.add(item["key"])
        out.append(item)
    taken = {q["key"] for q in out if q["key"]}
    n = 0
    for q in out:
        while not q["key"]:
            n += 1
            q["key"] = f"q{n}" if f"q{n}" not in taken else None
        taken.add(q["key"])
    return out


def clean_spec(form, current=None):
    """(kind, ask_category, ask_form JSON) from a posted task, or ValueError.
    `current`: the task's row on an edit, so an edit that leaves the kind out
    keeps it."""
    from db import get_doc_category_names
    if "kind" not in form and current is not None:
        return current["kind"] or "task", current["ask_category"], current["ask_form"]
    kind = form.get("kind") or "task"
    if kind not in KINDS:
        raise ValueError(f"Kind is one of: {', '.join(KINDS)}")
    if kind == "upload":
        category = form.get("ask_category")
        if category not in get_doc_category_names():
            raise ValueError("Pick the kind of document to ask for")
        return kind, category, None
    if kind == "form":
        return kind, None, json.dumps(clean_questions(form.get("questions")))
    return kind, None, None


def questions(task):
    try:
        value = json.loads(task["ask_form"] or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


# ---- answers -------------------------------------------------------------------------

def clean_answers(qs, raw):
    """{key: value as stored text} for a form, each checked by its kind, or
    ValueError naming the question. A required question must be answered."""
    from core import parse_date
    if not isinstance(raw, dict):
        raise ValueError("Send the answers as an object")
    out = {}
    for q in qs:
        v = raw.get(q["key"])
        if isinstance(v, str):
            v = v.strip()
        if v in (None, ""):
            if q.get("required", True):
                raise ValueError(f"Answer: {q['label']}")
            continue
        kind, label = q["kind"], q["label"]
        if kind == "text":
            v = _text(v, 2000, label)
        elif kind == "number":
            try:
                n = float(v) if not isinstance(v, bool) else math.nan
            except (TypeError, ValueError):
                n = math.nan
            if not math.isfinite(n) or abs(n) > 1e12:
                raise ValueError(f"{label}: a number")
            v = str(int(n)) if n == int(n) else str(n)
        elif kind == "date":
            try:
                v = parse_date(v)
            except ValueError as exc:
                raise ValueError(f"{label}: {exc}") from None
        elif kind == "choice":
            if v not in q.get("choices", []):
                raise ValueError(f"{label}: pick one of the choices")
        elif kind == "yesno":
            v = {True: "yes", False: "no", "yes": "yes", "no": "no"}.get(v)
            if v is None:
                raise ValueError(f"{label}: yes or no")
        out[q["key"]] = v
    return out


def save_answers(db, task, answers, user_id, user_name):
    """Store the answers (a re-answer after a reopen replaces them) and mark
    the ask done. The caller commits and audits."""
    now = datetime.utcnow().isoformat()
    db.execute("DELETE FROM task_answers WHERE task_id = ?", (task["id"],))
    db.executemany("INSERT INTO task_answers (project_id, task_id, question_key, value, by_id, by_name, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   [(task["project_id"], task["id"], k, v, user_id, user_name, now) for k, v in answers.items()])
    db.execute("UPDATE tasks SET done = 1, done_at = ? WHERE id = ?", (now, task["id"]))
    from services import rules   # automations: in a request it waits for the request's end, after the caller's commit
    rules.fire("ask_completed", task["project_id"], {"task": task["title"], "kind": task["kind"] or "task"})


def record_upload(db, task, document_id, user_id, user_name):
    save_answers(db, task, {FILE_KEY: str(document_id)}, user_id, user_name)


# ---- who sees what ---------------------------------------------------------------------

def own_ask(project_id, task_id, user_id):
    """The task row when it is this person's own ask on this rollout, else None."""
    return get_db().execute("SELECT * FROM tasks WHERE id = ? AND project_id = ? AND assignee_id = ?",
                            (task_id, project_id, user_id)).fetchone()


def _rows(db, project_id, user_id=None):
    """Tasks assigned to someone external on the rollout (only `user_id`'s when given)."""
    return db.execute(
        "SELECT t.*, u.name AS assignee_name, pp.role AS assignee_role FROM tasks t JOIN users u ON u.id = t.assignee_id "
        "JOIN project_participants pp ON pp.project_id = t.project_id AND pp.user_id = t.assignee_id "
        "WHERE t.project_id = ? AND u.kind = 'external'" + (" AND t.assignee_id = ?" if user_id else "") +
        " ORDER BY t.done, t.due_date IS NULL, t.due_date, t.id", (project_id, *([user_id] if user_id else []))).fetchall()


def listing(project_id, user_id=None):
    """The asks as the pages show them: kind, what is asked, the answers given
    (an upload's file by name, while it is not deleted)."""
    db = get_db()
    rows = _rows(db, project_id, user_id)
    answers = {}
    if rows:
        marks = ",".join("?" for _ in rows)
        for a in db.execute(f"SELECT * FROM task_answers WHERE task_id IN ({marks}) ORDER BY id", [r["id"] for r in rows]):
            answers.setdefault(a["task_id"], []).append(a)
    out = []
    for t in rows:
        qs = questions(t) if t["kind"] == "form" else []
        given = {a["question_key"]: a for a in answers.get(t["id"], [])}
        item = {"id": t["id"], "title": t["title"], "kind": t["kind"] or "task", "done": bool(t["done"]), "done_at": t["done_at"],
                "due_date": t["due_date"], "assignee": t["assignee_name"], "assignee_role": t["assignee_role"],
                "category": t["ask_category"], "questions": qs,
                "answers": [{"key": q["key"], "label": q["label"], "value": given[q["key"]]["value"]} for q in qs if q["key"] in given],
                "answered_by": next(iter(given.values()))["by_name"] if given else None,
                "answered_at": next(iter(given.values()))["at"] if given else None, "file": None}
        if FILE_KEY in given and str(given[FILE_KEY]["value"]).isdigit():
            doc = db.execute("SELECT id, filename FROM documents WHERE id = ? AND project_id = ? AND deleted_at IS NULL",
                             (int(given[FILE_KEY]["value"]), project_id)).fetchone()
            item["file"] = {"id": doc["id"], "filename": doc["filename"]} if doc else None
        out.append(item)
    return out


def limited(user_id):
    """An external account's writes to its asks (a tick, an upload, answers):
    at most policy guest_writes_per_minute a minute, from any address."""
    from security import rate_limited
    return rate_limited(f"ask:{user_id}", policy("guest_writes_per_minute"), 1, any_ip=True)


def is_external(db, user_id):
    row = db.execute("SELECT kind FROM users WHERE id = ?", (user_id,)).fetchone() if user_id else None
    return bool(row) and row["kind"] == "external"


# ---- the rating at sign-off -------------------------------------------------------------

def clean_rating(body):
    """(rating, comment) from a signing body, None when no rating was given,
    or ValueError. The rating is optional; a comment without one is ignored."""
    rating = body.get("rating")
    if rating in (None, ""):
        return None
    if isinstance(rating, bool) or not isinstance(rating, (int, str)) or str(rating) not in ("1", "2", "3", "4", "5"):
        raise ValueError("Rate the rollout from 1 to 5")
    from core import text_field
    return int(rating), text_field(body.get("rating_comment"), 1000, "Comment", multiline=True) or None


def save_rating(db, project_id, version, rating, comment, user_id, user_name):
    """Once per sign-off version: a second rating for the same version is
    refused by the table (UNIQUE) and answers False. The caller commits."""
    import sqlite3
    try:
        db.execute("INSERT INTO csat (project_id, signoff_version, rating, comment, by_id, by_name, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (project_id, version, rating, comment, user_id, user_name, datetime.utcnow().isoformat()))
    except sqlite3.IntegrityError:
        return False
    return True


def ratings(project_id):
    return [dict(r) for r in get_db().execute(
        "SELECT signoff_version, rating, comment, by_name, at FROM csat WHERE project_id = ? ORDER BY signoff_version", (project_id,))]


def averages(project_ids=None, by_owner=False):
    """{project id: (avg, n)}, or {owner id: (avg, n)} with by_owner, over
    live rollouts (the latest rating of each rollout counts once)."""
    db = get_db()
    where, params = "", []
    if project_ids is not None:
        if not project_ids:
            return {}
        where = f" AND c.project_id IN ({','.join('?' for _ in project_ids)})"
        params = list(project_ids)
    rows = db.execute(
        "SELECT c.project_id, p.owner_id, c.rating FROM csat c JOIN projects p ON p.id = c.project_id "
        "WHERE p.deleted_at IS NULL AND c.signoff_version = (SELECT MAX(x.signoff_version) FROM csat x WHERE x.project_id = c.project_id)" + where, params)
    acc = {}
    for r in rows:
        acc.setdefault(r["owner_id"] if by_owner else r["project_id"], []).append(r["rating"])
    return {k: (round(sum(v) / len(v), 1), len(v)) for k, v in acc.items()}

