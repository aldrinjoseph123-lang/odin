"""Automations (Odin 2.0, workstream 6): when a trigger fires on a rollout and
every condition holds, the rule's actions run.

A rule is a trigger (EVENTS, with a little config for two of them), a list of
conditions (all must hold) and a list of actions. Rules reach staff and Teams
only, never the customer, and never move a stage: an action tells people,
adds a task from a template task, adds a RAID item, sets a field, or posts to
Teams. An admin writes them under Settings › Automations (manage_rules).

The one way in is `fire(event, project_id, context)`, called from the event
points (change_stage, project creation and the CRM intake, the document
upload, a field value saved, a customer's decline, an ask completed) and, for
the conditions only time brings, `scan(alerts)` from the alert pass. Inside a
request the firing waits for the end of the request (routes/rules.py), so a
rule sees the user's action whole and committed, and nothing a rule does can
break it: every failure is caught and written to the rule's run log.

Depth 1: while a rule's actions run, firing is suppressed, so a field a rule
sets never starts another rule. Each firing is one `rule_runs` row (the run
log, trimmed nightly past rule_runs_keep_days) and one audit row. A condition
the alert pass sees (an SLA breach, an overdue task, a missed milestone) fires
once per rule (the run's `event_key`), and only when it arose after the rule
was made or last resumed: a new rule does not flood the bell with the past.
"""
import json
from contextvars import ContextVar
from datetime import datetime, timedelta

from flask import g, has_app_context, has_request_context, session
from markupsafe import escape

from db import get_db
from policies import local_today, policy
from services.fmt import plural

EVENTS = {
    "rollout_created": "A rollout is created",
    "stage_entered": "A rollout enters a stage",
    "stage_sla_breached": "A stage goes over its SLA",
    "task_overdue": "A task becomes overdue",
    "ask_completed": "A customer or partner completes an ask",
    "document_uploaded": "A document is uploaded",
    "field_set": "A custom field is set",
    "stage_declined": "The customer declines a stage",
    "milestone_missed": "A milestone is missed",
}
CONDITIONS = {"stage": "Stage is", "delivery_mode": "Delivery mode is", "field": "Field equals", "client": "Client is"}
ACTIONS = {"notify": "Tell people (bell and email)", "add_task": "Add a task from a template task", "add_raid": "Add a RAID item",
           "set_field": "Set a field", "teams": "Post to Teams"}
STAFF_ROLES = ("Project manager", "Sales", "Coordinator")   # a rule never reaches the customer: no external role
SCANNED = ("stage_sla_breached", "task_overdue", "milestone_missed")
MAX_CONDITIONS = 10
MAX_ACTIONS = 10
SCAN_MAX = 200     # firings per scanned trigger per alert pass; a backlog drains over the next passes
RUNS_SHOWN = 100
REPLAY_DAYS = 30

_quiet = ContextVar("rules_quiet", default=False)


def _now():
    return datetime.utcnow()   # one clock, which the tests freeze


class ActionFailed(Exception):
    """An action that could not run, in words for the run log."""


# ---- what an admin writes ----------------------------------------------------------

def _options(db=None):
    db = db or get_db()
    from constants import DELIVERY_MODES
    from db import get_doc_category_names
    from services import fields
    from services.raid import KINDS, LEVELS
    stages = sorted({r[0] for r in db.execute("SELECT name FROM stage_template_stages UNION SELECT name FROM project_stages")}, key=str.lower)
    return {
        "stages": stages, "delivery_modes": list(DELIVERY_MODES), "categories": get_doc_category_names(),
        "fields": [{"id": f["id"], "name": f["name"], "kind": f["kind"], "choices": f["choices"]} for f in fields.definitions(db=db)],
        "roles": list(STAFF_ROLES), "raid_kinds": list(KINDS), "raid_levels": list(LEVELS),
        "users": [{"id": r[0], "name": r[1]} for r in db.execute("SELECT id, name FROM users WHERE active = 1 AND kind = 'internal' ORDER BY name")],
        "template_tasks": [{"id": r[0], "label": f"{r[1]} › {r[2]} › {r[3]}"} for r in db.execute(
            "SELECT tt.id, t.name, s.name, tt.title FROM template_tasks tt JOIN stage_template_stages s ON s.id = tt.stage_id "
            "JOIN stage_templates t ON t.id = s.template_id ORDER BY t.name, s.position, tt.position, tt.id")],
    }


def catalogue():
    """What the editor offers: the triggers, conditions and actions, and the values each may take."""
    return {"events": EVENTS, "conditions": CONDITIONS, "actions": ACTIONS, "options": _options()}


def _field_value(field_id, raw, label):
    """(field, stored value) for a field and a value an admin typed, or ValueError."""
    from services import fields
    f = fields.get(field_id) if isinstance(field_id, int) and not isinstance(field_id, bool) else None
    if f is None:
        raise ValueError(f"{label}: pick one of the custom fields")
    return f, fields.parse_value(f, raw)


def clean(body):
    """A rule from a posted body, checked, or ValueError naming what is wrong."""
    from core import as_bool, text_field
    from constants import DELIVERY_MODES
    from db import get_doc_category_names
    from services.raid import KINDS, LEVELS
    name = text_field(body.get("name"), 100, "Name")
    if not name:
        raise ValueError("Name the rule")
    event = body.get("event")
    if event not in EVENTS:
        raise ValueError("Pick what starts the rule")
    raw_cfg = body.get("event_config") or {}
    if not isinstance(raw_cfg, dict):
        raise ValueError("Send the trigger's settings as an object")
    cfg = {}
    if event == "document_uploaded" and raw_cfg.get("category"):
        if raw_cfg["category"] not in get_doc_category_names():
            raise ValueError("Pick one of the document categories, or any")
        cfg["category"] = raw_cfg["category"]
    if event == "field_set":
        f, value = _field_value(raw_cfg.get("field_id"), raw_cfg.get("value"), "Trigger")
        cfg = {"field_id": f["id"], "value": value}

    conditions = body.get("conditions") or []
    if not isinstance(conditions, list) or len(conditions) > MAX_CONDITIONS:
        raise ValueError(f"At most {MAX_CONDITIONS} conditions")
    conds = []
    for i, c in enumerate(conditions, 1):
        if not isinstance(c, dict) or c.get("kind") not in CONDITIONS:
            raise ValueError(f"Condition {i}: pick stage, delivery mode, field or client")
        kind = c["kind"]
        if kind == "field":
            f, value = _field_value(c.get("field_id"), c.get("value"), f"Condition {i}")
            conds.append({"kind": kind, "field_id": f["id"], "value": value})
            continue
        value = text_field(c.get("value"), 200, f"Condition {i}")
        if not value:
            raise ValueError(f"Condition {i}: say which {CONDITIONS[kind].split()[0].lower()}")
        if kind == "delivery_mode" and value not in DELIVERY_MODES:
            raise ValueError(f"Condition {i}: the delivery mode is one of {', '.join(DELIVERY_MODES)}")
        conds.append({"kind": kind, "value": value})

    actions = body.get("actions") or []
    if not isinstance(actions, list) or not actions:
        raise ValueError("Add at least one action")
    if len(actions) > MAX_ACTIONS:
        raise ValueError(f"At most {MAX_ACTIONS} actions")
    db = get_db()
    acts = []
    for i, a in enumerate(actions, 1):
        if not isinstance(a, dict) or a.get("kind") not in ACTIONS:
            raise ValueError(f"Action {i}: pick what it does")
        kind = a["kind"]
        if kind == "notify":
            roles = a.get("roles") or []
            ids = a.get("user_ids") or []
            if not isinstance(roles, list) or any(r not in STAFF_ROLES for r in roles):
                raise ValueError(f"Action {i}: tell the project manager, sales or coordinators (rules never reach the customer)")
            if not isinstance(ids, list) or any(not isinstance(u, int) or isinstance(u, bool) for u in ids):
                raise ValueError(f"Action {i}: pick people from the list")
            staff = {r[0] for r in db.execute("SELECT id FROM users WHERE active = 1 AND kind = 'internal'")}
            if any(u not in staff for u in ids):
                raise ValueError(f"Action {i}: only active staff accounts can be told")
            if not roles and not ids:
                raise ValueError(f"Action {i}: pick a role or a person to tell")
            email = a.get("email", True)
            if as_bool(email) is None:
                raise ValueError(f"Action {i}: send email as true or false")
            acts.append({"kind": kind, "roles": list(dict.fromkeys(roles)), "user_ids": list(dict.fromkeys(ids)), "email": as_bool(email),
                         "message": text_field(a.get("message"), 500, f"Action {i} message", multiline=True)})
        elif kind == "add_task":
            tid = a.get("template_task_id")
            if not isinstance(tid, int) or isinstance(tid, bool) or not db.execute("SELECT 1 FROM template_tasks WHERE id = ?", (tid,)).fetchone():
                raise ValueError(f"Action {i}: pick one of the template tasks")
            acts.append({"kind": kind, "template_task_id": tid})
        elif kind == "add_raid":
            if a.get("raid_kind") not in KINDS:
                raise ValueError(f"Action {i}: a RAID item is a risk, issue, decision or blocker")
            title = text_field(a.get("title"), 200, f"Action {i} title")
            if not title:
                raise ValueError(f"Action {i}: give the RAID item a title")
            impact = a.get("impact") or "medium"
            if impact not in LEVELS:
                raise ValueError(f"Action {i}: impact is low, medium or high")
            acts.append({"kind": kind, "raid_kind": a["raid_kind"], "title": title, "impact": impact})
        elif kind == "set_field":
            f, value = _field_value(a.get("field_id"), a.get("value"), f"Action {i}")
            if value is None:
                raise ValueError(f"Action {i}: say what {f['name']} is set to")
            acts.append({"kind": kind, "field_id": f["id"], "value": value})
        else:   # teams
            acts.append({"kind": kind, "message": text_field(a.get("message"), 500, f"Action {i} message", multiline=True)})
    return {"name": name, "event": event, "event_config": cfg, "conditions": conds, "actions": acts}


def _row(r, db):
    last = db.execute("SELECT at, ok FROM rule_runs WHERE rule_id = ? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()
    return {"id": r["id"], "name": r["name"], "event": r["event"], "event_config": json.loads(r["event_config"] or "{}"),
            "conditions": json.loads(r["conditions"] or "[]"), "actions": json.loads(r["actions"] or "[]"), "paused": bool(r["paused"]),
            "created_by": r["created_by"], "created_at": r["created_at"], "updated_at": r["updated_at"],
            "runs": db.execute("SELECT COUNT(*) FROM rule_runs WHERE rule_id = ?", (r["id"],)).fetchone()[0],
            "last_run": {"at": last["at"], "ok": bool(last["ok"])} if last else None}


def listing():
    db = get_db()
    return [_row(r, db) for r in db.execute("SELECT * FROM rules ORDER BY id")]


def get(rule_id):
    return get_db().execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()


def create(d, author):
    db = get_db()
    cap = policy("rules_max")
    if db.execute("SELECT COUNT(*) FROM rules").fetchone()[0] >= cap:
        raise ValueError(f"At most {cap} rules (Settings › Rollouts & workflow › Most automations)")
    now = _now().isoformat()
    cur = db.execute("INSERT INTO rules (name, event, event_config, conditions, actions, paused, armed_at, created_by, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
                     (d["name"], d["event"], json.dumps(d["event_config"]), json.dumps(d["conditions"]), json.dumps(d["actions"]), now, author, now, now))
    db.commit()
    return cur.lastrowid


def update(rule_id, d):
    db = get_db()
    db.execute("UPDATE rules SET name = ?, event = ?, event_config = ?, conditions = ?, actions = ?, updated_at = ? WHERE id = ?",
               (d["name"], d["event"], json.dumps(d["event_config"]), json.dumps(d["conditions"]), json.dumps(d["actions"]),
                _now().isoformat(), rule_id))
    db.commit()


def set_paused(rule_id, paused):
    """Pause, or resume: a resumed rule watches from now on (what the alert pass
    saw while it was paused does not all arrive at once)."""
    db = get_db()
    now = _now().isoformat()
    if paused:
        db.execute("UPDATE rules SET paused = 1, updated_at = ? WHERE id = ?", (now, rule_id))
    else:
        db.execute("UPDATE rules SET paused = 0, armed_at = ?, updated_at = ? WHERE id = ? AND paused = 1", (now, now, rule_id))
    db.commit()


def delete(rule_id):
    db = get_db()
    db.execute("DELETE FROM rule_runs WHERE rule_id = ?", (rule_id,))
    db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    db.commit()


def runs(rule_id, limit=RUNS_SHOWN):
    """The run log, newest first."""
    out = []
    for r in get_db().execute("SELECT rr.*, p.name AS project FROM rule_runs rr LEFT JOIN projects p ON p.id = rr.project_id "
                              "WHERE rr.rule_id = ? ORDER BY rr.id DESC LIMIT ?", (rule_id, limit)):
        try:
            detail = json.loads(r["detail"] or "{}")
        except ValueError:
            detail = {}
        out.append({"id": r["id"], "at": r["at"], "ok": bool(r["ok"]), "project_id": r["project_id"], "project": r["project"],
                    "what": detail.get("what", ""), "actions": detail.get("actions", [])})
    return out


def trim(db=None):
    """Run log rows past Settings › Retention (rule_runs_keep_days). Nightly (scheduler housekeeping)."""
    db = db or get_db()
    db.execute("DELETE FROM rule_runs WHERE at < ?", ((_now() - timedelta(days=policy("rule_runs_keep_days", db))).isoformat(),))
    db.commit()


# ---- firing --------------------------------------------------------------------------

def fire(event, project_id, context=None, key=None):
    """An event happened on a rollout: run the rules it starts. Never raises.
    Inside a request (routes/rules.py opened the queue) the firing waits for
    the end of the request; elsewhere (the scheduler, a test) it runs now.
    While a rule's actions run, nothing fires (depth 1). Returns how many
    rules ran now (0 when queued)."""
    if _quiet.get() or event not in EVENTS or not project_id:
        return 0
    queue = g.get("rules_later") if has_app_context() else None
    if queue is not None:
        queue.append((event, project_id, context or {}, key))
        return 0
    return _run(event, project_id, context or {}, key)


def flush():
    """Run what the request queued (routes/rules.py, after the request). Never raises.
    What the request wrote and did not commit is dropped first: a firing commits
    its own writes and nothing else."""
    queue = g.pop("rules_later", None) if has_app_context() else None
    if queue:
        discard_uncommitted()
    for event, project_id, context, key in queue or ():
        _run(event, project_id, context, key)


def discard_uncommitted():
    """Roll back the request's open transaction, if it left one. Never raises."""
    db = g.get("db") if has_app_context() else None
    try:
        if db is not None and db.in_transaction:
            db.rollback()
    except Exception:  # noqa: BLE001 — the connection is closed at teardown either way
        pass


def describe(event, ctx, db=None):
    """The event in words, for the run log, the audit row and the message."""
    if event == "rollout_created":
        return "Rollout created" + (f" from {ctx['source']}" if ctx.get("source") not in (None, "form") else "")
    if event == "stage_entered":
        return f"Entered {ctx.get('stage')}"
    if event == "stage_sla_breached":
        return f"Over the SLA in {ctx.get('stage')}"
    if event == "task_overdue":
        return f"Task overdue: {ctx.get('task')} (due {ctx.get('due')})"
    if event == "ask_completed":
        return f"Ask completed: {ctx.get('task')}"
    if event == "document_uploaded":
        return f"Document uploaded: {ctx.get('file')} ({ctx.get('category')})"
    if event == "field_set":
        from services import fields
        f = fields.get(ctx.get("field_id"))
        return f"{f['name']} set to {fields.shown(f['kind'], ctx.get('value'))}" if f else "A field was set"
    if event == "stage_declined":
        return f"Customer declined {ctx.get('stage')}"
    return f"Milestone missed: {ctx.get('milestone')} ({ctx.get('date')})"


def _matches_config(rule, cfg, ctx):
    if rule["event"] == "document_uploaded" and cfg.get("category"):
        return ctx.get("category") == cfg["category"]
    if rule["event"] == "field_set":
        return ctx.get("field_id") == cfg.get("field_id") and (cfg.get("value") is None or ctx.get("value") == cfg["value"])
    return True


def _holds(cond, project, ctx, db):
    kind, value = cond["kind"], cond.get("value")
    if kind == "stage":
        return (ctx.get("stage") or project["stage"]) == value
    if kind == "delivery_mode":
        return project["delivery_mode"] == value
    if kind == "client":
        return (project["client"] or "").strip().lower() == (value or "").strip().lower()
    row = db.execute("SELECT value FROM project_field_values WHERE project_id = ? AND field_id = ?", (project["id"], cond.get("field_id"))).fetchone()
    return (row[0] if row else None) == value


def matches(rule, project, ctx, db):
    """The trigger's config and every condition hold for this rollout and event."""
    cfg = json.loads(rule["event_config"] or "{}")
    return _matches_config(rule, cfg, ctx) and all(_holds(c, project, ctx, db) for c in json.loads(rule["conditions"] or "[]"))


def _run(event, project_id, ctx, key=None):
    ran = 0
    try:
        db = get_db()
        rows = db.execute("SELECT * FROM rules WHERE event = ? AND paused = 0 ORDER BY id", (event,)).fetchall()
        if not rows:
            return 0
        project = db.execute("SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
        if project is None:
            return 0
    except Exception:  # noqa: BLE001 — a rule never breaks the action that fired it
        _log_failure(event)
        return 0
    for rule in rows:
        try:
            if ctx.get("on") and ctx["on"] < rule["armed_at"][:10]:
                continue   # a scanned condition that arose before the rule was made or resumed
            if matches(rule, project, ctx, db):
                ran += _one(db, rule, project, event, ctx, key)
        except Exception:  # noqa: BLE001
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            _log_failure(event)
    return ran


def _log_failure(event):
    from flask import current_app
    if has_app_context():
        current_app.logger.exception("automation for %s failed", event)


def _one(db, rule, project, event, ctx, key):
    import sqlite3
    what = describe(event, ctx, db)
    now = _now().isoformat()
    try:   # the claim: one run per rule and scanned condition, even with two passes racing
        run_id = db.execute("INSERT INTO rule_runs (rule_id, project_id, event, event_key, at, ok, detail) VALUES (?, ?, ?, ?, ?, 0, ?)",
                            (rule["id"], project["id"], event, key, now, json.dumps({"what": what}))).lastrowid
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return 0
    done = []
    token = _quiet.set(True)
    try:
        for a in json.loads(rule["actions"] or "[]"):
            try:
                said = _act(db, rule, project, a, what)
                done.append({"kind": a.get("kind"), "ok": True, "said": said})
            except Exception as exc:  # noqa: BLE001 — logged in the run, never raised
                db.rollback()
                done.append({"kind": a.get("kind"), "ok": False, "said": str(exc)[:300] if isinstance(exc, (ActionFailed, ValueError)) else "failed: see the server log"})
                if not isinstance(exc, (ActionFailed, ValueError)):
                    _log_failure(event)
    finally:
        _quiet.reset(token)
    ok = all(d["ok"] for d in done)
    db.execute("UPDATE rule_runs SET ok = ?, detail = ? WHERE id = ?", (1 if ok else 0, json.dumps({"what": what, "actions": done}), run_id))
    db.commit()
    from services.audit import audit_log
    audit_log("rule_fired", "project", project["id"], project["name"],
              f"{rule['name'][:80]} (rule {rule['id']}): {what}; " + "; ".join(f"{d['kind']}: {'' if d['ok'] else 'FAILED '}{d['said']}" for d in done),
              actor=f"rule: {rule['name'][:60]}", db=db)
    return 1


def _act(db, rule, project, a, what):
    """Run one action; the words for the run log, or ActionFailed."""
    from db import touch_project
    kind = a.get("kind")
    subject = f"{escape(rule['name'])}: {escape(project['name'])}"
    body = (f"{escape(a['message'])}<br>" if a.get("message") else "") + f"{escape(what)} on <b>{escape(project['name'])}</b> ({escape(project['client'])})."
    if kind == "notify":
        from services.notifications import notify_users
        roles = [r for r in a.get("roles", []) if r in STAFF_ROLES]
        ids = [project["owner_id"]] if "Project manager" in roles else []
        if roles:
            marks = ",".join("?" * len(roles))
            ids += [r[0] for r in db.execute(f"SELECT pp.user_id FROM project_participants pp JOIN users u ON u.id = pp.user_id "
                                             f"WHERE pp.project_id = ? AND pp.role IN ({marks}) ORDER BY pp.id", (project["id"], *roles))]
        ids += a.get("user_ids", [])
        ids = list(dict.fromkeys(ids))
        if ids:   # staff only, active: whatever the roles hold, the customer is never told
            marks = ",".join("?" * len(ids))
            staff = {r[0] for r in db.execute(f"SELECT id FROM users WHERE active = 1 AND kind = 'internal' AND id IN ({marks})", ids)}
            ids = [i for i in ids if i in staff]
        actor = session.get("user_id") if has_request_context() else None
        told = [i for i in ids if i != actor]
        if not told:
            return "nobody to tell (the roles are empty, or only the person who did it)"
        notify_users(told, "automation", project["id"], subject, body, exclude_user_id=actor, link=f"/projects/{project['id']}", email=bool(a.get("email", True)))
        return f"told {len(told)} {plural(len(told), 'person', 'people')}"
    if kind == "add_task":
        from db import get_stage_names
        from services import template_tasks
        tt = db.execute("SELECT tt.*, s.name AS stage_name FROM template_tasks tt JOIN stage_template_stages s ON s.id = tt.stage_id WHERE tt.id = ?",
                        (a.get("template_task_id"),)).fetchone()
        if tt is None:
            raise ActionFailed("that template task no longer exists: edit the rule")
        stage = tt["stage_name"] if tt["stage_name"] in get_stage_names(project["id"]) else None
        # a rule never reaches the customer: a template task meant for the customer is left unassigned
        _, due = template_tasks.make_task(db, project, tt, stage, local_today(db), f"Automation: {rule['name'][:60]}", customer=False, created_at=_now().isoformat())
        touch_project(db, project["id"])
        db.commit()
        return f"added the task {tt['title']} (due {due})"
    if kind == "add_raid":
        from services import raid
        fields = raid.clean({"kind": a.get("raid_kind"), "title": a.get("title"), "impact": a.get("impact") or "medium"}, project["id"])
        raid.create(project["id"], fields, f"Automation: {rule['name'][:60]}")
        touch_project(db, project["id"])
        db.commit()
        return f"added the {fields['kind']} {fields['title']}"
    if kind == "set_field":
        from services import fields
        f = fields.get(a.get("field_id"))
        if f is None:
            raise ActionFailed("that field no longer exists: edit the rule")
        value = fields.parse_value(f, a.get("value"))   # a choice since removed is refused here, in words
        changed = fields.save(db, project["id"], {f["id"]: value})
        if changed:
            touch_project(db, project["id"])
        db.commit()
        return f"set {f['name']} to {fields.shown(f['kind'], value)}" if changed else f"{f['name']} was already {fields.shown(f['kind'], value)}"
    if kind == "teams":
        if not policy("notify_teams_enabled"):
            raise ActionFailed("Teams posts are switched off (Settings › Notifications)")
        from services.notifications import notify_event
        notify_event(project, subject, body, channels={"email": False, "teams": True})
        return "posted to Teams"
    raise ActionFailed(f"unknown action {kind}")


# ---- the alert pass ----------------------------------------------------------------

def _day_after(day):
    """A due day passed: the task (or milestone) is late from the next day."""
    from datetime import date
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def scan(alerts, today=None):
    """The triggers only time brings, from the alert pass (services/alerts.py):
    a stage over its SLA (per visit), a task overdue (per task and due day),
    a milestone missed (per milestone and day). Each fires once per rule;
    older than the run log keeps is never fired (its run row may be gone)."""
    try:
        db = get_db()
        live = {r[0] for r in db.execute("SELECT DISTINCT event FROM rules WHERE paused = 0")} & set(SCANNED)
        if not live:
            return
        today = today or local_today(db)
        floor = (today - timedelta(days=policy("rule_runs_keep_days", db))).isoformat()
        from db import PROJECT_OPEN_SQL, stages_for_projects
        if "stage_sla_breached" in live:
            # the day the breach was first recorded (its alert, when that alert is on), else the day the SLA ran out:
            # never today, or the same breach would fire again once its run row is trimmed
            from policies import local_date
            from services import workdays
            from services.analytics import sla_by_stage
            seen = {r[0]: r[1][:10] for r in db.execute("SELECT project_id, created_at FROM alerts WHERE alert_type = 'stage_sla_breach' AND resolved = 0")}
            over = alerts.get("stage_sla_breach", [])
            stages, cal, ran = stages_for_projects([p["id"] for p in over]), workdays.calendar(db), 0
            for p in over:
                on = seen.get(p["id"])
                if on is None:
                    entered, sla = local_date(p["stage_entered_at"], db), sla_by_stage(stages.get(p["id"]) or []).get(p["stage"])
                    on = workdays.add(entered, sla, cal).isoformat() if entered and sla else today.isoformat()
                if on >= floor:
                    ran += fire("stage_sla_breached", p["id"], {"stage": p["stage"], "on": on}, key=f"sla:{p['stage']}:{p['stage_entered_at']}")
                if ran >= SCAN_MAX:
                    break
        # candidates some live rule has not run for yet (the run log holds the rest); the cap counts runs, not candidates,
        # so conditions that match nobody never crowd out a new one
        unrun = ("EXISTS (SELECT 1 FROM rules r WHERE r.event = '{event}' AND r.paused = 0 AND NOT EXISTS "
                 "(SELECT 1 FROM rule_runs rr WHERE rr.rule_id = r.id AND rr.event_key = {key}))")
        task_unrun = unrun.format(event="task_overdue", key="'task:' || t.id || ':' || t.due_date")
        milestone_unrun = unrun.format(event="milestone_missed", key="'milestone:' || m.id || ':' || m.date")
        if "task_overdue" in live:
            ran = 0
            for t in db.execute(f"SELECT t.id, t.project_id, t.title, t.due_date FROM tasks t JOIN projects p ON p.id = t.project_id "
                                f"WHERE t.done = 0 AND t.due_date IS NOT NULL AND t.due_date < ? AND t.due_date >= ? AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} "
                                f"AND {task_unrun} "
                                f"ORDER BY t.due_date, t.id", (today.isoformat(), floor)).fetchall():
                ran += fire("task_overdue", t["project_id"], {"task": t["title"], "task_id": t["id"], "due": t["due_date"], "on": _day_after(t["due_date"])},
                            key=f"task:{t['id']}:{t['due_date']}")
                if ran >= SCAN_MAX:
                    break
        if "milestone_missed" in live:
            ran = 0
            for m in db.execute(f"SELECT m.id, m.project_id, m.name, m.date FROM milestones m JOIN projects p ON p.id = m.project_id "
                                f"WHERE m.done_at IS NULL AND m.date < ? AND m.date >= ? AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} "
                                f"AND {milestone_unrun} "
                                f"ORDER BY m.date, m.id", (today.isoformat(), floor)).fetchall():
                ran += fire("milestone_missed", m["project_id"], {"milestone": m["name"], "date": m["date"], "on": _day_after(m["date"])}, key=f"milestone:{m['id']}:{m['date']}")
                if ran >= SCAN_MAX:
                    break
    except Exception:  # noqa: BLE001 — the alert pass goes on
        _log_failure("the alert pass")


# ---- the dry run -------------------------------------------------------------------

REPLAY = {
    "rollout_created": "Rollouts created in the last 30 days.",
    "stage_entered": "Stage moves in the stage history of the last 30 days (a move that was undone is not there).",
    "stage_sla_breached": "SLA breaches recorded as alerts in the last 30 days (only while the Stage SLA breached alert is on); "
                          "the stage checked is the rollout's stage now.",
    "task_overdue": "Tasks that fell due in the last 30 days and were not done by their day.",
    "ask_completed": "Asks finished in the last 30 days.",
    "document_uploaded": "Documents uploaded in the last 30 days that are still on file.",
    "field_set": "Field changes in the audit trail of the last 30 days (values a rollout brought from the CRM are not replayed).",
    "stage_declined": "Customer declines in the last 30 days that a later move did not overtake.",
    "milestone_missed": "Milestones whose day fell in the last 30 days and that were not reached by it.",
}
CAVEAT = "Conditions are checked against each rollout as it is now, not as it was then. A dry run sends nothing and changes nothing."


def _replay(event, cfg, db, since, today):
    """(project id, context, when) for each event of the last 30 days, as far as Odin's records allow."""
    day = since[:10]
    if event == "rollout_created":
        return [(r[0], {"source": r[1] or "form"}, r[2]) for r in db.execute(
            "SELECT id, intake_source, created_at FROM projects WHERE created_at >= ? AND COALESCE(intake_pending, 0) = 0", (since,))]
    if event == "stage_entered":
        return [(r[0], {"stage": r[1], "from": r[2]}, r[3]) for r in db.execute(
            "SELECT project_id, stage, prev_stage, created_at FROM status_notes WHERE prev_stage IS NOT NULL AND created_at >= ?", (since,))]
    if event == "stage_sla_breached":
        return [(r[0], {"stage": None}, r[1]) for r in db.execute(
            "SELECT project_id, created_at FROM alerts WHERE alert_type = 'stage_sla_breach' AND created_at >= ?", (since,))]
    if event == "task_overdue":
        return [(r[0], {"task": r[1], "due": r[2]}, r[2]) for r in db.execute(
            "SELECT project_id, title, due_date FROM tasks WHERE due_date >= ? AND due_date < ? AND (done = 0 OR substr(done_at, 1, 10) > due_date)",
            (day, today))]
    if event == "ask_completed":
        return [(r[0], {"task": r[1]}, r[2]) for r in db.execute(
            "SELECT t.project_id, t.title, t.done_at FROM tasks t JOIN users u ON u.id = t.assignee_id WHERE u.kind = 'external' AND t.done = 1 AND t.done_at >= ?",
            (since,))]
    if event == "document_uploaded":
        return [(r[0], {"category": r[1], "file": r[2]}, r[3]) for r in db.execute(
            "SELECT project_id, category, filename, uploaded_at FROM documents WHERE deleted_at IS NULL AND review_status = 'accepted' AND uploaded_at >= ?", (since,))]
    if event == "field_set":
        from services import fields
        f = fields.get(cfg.get("field_id"))
        if f is None:
            return []
        out = []
        for r in db.execute("SELECT resource_id, details, timestamp FROM audit_logs WHERE action = 'update_field_values' AND resource_type = 'project' "
                            "AND timestamp >= ?", (since,)):
            for seg in (r[1] or "").split("; "):   # "Name: old → new", as services/fields.save wrote it
                if seg.startswith(f"{f['name']}: ") and " → " in seg:
                    new = seg.rsplit(" → ", 1)[1]
                    if new != "—":
                        out.append((r[0], {"field_id": f["id"], "value": new}, r[2]))
        return out
    if event == "stage_declined":
        return [(r[0], {"stage": r[1]}, r[2]) for r in db.execute(
            "SELECT project_id, stage, decided_at FROM stage_approvals WHERE status = 'declined' AND decided_at >= ?", (since,))]
    return [(r[0], {"milestone": r[1], "date": r[2]}, r[2]) for r in db.execute(
        "SELECT project_id, name, date FROM milestones WHERE date >= ? AND date < ? AND (done_at IS NULL OR substr(done_at, 1, 10) > date)", (day, today))]


def dry_run(d, now=None):
    """Which rollouts a rule (saved or not, already cleaned) would have matched
    in the last 30 days: per rollout, how often and the latest, plus what was
    replayed and what cannot be."""
    db = get_db()
    now = now or _now()
    since = (now - timedelta(days=REPLAY_DAYS)).isoformat()
    rule = {"event": d["event"], "event_config": json.dumps(d["event_config"]), "conditions": json.dumps(d["conditions"])}
    projects = {r["id"]: r for r in db.execute("SELECT * FROM projects WHERE deleted_at IS NULL")}
    hits = {}
    for pid, ctx, at in _replay(d["event"], d["event_config"], db, since, local_today(db).isoformat()):
        p = projects.get(pid)
        if p is None or not matches(rule, p, ctx, db):
            continue
        h = hits.setdefault(pid, {"project_id": pid, "name": p["name"], "client": p["client"], "times": 0, "last_at": at, "last": ""})
        h["times"] += 1
        if at >= h["last_at"]:
            h["last_at"], h["last"] = at, describe(d["event"], {**ctx, "stage": ctx.get("stage") or p["stage"]}, db)
    out = sorted(hits.values(), key=lambda h: h["last_at"], reverse=True)
    return {"matches": out[:200], "total": len(out), "replayed": REPLAY[d["event"]], "caveat": CAVEAT}
