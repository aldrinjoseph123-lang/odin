"""The one clock for Odin's recurring jobs, at the times set in Settings.

Runs as its own process (the `scheduler` service in docker-compose.yml), so
jobs never run once per web worker. Every minute it asks which jobs are due
in the workspace time zone (Settings → General), runs them, and remembers the
day it last ran each one, so a job missed while the service was down still
runs later the same day, and never twice in a day.

    python scheduler.py          # the service: loops forever
    python scheduler.py --once   # one check, for cron instead of the service

It also leaves a heartbeat that Settings shows, so an admin can see whether
the schedule is really being kept.
"""
import sqlite3
import sys
import time
from datetime import datetime

import db as _db

HEARTBEAT = "scheduler.heartbeat"

# (job, the policy holding its time, the policy holding the days it runs on);
# None = fixed: housekeeping runs nightly at 03:30 every day.
JOBS = (
    ("digest", "digest_time", "working_days"),
    ("backup", "backup_time", "backup_days"),
    ("report", "report_time", "report_days"),
    ("housekeeping", None, None),
)
FIXED_TIME, EVERY_DAY = "03:30", ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def due_jobs(now_local, last_runs, times, days):
    """Which jobs to run now: past today's time, on one of their days, and
    not already run today. `last_runs` maps job -> ISO date last run."""
    from policies import WEEKDAYS
    today, weekday, clock = now_local.date().isoformat(), WEEKDAYS[now_local.weekday()], now_local.strftime("%H:%M")
    return [job for job, time_key, days_key in JOBS
            if weekday in (days[days_key] if days_key else EVERY_DAY) and clock >= (times[time_key] if time_key else FIXED_TIME)
            and last_runs.get(job) != today]


def next_run(now_local, at, days):
    """The next local datetime a job set for `at` on `days` will run."""
    from datetime import timedelta
    from policies import WEEKDAYS
    hour, minute = map(int, at.split(":"))
    for ahead in range(8):
        day = now_local + timedelta(days=ahead)
        when = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if WEEKDAYS[day.weekday()] in days and when > now_local:
            return when
    return None


def _set(con, key, value):
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    con.commit()


def run_due():
    """One pass: heartbeat, then every due job. Returns the jobs it ran."""
    from zoneinfo import ZoneInfo
    from policies import policy
    con = sqlite3.connect(_db.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        now_local = datetime.now(ZoneInfo(policy("timezone", con)))
        _set(con, HEARTBEAT, datetime.utcnow().isoformat())
        last = {r["key"].split(".")[1]: r["value"] for r in con.execute("SELECT key, value FROM settings WHERE key LIKE 'job.%.last_run'")}
        times = {k: policy(k, con) for _, k, _ in JOBS if k}
        days = {k: policy(k, con) for _, _, k in JOBS if k}
        report_on = policy("report_enabled", con)
        todo = due_jobs(now_local, last, times, days)
        for job in todo:
            # Marked first: a job that crashes is not retried every minute all day.
            _set(con, f"job.{job}.last_run", now_local.date().isoformat())
    finally:
        con.close()
    for job in todo:
        try:
            if job == "digest":
                import send_daily_alerts
                send_daily_alerts.main()
            elif job == "backup":
                import backup
                ok, message = backup.run_backup(trigger="schedule")
                print(f"[scheduler] backup: {message}")
            elif job == "report" and report_on:
                from app import app
                from services import weekly_report
                with app.test_request_context():
                    print(f"[scheduler] weekly report: {weekly_report.send()[2]}")
            elif job == "housekeeping":
                from services.retention import run_audit_retention
                removed, path = run_audit_retention()
                if removed:
                    print(f"[scheduler] audit retention: {removed} rows archived to {path}")
                from app import app
                from services.dashboard import record_snapshot
                with app.app_context():   # the day's portfolio counts, for the Dashboard's deltas
                    record_snapshot()
        except Exception as exc:  # noqa: BLE001 — one failed job must not stop the clock
            print(f"[scheduler] {job} failed: {exc}", file=sys.stderr)
    return todo


def healthy(max_age_minutes=3):
    """For the container health check: a heartbeat in the last few minutes."""
    from datetime import timedelta
    try:
        con = sqlite3.connect(_db.DB_PATH)
        row = con.execute("SELECT value FROM settings WHERE key = ?", (HEARTBEAT,)).fetchone()
        con.close()
        return bool(row) and datetime.fromisoformat(row[0]) > datetime.utcnow() - timedelta(minutes=max_age_minutes)
    except Exception:  # noqa: BLE001 — no database yet is simply "not healthy"
        return False


if __name__ == "__main__":
    if "--healthcheck" in sys.argv:
        sys.exit(0 if healthy() else 1)
    if "--once" in sys.argv:
        print(f"[scheduler] ran: {', '.join(run_due()) or 'nothing due'}")
        sys.exit(0)
    while True:
        try:
            run_due()
        except Exception as exc:  # noqa: BLE001 — a bad pass (e.g. the database mid-migration) must not end the service
            print(f"[scheduler] pass failed: {exc}", file=sys.stderr)
        time.sleep(60 - datetime.utcnow().second)   # wake on the minute
