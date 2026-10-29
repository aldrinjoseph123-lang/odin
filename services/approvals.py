"""Customer approval of a stage move: the one door (29 Oct 2026, the user's call).

A rollout with customer approval on asks ONE named person: its approver,
`projects.approver_id` while that user is still an active Customer on the
team, else the first Customer who joined (lowest project_participants.id).
Only the approver decides, and only the approver hears the requests, the
chasers and the "approval switched on" notice; other Customer contacts see
"Waiting on <name>".

A decline pauses the stage: services/gates.blocked() holds the next move
until the customer approves, or the project manager re-requests and waits,
or overrides with a typed reason. A move while a request is still pending
goes ahead, but the request is withdrawn and the approver is told, never
silently. The caller commits.
"""
from datetime import datetime

from markupsafe import escape

from db import get_db


def customers(db, project_id):
    """The rollout's active Customer contacts (id, name, approver_id), first to join first: who may be the approver."""
    return db.execute(
        "SELECT u.id, u.name, p.approver_id FROM project_participants pp JOIN users u ON u.id = pp.user_id "
        "JOIN projects p ON p.id = pp.project_id WHERE pp.project_id = ? AND pp.role = 'Customer' AND u.active = 1 ORDER BY pp.id",
        (project_id,)).fetchall()


def approver(db, project_id):
    """The approver's user row (id, name), or None when the rollout has no active Customer."""
    rows = customers(db, project_id)
    return next((r for r in rows if r["id"] == r["approver_id"]), rows[0] if rows else None)


def approver_ids(project_id, db=None):
    a = approver(db or get_db(), project_id)
    return [a["id"]] if a else []


def is_approver(project_id, user_id, db=None):
    return user_id in approver_ids(project_id, db)


def ask(project, stage, body_html="", to=None):
    """Tell the approver (or `to`) that `stage` waits for their approval."""
    from services.notifications import notify_users
    pid = project["id"]
    notify_users(to if to is not None else approver_ids(pid), "approval", pid,
                 f"{escape(project['name'])}: please approve the move to {escape(stage)}",
                 (body_html or f"<b>{escape(project['name'])}</b> is in <b>{escape(stage)}</b>.") + "<br>Please review and approve this step.",
                 link=f"/projects/{pid}")


def request(db, project, stage, by_name, tell=True):
    """Open a pending request for `stage`, to the approver. Returns the new row's id, or None (no approver)."""
    if not approver_ids(project["id"], db):
        return None
    aid = db.execute("INSERT INTO stage_approvals (project_id, stage, requested_by, requested_at) VALUES (?, ?, ?, ?)",
                     (project["id"], stage, by_name, datetime.utcnow().isoformat())).lastrowid
    if tell:
        ask(project, stage)
    return aid


def tell_withdrawn(project_id, reason, to=None):
    """The approver (or `to`) hears that what they were asked is no longer needed."""
    from services.notifications import notify_users
    name = get_db().execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()[0]
    notify_users(to if to is not None else approver_ids(project_id), "approval", project_id,
                 f"{escape(name)}: approval no longer needed", f"No longer needed: {escape(reason)}.", link=f"/projects/{project_id}")


def withdraw(db, project_id, reason, to=None, tell=True):
    """Pending requests become 'superseded'; the approver (or `to`) is told. Returns how many."""
    n = db.execute("UPDATE stage_approvals SET status = 'superseded' WHERE project_id = ? AND status = 'pending'", (project_id,)).rowcount
    if n and tell:
        tell_withdrawn(project_id, reason, to)
    return n


def approver_left(db, project_id, before):
    """After a team change: when `before` (the approver before it) no longer is, the setting is
    cleared and an open request withdrawn, telling them. Returns how many were withdrawn."""
    after = approver(db, project_id)
    if before is None or (after and after["id"] == before["id"]):
        return 0
    db.execute("UPDATE projects SET approver_id = NULL WHERE id = ? AND approver_id = ?", (project_id, before["id"]))
    return withdraw(db, project_id, "the approver left the rollout", to=[before["id"]])


def declined_many(db, project_ids):
    """{project id: row} for the rollouts whose current stage stands declined: in this visit
    (asked since the rollout entered the stage), the latest decision is a decline. A re-request
    still pending does not lift it; an approval does. Only while the rollout asks."""
    ids = list(project_ids)
    if not ids:
        return {}
    visit = ("b.project_id = p.id AND b.stage = p.stage AND b.requested_at >= COALESCE(p.stage_entered_at, '') "
             "AND b.status IN ('approved', 'declined')")
    rows = db.execute(
        "SELECT b.* FROM stage_approvals b JOIN projects p ON p.id = b.project_id "
        f"WHERE p.id IN ({','.join('?' * len(ids))}) AND p.customer_approval = 1 AND {visit} "
        f"AND b.id = (SELECT MAX(b2.id) FROM stage_approvals b2 WHERE b2.project_id = p.id AND {visit.replace('b.', 'b2.')})", ids)
    return {r["project_id"]: r for r in rows if r["status"] == "declined"}


def declined(project, db=None):
    """The decline that pauses `project`'s current stage, or None."""
    return declined_many(db or get_db(), [project["id"]]).get(project["id"])
