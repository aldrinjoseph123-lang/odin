"""Milestones (Odin 2.0).

A milestone is a dated commitment of a rollout: a name, a day, optionally the
stage it belongs to, and whether the customer may see it. It is done when
someone marks it reached (done_at). Everything that draws milestones (the
calendar, the dashboard timeline, both report cuts, the sign-off draft)
reads them here, and the customer cut is made here: `items(..., customer=True)`
returns only the ones marked for the customer, and every outsider (a partner
as much as the customer) gets that cut. Repeating tasks are services/recurrence.py.
"""
from datetime import datetime, timedelta

from db import get_db
from policies import local_today
from services.fmt import fmt_date


# ---- milestones ----------------------------------------------------------------

def _row(r, today):
    d = dict(r)
    d["customer_visible"] = bool(r["customer_visible"])
    d["done"] = r["done_at"] is not None
    d["missed"] = r["done_at"] is None and r["date"] < today
    return d


def _cut(customer, alias=""):
    """The customer cut as SQL: only the milestones marked for the customer."""
    return f"AND {alias}customer_visible = 1 " if customer else ""


def items(project_id, customer=False, today=None):
    """A rollout's milestones, open ones first by date, then the done ones.
    `customer`: only those marked for the customer."""
    return items_for([project_id], customer, today)[project_id]


def items_for(project_ids, customer=False, today=None):
    """{project id: [milestones]} for many rollouts, in one query."""
    today = today or local_today().isoformat()
    ids = list(project_ids)
    out = {i: [] for i in ids}
    if not ids:
        return out
    marks = ",".join("?" * len(ids))
    for r in get_db().execute(
            f"SELECT * FROM milestones WHERE project_id IN ({marks}) {_cut(customer)}"
            "ORDER BY done_at IS NOT NULL, date, id", ids):
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
                f"WHERE m.date BETWEEN ? AND ? AND p.deleted_at IS NULL{scope_sql} {_cut(customer, 'm.')}"
                "ORDER BY m.date, m.id", (start, end, *scope_params))]


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
    return [f"Milestone reached: {m['name']} ({fmt_date(local_date(m['done_at']).isoformat())})"
            for m in sorted(items(project_id, customer=True), key=lambda m: m["done_at"] or "") if m["done"]]


def summary_of(list_, today=None):
    """What one row of the portfolio report says: counts, and the next open one."""
    today = today or local_today().isoformat()
    open_ = sorted((m for m in list_ if not m["done"]), key=lambda m: m["date"])
    nxt = next((m for m in open_ if m["date"] >= today), None)
    return {"total": len(list_), "done": sum(1 for m in list_ if m["done"]), "missed": sum(1 for m in open_ if m["date"] < today),
            "next": {"name": nxt["name"], "date": nxt["date"]} if nxt else None}
