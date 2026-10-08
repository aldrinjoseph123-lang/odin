"""Risks proposed: risks, issues, blockers and decisions the notes imply but
nobody logged. Each proposal carries the note words that show it; Odin drops
any whose quote is not in a note, or that repeats an item already in the
register. The project manager adds one through the normal RAID dialog, or
dismisses it. Fallback: nothing (the register as it is)."""
import re
from datetime import timedelta

from services.ai import AIFeature, register
from services.ai.features.weekly_words import _fmt
from services.ai.graders import finds

LEVEL = {"type": "string", "enum": ["low", "medium", "high"]}
SCHEMA = {"type": "object", "required": ["proposals"], "properties": {"proposals": {"type": "array", "maxItems": 5, "items": {
    "type": "object", "required": ["kind", "title", "detail", "impact", "evidence"], "properties": {
        "kind": {"type": "string", "enum": ["risk", "issue", "blocker", "decision"]},
        "title": {"type": "string", "maxLength": 200}, "detail": {"type": "string", "maxLength": 800},
        "impact": LEVEL, "likelihood": LEVEL, "evidence": {"type": "string", "maxLength": 400}}}}}}


def gather(project_id):
    from db import get_db
    from policies import local_today
    from services import raid
    from services.ai.client import AIError
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    today = local_today()
    since = (today - timedelta(days=14)).isoformat()
    notes = db.execute("SELECT note, stage, created_at FROM status_notes WHERE project_id = ? AND prev_stage IS NULL AND created_at >= ? ORDER BY created_at DESC LIMIT 20",
                       (project_id, since)).fetchall()
    items = raid.items(project_id)
    t_iso = today.isoformat()
    overdue = db.execute("SELECT title, due_date FROM tasks WHERE project_id = ? AND done = 0 AND due_date < ? ORDER BY due_date LIMIT 8", (project_id, t_iso)).fetchall()
    approval = db.execute("SELECT stage, requested_at FROM stage_approvals WHERE project_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
    return {
        "today": _fmt(t_iso),
        "rollout": {"name": project["name"], "client": project["client"], "stage": project["stage"], "vendor": project["vendor_name"], "product": project["product_name"]},
        "notes": [{"date": _fmt(n["created_at"]), "stage": n["stage"], "text": n["note"][:800]} for n in notes],
        "already_logged": [{"kind": i["kind"], "title": i["title"], "status": i["status"]} for i in items if i["open"] or (i["closed_at"] or "") >= since][:30],
        "overdue_tasks": [{"title": t["title"], "due": _fmt(t["due_date"])} for t in overdue],
        "approval_waiting": {"stage": approval["stage"], "asked": _fmt(approval["requested_at"])} if approval else None,
    }


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def refine(inputs, output):
    """Keep only proposals whose evidence is really in a note and that do not
    repeat an item already logged (most of the title's words already there)."""
    notes = [_norm(n["text"]) for n in inputs["notes"]]
    logged = [_words(i["title"]) for i in inputs["already_logged"]]
    kept = []
    for p in output["proposals"]:
        quote = _norm(p.get("evidence", ""))
        if len(quote) < 8 or not any(quote in n for n in notes):
            continue
        title = _words(p["title"])
        if title and any(len(title & seen) >= max(2, 0.6 * len(title)) for seen in logged):
            continue
        if p["kind"] != "risk":
            p["likelihood"] = None
        kept.append(p)
        logged.append(title)   # and no two proposals for the same thing
    return {"proposals": kept}


def fixture():
    """A synthetic rollout: a late vendor and an open scope question are in
    the notes but not the register; Site B access is already logged."""
    return {
        "today": "8 Oct 2026",
        "rollout": {"name": "SIEM onboarding", "client": "Northwind Clinics", "stage": "Design", "vendor": "Contoso Security", "product": "Sentinel"},
        "notes": [
            {"date": "6 Oct 2026", "stage": "Design", "text": "Site B cabling blocked: building access not granted yet."},
            {"date": "3 Oct 2026", "stage": "Design", "text": "Customer asked whether the phase 2 scope can change to add the two clinics in the north. No decision yet; it would move the go-live."},
            {"date": "2 Oct 2026", "stage": "Design", "text": "Vendor delivered the firewall configuration two days late, the second late delivery this month. Ravi from their team says the next drop is on time."},
            {"date": "30 Sep 2026", "stage": "Design", "text": "Design workshop held; customer happy with the log source list."},
        ],
        "already_logged": [{"kind": "blocker", "title": "No building access at Site B", "status": "open"},
                           {"kind": "risk", "title": "Log volume above the licence", "status": "open"}],
        "overdue_tasks": [{"title": "Approve design document", "due": "6 Oct 2026"}],
        "approval_waiting": {"stage": "Design", "asked": "29 Sep 2026"},
    }


def says_nothing_logged_or_named(inputs, output):
    """Titles and details (not the quotes, which may name someone) never
    repeat a logged item or name a person."""
    text = " ".join(f"{p['title']} {p['detail']}" for p in output["proposals"]).lower()
    said = [w for w in ("building access", "log volume", "ravi") if w in text]
    return f"proposed \"{said[0]}\", which is already logged or names a person" if said else None


def on_new(db, project_id, output):
    """The night shift found things the register does not hold: one bell to
    the project manager, with the titles. Nothing when it found nothing."""
    from markupsafe import escape
    from services.notifications import notify_users
    found = output["proposals"]
    if not found:
        return
    project = db.execute("SELECT name, owner_id FROM projects WHERE id = ?", (project_id,)).fetchone()
    items = "".join(f"<li>{escape(p['title'])}</li>" for p in found)
    notify_users([project["owner_id"]], "alert", project_id, f"AI noticed {len(found)} thing{'s' if len(found) != 1 else ''} in the notes of {escape(project['name'])} that the register does not hold",
                 f"<ul>{items}</ul><p>Each comes with the note words behind it. Add or dismiss them on the RAID panel.</p>",
                 link=f"/projects/{project_id}#raid", email=False)


FEATURE = register(AIFeature(
    key="raid_proposals", label="Risks proposed",
    description="Reads the last two weeks of notes and proposes risks, issues, blockers and decisions nobody has logged, each with the note words that show it.",
    prompt="raid_proposals.v1.txt", schema=SCHEMA, gather=gather, fixture=fixture, refine=refine,
    graders=(finds("proposals", ["scope", "vendor"], at_least=1.0), says_nothing_logged_or_named),
    runs="nightly", max_tokens=600, temperature=0.2, project_role="manage_tasks", on_new=on_new,
))
