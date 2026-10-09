"""Catch me up: a one-page brief on a rollout for a stand-in project manager,
a new joiner or a manager before a call: where it stands (Odin's status
words), who is who, what changed and why, what waits on whom, what to watch.
On demand from the project page, for every staff member who sees the rollout.
Fallback: the project page itself."""
import re

from services.ai import AIFeature, register
from services.ai.features.weekly_words import _fmt
from services.ai.graders import facts_kept, max_words, never_says

SCHEMA = {"type": "object", "required": ["where_it_stands", "who_is_who", "what_changed", "watch_out"], "properties": {
    "where_it_stands": {"type": "string", "maxLength": 800}, "who_is_who": {"type": "string", "maxLength": 600},
    "what_changed": {"type": "string", "maxLength": 800},
    "watch_out": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 300}}}}


GUESS = re.compile(r"[,;—-]?\s*(?:which|that|this|and)?\s*(?:could|may|might|would)\s+(?:cause|lead|result|impact|affect|delay|mean)[^.;]*", re.I)


def _no_guesses(text):
    """A small model adds "which could cause …" to facts; Odin keeps the fact."""
    return re.sub(r"\s+([.;])", r"\1", GUESS.sub("", text)).strip()


def refine(inputs, output):
    """Who is waited on is Odin's to say, not the model's (it once put the
    customer's approval on a colleague): the lines go into the answer as Odin
    wrote them. Guessed consequences are trimmed from every sentence."""
    out = {k: _no_guesses(v) if isinstance(v, str) else v for k, v in output.items()}
    words = lambda t: {w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 2}   # noqa: E731
    waiting = [words(w) for w in inputs["waiting"]]
    # a watch-out that only repeats a waiting line is dropped (the model repeats them)
    out["watch_out"] = [x for x in (_no_guesses(x) for x in output.get("watch_out", []))
                        if not any(len(words(x) & w) >= 0.6 * max(1, len(words(x))) for w in waiting)]
    return {**out, "waiting": inputs["waiting"]}


def waiting_lines(customer, items, overdue):
    """Finished lines: who is waited on, for what, since when."""
    out = [f"{customer} (customer): {w['what'].lower() if w['what'].startswith('Approval') else w['what']}, "
           + (f"asked {w['since']}, {w['days_waiting']} d waiting" if "days_waiting" in w else f"due {w['due']}, {w['days_overdue']} d overdue") for w in items]
    out += [f"{t['owner']}: {t['task']}, due {t['due']}" for t in overdue]
    return out[:8]


def _date_or(value):
    """A plan change's value: dates read like every other date ("29 Sep 2026")."""
    return _fmt(value) if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)) else value


def gather(project_id):
    from db import get_db, participants_for
    from policies import local_today
    from services import portfolio, plan as plan_service, raid
    from services.ai.client import AIError
    from services.ai.features.chase_draft import waiting
    from services.ai.features.morning_brief import status_words
    db = get_db()
    project = db.execute("SELECT p.*, u.name AS owner_name FROM projects p LEFT JOIN users u ON u.id = p.owner_id WHERE p.id = ? AND p.deleted_at IS NULL",
                         (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    row = portfolio.build([project])["rows"][0]
    today = local_today().isoformat()
    overdue = db.execute("SELECT t.title, t.due_date, u.name AS who FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id "
                         "WHERE t.project_id = ? AND t.done = 0 AND t.due_date < ? ORDER BY t.due_date LIMIT 6", (project_id, today)).fetchall()
    notes = db.execute("SELECT note, created_at, author FROM status_notes WHERE project_id = ? AND prev_stage IS NULL ORDER BY created_at DESC LIMIT 6",
                       (project_id,)).fetchall()
    return {
        "rollout": {"name": project["name"], "client": project["client"], "product": project["product_name"], "vendor": project["vendor_name"],
                    "stage": f"{project['stage']} (stage {row['stage_number']} of {row['stage_count']})", "go_live": _fmt(project["target_end_date"]),
                    "health": row["rag"], "status": status_words(row)},
        "team": [{"name": p["name"], "role": p["role"]} for p in participants_for(project_id) if p["active"]][:12],
        "plan_changes": [{"date": _fmt(c["created_at"]), "stage": c["stage"], "what": c["field"], "from": _date_or(c["old"]), "to": _date_or(c["new"]), "reason": c["reason"]}
                         for c in plan_service.changes(project_id, 8)],
        "waiting": waiting_lines(next((p["name"] for p in participants_for(project_id) if p["role"] == "Customer" and p["active"]), "The customer"),
                                 waiting(project_id, db), [{"task": t["title"], "owner": t["who"] or "Nobody (unassigned)", "due": _fmt(t["due_date"])} for t in overdue]),
        "open_risks_and_issues": [{"kind": r["kind"], "title": r["title"], "impact": r["impact"]} for r in raid.items(project_id) if r["open"]][:8],
        "latest_notes": [{"date": _fmt(n["created_at"]), "by": n["author"], "text": n["note"][:400]} for n in notes],
    }


def fixture():
    """A synthetic rollout to hand over."""
    return {
        "rollout": {"name": "SIEM onboarding", "client": "Northwind Clinics", "product": "Sentinel", "vendor": "Contoso Security",
                    "stage": "Design (stage 2 of 6)", "go_live": "20 Oct 2026", "health": "amber",
                    "status": "Design is 3 d over its 6 d SLA; forecast 4 d after the target"},
        "team": [{"name": "Sam Rivera", "role": "Project manager"}, {"name": "Omar Haddad", "role": "Coordinator"},
                 {"name": "Ann Lee", "role": "Customer"}],
        "plan_changes": [{"date": "6 Oct 2026", "stage": "Design", "what": "end", "from": "2 Oct 2026", "to": "9 Oct 2026", "reason": "Vendor configuration late"}],
        "waiting": ["Ann Lee (customer): approval of the Design stage, asked 29 Sep 2026, 9 d waiting", "Omar Haddad: Cable Site B racks, due 6 Oct 2026"],
        "open_risks_and_issues": [{"kind": "blocker", "title": "No building access at Site B", "impact": "high"},
                                  {"kind": "risk", "title": "Log volume above the licence", "impact": "medium"}],
        "latest_notes": [{"date": "6 Oct 2026", "by": "Omar Haddad", "text": "Site B cabling blocked: building access not granted yet."},
                         {"date": "3 Oct 2026", "by": "Sam Rivera", "text": "Customer asked whether the phase 2 scope can change. No decision yet."}],
    }


FEATURE = register(AIFeature(
    key="catch_up", label="Catch me up",
    description="A one-page brief on a rollout for whoever takes it over or joins: where it stands, who is who, what changed and why, what waits on whom, what to watch.",
    prompt="catch_up.v3.txt", schema=SCHEMA, gather=gather, fixture=fixture, refine=refine,
    graders=(facts_kept("Sam Rivera", "Ann Lee", "Design", "29 Sep", "Site B", "vendor"), never_says("on track", "4 days over", "4 d over", "could cause", "may lead to", "cost overrun"),
             max_words("where_it_stands", 70), max_words("what_changed", 70)),
    runs="on_demand", budget_s=150, max_tokens=500, temperature=0.2, project_role=None,
))
