"""Settings → AI: the server (with a Check before saving), its status, and
every AI feature's validation. The model is never called from here: checks
that need the model are queued for the scheduler's AI worker (services/ai)."""
import json

from flask import abort, flash, jsonify, redirect, request, session, url_for

from core import app, permission_required
from db import get_db, get_setting
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
    return jsonify(status=status(db), has_key=bool(get_setting(KEY_SETTING)), features=features, jobs=jobs, run_checks=checks,
                   scheduler_alive=healthy())


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
