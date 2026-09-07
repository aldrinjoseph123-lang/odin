"""Audit trail: record who did what, when, from where.

Reads the acting user from the Flask session and the caller IP from the
request, so it must run inside a request context (every route does). Depends
only on db — nothing depends on it except route handlers.
"""
from datetime import datetime

from flask import request, session

from db import get_db


def audit_log(action, resource_type=None, resource_id=None, resource_name=None, details=None, actor=None):
    """Log action to audit trail.

    `actor` overrides the session username for events that happen without a
    login — a failed sign-in attempt, or a guest-link write — so the trail
    still names who (or which link) did it.
    """
    db = get_db()
    user_id = session.get("user_id")
    username = actor or session.get("user_name", "unknown")
    ip_address = request.remote_addr
    timestamp = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO audit_logs (user_id, username, action, resource_type, resource_id, resource_name, details, timestamp, ip_address) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, action, resource_type, resource_id, resource_name, details, timestamp, ip_address),
    )
    db.commit()
