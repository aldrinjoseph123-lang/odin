"""Outbound notifications: Outlook mail + Teams channel messages via Graph.

Best-effort — never raises, so a Graph outage can't break a project update.
Depends on db (for the admin on/off toggles and the owner's email) and graph.
"""
import graph
from db import get_db, get_setting


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
            "SELECT email FROM users WHERE id = ?", (project["owner_id"],)
        ).fetchone()
        if owner and owner["email"]:
            ok, error = graph.send_mail(owner["email"], subject, message_html)
            if not ok:
                print(f"[notify_event] email failed: {error}")

    if channels.get("teams") and get_setting("notify_teams_enabled") == "1":
        ok, error = graph.send_teams_message(f"<b>{subject}</b><br>{message_html}")
        if not ok:
            print(f"[notify_event] teams failed: {error}")
