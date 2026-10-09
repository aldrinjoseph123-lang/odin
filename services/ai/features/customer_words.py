"""Tidy for the customer: the project manager's report words, rewritten so
the customer can read them (names, blame, remarks and internal shorthand
out; every fact kept; nothing added). Works on the words as typed on the
report page, on demand; the project manager reviews the result before
saving. Fallback: the words as written."""
import re

from services.ai import AIFeature, register
from services.ai.graders import facts_kept, max_words, never_says

SCHEMA = {"type": "object", "required": ["summary", "next_steps", "asks"], "properties": {
    "summary": {"type": "string", "maxLength": 6000},
    "next_steps": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 500}},
    "asks": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 500}}}}


def _lines(text):
    return [x.strip() for x in str(text or "").splitlines() if x.strip()]


DATES_AND_NUMBERS = re.compile(r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?: \d{4})?\b|\b\d{4}-\d{2}-\d{2}\b|\b\d+(?:[.,]\d+)?\s?(?:%|days?|d|hours?|weeks?|sites?|endpoints?|users?)?\b")


def must_keep(words):
    """The dates and numbers in the words, found by Odin, not the model: the
    model is told to keep every one, and validation checks it did."""
    text = " ".join([words["summary"], *words["next_steps"], *words["asks"]])
    return list(dict.fromkeys(m.group(0).strip() for m in DATES_AND_NUMBERS.finditer(text) if not m.group(0).strip().isdigit() or len(m.group(0).strip()) > 1))[:20]


def gather(project_id, given=None):
    from db import get_db
    from services.ai.client import AIError
    project = get_db().execute("SELECT name, client FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    given = given or {}
    if not str(given.get("summary") or "").strip():
        raise AIError("Write the summary first; there is nothing to tidy", "skip")
    words = {"summary": str(given["summary"])[:6000], "next_steps": _lines(given.get("next_steps"))[:12], "asks": _lines(given.get("asks"))[:12]}
    return {"rollout": {"name": project["name"], "client": project["client"]}, "words": words, "must_keep": must_keep(words)}


def fixture():
    """Words a tired project manager might write at 17:55."""
    f = {"rollout": {"name": "SIEM onboarding", "client": "Northwind Clinics"},
            "words": {"summary": "Design slipped again because Ravi at Contoso was useless with the FW config, 2 days late. Customer still sitting on the "
                                 "design approval since 29 Sep (typical). Site B blocked, no access to the building. Go-live 20 Oct now at risk, forecast 24 Oct.",
                      "next_steps": ["Chase Northwind for the approval", "Get Ravi to fix the FW config", "Cable Site B racks once in"],
                      "asks": ["Approve the design doc ASAP", "Building access for Site B"]}}
    f["must_keep"] = must_keep(f["words"])
    return f


FEATURE = register(AIFeature(
    key="customer_words", label="Tidy for the customer",
    description="Rewrites the report's words, as typed, so the customer can read them: names, blame and shorthand out, every fact kept, nothing added.",
    prompt="customer_words.v4.txt", schema=SCHEMA, gather=gather, fixture=fixture,
    graders=(facts_kept("Site B", "20 Oct", "24 Oct", "29 Sep", "approv"), never_says("Ravi", "useless", "typical", "sitting on", "ASAP"),
             max_words("summary", 75)),
    runs="on_demand", max_tokens=600, temperature=0.2, takes_input=True,
))
