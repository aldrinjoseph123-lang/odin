"""The one clock for Odin's recurring jobs, at the times set in Settings.

Runs as its own process (the `scheduler` service in docker-compose.yml), so
jobs never run once per web worker. Every minute it asks which jobs are due
in the workspace time zone (Settings → General), runs them, and remembers the
day each one last *succeeded*, so a job missed while the service was down still
runs later the same day, and never twice in a day. A job that fails is tried
again an hour later (not every minute), and the admins hear about it in the
bell, once a day per job. Two jobs are never retried the same day, because a
retry repeats what already went out: the digest (reminders and Teams posts
already sent) and the backup (every retry writes a full archive and uploads it
to each cloud destination again).

    python scheduler.py          # the service: loops forever
    python scheduler.py --once   # one check, for cron instead of the service

It also leaves a heartbeat that Settings shows, so an admin can see whether
the schedule is really being kept.
"""
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import db as _db


def _utcnow():
    """Naive UTC, as every stored timestamp is (_utcnow() warns on 3.12)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

HEARTBEAT = "scheduler.heartbeat"
# ponytail: not a policy. It is a guard against a minute-by-minute retry storm, not a business rule; no admin has a reason to tune it, and the only jobs it still applies to (report, housekeeping) are idempotent.
RETRY_AFTER = timedelta(hours=1)   # a failing job is tried again at most this often
RETRY_MINUTES = int(RETRY_AFTER.total_seconds() // 60)
ONCE_A_DAY = ("digest", "backup")   # attempted = done for the day: a retry would repeat sent mail or a full upload

# what an admin reads in the bell: (name, where to look)
JOB_LABELS = {
    "digest": ("daily digest", "/settings/notifications"),
    "backup": ("scheduled backup", "/settings/backups"),
    "report": ("weekly report", "/settings/reports"),
    "housekeeping": ("nightly housekeeping (purge and retention)", "/settings/audit"),
}

_stopping = False   # set by SIGTERM: finish the job in hand, run no more, exit


def _on_term(*_):
    global _stopping
    _stopping = True


def _nap(seconds):
    """Sleep in short slices so a SIGTERM is noticed within a second."""
    for _ in range(int(seconds)):
        if _stopping:
            return
        time.sleep(1)

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
            and (last_runs.get(job) or "") < today]   # "before today": a time zone moved west must not re-run a day (test report OPS-17)


def next_run(now_local, at, days):
    """The next local datetime a job set for `at` on `days` will run."""
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


def _run_job(job, report_on):
    """Run one job. Raises when it did not complete: the caller marks the day
    done only if this returns (the ONCE_A_DAY jobs are marked before it runs)."""
    if job == "digest":
        import send_daily_alerts
        send_daily_alerts.main()
    elif job == "backup":
        import backup
        ok, message = backup.run_backup(trigger="schedule")
        print(f"[scheduler] backup: {message}")
        if not ok:
            raise RuntimeError(message)
    elif job == "report" and report_on:
        from app import app
        from services import weekly_report
        with app.test_request_context():
            sent, failed, message = weekly_report.send()
        print(f"[scheduler] weekly report: {message}")
        if failed and not sent:   # a partly sent report is not re-sent: the others would get it twice
            raise RuntimeError(message)
    elif job == "housekeeping":
        from services.retention import run_audit_retention

        def audit_retention():
            removed, path = run_audit_retention()
            if removed:
                print(f"[scheduler] audit retention: {removed} rows archived to {path}")
        from app import app
        from db import cleanup_soft_deletes
        from services.dashboard import record_snapshot
        from services.activity import trim as trim_activity
        from services.notifications import trim as trim_notifications
        from services.signup import trim as trim_signup_links
        from services.ai.health import trim as trim_ai
        from services.doctext import extract_pending as read_documents
        failed = []
        with app.app_context():
            for step in (audit_retention,        # a step like the rest: its failure skipped them all (OPS-10)
                         cleanup_soft_deletes,   # deleted projects and files past the undo window
                         trim_activity,          # active-minute rows past activity_keep_days
                         trim_notifications,     # read bell items past notifications_keep_days
                         trim_signup_links,      # sign-up links dead for 90 days
                         trim_ai,                # AI checks past 180 days, finished AI jobs past 30
                         read_documents,         # the text of new uploads, for search and the AI
                         record_snapshot):       # the day's portfolio counts, for the Dashboard's deltas
                try:   # one failing step must not skip the others
                    step()
                except Exception as exc:  # noqa: BLE001
                    # ...nor leave half its work for the next step's commit to make permanent
                    from db import get_db
                    get_db().rollback()
                    failed.append(f"{step.__name__}: {exc}")
                    print(f"[scheduler] housekeeping {step.__name__} failed: {exc}", file=sys.stderr)
        if failed:
            raise RuntimeError("; ".join(failed))


def _tell_admins_once_a_day(key, title, body, link):
    """A bell notice to every active admin, at most once a day per `key`
    (the day in UTC, kept in the settings table). Never raises."""
    try:
        from app import app
        from markupsafe import escape
        from services.notifications import notify_users
        today = _utcnow().date().isoformat()
        con = sqlite3.connect(_db.DB_PATH)
        try:
            row = con.execute("SELECT value FROM settings WHERE key = ?", (f"scheduler.notified.{key}",)).fetchone()
            if row and row[0] == today:
                return
            _set(con, f"scheduler.notified.{key}", today)
            admins = [r[0] for r in con.execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
        finally:
            con.close()
        with app.test_request_context():
            notify_users(admins, "ops", None, title, escape(body), link=link, email=False)
    except Exception as exc:  # noqa: BLE001 — telling people must not stop the clock
        print(f"[scheduler] could not notify admins ({key}): {exc}", file=sys.stderr)


def _report_failure(job, error):
    label, link = JOB_LABELS[job]
    _tell_admins_once_a_day(
        job, f"Odin's {label} failed",
        f"The {label} did not complete: {str(error)[:300]}. "
        + ("Odin does not retry it today." if job in ONCE_A_DAY else f"Odin tries again after {RETRY_MINUTES} minutes.")
        + " See the container log of the scheduler for details.",
        link)


def stale_backup_limit(days):
    """How old the newest good backup may be before it is a problem: the
    longest gap between two scheduled backup days (round the week) plus a day,
    so a Sunday-only schedule allows 8 days and a daily one 2."""
    from policies import WEEKDAYS
    idx = sorted(WEEKDAYS.index(d) for d in days)
    gap = max((b - a) % 7 or 7 for a, b in zip(idx, idx[1:] + idx[:1]))
    return timedelta(days=gap + 1)


def check_backups_fresh(con):
    """The newest good backup is older than the schedule allows (or none ever
    worked since the first attempt): say so once a day. Only when backups are
    scheduled."""
    from policies import policy
    days = policy("backup_days", con)
    if not days:
        return
    last = con.execute("SELECT MAX(finished_at) FROM backup_runs WHERE ok = 1").fetchone()[0] \
        or con.execute("SELECT MIN(started_at) FROM backup_runs").fetchone()[0]
    limit = stale_backup_limit(days)
    if last and datetime.fromisoformat(last) < _utcnow() - limit:
        age = (_utcnow() - datetime.fromisoformat(last)).days
        _tell_admins_once_a_day(
            "backup_stale", "Odin has no recent good backup",
            f"The newest successful backup is {age} days old; backups are scheduled on {', '.join(days)}, so more than {limit.days} days is too long. Check Settings > Backups and the scheduler's log.",
            "/settings/backups")


def run_due():
    """One pass: heartbeat, then every due job. Returns the jobs it ran."""
    from zoneinfo import ZoneInfo
    from policies import policy
    import fcntl
    # one scheduler at a time decides what is due (test report OPS-8: a second
    # process on the same minute ran every job twice); the lock covers the
    # read-and-mark, so whoever comes second finds the jobs marked
    lock = open(os.path.join(_db.DATA_DIR, "scheduler.lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    con = sqlite3.connect(_db.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        now_local = datetime.now(ZoneInfo(policy("timezone", con)))
        _set(con, HEARTBEAT, _utcnow().isoformat())
        settings = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM settings WHERE key LIKE 'job.%'")}
        last = {k.split(".")[1]: v for k, v in settings.items() if k.endswith(".last_run")}
        times = {k: policy(k, con) for _, k, _ in JOBS if k}
        days = {k: policy(k, con) for _, _, k in JOBS if k}
        report_on = policy("report_enabled", con)
        cutoff = (_utcnow() - RETRY_AFTER).isoformat()
        todo = [j for j in due_jobs(now_local, last, times, days)
                if (settings.get(f"job.{j}.last_try") or "") < cutoff]   # a failure waits an hour
        for job in todo:
            # Marked tried first (not done: that waits for success), so a second
            # process or a crash loop does not start it again this hour.
            _set(con, f"job.{job}.last_try", _utcnow().isoformat())
        try:
            check_backups_fresh(con)
        except Exception as exc:  # noqa: BLE001
            print(f"[scheduler] backup freshness check failed: {exc}", file=sys.stderr)
    finally:
        con.close()
        lock.close()
    for n, job in enumerate(todo):
        if _stopping:   # SIGTERM: leave the rest for the next start, which must not wait an hour
            con = sqlite3.connect(_db.DB_PATH)
            con.executemany("DELETE FROM settings WHERE key = ?", [(f"job.{j}.last_try",) for j in todo[n:]])
            con.commit()
            con.close()
            break
        if job in ONCE_A_DAY:   # marked before it runs: a failure is reported, not repeated
            con = sqlite3.connect(_db.DB_PATH)
            _set(con, f"job.{job}.last_run", now_local.date().isoformat())
            con.close()
        try:
            _run_job(job, report_on)
        except Exception as exc:  # noqa: BLE001 — one failed job must not stop the clock
            print(f"[scheduler] {job} failed: {exc}", file=sys.stderr)
            _report_failure(job, exc)
        else:
            con = sqlite3.connect(_db.DB_PATH)
            _set(con, f"job.{job}.last_run", now_local.date().isoformat())
            con.close()
    return todo


def healthy(max_age_minutes=3):
    """For the container health check: a heartbeat in the last few minutes."""
    try:
        con = sqlite3.connect(_db.DB_PATH)
        row = con.execute("SELECT value FROM settings WHERE key = ?", (HEARTBEAT,)).fetchone()
        con.close()
        return bool(row) and datetime.fromisoformat(row[0]) > _utcnow() - timedelta(minutes=max_age_minutes)
    except Exception:  # noqa: BLE001 — no database yet is simply "not healthy"
        return False


def alert_quarter(now):
    """Which quarter hour `now` is in: alerts are recorded once in each."""
    return now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)


def sync_alerts():
    """Record the alert conditions (overdue, over SLA, due soon, stale...) every
    quarter hour: the Alerts page, the nav badge, the dashboard and the alert
    notifications all read the stored rows, which nothing else keeps current."""
    from app import app
    from db import PROJECT_OPEN_SQL, get_db
    from services.alerts import build_alerts, sync_alerts_to_db
    with app.test_request_context():   # notifications build links
        rows = get_db().execute(f"SELECT p.* FROM projects p WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}").fetchall()
        sync_alerts_to_db(build_alerts(rows))


def ai_pass():
    """One pass of the AI worker (services/ai/health.tick): heartbeat when
    due, the daily validation when due, one queued job."""
    from app import app
    from db import get_db
    from services.ai.health import tick
    with app.app_context():
        return tick(get_db())


def ai_worker():
    """The AI worker, a thread beside the clock: a validation can take ten
    minutes and must not hold up a backup or the digest. Idle passes are
    cheap (a heartbeat is one GET every few minutes)."""
    while not _stopping:
        try:
            busy = ai_pass()
        except Exception as exc:  # noqa: BLE001 — the worker outlives a bad pass
            print(f"[scheduler] AI worker pass failed: {exc}", file=sys.stderr)
            busy = None
        _nap(1 if busy else 15)


if __name__ == "__main__":
    if "--healthcheck" in sys.argv:
        sys.exit(0 if healthy() else 1)
    if "--once" in sys.argv:   # cron mode: alerts too (test report OPS-15)
        print(f"[scheduler] ran: {', '.join(run_due()) or 'nothing due'}")
        sync_alerts()
        ai_pass()
        sys.exit(0)
    import threading
    signal.signal(signal.SIGTERM, _on_term)   # docker stop: finish the job in hand, then leave
    worker = threading.Thread(target=ai_worker, name="ai-worker", daemon=True)
    worker.start()
    synced = None   # the quarter hour alerts were last recorded in
    while not _stopping:
        try:
            run_due()
        except Exception as exc:  # noqa: BLE001 — a bad pass (e.g. the database mid-migration) must not end the service
            print(f"[scheduler] pass failed: {exc}", file=sys.stderr)
        # alerts every quarter hour, on the first pass after each boundary
        # even when a long job made this pass late, and whatever run_due did
        quarter = alert_quarter(_utcnow())
        if quarter != synced:
            try:
                sync_alerts()
                synced = quarter
            except Exception as exc:  # noqa: BLE001
                print(f"[scheduler] alert sync failed: {exc}", file=sys.stderr)
        _nap(60 - _utcnow().second)   # wake on the minute
    worker.join(timeout=90)   # an AI job in hand finishes inside the compose grace period
    print("[scheduler] stopped on SIGTERM")
