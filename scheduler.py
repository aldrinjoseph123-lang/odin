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
the schedule is really being kept (a thread of its own, every minute, so a
long backup does not look like a dead scheduler); that thread also warns the
admins once a day when the clock loop itself has not moved for
scheduler_stuck_hours (a hung job). Each pass it also runs a
backup an admin asked for (Back up now), turns the self-updater's notices
(DATA_DIR/ops-notices, deploy/odin-update.sh) into bell items for the admins,
and warns them once a day when the data disk runs low.
"""
import logging
import os
import signal
import sqlite3
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone

import db as _db

log = logging.getLogger("odin.scheduler")

def _utcnow():
    """Naive UTC, as every stored timestamp is (_utcnow() warns on 3.12)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

HEARTBEAT = "scheduler.heartbeat"
LOOP = "scheduler.loop"   # the clock loop's own stamp, each pass: the heartbeat thread warns when it stops moving
STARTED = None   # when this process's clock loop started (the service sets it): an old stamp from before a restart is not a hang
BOOT = "scheduler.boot"   # which process left the heartbeat: the container health check accepts only its own
BOOT_ID = uuid.uuid4().hex   # this process; written beside every beat and, by the service, to BOOT_FILE
BOOT_FILE = os.path.join(tempfile.gettempdir(), "odin-scheduler.boot")   # inside the container, so `--healthcheck` (a second process) can read it
STOP_BUDGET = 105   # seconds after SIGTERM the threads may take to finish; compose's stop_grace_period is 2m (120 s), the rest is the margin before SIGKILL
BACKUP_REQUEST = "backup.requested"   # Back up now: who asked; the next pass runs it (routes/integrations.py)
OPS_NOTICES = "ops-notices"           # in DATA_DIR: one line per notice, appended by deploy/odin-update.sh
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
_stop_at = None     # when SIGTERM came (monotonic): the join budget counts from here, not from the end of the job in hand


def _on_term(*_):
    global _stopping, _stop_at
    _stop_at = time.monotonic()
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


def _connect():
    """The clock's own connection: wait up to 30 s for a web worker's write
    instead of failing the pass on "database is locked"."""
    return sqlite3.connect(_db.DB_PATH, timeout=30)


def _set(con, key, value):
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    con.commit()


def _stamp(con):
    """The heartbeat, with the process that left it."""
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (BOOT, BOOT_ID))
    _set(con, HEARTBEAT, _utcnow().isoformat())


def _run_job(job, report_on):
    """Run one job. Raises when it did not complete: the caller marks the day
    done only if this returns (the ONCE_A_DAY jobs are marked before it runs)."""
    if job == "digest":
        import send_daily_alerts
        from app import app
        from services import chasers
        from services.notifications import send_summaries
        from policies import is_working_day

        def on_working_days(step):   # a holiday holds the summaries and chasers, as it holds the digest
            def run():
                with app.test_request_context():   # mail links need one
                    if is_working_day():
                        step()
            return run

        failed = []
        # the reminders and alert digest, each person's daily summary (B2) and the customer chasers (B9): one failing does not skip the rest
        for name, step in (("digest", send_daily_alerts.main), ("daily summaries", on_working_days(send_summaries)), ("chasers", on_working_days(chasers.run))):
            try:
                step()
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{name}: {exc}")
                log.error("%s failed: %s", name, exc)
        if failed:
            raise RuntimeError("; ".join(failed))
    elif job == "backup":
        import backup
        ok, message = backup.run_backup(trigger="schedule")
        log.info("backup: %s", message)
        if not ok:
            raise RuntimeError(message)
    elif job == "report" and report_on:
        from app import app
        from services import weekly_report
        with app.test_request_context():
            sent, failed, message = weekly_report.send()
        log.info("weekly report: %s", message)   # queued: the outbox sends it and tries again
    elif job == "housekeeping":
        from services.retention import run_audit_retention

        def audit_retention():
            removed, path = run_audit_retention()
            if removed:
                log.info("audit retention: %s rows archived to %s", removed, path)
        from app import app
        from db import cleanup_soft_deletes, optimize, trim_settled
        from services.dashboard import record_snapshot
        from services.activity import trim as trim_activity
        from services.notifications import trim as trim_notifications
        from services.signup import trim as trim_signup_links
        from services.partner_access import end_dormant as end_dormant_partners
        from services.ai.health import trim as trim_ai
        from services.outbox import trim as trim_outbox
        from services.rules import trim as trim_rule_runs
        from services.recurrence import run_recurring
        from services.doctext import extract_pending as read_documents
        from services.ics import switch_off_idle as idle_calendar_feeds
        failed = []
        with app.app_context():
            for step in (audit_retention,        # a step like the rest: its failure skipped them all (OPS-10)
                         cleanup_soft_deletes,   # deleted projects and files past the undo window
                         run_recurring,          # the next occurrence of repeating tasks done or past their day
                         trim_activity,          # active-minute rows past activity_keep_days
                         trim_notifications,     # read bell items past notifications_keep_days
                         trim_signup_links,      # sign-up links dead for 90 days
                         end_dormant_partners,   # partner accounts whose rollouts all closed long ago (A12)
                         idle_calendar_feeds,    # calendar feeds unread for ics_idle_days switch off
                         trim_ai,                # AI checks past 180 days, finished AI jobs past 30
                         trim_outbox,            # mail and Teams messages sent, or given up on long ago
                         trim_rule_runs,         # automation run logs past rule_runs_keep_days
                         trim_settled,           # resolved alerts past alerts_keep_days, Teams chats of people gone
                         read_documents,         # the text of new uploads, for search and the AI
                         record_snapshot,        # the day's portfolio counts, for the Dashboard's deltas
                         optimize):              # PRAGMA optimize, last: statistics after the day's changes
                try:   # one failing step must not skip the others
                    step()
                except Exception as exc:  # noqa: BLE001
                    # ...nor leave half its work for the next step's commit to make permanent
                    from db import get_db
                    get_db().rollback()
                    failed.append(f"{step.__name__}: {exc}")
                    log.error("housekeeping %s failed: %s", step.__name__, exc)
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
        con = _connect()
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
        log.error("could not notify admins (%s): %s", key, exc)


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
    """One pass: heartbeat, then every due job, the backup last and after this
    quarter hour's alert sync (a 2 GB archive takes a minute and more, and
    must not hold up the alerts). Returns the jobs it ran."""
    from policies import local_now, policy
    import fcntl
    # one scheduler at a time decides what is due (test report OPS-8: a second
    # process on the same minute ran every job twice); the lock covers the
    # read-and-mark, so whoever comes second finds the jobs marked
    lock = open(os.path.join(_db.DATA_DIR, "scheduler.lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    con = _connect()
    con.row_factory = sqlite3.Row
    try:
        now_local = local_now(con)
        _stamp(con)
        _set(con, LOOP, _utcnow().isoformat())
        settings = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM settings WHERE key LIKE 'job.%'")}
        last = {k.split(".")[1]: v for k, v in settings.items() if k.endswith(".last_run")}
        times = {k: policy(k, con) for _, k, _ in JOBS if k}
        days = {k: policy(k, con) for _, _, k in JOBS if k}
        report_on = policy("report_enabled", con)
        cutoff = (_utcnow() - RETRY_AFTER).isoformat()
        todo = [j for j in due_jobs(now_local, last, times, days)
                if (settings.get(f"job.{j}.last_try") or "") < cutoff]   # a failure waits an hour
        todo.sort(key=lambda j: j == "backup")   # the long one last
        for job in todo:
            # Marked tried first (not done: that waits for success), so a second
            # process or a crash loop does not start it again this hour.
            _set(con, f"job.{job}.last_try", _utcnow().isoformat())
        try:
            check_backups_fresh(con)
        except Exception as exc:  # noqa: BLE001
            log.error("backup freshness check failed: %s", exc)
        try:
            check_disk(con)
        except Exception as exc:  # noqa: BLE001
            log.error("disk space check failed: %s", exc)
    finally:
        con.close()
        lock.close()
    for n, job in enumerate(todo):
        if _stopping:   # SIGTERM: leave the rest for the next start, which must not wait an hour
            con = _connect()
            con.executemany("DELETE FROM settings WHERE key = ?", [(f"job.{j}.last_try",) for j in todo[n:]])
            con.commit()
            con.close()
            break
        if job == "backup":
            sync_alerts_due()
        if job in ONCE_A_DAY:   # marked before it runs: a failure is reported, not repeated
            con = _connect()
            _set(con, f"job.{job}.last_run", now_local.date().isoformat())
            con.close()
        try:
            _run_job(job, report_on)
        except Exception as exc:  # noqa: BLE001 — one failed job must not stop the clock
            log.error("%s failed: %s", job, exc)
            _report_failure(job, exc)
        else:
            con = _connect()
            _set(con, f"job.{job}.last_run", now_local.date().isoformat())
            con.close()
    if not _stopping:
        run_requested_backup()
    read_ops_notices()
    return todo


def _tell_admins(title, body, link):
    """A bell notice to every active admin, now (kind "ops"). Never raises."""
    try:
        from app import app
        from markupsafe import escape
        from services.notifications import notify_users
        con = _connect()
        try:
            admins = [r[0] for r in con.execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
        finally:
            con.close()
        with app.test_request_context():
            notify_users(admins, "ops", None, title, escape(body), link=link, email=False)
    except Exception as exc:  # noqa: BLE001 — telling people must not stop the clock
        log.error("could not notify admins (%s): %s", title, exc)


def run_requested_backup():
    """Back up now (Settings › Backups) asks by leaving who asked in the
    settings; the request is cleared before the run, so a crash does not
    repeat it every minute. Runs here, never in a web worker (review P3-29)."""
    con = _connect()
    try:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (BACKUP_REQUEST,)).fetchone()
        if not row:
            return
        con.execute("DELETE FROM settings WHERE key = ?", (BACKUP_REQUEST,))
        con.commit()
    finally:
        con.close()
    import backup
    sync_alerts_due()
    ok, message = backup.run_backup(trigger="manual", actor=row[0] or None)
    log.info("backup now (%s): %s", row[0], message)
    if not ok:
        _tell_admins("Odin's backup (Back up now) failed", f"The backup {row[0]} asked for did not complete: {message[:300]}", "/settings/backups")


def read_ops_notices():
    """The self-updater writes a line to DATA_DIR/ops-notices when an update
    fails or its rollback fails (it cannot reach the bell itself): each line
    becomes a bell notice for the admins, once."""
    path = os.path.join(_db.DATA_DIR, OPS_NOTICES)
    if not os.path.exists(path):
        return
    taken = f"{path}.{os.getpid()}"
    try:
        os.replace(path, taken)   # a line the updater appends meanwhile lands in a new file, read next pass
        with open(taken, encoding="utf-8", errors="replace") as f:
            lines = [line.strip() for line in f if line.strip()]
        os.remove(taken)
    except OSError as exc:
        log.error("could not read %s: %s", path, exc)
        return
    for line in lines[-20:]:   # a flood (an updater failing for days) is the newest twenty
        _tell_admins("Odin's update failed" if "ROLLBACK FAILED" not in line else "Odin's update failed and so did the rollback",
                     line[:600], "/settings/map")


def check_disk(con):
    """Free space on the data volume (the database, uploads and local
    backups share it) below the policy disk_free_min_pct: say so once a day."""
    import shutil
    from policies import policy
    usage = shutil.disk_usage(_db.DATA_DIR)
    free = 100 * usage.free / usage.total
    if free < policy("disk_free_min_pct", con):
        _tell_admins_once_a_day(
            "disk_low", "Odin's disk is nearly full",
            f"Only {free:.0f}% ({usage.free // 2**30} GB) of the disk holding Odin's data is free. A full disk stops every save and every backup. "
            "Free space on the server or prune old backups (Settings > Backups > Copies kept); see docs/RUNBOOK.md, \"Disk full\".",
            "/settings/backups")


def beat():
    """The heartbeat (Settings › Backups and the container health check read it)."""
    con = sqlite3.connect(_db.DB_PATH, timeout=10)
    try:
        _stamp(con)
    finally:
        con.close()


def check_loop():
    """The heartbeat proves the process lives, not that the clock moves: a job
    that hangs (a network share with no timeout) stops the digest, alerts,
    backups and housekeeping, and the checks inside the loop with them. Warn
    the admins once a day when the loop's stamp is older than the policy
    scheduler_stuck_hours (counted from this process's start, not from the
    stamp the previous container left)."""
    from policies import policy
    con = _connect()
    try:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (LOOP,)).fetchone()
        hours = policy("scheduler_stuck_hours", con)
    finally:
        con.close()
    moved = max(filter(None, (STARTED, datetime.fromisoformat(row[0]) if row else None)), default=None)
    if moved and moved < _utcnow() - timedelta(hours=hours):
        _tell_admins_once_a_day(
            "loop_stuck", "Odin's schedule has stopped",
            f"The scheduler's clock has not moved since {moved.strftime('%d %b %H:%M')} UTC (more than {hours} hours): a job is hanging, "
            "so the digest, alerts, backups and housekeeping are waiting behind it. Restart the scheduler (docker compose restart scheduler) "
            "and read its log; see docs/RUNBOOK.md, \"The schedule has stopped\".",
            "/settings/backups")


def heartbeat():
    """The heartbeat from a thread of its own: a backup or report that takes
    longer than the health check's three minutes must not mark the scheduler
    dead while it works (review P3-27). It also watches the clock loop
    (check_loop), which cannot watch itself."""
    while not _stopping:
        for step in (beat, check_loop):
            try:
                step()
            except Exception as exc:  # noqa: BLE001 — a locked database this minute is fine next minute
                log.error("%s failed: %s", step.__name__, exc)
        _nap(60)


def healthy(max_age_minutes=3, boot=None):
    """For the container health check: a heartbeat in the last few minutes.
    With `boot` (the container's own process, from BOOT_FILE) the beat must be
    that process's: the database is shared, so the previous container's last
    beat would otherwise make a hung new scheduler look alive for three minutes."""
    try:
        con = sqlite3.connect(_db.DB_PATH)  # healthcheck: the default 5 s wait, inside Docker's budget
        row = con.execute("SELECT value FROM settings WHERE key = ?", (HEARTBEAT,)).fetchone()
        who = con.execute("SELECT value FROM settings WHERE key = ?", (BOOT,)).fetchone()
        con.close()
        if boot is not None and (not who or who[0] != boot):
            return False
        return bool(row) and datetime.fromisoformat(row[0]) > _utcnow() - timedelta(minutes=max_age_minutes)
    except Exception:  # noqa: BLE001 — no database yet is simply "not healthy"
        return False


def alert_quarter(now):
    """Which quarter hour `now` is in: alerts are recorded once in each."""
    return now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)


_synced = None   # the quarter hour alerts were last recorded in (sync_alerts_due)


def sync_alerts_due():
    """sync_alerts on the first call in each quarter hour: from the clock loop
    after each pass, and from run_due before a backup. Never raises."""
    global _synced
    quarter = alert_quarter(_utcnow())
    if quarter == _synced:
        return
    try:
        sync_alerts()
        _synced = quarter
    except Exception as exc:  # noqa: BLE001
        log.error("alert sync failed: %s", exc)


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
            log.error("AI worker pass failed: %s", exc)
            busy = None
        _nap(1 if busy else 15)


def outbox_pass():
    """Send the mail and Teams messages that are due (services/outbox.py),
    urgent first, for at most outbox_pass_seconds (a hung Microsoft takes 15 s
    a row): it stops between rows, so a SIGTERM waits for the send in hand
    (which commits its result) and for no more, not for the whole batch."""
    from app import app
    from policies import policy
    from services.outbox import drain
    with app.app_context():
        deadline = time.monotonic() + policy("outbox_pass_seconds")
        return drain(limit=50, stop=lambda: _stopping or time.monotonic() >= deadline)


def outbox_worker():
    """The outbox worker, a thread beside the clock like the AI worker: a long
    backup must not hold up a stage-move mail. The queued mail and Teams
    messages (stage moves, digests, alerts) go out here, never from a web
    worker; sign-in and reset links and the signed sign-off PDF are sent
    inline, in the request that asks for them."""
    while not _stopping:
        try:
            busy = outbox_pass()
        except Exception as exc:  # noqa: BLE001 — the worker outlives a bad pass
            log.error("outbox pass failed: %s", exc)
            busy = None
        _nap(1 if busy else 5)


if __name__ == "__main__":
    if "--healthcheck" in sys.argv:
        try:
            with open(BOOT_FILE) as f:
                boot = f.read().strip()
        except OSError:   # the service has not started yet
            sys.exit(1)
        sys.exit(0 if healthy(boot=boot) else 1)
    import core  # noqa: F401 — configures logging (core.configure_logging), as in the web app
    if "--once" in sys.argv:   # cron mode: alerts too (test report OPS-15)
        log.info("ran: %s", ", ".join(run_due()) or "nothing due")
        sync_alerts()
        ai_pass()
        outbox_pass()
        sys.exit(0)
    import threading
    signal.signal(signal.SIGTERM, _on_term)   # docker stop: finish the job in hand, then leave
    STARTED = _utcnow()
    try:   # AI jobs the previous process left running are not running: no other worker exists yet
        from app import app
        from db import get_db
        from services.ai.health import fail_interrupted
        with app.app_context():
            fail_interrupted(get_db())
    except Exception as exc:  # noqa: BLE001
        log.error("could not clear interrupted AI jobs: %s", exc)
    try:
        with open(BOOT_FILE, "w") as f:
            f.write(BOOT_ID)
    except OSError as exc:
        log.error("could not write %s (the health check will fail): %s", BOOT_FILE, exc)
    threading.Thread(target=heartbeat, name="heartbeat", daemon=True).start()
    worker = threading.Thread(target=ai_worker, name="ai-worker", daemon=True)
    worker.start()
    mailer = threading.Thread(target=outbox_worker, name="outbox-worker", daemon=True)
    mailer.start()
    while not _stopping:
        try:
            run_due()
        except Exception as exc:  # noqa: BLE001 — a bad pass (e.g. the database mid-migration) must not end the service
            log.error("pass failed: %s", exc)
        # alerts every quarter hour, on the first pass after each boundary
        # even when a long job made this pass late, and whatever run_due did
        sync_alerts_due()
        _nap(60 - _utcnow().second)   # wake on the minute
    # one budget for both, counted from the SIGTERM (not from the end of the job in
    # hand), so the joins never run past compose's stop_grace_period
    deadline = (_stop_at or time.monotonic()) + STOP_BUDGET
    for thread in (mailer, worker):   # the mailer first: a message in hand matters more than an AI draft
        thread.join(timeout=max(1, deadline - time.monotonic()))
        if thread.is_alive():
            log.warning("%s did not finish in time; leaving it (its work is retried on the next start)", thread.name)
    log.info("stopped on SIGTERM")
