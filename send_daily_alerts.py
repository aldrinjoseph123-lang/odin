"""The daily digest: overdue, due-soon, over-SLA and stalled rollouts.

scheduler.py runs main() at the digest time (Settings → Notifications) on
working days; do not cron it as well, or the digest goes out twice. Running
it by hand sends one now.

Sends one Teams channel message and one email per Admin (with an address),
and each project manager a bell note about their own rollouts. Real-time
events (a project created, a stage changed) are sent as they happen instead.
"""
import sys

from app import app  # only for the Flask app context that get_db() needs
from db import PROJECT_OPEN_SQL, get_db, get_setting
from services.alerts import build_alerts

import graph


def _format_alerts_html(alerts):
    from markupsafe import escape
    lines = []
    labels = {
        "project_overdue": "Projects overdue",
        "project_due_soon": "Projects due soon",
        "stage_sla_breach": "Projects over their stage SLA",
        "stale": "Projects untouched for a while",
        "approval_waiting": "Customer approvals waiting",
        "blocker_open": "Blockers still open",
        "task_unowned": "Overdue tasks nobody owns",
        "customer_quiet": "Customer tasks overdue",
    }
    for key, label in labels.items():
        items = alerts.get(key) or []
        if not items:
            continue
        names = ", ".join(str(escape(p["name"])) for p in items)   # names are user input; the digest is HTML
        lines.append(f"<b>{label} ({len(items)}):</b> {names}")
    return "<br>".join(lines) if lines else None


def send_due_reminders(db):
    """One reminder per person with open tasks due today or overdue, through
    the normal notification path: the bell always, email unless they turned
    'due' off. Returns how many people were reminded."""
    from datetime import date
    from markupsafe import escape
    from db import PROJECT_OPEN_SQL as OPEN
    from services.notifications import notify_users
    from policies import local_today
    today = local_today(db).isoformat()
    rows = db.execute(
        "SELECT t.title, t.due_date, t.assignee_id, p.name AS project_name FROM tasks t JOIN projects p ON p.id = t.project_id "
        "JOIN users u ON u.id = t.assignee_id "
        f"WHERE t.done = 0 AND t.assignee_id IS NOT NULL AND t.due_date IS NOT NULL AND t.due_date <= ? AND p.deleted_at IS NULL AND {OPEN} "
        # an outsider hears only about projects they are still on (a removed partner is not told a project's task names)
        "AND (u.kind = 'internal' OR EXISTS (SELECT 1 FROM project_participants pp WHERE pp.project_id = t.project_id AND pp.user_id = t.assignee_id)) "
        "ORDER BY t.assignee_id, t.due_date", (today,),
    ).fetchall()
    by_person = {}
    for r in rows:
        by_person.setdefault(r["assignee_id"], []).append(r)
    for uid, tasks in by_person.items():
        items = "".join(
            f"<li>{escape(t['title'])} — {escape(t['project_name'])}, {'due today' if t['due_date'] == today else 'overdue since ' + t['due_date']}</li>"
            for t in tasks)
        n = len(tasks)
        notify_users([uid], "due", None, f"{n} task{'s' if n != 1 else ''} need{'' if n != 1 else 's'} you today", f"<ul>{items}</ul>", link="/my-work")
    return len(by_person)


def main():
    with app.test_request_context():   # url_for in mails needs a request context
        db = get_db()
        from policies import is_working_day
        if not is_working_day(db=db):   # Settings → General → Working week
            print("Not a working day — no reminders or digest.")
            return 0
        reminded = send_due_reminders(db)
        print(f"Due-task reminders: {reminded} person(s).")
        projects = db.execute(
            f"SELECT p.* FROM projects p WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}"
        ).fetchall()
        alerts = build_alerts(projects)
        html = _format_alerts_html(alerts)

        if html is None:
            print("No alerts today — nothing sent.")
            return 0

        sent_anything = False

        if get_setting("notify_teams_enabled") == "1":
            ok, error = graph.send_teams_message(f"<b>Daily Odin Alert Digest</b><br>{html}")
            print("Teams digest sent." if ok else f"Teams digest failed: {error}")
            sent_anything = sent_anything or ok

        # Admins get the whole picture, each project manager their own rollouts:
        # the bell always, email unless they turned alert mails off.
        from services.notifications import notify_users
        admins = [r[0] for r in db.execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
        notify_users(admins, "alert", None, "Odin daily alert digest", html, link="/alerts")
        sent_anything = sent_anything or bool(admins)
        mine = {}
        for key, items in alerts.items():
            for p in items or []:
                mine.setdefault(p["owner_id"], {}).setdefault(p["id"], p["name"])
        for owner, projects in mine.items():
            if owner in admins:
                continue   # already has the whole digest
            n = len(projects)
            notify_users([owner], "alert", None, f"{n} of your rollout{'s' if n != 1 else ''} need{'s' if n == 1 else ''} attention today",
                         _format_alerts_html({k: [p for p in v if p["owner_id"] == owner] for k, v in alerts.items()}), link="/alerts")
        print(f"Digest: {len(admins)} admin(s), {len([o for o in mine if o not in admins])} project manager(s).")
        return 0 if sent_anything else 1


if __name__ == "__main__":
    sys.exit(main())
