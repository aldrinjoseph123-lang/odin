"""Weekly words, drafted: the report's summary, next steps and asks, written
by the model from the rollout's week, for the project manager to edit and
save. Fallback: the template draft (report_data.draft_words) the report page
has always offered."""
from datetime import date, timedelta

from services.ai import AIFeature, register
from services.ai.graders import facts_kept, finds, max_words, never_says


def _fmt(iso):
    if not iso:
        return None
    d = date.fromisoformat(str(iso)[:10])
    return f"{d.day} {d.strftime('%b %Y')}"


def gather(project_id):
    """The rollout's facts as of today, in the shape fixture() shows."""
    from db import get_db
    from policies import local_today
    from services import report_data
    from services.ai.client import AIError
    db = get_db()
    project = db.execute("SELECT p.*, u.name AS owner_name FROM projects p LEFT JOIN users u ON u.id = p.owner_id "
                         "WHERE p.id = ? AND p.deleted_at IS NULL", (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    d = report_data.build(project, "internal")
    today = local_today()
    week_ago = (today - timedelta(days=7)).isoformat()
    soon = (today + timedelta(days=7)).isoformat()
    f, cur = d["finish"], next((x for x in d["history"]["dwell"] if x["status"] == "current"), None)
    moves = db.execute("SELECT prev_stage, stage, created_at FROM status_notes WHERE project_id = ? AND prev_stage IS NOT NULL AND created_at >= ? ORDER BY created_at",
                       (project_id, week_ago)).fetchall()
    open_tasks = d["work"]["open"]
    return {
        "today": _fmt(today.isoformat()),
        "rollout": {"name": project["name"], "client": project["client"], "product": project["product_name"], "vendor": project["vendor_name"],
                    "stage": project["stage"], "stage_number": f"{d['project']['stage_number']} of {d['project']['stage_count']}",
                    "percent_complete": d["pct_complete"], "health": d["health"]["rag"], "health_reasons": d["health"]["reasons"],
                    "target_date": _fmt(f.get("target")), "forecast_finish": _fmt(f.get("forecast")),
                    "days_late_against_target": f.get("vs_target_days")},
        "current_stage": {"name": project["stage"], "days_in_stage": cur["days"] if cur else None, "sla_days": cur["sla"] if cur else None,
                          "days_over_sla": cur["over"] if cur else 0},
        "this_week": {
            "notes": [{"date": _fmt(n["created_at"]), "stage": n["stage"], "text": n["note"][:500]} for n in d["history"]["notes"] if n["created_at"][:10] >= week_ago][:10],
            "stage_moves": [{"date": _fmt(m["created_at"]), "from": m["prev_stage"], "to": m["stage"]} for m in moves],
            "plan_changes": [{"date": _fmt(c["created_at"]), "stage": c["stage"], "what": c["field"], "from": c["old"], "to": c["new"], "reason": c["reason"]}
                             for c in d.get("plan_changes", []) if c["created_at"][:10] >= week_ago][:8],
        },
        "open_risks_and_issues": [{"kind": r["kind"], "title": r["title"], "impact": r["impact"], "status": r["status"], "due": _fmt(r["due_date"])}
                                  for r in d["raid"] if r["open"]][:8],
        "tasks": {"open": d["work"]["total"] - d["work"]["done"], "done": d["work"]["done"], "total": d["work"]["total"],
                  "overdue": [{"title": t["title"], "due": _fmt(t["due_date"])} for t in open_tasks if t["late"]][:8],
                  "due_next_7_days": [{"title": t["title"], "due": _fmt(t["due_date"])} for t in open_tasks if not t["late"] and t["due_date"] and t["due_date"] <= soon][:8]},
        "waiting_on_customer": {"approval": {"stage": d["needs"]["approval"]["stage"], "asked": _fmt(d["needs"]["approval"]["requested_at"])} if d["needs"]["approval"] else None,
                                "tasks": [t["title"] for t in d["needs"]["tasks"]][:6]},
        "next_stages": [{"name": s["name"], "start": _fmt(s["forecast_start"]), "end": _fmt(s["forecast_end"])} for s in d["stages"] if s["status"] == "next"][:2],
    }


def fixture():
    """A synthetic rollout (never customer data): late, blocked at one site,
    an approval waiting, a scope question nobody logged, a named engineer in
    a note who must not be named in the words."""
    return {
        "today": "8 Oct 2026",
        "rollout": {"name": "SIEM onboarding", "client": "Northwind Clinics", "product": "Sentinel", "vendor": "Contoso Security",
                    "stage": "Design", "stage_number": "2 of 6", "percent_complete": 36, "health": "amber",
                    "health_reasons": ["Design is 3 working days over its 6-day SLA", "Forecast 4 days after the target"],
                    "target_date": "20 Oct 2026", "forecast_finish": "24 Oct 2026", "days_late_against_target": 4},
        "current_stage": {"name": "Design", "days_in_stage": 9, "sla_days": 6, "days_over_sla": 3},
        "this_week": {
            "notes": [{"date": "2 Oct 2026", "stage": "Design", "text": "Vendor delivered the firewall configuration, two days late. Ravi from their team says the next drop is on time."},
                      {"date": "3 Oct 2026", "stage": "Design", "text": "Customer asked whether the phase 2 scope can change. No decision yet."},
                      {"date": "6 Oct 2026", "stage": "Design", "text": "Site B cabling blocked: building access not granted yet."}],
            "stage_moves": [],
            "plan_changes": [{"date": "6 Oct 2026", "stage": "Design", "what": "end", "from": "2 Oct 2026", "to": "9 Oct 2026", "reason": "Vendor configuration late"}],
        },
        "open_risks_and_issues": [{"kind": "risk", "title": "Log volume above the licence", "impact": "medium", "status": "open", "due": None},
                                  {"kind": "blocker", "title": "No building access at Site B", "impact": "high", "status": "open", "due": "10 Oct 2026"}],
        "tasks": {"open": 7, "done": 4, "total": 11, "overdue": [{"title": "Approve design document", "due": "6 Oct 2026"}],
                  "due_next_7_days": [{"title": "Cable Site B racks", "due": "13 Oct 2026"}]},
        "waiting_on_customer": {"approval": {"stage": "Design", "asked": "29 Sep 2026"}, "tasks": ["Grant building access at Site B"]},
        "next_stages": [{"name": "Build", "start": "10 Oct 2026", "end": "17 Oct 2026"}],
    }


SCHEMA = {"type": "object", "required": ["summary", "next_steps", "asks"], "properties": {
    "summary": {"type": "string", "maxLength": 1200},
    "next_steps": {"type": "array", "minItems": 1, "maxItems": 5, "items": {"type": "string", "maxLength": 300}},
    "asks": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 300}},
}}


def as_words(output):
    """The report's three fields from an answer."""
    return {"summary": output["summary"].strip(), "next_steps": "\n".join(s.strip() for s in output["next_steps"] if s.strip()),
            "asks": "\n".join(s.strip() for s in output["asks"] if s.strip())}


FEATURE = register(AIFeature(
    key="weekly_words", label="Weekly words, drafted",
    description="Drafts the report's summary, next steps and asks from the rollout's week; the project manager edits and saves.",
    prompt="weekly_words.v1.txt", schema=SCHEMA, gather=gather, fixture=fixture,
    graders=(facts_kept("Site B", "20 Oct"), never_says("on track", "ahead of schedule", "no risks", "Ravi"),
             max_words("summary", 130), finds("asks", ["design", "access"], at_least=0.5)),
    runs="nightly", max_tokens=700,
))
