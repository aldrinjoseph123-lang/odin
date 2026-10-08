"""Lessons drafted: what went wrong and what to repeat, from a rollout's plan
changes, stage overruns, risks and their resolutions, partial or descoped
scope, and notes, each with its evidence. Odin keeps lessons whose evidence
is in the input; the project manager ticks the ones to save to the library
(services/lessons.py). On demand from the project page."""
from services.ai import AIFeature, register
from services.ai.features.sow_plan import _norm, _supported
from services.ai.features.weekly_words import _fmt
from services.ai.graders import finds, never_says

SCHEMA = {"type": "object", "required": ["lessons"], "properties": {"lessons": {"type": "array", "maxItems": 8, "items": {
    "type": "object", "required": ["kind", "text", "evidence"], "properties": {
        "kind": {"type": "string", "enum": ["avoid", "repeat"]}, "text": {"type": "string", "maxLength": 400}, "evidence": {"type": "string", "maxLength": 400}}}}}}


def gather(project_id):
    from db import get_db
    from services import plan as plan_service, raid
    from services.ai.client import AIError
    from services.signoff import scope
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    p = plan_service.build(project)
    facts = {
        "rollout": {"name": project["name"], "client": project["client"], "product": project["product_name"], "vendor": project["vendor_name"]},
        "plan_changes": [{"stage": c["stage"], "what": c["field"], "reason": c["reason"]} for c in plan_service.changes(project_id, 20) if c["reason"]],
        "stage_overruns": [f"{s['name']} took {s['actual_days']} d against a {s['sla_days']} d SLA" for s in p["stages"]
                           if s["actual_days"] is not None and s["sla_days"] and s["actual_days"] > s["sla_days"]],
        "risks_and_issues": [{"kind": r["kind"], "title": r["title"], "status": r["status"], "resolution": r["resolution"]} for r in raid.items(project_id)][:12],
        "scope_exceptions": [{"title": s["title"], "status": s["status"], "note": s["note"]} for s in scope(project_id) if s["status"] in ("partial", "descoped")],
        "recent_notes": [n["note"][:300] for n in db.execute("SELECT note FROM status_notes WHERE project_id = ? AND prev_stage IS NULL ORDER BY created_at DESC LIMIT 8",
                                                             (project_id,))],
    }
    if not any(facts[k] for k in ("plan_changes", "stage_overruns", "risks_and_issues", "scope_exceptions", "recent_notes")):
        raise AIError("Nothing recorded yet to learn from", "skip")
    return facts


def refine(inputs, output):
    import json
    corpus = _norm(json.dumps({k: v for k, v in inputs.items() if k != "rollout"}, ensure_ascii=False))
    words = set(corpus.split())
    seen, kept = set(), []
    for l in output.get("lessons") or []:
        if not _supported(l.get("evidence", ""), corpus, words) or _norm(l["text"]) in seen:
            continue
        seen.add(_norm(l["text"]))
        kept.append(l)
    return {"lessons": kept}


def fixture():
    return {"rollout": {"name": "SIEM onboarding", "client": "Northwind Clinics", "product": "Sentinel", "vendor": "Contoso Security"},
            "plan_changes": [{"stage": "Design", "what": "end", "reason": "Vendor configuration late"},
                             {"stage": "Build", "what": "start", "reason": "Waiting on building access at Site B"}],
            "stage_overruns": ["Design took 9 d against a 6 d SLA", "Build took 12 d against a 8 d SLA"],
            "risks_and_issues": [{"kind": "blocker", "title": "No building access at Site B", "status": "closed", "resolution": "Access badge issued after 2 weeks"},
                                 {"kind": "risk", "title": "Log volume above the licence", "status": "closed", "resolution": "Filtered noisy sources at onboarding"}],
            "scope_exceptions": [{"title": "Branch firewalls", "status": "partial", "note": "Two legacy firewalls excluded: end of life"}],
            "recent_notes": ["Daily stand-ups with the vendor during Build kept the onboarding on pace."]}


def has_repeat(inputs, output):
    return None if any(l["kind"] == "repeat" for l in output["lessons"]) else "no lesson on what worked"


FEATURE = register(AIFeature(
    key="lessons", label="Lessons drafted",
    description="Drafts what went wrong and what to repeat from a rollout's history, each with its evidence, for the project manager to save to the lessons library.",
    prompt="lessons.v2.txt", schema=SCHEMA, gather=gather, fixture=fixture, refine=refine,
    graders=(finds("lessons", ["access", "vendor"], at_least=1.0), never_says("Ravi", "change-freeze", "cut-overs"), has_repeat),
    runs="on_demand", budget_s=150, max_tokens=600, temperature=0.2, project_role="manage_project",
))
