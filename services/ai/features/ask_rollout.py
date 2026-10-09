"""Ask this rollout: a question about one rollout, answered only from the
passages Odin finds in its notes, RAID, scope, tasks, plan changes and
uploaded documents (a keyword search, no embeddings: the AI server has no
embedding model). The answer cites its passages by number; Odin turns the
numbers into links and drops any it did not give. On demand, staff only."""
import re

from services.ai import AIFeature, register
from services.ai.features.weekly_words import _fmt
from services.ai.graders import facts_kept

SCHEMA = {"type": "object", "required": ["answer", "sources", "found"], "properties": {
    "answer": {"type": "string", "maxLength": 1200}, "sources": {"type": "array", "maxItems": 12, "items": {"type": "integer"}},
    "found": {"type": "boolean"}}}
STOP = set("the a an and or of to in on for is are was were be been it its this that with at by from as what why when who how which did does do has have had "
           "about any there their they them we our you your not no yes can could should would will".split())
BUDGET, MOST = 2200, 8   # characters and passages per question: more made answers slow (188 s for 12) without making them better


def _words(text):
    return {w for w in re.findall(r"[a-z0-9][a-z0-9-]+", str(text).lower()) if w not in STOP and len(w) > 2}


def passages(project_id, db):
    """Every piece of the rollout's record, as (kind, label, href, text)."""
    from services import plan as plan_service, raid
    from services.signoff import scope
    out = []
    for n in db.execute("SELECT note, stage, author, created_at FROM status_notes WHERE project_id = ? AND prev_stage IS NULL ORDER BY created_at DESC LIMIT 200", (project_id,)):
        out.append(("note", f"note, {_fmt(n['created_at'])}, {n['author']}", f"/projects/{project_id}", n["note"]))
    for r in raid.items(project_id):
        out.append(("risk", f"{r['kind']}: {r['title']}", f"/projects/{project_id}#raid",
                    f"{r['kind']} ({r['status']}, {r['impact']} impact): {r['title']}. {r['detail'] or ''} {r['resolution'] or ''}"))
    for s in scope(project_id):
        out.append(("scope", f"scope: {s['title']}", f"/projects/{project_id}#scope", f"Scope item ({s['status']}): {s['title']}. {s['detail'] or ''} {s['note'] or ''}"))
    for t in db.execute("SELECT title, done, due_date, stage FROM tasks WHERE project_id = ? ORDER BY id DESC LIMIT 200", (project_id,)):
        out.append(("task", f"task: {t['title']}", f"/board?rollout={project_id}",
                    f"Task ({'done' if t['done'] else 'open'}{', due ' + _fmt(t['due_date']) if t['due_date'] else ''}, {t['stage'] or 'current stage'}): {t['title']}"))
    for c in plan_service.changes(project_id, 50):
        out.append(("plan", f"plan change, {_fmt(c['created_at'])}", f"/projects/{project_id}#plan",
                    f"Plan change on {_fmt(c['created_at'])}: {c['stage']} {c['field']} moved from {c['old']} to {c['new']}. Reason: {c['reason'] or 'none given'}"))
    for d in db.execute("SELECT d.filename, t.text FROM doc_text t JOIN documents d ON d.id = t.document_id AND d.deleted_at IS NULL WHERE t.project_id = ? AND t.text != ''",
                        (project_id,)):
        text = d["text"]
        for i in range(0, min(len(text), 40_000), 700):   # a document in short pieces, so the right paragraph can be picked
            out.append(("document", f"document: {d['filename']}", f"/projects/{project_id}", text[i:i + 800]))
    return out


def gather(project_id, given=None):
    from db import get_db
    from services import portfolio
    from services.ai.client import AIError
    from services.ai.features.morning_brief import status_words
    db = get_db()
    project = db.execute("SELECT p.*, u.name AS owner_name FROM projects p LEFT JOIN users u ON u.id = p.owner_id WHERE p.id = ? AND p.deleted_at IS NULL",
                         (project_id,)).fetchone()
    if project is None:
        raise AIError("The rollout no longer exists", "gate")
    question = str((given or {}).get("question") or "").strip()[:300]
    if len(question) < 5:
        raise AIError("Ask a question first", "skip")
    want = _words(question)
    scored = []
    for i, (kind, label, href, text) in enumerate(passages(project_id, db)):
        hits = len(want & _words(text + " " + label))
        if hits:
            scored.append((hits, -i, kind, label, href, text))
    scored.sort(reverse=True)
    chosen, used = [], 0
    for hits, _i, kind, label, href, text in scored:
        if used + len(text) > BUDGET or len(chosen) >= MOST:
            continue
        chosen.append({"n": len(chosen) + 1, "from": label, "text": " ".join(text.split())[:800], "kind": kind, "href": href})
        used += len(text)
    row = portfolio.build([project])["rows"][0]
    return {"question": question,
            "rollout": f"{project['name']} for {project['client']}: {project['stage']}, {row['rag']} ({status_words(row)}), go-live {_fmt(project['target_end_date'])}.",
            "passages": [{"n": c["n"], "from": c["from"], "text": c["text"]} for c in chosen], "_links": [{k: c[k] for k in ("n", "kind", "from", "href")} for c in chosen]}


def refine(inputs, output):
    """Only passages Odin gave count as sources; each becomes a link."""
    links = {c["n"]: c for c in inputs.get("_links", [])}
    groups = re.findall(r"\[([\d,\s]+)\]", output["answer"])           # "[2]" and "[1, 5, 7]"
    cited = [int(n) for g in groups for n in re.findall(r"\d+", g)]
    used = [n for n in dict.fromkeys([*output.get("sources", []), *cited]) if n in links]

    def keep(m):
        ok = [n for n in re.findall(r"\d+", m.group(1)) if int(n) in links]
        return f"[{', '.join(ok)}]" if ok else ""
    answer = re.sub(r"\[([\d,\s]+)\]", keep, output["answer"])
    return {"question": inputs["question"], "answer": answer.strip(), "found": bool(output.get("found")) and bool(used),
            "sources": [links[n] for n in used]}


def cites_its_source(inputs, output):
    return None if output["found"] and any(s["n"] == 2 for s in output["sources"]) else "did not cite the passage that answers it"


def fixture():
    links = [{"n": 1, "kind": "note", "from": "note, 6 Oct 2026, Omar", "href": "/projects/1"},
             {"n": 2, "kind": "plan", "from": "plan change, 6 Oct 2026", "href": "/projects/1#plan"},
             {"n": 3, "kind": "note", "from": "note, 2 Oct 2026, Sam", "href": "/projects/1"}]
    return {"question": "Why did the Design stage slip?",
            "rollout": "SIEM onboarding for Northwind Clinics: Design, amber (Design is 3 d over its 6 d SLA), go-live 20 Oct 2026.",
            "passages": [{"n": 1, "from": "note, 6 Oct 2026, Omar", "text": "Site B cabling blocked: building access not granted yet."},
                         {"n": 2, "from": "plan change, 6 Oct 2026", "text": "Plan change on 6 Oct 2026: Design end moved from 2 Oct 2026 to 9 Oct 2026. Reason: Vendor configuration late"},
                         {"n": 3, "from": "note, 2 Oct 2026, Sam", "text": "Vendor delivered the firewall configuration two days late."}],
            "_links": links}


FEATURE = register(AIFeature(
    key="ask_rollout", label="Ask this rollout",
    description="Answers a question about a rollout from its own notes, risks, scope, tasks, plan changes and documents, citing each passage it used.",
    prompt="ask_rollout.v1.txt", schema=SCHEMA, gather=gather, fixture=fixture, refine=refine,
    graders=(facts_kept("vendor", "9 Oct"), cites_its_source),
    runs="on_demand", budget_s=150, max_tokens=350, temperature=0.1, takes_input=True, project_role=None,
))
