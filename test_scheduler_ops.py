"""Scheduler reliability (review P2-13): a job is marked done only when it
completed, a failure is retried no more than hourly, and admins hear about it
in the bell once a day. Run with: python -m unittest test_scheduler_ops"""
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import backup
import db as db_module
import scheduler
from test_fix_logic import FixBase


class SchedulerOpsTestCase(FixBase):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, scheduler, "_stopping", False)
        # every pass checks free disk (scheduler.check_disk): a host under disk_free_min_pct would add its notice
        p = patch("shutil.disk_usage", return_value=__import__("shutil")._ntuple_diskusage(100 * 2**30, 10 * 2**30, 90 * 2**30))
        p.start()
        self.addCleanup(p.stop)

    def run_backup_pass(self, result):
        """One pass in which only the backup is due and run_backup gives `result`."""
        with patch("scheduler.due_jobs", return_value=["backup"]), patch("backup.run_backup", return_value=result) as run:
            scheduler.run_due()
        return run

    def setting(self, key):
        rows = self.sql("SELECT value FROM settings WHERE key = ?", key)
        return rows[0][0] if rows else None

    def notices(self, like="Odin%"):
        return self.sql("SELECT user_id, kind, title, body, link FROM notifications WHERE title LIKE ?", like)

    def test_success_marks_the_job_done_and_tells_nobody(self):
        self.run_backup_pass((True, "local"))
        self.assertTrue(self.setting("job.backup.last_run"))
        self.assertEqual(self.notices(), [])

    def run_housekeeping_pass(self):
        """One pass in which only housekeeping is due and one of its steps fails."""
        def trim_activity():
            raise RuntimeError("locked")
        with patch("scheduler.due_jobs", return_value=["housekeeping"]), \
             patch("services.retention.run_audit_retention", return_value=(0, None)), \
             patch("services.activity.trim", new=trim_activity):
            scheduler.run_due()

    def test_idempotent_job_failure_is_retried_hourly_and_told_once_a_day(self):
        self.run_housekeeping_pass()
        self.assertIsNone(self.setting("job.housekeeping.last_run"))
        notes = self.notices()
        self.assertEqual(len(notes), 1)   # one admin in the harness
        self.assertEqual(notes[0]["title"], "Odin's nightly housekeeping (purge and retention) failed")
        self.assertIn("locked", notes[0]["body"])
        self.assertIn("after 60 minutes", notes[0]["body"])
        self.assertEqual(notes[0]["link"], "/settings/audit")
        with patch("scheduler.due_jobs", return_value=["housekeeping"]):   # the next minute: inside the hour
            self.assertEqual(scheduler.run_due(), [])
        self.sql("UPDATE settings SET value = ? WHERE key = 'job.housekeeping.last_try'", (datetime.utcnow() - timedelta(hours=2)).isoformat())
        self.run_housekeeping_pass()   # retried, fails again, but today's notice stands
        self.assertEqual(len(self.notices()), 1)
        self.sql("UPDATE settings SET value = '2020-01-01' WHERE key = 'scheduler.notified.housekeeping'")
        self.sql("UPDATE settings SET value = ? WHERE key = 'job.housekeeping.last_try'", (datetime.utcnow() - timedelta(hours=2)).isoformat())
        self.run_housekeeping_pass()   # the next day it is told again
        self.assertEqual(len(self.notices()), 2)

    def test_failed_backup_counts_as_done_for_the_day_and_is_not_rerun(self):
        """Each retry writes a full archive (and re-uploads to healthy cloud destinations)."""
        self.run_backup_pass((False, "OneDrive failed: boom"))
        today = self.setting("job.backup.last_run")
        self.assertTrue(today)
        notes = self.notices()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["title"], "Odin's scheduled backup failed")
        self.assertIn("boom", notes[0]["body"])
        self.assertIn("does not retry it today", notes[0]["body"])
        self.assertEqual(notes[0]["link"], "/settings/backups")
        self.assertEqual(notes[0]["kind"], "ops")
        # the real due check (not the patch) does not offer it again today, hour after hour
        now = datetime.fromisoformat(today + "T23:00:00")
        times = {"backup_time": "00:00", "digest_time": "00:00", "report_time": "00:00"}
        days = {k: scheduler.EVERY_DAY for k in ("working_days", "backup_days", "report_days")}
        self.assertNotIn("backup", scheduler.due_jobs(now, {"backup": today}, times, days))

    def test_digest_is_marked_done_before_it_sends_so_a_failure_cannot_resend(self):
        with patch("scheduler.due_jobs", return_value=["digest"]), patch("send_daily_alerts.main", side_effect=RuntimeError("teams down")):
            scheduler.run_due()
        self.assertTrue(self.setting("job.digest.last_run"))
        self.assertIn("teams down", self.notices()[0]["body"])   # still reported

    def test_a_crashing_job_counts_as_failed_and_a_retry_that_works_is_done(self):
        with patch("scheduler.due_jobs", return_value=["housekeeping"]), patch("services.retention.run_audit_retention", side_effect=OSError("disk full")), \
             patch("services.activity.trim", new=lambda: None):
            scheduler.run_due()
        self.assertIsNone(self.setting("job.housekeeping.last_run"))
        self.assertIn("disk full", self.notices()[0]["body"])
        self.sql("UPDATE settings SET value = ? WHERE key = 'job.housekeeping.last_try'", (datetime.utcnow() - timedelta(hours=2)).isoformat())
        with patch("scheduler.due_jobs", return_value=["housekeeping"]), patch("services.retention.run_audit_retention", return_value=(0, None)):
            scheduler.run_due()
        self.assertTrue(self.setting("job.housekeeping.last_run"))

    def test_housekeeping_step_failure_fails_the_job(self):
        self.run_housekeeping_pass()
        self.assertIsNone(self.setting("job.housekeeping.last_run"))
        self.assertIn("locked", self.notices()[0]["body"])

    def test_stale_limit_follows_the_backup_schedule(self):
        limit = lambda *d: scheduler.stale_backup_limit(d).days
        self.assertEqual(limit("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), 2)
        self.assertEqual(limit("Mon", "Tue", "Wed", "Thu", "Fri"), 4)   # Fri to Mon is 3 days
        self.assertEqual(limit("Sun"), 8)
        self.assertEqual(limit("Wed", "Sun"), 5)                        # Sun to Wed is 3 days, Wed to Sun 4

    def test_weekly_schedule_has_no_false_stale_alarm(self):
        when = lambda days: (datetime.utcnow() - timedelta(days=days)).isoformat()
        self._set_policy(backup_days="Sun")
        self.sql("INSERT INTO backup_runs (started_at, finished_at, trigger, file, ok) VALUES (?, ?, 'schedule', 'x.zip', 1)", when(6), when(6))
        with patch("scheduler.due_jobs", return_value=[]):
            scheduler.run_due()
            self.assertEqual(self.notices("Odin has no recent good backup"), [])   # 6 days on a Sunday-only schedule is fine
            self.sql("UPDATE backup_runs SET finished_at = ?", when(9))
            scheduler.run_due()
        stale = self.notices("Odin has no recent good backup")
        self.assertEqual(len(stale), 1)
        self.assertIn("9 days old", stale[0]["body"])
        self.assertIn("Sun", stale[0]["body"])

    def test_stale_backup_notice_once_a_day(self):
        def backup_run(age_days, ok=1):
            when = (datetime.utcnow() - timedelta(days=age_days)).isoformat()
            self.sql("INSERT INTO backup_runs (started_at, finished_at, trigger, file, ok) VALUES (?, ?, 'schedule', 'x.zip', ?)", when, when, ok)
        stale = lambda: self.notices("Odin has no recent good backup")
        with patch("scheduler.due_jobs", return_value=[]):
            backup_run(1)
            scheduler.run_due()
            self.assertEqual(stale(), [])        # a day old is fine
            backup_run(3)
            self.sql("DELETE FROM backup_runs WHERE finished_at > ?", (datetime.utcnow() - timedelta(days=2)).isoformat())
            backup_run(0, ok=0)                  # a recent FAILED run does not make it fresh
            scheduler.run_due()
            scheduler.run_due()
            self.assertEqual(len(stale()), 1)
            self.assertEqual(stale()[0]["link"], "/settings/backups")
            self.assertEqual(stale()[0]["kind"], "ops")

    def test_sigterm_skips_the_remaining_jobs_without_penalty(self):
        scheduler._stopping = True
        with patch("scheduler.due_jobs", return_value=["backup", "digest"]), patch("backup.run_backup") as run:
            scheduler.run_due()
        self.assertEqual(run.call_count, 0)
        self.assertIsNone(self.setting("job.backup.last_try"))   # not held back for an hour
        self.assertIsNone(self.setting("job.backup.last_run"))

    # ---- backup integrity and scheduler robustness (review 18 Oct 2026) ----------

    def test_backup_is_written_under_a_partial_name_and_leftovers_are_removed(self):
        with patch.object(db_module, "DATA_DIR", tempfile.mkdtemp()):
            folder = backup._backup_dir()
            open(os.path.join(folder, ".partial-odin-backup-20260101-020000.zip"), "w").close()   # a killed run's leftover
            seen, writestr = [], zipfile.ZipFile.writestr
            def spy(zf, *a, **kw):   # mid-write: only the temporary name exists
                seen.append(sorted(n for n in os.listdir(folder) if n.endswith(".zip")))
                return writestr(zf, *a, **kw)
            with patch("zipfile.ZipFile.writestr", spy):
                ok, message = backup.run_backup(local_only=True)
            self.assertTrue(ok, message)
            self.assertEqual(len(seen[0]), 1)
            self.assertTrue(seen[0][0].startswith(".partial-odin-backup-"))
            names = [n for n in os.listdir(folder) if n.endswith(".zip")]
            self.assertEqual(len(names), 1)
            self.assertTrue(names[0].startswith("odin-backup-"))
            with patch("zipfile.ZipFile.writestr", side_effect=OSError("disk full")):   # a failed write leaves nothing behind
                ok, message = backup.run_backup(local_only=True)
            self.assertFalse(ok)
            self.assertEqual([n for n in os.listdir(folder) if n.endswith(".zip")], names)

    def test_pre_update_backups_have_their_own_name_and_keep_the_newest_three(self):
        with patch.object(db_module, "DATA_DIR", tempfile.mkdtemp()):
            folder = backup._backup_dir()
            pre = [f"odin-preupdate-2026101{d}-020000.zip" for d in range(5)]
            for name in pre + ["odin-backup-20261014-010000.zip"]:
                open(os.path.join(folder, name), "w").close()
            ok, message = backup.run_backup(trigger=backup.PRE_UPDATE_TRIGGER, local_only=True)
            self.assertTrue(ok, message)
            made = sorted(n for n in os.listdir(folder) if n.startswith("odin-preupdate-"))
            self.assertEqual(len(made), 3)
            self.assertEqual(made[:2], pre[3:])   # the two newest old ones and the one just made
            ok, message = backup.run_backup(local_only=True)   # a later backup the same day
            self.assertTrue(ok, message)
            self.assertEqual(sorted(n for n in os.listdir(folder) if n.startswith("odin-preupdate-")), made)   # never prunes them
            self.assertIsNone(backup._stamp(made[-1]))   # outside daily/weekly/monthly retention

    def test_the_weekly_report_is_queued_never_mailed_from_the_clock_thread(self):
        """Sim B3: the report sent one mail per recipient inline in the clock thread, and an address that
        failed was never tried again. Its mail goes through the outbox now, retried like any other."""
        self._set_policy(report_enabled="1", report_teams="1", report_emails="boss@corp.example",
                         teams_webhook_url="https://hook.example/x", report_attach="0")
        with patch("scheduler.due_jobs", return_value=["report"]), patch("graph.send_mail") as mail, \
             patch("graph.post_teams_webhook", return_value=(True, None)) as hook:
            scheduler.run_due()
        mail.assert_not_called()
        self.assertEqual(hook.call_count, 1)
        self.assertTrue(self.setting("job.report.last_run"))
        self.assertEqual([__import__("json").loads(r[0])["to"] for r in self.sql("SELECT payload FROM outbox WHERE kind = 'mail'")], ["boss@corp.example"])
        self.ctx()
        from services import outbox
        with patch("graph.send_mail", return_value=(False, "mailbox gone")):
            outbox.drain()
        self.assertEqual(self.tuples("SELECT attempts, sent_at IS NULL, next_try_at IS NOT NULL FROM outbox"), [(1, 1, 1)])   # tried again later

    def test_a_stuck_clock_loop_is_told_once_a_day(self):
        stuck = lambda: self.notices("Odin's schedule has stopped")
        with patch("scheduler.due_jobs", return_value=[]):
            scheduler.run_due()   # stamps the loop
        scheduler.check_loop()
        self.assertEqual(stuck(), [])
        self.sql("UPDATE settings SET value = ? WHERE key = ?", (datetime.utcnow() - timedelta(hours=4)).isoformat(), scheduler.LOOP)
        with patch.object(scheduler, "STARTED", datetime.utcnow()):   # just restarted: the old stamp is not a hang
            scheduler.check_loop()
        self.assertEqual(stuck(), [])
        scheduler.check_loop()
        scheduler.check_loop()
        self.assertEqual(len(stuck()), 1)
        self.assertEqual(stuck()[0]["kind"], "ops")
        self._set_policy(scheduler_stuck_hours="6")
        self.sql("DELETE FROM settings WHERE key = 'scheduler.notified.loop_stuck'")
        scheduler.check_loop()
        self.assertEqual(len(stuck()), 1)   # the threshold is the admin's

    def test_ai_jobs_left_running_are_failed_at_start(self):
        from services.ai.health import fail_interrupted
        now = datetime.utcnow().isoformat()
        for status in ("running", "cancelling", "queued"):
            self.sql("INSERT INTO ai_jobs (kind, status, created_at, started_at) VALUES ('feature', ?, ?, ?)", status, now, now)
        with db_module.sqlite3.connect(db_module.DB_PATH) as con:
            fail_interrupted(con)
        self.assertEqual(self.tuples("SELECT status, error FROM ai_jobs ORDER BY id"),
                         [("failed", "interrupted"), ("failed", "interrupted"), ("queued", None)])

    def test_a_crashing_grader_fails_its_feature_and_is_recorded(self):
        from services.ai import health
        def grader(inputs, out):
            raise KeyError("summary")
        feature = SimpleNamespace(key="fake", fixture=lambda: {}, graders=(grader,), budget_s=None)
        with patch("services.ai.health.run", return_value=({}, {"seconds": 1, "model": "m", "prompt_hash": "h"})), \
             patch("services.ai.health.prompt_of", return_value=("p", "h")), db_module.sqlite3.connect(db_module.DB_PATH) as con:
            self.assertEqual(health.validate_feature(con, feature, {"model": "m"}, "fp"), "failed")
        self.assertEqual(self.tuples("SELECT feature, state, fingerprint FROM ai_checks"), [("fake", "failed", "fp")])
        self.assertIn("KeyError", self.sql("SELECT detail FROM ai_checks")[0][0])


if __name__ == "__main__":
    unittest.main()
