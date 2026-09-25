"""Outbound notifications: Outlook mail + Teams channel messages via Graph.

Best-effort — never raises, so a Graph outage can't break a project update.
Depends on db (for the admin on/off toggles and the owner's email) and graph.
"""
from flask import url_for

import graph
from db import get_db, get_setting


def project_link(project_id, user):
    """The line that lets the reader act on the mail. Staff get the project
    page. An external account has no password, so it gets a fresh one-time
    sign-in link that lands on the project — the same bearer-by-email model
    the invitation uses, with the same 30-minute life and single use."""
    from security import issue_login_link
    target = url_for("project_detail", project_id=project_id)
    if user["kind"] == "external":
        href = url_for("auth_link_consume", token=issue_login_link(user["id"]), next=target, _external=True)
        return (f'<p><a href="{href}">Open the project in Odin</a> — this sign-in link works once and '
                f"expires in 30 minutes; after that, request a new one from the sign-in page.</p>")
    return f'<p><a href="{url_for("project_detail", project_id=project_id, _external=True)}">Open the project in Odin</a></p>'


def notify_participants(project_id, subject, message_html, exclude_user_id=None):
    """Email every active participant who has an address — internal or
    external — except the person who caused the event. Same admin toggle as
    notify_event; best effort, never raises."""
    if get_setting("notify_email_enabled") != "1":
        return
    rows = get_db().execute(
        "SELECT u.id, u.email, u.kind FROM project_participants pp JOIN users u ON u.id = pp.user_id "
        "WHERE pp.project_id = ? AND u.active = 1 AND u.email IS NOT NULL AND u.email != ''", (project_id,)
    ).fetchall()
    for r in rows:
        if r["id"] == exclude_user_id:
            continue
        try:
            ok, error = graph.send_mail(r["email"], subject, message_html + project_link(project_id, r))
        except Exception as exc:   # never let mail break the request that caused it
            ok, error = False, str(exc)
        if not ok:
            print(f"[notify_participants] email to {r['email']} failed: {error}")


def notify_event(project, subject, message_html, channels=None):
    """Best-effort Outlook + Teams notification for a project event.

    Never raises and never blocks the caller — a Graph/network failure just
    gets printed to the server console. Respects the admin on/off toggles in
    Settings > Integrations independently of whether Graph is configured.

    `channels` optionally narrows which of email/teams to attempt (both
    default True) — used by alert delivery, where each alert type has its
    own email/Teams checkboxes layered on top of the global toggles.
    """
    channels = channels or {"email": True, "teams": True}

    if channels.get("email") and get_setting("notify_email_enabled") == "1":
        db = get_db()
        owner = db.execute(
            "SELECT id, email, kind FROM users WHERE id = ?", (project["owner_id"],)
        ).fetchone()
        if owner and owner["email"]:
            # alert digests and creation pass a bare {"owner_id"}; only a real
            # project row has an id to link to
            link = project_link(project["id"], owner) if "id" in project.keys() else ""
            ok, error = graph.send_mail(owner["email"], subject, message_html + link)
            if not ok:
                print(f"[notify_event] email failed: {error}")

    if channels.get("teams") and get_setting("notify_teams_enabled") == "1":
        ok, error = graph.send_teams_message(f"<b>{subject}</b><br>{message_html}")
        if not ok:
            print(f"[notify_event] teams failed: {error}")
