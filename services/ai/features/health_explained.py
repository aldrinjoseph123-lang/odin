"""Why is this amber? The rollout's health in two plain sentences and a first
move, written from the reasons and figures Odin's health check already
computed (services/plan.py): the model only phrases them. Green and closed
rollouts are skipped. Fallback: the reasons list the page already shows."""
from services.ai import AIFeature, register
from services.ai.features.weekly_words import _fmt
from services.ai.graders import facts_kept, max_words, never_says

SCHEMA = {"type": "object", "required": ["why", "first_move"], "properties": {
    "why": {"type": "string", "maxLength": 500}, "first_move": {"type": "string", "maxLength": 250}}}


def gather(project_id):
    from db import get_db
    from policies import local_today
    from services import plan as plan_service, raid
    from services.ai.client import AIError
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    p = plan_service.build(project)
    if p["health"]["rag"] not in ("amber", "red"):
        raise AIError(f"Health is {p['health']['rag']}: nothing to explain", "skip")
    today = local_today().isoformat()
    cur = next((s for s in p["stages"] if s["status"] == "current"), None)
    items = [r for r in raid.items(project_id) if r["open"]]
    overdue = db.execute("SELECT title, due_date FROM tasks WHERE project_id = ? AND done = 0 AND due_date < ? ORDER BY due_date LIMIT 5", (project_id, today)).fetchall()
    approval = db.execute("SELECT stage, requested_at FROM stage_approvals WHERE project_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
    f = p["finish"]
    return {
        "rollout": {"name": project["name"], "stage": project["stage"]},
        "health": p["health"]["rag"], "reasons": p["health"]["reasons"],
        "finish": {"target": _fmt(f.get("target")), "forecast": _fmt(f.get("forecast")), "days_late_against_target": f.get("vs_target_days")},
        "current_stage": {"name": cur["name"], "working_days_in_stage": cur["actual_days"], "sla_days": cur["sla_days"]} if cur else None,
        "open_blockers": [r["title"] for r in items if r["kind"] == "blocker"][:5],
        "high_impact_risks_and_issues": [r["title"] for r in items if r["kind"] in ("risk", "issue") and r["impact"] == "high"][:5],
        "overdue_tasks": [{"title": t["title"], "due": _fmt(t["due_date"])} for t in overdue],
        "approval_waiting": {"stage": approval["stage"], "asked": _fmt(approval["requested_at"])} if approval else None,
    }


def fixture():
    """A synthetic amber rollout: over its SLA, forecast late, an approval
    waiting since 29 Sep, an overdue approval task."""
    return {
        "rollout": {"name": "SIEM onboarding", "stage": "Design"},
        "health": "amber",
        "reasons": ["Forecast to finish 4 d after the target date.", "Design is 3 d over its 6 d SLA."],
        "finish": {"target": "20 Oct 2026", "forecast": "24 Oct 2026", "days_late_against_target": 4},
        "current_stage": {"name": "Design", "working_days_in_stage": 9, "sla_days": 6},
        "open_blockers": [], "high_impact_risks_and_issues": [],
        "overdue_tasks": [{"title": "Approve design document", "due": "6 Oct 2026"}],
        "approval_waiting": {"stage": "Design", "asked": "29 Sep 2026"},
    }


FEATURE = register(AIFeature(
    key="health_explained", label="Why is this amber?",
    description="Explains an amber or red rollout's health in two sentences and suggests the first move, from the reasons Odin computed.",
    prompt="health_explained.v1.txt", schema=SCHEMA, gather=gather, fixture=fixture,
    graders=(facts_kept("Design", "approv"), never_says("on track", "green"), max_words("why", 60), max_words("first_move", 30)),
    runs="nightly", max_tokens=250, temperature=0.2, project_role=None,
))
