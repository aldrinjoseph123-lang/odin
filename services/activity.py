"""Last seen and active time (People, Person, Account).

The browser pings once a minute while Odin is open, visible and was used
within the idle limit (policy activity_idle_minutes; POST /api/activity). Each accepted
ping is one active minute on the person's workspace-local day; pings closer
than 50 seconds apart are not counted, so a second tab or a fast client
cannot inflate the figure. Idle time with a tab left open is never counted.
Rows older than activity_keep_days (Settings → Retention) are trimmed nightly. An admin can
switch the whole thing off (activity_tracking) and choose which roles see
other people's figures (activity_roles).
"""
from datetime import datetime, timedelta

from db import get_db
from policies import local_today, policy

MIN_GAP_SECONDS = 50


def enabled():
    return policy("activity_tracking")


def ping(user_id):
    """Record one active minute unless one was recorded under 50 s ago (or tracking is off)."""
    if not enabled():
        return False
    db = get_db()
    now = datetime.utcnow()
    row = db.execute("SELECT last_ping_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if row and row["last_ping_at"]:
        try:
            if (now - datetime.fromisoformat(row["last_ping_at"])).total_seconds() < MIN_GAP_SECONDS:
                return False
        except ValueError:
            pass
    db.execute("UPDATE users SET last_seen_at = ?, last_ping_at = ? WHERE id = ?", (now.isoformat(), now.isoformat(), user_id))
    db.execute("INSERT INTO user_activity (user_id, day, minutes) VALUES (?, ?, 1) "
               "ON CONFLICT(user_id, day) DO UPDATE SET minutes = minutes + 1", (user_id, local_today().isoformat()))
    db.commit()
    return True


def summary(user_id, days=30):
    """Today, the last 7 and 30 days, and one row per day (oldest first)."""
    db = get_db()
    today = local_today()
    start = today - timedelta(days=days - 1)
    rows = dict(db.execute("SELECT day, minutes FROM user_activity WHERE user_id = ? AND day >= ?", (user_id, start.isoformat())).fetchall())
    series = [{"day": (start + timedelta(days=i)).isoformat(), "minutes": rows.get((start + timedelta(days=i)).isoformat(), 0)} for i in range(days)]
    total = lambda n: sum(x["minutes"] for x in series[-n:])   # noqa: E731
    u = db.execute("SELECT last_seen_at, last_login_at FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"today": total(1), "week": total(7), "month": total(30), "days": series,
            "last_seen_at": (u["last_seen_at"] or u["last_login_at"]) if u else None, "last_login_at": u["last_login_at"] if u else None}


def can_see_others(role):
    return enabled() and role in policy("activity_roles")


def trim(db=None):
    db = db or get_db()
    db.execute("DELETE FROM user_activity WHERE day < ?", ((local_today(db) - timedelta(days=policy("activity_keep_days", db))).isoformat(),))
    db.commit()
