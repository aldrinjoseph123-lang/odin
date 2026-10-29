"""Outbound notifications: the bell at once; Outlook mail, Teams chat cards
and Teams channel posts queued in the outbox (services/outbox.py), which
the scheduler sends with retries.

Best-effort — never raises, so a Graph outage can't break a project update.
Depends on db (for the admin on/off toggles and the owner's email) and graph.
"""
from flask import url_for

from db import get_db, get_setting
from policies import policy
from services import outbox
from services.fmt import plural


def odin_link(user, path, label="Open in Odin"):
    """The line that lets the reader act on the mail. Staff get the page. An
    external account has no password, so it gets a fresh one-time sign-in
    link that lands on the page — the same bearer-by-email model the
    invitation uses, with the same life (policy link_minutes) and single use.
    Needs a request context (the outbox mints it in one, at send time)."""
    from core import external_url, public_base
    from policies import policy
    from security import issue_login_link
    if user["kind"] == "external":
        href = external_url("auth_link_consume", token=issue_login_link(user["id"]), next=path)
        return (f'<p><a href="{href}">{label}</a> — this sign-in link works once and '
                f"expires in {policy('link_minutes')} minutes; after that, request a new one from the sign-in page.</p>")
    return f'<p><a href="{public_base()}{path}">{label}</a></p>'


URGENT_KINDS = ("stage", "approval")   # a stage move, a customer approval or sign-off request: out before the digests
BULK_KINDS = ("due", "brief")          # the morning's reminders and briefs: after everything else


def priority_of(kind):
    return outbox.URGENT if kind in URGENT_KINDS else outbox.BULK if kind in BULK_KINDS else outbox.NORMAL


def queue_mail(user, subject, html, path=None, label="Open in Odin", priority=outbox.NORMAL):
    """Queue one mail with its line into Odin. An external account's sign-in
    link is only an intent here (who, which page): the outbox mints it when it
    sends, so no live token ever sits in the outbox table or a backup of it."""
    if path and user["kind"] == "external":
        outbox.add("mail", priority, to=user["email"], subject=subject, html=html, signin={"user_id": user["id"], "path": path, "label": label})
    else:
        outbox.add("mail", priority, to=user["email"], subject=subject, html=html + (odin_link(user, path, label) if path else ""))


def _rollout_path(project_id, target=None):
    return target or url_for("project_detail", project_id=project_id)


def _plain(html):
    """Text from a message's HTML: a paragraph, a list item and a line break end a line."""
    import re
    from html import unescape
    text = unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>|</(?:p|li)\s*>", "\n", html or "", flags=re.I)))
    return re.sub(r"\s*\n\s*", "\n", re.sub(r"[^\S\n]+", " ", text)).strip()


def delivery(user, kind):
    """How this person takes `kind` by email and Teams (Account page): "instant",
    "summary" (held for the daily summary) or "off"."""
    if kind in (user["email_off"] or "").split(","):
        return "off"
    return "summary" if kind in (user["email_summary"] or "").split(",") else "instant"


def watch_of(project_id, mode):
    """Who has muted (or follows) this rollout."""
    return {r[0] for r in get_db().execute("SELECT user_id FROM rollout_watch WHERE project_id = ? AND mode = ?", (project_id, mode))}


def watch_state(project_id, user_id, kind):
    """Mute or follow (B3): a participant may mute the rollout, staff not on it
    may follow it. `can` is which one this person has, `on` whether it is set."""
    db = get_db()
    on_it = db.execute("SELECT 1 FROM project_participants WHERE project_id = ? AND user_id = ?", (project_id, user_id)).fetchone()
    can = "mute" if on_it else "follow" if kind == "internal" else None
    row = db.execute("SELECT mode FROM rollout_watch WHERE project_id = ? AND user_id = ?", (project_id, user_id)).fetchone()
    return {"can": can, "on": bool(can and row and row["mode"] == can)}


def set_watch(project_id, user_id, mode, on):
    """Mute or follow (mode) the rollout, or stop (on False). No commit."""
    db = get_db()
    db.execute("DELETE FROM rollout_watch WHERE project_id = ? AND user_id = ?", (project_id, user_id))
    if on:
        from datetime import datetime
        db.execute("INSERT INTO rollout_watch (user_id, project_id, mode, created_at) VALUES (?, ?, ?, ?)",
                   (user_id, project_id, mode, datetime.utcnow().isoformat()))


def next_step(user, project_id):
    """The reader's own next step on this rollout (B18): their open tasks
    there, the three soonest. A partner or customer reads them as what we need
    from them (their asks, services/asks.py, are tasks assigned to them)."""
    from markupsafe import escape
    rows = get_db().execute("SELECT title, due_date FROM tasks WHERE project_id = ? AND assignee_id = ? AND done = 0 "
                            "ORDER BY due_date IS NULL, due_date, id LIMIT 4", (project_id, user["id"])).fetchall()
    if not rows:
        return ""
    items = "".join(f"<li>{escape(r['title'])}{' (due ' + r['due_date'] + ')' if r['due_date'] else ''}</li>" for r in rows[:3])
    more = "<li>and more on the rollout page</li>" if len(rows) > 3 else ""
    head = "What we need from you" if user["kind"] == "external" else "Your next step on this rollout"
    return f"<p><b>{head}</b></p><ul>{items}{more}</ul>"


def notify_users(user_ids, kind, project_id, subject, message_html, exclude_user_id=None, link=None, email=True, teams=True):
    """The one way a person hears about an event. Every recipient gets an
    in-app notification; those with an address who take this kind (Account
    page: at once, in the daily summary, or off) also get a mail (when mail is
    on) and, staff only, a card in their own chat with the Odin PMS Teams app
    (when Teams messages are on: every notification, mailed or not, as
    Settings says; partners and customers sit in other tenants). A rollout's
    events also reach the staff who follow it (FOLLOW_KINDS); someone who
    muted the rollout still sees it in the bell, marked muted, and gets no
    mail or Teams from it. Recipients are de-duplicated and the person who
    caused the event is never told about their own action. `email=False`
    keeps it off mail, `teams=False` off Teams. Mail and Teams go through the
    outbox: the request never waits on Microsoft."""
    from datetime import datetime
    from flask import has_request_context, session
    from constants import FOLLOW_KINDS
    if project_id and kind in FOLLOW_KINDS:
        # followers are staff only (the follow route refuses anyone else)
        user_ids = [*user_ids, *(r[0] for r in get_db().execute(
            "SELECT w.user_id FROM rollout_watch w JOIN users u ON u.id = w.user_id WHERE w.project_id = ? AND w.mode = 'follow' AND u.kind = 'internal' ORDER BY w.user_id",
            (project_id,)))]
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
    rows = db.execute(f"SELECT id, email, kind, email_off, email_summary FROM users WHERE active = 1 AND id IN ({marks})", ids).fetchall()
    muted = watch_of(project_id, "mute") if project_id else set()
    for r in rows:
        db.execute(
            "INSERT INTO notifications (user_id, project_id, kind, title, body, link, actor, created_at, muted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r["id"], project_id, kind, title[:300], body[:2000], link, actor, now.isoformat(), int(r["id"] in muted)),
        )
    db.commit()
    # the per-kind choices on the Account page ("Tell me about") cover email and Teams alike
    wanted = [r for r in rows if r["email"] and r["id"] not in muted and delivery(r, kind) != "off"]
    held = [r for r in wanted if delivery(r, kind) == "summary"]
    held_ids = {r["id"] for r in held}
    if held and ((email and policy("notify_email_enabled")) or (teams and policy("notify_teams_chat_enabled"))):
        project = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone() if project_id else None
        for r in held:   # the outbox keeps it for the daily summary (send_summaries, at the digest time)
            outbox.add("held", user_id=r["id"], project_id=project_id, project=project["name"] if project else None,
                       title=title, text=body[:600], mail=email, teams=teams)
    wanted = [r for r in wanted if r["id"] not in held_ids]
    for r in wanted if email and policy("notify_email_enabled") else []:
        # every mail links into Odin: the rollout, or the page the bell links to (P2-21); and says what is the reader's to do (B18)
        if project_id:
            queue_mail(r, title, message_html + next_step(r, project_id), _rollout_path(project_id, link if link and link.startswith("/projects/") else None),
                       "Open the rollout in Odin", priority_of(kind))
        else:
            queue_mail(r, title, message_html, link, priority=priority_of(kind))
    for r in [r for r in wanted if r["kind"] != "external"] if teams and policy("notify_teams_chat_enabled") else []:
        outbox.add("teams", priority_of(kind), to=r["email"], title=title, text=body, link=_odin_url(project_id, link))


def send_summaries(db=None):
    """The daily summary (B2): what the outbox held for each person, one mail
    grouped by rollout (with their next step on each) and, for staff with Teams
    messages on, one card. Run by the scheduler's digest job; returns how many
    people it summarised. Needs a request context (links)."""
    import json
    from datetime import datetime
    from markupsafe import escape
    from core import public_base
    db = db or get_db()
    held = db.execute("SELECT id, payload FROM outbox WHERE kind = 'held' AND sent_at IS NULL ORDER BY id").fetchall()
    per = {}
    for h in held:
        p = json.loads(h["payload"])
        per.setdefault(p["user_id"], []).append({**p, "row": h["id"]})
    now = datetime.utcnow().isoformat()
    done = 0
    for uid, items in per.items():
        user = db.execute("SELECT id, email, kind, active FROM users WHERE id = ?", (uid,)).fetchone()
        if user and user["active"] and user["email"]:
            groups = {}
            for it in items:
                groups.setdefault((it["project_id"], it["project"]), []).append(it)
            parts = []
            for (pid, name), group in groups.items():
                head = escape(name) if name else "Elsewhere in Odin"
                if pid and user["kind"] != "external":
                    head = f'<a href="{public_base()}/projects/{pid}">{head}</a>'
                lines = "".join(f"<li><b>{escape(it['title'])}</b>{' — ' + escape(it['text']) if it['text'] else ''}</li>" for it in group)
                parts.append(f"<h3>{head}</h3><ul>{lines}</ul>" + (next_step(user, pid) if pid else ""))
            n = len(items)
            subject = f"Odin daily summary: {n} {plural(n, 'update')} on {len(groups)} {plural(len(groups), 'rollout')}"
            if policy("notify_email_enabled", db) and any(it.get("mail", True) for it in items):
                queue_mail(user, subject, "".join(parts), "/board" if user["kind"] == "external" else "/dashboard", "Open Odin", outbox.BULK)
            if user["kind"] != "external" and policy("notify_teams_chat_enabled", db) and any(it.get("teams", True) for it in items):
                outbox.add("teams", outbox.BULK, to=user["email"], title=subject, text="; ".join(sorted({it["project"] or "Odin" for it in items})), link=f"{public_base()}/dashboard")
            done += 1
        # taken, whether sent or not (a person gone or without an address meanwhile): never summarised twice
        db.execute(f"UPDATE outbox SET sent_at = ? WHERE id IN ({','.join('?' * len(items))})", (now, *[it["row"] for it in items]))
    db.commit()
    return done


def _odin_url(project_id, link):
    """The address behind a Teams card's "Open in Odin" (staff: no sign-in link needed)."""
    from core import public_base
    path = link or (url_for("project_detail", project_id=project_id) if project_id else None)
    return f"{public_base()}{path}" if path else None


def admin_ids(db=None):
    """The active Admins' user ids: who hears of a failure."""
    return [r[0] for r in (db or get_db()).execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]


# what report_mail_failure can say, each its own daily notice (so one never hides another):
# kind -> (setting that holds the last time, title, words, link, how much of the error to quote)
_FAILURES = {
    "mail": ("mail_failure_reported_at", "Odin could not send email",
             "Email is switched on but a message failed ({}). Everything still reaches the bell. "
             "Connect Microsoft 365 under Settings › Integrations, or switch email off under Settings › Notifications.", "/settings/integrations", 300),
    "alias": ("mail_alias_reported_at", "Odin's email went out from the mailbox, not its alias",
              "Microsoft refused the address under Settings › Notifications › Send email as ({}). "
              "Mail still goes out, from the connected mailbox's own address. Allow sending from aliases in Exchange "
              "(Set-OrganizationConfig -SendFromAliasEnabled $true) or clear the setting.", "/settings/notifications", 200),
    "teams": ("teams_failure_reported_at", "Odin could not send a Teams message",
              "A Teams message failed ({}). Everything still reaches the bell and email. "
              "Check that the Odin PMS app is installed in Teams for everyone and Microsoft 365 is connected "
              "(Settings › Integrations; if it was connected before 13 Oct 2026, Disconnect and Connect again so Odin may look people up), "
              "or switch Teams messages off under Settings › Notifications.", "/settings/integrations", 300),
    "resend": ("resend_failure_reported_at", "Odin could not send a sign-in email through Resend",
               "{}. Check the key and the sending domain in Resend, and Settings › Notifications › Sign-in mail.", "/settings/notifications", None),
}


def report_mail_failure(error, kind="mail"):
    """A message failed (sent directly, or given up on by the outbox): tell
    the admins in the bell, at most once a day, instead of failing silently
    (system map #2). `kind`: mail (Microsoft refused or could not send), alias
    (the mail went out, but from the mailbox, because Microsoft refused the
    "Send email as" alias), teams (a Teams message failed) or resend (a
    sign-in email through Resend failed); each its own daily notice.
    Bell only: a notice about failing mail or Teams must not queue more."""
    from datetime import datetime, timedelta
    from markupsafe import escape
    from db import set_setting
    if kind in ("mail", "alias") and not policy("notify_email_enabled"):
        return
    key, title, words, link, cap = _FAILURES[kind]
    last, now = get_setting(key), datetime.utcnow()
    if last and datetime.fromisoformat(last) > now - timedelta(hours=24):
        return
    set_setting(key, now.isoformat())
    notify_users(admin_ids(), "ops", None, title, words.format(escape(str(error)[:cap])), link=link, email=False, teams=False)


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

    if channels.get("email") and policy("notify_email_enabled"):
        owner = get_db().execute("SELECT id, email, kind FROM users WHERE id = ?", (project["owner_id"],)).fetchone()
        from flask import has_request_context, session
        acting = session.get("user_id") if has_request_context() else None
        muted = has_id and owner is not None and owner["id"] in watch_of(project["id"], "mute")   # B3: the bell only
        if owner and owner["email"] and owner["id"] != acting and not muted:   # never mail someone about their own action
            queue_mail(owner, _plain(subject), message_html, _rollout_path(project["id"]) if has_id else None, "Open the rollout in Odin")

    if channels.get("teams") and policy("notify_teams_enabled"):
        href = external_url("project_detail", project_id=project["id"]) if has_id else None
        outbox.add("teams", to="channel", html=f"<b>{subject}</b><br>{message_html}" + (f'<br><a href="{href}">Open in Odin</a>' if href else ""))
        # the same event to a Teams Workflows webhook, when one is set (Settings › Notifications)
        if policy("teams_webhook_url"):
            outbox.add("teams", to="webhook", title=_plain(subject), lines=[_plain(message_html)], link=href)
