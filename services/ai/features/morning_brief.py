"""Personal morning brief: one short note a working day for each person with
open rollouts: what needs attention first, what is due and overdue, what came
in since yesterday, and a first move. Written from Odin's own figures; sent at
policy ai_brief_time to the bell (and by email unless the person turned the
"brief" kind off). Fallback: nothing (the dashboard and digest, as before)."""
from datetime import datetime, timedelta

from services.ai import AIFeature, register
from services.ai.features.weekly_words import _fmt
from services.ai.graders import facts_kept, max_words, never_says

SCHEMA = {"type": "object", "required": ["brief", "first_move"], "properties": {
    "brief": {"type": "string", "maxLength": 1200}, "first_move": {"type": "string", "maxLength": 250}}}


def people(db):
    """Who gets a brief: active staff who own or work on an open rollout."""
    from db import PROJECT_OPEN_SQL
    return [r[0] for r in db.execute(
        f"SELECT DISTINCT u.id FROM users u JOIN projects p ON p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} "
        "LEFT JOIN project_participants pp ON pp.project_id = p.id AND pp.user_id = u.id "
        "WHERE u.active = 1 AND u.kind = 'internal' AND (p.owner_id = u.id OR pp.user_id IS NOT NULL) ORDER BY u.id")]


def gather(user_id):
    from db import PROJECT_OPEN_SQL, get_db
    from policies import local_today
    from services import portfolio
    from services.ai.client import AIError
    db = get_db()
    projects = db.execute(f"SELECT DISTINCT p.*, u.name AS owner_name FROM projects p LEFT JOIN users u ON u.id = p.owner_id "
                          f"LEFT JOIN project_participants pp ON pp.project_id = p.id AND pp.user_id = ? "
                          f"WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} AND (p.owner_id = ? OR pp.user_id IS NOT NULL) ORDER BY p.name",
                          (user_id, user_id)).fetchall()
    if not projects:
        raise AIError("No open rollouts", "skip")
    rows = portfolio.build(projects)["rows"]
    today = local_today().isoformat()
    tasks = db.execute("SELECT t.title, t.due_date, p.name AS rollout FROM tasks t JOIN projects p ON p.id = t.project_id "
                       "WHERE t.assignee_id = ? AND t.done = 0 AND t.due_date IS NOT NULL AND t.due_date <= ? AND p.deleted_at IS NULL ORDER BY t.due_date LIMIT 12",
                       (user_id, today)).fetchall()
    since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    news = db.execute("SELECT title FROM notifications WHERE user_id = ? AND created_at >= ? AND kind != 'brief' ORDER BY id DESC LIMIT 12",
                      (user_id, since)).fetchall()
    return {
        "today": _fmt(today),
        "rollouts": [{"name": r["name"], "health": r["rag"], "stage": r["stage"], "status": status_words(r)} for r in rows][:15],
        "due_today": [{"task": t["title"], "rollout": t["rollout"]} for t in tasks if t["due_date"] == today],
        "overdue": [{"task": t["title"], "rollout": t["rollout"], "due": _fmt(t["due_date"])} for t in tasks if t["due_date"] < today],
        "since_yesterday": [n["title"] for n in news],
    }


def status_words(r):
    """A rollout's state as finished words, so the model never has to combine
    two numbers itself (it mixed "3 d over SLA" with "4 d late" once)."""
    if r["rag"] not in ("red", "amber"):
        return "on plan"
    words = [x.rstrip(".") for x in r["reasons"][:2]]
    if r["vs_target_days"] and r["vs_target_days"] > 0 and not any("target" in w for w in words):
        words.append(f"forecast {r['vs_target_days']} d after the target")
    return "; ".join(words)


def deliver(db, user_id, output):
    """The bell, and email unless the person turned briefs off."""
    from markupsafe import escape
    from services.notifications import notify_users
    notify_users([user_id], "brief", None, "Your morning brief",
                 f"<p>{escape(output['brief'])}</p><p><b>First move:</b> {escape(output['first_move'])}</p>"
                 "<p style='color:#6B7280'>Written by AI from Odin's figures. Switch the email off on your Account page.</p>", link="/dashboard")


def fixture():
    """A synthetic project manager with three rollouts, work due and overnight news."""
    return {"today": "8 Oct 2026",
            "rollouts": [{"name": "Firewall refresh", "health": "red", "stage": "Deployment", "status": "Past its target date by 8 d; 1 open blocker"},
                         {"name": "SIEM onboarding", "health": "amber", "stage": "Design", "status": "Design is 3 d over its 6 d SLA; forecast 4 d after the target"},
                         {"name": "EDR rollout", "health": "green", "stage": "Deployment", "status": "on plan"}],
            "due_today": [{"task": "Send the change window request", "rollout": "Firewall refresh"}],
            "overdue": [{"task": "Review the design document", "rollout": "SIEM onboarding", "due": "6 Oct 2026"}],
            "since_yesterday": ["Customer approved the Kickoff stage on EDR rollout", "AI noticed 2 things in the notes of SIEM onboarding that the register does not hold"]}


FEATURE = register(AIFeature(
    key="morning_brief", label="Morning brief",
    description="Each working morning, a short note per person: rollouts needing attention, what is due and overdue, what came in, and a first move.",
    prompt="morning_brief.v2.txt", schema=SCHEMA, gather=gather, fixture=fixture,
    graders=(facts_kept("Firewall refresh", "SIEM", "change window", "design document"),
             never_says("good morning", "dear", "regards", "on track", "4 days over", "4 d over", "3 days late", "3 d late", "3 days after"),
             max_words("brief", 120), max_words("first_move", 30)),
    runs="daily", scope="person", max_tokens=400, temperature=0.3, project_role=None, on_new=deliver,
))
