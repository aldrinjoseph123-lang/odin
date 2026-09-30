"""The agreed scope of a rollout and the sign-off document that closes it.

Scope items are recorded while scoping (agreed) and marked delivered,
partial or descoped at the end. The sign-off document lists them — or, when
no scope was recorded, what was delivered, drafted from the stages, tasks
and deliverables — with the outstanding items, the handover terms and the
acceptance statement.

A version is frozen when it is sent: its content is stored as canonical
JSON with a SHA-256 fingerprint, and every signature is checked against it.
The customer signs (or rejects with comments, which become an open issue),
then we countersign. A signed paper copy can be uploaded instead, and an
admin can waive the lot with a written reason. Until one of those three
completes a version, the project cannot reach its terminal stage
(`gate`, called by every stage move) while the policy asks for sign-off.
"""
import hashlib
import json
from datetime import datetime

from constants import SIGNOFF_STAGE
from db import get_db, get_stage_names, get_terminal_stage, participants_for
from policies import local_date, local_today, policy
from services import plan as plan_service
from services import raid as raid_service

SCOPE_STATUSES = ("agreed", "delivered", "partial", "descoped")
OPEN = ("sent", "signed")
DONE = ("countersigned", "uploaded", "waived")
SIGNER_ROLES = ("Customer", "Reseller")


def _now():
    return datetime.utcnow().isoformat()


def _fmt(iso):
    if not iso:
        return "—"
    d = datetime.fromisoformat(iso[:10])
    return f"{d.day} {d.strftime('%b %Y')}"


# ---- scope -----------------------------------------------------------------

def scope(project_id):
    return [dict(r) for r in get_db().execute(
        "SELECT id, title, detail, status, note, position FROM scope_items WHERE project_id = ? ORDER BY position, id", (project_id,))]


def clean_scope(body, existing=None):
    """Validated fields from a posted body, or raise ValueError."""
    title = str(body.get("title", existing["title"] if existing else "") or "").strip()[:300]
    if not title:
        raise ValueError("Give the scope item a title")
    status = body.get("status", existing["status"] if existing else "agreed")
    if status not in SCOPE_STATUSES:
        raise ValueError("Status is agreed, delivered, partial or descoped")
    note = str(body.get("note", existing["note"] if existing else "") or "").strip()[:1000] or None
    if status in ("partial", "descoped") and not note:
        raise ValueError("Say what was left out, and why" if status == "partial" else "Say why it was descoped")
    detail = str(body.get("detail", existing["detail"] if existing else "") or "").strip()[:2000] or None
    return {"title": title, "detail": detail, "status": status, "note": note}


def add_scope(project_id, fields, author):
    db = get_db()
    pos = db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM scope_items WHERE project_id = ?", (project_id,)).fetchone()[0]
    now = _now()
    cur = db.execute("INSERT INTO scope_items (project_id, position, title, detail, status, note, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (project_id, pos, fields["title"], fields["detail"], fields["status"], fields["note"], author, now, now))
    db.commit()
    return cur.lastrowid


def update_scope(item_id, fields):
    db = get_db()
    db.execute("UPDATE scope_items SET title = ?, detail = ?, status = ?, note = ?, updated_at = ? WHERE id = ?",
               (fields["title"], fields["detail"], fields["status"], fields["note"], _now(), item_id))
    db.commit()


def move_scope(project_id, item_id, delta):
    """Swap an item with its neighbour (delta -1 up, +1 down)."""
    items = scope(project_id)
    i = next((n for n, x in enumerate(items) if x["id"] == item_id), None)
    j = None if i is None else i + delta
    if i is None or j < 0 or j >= len(items):
        return
    items[i], items[j] = items[j], items[i]
    db = get_db()
    for pos, x in enumerate(items):
        db.execute("UPDATE scope_items SET position = ? WHERE id = ?", (pos, x["id"]))
    db.commit()


# ---- who signs ---------------------------------------------------------------

def candidates(project_id):
    """(signers, countersigners): the customer side are the project's active
    Customer and Reseller contacts with an address; our side, its active staff."""
    signers, counters = [], []
    for p in participants_for(project_id):
        if not p["active"]:
            continue
        who = {"id": p["user_id"], "name": p["name"], "role": p["role"], "email": p["email"]}
        kind = get_db().execute("SELECT kind FROM users WHERE id = ?", (p["user_id"],)).fetchone()[0]
        if p["role"] in SIGNER_ROLES and p["email"] and kind == "external":   # the customer's side is never a staff account
            signers.append(who)
        elif kind == "internal":
            counters.append(who)
    return signers, counters


# ---- versions ----------------------------------------------------------------

def versions(project_id):
    return get_db().execute("SELECT * FROM signoffs WHERE project_id = ? ORDER BY version DESC", (project_id,)).fetchall()


def get(project_id, version):
    return get_db().execute("SELECT * FROM signoffs WHERE project_id = ? AND version = ?", (project_id, version)).fetchone()


def latest(project_id):
    return get_db().execute("SELECT * FROM signoffs WHERE project_id = ? ORDER BY version DESC LIMIT 1", (project_id,)).fetchone()


def completed(project_id):
    return get_db().execute(f"SELECT * FROM signoffs WHERE project_id = ? AND status IN ({','.join('?' * len(DONE))}) ORDER BY version DESC LIMIT 1",
                            (project_id, *DONE)).fetchone()


def gate(project, new_stage):
    """Why this move is refused, or None: the terminal stage waits for a
    completed sign-off while the policy asks for one."""
    if not policy("signoff_required") or new_stage != get_terminal_stage(project["id"]) or completed(project["id"]):
        return None
    return "The project closes once the sign-off is signed by the customer and countersigned. Send it from the Sign-off page, or ask an admin to waive it."


def state(project, user_id=None, staff=True):
    """The summary the flow and the project page show; `awaiting_me` when this
    person's signature (or countersignature) is the one it waits for."""
    pid = project["id"]
    last, done = latest(pid), completed(pid)
    names = get_stage_names(pid)
    terminal = names[-1] if names else None
    nxt = names[names.index(project["stage"]) + 1] if project["stage"] in names and names.index(project["stage"]) + 1 < len(names) else None
    return {"required": bool(policy("signoff_required")), "status": last["status"] if last else None, "version": last["version"] if last else None,
            "complete": bool(done), "in_stage": project["stage"] == SIGNOFF_STAGE,
            "needed": bool(policy("signoff_required")) and nxt == terminal and nxt is not None and not done,
            "awaiting_me": bool(last) and user_id is not None and ((last["status"] == "sent" and last["signer_id"] == user_id)
                                                                   or (last["status"] == "signed" and staff and last["counter_id"] == user_id))}


def canonical(content):
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(content):
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()


def intact(row):
    """The stored content still matches the fingerprint taken when it was sent."""
    return fingerprint(json.loads(row["content"])) == row["content_hash"]


# ---- the document --------------------------------------------------------------

def _meta(project):
    return {"id": project["id"], "name": project["name"], "client": project["client"], "po_number": project["po_number"], "po_date": project["po_date"],
            "start_date": project["start_date"] or (local_date(project["created_at"]).isoformat() if local_date(project["created_at"]) else None), "target_end_date": project["target_end_date"], "finished": local_today().isoformat(),
            "owner_name": project["owner_name"], "partner_name": project["partner_name"] if project["via"] == "Partner" else None,
            "vendor_name": project["vendor_name"], "product_name": project["product_name"], "delivery_mode": project["delivery_mode"],
            "company": policy("company_name")}


def _values(project):
    from services.report_pdf import _fmt
    return {"project": project["name"], "client": project["client"], "company": policy("company_name"), "pm": project["owner_name"],
            "po": project["po_number"] or "", "stage": project["stage"], "target": _fmt(project["target_end_date"]), "forecast": "",
            "date": _fmt(local_today().isoformat())}


def draft(project, template_id=None):
    """The suggested words: the PM edits them before sending. The template's
    statement and terms stand in for the workspace's when it has them."""
    from services.doc_templates import resolve
    tpl = resolve("signoff", template_id)
    db = get_db()
    pid = project["id"]
    items = scope(pid)
    stages = plan_service.build(project)["stages"]
    tasks = db.execute("SELECT title, done, due_date, stage FROM tasks WHERE project_id = ? ORDER BY due_date IS NULL, due_date, id", (pid,)).fetchall()
    delivered = []
    if not items:
        for s in stages:
            if s["status"] == "done" and s["actual_start"]:
                n = sum(1 for t in tasks if t["done"] and t["stage"] == s["name"])
                delivered.append(f"{s['name']}: completed {_fmt(s['actual_end'])}" + (f" ({n} task{'s' if n != 1 else ''})" if n else ""))
        delivered += [f"Delivered: {d['filename']}" for d in db.execute(
            "SELECT filename FROM documents WHERE project_id = ? AND category = 'Deliverable' AND deleted_at IS NULL ORDER BY uploaded_at", (pid,))]
    outstanding = [t["title"] + (f" (due {_fmt(t['due_date'])})" if t["due_date"] else "") for t in tasks if not t["done"]]
    outstanding += [r["title"] for r in raid_service.items(pid, customer=True) if r["open"] and r["kind"] != "decision"]
    counts = {k: sum(1 for x in items if x["status"] == k) for k in ("delivered", "partial", "descoped")}
    start = project["start_date"] or (stages[0]["actual_start"] if stages else None)
    words = [f"{policy('company_name')} has completed {project['name']} for {project['client']}."]
    if start:
        words.append(f"The work started on {_fmt(start)}" + (f" against a target of {_fmt(project['target_end_date'])}." if project["target_end_date"] else "."))
    if items:
        extra = [f"{counts['partial']} in part" if counts["partial"] else "", f"{counts['descoped']} descoped by agreement" if counts["descoped"] else ""]
        words.append(f"{counts['delivered']} of {len(items)} agreed scope items were delivered in full" + ("".join(f", {x}" for x in extra if x)) + ".")
    terms = tpl["texts"].get("terms") or policy("signoff_terms") or ""
    return {"summary": " ".join(words), "delivered": delivered, "outstanding": outstanding[:30],
            "terms": [x for x in terms.splitlines() if x.strip()], "scope": items, "statement": tpl["texts"].get("statement") or policy("signoff_statement")}


def _lines(value, limit=40, width=500):
    if isinstance(value, str):
        value = value.splitlines()
    return [str(x).strip()[:width] for x in (value or []) if str(x).strip()][:limit]


def send(project, body, author):
    """Freeze a new version and send it for signature. Returns the row or raises ValueError."""
    pid = project["id"]
    if completed(pid):
        raise ValueError("This project is already signed off")
    signers, counters = candidates(pid)
    signer = next((s for s in signers if s["id"] == body.get("signer_id")), None)
    counter = next((s for s in counters if s["id"] == body.get("counter_id")), None)
    if not signer:
        raise ValueError("Pick the customer's signatory: a Customer or Reseller contact on the project with an email address")
    if not counter:
        raise ValueError("Pick who countersigns for us")
    items = scope(pid)
    if any(x["status"] == "agreed" for x in items):
        raise ValueError("Mark every scope item delivered, partial or descoped first")
    summary = str(body.get("summary") or "").strip()[:4000]
    if not summary:
        raise ValueError("Write the summary")
    delivered = _lines(body.get("delivered"))
    if not items and not delivered:
        raise ValueError("List what was delivered, or record the scope")
    from services.doc_templates import fill, resolve
    tpl = resolve("signoff", body.get("template_id"))
    values = _values(project)
    content = {
        "template": tpl, "intro": fill(tpl["texts"].get("intro"), values).strip(), "closing": fill(tpl["texts"].get("closing"), values).strip(),
        "project": _meta(project), "summary": summary,
        "scope": [{"title": x["title"], "detail": x["detail"], "status": x["status"], "note": x["note"]} for x in items],
        "delivered": [] if items else delivered, "outstanding": _lines(body.get("outstanding")), "terms": _lines(body.get("terms")),
        "statement": fill(tpl["texts"].get("statement"), values).strip() or policy("signoff_statement"),
        "signer": {"name": signer["name"], "email": signer["email"], "role": signer["role"]},
        "countersigner": {"name": counter["name"], "role": counter["role"]},
        "prepared_by": author, "prepared_at": _now(),
    }
    db = get_db()
    version = db.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM signoffs WHERE project_id = ?", (pid,)).fetchone()[0]
    db.execute(f"UPDATE signoffs SET status = 'withdrawn' WHERE project_id = ? AND status IN ({','.join('?' * len(OPEN))})", (pid, *OPEN))
    db.execute("INSERT INTO signoffs (project_id, version, status, content, content_hash, created_by, created_at, signer_id, signer_email, counter_id) "
               "VALUES (?, ?, 'sent', ?, ?, ?, ?, ?, ?, ?)",
               (pid, version, canonical(content), fingerprint(content), author, content["prepared_at"], signer["id"], signer["email"], counter["id"]))
    db.commit()
    return get(pid, version)


def clean_signature(body):
    """A signature is drawn strokes (points on a 1000 x 300 pad) or typed text; stored as JSON."""
    sig = body.get("signature") or {}
    if sig.get("kind") == "typed":
        text = str(sig.get("text") or "").strip()[:80]
        if not text:
            raise ValueError("Type your signature")
        return json.dumps({"kind": "typed", "text": text})
    if sig.get("kind") == "drawn":
        strokes = sig.get("strokes")
        if not isinstance(strokes, list) or not strokes or len(strokes) > 60:
            raise ValueError("Draw your signature")
        out, total = [], 0
        for st in strokes:
            if not isinstance(st, list):
                raise ValueError("Draw your signature")
            pts = [[max(0, min(1000, int(p[0]))), max(0, min(300, int(p[1])))] for p in st if isinstance(p, (list, tuple)) and len(p) == 2]
            total += len(pts)
            if pts:
                out.append(pts)
        if total < 5 or total > 6000:
            raise ValueError("Draw your signature")
        return json.dumps({"kind": "drawn", "strokes": out})
    raise ValueError("Sign by drawing or typing your name")


def _who(body):
    name = str(body.get("name") or "").strip()[:120]
    title = str(body.get("title") or "").strip()[:120]
    if not name:
        raise ValueError("Your full name")
    if not body.get("accept"):
        raise ValueError("Tick the box to accept")
    return name, title


def sign(row, body, ip, agent):
    if row["status"] != "sent":
        raise ValueError("This version is not waiting for a signature")
    if not intact(row):
        raise ValueError("This document has changed since it was sent; ask for a new version")
    name, title = _who(body)
    signature = clean_signature(body)
    db = get_db()
    db.execute("UPDATE signoffs SET status = 'signed', signer_name = ?, signer_title = ?, signed_at = ?, signed_ip = ?, signed_agent = ?, signature = ? WHERE id = ? AND status = 'sent'",
               (name, title, _now(), ip, (agent or "")[:300], signature, row["id"]))
    db.commit()


def countersign(row, body, ip, agent):
    if row["status"] != "signed":
        raise ValueError("The customer has not signed this version yet")
    if not intact(row):
        raise ValueError("This document has changed since it was sent; send a new version")
    name, title = _who(body)
    signature = clean_signature(body)
    now = _now()
    db = get_db()
    db.execute("UPDATE signoffs SET status = 'countersigned', counter_name = ?, counter_title = ?, counter_signed_at = ?, counter_ip = ?, counter_agent = ?, "
               "counter_signature = ?, completed_at = ? WHERE id = ? AND status = 'signed'", (name, title, now, ip, (agent or "")[:300], signature, now, row["id"]))
    db.commit()


def reject(project, row, comment, author):
    """The customer says no: the version is closed and the reason becomes an open issue everyone can see."""
    if row["status"] != "sent":
        raise ValueError("This version is not waiting for a signature")
    comment = str(comment or "").strip()[:2000]
    if not comment:
        raise ValueError("Say what needs to change before you can sign")
    now = _now()
    db = get_db()
    db.execute("UPDATE signoffs SET status = 'rejected', reject_comment = ?, rejected_at = ? WHERE id = ?", (comment, now, row["id"]))
    db.commit()
    raid_service.create(project["id"], {"kind": "issue", "title": f"Sign-off v{row['version']} not accepted"[:200], "detail": f"{author}: {comment}",
                                        "impact": "medium", "likelihood": None, "status": "open", "owner_id": project["owner_id"], "due_date": None,
                                        "stage": project["stage"], "resolution": None, "customer_visible": 1}, author)


def withdraw(row):
    if row["status"] not in OPEN:
        raise ValueError("Only a version waiting for signatures can be withdrawn")
    db = get_db()
    db.execute("UPDATE signoffs SET status = 'withdrawn' WHERE id = ? AND status IN ('sent', 'signed')", (row["id"],))
    db.commit()


def record_upload(row, document_id, name, title, signed_on):
    """A signed paper copy of an open version completes it."""
    if row["status"] not in OPEN:
        raise ValueError("Upload the signed copy of a version that is waiting for signatures")
    now = _now()
    db = get_db()
    db.execute("UPDATE signoffs SET status = 'uploaded', document_id = ?, signer_name = COALESCE(signer_name, ?), signer_title = COALESCE(signer_title, ?), "
               "signed_at = COALESCE(signed_at, ?), completed_at = ? WHERE id = ? AND status IN ('sent', 'signed')", (document_id, name, title, signed_on, now, row["id"]))
    db.commit()


def waive(project, reason, author):
    """An admin closes the gate without signatures; the reason is kept on a version of its own."""
    reason = str(reason or "").strip()[:1000]
    if len(reason) < 10:
        raise ValueError("Give the reason in a sentence")
    if completed(project["id"]):
        raise ValueError("This project is already signed off")
    d = draft(project)
    content = {"project": _meta(project), "summary": d["summary"], "scope": [{k: x[k] for k in ("title", "detail", "status", "note")} for x in d["scope"]],
               "delivered": d["delivered"], "outstanding": d["outstanding"], "terms": d["terms"], "statement": policy("signoff_statement"),
               "signer": None, "countersigner": None, "prepared_by": author, "prepared_at": _now()}
    db = get_db()
    version = db.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM signoffs WHERE project_id = ?", (project["id"],)).fetchone()[0]
    db.execute(f"UPDATE signoffs SET status = 'withdrawn' WHERE project_id = ? AND status IN ({','.join('?' * len(OPEN))})", (project["id"], *OPEN))
    db.execute("INSERT INTO signoffs (project_id, version, status, content, content_hash, created_by, created_at, waiver_reason, waived_by, completed_at) "
               "VALUES (?, ?, 'waived', ?, ?, ?, ?, ?, ?, ?)",
               (project["id"], version, canonical(content), fingerprint(content), author, content["prepared_at"], reason, author, content["prepared_at"]))
    db.commit()
    return get(project["id"], version)


def view(row, staff):
    """A version as the page shows it. The signing record (IP, browser) is for staff."""
    d = {k: row[k] for k in ("version", "status", "content_hash", "created_by", "created_at", "signer_name", "signer_title", "signer_email", "signed_at",
                             "counter_name", "counter_title", "counter_signed_at", "reject_comment", "rejected_at", "document_id", "waiver_reason",
                             "waived_by", "completed_at", "signer_id", "counter_id", "link_issued_by", "link_issued_at")}
    d["content"] = json.loads(row["content"])
    d["signature"] = json.loads(row["signature"]) if row["signature"] else None
    d["counter_signature"] = json.loads(row["counter_signature"]) if row["counter_signature"] else None
    d["intact"] = intact(row)
    if staff:
        d.update(signed_ip=row["signed_ip"], signed_agent=row["signed_agent"], counter_ip=row["counter_ip"], counter_agent=row["counter_agent"])
    return d
