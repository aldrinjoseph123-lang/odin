"""Audit trail: record who did what, when, from where.

Reads the acting user from the Flask session and the caller IP from the
request when there is one (every route); the scheduler names itself as the
actor. Depends
only on db — nothing depends on it except route handlers.
"""
import re
from datetime import datetime

from flask import has_request_context, request, session

from db import get_db


DETAILS_MAX = 2000
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _clean(details):
    """The log is append-only: no caller writes unbounded text or control characters
    (line breaks, escapes) into it: each control character becomes a space."""
    if details is None:
        return None
    details = _CONTROL.sub(" ", str(details))
    return details if len(details) <= DETAILS_MAX else details[:DETAILS_MAX - 1] + "…"


def audit_log(action, resource_type=None, resource_id=None, resource_name=None, details=None, actor=None, db=None):
    """Log action to audit trail.

    `actor` overrides the session username for events that happen without a
    login — a failed sign-in attempt, a guest-link write, or the scheduler
    (which has no request: no user id, no address) — so the trail still
    names who (or which link) did it.
    """
    db = db or get_db()
    web = has_request_context()
    user_id = session.get("user_id") if web else None
    username = actor or (session.get("user_name", "unknown") if web else "unknown")
    ip_address = request.remote_addr if web else None
    timestamp = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO audit_logs (user_id, username, action, resource_type, resource_id, resource_name, details, timestamp, ip_address) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, action, resource_type, resource_id, resource_name, _clean(details), timestamp, ip_address),
    )
    db.commit()
