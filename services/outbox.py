"""Mail and Teams messages, sent by the scheduler instead of the web request
(review advice A2).

notify_users and notify_event write the bell at once and queue the mail and
Teams messages here; the scheduler's outbox worker (a thread beside its
clock, never a web worker) sends what is due. A failure is tried again after
1, 2, 4, 8 … minutes and given up after policy outbox_attempts tries; then
the admins hear of it in the bell, once a day (kind "ops"). Sent rows and
old given-up rows go nightly (housekeeping).
"""
import json
from datetime import datetime, timedelta

from db import get_db


def add(kind, **payload):
    """Queue one message: kind "mail" (to, subject, html) or "teams" (to = an
    address for the person's chat, "channel" or "webhook")."""
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute("INSERT INTO outbox (kind, payload, next_try_at, created_at) VALUES (?, ?, ?, ?)",
               (kind, json.dumps(payload), now, now))
    db.commit()


def _send(kind, p):
    import graph
    if kind == "mail":
        return graph.send_mail(p["to"], p["subject"], p["html"], report=False)   # the admins hear when it is given up
    if p["to"] == "channel":
        return graph.send_teams_message(p["html"])
    if p["to"] == "webhook":   # the address is a sealed secret: read at send time, never queued
        from policies import policy
        url = policy("teams_webhook_url")
        return graph.post_teams_webhook(url, p["title"], p["lines"], p.get("link")) if url else (True, None)
    from services import teams_bot
    return teams_bot.send(p["to"], p["title"], p["text"], p.get("link"))


def drain(db=None, limit=50):
    """Send what is due, oldest first. Returns how many rows it took."""
    from policies import policy
    from services.notifications import report_mail_failure
    db = db or get_db()
    now = datetime.utcnow()
    rows = db.execute("SELECT * FROM outbox WHERE sent_at IS NULL AND next_try_at <= ? ORDER BY id LIMIT ?",
                      (now.isoformat(), limit)).fetchall()
    for r in rows:
        # claim it first: a second drain (a cron --once beside the service) leaves it alone,
        # and a crash mid-send tries it again ten minutes later
        claimed = db.execute("UPDATE outbox SET next_try_at = ? WHERE id = ? AND next_try_at = ?",
                             ((now + timedelta(minutes=10)).isoformat(), r["id"], r["next_try_at"])).rowcount
        db.commit()
        if not claimed:
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
            report_mail_failure(f"{error} (after {tries} tries)", teams=r["kind"] == "teams")
        else:
            db.execute("UPDATE outbox SET attempts = ?, next_try_at = ?, last_error = ? WHERE id = ?",
                       (tries, (datetime.utcnow() + timedelta(minutes=2 ** (tries - 1))).isoformat(), str(error)[:500], r["id"]))
        db.commit()
    return len(rows)


def trim(db=None):
    """Sent rows, and rows given up on longer ago than read notifications are
    kept (Settings › Retention). Nightly (scheduler housekeeping)."""
    from policies import policy
    db = db or get_db()
    cutoff = (datetime.utcnow() - timedelta(days=policy("notifications_keep_days", db))).isoformat()
    db.execute("DELETE FROM outbox WHERE sent_at IS NOT NULL OR (next_try_at IS NULL AND created_at < ?)", (cutoff,))
    db.commit()
