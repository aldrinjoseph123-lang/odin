"""Is the AI usable, and on which model? The heartbeat, validation and the
job queue, run by the scheduler's AI worker (a thread beside its clock, so a
ten-minute validation never delays a backup or the digest).

- heartbeat: GET /models every few minutes; no model work. Two misses in a
  row (policy) mark the AI down, once, with one bell to the admins; one more
  when it is back. It also reads the model's fingerprint (id + created): a
  change means the model behind the name was rebuilt or replaced, and every
  feature must pass validation again before it runs.
- validation: connect, one tiny structured answer (the speed shown in
  Settings), then every feature on its synthetic project, graded. After a
  settings change, daily at the policy time, on a model change, and when a
  feature has no check for the current model and prompt.
- jobs: ai_jobs rows the web app queues and this worker runs, so no web
  request ever waits on the model.
"""
import json
import logging
from datetime import datetime, timedelta

from services.ai import FEATURES, STALE_KEYS, STATUS_SETTING, prompt_of, run, status
from services.ai.client import AIError, chat, config, find_model, fingerprint, list_models

SMOKE_SCHEMA = {"type": "object", "properties": {"status": {"type": "string", "enum": ["ready"]}, "echo": {"type": "integer"}},
                "required": ["status", "echo"]}


def _now():
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _put(db, key, value):
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    db.commit()


def _notify_admins(db, subject, message, email=True):
    from services.notifications import notify_users
    admins = [r[0] for r in db.execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
    notify_users(admins, "ai", None, subject, message, link="/settings/ai", email=email)


def connect(cfg):
    """{ok, reason, model, fingerprint, models}: the server answers, the key
    is accepted, the configured model is there."""
    try:
        models = list_models(cfg)
    except AIError as exc:
        return {"ok": False, "reason": exc.reason, "kind": exc.kind, "models": []}
    m = find_model(models, cfg["model"])
    ids = [x["id"] for x in models]
    if not m:
        return {"ok": False, "reason": f"The server answers, but has no model named {cfg['model']} (it has {', '.join(ids[:8]) or 'none'})",
                "kind": "model", "models": ids}
    return {"ok": True, "reason": None, "model": m["id"], "fingerprint": fingerprint(m), "models": ids}


def heartbeat(db):
    """One beat: update the stored status, tell the admins on a change of
    state, queue validation when the model changed. Returns the new status."""
    from policies import policy
    prev = status(db)
    if prev["state"] == "off":
        return prev
    c = connect(config(db))
    now = _now()
    if c["ok"]:
        new = {"state": "up", "since": prev.get("since") if prev.get("state") == "up" else now, "checked_at": now, "misses": 0,
               "fingerprint": c["fingerprint"], "model": c["model"], "error": None, "seconds": prev.get("seconds")}
        _put(db, STATUS_SETTING, json.dumps(new))
        if prev.get("state") == "down":
            _notify_admins(db, "The AI server is answering again", f"{c['model']} is back. AI features that passed validation are running again.")
        if prev.get("fingerprint") and prev["fingerprint"] != c["fingerprint"]:
            queue(db, "validate", payload={"reason": f"the model changed ({prev['fingerprint']} to {c['fingerprint']})"})
        elif any(not _has_current_check(db, f, c["fingerprint"]) for f in FEATURES.values()) and not _validated_recently(db):
            queue(db, "validate", payload={"reason": "features not yet validated on this model"})
        return new
    misses = int(prev.get("misses") or 0) + 1
    down = misses >= policy("ai_down_after", db)
    new = {**{k: v for k, v in prev.items() if k not in STALE_KEYS}, "state": "down" if down else prev.get("state", "unknown"), "checked_at": now, "misses": misses, "error": c["reason"]}
    if down and prev.get("state") != "down":
        new["since"] = now
        _notify_admins(db, "The AI server is not answering",
                       f"{c['reason']}. AI features have stopped; Odin is using its usual behaviour until the server is back.")
    _put(db, STATUS_SETTING, json.dumps(new))
    return new


def _has_current_check(db, feature, fp):
    return db.execute("SELECT 1 FROM ai_checks WHERE kind = 'feature' AND feature = ? AND fingerprint = ? AND prompt_hash = ?",
                      (feature.key, fp, prompt_of(feature)[1])).fetchone() is not None


def _validated_recently(db, minutes=30):
    since = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
    return db.execute("SELECT 1 FROM ai_jobs WHERE kind = 'validate' AND (status IN ('queued', 'running') OR created_at > ?)", (since,)).fetchone() is not None


def _record(db, run_id, kind, state, feature=None, seconds=None, detail=None, output=None, model=None, fp=None, prompt_hash=None):
    db.execute("INSERT INTO ai_checks (run_id, kind, feature, model, fingerprint, prompt_hash, state, seconds, detail, output, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (run_id, kind, feature, model, fp, prompt_hash, state, seconds, detail,
                json.dumps(output, ensure_ascii=False) if output is not None else None, _now()))
    db.commit()


def validate_feature(db, feature, cfg, fp, run_id=None):
    """Run one feature on its synthetic project and grade the answer."""
    from policies import policy
    inputs = feature.fixture()
    try:
        out, meta = run(feature, inputs, cfg, log={"job_id": run_id, "user": "validation"})
        problems = [p for p in (g(inputs, out) for g in feature.graders) if p]
    except Exception as exc:  # noqa: BLE001 — a grader that crashes fails its feature; unrecorded, validation would be queued again every 30 minutes
        reason = exc.reason if isinstance(exc, AIError) else f"{type(exc).__name__}: {exc}"[:300]
        _record(db, run_id, "feature", "failed", feature.key, detail=reason, model=cfg["model"], fp=fp, prompt_hash=prompt_of(feature)[1])
        return "failed"
    budget = feature.budget_s or policy("ai_budget_s", db)
    state = "failed" if problems else "slow" if meta["seconds"] > budget else "passed"
    detail = "; ".join(problems) if problems else (f"{meta['seconds']} s, over the {budget} s budget" if state == "slow" else None)
    _record(db, run_id, "feature", state, feature.key, meta["seconds"], detail, out, meta["model"], fp, meta["prompt_hash"])
    return state


def validate_all(db, run_id=None):
    """Connect, one structured answer, then every feature. Returns a summary."""
    cfg = config(db)
    st = heartbeat(db)
    if st.get("state") != "up":
        _record(db, run_id, "connect", "failed", detail=st.get("error") or "AI is switched off")
        return {"ok": False, "reason": st.get("error") or "AI is switched off"}
    fp = st["fingerprint"]
    _record(db, run_id, "connect", "passed", model=st["model"], fp=fp)
    try:
        from services.ai import system_prompt
        out, meta = chat(cfg, [{"role": "system", "content": system_prompt("_smoke.v1.txt")},
                               {"role": "user", "content": "7"}], SMOKE_SCHEMA, max_tokens=40, temperature=0, log={"feature": "_smoke", "job_id": run_id})
        ok = out.get("echo") == 7
        _record(db, run_id, "smoke", "passed" if ok else "failed", seconds=meta["seconds"], output=out, model=meta["model"], fp=fp,
                detail=None if ok else "answered in the right form but with the wrong content")
        _put(db, STATUS_SETTING, json.dumps({**{k: v for k, v in status(db).items() if k not in STALE_KEYS}, "seconds": meta["seconds"]}))
    except AIError as exc:
        _record(db, run_id, "smoke", "failed", detail=exc.reason, model=cfg["model"], fp=fp)
        return {"ok": False, "reason": exc.reason}
    results = {f.key: validate_feature(db, f, cfg, fp, run_id) for f in FEATURES.values()}
    # a validation queued while this one ran (or before a direct call) has nothing left to prove
    db.execute("UPDATE ai_jobs SET status = 'done', finished_at = ?, result = ? WHERE kind = 'validate' AND status = 'queued' AND id IS NOT ?",
               (_now(), json.dumps({"skipped": "validated just before"}), run_id))
    db.commit()
    failed = [FEATURES[k].label for k, s in results.items() if s == "failed"]
    if failed:
        _notify_admins(db, "AI features failed validation",
                       f"On {st['model']}: {', '.join(failed)}. They are off, and Odin uses its usual behaviour for them, until they pass again.")
    return {"ok": True, "model": st["model"], "seconds": meta["seconds"], "features": results}



def queue(db, kind, feature=None, project_id=None, payload=None, actor=None):
    """Add a job for the AI worker. A validation already waiting or running
    is not queued twice. Returns the job id."""
    if kind == "validate":
        row = db.execute("SELECT id FROM ai_jobs WHERE kind = 'validate' AND status IN ('queued', 'running')").fetchone()
        if row:
            return row[0]
    if kind == "feature" and not (payload or {}).get("user_id") and "input" not in (payload or {}):   # someone's own words are never merged
        row = db.execute("SELECT id FROM ai_jobs WHERE kind = 'feature' AND feature = ? AND project_id IS ? AND status IN ('queued', 'running')",
                         (feature, project_id)).fetchone()
        if row:
            return row[0]
    cur = db.execute("INSERT INTO ai_jobs (kind, feature, project_id, payload, status, requested_by, created_at) VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                     (kind, feature, project_id, json.dumps(payload or {}), actor, _now()))
    db.commit()
    return cur.lastrowid


def run_feature_job(db, job):
    """A feature for one project: gate, gather, ask, keep the answer as a
    suggestion. A nightly run skips a rollout whose facts have not changed
    since its last unused draft."""
    import hashlib
    from services.ai import FEATURES, gate
    feature = FEATURES.get(job["feature"])
    if feature is None:
        raise ValueError(f"no AI feature {job['feature']}")
    reason = gate(feature.key, db)
    if reason:
        return {"skipped": reason}
    if feature.scope == "portfolio":
        return _run_portfolio(db, feature, job)
    if feature.scope == "person":
        return _run_person(db, feature, job)
    try:
        raw = job["payload"] if "payload" in job.keys() else None
        given = (json.loads(raw) if isinstance(raw, str) else raw or {}).get("input")
        inputs = feature.gather(project_id=job["project_id"], **({"given": given} if feature.takes_input else {}))
    except AIError as exc:
        if exc.kind == "skip":   # nothing to do for this rollout (a green one has no amber to explain)
            return {"skipped": exc.reason}
        raise
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:16]
    last = db.execute("SELECT inputs_hash FROM ai_suggestions WHERE project_id = ? AND feature = ? AND status = 'new' ORDER BY id DESC LIMIT 1",
                      (job["project_id"], feature.key)).fetchone()
    if job["requested_by"] is None and last and last[0] == digest:
        return {"skipped": "nothing changed since the last draft"}
    out, meta = run(feature, inputs, config(db), log={"job_id": job["id"], "project_id": job["project_id"], "user": job["requested_by"] or "night shift"})
    if _cancelled(db, job):
        return {"skipped": "cancelled"}
    db.execute("UPDATE ai_suggestions SET status = 'superseded' WHERE project_id = ? AND feature = ? AND status = 'new'", (job["project_id"], feature.key))
    cur = db.execute("INSERT INTO ai_suggestions (project_id, feature, payload, inputs_hash, model, fingerprint, prompt_hash, seconds, job_id, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (job["project_id"], feature.key, json.dumps(out, ensure_ascii=False), digest, meta["model"], status(db).get("fingerprint"),
                      meta["prompt_hash"], meta["seconds"], job["id"], _now()))
    db.commit()
    if feature.on_new and job["requested_by"] is None:   # a night-shift answer: tell whoever should look at it
        try:
            feature.on_new(db, job["project_id"], out)
        except Exception as exc:  # noqa: BLE001 — a notice that fails never loses the answer
            logging.getLogger("odin.ai").warning("%s notice failed: %s", feature.key, exc)
    return {"suggestion": cur.lastrowid, "seconds": meta["seconds"], "model": meta["model"]}


def _run_person(db, feature, job):
    """A feature for one person (the morning brief): asked, then handed to
    on_new to deliver; the call log keeps the record."""
    user_id = json.loads(job["payload"] or "{}").get("user_id") if isinstance(job["payload"], str) else (job["payload"] or {}).get("user_id")
    try:
        inputs = feature.gather(user_id=user_id)
    except AIError as exc:
        if exc.kind == "skip":
            return {"skipped": exc.reason}
        raise
    out, meta = run(feature, inputs, config(db), log={"job_id": job["id"], "user": f"user {user_id}"})
    if _cancelled(db, job):
        return {"skipped": "cancelled"}
    feature.on_new(db, user_id, out)
    return {"delivered_to": user_id, "seconds": meta["seconds"], "model": meta["model"]}


def _run_portfolio(db, feature, job):
    """A portfolio-wide feature: the answer is kept as the latest one (settings
    ai.latest.<key>), with its model and prompt, for the place that shows it."""
    import hashlib
    inputs = feature.gather()
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:16]
    row = db.execute("SELECT value FROM settings WHERE key = ?", (f"ai.latest.{feature.key}",)).fetchone()
    if job["requested_by"] is None and row and json.loads(row[0]).get("inputs_hash") == digest:
        return {"skipped": "nothing changed since the last answer"}
    out, meta = run(feature, inputs, config(db), log={"job_id": job["id"], "user": job["requested_by"] or "night shift"})
    _put(db, f"ai.latest.{feature.key}", json.dumps({"payload": out, "model": meta["model"], "fingerprint": status(db).get("fingerprint"),
                                                     "prompt_hash": meta["prompt_hash"], "seconds": meta["seconds"], "inputs_hash": digest,
                                                     "created_at": _now()}, ensure_ascii=False))
    return {"seconds": meta["seconds"], "model": meta["model"]}


def _cancelled(db, job):
    """Did someone cancel this job while the model was answering? Its answer
    is then dropped (the server finishes the request it was given)."""
    if not job["id"]:
        return False
    row = db.execute("SELECT status FROM ai_jobs WHERE id = ?", (job["id"],)).fetchone()
    return bool(row) and row[0] == "cancelling"


def cancel(db, job_id):
    """Cancel a job: a waiting one never runs; a running one's answer is dropped."""
    db.execute("UPDATE ai_jobs SET status = CASE status WHEN 'queued' THEN 'cancelled' ELSE 'cancelling' END, "
               "finished_at = CASE status WHEN 'queued' THEN ? ELSE finished_at END WHERE id = ? AND status IN ('queued', 'running')", (_now(), job_id))
    db.commit()


def work_once(db):
    """Run the oldest waiting job. Returns its id, or None when idle."""
    job = db.execute("SELECT * FROM ai_jobs WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
    if not job:
        return None
    # compare-and-set: a second worker (the --once cron beside the service) or a cancel got there first
    claimed = db.execute("UPDATE ai_jobs SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'", (_now(), job["id"])).rowcount
    db.commit()
    if not claimed:
        return None
    try:
        if job["kind"] == "validate":
            result = validate_all(db, job["id"])
        elif job["kind"] == "feature":
            result = run_feature_job(db, job)
        else:
            raise ValueError(f"unknown AI job kind {job['kind']}")
        db.execute("UPDATE ai_jobs SET status = CASE status WHEN 'cancelling' THEN 'cancelled' ELSE 'done' END, finished_at = ?, result = ? WHERE id = ?",
                   (_now(), json.dumps(result), job["id"]))
    except Exception as exc:  # noqa: BLE001 — a failed job is recorded, never fatal to the worker
        db.execute("UPDATE ai_jobs SET status = 'failed', finished_at = ?, error = ? WHERE id = ?", (_now(), str(exc)[:500], job["id"]))
    db.commit()
    return job["id"]


def fail_interrupted(db):
    """At the scheduler's start: no AI worker runs yet, so any job still
    'running' or 'cancelling' was cut off by the last stop. Fail it now rather
    than an hour later (tick's own sweep, for cron mode)."""
    db.execute("UPDATE ai_jobs SET status = 'failed', error = 'interrupted', finished_at = ? WHERE status IN ('running', 'cancelling')", (_now(),))
    db.commit()


def tick(db, now_local=None):
    """One pass of the AI worker: heartbeat when due, the daily validation
    when due, then one waiting job."""
    from policies import local_now, policy
    if status(db)["state"] == "off":
        return None
    # a job left "running" by a worker that died is not running
    stale = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    db.execute("UPDATE ai_jobs SET status = 'failed', error = 'interrupted', finished_at = ? WHERE status IN ('running', 'cancelling') AND started_at < ?", (_now(), stale))
    db.commit()
    st = status(db)
    last = st.get("checked_at")
    if not last or datetime.fromisoformat(last) <= datetime.utcnow() - timedelta(minutes=policy("ai_heartbeat_minutes", db)):
        heartbeat(db)
    now_local = now_local or local_now(db)
    today = now_local.date().isoformat()
    row = db.execute("SELECT value FROM settings WHERE key = 'ai.validate.last_date'").fetchone()
    if now_local.strftime("%H:%M") >= policy("ai_validate_time", db) and (row[0] if row else "") < today:
        _put(db, "ai.validate.last_date", today)
        queue(db, "validate", payload={"reason": "daily validation"})
    from policies import is_working_day
    row = db.execute("SELECT value FROM settings WHERE key = 'ai.brief.last_date'").fetchone()
    if now_local.strftime("%H:%M") >= policy("ai_brief_time", db) and (row[0] if row else "") < today:
        _put(db, "ai.brief.last_date", today)
        if is_working_day(now_local.date(), db):
            morning_briefs(db)
    row = db.execute("SELECT value FROM settings WHERE key = 'ai.night.last_date'").fetchone()
    if now_local.strftime("%H:%M") >= policy("ai_night_time", db) and (row[0] if row else "") < today:
        _put(db, "ai.night.last_date", today)
        night_shift(db)
    return work_once(db)


def morning_briefs(db):
    """Queue one brief per person with open rollouts, for each daily person feature switched on."""
    from services.ai import FEATURES, switch
    n = 0
    for f in FEATURES.values():
        if f.runs != "daily" or f.scope != "person" or not switch(f.key, db)[0]:
            continue
        for uid in f.extra.get("people", _people)(db):
            queue(db, "feature", feature=f.key, payload={"user_id": uid})
            n += 1
    return n


def _people(db):
    from services.ai.features.morning_brief import people
    return people(db)


def night_shift(db):
    """Queue every nightly feature for every open rollout. The gate is asked
    when each job runs, after the daily validation ahead of it in the queue."""
    from db import PROJECT_OPEN_SQL
    from services.ai import FEATURES, switch
    nightly = [f for f in FEATURES.values() if f.runs == "nightly" and switch(f.key, db)[0]]
    if not nightly:
        return 0
    ids = [r[0] for r in db.execute(f"SELECT p.id FROM projects p WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} ORDER BY p.id")]
    n = 0
    for f in nightly:
        for pid in (ids if f.scope == "project" else [None]):
            queue(db, "feature", feature=f.key, project_id=pid)
            n += 1
    return n


def trim(db=None):
    """Checks, finished jobs, suggestions (decided or left "new" by nobody)
    and the request log older than the policy ai_keep_days. Nightly."""
    from db import get_db
    from policies import policy
    db = db or get_db()
    cutoff = (datetime.utcnow() - timedelta(days=policy("ai_keep_days", db))).isoformat()
    db.execute("DELETE FROM ai_checks WHERE created_at < ?", (cutoff,))
    db.execute("DELETE FROM ai_jobs WHERE status IN ('done', 'failed', 'cancelled') AND created_at < ?", (cutoff,))
    db.execute("DELETE FROM ai_suggestions WHERE created_at < ?", (cutoff,))
    db.execute("DELETE FROM ai_calls WHERE at < ?", (cutoff,))
    db.commit()


def job_progress(db, job):
    """Where a queued or running draft stands, for the page's progress bar:
    how many jobs are ahead of it, when it started, and how long this feature
    usually takes (the median of its last real drafts, else its last test,
    else its time budget). The model does not stream, so this is an estimate
    the page counts towards; it never claims to be done before the answer is."""
    from services.ai import latest_check
    from policies import policy
    ahead = 0
    if job["status"] == "queued":
        ahead = db.execute("SELECT COUNT(*) FROM ai_jobs WHERE id < ? AND status IN ('queued', 'running', 'cancelling')", (job["id"],)).fetchone()[0]
    times = sorted(r[0] for r in db.execute(
        "SELECT seconds FROM ai_suggestions WHERE feature = ? AND seconds > 0 ORDER BY id DESC LIMIT 7", (job["feature"],)))
    expected = times[len(times) // 2] if times else None
    if expected is None and job["feature"] in FEATURES:
        check = latest_check(job["feature"], db, current=False)
        expected = check["seconds"] if check and check["seconds"] else None
    if expected is None:
        feature = FEATURES.get(job["feature"])
        expected = (feature.budget_s if feature and feature.budget_s else None) or policy("ai_budget_s", db)
    return {"ahead": ahead, "started_at": job["started_at"], "expected_s": round(float(expected), 1)}
