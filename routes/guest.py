"""Public guest routes — token-gated, no login.

Two links per project, two parties:
  access_token   → the vendor/outsourcer. May advance the stage one step.
  customer_token → the client. View and comment only.

Every write names its author, is rate limited, lands in the audit trail, and
notifies the project owner. Imported for its route-registration side effect.
"""
from datetime import datetime

from flask import abort, flash, make_response, redirect, render_template, request, url_for
from markupsafe import escape

from core import app
from db import get_db, get_setting, get_stage_names
from security import rate_limited
from services.audit import audit_log
from services.notifications import notify_event

GUEST_WRITES_PER_MINUTE = 10


def get_project_by_token(token):
    """Return (project, party) for a live token, else 404. When the admin has
    switched the anonymous links off (invited accounts replaced them), every
    token is dead: the old links must not keep working quietly."""
    if get_setting("guest_links_enabled", "1") != "1":
        abort(404)
    db = get_db()
    project = db.execute(
        "SELECT * FROM projects WHERE (access_token = ? OR customer_token = ?) AND deleted_at IS NULL",
        (token, token),
    ).fetchone()
    if project is None:
        abort(404)
    return project, ("vendor" if project["access_token"] == token else "customer")


def next_stage_for(project):
    """The one stage a vendor may move to: the next one, never the terminal
    stage — closing a project is an internal decision."""
    names = get_stage_names(project["id"])
    index = names.index(project["stage"]) if project["stage"] in names else -1
    return names[index + 1] if 0 <= index < len(names) - 2 else None


def _author(project, party):
    """'Name · Party' — a shared link is anonymous, so every write asks who."""
    who = request.form.get("author", "").strip()[:80]
    if not who:
        return None
    party_name = (project["outsourcer_name"] or "Vendor") if party == "vendor" else project["client"]
    return f"{who} · {party_name}"


def _guard(token):
    """Common front half of both write routes: throttle, then resolve author."""
    project, party = get_project_by_token(token)
    if rate_limited(f"guest:{token}", GUEST_WRITES_PER_MINUTE, 1):
        abort(429)
    author = _author(project, party)
    if not author:
        flash("Add your name so the team knows who wrote this")
        return project, party, None
    return project, party, author


@app.route("/guest/<token>")
def guest_view(token):
    project, party = get_project_by_token(token)
    db = get_db()
    # guest_visible only — internal notes must never reach the link holder
    notes = db.execute(
        "SELECT * FROM status_notes WHERE project_id = ? AND guest_visible = 1 ORDER BY created_at DESC",
        (project["id"],),
    ).fetchall()
    response = make_response(render_template(
        "guest_project.html", project=project, notes=notes, party=party,
        stages=get_stage_names(project["id"]),
        next_stage=next_stage_for(project) if party == "vendor" else None,
    ))
    # The token is the credential and it lives in the URL: keep it out of
    # referrers and search indexes.
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.route("/guest/<token>/stage", methods=["POST"])
def guest_stage(token):
    project, party, author = _guard(token)
    if party != "vendor":
        abort(403)
    if author is None:
        return redirect(url_for("guest_view", token=token))
    new_stage = request.form["stage"]
    if new_stage != next_stage_for(project):
        flash("Only the next stage can be set from this link")
        return redirect(url_for("guest_view", token=token))
    from services.signoff import gate
    if blocked := gate(project, new_stage):
        flash(blocked)
        return redirect(url_for("guest_view", token=token))
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute("UPDATE projects SET stage = ?, updated_at = ?, stage_entered_at = ? WHERE id = ?",
               (new_stage, now, now, project["id"]))
    note_text = request.form.get("note", "").strip() or f"Stage changed to {new_stage}"
    db.execute(
        "INSERT INTO status_notes (project_id, author, note, stage, created_at, guest_visible) VALUES (?, ?, ?, ?, ?, 1)",
        (project["id"], author, note_text, new_stage, now),
    )
    db.commit()
    audit_log("guest_stage_change", "project", project["id"], project["name"],
              f"stage={new_stage}; by={author}", actor=f"guest:{party}")
    notify_event(project, f"Vendor moved {escape(project['name'])} to {escape(new_stage)}",
                 f"{escape(author)}: {escape(note_text)}")
    return redirect(url_for("guest_view", token=token))


@app.route("/guest/<token>/note", methods=["POST"])
def guest_note(token):
    project, party, author = _guard(token)
    if author is None:
        return redirect(url_for("guest_view", token=token))
    note_text = request.form["note"].strip()[:5000]
    if note_text:
        db = get_db()
        now = datetime.utcnow().isoformat()
        db.execute(
            "INSERT INTO status_notes (project_id, author, note, stage, created_at, guest_visible) VALUES (?, ?, ?, ?, ?, 1)",
            (project["id"], author, note_text, project["stage"], now),
        )
        db.commit()
        audit_log("guest_note", "project", project["id"], project["name"],
                  f"by={author}", actor=f"guest:{party}")
        notify_event(project, f"New note on {escape(project['name'])}",
                     f"{escape(author)}: {escape(note_text)}")
    return redirect(url_for("guest_view", token=token))
