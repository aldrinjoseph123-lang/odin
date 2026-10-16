"""Access review (Users page): why an account deserves a second look.

{user_id: [reason, ...]} for active, approved accounts: no sign-in for
`access_review_days`, a partner whose rollouts have all closed. Odin has no
per-user rights beyond the role's defaults, so that third check does not exist.
"""
from datetime import datetime, timedelta

from db import PROJECT_OPEN_SQL


def review(db, days, now=None):
    now = now or datetime.utcnow()
    cutoff = (now - timedelta(days=days)).isoformat()
    open_on = {r[0] for r in db.execute(
        "SELECT DISTINCT pp.user_id FROM project_participants pp JOIN projects p ON p.id = pp.project_id "
        f"WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}")}
    on_any = {r[0] for r in db.execute("SELECT DISTINCT user_id FROM project_participants")}
    out = {}
    for u in db.execute("SELECT id, kind, last_login_at, created_at FROM users WHERE active = 1 AND COALESCE(pending, 0) = 0"):
        why = []
        seen = u["last_login_at"] or u["created_at"] or ""
        if seen and seen < cutoff:   # an account made inside the window has not had time to go quiet
            why.append(f"No sign-in for {days}+ days" if u["last_login_at"] else f"Never signed in, made over {days} days ago")
        if u["kind"] == "external" and u["id"] not in open_on:
            why.append("All their rollouts have closed" if u["id"] in on_any else "On no rollout")
        if why:
            out[u["id"]] = why
    return out
