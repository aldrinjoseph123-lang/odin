"""Outbound notifications: Outlook mail + Teams channel messages via Graph.

Best-effort — never raises, so a Graph outage can't break a project update.
Depends on db (for the admin on/off toggles and the owner's email) and graph.
"""
from flask import url_for

import graph
from db import get_db, get_setting


def project_link(project_id, user, target=None):
    """The line that lets the reader act on the mail. Staff get the project
    page. An external account has no password, so it gets a fresh one-time
    sign-in link that lands on the project — the same bearer-by-email model
    the invitation uses, with the same life (policy link_minutes) and single use."""
    from core import external_url
    from policies import policy
    from security import issue_login_link
    page = target or url_for("project_detail", project_id=project_id)
    if user["kind"] == "external":
        href = external_url("auth_link_consume", token=issue_login_link(user["id"]), next=page)
        return (f'<p><a href="{href}">Open the rollout in Odin</a> — this sign-in link works once and '
                f"expires in {policy('link_minutes')} minutes; after that, request a new one from the sign-in page.</p>")
    href = external_url("project_detail", project_id=project_id)
    if target:
        href = href.rsplit(url_for("project_detail", project_id=project_id), 1)[0] + target
    return f'<p><a href="{href}">Open the rollout in Odin</a></p>'


def _plain(html):
    import re
    from html import unescape
    return unescape(re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " ", re.sub(r"<(?!br)[^>]+>", "", html or "")))).strip()


def notify_users(user_ids, kind, project_id, subject, message_html, exclude_user_id=None, link=None, email=True):
    """The one way a person hears about an event. Every recipient gets an
    in-app notification; those with an address who have not switched this
    kind off by email also get a mail (when mail is on). Recipients are
    de-duplicated and the person who caused the event is never told about
    their own action. `email=False` keeps it to the bell. Best effort: mail
    failures never break the request."""
    from datetime import datetime
    from flask import has_request_context, session
    ids = []
    for uid in user_ids:
        if uid and uid != exclude_user_id and uid not in ids:
            ids.append(uid)
    if not ids:
        return
    db = get_db()
    now = datetime.utcnow()
    actor = session.get("user_name") if has_request_context() else None   # the daily script has no session
    link = link or (f"/board?rollout={project_id}" if project_id else None)
    title, body = _plain(subject), _plain(message_html)
    marks = ",".join("?" for _ in ids)
    rows = db.execute(f"SELECT id, email, kind, email_off FROM users WHERE active = 1 AND id IN ({marks})", ids).fetchall()
    for r in rows:
        db.execute(
            "INSERT INTO notifications (user_id, project_id, kind, title, body, link, actor, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (r["id"], project_id, kind, title[:300], body[:2000], link, actor, now.isoformat()),
        )
    db.commit()
    if not email or get_setting("notify_email_enabled") != "1":
        return
    for r in rows:
        if not r["email"] or kind in (r["email_off"] or "").split(","):
            continue
        try:
            extra = project_link(project_id, r, link if link and link.startswith("/projects/") else None) if project_id else ""
            ok, error = graph.send_mail(r["email"], subject, message_html + extra)
        except Exception as exc:   # never let mail break the request that caused it
            ok, error = False, str(exc)
        if not ok:
            print(f"[notify_users] email to {r['email']} failed: {error}")


def report_mail_failure(error):
    """Email is switched on but a message failed: tell the admins in the bell,
    at most once a day, instead of failing silently (system map #2)."""
    from datetime import datetime, timedelta
    from markupsafe import escape
    from db import set_setting
    if get_setting("notify_email_enabled") != "1":
        return
    last, now = get_setting("mail_failure_reported_at"), datetime.utcnow()
    if last and datetime.fromisoformat(last) > now - timedelta(hours=24):
        return
    set_setting("mail_failure_reported_at", now.isoformat())
    admins = [r[0] for r in get_db().execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
    notify_users(admins, "access", None, "Odin could not send email",
                 f"Email is switched on but a message failed ({escape(str(error)[:200])}). Everything still reaches the bell. "
                 "Connect Microsoft 365 under Settings › Integrations, or switch email off under Settings › Notifications.",
                 link="/settings/integrations", email=False)


def trim(db=None):
    """Read notifications past Settings › Retention; unread ones stay. Nightly (scheduler housekeeping)."""
    from datetime import datetime, timedelta
    from policies import policy
    db = db or get_db()
    db.execute("DELETE FROM notifications WHERE read_at IS NOT NULL AND created_at < ?",
               ((datetime.utcnow() - timedelta(days=policy("notifications_keep_days", db))).isoformat(),))
    db.commit()


def visible_clause(user_id, kind):
    """SQL (on alias n) keeping a bell to what the person may see now: a
    partner removed from a project stops seeing its notifications, and
    nobody sees those of a deleted project."""
    # a deleted project's notifications go quiet with it (its page is gone, sim L-16)
    live = " AND (n.project_id IS NULL OR n.project_id IN (SELECT id FROM projects WHERE deleted_at IS NULL))"
    if kind == "external":
        return live + " AND (n.project_id IS NULL OR n.project_id IN (SELECT project_id FROM project_participants WHERE user_id = ?))", (user_id,)
    return live, ()


def notify_participants(project_id, subject, message_html, exclude_user_id=None, kind="stage"):
    """Everyone on the project (the project manager is always a participant)."""
    ids = [r[0] for r in get_db().execute("SELECT user_id FROM project_participants WHERE project_id = ?", (project_id,))]
    notify_users(ids, kind, project_id, subject, message_html, exclude_user_id=exclude_user_id)


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
        from flask import has_request_context, session
        acting = session.get("user_id") if has_request_context() else None
        if owner and owner["email"] and owner["id"] != acting:   # never mail someone about their own action
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
        # the same event to a Teams Workflows webhook, when one is set (Settings › Notifications)
        from policies import policy
        if policy("teams_webhook_url"):
            from core import external_url
            link = external_url("project_detail", project_id=project["id"]) if "id" in project.keys() else None
            ok, error = graph.post_teams_webhook(policy("teams_webhook_url"), _plain(subject), [_plain(message_html)], link)
            if not ok:
                print(f"[notify_event] webhook failed: {error}")
