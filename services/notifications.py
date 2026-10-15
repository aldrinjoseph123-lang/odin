"""Outbound notifications: the bell at once; Outlook mail, Teams chat cards
and Teams channel posts queued in the outbox (services/outbox.py), which
the scheduler sends with retries.

Best-effort — never raises, so a Graph outage can't break a project update.
Depends on db (for the admin on/off toggles and the owner's email) and graph.
"""
from flask import url_for

from db import get_db, get_setting
from services import outbox


def odin_link(user, path):
    """The line that lets the reader act on the mail. Staff get the page. An
    external account has no password, so it gets a fresh one-time sign-in
    link that lands on the page — the same bearer-by-email model the
    invitation uses, with the same life (policy link_minutes) and single use."""
    from core import external_url, public_base
    from policies import policy
    from security import issue_login_link
    if user["kind"] == "external":
        href = external_url("auth_link_consume", token=issue_login_link(user["id"]), next=path)
        return (f'<p><a href="{href}">Open in Odin</a> — this sign-in link works once and '
                f"expires in {policy('link_minutes')} minutes; after that, request a new one from the sign-in page.</p>")
    return f'<p><a href="{public_base()}{path}">Open in Odin</a></p>'


def project_link(project_id, user, target=None):
    """odin_link for a rollout: its page, or `target` on it."""
    return odin_link(user, target or url_for("project_detail", project_id=project_id)).replace("Open in Odin", "Open the rollout in Odin", 1)


def _plain(html):
    import re
    from html import unescape
    return unescape(re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " ", re.sub(r"<(?!br)[^>]+>", "", html or "")))).strip()


def notify_users(user_ids, kind, project_id, subject, message_html, exclude_user_id=None, link=None, email=True, teams=True):
    """The one way a person hears about an event. Every recipient gets an
    in-app notification; those with an address who have not switched this
    kind off also get a mail (when mail is on) and, staff only, a card in
    their own chat with the Odin PMS Teams app (when Teams messages are on:
    every notification, mailed or not, as Settings says; partners and
    customers sit in other tenants). Recipients are de-duplicated and the
    person who caused the event is never told about their own action.
    `email=False` keeps it off mail, `teams=False` off Teams. Mail and Teams
    go through the outbox: the request never waits on Microsoft."""
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
    # the per-kind choices on the Account page ("Tell me about") cover email and Teams alike
    wanted = [r for r in rows if r["email"] and kind not in (r["email_off"] or "").split(",")]
    for r in wanted if email and get_setting("notify_email_enabled") == "1" else []:
        # every mail links into Odin: the rollout, or the page the bell links to (P2-21)
        extra = (project_link(project_id, r, link if link and link.startswith("/projects/") else None) if project_id
                 else odin_link(r, link) if link else "")
        outbox.add("mail", to=r["email"], subject=title, html=message_html + extra)
    for r in [r for r in wanted if r["kind"] != "external"] if teams and get_setting("notify_teams_chat_enabled") == "1" else []:
        outbox.add("teams", to=r["email"], title=title, text=body, link=_odin_url(project_id, link))


def _odin_url(project_id, link):
    """The address behind a Teams card's "Open in Odin" (staff: no sign-in link needed)."""
    from core import public_base
    path = link or (url_for("project_detail", project_id=project_id) if project_id else None)
    return f"{public_base()}{path}" if path else None


def report_mail_failure(error, alias=False, teams=False):
    """A message failed (sent directly, or given up on by the outbox): tell
    the admins in the bell, at most once a day, instead of failing silently
    (system map #2). `alias`: the mail went out, but from the mailbox,
    because Microsoft refused the "Send email as" alias; `teams`: a Teams
    message failed (each its own daily notice, so one never hides another).
    Bell only: a notice about failing mail or Teams must not queue more."""
    from datetime import datetime, timedelta
    from markupsafe import escape
    from db import set_setting
    if not teams and get_setting("notify_email_enabled") != "1":
        return
    key = "teams_failure_reported_at" if teams else "mail_alias_reported_at" if alias else "mail_failure_reported_at"
    last, now = get_setting(key), datetime.utcnow()
    if last and datetime.fromisoformat(last) > now - timedelta(hours=24):
        return
    set_setting(key, now.isoformat())
    admins = [r[0] for r in get_db().execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
    if teams:
        notify_users(admins, "ops", None, "Odin could not send a Teams message",
                     f"A Teams message failed ({escape(str(error)[:300])}). Everything still reaches the bell and email. "
                     "Check that the Odin PMS app is installed in Teams for everyone and Microsoft 365 is connected "
                     "(Settings › Integrations; if it was connected before 13 Oct 2026, Disconnect and Connect again so Odin may look people up), "
                     "or switch Teams messages off under Settings › Notifications.", link="/settings/integrations", email=False, teams=False)
        return
    if alias:
        notify_users(admins, "ops", None, "Odin's email went out from the mailbox, not its alias",
                     f"Microsoft refused the address under Settings › Notifications › Send email as ({escape(str(error)[:200])}). "
                     "Mail still goes out, from the connected mailbox's own address. Allow sending from aliases in Exchange "
                     "(Set-OrganizationConfig -SendFromAliasEnabled $true) or clear the setting.",
                     link="/settings/notifications", email=False, teams=False)
        return
    notify_users(admins, "ops", None, "Odin could not send email",
                 f"Email is switched on but a message failed ({escape(str(error)[:300])}). Everything still reaches the bell. "
                 "Connect Microsoft 365 under Settings › Integrations, or switch email off under Settings › Notifications.",
                 link="/settings/integrations", email=False, teams=False)


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
    """Best-effort Outlook + Teams channel notification for a project event,
    queued in the outbox. Respects the admin on/off toggles in Settings ›
    Notifications independently of whether Graph is configured.

    `channels` optionally narrows which of email/teams to attempt (both
    default True) — used by alert delivery, where each alert type has its
    own email/Teams checkboxes layered on top of the global toggles.
    """
    from core import external_url
    from policies import policy
    channels = channels or {"email": True, "teams": True}
    # alert digests and creation pass a bare {"owner_id"}; only a real project row has an id to link to
    has_id = "id" in project.keys()

    if channels.get("email") and get_setting("notify_email_enabled") == "1":
        owner = get_db().execute("SELECT id, email, kind FROM users WHERE id = ?", (project["owner_id"],)).fetchone()
        from flask import has_request_context, session
        acting = session.get("user_id") if has_request_context() else None
        if owner and owner["email"] and owner["id"] != acting:   # never mail someone about their own action
            outbox.add("mail", to=owner["email"], subject=_plain(subject), html=message_html + (project_link(project["id"], owner) if has_id else ""))

    if channels.get("teams") and get_setting("notify_teams_enabled") == "1":
        href = external_url("project_detail", project_id=project["id"]) if has_id else None
        outbox.add("teams", to="channel", html=f"<b>{subject}</b><br>{message_html}" + (f'<br><a href="{href}">Open in Odin</a>' if href else ""))
        # the same event to a Teams Workflows webhook, when one is set (Settings › Notifications)
        if policy("teams_webhook_url"):
            outbox.add("teams", to="webhook", title=_plain(subject), lines=[_plain(message_html)], link=href)
