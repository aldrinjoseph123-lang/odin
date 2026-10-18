"""CRM intake (Odin 2.0): the CRM posts a won deal to POST /api/v1/intake with a
token of the `create` scope, and Odin makes a *pending* rollout (projects.intake_pending = 1).
A pending rollout is neither open nor closed (db.PROJECT_OPEN_SQL), so no Flow lane, count,
alert, dashboard figure or report has it; staff see it in the Flow's holding lane and the
rollouts list's "Pending intake" view until a project manager confirms it by attaching
the PO and taking ownership (routes/intake.py).

The deal id is the key, per source (the token's name): a repeat call answers 200 with the
rollout it made before, never a second one; the same deal id from another source is a 409
that names nothing of the first. Every call is kept in intake_calls (the newest LOG_KEEP rows;
the last SHOWN are on the settings page). A created rollout is audited under the token's name;
a duplicate or refused call is audited too (intake_duplicate / intake_refused), at most once per
token, action and HTTP status a minute, so a CRM's retry loop cannot flood the audit trail.
A call from outside policy intake_allowed_ips is refused 403; an expired token is a 401
(routes/tokens.token_required, which logs it here through refuse()).
"""
import ipaddress
import json
import secrets
from datetime import datetime, timedelta

from markupsafe import escape

from constants import DELIVERY_MODES
from core import parse_date, text_field
from db import copy_template_stages, get_db, set_project_manager
from policies import email_domain_allowed, ip_networks, policy
from security import valid_email
from services import fields as custom_fields
from services.fmt import plural

# The request body: each key typed and length-capped. Anything else is refused.
LIMITS = {"client": 200, "name": 200, "product": 120, "vendor": 120, "po_number": 60, "deal_id": 80}
KEYS = {*LIMITS, "delivery_mode", "target_date", "contacts", "fields"}
REQUIRED = ("client", "name", "deal_id")
CONTACTS_MAX = 10
LOG_KEEP = 200
SHOWN = 10


class Refused(Exception):
    """A call Odin answers with `status` and `{"error": message}`."""
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _now():
    return datetime.utcnow()   # a seam for the tests: the rate limit counts minutes


# ---- the call log ----------------------------------------------------------------

def log_call(db, token, status, result, deal_id=None, project_id=None, detail=None):
    """One row per call, then trimmed to the newest LOG_KEEP. Commits."""
    db.execute("INSERT INTO intake_calls (token_name, at, status, result, deal_id, project_id, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (token, _now().isoformat(), status, result, (deal_id or "")[:LIMITS["deal_id"]] or None, project_id, (detail or "")[:300] or None))
    db.execute("DELETE FROM intake_calls WHERE id <= (SELECT MAX(id) FROM intake_calls) - ?", (LOG_KEEP,))
    db.commit()


AUDIT_EVERY = 60   # seconds: one audit row per token, action and status in this window (a seam for the tests)


def _audit_once(db, token, action, status, message):
    """An audit row for a duplicate or refused call, unless this token already has one for the
    same action and HTTP status in the last AUDIT_EVERY seconds; intake_calls keeps every call.
    The audit trail's own clock and rows are the bound, so nothing else needs to remember it."""
    from services.audit import audit_log
    actor, head = f"token:{token}", f"HTTP {status}"
    since = (datetime.utcnow() - timedelta(seconds=AUDIT_EVERY)).isoformat()
    if db.execute("SELECT 1 FROM audit_logs WHERE action = ? AND username = ? AND timestamp > ? AND details LIKE ? LIMIT 1",
                  (action, actor, since, head + ":%")).fetchone():
        return
    audit_log(action, "api_token", None, token, f"{head}: {message}", actor=actor, db=db)


def refuse(db, token, status, message, deal_id=None, result="refused"):
    """A refused call: logged in intake_calls and (bounded) in the audit trail. Commits."""
    log_call(db, token, status, result, deal_id, detail=message)
    _audit_once(db, token, "intake_refused", status, message)


def recent_calls(db, n=SHOWN):
    return [dict(r) for r in db.execute("SELECT * FROM intake_calls ORDER BY id DESC LIMIT ?", (n,))]


def over_rate(db, token):
    """True when this token has already made its quota of calls in the last minute
    (the refused ones do not count, or a flood would never end). It counts intake_calls,
    the log every call already lands in, rather than security.rate_limited: that would
    write a second row per call into login_attempts, and the `_now` seam lets a test move the minute."""
    since = (_now() - timedelta(seconds=60)).isoformat()
    # nor do calls refused for the token or the address (401/403): a stolen token used from elsewhere
    # must not use up the real CRM's minute
    n = db.execute("SELECT COUNT(*) FROM intake_calls WHERE token_name = ? AND at > ? AND result != 'rate_limited' AND status NOT IN (401, 403)",
                   (token, since)).fetchone()[0]
    return n >= policy("intake_rate_per_min", db)


def address_allowed(ip, db=None):
    """True when policy intake_allowed_ips is blank or holds this address (request.remote_addr:
    the proxy's X-Forwarded-For is applied only under PMS_TRUST_PROXY, security.py)."""
    nets = ip_networks(policy("intake_allowed_ips", db))
    if not nets:
        return True
    try:
        addr = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    addr = getattr(addr, "ipv4_mapped", None) or addr   # ::ffff:203.0.113.7 from a dual-stack socket is 203.0.113.7
    return any(addr in net for net in nets)


def source_allowed(token):
    allowed = [s.strip().lower() for s in policy("intake_sources").split(",") if s.strip()]
    return not allowed or token.lower() in allowed


# ---- the request -----------------------------------------------------------------

def clean(body):
    """(the checked values, warnings) from a posted body; Refused(400) otherwise."""
    if not isinstance(body, dict):
        raise Refused(400, "Send a JSON object")
    unknown = sorted(set(body) - KEYS)
    if unknown:
        raise Refused(400, f"Unknown {plural(len(unknown), 'field')}: {', '.join(str(k)[:40] for k in unknown)}")
    problems, out, warnings = [], {}, []
    for key, limit in LIMITS.items():
        try:
            out[key] = text_field(body.get(key), limit, key) or None
        except ValueError as e:
            problems.append(str(e))
    problems += [f"{k} is required" for k in REQUIRED if not out.get(k)]
    mode = body.get("delivery_mode", DELIVERY_MODES[0])
    if mode not in DELIVERY_MODES:
        problems.append(f"delivery_mode: one of {', '.join(DELIVERY_MODES)}")
    out["delivery_mode"] = mode
    try:
        out["target_date"] = parse_date(body.get("target_date"))
    except ValueError as e:
        problems.append(f"target_date: {e}")
    out["contacts"] = _contacts(body.get("contacts"), problems, warnings)
    out["fields"] = _fields(body.get("fields"), problems)
    if problems:
        raise Refused(400, "; ".join(problems))
    return out, warnings


def _contacts(raw, problems, warnings):
    """The customer contact emails: a list of well-formed addresses, each on an allowed
    domain (Settings › Sign-in & security › Partner email domains) or dropped with a warning."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > CONTACTS_MAX or not all(isinstance(x, str) for x in raw):
        problems.append(f"contacts: a list of at most {CONTACTS_MAX} email addresses")
        return []
    kept = []
    for email in (x.strip().lower() for x in raw):
        if not valid_email(email):
            problems.append(f"contacts: {email[:60] or '(empty)'} is not an email address")
        elif not email_domain_allowed(email):
            warnings.append(f"{email} was dropped: its domain is not allowed (Settings › Sign-in & security › Partner email domains)")
        elif email not in kept:
            kept.append(email)
    return kept


def _fields(raw, problems):
    """{field id: stored value} from {name or id: value}; an unknown field, or a value the
    field's kind refuses, is a problem, and so is a required field left out."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        problems.append("fields: an object of field name (or id) to value")
        return {}
    defs = custom_fields.definitions()
    by_name = {f["name"].lower(): f["id"] for f in defs}
    ids = {f["id"] for f in defs}
    items, unknown = {}, []
    for key, value in raw.items():
        fid = int(key) if isinstance(key, str) and key.isascii() and key.isdigit() else by_name.get(str(key).strip().lower())
        if fid in ids:
            items[fid] = value
        else:
            unknown.append(str(key)[:40])
    if unknown:
        problems.append(f"fields: unknown custom {plural(len(unknown), 'field')} {', '.join(unknown)}")
        return {}
    try:
        return custom_fields.clean_values(items, creating=True)
    except ValueError as e:
        problems.append(str(e))
        return {}


# ---- the rollout -----------------------------------------------------------------

def _template(db):
    want = policy("intake_template", db)
    row = db.execute("SELECT id, name FROM stage_templates WHERE id = ?", (int(want),)).fetchone() if want else None
    row = row or db.execute("SELECT id, name FROM stage_templates ORDER BY id LIMIT 1").fetchone()
    stages = row and [r[0] for r in db.execute("SELECT name FROM stage_template_stages WHERE template_id = ? ORDER BY position", (row["id"],))]
    if not stages or len(stages) < 2:
        raise Refused(409, "Intake is not set up: Odin has no stage template with two stages or more (Settings › Rollouts & workflow)")
    return row["id"], stages[0]


def _owner(db):
    """The default project manager, else the first active Admin."""
    want = policy("intake_owner", db)
    row = db.execute("SELECT id FROM users WHERE id = ? AND active = 1 AND kind = 'internal'", (int(want),)).fetchone() if want else None
    row = row or db.execute("SELECT id FROM users WHERE active = 1 AND kind = 'internal' AND role = 'Admin' ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise Refused(409, "Intake is not set up: Odin has no active Admin to hold it")
    return row["id"]


def find(db, deal_id):
    return db.execute("SELECT * FROM projects WHERE intake_deal_id = ? AND deleted_at IS NULL ORDER BY id LIMIT 1", (deal_id,)).fetchone()


def shown(p):
    """A rollout as the intake answers describe it."""
    return {"id": p["id"], "name": p["name"], "client": p["client"], "deal_id": p["intake_deal_id"],
            "status": "pending" if p["intake_pending"] else "confirmed", "path": f"/projects/{p['id']}"}


def create(db, c, source):
    """(rollout row, created, audit details) for a checked body: the existing rollout when the deal id was
    seen before. The write lock is taken before the look-up, so two calls for one deal
    cannot both create it."""
    template_id, first_stage = _template(db)
    owner = _owner(db)
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    try:
        if (old := find(db, c["deal_id"])) is not None:
            db.rollback()
            if (old["intake_source"] or "").lower() != source.lower():
                # a deal id is the key only within one source: another CRM's rollout is not this caller's to read
                raise Refused(409, "That deal id is already taken by another source; send it with the token that created it")
            return old, False, None
        now = _now().isoformat()
        pid = db.execute(
            """INSERT INTO projects (name, client, po_number, stage, owner_id, target_end_date, delivery_mode, vendor_name, product_name,
               access_token, customer_token, stage_template_id, created_at, updated_at, stage_entered_at, customer_approval,
               intake_pending, intake_deal_id, intake_source, intake_contacts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (c["name"], c["client"], c["po_number"], first_stage, owner, c["target_date"], c["delivery_mode"], c["vendor"], c["product"],
             secrets.token_urlsafe(16), secrets.token_urlsafe(16), template_id, now, now, now, 1 if policy("default_customer_approval", db) else 0,
             c["deal_id"], source, json.dumps(c["contacts"]) if c["contacts"] else None)).lastrowid
        copy_template_stages(db, template_id, pid)
        changes = custom_fields.save(db, pid, c["fields"])
        set_project_manager(db, pid, owner)
        db.commit()
    except Exception:
        db.rollback()
        raise
    from services.notifications import notify_users
    notify_users([owner], "assigned", pid, f"New intake: {escape(c['name'])}",
                 f"<b>{escape(c['name'])}</b> for {escape(c['client'])} came in from {escape(source)} and waits for a project manager to confirm it.",
                 link="/projects?view=pending")
    # "rollout created" automations fire when staff confirm it (routes/intake.py), once the real
    # project manager is known: firing here put their tasks and notices on the placeholder owner
    return db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone(), True, (
        f"source={source} deal={c['deal_id']} client={c['client']}" + (f" fields: {'; '.join(changes)}" if changes else ""))


def handle(db, token, body, ip=None):
    """The whole call after authentication: (status, JSON body, audit details). Every call is
    logged in intake_calls; the details are set when a rollout was made, for the route to audit.
    `ip` is the caller's address as the app trusts it (request.remote_addr)."""
    deal = body.get("deal_id") if isinstance(body, dict) and isinstance(body.get("deal_id"), str) else None
    try:
        if not address_allowed(ip, db):
            raise Refused(403, f"Calls from {ip or 'an unknown address'} are not allowed (Settings › Integrations › Intake › Allowed addresses)")
        if not source_allowed(token):
            raise Refused(403, f"The token {token} is not an allowed source (Settings › Integrations › Intake)")
        if over_rate(db, token):
            refuse(db, token, 429, "over the limit for a minute", deal, result="rate_limited")
            return 429, {"error": f"Too many intakes from {token}: at most {policy('intake_rate_per_min', db)} a minute. Retry in a minute."}, None
        c, warnings = clean(body)
        p, created, details = create(db, c, token)
    except Refused as e:
        refuse(db, token, e.status, e.message, deal)
        return e.status, {"error": e.message}, None
    log_call(db, token, 201 if created else 200, "created" if created else "duplicate", c["deal_id"], p["id"])
    if not created:
        _audit_once(db, token, "intake_duplicate", 200, f"deal {c['deal_id']} already made rollout {p['id']}")
    return (201 if created else 200), {"created": created, "rollout": shown(p), "warnings": warnings if created else []}, details


# ---- the pending view ------------------------------------------------------------

def pending_rows(db=None):
    """The unconfirmed intakes, oldest first, for the Flow's holding lane and the list's view."""
    db = db or get_db()
    return [{"id": p["id"], "name": p["name"], "client": p["client"], "source": p["intake_source"], "deal_id": p["intake_deal_id"],
             "delivery_mode": p["delivery_mode"], "vendor_name": p["vendor_name"], "product_name": p["product_name"], "po_number": p["po_number"],
             "target_end_date": p["target_end_date"], "contacts": json.loads(p["intake_contacts"] or "[]"), "owner_name": p["owner_name"],
             "created_at": p["created_at"]}
            for p in db.execute("SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
                                "WHERE p.deleted_at IS NULL AND p.intake_pending = 1 ORDER BY p.id")]

