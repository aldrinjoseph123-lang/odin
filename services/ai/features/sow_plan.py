"""Scope of work → suggested plan. The PO and scope of work uploaded to a
rollout are read (services/doctext.py) and, part by part, turned into scope
items, tasks on the rollout's own stages, the customer's obligations, key
dates and exclusions, each with the document words that state it. Odin drops
what the text does not support, anything commercial, tasks on stages the
rollout does not have, and repeats. The project manager ticks what to keep;
each is added through the normal scope and task routes. On demand. Fallback:
nothing (the plan is typed by hand, as before)."""
import re

from services.ai import AIFeature, register
from services.ai.graders import finds

def _chunk_size():
    """Characters of document text per request: the input cap (policy
    ai_max_input_chars) less room for the rollout and its stage names."""
    from policies import policy
    return max(1500, policy("ai_max_input_chars") - 700)
ITEM = {"type": "object", "required": ["title"], "properties": {"title": {"type": "string", "maxLength": 300}, "detail": {"type": "string", "maxLength": 600},
                                                                  "stage": {"type": "string", "maxLength": 120}, "quote": {"type": "string", "maxLength": 600}}}
SCHEMA = {"type": "object", "required": ["scope_items", "tasks", "customer_obligations", "key_dates", "exclusions"], "properties": {
    "scope_items": {"type": "array", "maxItems": 25, "items": ITEM},
    "tasks": {"type": "array", "maxItems": 30, "items": ITEM},
    "customer_obligations": {"type": "array", "maxItems": 15, "items": ITEM},
    "key_dates": {"type": "array", "maxItems": 15, "items": {"type": "object", "required": ["what", "date"], "properties": {
        "what": {"type": "string", "maxLength": 200}, "date": {"type": "string", "maxLength": 60}}}},
    "exclusions": {"type": "array", "maxItems": 15, "items": {"type": "string", "maxLength": 300}}}}
MONEY = re.compile(r"(\b(AED|USD|EUR|GBP|SAR|QAR|INR)\b|[$€£]\s?\d|\b\d[\d,.]*\s?(AED|USD|EUR|GBP|dirhams?|dollars?)\b)", re.I)
SOW_WORDS = re.compile(r"scope|sow|statement of work|proposal|quotation|\bpo\b|purchase", re.I)


def documents(project_id):
    """The rollout's readable documents, the PO and scope-like ones first,
    for the page to choose from."""
    from db import get_db
    from services.doctext import READABLE
    rows = get_db().execute("SELECT id, filename, category, uploaded_at FROM documents WHERE project_id = ? AND deleted_at IS NULL AND review_status = 'accepted' ORDER BY uploaded_at DESC",
                            (project_id,)).fetchall()
    out = [{"id": r["id"], "filename": r["filename"], "category": r["category"],
            "likely": bool(r["category"] == "Client PO" or SOW_WORDS.search(r["filename"]))}
           for r in rows if r["filename"].rsplit(".", 1)[-1].lower() in READABLE]
    return {"documents": sorted(out, key=lambda d: not d["likely"])}


def gather(project_id, given=None):
    from db import get_db, get_stage_names
    from services.ai.client import AIError
    from services.doctext import text_of
    db = get_db()
    project = db.execute("SELECT name, client, product_name, vendor_name FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    ids = [int(i) for i in (given or {}).get("document_ids") or [] if str(i).isdigit()]
    if not ids:
        ids = [d["id"] for d in documents(project_id)["documents"] if d["likely"]][:3]
    docs, problems = [], []
    for row in db.execute(f"SELECT id, filename FROM documents WHERE project_id = ? AND deleted_at IS NULL AND id IN ({','.join('?' * len(ids)) or 'NULL'})",
                          (project_id, *ids)).fetchall():
        text, error = text_of(row["id"], db)
        if text:
            docs.append(f"=== {row['filename']} ===\n{text}")
        else:
            problems.append(f"{row['filename']}: {error}")
    if not docs:
        raise AIError("No readable text in the chosen documents" + (f" ({'; '.join(problems)})" if problems else ""), "skip")
    return {"rollout": {"name": project["name"], "client": project["client"], "product": project["product_name"], "vendor": project["vendor_name"]},
            "stages": get_stage_names(project_id), "text": "\n\n".join(docs)[:60_000]}


def chunks(inputs):
    """The text in parts that fit one request, cut at paragraph breaks."""
    size = _chunk_size()
    pieces = []
    for para in inputs["text"].split("\n"):   # a paragraph longer than a part (a PDF without line breaks) is cut into parts too
        pieces += [para[i:i + size] for i in range(0, len(para), size)] or [""]
    parts, cur = [], ""
    for piece in pieces:
        if len(cur) + len(piece) > size and cur:
            parts.append(cur)
            cur = ""
        cur += piece + "\n"
    if cur.strip():
        parts.append(cur)
    return [{**inputs, "text": p, "part": f"{i + 1} of {len(parts)}"} for i, p in enumerate(parts)]


def merge(outputs):
    out = {k: [] for k in SCHEMA["properties"]}
    for o in outputs:
        for k in out:
            out[k] += o.get(k) or []
    return out


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(s).lower())).strip()


def _supported(quote, text_norm, words):
    q = _norm(quote)
    if len(q) < 6:
        return False
    if q in text_norm:
        return True
    qw = [w for w in q.split() if len(w) > 2]
    return bool(qw) and sum(w in words for w in qw) / len(qw) >= 0.85   # small reformatting (line breaks, bullets) allowed


def refine(inputs, output):
    text = _norm(inputs["text"])
    words = set(text.split())
    stages = {s.lower(): s for s in inputs["stages"]}
    out = {k: [] for k in SCHEMA["properties"]}
    for key in ("scope_items", "tasks", "customer_obligations"):
        seen = set()
        for item in output.get(key) or []:
            title = str(item.get("title") or "").strip()
            if not title or MONEY.search(title + " " + str(item.get("detail") or "")) or not _supported(item.get("quote", ""), text, words):
                continue
            if _norm(title) in seen:
                continue
            seen.add(_norm(title))
            if key == "tasks":
                item["stage"] = stages.get(str(item.get("stage") or "").strip().lower())   # None: the stage the rollout is in
            out[key].append(item)
    out["key_dates"] = [d for d in output.get("key_dates") or [] if not MONEY.search(d.get("what", ""))][:15]
    out["exclusions"] = list(dict.fromkeys(x for x in output.get("exclusions") or [] if x and not MONEY.search(x)))[:15]
    return out


def fixture():
    """A synthetic short scope of work, with a price that must not come through."""
    return {"rollout": {"name": "EDR rollout", "client": "Globex", "product": "Defender for Endpoint", "vendor": "Contoso"},
            "stages": ["Kickoff", "Design", "Deployment", "Tuning", "Hand-over", "Closed"],
            "text": "=== Globex SOW v2.pdf ===\n"
                    "1. Scope. Protect24x7 will deploy endpoint detection and response to 500 Windows endpoints across the Dubai and Abu Dhabi offices.\n"
                    "2. Deliverables. A design document approved by Globex. Onboarding of all 500 endpoints in two waves. Tuning of detection policies for 30 days. "
                    "An operations runbook and a hand-over session for the Globex IT team.\n"
                    "3. Customer responsibilities. Globex will provide local admin credentials and a maintenance window for each wave, and approve the design "
                    "within 5 working days of receipt.\n"
                    "4. Out of scope. Mac and Linux endpoints. Server workloads.\n"
                    "5. Timeline. Kick-off on 12 Oct 2026; wave 1 complete by 30 Oct 2026; hand-over by 15 Dec 2026.\n"
                    "6. Fees. The total fixed fee is AED 184,000, payable 50% at kick-off."}


FEATURE = register(AIFeature(
    key="sow_plan", label="Plan from the scope of work",
    description="Reads the PO and scope of work and suggests scope items, tasks per stage, the customer's obligations, key dates and exclusions; the project manager ticks what to keep.",
    prompt="sow_plan.v1.txt", schema=SCHEMA, gather=gather, fixture=fixture, refine=refine, chunks=chunks, merge=merge, options=documents,
    graders=(finds("scope_items", ["500", "design", "runbook"], at_least=0.67), finds("customer_obligations", ["credential", "window", "approv"], at_least=0.67),
             finds("exclusions", ["mac"], at_least=1.0), lambda inputs, out: "a price came through" if "184" in str(out) else None),
    runs="on_demand", budget_s=200, max_tokens=1000, temperature=0.1, takes_input=True, project_role="manage_project",
))
