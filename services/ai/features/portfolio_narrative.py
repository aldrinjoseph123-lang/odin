"""Portfolio narrative: a short opening for the weekly report email, written
from the portfolio's figures (services/portfolio.py), the week's stage moves,
waiting approvals and open blockers. Nightly; the weekly report uses the
latest answer when the gate is open and it is recent, and leaves it out
otherwise (the email as it always was)."""
from datetime import datetime, timedelta

from services.ai import AIFeature, register
from services.ai.features.weekly_words import _fmt
from services.ai.graders import facts_kept, finds, max_words, never_says

SCHEMA = {"type": "object", "required": ["opening", "needs_decision"], "properties": {
    "opening": {"type": "string", "maxLength": 1200},
    "needs_decision": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 300}}}}


def gather():
    from db import PROJECT_OPEN_SQL, get_db
    from services import portfolio
    db = get_db()
    projects = db.execute(f"SELECT p.*, u.name AS owner_name FROM projects p LEFT JOIN users u ON u.id = p.owner_id "
                          f"WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} ORDER BY p.name").fetchall()
    folio = portfolio.build(projects)
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    moves = db.execute("SELECT p.name, n.prev_stage, n.stage FROM status_notes n JOIN projects p ON p.id = n.project_id "
                       "WHERE n.prev_stage IS NOT NULL AND n.created_at >= ? AND p.deleted_at IS NULL ORDER BY n.created_at", (week_ago,)).fetchall()
    approvals = db.execute("SELECT p.name, a.stage, a.requested_at FROM stage_approvals a JOIN projects p ON p.id = a.project_id "
                           "WHERE a.status = 'pending' AND p.deleted_at IS NULL ORDER BY a.requested_at").fetchall()
    rows = folio["rows"]   # red first, then amber, then green
    return {
        "counts": {"open_rollouts": folio["summary"]["count"], **{k: folio["summary"]["health"].get(k, 0) for k in ("green", "amber", "red")},
                   "late_against_target": folio["summary"]["late_vs_target"], "open_blockers": folio["summary"]["blockers"]},
        "rollouts": [{"name": r["name"], "client": r["client"], "health": r["rag"], "stage": r["stage"], "forecast": _fmt(r["forecast"]),
                      "target": _fmt(r["target_end_date"]), "days_late_against_target": r["vs_target_days"], "reasons": r["reasons"]}
                     for r in rows if r["rag"] in ("red", "amber")][:15]
                    + [{"name": r["name"], "health": r["rag"], "stage": r["stage"]} for r in rows if r["rag"] not in ("red", "amber")][:15],
        "stage_moves_this_week": [{"rollout": m["name"], "from": m["prev_stage"], "to": m["stage"]} for m in moves][:20],
        "approvals_waiting": [{"rollout": a["name"], "stage": a["stage"], "asked": _fmt(a["requested_at"])} for a in approvals][:10],
        "open_blockers": [{"rollout": r["project"], "title": r["title"]} for r in folio["risks"] if r["kind"] == "blocker"][:10],
    }


def fixture():
    """A synthetic portfolio of five: one red, one amber, three green; one
    stage move; one approval waiting; one blocker."""
    return {
        "counts": {"open_rollouts": 5, "green": 3, "amber": 1, "red": 1, "late_against_target": 2, "open_blockers": 1},
        "rollouts": [
            {"name": "Firewall refresh", "client": "Initech", "health": "red", "stage": "Deployment", "forecast": "12 Oct 2026", "target": "30 Sep 2026",
             "days_late_against_target": 12, "reasons": ["Past its target date by 8 d.", "1 open blocker."]},
            {"name": "SIEM onboarding", "client": "Northwind Clinics", "health": "amber", "stage": "Design", "forecast": "24 Oct 2026", "target": "20 Oct 2026",
             "days_late_against_target": 4, "reasons": ["Forecast to finish 4 d after the target date.", "Design is 3 d over its 6 d SLA."]},
            {"name": "EDR rollout", "health": "green", "stage": "Deployment"},
            {"name": "Email security", "health": "green", "stage": "Scoping"},
            {"name": "PAM pilot", "health": "green", "stage": "Kickoff"},
        ],
        "stage_moves_this_week": [{"rollout": "EDR rollout", "from": "Kickoff", "to": "Deployment"}],
        "approvals_waiting": [{"rollout": "SIEM onboarding", "stage": "Design", "asked": "29 Sep 2026"}],
        "open_blockers": [{"rollout": "Firewall refresh", "title": "Change window not approved by the customer"}],
    }


FEATURE = register(AIFeature(
    key="portfolio_narrative", label="Portfolio narrative",
    description="Writes the opening of the weekly report email: how the portfolio stands, what moved, what slipped, and what needs a decision.",
    prompt="portfolio_narrative.v1.txt", schema=SCHEMA, gather=gather, fixture=fixture,
    graders=(facts_kept("Firewall refresh", "SIEM", "EDR"), never_says("all rollouts are on track", "everything is on track"),
             max_words("opening", 110), finds("needs_decision", ["approv", "change window"], at_least=1.0)),
    runs="nightly", scope="portfolio", max_tokens=700, temperature=0.2, project_role=None,
))
