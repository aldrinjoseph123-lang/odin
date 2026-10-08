"""SLA calibration reasons: one sentence per SLA proposal (services/sla_calibration.py)
saying what the history shows. The proposals and their numbers are Odin's;
the AI only words them. Nightly; Settings shows the proposals with or
without the reasons."""
from services.ai import AIFeature, register
from services.ai.graders import facts_kept, never_says

SCHEMA = {"type": "object", "required": ["reasons"], "properties": {"reasons": {"type": "array", "maxItems": 40, "items": {"type": "string", "maxLength": 400}}}}


def gather():
    from services.ai.client import AIError
    from services.sla_calibration import proposals
    found = proposals()
    if not found:
        raise AIError("Every SLA matches its history", "skip")
    return {"proposals": [{**{k: p[k] for k in ("key", "template", "stage", "current", "proposed", "visits", "median", "p80", "unit")},
                           "today_vs_history": direction(p["current"], p["p80"])} for p in found[:20]]}


def direction(current, p80):
    """Which way the SLA is wrong, worked out here (the model once called a too-long SLA "exceeded")."""
    if not current:
        return "no SLA is set today"
    return "today's SLA is shorter than most rollouts achieve" if p80 > current else "today's SLA is longer than most rollouts need"


def refine(inputs, output):
    """Reasons keyed by proposal, so the page shows each next to its own numbers."""
    reasons = output.get("reasons") or []
    return {"reasons": {p["key"]: (reasons[i] if i < len(reasons) else None) for i, p in enumerate(inputs["proposals"])}}


def same_count(inputs, output):
    missing = [k for k, v in output["reasons"].items() if not v]
    return f"no reason for {len(missing)} proposal(s)" if missing else None


def fixture():
    return {"proposals": [
        {"key": "1:2:11", "template": "SIEM onboarding", "stage": "Design", "current": 6, "proposed": 11, "visits": 6, "median": 8, "p80": 11, "unit": "working days",
         "today_vs_history": "today's SLA is shorter than most rollouts achieve"},
        {"key": "1:5:3", "template": "SIEM onboarding", "stage": "Hand-over", "current": 10, "proposed": 3, "visits": 5, "median": 2, "p80": 3, "unit": "working days",
         "today_vs_history": "today's SLA is longer than most rollouts need"}]}


FEATURE = register(AIFeature(
    key="sla_calibration", label="SLA calibration",
    description="Says in one sentence per proposal what the history shows when a stage's SLA disagrees with how long the stage really takes.",
    prompt="sla_calibration.v3.txt", schema=SCHEMA, gather=gather, fixture=fixture, refine=refine,
    graders=(same_count, facts_kept("Design", "Hand-over", "8", "11", "6"), never_says("Kickoff", "4 of 5", "4 rollouts", "exceeded")),
    runs="nightly", scope="portfolio", budget_s=150, max_tokens=500, temperature=0.1, project_role=None,
))
