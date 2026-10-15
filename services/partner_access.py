"""Partner accounts end when their work ends (review A12).

An external account (partner, contractor, customer contact) is deactivated
once every live rollout it is on has sat in its last stage for
`external_access_days_after_close` days. 0 (the default) leaves them alone.
Run nightly by the scheduler's housekeeping; each account ended is audited.
"""
from datetime import datetime, timedelta

from db import PROJECT_OPEN_SQL, get_db
from policies import policy


def end_dormant(db=None):
    """Deactivate dormant partner accounts; returns how many."""
    db = db or get_db()
    days = policy("external_access_days_after_close", db)
    if not days:
        return 0
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    # on at least one live rollout, and on none that is open or closed more recently than the cutoff
    rows = db.execute(
        "SELECT u.id, u.username FROM users u WHERE u.kind = 'external' AND u.active = 1 "
        "AND EXISTS (SELECT 1 FROM project_participants pp JOIN projects p ON p.id = pp.project_id WHERE pp.user_id = u.id AND p.deleted_at IS NULL) "
        "AND NOT EXISTS (SELECT 1 FROM project_participants pp JOIN projects p ON p.id = pp.project_id WHERE pp.user_id = u.id AND p.deleted_at IS NULL "
        f"AND ({PROJECT_OPEN_SQL} OR COALESCE(p.stage_entered_at, p.updated_at) > ?))", (cutoff,)).fetchall()
    now = datetime.utcnow().isoformat()
    for uid, username in rows:
        # the epoch ends any session the account still has open, as the Users page's switch does
        db.execute("UPDATE users SET active = 0, session_epoch = session_epoch + 1 WHERE id = ? AND active = 1", (uid,))
        db.execute("INSERT INTO audit_logs (user_id, username, action, resource_type, resource_id, resource_name, details, timestamp) "
                   "VALUES (NULL, 'scheduler', 'set_user_active', 'user', ?, ?, ?, ?)",
                   (uid, username, f"active=0: every rollout closed over {days} days ago (external_access_days_after_close)", now))
    db.commit()
    return len(rows)
