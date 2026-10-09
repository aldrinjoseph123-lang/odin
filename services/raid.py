"""A rollout's RAID register: risks, issues, decisions and blockers.

Each item has an owner, an impact (and, for a risk, a likelihood), a due
date, the stage it belongs to and a status whose words depend on the kind.
An item is internal unless marked for the customer, in which case the
customer's version of the report shows it. Open blockers and high-impact
risks and issues count against the rollout's health (services/plan.py).
"""
from datetime import datetime

from db import get_db

KINDS = ("risk", "issue", "decision", "blocker")
LEVELS = ("low", "medium", "high")
STATUSES = {"risk": ("open", "mitigating", "closed"), "issue": ("open", "closed"),
            "blocker": ("open", "closed"), "decision": ("proposed", "decided")}
DONE = ("closed", "decided")


def items(project_id, customer=False):
    rows = get_db().execute(
        "SELECT r.*, u.name AS owner_name FROM raid_items r LEFT JOIN users u ON u.id = r.owner_id WHERE r.project_id = ? "
        + ("AND r.customer_visible = 1 " if customer else "")
        + "ORDER BY r.status IN ('closed', 'decided'), CASE r.kind WHEN 'blocker' THEN 0 WHEN 'issue' THEN 1 WHEN 'risk' THEN 2 ELSE 3 END, "
          "CASE r.impact WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, r.due_date IS NULL, r.due_date, r.id", (project_id,)).fetchall()
    return [dict(r) | {"customer_visible": bool(r["customer_visible"]), "open": r["status"] not in DONE} for r in rows]


def clean(body, project_id, existing=None):
    """A validated dict of fields from a posted body, or raise ValueError."""
    from core import as_id, parse_date
    for k in ("title", "detail", "stage", "resolution", "due_date"):
        if body.get(k) is not None and not isinstance(body.get(k), str):
            raise ValueError(f"Send the {k.replace('_', ' ')} as text")
    kind = body.get("kind", existing["kind"] if existing else None)
    if kind not in KINDS:
        raise ValueError("Pick a kind: risk, issue, decision or blocker")
    title = str(body.get("title", existing["title"] if existing else "") or "").strip()[:200]
    if not title:
        raise ValueError("Give it a title")
    impact = body.get("impact", existing["impact"] if existing else "medium")
    if impact not in LEVELS:
        raise ValueError("Impact is low, medium or high")
    likelihood = body.get("likelihood", existing["likelihood"] if existing else None) if kind == "risk" else None
    if likelihood is not None and likelihood not in LEVELS:
        raise ValueError("Likelihood is low, medium or high")
    status = body.get("status", existing["status"] if existing and existing["kind"] == kind else STATUSES[kind][0])
    if status not in STATUSES[kind]:
        raise ValueError(f"A {kind} is {', '.join(STATUSES[kind])}")
    try:
        due = parse_date(body.get("due_date", existing["due_date"] if existing else None))
    except ValueError as exc:
        raise ValueError(f"Due date: {exc}") from None
    owner = body.get("owner_id", existing["owner_id"] if existing else None) or None
    if owner is not None:
        # the task assignee's rule: staff, or an outsider on this project (never a partner from elsewhere)
        if as_id(owner) is None or not get_db().execute(
                "SELECT 1 FROM users u WHERE u.id = ? AND u.active = 1 AND (u.kind = 'internal' OR EXISTS "
                "(SELECT 1 FROM project_participants pp WHERE pp.project_id = ? AND pp.user_id = u.id))", (as_id(owner), project_id)).fetchone():
            raise ValueError("Pick an owner from the list")
        owner = as_id(owner)
    return {
        "kind": kind, "title": title, "impact": impact, "likelihood": likelihood, "status": status, "due_date": due, "owner_id": owner,
        "detail": (str(body.get("detail", existing["detail"] if existing else "") or "").strip()[:4000]) or None,
        "stage": (str(body.get("stage", existing["stage"] if existing else "") or "").strip()[:100]) or None,
        "resolution": (str(body.get("resolution", existing["resolution"] if existing else "") or "").strip()[:2000]) or None,
        "customer_visible": 1 if body.get("customer_visible", bool(existing["customer_visible"]) if existing else False) else 0,
    }


def create(project_id, fields, author):
    now = datetime.utcnow().isoformat()
    db = get_db()
    cur = db.execute(
        "INSERT INTO raid_items (project_id, kind, title, detail, impact, likelihood, status, owner_id, due_date, stage, resolution, customer_visible, "
        "created_by, created_at, updated_at, closed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, fields["kind"], fields["title"], fields["detail"], fields["impact"], fields["likelihood"], fields["status"], fields["owner_id"],
         fields["due_date"], fields["stage"], fields["resolution"], fields["customer_visible"], author, now, now, now if fields["status"] in DONE else None))
    db.commit()
    return cur.lastrowid


def update(item, fields):
    now = datetime.utcnow().isoformat()
    closed_at = item["closed_at"] if item["status"] in DONE and fields["status"] in DONE else (now if fields["status"] in DONE else None)
    db = get_db()
    db.execute(
        "UPDATE raid_items SET kind = ?, title = ?, detail = ?, impact = ?, likelihood = ?, status = ?, owner_id = ?, due_date = ?, stage = ?, "
        "resolution = ?, customer_visible = ?, updated_at = ?, closed_at = ? WHERE id = ?",
        (fields["kind"], fields["title"], fields["detail"], fields["impact"], fields["likelihood"], fields["status"], fields["owner_id"],
         fields["due_date"], fields["stage"], fields["resolution"], fields["customer_visible"], now, closed_at, item["id"]))
    db.commit()
