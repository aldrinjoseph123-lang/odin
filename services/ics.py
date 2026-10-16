"""A person's calendar feed (review B13), for Outlook and any calendar app.

Staff only: their own open tasks with a due date, and the target dates and
milestones of the open rollouts they are on or manage, as all-day events.
Partner and customer accounts get no feed (their view is cut per rollout and
per ask; a bearer URL forwarded once would leak it for good).

The feed's address carries a token (routes/feeds.py); only its SHA-256 sits
on the user row (users.ics_token_hash), so the address is shown once, when
it is made or rotated. Turning it off clears the hash.
"""
import secrets
from datetime import date, datetime, timedelta

from db import PROJECT_OPEN_SQL, get_db
from security import token_hash


def mint(user_id):
    """A new feed token for this person (replacing any old one); the raw token, to show once. No commit."""
    raw = secrets.token_urlsafe(32)
    get_db().execute("UPDATE users SET ics_token_hash = ?, ics_created_at = ? WHERE id = ?",
                     (token_hash(raw), datetime.utcnow().isoformat(), user_id))
    return raw


def revoke(user_id):
    get_db().execute("UPDATE users SET ics_token_hash = NULL, ics_created_at = NULL WHERE id = ?", (user_id,))


def owner_of(raw):
    """The active staff account this token belongs to, or None."""
    if not raw or len(raw) > 100:
        return None
    return get_db().execute("SELECT id, name FROM users WHERE ics_token_hash = ? AND active = 1 AND kind = 'internal'",
                            (token_hash(raw),)).fetchone()


def _text(value):
    """RFC 5545 TEXT: backslash, semicolon, comma and line breaks escaped."""
    return (value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line):
    """Lines longer than 75 octets continue on the next line after a space."""
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts, cut = [], 75
    while raw:
        while cut < len(raw) and (raw[cut] & 0xC0) == 0x80:   # never split a UTF-8 character
            cut -= 1
        piece = raw[:cut]
        parts.append(piece.decode())
        raw, cut = raw[len(piece):], 74
    return "\r\n ".join(parts)


def _event(uid, day, summary, description, url, stamp):
    try:
        d = date.fromisoformat((day or "")[:10])
    except ValueError:   # a date that never parsed is left out, not a broken feed
        return []
    return ["BEGIN:VEVENT", f"UID:{uid}@odin", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
            f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}", f"SUMMARY:{_text(summary)}",
            f"DESCRIPTION:{_text(description)}", f"URL:{url}", "TRANSP:TRANSPARENT", "END:VEVENT"]


def build(user_id, base):
    """The feed as text/calendar. `base` is the public address for the links."""
    db = get_db()
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    live = f"p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Protect24x7//Odin//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:Odin", "X-PUBLISHED-TTL:PT1H"]
    for t in db.execute(f"SELECT t.id, t.title, t.due_date, p.id AS pid, p.name FROM tasks t JOIN projects p ON p.id = t.project_id "
                        f"WHERE t.assignee_id = ? AND t.done = 0 AND t.due_date IS NOT NULL AND {live}", (user_id,)):
        lines += _event(f"task-{t['id']}", t["due_date"], f"{t['title']} ({t['name']})", f"Task due on {t['name']}", f"{base}/projects/{t['pid']}", stamp)
    mine = f"(p.owner_id = ? OR p.id IN (SELECT project_id FROM project_participants WHERE user_id = ?)) AND {live}"
    for p in db.execute(f"SELECT p.id, p.name, p.client, p.target_end_date FROM projects p WHERE p.target_end_date IS NOT NULL AND {mine}", (user_id, user_id)):
        lines += _event(f"target-{p['id']}", p["target_end_date"], f"Target: {p['name']}", f"{p['name']} for {p['client']} is due to finish", f"{base}/projects/{p['id']}", stamp)
    for m in db.execute(f"SELECT m.id, m.name, m.date, p.id AS pid, p.name AS project FROM milestones m JOIN projects p ON p.id = m.project_id "
                        f"WHERE m.done_at IS NULL AND {mine}", (user_id, user_id)):
        lines += _event(f"milestone-{m['id']}", m["date"], f"{m['name']} ({m['project']})", f"Milestone on {m['project']}", f"{base}/projects/{m['pid']}", stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
