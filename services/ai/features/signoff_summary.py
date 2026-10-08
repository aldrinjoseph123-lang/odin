"""Sign-off summary: the summary paragraph of the sign-off document the
customer signs, drafted from customer-safe facts only (scope with status and
notes, delivered, outstanding, dates, customer-visible decisions; no internal
notes or plan-change reasons). On demand from the sign-off page; the project
manager edits it before sending, and the send records the draft it came
from. Fallback: the template sentence signoff.draft() has always offered."""
from services.ai import AIFeature, register
from services.ai.features.weekly_words import _fmt
from services.ai.graders import facts_kept, max_words, mentions_any, never_says

SCHEMA = {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string", "maxLength": 1600}}}


def gather(project_id):
    from db import get_db
    from policies import local_today, policy
    from services import plan as plan_service, raid, signoff
    from services.ai.client import AIError
    db = get_db()
    project = db.execute("SELECT p.*, u.name AS owner_name FROM projects p LEFT JOIN users u ON u.id = p.owner_id WHERE p.id = ? AND p.deleted_at IS NULL",
                         (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    d = signoff.draft(project)
    stages = plan_service.build(project)["stages"]
    items = d["scope"]
    counts = {"agreed_items": len(items), **{k: sum(1 for x in items if x["status"] == k) for k in ("delivered", "partial", "descoped")}}
    start = project["start_date"] or (stages[0]["actual_start"] if stages else None)
    return {
        "timing": timing(project["target_end_date"], local_today().isoformat()),
        "company": policy("company_name"),
        "rollout": {"name": project["name"], "client": project["client"], "product": project["product_name"], "vendor": project["vendor_name"]},
        "dates": {"started": _fmt(start), "target": _fmt(project["target_end_date"]), "finished": _fmt(local_today().isoformat())},
        "scope_counts": counts if items else None,
        "scope": [{"title": x["title"], "status": x["status"], "note": x["note"]} for x in items],
        "delivered_without_scope": d["delivered"],
        "outstanding": d["outstanding"],
        "decisions_with_the_customer": [{"title": r["title"], "decision": r["resolution"]} for r in raid.items(project_id, customer=True)
                                        if r["kind"] == "decision" and not r["open"]][:8],
    }


def timing(target, finished):
    """The finish against the target, worked out here: the model compares no dates."""
    from datetime import date
    if not target:
        return "no target date was set"
    days = (date.fromisoformat(finished[:10]) - date.fromisoformat(target[:10])).days
    return "on the target date" if days == 0 else f"{abs(days)} day{'s' if abs(days) != 1 else ''} {'after' if days > 0 else 'before'} the target"


def fixture():
    """A synthetic finished rollout: three items delivered, one in part, one
    descoped, one hand-over item outstanding."""
    return {
        "timing": "4 days after the target",
        "company": "Protect24x7",
        "rollout": {"name": "SIEM onboarding", "client": "Northwind Clinics", "product": "Sentinel", "vendor": "Contoso Security"},
        "dates": {"started": "4 Aug 2026", "target": "20 Oct 2026", "finished": "24 Oct 2026"},
        "scope_counts": {"agreed_items": 5, "delivered": 3, "partial": 1, "descoped": 1},
        "scope": [{"title": "Onboard 40 log sources", "status": "delivered", "note": None},
                  {"title": "Build 25 detection rules", "status": "delivered", "note": None},
                  {"title": "SOC runbooks", "status": "delivered", "note": None},
                  {"title": "Onboard the branch firewalls", "status": "partial", "note": "Two legacy firewalls excluded: end of life, no log export."},
                  {"title": "Phase 2 clinics", "status": "descoped", "note": "Moved to a separate purchase order at the customer's request."}],
        "delivered_without_scope": [],
        "outstanding": ["Hand over the admin credentials vault (due 31 Oct 2026)"],
        "decisions_with_the_customer": [{"title": "Retention period", "decision": "90 days hot, 1 year archive"}],
    }


FEATURE = register(AIFeature(
    key="signoff_summary", label="Sign-off summary",
    description="Drafts the summary paragraph of the sign-off document from the scope, dates and deliverables; the project manager edits it before sending.",
    prompt="signoff_summary.v4.txt", schema=SCHEMA, gather=gather, fixture=fixture,
    graders=(facts_kept("Northwind", "legacy", "separate purchase order"),
             mentions_any("3 of 5", "of 5 agreed items, 3", "three of the five", "three of five", "3 of the 5", what="the scope counts (3 of 5)"),
             mentions_any("4 days after", what="the timing as given (4 days after the target)"),
             never_says("all agreed items were delivered", "all items were delivered", "as scheduled", "on schedule", "on time", "ahead of schedule", "within the target", "before the target"),
             max_words("summary", 160)),
    runs="on_demand", max_tokens=450, temperature=0.2, project_role="manage_project",
))
