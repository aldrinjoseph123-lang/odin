"""Daily digest of overdue/due-soon invoices and stale projects.

Cron this once a day, e.g.:
    0 8 * * * cd /path/to/PMS && ./venv/bin/python send_daily_alerts.py >> alerts.log 2>&1

Sends one Teams channel message and one email per Admin user (with an email
set) summarizing the same alerts shown on the Board page. Real-time events
(project created, stage changed, vendor invoice received) are sent instantly
from app.py instead — this script only covers the "scan everything, once a
day" style alerts that would be spammy to send on every page load.

Deliberately ignores the board's per-login session dismissals — this is a
cron job with no browser session, and the digest should always reflect the
real, current alert state regardless of what anyone clicked on the board.
"""
import sys

from app import app  # only for the Flask app context that get_db() needs
from db import get_db, get_setting, get_terminal_stage
from services.alerts import build_alerts

import graph


def _format_alerts_html(alerts):
    lines = []
    labels = {
        "project_overdue": "Projects overdue",
        "project_due_soon": "Projects due soon",
        "stale": "Projects untouched for a while",
    }
    for key, label in labels.items():
        items = alerts.get(key) or []
        if not items:
            continue
        names = ", ".join(p["name"] for p in items)
        lines.append(f"<b>{label} ({len(items)}):</b> {names}")
    return "<br>".join(lines) if lines else None


def main():
    with app.app_context():
        db = get_db()
        projects = db.execute(
            "SELECT * FROM projects WHERE stage != ?", (get_terminal_stage(),)
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

        if get_setting("notify_email_enabled") == "1":
            admins = db.execute(
                "SELECT email FROM users WHERE role = 'Admin' AND active = 1 AND email IS NOT NULL AND email != ''"
            ).fetchall()
            for admin in admins:
                ok, error = graph.send_mail(admin["email"], "Odin Daily Alert Digest", html)
                print(f"Email to {admin['email']}: {'sent' if ok else error}")
                sent_anything = sent_anything or ok

        return 0 if sent_anything else 1


if __name__ == "__main__":
    sys.exit(main())
