"""Settings → AI: the server (with a Check before saving), its status, and
every AI feature's validation. The model is never called from here: checks
that need the model are queued for the scheduler's AI worker (services/ai)."""
import json

from flask import abort, flash, jsonify, redirect, request, session, url_for

from core import app, login_required, permission_required, project_allows
from db import get_db, get_setting
from routes.projects import load_project
from services.audit import audit_log


@app.route("/api/settings/ai")
@permission_required("manage_settings")
def api_settings_ai():
    from services.ai import FEATURES, latest_check, prompt_of, status, switch
    from services.ai.client import KEY_SETTING
    from scheduler import healthy
    db = get_db()
    features = []
    for f in FEATURES.values():
        on, forced = switch(f.key, db)
        cur, last = latest_check(f.key, db), latest_check(f.key, db, current=False)
        shown = cur or last
        features.append({
            "key": f.key, "label": f.label, "description": f.description, "runs": f.runs, "on": on, "forced": forced,
            "state": cur["state"] if cur else "pending", "current": bool(cur),
            "checked_at": shown["created_at"] if shown else None, "model": shown["model"] if shown else None,
            "seconds": shown["seconds"] if shown else None, "detail": shown["detail"] if shown else None,
            "output": json.loads(shown["output"]) if shown and shown["output"] else None, "prompt": f.prompt, "prompt_hash": prompt_of(f)[1],
        })
    jobs = [dict(r) for r in db.execute("SELECT id, kind, status, requested_by, created_at, started_at, finished_at, result, error, payload "
                                        "FROM ai_jobs WHERE kind = 'validate' ORDER BY id DESC LIMIT 5")]
    for j in jobs:
        for k in ("result", "payload"):
            j[k] = json.loads(j[k]) if j[k] else None
    last_run = jobs[0]["id"] if jobs else None
    checks = [dict(r) for r in db.execute("SELECT kind, state, seconds, detail, model, created_at FROM ai_checks WHERE run_id = ? AND kind != 'feature' ORDER BY id",
                                          (last_run,))] if last_run else []
    from datetime import datetime, timedelta
    day = db.execute("SELECT COUNT(*) AS calls, SUM(ok = 0) AS failed, AVG(seconds) AS avg_s, MAX(seconds) AS max_s, SUM(prompt_tokens) AS tokens_in, "
                     "SUM(completion_tokens) AS tokens_out FROM ai_calls WHERE at >= ?", ((datetime.utcnow() - timedelta(hours=24)).isoformat(),)).fetchone()
    return jsonify(status=status(db), has_key=bool(get_setting(KEY_SETTING)), features=features, jobs=jobs, run_checks=checks,
                   scheduler_alive=healthy(), usage={k: day[k] for k in day.keys()})


@app.route("/settings/ai/check", methods=["POST"])
@permission_required("manage_settings")
def settings_ai_check():
    """Before saving: does a server answer at this address, accept the key and
    have this model? One quick GET; no model work, so it may run here."""
    from policies import POLICIES, _parse
    from services.ai.client import address_problem, config
    from services.ai.health import connect
    cfg = config()
    try:
        cfg["base_url"] = _parse(POLICIES["ai_base_url"], request.form.get("ai_base_url", ""))
        cfg["model"] = _parse(POLICIES["ai_model"], request.form.get("ai_model", ""))
    except ValueError as exc:
        return jsonify(ok=False, messages=[f"Not checked: {exc}"], result={"ok": False, "reason": str(exc)})
    cfg["allow_external"] = request.form.get("ai_allow_external") == "on"
    if request.form.get("api_key"):
        cfg["key"] = request.form["api_key"]
    problem = address_problem(cfg["base_url"], cfg["allow_external"])
    result = {"ok": False, "reason": problem} if problem else connect(cfg)
    audit_log("check_ai_server", "settings", None, "ai", f"{cfg['base_url']} {cfg['model']}: {'ok' if result['ok'] else result['reason']}")
    msg = (f"The server answers and runs {result['model']}. Save to start using it; every feature is then validated on it."
           if result["ok"] else f"Not ready: {result['reason']}")
    return jsonify(ok=True, messages=[msg], result=result)


@app.route("/settings/ai/key", methods=["POST"])
@permission_required("manage_settings")
def settings_ai_key():
    """The API key, sealed. Blank keeps the saved one; clear removes it."""
    from db import set_setting
    from services.ai.client import KEY_SETTING
    from services.sealed import seal
    if request.form.get("clear"):
        get_db().execute("DELETE FROM settings WHERE key = ?", (KEY_SETTING,))
        get_db().commit()
        audit_log("clear_ai_key", "settings", None, "ai")
        flash("API key removed")
    elif request.form.get("api_key", "").strip():
        set_setting(KEY_SETTING, seal(request.form["api_key"].strip()))
        audit_log("set_ai_key", "settings", None, "ai")
        flash("API key saved")
    else:
        flash("Nothing changed")
    return redirect(url_for("settings_section", section="ai"))


@app.route("/settings/ai/validate", methods=["POST"])
@permission_required("manage_settings")
def settings_ai_validate():
    from services.ai import status
    from services.ai.health import queue
    if status()["state"] == "off":
        flash("Switch AI on and set the server address first")
        return redirect(url_for("settings_section", section="ai"))
    job = queue(get_db(), "validate", payload={"reason": "asked for in Settings"}, actor=session.get("user_name"))
    audit_log("validate_ai", "settings", job, "ai")
    flash("Validation queued. It runs every feature on its test project; this page updates as it goes.")
    return redirect(url_for("settings_section", section="ai"))


@app.route("/settings/ai/features/<key>", methods=["POST"])
@permission_required("manage_settings")
def settings_ai_feature(key):
    """Switch one feature on or off, or force it on without a passed check."""
    from db import set_setting
    from services.ai import FEATURES
    if key not in FEATURES:
        abort(404)
    on, forced = request.form.get("on") == "on", request.form.get("force") == "on"
    set_setting(f"ai.feature.{key}", "1" if on else "0")
    set_setting(f"ai.feature.{key}.force", "1" if forced else "0")
    audit_log("set_ai_feature", "settings", None, key, f"on={on} forced={forced}")
    flash(f"{FEATURES[key].label}: {'forced on' if forced else 'on' if on else 'off'}")
    return redirect(url_for("settings_section", section="ai"))


# ---- a feature on one rollout: ask for it, read it, dismiss it ------------

def _feature_for(project, key):
    """The feature, if this person may use it on this rollout (already loaded
    through load_project); else 404/403."""
    from services.ai import FEATURES
    project_id = project["id"]
    feature = FEATURES.get(key)
    if feature is None or feature.scope != "project":
        abort(404)
    if session.get("kind") == "external" or (feature.project_role and not project_allows(project_id, feature.project_role)):
        abort(403)
    return feature


def _suggestion_view(row):
    return {"id": row["id"], "payload": json.loads(row["payload"]), "model": row["model"], "seconds": row["seconds"],
            "created_at": row["created_at"], "status": row["status"]}


@app.route("/api/projects/<int:project_id>/ai/<key>")
@login_required
def api_project_ai(project_id, key):
    """Whether the feature can run here now, its latest unused draft, and the
    job drafting a new one, if any."""
    from services.ai import gate
    feature = _feature_for(load_project(project_id), key)
    db = get_db()
    row = db.execute("SELECT * FROM ai_suggestions WHERE project_id = ? AND feature = ? AND status = 'new' ORDER BY id DESC LIMIT 1", (project_id, key)).fetchone()
    job = db.execute("SELECT id, status, error, result, requested_by, created_at FROM ai_jobs WHERE kind = 'feature' AND feature = ? AND project_id = ? "
                     "ORDER BY id DESC LIMIT 1", (key, project_id)).fetchone()
    reason = gate(key, db)
    return jsonify(available=reason is None, reason=reason, label=feature.label, options=feature.options(project_id) if feature.options else None,
                   suggestion=_suggestion_view(row) if row else None,
                   job={"id": job["id"], "status": job["status"], "error": job["error"], "result": json.loads(job["result"]) if job["result"] else None,
                        "created_at": job["created_at"]} if job else None)


@app.route("/api/projects/<int:project_id>/ai/<key>", methods=["POST"])
@login_required
def api_project_ai_request(project_id, key):
    """Queue a fresh draft. The AI worker writes it; the page polls."""
    from services.ai import gate
    from services.ai.health import queue
    project = load_project(project_id)
    feature = _feature_for(project, key)
    reason = gate(key)
    if reason:
        return jsonify(error=reason), 409
    payload = None
    if feature.takes_input:
        given = (request.get_json(silent=True) or {}).get("input")
        if not isinstance(given, dict) or len(json.dumps(given)) > 20000:
            return jsonify(error="Nothing to work on"), 400
        payload = {"input": given}
    job = queue(get_db(), "feature", feature=key, project_id=project_id, payload=payload, actor=session.get("user_name"))
    audit_log("request_ai_draft", "project", project_id, project["name"], f"{key}, job {job}")
    return jsonify(ok=True, job=job)


@app.route("/api/projects/<int:project_id>/ai/suggestions/<int:suggestion_id>/dismiss", methods=["POST"])
@login_required
def api_project_ai_dismiss(project_id, suggestion_id):
    from datetime import datetime
    project = load_project(project_id)
    db = get_db()
    row = db.execute("SELECT * FROM ai_suggestions WHERE id = ? AND project_id = ?", (suggestion_id, project_id)).fetchone()
    if row is None:
        abort(404)
    _feature_for(project, row["feature"])
    db.execute("UPDATE ai_suggestions SET status = 'dismissed', decided_by = ?, decided_at = ? WHERE id = ? AND status = 'new'",
               (session.get("user_name"), datetime.utcnow().isoformat(), suggestion_id))
    db.commit()
    audit_log("dismiss_ai_draft", "project", project_id, project["name"], f"{row['feature']} suggestion {suggestion_id}")
    return jsonify(ok=True)


def use_suggestion(project_id, suggestion_id, features):
    """Mark a draft as used by the save that is about to happen. Returns the
    words for the audit row ("with the AI draft …"), or "" when there is none."""
    from datetime import datetime
    if not suggestion_id:
        return ""
    db = get_db()
    features = (features,) if isinstance(features, str) else tuple(features)
    row = db.execute(f"SELECT id, model FROM ai_suggestions WHERE id = ? AND project_id = ? AND feature IN ({','.join('?' * len(features))}) AND status = 'new'",
                     (suggestion_id, project_id, *features)).fetchone()
    if row is None:
        return ""
    db.execute("UPDATE ai_suggestions SET status = 'used', decided_by = ?, decided_at = ? WHERE id = ?",
               (session.get("user_name"), datetime.utcnow().isoformat(), row["id"]))
    return f", from AI draft {row['id']} ({row['model']}), edited by {session.get('user_name')}"


@app.route("/api/projects/<int:project_id>/ai/suggestions/<int:suggestion_id>/items/<int:index>", methods=["POST"])
@login_required
def api_project_ai_item(project_id, suggestion_id, index):
    """One proposal in a list-shaped draft (risks proposed): accepted (it was
    added through the normal route, which audits the new item) or dismissed.
    When every proposal is decided the draft is used or dismissed."""
    from datetime import datetime
    project = load_project(project_id)
    db = get_db()
    row = db.execute("SELECT * FROM ai_suggestions WHERE id = ? AND project_id = ? AND status = 'new'", (suggestion_id, project_id)).fetchone()
    if row is None:
        abort(404)
    _feature_for(project, row["feature"])
    body = request.get_json(silent=True) or {}
    decision = body.get("decision")
    payload = json.loads(row["payload"])
    items = payload.get("proposals") or []
    if decision not in ("accepted", "dismissed") or not 0 <= index < len(items):
        return jsonify(error="Unknown proposal or decision"), 400
    decisions = payload.setdefault("decisions", {})
    decisions[str(index)] = {"decision": decision, "by": session.get("user_name"), "raid_id": body.get("raid_id")}
    status = row["status"]
    if len(decisions) == len(items):
        status = "used" if any(d["decision"] == "accepted" for d in decisions.values()) else "dismissed"
    db.execute("UPDATE ai_suggestions SET payload = ?, status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
               (json.dumps(payload, ensure_ascii=False), status, session.get("user_name"), datetime.utcnow().isoformat(), suggestion_id))
    db.commit()
    audit_log("decide_ai_proposal", "project", project_id, project["name"], f"{row['feature']} suggestion {suggestion_id} item {index}: {decision}"
              + (f", RAID item {body['raid_id']}" if body.get("raid_id") else ""))
    return jsonify(ok=True, status=status)


@app.route("/api/projects/<int:project_id>/ai/suggestions/<int:suggestion_id>/close", methods=["POST"])
@login_required
def api_project_ai_close(project_id, suggestion_id):
    """A draft whose parts were taken through their own routes (a suggested
    plan: scope items and tasks, each added and audited there): record how
    many were taken and close it."""
    from datetime import datetime
    project = load_project(project_id)
    db = get_db()
    row = db.execute("SELECT * FROM ai_suggestions WHERE id = ? AND project_id = ? AND status = 'new'", (suggestion_id, project_id)).fetchone()
    if row is None:
        abort(404)
    _feature_for(project, row["feature"])
    taken = int((request.get_json(silent=True) or {}).get("taken") or 0)
    db.execute("UPDATE ai_suggestions SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
               ("used" if taken else "dismissed", session.get("user_name"), datetime.utcnow().isoformat(), suggestion_id))
    db.commit()
    audit_log("close_ai_draft", "project", project_id, project["name"], f"{row['feature']} suggestion {suggestion_id}: {taken} item(s) taken")
    return jsonify(ok=True)


@app.route("/api/projects/<int:project_id>/ai/jobs/<int:job_id>/cancel", methods=["POST"])
@login_required
def api_project_ai_cancel(project_id, job_id):
    """Stop a draft: a waiting one never runs; a running one's answer is
    dropped when it arrives."""
    from services.ai.health import cancel
    project = load_project(project_id)
    db = get_db()
    job = db.execute("SELECT id, feature FROM ai_jobs WHERE id = ? AND project_id = ? AND kind = 'feature'", (job_id, project_id)).fetchone()
    if job is None:
        abort(404)
    _feature_for(project, job["feature"])
    cancel(db, job_id)
    audit_log("cancel_ai_draft", "project", project_id, project["name"], f"{job['feature']} job {job_id}")
    return jsonify(ok=True)
