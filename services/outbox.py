"""Mail and Teams messages, sent by the scheduler instead of the web request
(review advice A2).

notify_users and notify_event write the bell at once and queue the mail and
Teams messages here; the scheduler's outbox worker (a thread beside its
clock, never a web worker) sends what is due. A failure is tried again after
1, 2, 4, 8 … minutes and given up after policy outbox_attempts tries, or
once it is older than policy outbox_max_age_hours; then the admins hear of
it in the bell, once a day (kind "ops"). Sent rows and old given-up rows go
nightly (housekeeping).

An external account's mail holds no sign-in token: only who and which page
(services/notifications.queue_mail); the link is minted as the row is sent.
Sign-in links asked for at the sign-in page, invitations and the signed
sign-off PDF never come here: they are sent inline by their request.
"""
import json
from datetime import datetime, timedelta

from db import get_db

# Which rows go first (the payload's "priority"; absent is NORMAL): a stage move or an approval
# or sign-off request before the bulk of digests, daily summaries and the weekly report.
URGENT, NORMAL, BULK = 0, 1, 2


def pack(files):
    """Attachments [(name, bytes, content type)] as the queue keeps them (JSON: base64)."""
    import base64
    return [[name, base64.b64encode(data).decode(), ctype] for name, data, ctype in files]


def add(kind, priority=NORMAL, **payload):
    """Queue one message: kind "mail" (to, subject, html, optionally
    attachments from pack()) or "teams" (to = an
    address for the person's chat, "channel" or "webhook"). Kind "held" is an
    item kept for the daily summary (services/notifications.send_summaries):
    never due, so the worker never sends it. `priority`: URGENT, NORMAL or BULK."""
    if priority != NORMAL:
        payload["priority"] = priority
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute("INSERT INTO outbox (kind, payload, next_try_at, created_at) VALUES (?, ?, ?, ?)",
               (kind, json.dumps(payload), None if kind == "held" else now, now))
    db.commit()


def _send(kind, p):
    import graph
    if kind == "mail":
        html = p["html"]
        if "signin" in p:   # an external account's one-time link, minted now: never stored in the queue (FX1)
            from flask import current_app
            from services.notifications import odin_link
            intent = p["signin"]
            user = get_db().execute("SELECT id, kind FROM users WHERE id = ? AND active = 1", (intent["user_id"],)).fetchone()
            if user is None:   # removed or deactivated meanwhile: nothing to send
                return True, None
            with current_app.test_request_context():   # links are built from Settings › General, never a request
                html += odin_link(user, intent["path"], intent["label"])
        import base64
        files = [(name, base64.b64decode(data), ctype) for name, data, ctype in p.get("attachments", [])]
        return graph.send_mail(p["to"], p["subject"], html, report=False, **({"attachments": files} if files else {}))   # the admins hear when given up
    if p["to"] == "channel":
        return graph.send_teams_message(p["html"])
    if p["to"] == "webhook":   # the address is a sealed secret: read at send time, never queued
        from policies import policy
        url = policy("teams_webhook_url")
        return graph.post_teams_webhook(url, p["title"], p["lines"], p.get("link")) if url else (True, None)
    from services import teams_bot
    return teams_bot.send(p["to"], p["title"], p["text"], p.get("link"))


def drain(db=None, limit=50, stop=None):
    """Send what is due, urgent first, then oldest first, until `stop()` says
    so (checked before each row: the scheduler's time budget and SIGTERM).
    Returns how many rows it took."""
    from policies import policy
    from services.notifications import report_mail_failure
    db = db or get_db()
    now = datetime.utcnow()
    rows = db.execute("SELECT * FROM outbox WHERE sent_at IS NULL AND kind != 'held' AND next_try_at <= ? "
                      "ORDER BY COALESCE(json_extract(payload, '$.priority'), ?), id LIMIT ?", (now.isoformat(), NORMAL, limit)).fetchall()
    taken = 0
    for r in rows:
        if stop and stop():
            break
        taken += 1
        # claim it first: a second drain (a cron --once beside the service) leaves it alone,
        # and a crash mid-send tries it again ten minutes later
        claimed = db.execute("UPDATE outbox SET next_try_at = ? WHERE id = ? AND next_try_at = ?",
                             ((now + timedelta(minutes=10)).isoformat(), r["id"], r["next_try_at"])).rowcount
        db.commit()
        if not claimed:
            continue
        if r["created_at"] < (now - timedelta(hours=policy("outbox_max_age_hours", db))).isoformat():
            # too late to be worth sending (a sign-in link a day on, an event long past): given up, the admins told
            db.execute("UPDATE outbox SET next_try_at = NULL, last_error = ? WHERE id = ?", ("too old to send", r["id"]))
            db.commit()
            report_mail_failure(f"a message queued at {r['created_at'][:16]} was too old to send", "teams" if r["kind"] == "teams" else "mail")
            continue
        try:
            ok, error = _send(r["kind"], json.loads(r["payload"]))
        except Exception as exc:  # noqa: BLE001 — one bad row must not stop the rest
            ok, error = False, str(exc)
        tries = r["attempts"] + 1
        if ok:
            db.execute("UPDATE outbox SET attempts = ?, sent_at = ?, last_error = NULL WHERE id = ?",
                       (tries, datetime.utcnow().isoformat(), r["id"]))
        elif tries >= policy("outbox_attempts", db):
            db.execute("UPDATE outbox SET attempts = ?, next_try_at = NULL, last_error = ? WHERE id = ?",
                       (tries, str(error)[:500], r["id"]))
            db.commit()
            report_mail_failure(f"{error} (after {tries} tries)", "teams" if r["kind"] == "teams" else "mail")
        else:
            db.execute("UPDATE outbox SET attempts = ?, next_try_at = ?, last_error = ? WHERE id = ?",
                       (tries, (datetime.utcnow() + timedelta(minutes=2 ** (tries - 1))).isoformat(), str(error)[:500], r["id"]))
        db.commit()
    return taken


def trim(db=None):
    """Sent rows, and rows given up on longer ago than read notifications are
    kept (Settings › Retention). Nightly (scheduler housekeeping)."""
    from policies import policy
    db = db or get_db()
    cutoff = (datetime.utcnow() - timedelta(days=policy("notifications_keep_days", db))).isoformat()
    db.execute("DELETE FROM outbox WHERE sent_at IS NOT NULL OR (next_try_at IS NULL AND created_at < ?)", (cutoff,))
    db.commit()
