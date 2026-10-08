"""Meeting notes to tasks: the actions agreed in pasted minutes, each with the
words that state it, an owner from the project's own team, a stage from its
own list and a due date read by Odin (not the model). The project manager
ticks the ones to add; each goes through the normal task route. On demand."""
import re
from datetime import date

from services.ai import AIFeature, register
from services.ai.features.sow_plan import _norm, _supported
from services.ai.graders import finds

SCHEMA = {"type": "object", "required": ["tasks"], "properties": {"tasks": {"type": "array", "maxItems": 12, "items": {
    "type": "object", "required": ["title", "quote"], "properties": {
        "title": {"type": "string", "maxLength": 200}, "owner": {"type": "string", "maxLength": 120}, "stage": {"type": "string", "maxLength": 120},
        "due": {"type": "string", "maxLength": 60}, "quote": {"type": "string", "maxLength": 400}}}}}}
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}


def read_date(text, today):
    """A due date as minutes write it, read by code: "13 Oct", "13 October
    2026", "2026-10-13", "13/10/2026" (day first). The next such date on or
    after today when the year is missing; None when it is not a date."""
    t = str(text or "").strip().lower()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t)
    if m:
        return _safe(int(m[3]), int(m[2]), int(m[1]))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*\.?(?:\s+(\d{4}))?", t)
    if m and m[2] in MONTHS:
        year = int(m[3]) if m[3] else today.year
        d = _safe(year, MONTHS[m[2]], int(m[1]))
        if d and not m[3] and d < today:
            d = _safe(year + 1, MONTHS[m[2]], int(m[1]))
        return d
    return None


def _safe(y, mo, d):
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _after_by(quote):
    """The date part of an action: what follows "by", "before", "due" or "on"."""
    m = re.search(r"\b(?:by|before|due|on|until)\s+(.{3,30})", str(quote), re.I)
    return m.group(1) if m else ""


def gather(project_id, given=None):
    from db import get_db, get_stage_names, participants_for
    from services.ai.client import AIError
    db = get_db()
    if db.execute("SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone() is None:
        raise AIError("The rollout no longer exists", "gate")
    text = str((given or {}).get("text") or "").strip()[:3500]
    if len(text) < 20:
        raise AIError("Paste the minutes first", "skip")
    team = [{"name": p["name"], "role": p["role"]} for p in participants_for(project_id) if p["active"]]
    return {"stages": get_stage_names(project_id), "people": team, "minutes": text,
            "_ids": {p["name"]: p["user_id"] for p in participants_for(project_id) if p["active"]}}


def refine(inputs, output):
    """Keep actions the minutes really state; owner only from the team, stage
    only from the list, the date read here."""
    from policies import local_today
    text = _norm(inputs["minutes"])
    words = set(text.split())
    stages = {s.lower(): s for s in inputs["stages"]}
    ids = inputs.get("_ids", {})
    by_lower = {n.lower(): n for n in ids}
    first = {}
    for n in ids:
        first.setdefault(n.split()[0].lower(), []).append(n)
    today = local_today()
    out, seen = [], set()
    for t in output.get("tasks") or []:
        title = str(t.get("title") or "").strip()
        if not title or not _supported(t.get("quote", ""), text, words) or _norm(title) in seen:
            continue
        seen.add(_norm(title))
        owner = str(t.get("owner") or "").strip().lower()
        name = by_lower.get(owner) or (first.get(owner.split()[0])[0] if owner and len(first.get(owner.split()[0], [])) == 1 else None)
        due = read_date(t.get("due"), today) or read_date(_after_by(t.get("quote", "")), today)   # the model often leaves "due" empty; the quote says it
        out.append({"title": title[:200], "owner": name, "assignee_id": ids.get(name), "stage": stages.get(str(t.get("stage") or "").lower()),
                    "due_date": due.isoformat() if due else None, "due_text": t.get("due") or "", "quote": t.get("quote", "")})
    return {"tasks": out}


def dated(inputs, output):
    cable = next((t for t in output["tasks"] if "cable" in t["title"].lower()), None)
    return None if cable and cable["due_date"] and cable["due_date"].endswith("-10-13") else "the cabling action lost its date (13 Oct)"


def owners_right(inputs, output):
    by = {t["title"].lower(): t["owner"] for t in output["tasks"]}
    cable = next((o for title, o in by.items() if "cable" in title), "missing")
    return None if cable == "Omar Haddad" else f"the cabling action went to {cable!r}, not Omar Haddad"


def fixture():
    return {"stages": ["Kickoff", "Design", "Build", "UAT", "Hand-over", "Closed"],
            "people": [{"name": "Sam Rivera", "role": "Project manager"}, {"name": "Omar Haddad", "role": "Coordinator"}, {"name": "Ann Lee", "role": "Customer"}],
            "minutes": "Weekly call, 8 Oct. Present: Sam, Omar, Ann.\n"
                       "1. Site B: Omar to cable the Site B racks by 13 Oct once access is granted.\n"
                       "2. Ann will send the log samples from the clinic firewalls by Friday 10 Oct.\n"
                       "3. Sam to update the design document with the new retention period.\n"
                       "4. We agreed the retention period: 90 days hot, 1 year archive.\n"
                       "5. Next call on Tuesday.",
            "_ids": {"Sam Rivera": 1, "Omar Haddad": 2, "Ann Lee": 3}}


FEATURE = register(AIFeature(
    key="notes_to_tasks", label="Meeting notes to tasks",
    description="Finds the actions agreed in pasted meeting minutes and suggests them as tasks with owner, stage and due date, each with the words that state it.",
    prompt="notes_to_tasks.v1.txt", schema=SCHEMA, gather=gather, fixture=fixture, refine=refine,
    graders=(finds("tasks", ["cable", "log sample", "design document"], at_least=1.0), owners_right, dated),
    runs="on_demand", budget_s=150, max_tokens=700, temperature=0.1, takes_input=True, project_role="manage_tasks",
))
