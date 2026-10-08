"""Chase drafts: a short, polite follow-up email to the customer contact
about what is waiting on them (an approval past its wait, customer tasks
overdue), with the dates and days worked out in code. On demand from the
project page; the project manager copies it or opens it in their mail. Odin
sends nothing. Fallback: nothing (chasing by hand, as before)."""

from services.ai import AIFeature, register
from services.ai.features.weekly_words import _fmt
from services.ai.graders import facts_kept, max_words, never_says

SCHEMA = {"type": "object", "required": ["subject", "body"], "properties": {
    "subject": {"type": "string", "maxLength": 200}, "body": {"type": "string", "maxLength": 2000}}}


def waiting(project_id, db=None):
    """What waits on the customer now: the pending approval of the current
    stage and the customer's overdue tasks, each with how long."""
    from db import get_db
    from policies import local_date, local_today
    db = db or get_db()
    today = local_today()
    days = lambda iso: (today - local_date(iso)).days   # noqa: E731   a stored UTC time counts from its local day
    out = []
    a = db.execute("SELECT a.stage, a.requested_at FROM stage_approvals a JOIN projects p ON p.id = a.project_id "
                   "WHERE a.project_id = ? AND a.status = 'pending' AND a.stage = p.stage ORDER BY a.id DESC LIMIT 1", (project_id,)).fetchone()
    if a:
        out.append({"what": f"Approval of the {a['stage']} stage", "since": _fmt(a["requested_at"]), "days_waiting": days(a["requested_at"])})
    for t in db.execute("SELECT t.title, t.due_date FROM tasks t JOIN project_participants pp ON pp.project_id = t.project_id AND pp.user_id = t.assignee_id "
                        "WHERE t.project_id = ? AND t.done = 0 AND pp.role = 'Customer' AND t.due_date IS NOT NULL AND t.due_date < ? ORDER BY t.due_date LIMIT 6",
                        (project_id, today.isoformat())):
        out.append({"what": t["title"], "due": _fmt(t["due_date"]), "days_overdue": days(t["due_date"])})
    return out


def options(project_id):
    """For the page: is anything waiting (else the panel stays hidden), and who to write to."""
    from db import get_db
    contact = get_db().execute("SELECT u.name, u.email FROM project_participants pp JOIN users u ON u.id = pp.user_id "
                               "WHERE pp.project_id = ? AND pp.role = 'Customer' AND u.active = 1 ORDER BY pp.id LIMIT 1", (project_id,)).fetchone()
    return {"waiting": waiting(project_id), "contact": dict(contact) if contact else None}


def gather(project_id):
    from db import get_db
    from services.ai.client import AIError
    db = get_db()
    project = db.execute("SELECT p.*, u.name AS owner_name FROM projects p LEFT JOIN users u ON u.id = p.owner_id WHERE p.id = ? AND p.deleted_at IS NULL",
                         (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    items = waiting(project_id, db)
    if not items:
        raise AIError("Nothing is waiting on the customer", "skip")
    contact = options(project_id)["contact"]
    return {"rollout": {"name": project["name"], "client": project["client"], "go_live": _fmt(project["target_end_date"])},
            "customer_contact": (contact or {}).get("name") or "the customer", "project_manager": project["owner_name"],
            "waiting_on_the_customer": items}


def fixture():
    """A synthetic rollout waiting on an approval for 9 days and on building access."""
    return {"rollout": {"name": "SIEM onboarding", "client": "Northwind Clinics", "go_live": "20 Oct 2026"},
            "customer_contact": "Ann Lee", "project_manager": "Sam Rivera",
            "waiting_on_the_customer": [{"what": "Approval of the Design stage", "since": "29 Sep 2026", "days_waiting": 9},
                                        {"what": "Grant building access at Site B", "due": "4 Oct 2026", "days_overdue": 4}]}


FEATURE = register(AIFeature(
    key="chase_draft", label="Chase drafts",
    description="Drafts a short, polite follow-up email to the customer about what is waiting on them, with the dates; the project manager sends it.",
    prompt="chase_draft.v1.txt", schema=SCHEMA, gather=gather, fixture=fixture, options=options,
    graders=(facts_kept("Ann", "Design", "Site B", "29 Sep", "Sam"), never_says("urgent", "immediately", "asap", "failure", "!"),
             max_words("body", 150)),
    runs="on_demand", max_tokens=450, temperature=0.3, project_role="manage_project",
))
