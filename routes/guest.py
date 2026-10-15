"""Public guest routes — token-gated, no login.

Two links per project, two parties:
  access_token   → the vendor/outsourcer. May advance the stage one step.
  customer_token → the client. View and comment only.

Every write names its author, is rate limited, lands in the audit trail, and
notifies the project owner. Imported for its route-registration side effect.
"""
from datetime import datetime, timedelta

from flask import abort, flash, make_response, redirect, render_template, request, url_for
from markupsafe import escape

from core import app
from db import get_db, get_setting, get_stage_names, get_terminal_stage, touch_project
from security import rate_limited
from services.audit import audit_log
from services.notifications import notify_event, notify_users


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
    party = "vendor" if project["access_token"] == token else "customer"
    # the vendor link exists only for Outsourced rollouts (the page never shows it elsewhere): a mode switched away kills it
    if party == "vendor" and project["delivery_mode"] != "Outsourced":
        abort(404)
    expires = links_expire(project)
    if expires and expires <= datetime.utcnow().isoformat():
        # said plainly, so the holder asks for a new link rather than thinking Odin is down (P2-6)
        abort(make_response(render_template("error.html", code=410, title="This link has expired",
                                            hint="Guest links last a set time. Ask the project manager for a new one."), 410))
    return project, party


def links_expire(project):
    """When the project's guest links stop working (UTC ISO timestamp), or
    None when they never expire: policy guest_link_days, counted from when
    they were minted (creation, or the last rotation)."""
    from policies import policy
    days = policy("guest_link_days")
    minted = project["guest_tokens_at"] or project["created_at"]
    return (datetime.fromisoformat(minted[:19]) + timedelta(days=days)).isoformat() if days and minted else None


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
    from policies import policy
    project, party = get_project_by_token(token)
    if rate_limited(f"guest:{token}", policy("guest_writes_per_minute"), 1):
        abort(429)
    if project["stage"] == get_terminal_stage(project["id"]):   # a closed rollout is read-only through a link
        abort(403)
    author = _author(project, party)
    if not author:
        flash("Add your name so the team knows who wrote this", "error")
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
    new_stage = request.form.get("stage", "")
    if new_stage != next_stage_for(project):
        flash("Only the next stage can be set from this link", "error")
        return redirect(url_for("guest_view", token=token))
    # the same path as a staff move: the sign-off gate, history, customer
    # approval when the project asks for it, and the whole team is told
    from routes.projects import change_stage
    if error := change_stage(project["id"], new_stage, request.form.get("note", "").strip()[:5000], guest=(author, party)):
        flash(error, "error")
    return redirect(url_for("guest_view", token=token))


@app.route("/guest/<token>/note", methods=["POST"])
def guest_note(token):
    project, party, author = _guard(token)
    if author is None:
        return redirect(url_for("guest_view", token=token))
    note_text = request.form.get("note", "").strip()[:5000]
    if note_text:
        db = get_db()
        now = datetime.utcnow().isoformat()
        db.execute(
            "INSERT INTO status_notes (project_id, author, note, stage, created_at, guest_visible) VALUES (?, ?, ?, ?, ?, 1)",
            (project["id"], author, note_text, project["stage"], now),
        )
        touch_project(db, project["id"])   # a vendor's word is activity, as a staff note is (sim L-19)
        db.commit()
        audit_log("guest_note", "project", project["id"], project["name"],
                  f"by={author}", actor=f"guest:{party}")
        # the project manager's bell (and mail), plus the Teams channel
        notify_users([project["owner_id"]], "activity", project["id"], f"New note on {escape(project['name'])}", f"{escape(author)} (guest link): {escape(note_text)}")
        notify_event(project, f"New note on {escape(project['name'])}",
                     f"{escape(author)}: {escape(note_text)}", channels={"email": False, "teams": True})
    return redirect(url_for("guest_view", token=token))
