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
from datetime import datetime, timedelta

from constants import SIGNOFF_STAGE
from db import get_db, get_stage_names, get_terminal_stage, participants_for, touch_project
from policies import local_date, local_today, policy
from services import plan as plan_service
from services import raid as raid_service
from services.fmt import fmt_date, plural

SCOPE_STATUSES = ("agreed", "delivered", "partial", "descoped")
OPEN = ("sent", "signed")
DONE = ("countersigned", "uploaded", "waived")
SIGNER_ROLES = ("Customer", "Reseller")


def _now():
    return datetime.utcnow().isoformat()


# ---- scope -----------------------------------------------------------------

def scope(project_id):
    return [dict(r) for r in get_db().execute(
        "SELECT id, title, detail, status, note, position FROM scope_items WHERE project_id = ? ORDER BY position, id", (project_id,))]


def clean_scope(body, existing=None):
    """Validated fields from a posted body, or raise ValueError. Text is text:
    a list is refused, never stored as its Python spelling and then frozen
    into a signed document; too long is said, never cut (P2-27)."""
    from core import text_field
    title = text_field(body.get("title", existing["title"] if existing else ""), 300, "Title")
    if not title:
        raise ValueError("Give the scope item a title")
    status = body.get("status", existing["status"] if existing else "agreed")
    if status not in SCOPE_STATUSES:
        raise ValueError("Status is agreed, delivered, partial or descoped")
    note = text_field(body.get("note", existing["note"] if existing else ""), 1000, "Note", multiline=True) or None
    if status in ("partial", "descoped") and not note:
        raise ValueError("Say what was left out, and why" if status == "partial" else "Say why it was descoped")
    detail = text_field(body.get("detail", existing["detail"] if existing else ""), 2000, "Detail", multiline=True) or None
    return {"title": title, "detail": detail, "status": status, "note": note}


def add_scope(project_id, fields, author):
    db = get_db()
    pos = db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM scope_items WHERE project_id = ?", (project_id,)).fetchone()[0]
    now = _now()
    cur = db.execute("INSERT INTO scope_items (project_id, position, title, detail, status, note, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (project_id, pos, fields["title"], fields["detail"], fields["status"], fields["note"], author, now, now))
    touch_project(db, project_id)
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
    """The version that signs the rollout off, or None. One set aside when the
    rollout was reopened (superseded_at, P3-24) is kept as signed but closes nothing."""
    return get_db().execute(f"SELECT * FROM signoffs WHERE project_id = ? AND status IN ({','.join('?' * len(DONE))}) AND superseded_at IS NULL "
                            "ORDER BY version DESC LIMIT 1", (project_id, *DONE)).fetchone()


GATE_MESSAGE = "The rollout closes once the sign-off is signed by the customer and countersigned. Send it from the Sign-off page, or ask an admin to waive it."


def gate(project, new_stage, terminal=None):
    """Why this move is refused, or None: the terminal stage waits for a
    completed sign-off while the policy asks for one. `terminal` is the
    terminal stage a stage-list edit would leave (default: today's)."""
    if not policy("signoff_required") or new_stage != (terminal or get_terminal_stage(project["id"])) or completed(project["id"]):
        return None
    return GATE_MESSAGE


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
    from services.fields import placeholders as fields_placeholders
    return {"project": project["name"], "client": project["client"], "company": policy("company_name"), "pm": project["owner_name"],
            "po": project["po_number"] or "", "stage": project["stage"], "target": fmt_date(project["target_end_date"]), "forecast": "",
            "date": fmt_date(local_today().isoformat())} | fields_placeholders(project["id"])   # {field:Name}: the customer's fields only


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
                delivered.append(f"{s['name']}: completed {fmt_date(s['actual_end'], '—')}" + (f" ({n} {plural(n, 'task')})" if n else ""))
        delivered += [f"Delivered: {d['filename']}" for d in db.execute(
            "SELECT filename FROM documents WHERE project_id = ? AND category = 'Deliverable' AND deleted_at IS NULL AND review_status = 'accepted' ORDER BY uploaded_at", (pid,))]
        # the milestones reached that the customer may see (a recorded scope is its own table of what was delivered)
        from services import milestones
        delivered += milestones.delivered_lines(pid)
    # the customer's document: only the asks on outside parties, never an internal task (services/asks.py)
    from services import asks
    outstanding = [t["title"] + (f" (due {fmt_date(t['due_date'], '—')})" if t["due_date"] else "") for t in asks.listing(pid) if not t["done"]]
    outstanding += [r["title"] for r in raid_service.items(pid, customer=True) if r["open"] and r["kind"] != "decision"]
    counts = {k: sum(1 for x in items if x["status"] == k) for k in ("delivered", "partial", "descoped")}
    start = project["start_date"] or (stages[0]["actual_start"] if stages else None)
    # the draft is written before the last move: "completed" fits only once the work stages are done
    now = next((i for i, s in enumerate(stages) if s["status"] == "current"), len(stages))
    words = [f"{policy('company_name')} has completed {project['name']} for {project['client']}." if now >= len(stages) - 2
             else f"{policy('company_name')} is delivering {project['name']} for {project['client']}; the work is now in {stages[now]['name']}."]
    if start:
        words.append(f"The work started on {fmt_date(start, '—')}" + (f" against a target of {fmt_date(project['target_end_date'], '—')}." if project["target_end_date"] else "."))
    if items:
        extra = [f"{counts['partial']} in part" if counts["partial"] else "", f"{counts['descoped']} descoped by agreement" if counts["descoped"] else ""]
        words.append(f"{counts['delivered']} of {len(items)} agreed scope items were delivered in full" + ("".join(f", {x}" for x in extra if x)) + ".")
    terms = tpl["texts"].get("terms") or policy("signoff_terms") or ""
    return {"summary": " ".join(words), "delivered": delivered, "outstanding": outstanding[:30],
            "terms": [x for x in terms.splitlines() if x.strip()], "scope": items, "statement": tpl["texts"].get("statement") or policy("signoff_statement")}


def _lines(value, label, limit=40, width=500):
    """The non-empty lines of a list or text; more than `limit`, or a line
    longer than `width`, is refused, never cut silently (D6, P2-27): a signed
    document must say everything it was sent with."""
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value or [], list) or any(not isinstance(x, str) for x in value or []):
        raise ValueError(f"{label}: send lines of text")
    out = [x.strip() for x in (value or []) if x.strip()]
    if any(len(x) > width for x in out):
        raise ValueError(f"{label}: at most {width} characters a line")
    if len(out) > limit:
        raise ValueError(f"At most {limit} lines under {label} (this has {len(out)}); group them or attach the full list as a document")
    return out


def sendable(project):
    """Why the sign-off cannot be sent from the project's stage, or None. It
    is sent from the stage before the finish (or the Sign-off stage), so a
    project cannot jump from its first stage to Closed (D5/L22)."""
    names = get_stage_names(project["id"])
    if len(names) < 2:
        return "The rollout needs a stage before its finish to send a sign-off from"
    if project["stage"] in (names[-2], SIGNOFF_STAGE) and project["stage"] != names[-1]:
        return None
    return f"Send the sign-off once the rollout is in {names[-2]}, the stage before {names[-1]}"


def send(project, body, author, commit=True):
    """Freeze a new version and send it for signature. Returns the row or
    raises ValueError. With commit=False the caller commits (and may add to
    the same transaction)."""
    pid = project["id"]
    if completed(pid):
        raise ValueError("This rollout is already signed off")
    why = sendable(project)
    if why:
        raise ValueError(why)
    signers, counters = candidates(pid)
    signer = next((s for s in signers if s["id"] == body.get("signer_id")), None)
    counter = next((s for s in counters if s["id"] == body.get("counter_id")), None)
    if not signer:
        raise ValueError("Pick the customer's signatory: a Customer or Reseller contact on the rollout with an email address")
    if not counter:
        raise ValueError("Pick who countersigns for us")
    items = scope(pid)
    if any(x["status"] == "agreed" for x in items):
        raise ValueError("Mark every scope item delivered, partial or descoped first")
    from core import as_id, text_field
    summary = text_field(body.get("summary"), 4000, "Summary", multiline=True)
    if not summary:
        raise ValueError("Write the summary")
    delivered = _lines(body.get("delivered"), "Delivered")
    if not items and not delivered:
        raise ValueError("List what was delivered, or record the scope")
    from services.doc_templates import fill, resolve
    tpl = resolve("signoff", as_id(body.get("template_id")))
    values = _values(project)
    content = {
        "template": tpl, "intro": fill(tpl["texts"].get("intro"), values).strip(), "closing": fill(tpl["texts"].get("closing"), values).strip(),
        "project": _meta(project), "summary": summary,
        "scope": [{"title": x["title"], "detail": x["detail"], "status": x["status"], "note": x["note"]} for x in items],
        "delivered": [] if items else delivered, "outstanding": _lines(body.get("outstanding"), "Outstanding"), "terms": _lines(body.get("terms"), "Terms"),
        "statement": fill(tpl["texts"].get("statement"), values).strip() or policy("signoff_statement"),
        "signer": {"name": signer["name"], "email": signer["email"], "role": signer["role"]},
        "countersigner": {"name": counter["name"], "role": counter["role"]},
        "prepared_by": author, "prepared_at": _now(),
    }
    db = get_db()
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")   # one sender at a time: the check below and the insert are one step
    # a double submit (two clicks, two tabs) sends one version, not two (F-M5)
    last = latest(pid)
    if last and last["status"] == "sent" and last["created_by"] == author and last["created_at"] >= (datetime.utcnow() - timedelta(seconds=10)).isoformat():
        db.rollback()
        raise ValueError(f"Version {last['version']} was sent a moment ago")
    version = db.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM signoffs WHERE project_id = ?", (pid,)).fetchone()[0]
    db.execute(f"UPDATE signoffs SET status = 'withdrawn' WHERE project_id = ? AND status IN ({','.join('?' * len(OPEN))})", (pid, *OPEN))
    db.execute("INSERT INTO signoffs (project_id, version, status, content, content_hash, created_by, created_at, signer_id, signer_email, counter_id) "
               "VALUES (?, ?, 'sent', ?, ?, ?, ?, ?, ?, ?)",
               (pid, version, canonical(content), fingerprint(content), author, content["prepared_at"], signer["id"], signer["email"], counter["id"]))
    touch_project(db, pid)
    if commit:
        db.commit()
    return get(pid, version)


def clean_signature(body):
    """A signature is drawn strokes (points on a 1000 x 300 pad) or typed text; stored as JSON."""
    sig = body.get("signature") or {}
    if not isinstance(sig, dict):
        raise ValueError("Sign by drawing or typing your name")
    if sig.get("kind") == "typed":
        from core import text_field
        text = text_field(sig.get("text"), 80, "Signature")
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
            pts = [[max(0, min(1000, int(p[0]))), max(0, min(300, int(p[1])))] for p in st
                   if isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and -1e6 < v < 1e6 for v in p)]
            total += len(pts)
            if pts:
                out.append(pts)
        if total < 5 or total > 6000:
            raise ValueError("Draw your signature")
        return json.dumps({"kind": "drawn", "strokes": out})
    raise ValueError("Sign by drawing or typing your name")


def _who(body):
    from core import text_field
    name, title = text_field(body.get("name"), 120, "Name"), text_field(body.get("title"), 120, "Title")
    if not name:
        raise ValueError("Your full name")
    if not body.get("accept"):
        raise ValueError("Tick the box to accept")
    return name, title


def sign(row, body, ip, agent):
    if row["status"] != "sent" or row["superseded_at"]:
        raise ValueError("This version is not waiting for a signature")
    if not intact(row):
        raise ValueError("This document has changed since it was sent; ask for a new version")
    name, title = _who(body)
    signature = clean_signature(body)
    db = get_db()
    done = db.execute("UPDATE signoffs SET status = 'signed', signer_name = ?, signer_title = ?, signed_at = ?, signed_ip = ?, signed_agent = ?, signature = ? WHERE id = ? AND status = 'sent' AND superseded_at IS NULL",
                      (name, title, _now(), ip, (agent or "")[:300], signature, row["id"])).rowcount
    if not done:   # signed or withdrawn a moment ago, by another request
        db.rollback()
        raise ValueError("This version is not waiting for a signature")
    touch_project(db, row["project_id"])
    db.commit()


def countersign(row, body, ip, agent):
    if row["status"] in DONE:
        raise ValueError("This version is already signed off")
    if row["status"] != "signed":
        raise ValueError("The customer has not signed this version yet")
    if row["superseded_at"]:   # the rollout was reopened after the customer signed
        raise ValueError("The rollout was reopened since this version was signed; send a new version")
    if not intact(row):
        raise ValueError("This document has changed since it was sent; send a new version")
    name, title = _who(body)
    signature = clean_signature(body)
    now = _now()
    db = get_db()
    done = db.execute("UPDATE signoffs SET status = 'countersigned', counter_name = ?, counter_title = ?, counter_signed_at = ?, counter_ip = ?, counter_agent = ?, "
                      "counter_signature = ?, completed_at = ? WHERE id = ? AND status = 'signed'", (name, title, now, ip, (agent or "")[:300], signature, now, row["id"])).rowcount
    if not done:
        db.rollback()
        raise ValueError("This version is not waiting for our countersignature")
    touch_project(db, row["project_id"])
    db.commit()


def reject(project, row, comment, author):
    """The customer says no: the version is closed and the reason becomes an open issue everyone can see."""
    if row["status"] != "sent":
        raise ValueError("This version is not waiting for a signature")
    from core import text_field
    comment = text_field(comment, 2000, "Comment", multiline=True)
    if not comment:
        raise ValueError("Say what needs to change before you can sign")
    now = _now()
    db = get_db()
    # only a version still waiting: never overwrite one signed meanwhile, and one issue per rejection (F-M4)
    done = db.execute("UPDATE signoffs SET status = 'rejected', reject_comment = ?, rejected_at = ? WHERE id = ? AND status = 'sent'", (comment, now, row["id"])).rowcount
    if not done:
        db.rollback()
        raise ValueError("This version is not waiting for a signature")
    touch_project(db, project["id"])
    db.commit()
    raid_service.create(project["id"], {"kind": "issue", "title": f"Sign-off v{row['version']} not accepted"[:200], "detail": f"{author}: {comment}",
                                        "impact": "medium", "likelihood": None, "status": "open", "owner_id": project["owner_id"], "due_date": None,
                                        "stage": project["stage"], "resolution": None, "customer_visible": 1}, author)


def withdraw(row):
    if row["status"] not in OPEN:
        raise ValueError("Only a version waiting for signatures can be withdrawn")
    db = get_db()
    if not db.execute("UPDATE signoffs SET status = 'withdrawn' WHERE id = ? AND status IN ('sent', 'signed')", (row["id"],)).rowcount:
        raise ValueError("Only a version waiting for signatures can be withdrawn")
    touch_project(db, row["project_id"])
    db.commit()


def record_upload(row, document_id, name, title, signed_on):
    """A signed paper copy of an open version completes it."""
    if row["status"] not in OPEN:
        raise ValueError("Upload the signed copy of a version that is waiting for signatures")
    now = _now()
    db = get_db()
    if not db.execute("UPDATE signoffs SET status = 'uploaded', document_id = ?, signer_name = COALESCE(signer_name, ?), signer_title = COALESCE(signer_title, ?), "
                      "signed_at = COALESCE(signed_at, ?), completed_at = ? WHERE id = ? AND status IN ('sent', 'signed')",
                      (document_id, name, title, signed_on, now, row["id"])).rowcount:
        raise ValueError("Upload the signed copy of a version that is waiting for signatures")
    touch_project(db, row["project_id"])
    db.commit()


def waive(project, reason, author):
    """An admin closes the gate without signatures; the reason is kept on a version of its own."""
    from core import text_field
    reason = text_field(reason, 1000, "Reason", multiline=True)
    if len(reason) < 10:
        raise ValueError("Give the reason in a sentence")
    if completed(project["id"]):
        raise ValueError("This rollout is already signed off")
    early = sendable(project)   # a waiver stands in for the signatures, not for the stages before them (sim L-12)
    if early:
        raise ValueError(early.replace("Send the sign-off", "Waive the sign-off"))
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
    touch_project(db, project["id"])
    db.commit()
    return get(project["id"], version)


def view(row, staff, partner_cut=False):
    """A version as the page shows it. The signing record (IP, browser) is for staff.
    `partner_cut`: a partner or contractor who is not the named signatory reads it
    without the PO, the partner channel, the signatory's email or the drawn
    signatures (core.sees_po: the PO is ours and the customer's; review P1-1)."""
    d = {k: row[k] for k in ("version", "status", "content_hash", "created_by", "created_at", "signer_name", "signer_title", "signer_email", "signed_at",
                             "counter_name", "counter_title", "counter_signed_at", "reject_comment", "rejected_at", "document_id", "waiver_reason",
                             "waived_by", "completed_at", "signer_id", "counter_id", "link_issued_by", "link_issued_at", "superseded_at")}
    d["content"] = json.loads(row["content"])
    d["signature"] = json.loads(row["signature"]) if row["signature"] else None
    d["counter_signature"] = json.loads(row["counter_signature"]) if row["counter_signature"] else None
    d["intact"] = intact(row)
    if staff:
        d.update(signed_ip=row["signed_ip"], signed_agent=row["signed_agent"], counter_ip=row["counter_ip"], counter_agent=row["counter_agent"])
    if partner_cut:
        for k in ("po_number", "po_date", "partner_name"):
            d["content"].get("project", {}).pop(k, None)
        if isinstance(d["content"].get("signer"), dict):
            d["content"]["signer"] = {k: v for k, v in d["content"]["signer"].items() if k != "email"}
        d["signer_email"] = None
        d["signature"] = d["counter_signature"] = None
    return d
