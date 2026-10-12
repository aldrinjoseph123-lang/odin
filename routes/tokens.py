"""Read-only API tokens and the small API they open (Settings › API tokens).

An admin names a token and picks how long it lives; the token is shown once
and only its SHA-256 is stored. A script sends it as
`Authorization: Bearer <token>` to the /api/v1 endpoints below, which read
projects, their stages and tasks, and saved reports — never write. A token
sees what internal staff see (every project). Behind Cloudflare Access,
/api/v1 needs its own Access policy (a service token) to be reachable.
"""
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import abort, flash, g, jsonify, redirect, request, session, url_for

from core import app, permission_required
from db import PROJECT_OPEN_SQL, get_db, get_stage_names
from routes.projects import load_project
from security import token_hash
from services.audit import audit_log

LIFETIMES = {"30": 30, "90": 90, "365": 365}



def token_required(view):
    """Bearer token → the view, or 401. Never falls back to a session."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        raw = header[7:].strip() if header.startswith("Bearer ") else ""
        now = datetime.utcnow().isoformat()
        row = raw and get_db().execute(
            "SELECT * FROM api_tokens WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?", (token_hash(raw), now)).fetchone()
        if not row:
            return jsonify(error="A valid API token is required (Authorization: Bearer <token>)"), 401
        db = get_db()
        if (row["last_used_at"] or "")[:10] != now[:10]:
            # one audit row per token per day, naming what it read first; last_used_at keeps the rest
            from services.audit import audit_log
            audit_log("api_token_read", "api_token", row["id"], row["name"], f"{request.method} {request.path}", actor=f"token:{row['name']}")
        db.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (now, row["id"]))
        db.commit()
        g.api_token = row["name"]
        return view(*args, **kwargs)
    return wrapped


@app.route("/settings/api-tokens", methods=["POST"])
@permission_required("manage_settings")
def api_token_create():
    name = request.form.get("name", "").strip()[:80]
    days = LIFETIMES.get(request.form.get("days", ""))
    if not name or not days:
        flash("Name the token and pick how long it lives", "error")
        return redirect(url_for("settings_section", section="api"))
    raw = f"odin_{secrets.token_urlsafe(32)}"
    now = datetime.utcnow()
    db = get_db()
    db.execute("DELETE FROM api_tokens WHERE (revoked_at IS NOT NULL OR expires_at < ?) AND created_at < ?",
               (now.isoformat(), (now - timedelta(days=90)).isoformat()))
    cur = db.execute("INSERT INTO api_tokens (name, token_hash, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                     (name, token_hash(raw), session.get("user_name", "?"), now.isoformat(), (now + timedelta(days=days)).isoformat()))
    db.commit()
    audit_log("create_api_token", "api_token", cur.lastrowid, name, f"read-only, {days} days")
    flash(f"Token for {name} (shown once — copy it now): {raw}")
    return redirect(url_for("settings_section", section="api"))


@app.route("/settings/api-tokens/<int:token_id>/revoke", methods=["POST"])
@permission_required("manage_settings")
def api_token_revoke(token_id):
    db = get_db()
    row = db.execute("SELECT * FROM api_tokens WHERE id = ? AND revoked_at IS NULL", (token_id,)).fetchone()
    if row is None:
        abort(404)
    db.execute("UPDATE api_tokens SET revoked_at = ? WHERE id = ?", (datetime.utcnow().isoformat(), token_id))
    db.commit()
    audit_log("revoke_api_token", "api_token", token_id, row["name"])
    flash(f"Revoked {row['name']}: it stops working now")
    return redirect(url_for("settings_section", section="api"))


# ---- the read-only API -------------------------------------------------------

def _project_json(p):
    return {k: p[k] for k in ("id", "name", "client", "stage", "delivery_mode", "vendor_name", "product_name",
                              "po_number", "start_date", "target_end_date", "created_at", "updated_at")} | {"owner": p["owner_name"]}


@app.route("/api/v1/projects")
@token_required
def api_v1_projects():
    """Active projects (?all=1 includes closed ones)."""
    where = "" if request.args.get("all") == "1" else f" AND {PROJECT_OPEN_SQL}"
    rows = get_db().execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.deleted_at IS NULL" + where + " ORDER BY p.id").fetchall()
    return jsonify(projects=[_project_json(p) for p in rows])


@app.route("/api/v1/projects/<int:project_id>")
@token_required
def api_v1_project(project_id):
    """One project with its stage list and tasks."""
    p = load_project(project_id)
    db = get_db()
    tasks = db.execute("SELECT t.title, t.stage, t.done, t.due_date, u.name AS assignee FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id "
                       "WHERE t.project_id = ? ORDER BY t.id", (project_id,)).fetchall()
    return jsonify(project=_project_json(p) | {"stages": get_stage_names(project_id)},
                   tasks=[dict(t) | {"done": bool(t["done"])} for t in tasks])


@app.route("/api/v1/projects/<int:project_id>/report")
@token_required
def api_v1_report(project_id):
    """The latest saved report version, as plain text."""
    load_project(project_id)
    row = get_db().execute("SELECT version, body, created_by, created_at FROM project_reports WHERE project_id = ? ORDER BY version DESC LIMIT 1",
                           (project_id,)).fetchone()
    if row is None:
        return jsonify(error="No saved report for this rollout"), 404
    return jsonify(dict(row))
