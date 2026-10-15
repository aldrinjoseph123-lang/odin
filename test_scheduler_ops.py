"""Scheduler reliability (review P2-13): a job is marked done only when it
completed, a failure is retried no more than hourly, and admins hear about it
in the bell once a day. Run with: python -m unittest test_scheduler_ops"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import scheduler
from test_fix_logic import FixBase


class SchedulerOpsTestCase(FixBase):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, scheduler, "_stopping", False)

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


if __name__ == "__main__":
    unittest.main()
