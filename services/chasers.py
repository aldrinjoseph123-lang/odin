"""Automatic chasers (review B9): the customer is reminded of what waits on them.

A sign-off out for the customer's signature, and a stage move waiting for the
customer's approval, get one reminder after policy chase_after_days working
days (Settings › General's working week and holidays) and then one every as
many days, at most chase_max reminders each. The reminder is an ordinary
notification (kind "approval"): bell and, through the outbox, a mail whose
sign-in link is minted as it is sent. The count sits on the row
(chase_count, chased_at) for the project manager to see.

The scheduler runs run() in its daily digest pass (working days only). 0 days
switches it off.
"""
from datetime import datetime

from markupsafe import escape

from db import PROJECT_OPEN_SQL, customer_ids, get_db
from policies import local_date, local_today, policy
from services import workdays


def _due(since, today, every, cal):
    day = local_date(since)
    return day is not None and workdays.between(day, today, cal) >= every


def run(db=None, today=None):
    """Send the reminders that are due; returns how many went out. Needs a
    request context (notify_users builds links)."""
    from services.audit import audit_log
    from services.notifications import notify_users
    db = db or get_db()
    every, cap = policy("chase_after_days", db), policy("chase_max", db)
    if not every:
        return 0
    today = today or local_today(db)
    cal = workdays._calendar(tuple(policy("working_days", db)), policy("holidays", db))   # working days, whatever the SLA clock counts
    now = datetime.utcnow().isoformat()
    sent = 0
    live = f"p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}"
    for s in db.execute(
            "SELECT s.id, s.project_id, s.version, s.signer_id, s.created_at, s.chased_at, s.chase_count, p.name FROM signoffs s "
            f"JOIN projects p ON p.id = s.project_id WHERE s.status = 'sent' AND s.superseded_at IS NULL AND s.signer_id IS NOT NULL "
            f"AND s.chase_count < ? AND {live}", (cap,)).fetchall():
        if not _due(s["chased_at"] or s["created_at"], today, every, cal):
            continue
        db.execute("UPDATE signoffs SET chase_count = chase_count + 1, chased_at = ? WHERE id = ?", (now, s["id"]))
        db.commit()
        notify_users([s["signer_id"]], "approval", s["project_id"], f"Reminder: please sign off {escape(s['name'])}",
                     f"<p>The sign-off for <b>{escape(s['name'])}</b> (version {s['version']}) is waiting for your signature. "
                     "Please review it, then sign — or say what needs to change.</p>", link=f"/projects/{s['project_id']}/signoff")
        audit_log("chase_signoff", "project", s["project_id"], s["name"], f"v{s['version']} reminder {s['chase_count'] + 1} of {cap}", actor="scheduler")
        sent += 1
    # the latest request of each rollout, for the stage it is still in (as the dashboard counts them waiting)
    for a in db.execute(
            "SELECT a.id, a.project_id, a.stage, a.requested_at, a.chased_at, a.chase_count, p.name FROM stage_approvals a "
            "JOIN projects p ON p.id = a.project_id WHERE a.status = 'pending' AND a.stage = p.stage "
            "AND a.id = (SELECT MAX(id) FROM stage_approvals WHERE project_id = a.project_id) "
            f"AND a.chase_count < ? AND {live}", (cap,)).fetchall():
        if not _due(a["chased_at"] or a["requested_at"], today, every, cal):
            continue
        customers = customer_ids(a["project_id"], db)
        if not customers:
            continue
        db.execute("UPDATE stage_approvals SET chase_count = chase_count + 1, chased_at = ? WHERE id = ?", (now, a["id"]))
        db.commit()
        notify_users(customers, "approval", a["project_id"], f"Reminder: please approve the move of {escape(a['name'])} to {escape(a['stage'])}",
                     f"<p><b>{escape(a['name'])}</b> moved to <b>{escape(a['stage'])}</b> and is waiting for your approval. "
                     "Please review and approve this step, or decline it with a comment.</p>", link=f"/projects/{a['project_id']}")
        audit_log("chase_approval", "project", a["project_id"], a["name"], f"{a['stage']} reminder {a['chase_count'] + 1} of {cap}", actor="scheduler")
        sent += 1
    return sent
