"""v1.8.0 operations, data safety and performance (review P2-14, P2-16, P3-5,
P3-25 to P3-31, advice A7 to A9, A23). The updater itself has its own shell
check: sh deploy/test-odin-update.sh. Run with: python -m unittest test_v18_ops"""
import contextlib
import io
import os
import sqlite3
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import scheduler
from test_app import app_module, db_module
from test_fix_logic import FixBase


class OpsBase(FixBase):
    def setUp(self):
        super().setUp()
        self.data = tempfile.mkdtemp()
        p = patch.object(db_module, "DATA_DIR", self.data)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(setattr, scheduler, "_stopping", False)

    def setting(self, key):
        rows = self.sql("SELECT value FROM settings WHERE key = ?", key)
        return rows[0][0] if rows else None

    def ops_notices(self):
        return self.sql("SELECT title, body, link FROM notifications WHERE kind = 'ops' ORDER BY id")


class ResetBackupTestCase(OpsBase):
    def test_the_pre_reset_copy_keeps_rows_still_in_the_wal(self):
        """P2-16: a file copy of odin.db alone had none of 100 committed rows."""
        import reset_data
        self.new_project()
        held = sqlite3.connect(db_module.DB_PATH)   # an open reader keeps the WAL from being folded back on close
        held.execute("SELECT 1").fetchone()
        writer = sqlite3.connect(db_module.DB_PATH)
        writer.execute("PRAGMA journal_mode = WAL")
        writer.executemany("INSERT INTO status_notes (project_id, stage, note, author, created_at) VALUES (1, 'x', ?, 't', '2026-10-01')",
                           [(f"n{i}",) for i in range(100)])
        writer.commit(); writer.close()
        with patch.object(reset_data, "DB_PATH", db_module.DB_PATH), patch.object(reset_data, "UPLOAD_DIR", tempfile.mkdtemp()), \
                patch.object(sys, "argv", ["reset_data.py", "--yes"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reset_data.main(), 0)
        held.close()
        copy = sqlite3.connect(db_module.DB_PATH + ".pre-reset.bak")
        self.addCleanup(os.remove, db_module.DB_PATH + ".pre-reset.bak")
        self.assertGreaterEqual(copy.execute("SELECT COUNT(*) FROM status_notes").fetchone()[0], 100)
        copy.close()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM status_notes")[0][0], 0)


class BackupTestCase(OpsBase):
    def test_archives_are_owner_only(self):
        """P3-5: a zip holds the database and every guest token."""
        import backup
        ok, message = backup.run_backup(trigger="test", local_only=True)
        self.assertTrue(ok, message)
        folder = os.path.join(self.data, "backups")
        self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)
        zips = [n for n in os.listdir(folder) if n.endswith(".zip")]
        self.assertEqual(len(zips), 1)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(folder, zips[0])).st_mode), 0o600)

    def test_back_up_now_is_queued_for_the_scheduler(self):
        """P3-29: the web worker only asks; the scheduler's next pass runs it once."""
        c, csrf = self._api_client()
        with patch("backup.run_backup", side_effect=AssertionError("never in the request")):
            r = c.post("/settings/integrations/backup-now", headers={"X-CSRF-Token": csrf, "Accept": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("queued", r.get_data(as_text=True))
        self.assertEqual(self.setting(scheduler.BACKUP_REQUEST), "Admin")
        self.assertEqual(self.sql("SELECT action FROM audit_logs WHERE action = 'backup_now'")[0][0], "backup_now")
        with patch("backup.run_backup", return_value=(False, "share is not mounted")) as run:
            scheduler.run_requested_backup()
            scheduler.run_requested_backup()   # asked once, run once
        run.assert_called_once_with(trigger="manual", actor="Admin")
        self.assertIsNone(self.setting(scheduler.BACKUP_REQUEST))
        self.assertEqual(self.ops_notices()[0]["title"], "Odin's backup (Back up now) failed")


class SchedulerOpsTestCase(OpsBase):
    def test_updater_notices_reach_the_admins_once(self):
        """A8: deploy/odin-update.sh appends to DATA_DIR/ops-notices; the next pass tells the bell."""
        with open(os.path.join(self.data, "ops-notices"), "w") as f:
            f.write("The update to Odin v1.8.0 failed and the server went back to v1.7.1.\n\n"
                    "ROLLBACK FAILED: the update to Odin v1.8.1 failed and going back to v1.7.1 failed too.\n")
        scheduler.read_ops_notices()
        scheduler.read_ops_notices()
        notes = self.ops_notices()
        self.assertEqual([n["title"] for n in notes], ["Odin's update failed", "Odin's update failed and so did the rollback"])
        self.assertIn("v1.8.0", notes[0]["body"])
        self.assertFalse(os.path.exists(os.path.join(self.data, "ops-notices")))

    def test_low_disk_is_told_once_a_day(self):
        """A9: below disk_free_min_pct (10 by default) the admins hear it, once a day."""
        usage = __import__("shutil")._ntuple_diskusage(100 * 2**30, 95 * 2**30, 5 * 2**30)
        con = sqlite3.connect(db_module.DB_PATH)
        with patch("shutil.disk_usage", return_value=usage):
            scheduler.check_disk(con)
            scheduler.check_disk(con)
        con.close()
        notes = self.ops_notices()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["title"], "Odin's disk is nearly full")
        self.assertIn("5%", notes[0]["body"])
        self._set_policy(disk_free_min_pct="3")
        self.sql("DELETE FROM settings WHERE key = 'scheduler.notified.disk_low'")
        con = sqlite3.connect(db_module.DB_PATH)
        with patch("shutil.disk_usage", return_value=usage):
            scheduler.check_disk(con)
        con.close()
        self.assertEqual(len(self.ops_notices()), 1)   # 5% free is fine at a 3% threshold

    def test_heartbeat_has_its_own_thread(self):
        """P3-27: the beat does not wait for the job in hand."""
        self.assertFalse(scheduler.healthy())
        naps = []
        def nap(seconds):
            naps.append(seconds)
            scheduler._stopping = True
        with patch.object(scheduler, "_nap", nap):
            scheduler.heartbeat()
        self.assertEqual(naps, [60])
        self.assertTrue(scheduler.healthy())

    def test_housekeeping_trims_what_only_grows(self):
        """P3-26, P3-31: resolved alerts, AI history (stale "new" suggestions too) and
        Teams chats of people gone, by policy; then PRAGMA optimize (A23)."""
        old, recent = (datetime.utcnow() - timedelta(days=400)).isoformat(), datetime.utcnow().isoformat()
        self.new_project()
        self.sql("INSERT INTO alerts (alert_type, project_id, title, created_at, resolved, resolved_at) VALUES ('stale', 1, 'gone', ?, 1, ?)", old, old)
        self.sql("INSERT INTO alerts (alert_type, project_id, title, created_at, resolved, resolved_at) VALUES ('stale', 1, 'cleared lately', ?, 1, ?)", old, recent)
        self.sql("INSERT INTO alerts (alert_type, project_id, title, created_at) VALUES ('project_overdue', 1, 'still open', ?)", old)
        cols = {r[1] for r in self.sql("PRAGMA table_info(ai_suggestions)")}
        self.assertIn("status", cols)
        self.sql("UPDATE users SET email = 'admin@example.com'")
        for key in ("teams_conv:admin@example.com", "teams_conv:left@example.com"):
            self.sql("INSERT INTO settings (key, value) VALUES (?, 'conv')", key)
        with app_module.app.app_context():
            db_module.trim_settled()
            db_module.optimize()
        self.assertEqual([r[0] for r in self.sql("SELECT title FROM alerts ORDER BY id")], ["cleared lately", "still open"])
        self.assertEqual([r[0] for r in self.sql("SELECT key FROM settings WHERE key LIKE 'teams_conv:%'")], ["teams_conv:admin@example.com"])

    def test_ai_history_follows_its_policy(self):
        from services.ai.health import trim
        self.new_project()
        stamp = (datetime.utcnow() - timedelta(days=40)).isoformat()
        self.sql("INSERT INTO ai_calls (at, ok) VALUES (?, 1)", stamp)
        with app_module.app.app_context():
            trim()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM ai_calls")[0][0], 1)   # 90 days by default
        self._set_policy(ai_keep_days="30")
        with app_module.app.app_context():
            trim()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM ai_calls")[0][0], 0)


class HealthTestCase(OpsBase):
    def test_reports_the_database_the_scheduler_and_the_disk(self):
        r = app_module.app.test_client().get("/healthz")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertTrue(body.startswith("ok\n"))
        self.assertIn("database: writable", body)
        self.assertIn("scheduler: no heartbeat yet", body)   # reported, never a 503
        self.assertIn("% free", body)
        scheduler.beat()
        self.assertIn("scheduler: last beat", app_module.app.test_client().get("/healthz").get_data(as_text=True))

    def test_a_database_that_cannot_be_written_is_down(self):
        """P3-26: SELECT 1 passed on a read-only volume."""
        os.chmod(db_module.DB_PATH, 0o444)
        try:
            r = app_module.app.test_client().get("/healthz")
        finally:
            os.chmod(db_module.DB_PATH, 0o644)
        self.assertEqual(r.status_code, 503)
        self.assertIn("cannot be read or written", r.get_data(as_text=True))


class RequestIdTestCase(OpsBase):
    def test_every_reply_carries_an_id_and_a_500_quotes_it(self):
        """A7: the id in the reply header, the log line and the 500's words."""
        c = app_module.app.test_client()
        mine = c.get("/healthz").headers["X-Request-Id"]
        self.assertRegex(mine, r"^[0-9a-f]{16}$")
        self.assertEqual(c.get("/healthz", headers={"X-Request-Id": "cf-ray-1234abcd"}).headers["X-Request-Id"], "cf-ray-1234abcd")
        self.assertNotEqual(c.get("/healthz", headers={"X-Request-Id": "bad id; forged"}).headers["X-Request-Id"], "bad id; forged")
        admin, _ = self._api_client()

        def boom():
            raise RuntimeError("kaput")
        with patch.dict(app_module.app.view_functions, {"api_notifications": boom}), \
                patch.dict(app_module.app.config, {"PROPAGATE_EXCEPTIONS": False}), \
                self.assertLogs(app_module.app.logger, "ERROR") as logs:
            r = admin.get("/api/notifications")
        self.assertEqual(r.status_code, 500)
        ref = r.headers["X-Request-Id"]
        self.assertEqual(r.get_json()["ref"], ref)
        self.assertIn(f"Reference: {ref}", r.get_json()["error"])
        self.assertIn("kaput", "\n".join(logs.output))


class PreflightUpdateTestCase(OpsBase):
    def test_settings_only_warn_when_the_updater_asks(self):
        """P2-14: a release must not roll back over the public address an admin has not set."""
        import preflight
        env = {"SECRET_KEY": "k" * 64, "PMS_HTTPS": "1", "PMS_TRUST_PROXY": "1"}
        self.sql("UPDATE users SET password_hash = 'x'")
        for update, code in ((False, 1), (True, 0)):
            out = io.StringIO()
            with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out):
                self.assertEqual(preflight.main(update=update), code, out.getvalue())
            self.assertIn("[WARN] Public web address" if update else "[FAIL] Public web address", out.getvalue())
        with patch.dict(os.environ, {**env, "SECRET_KEY": ""}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(preflight.main(update=True), 1)   # what a build or the environment breaks still fails


class PerformanceTestCase(OpsBase):
    def test_a_saved_time_zone_is_cheap_to_read(self):
        """P3-25: each read listed every zone on disk; the Gantt reads it per date."""
        from policies import policy
        self._set_policy(timezone="Asia/Dubai")
        with app_module.app.test_request_context():
            start = time.perf_counter()
            for _ in range(3000):
                self.assertEqual(policy("timezone"), "Asia/Dubai")
            self.assertLess(time.perf_counter() - start, 2)

    def test_notifications_page_backwards(self):
        """P3-25: the bell lists 40 and can ask for the ones before."""
        stamp = datetime.utcnow().isoformat()
        for i in range(45):
            self.sql("INSERT INTO notifications (user_id, kind, title, created_at) VALUES (1, 'note', ?, ?)", f"n{i}", stamp)
        c, _ = self._api_client()
        first = c.get("/api/notifications").get_json()
        self.assertEqual((len(first["rows"]), first["more"], first["unread"]), (40, True, 45))
        rest = c.get(f"/api/notifications?before_id={first['rows'][-1]['id']}").get_json()
        self.assertEqual((len(rest["rows"]), rest["more"]), (5, False))
        self.assertEqual(rest["rows"][0]["title"], "n4")
        self.assertEqual(len(c.get("/api/notifications?limit=500").get_json()["rows"]), 45)   # capped at 100

    def test_the_dashboard_version_moves_on_writes_only(self):
        """Sim B2: the change check was MAX(audit_logs.id), so a sign-in, a download or a theme change
        rebuilt every open dashboard. Read-only actions (routes/api.READ_ONLY_ACTIONS) no longer move it."""
        import glob
        import re
        from routes.api import READ_ONLY_ACTIONS
        c, _ = self._api_client()
        version = lambda: c.get("/api/dashboard/version").get_json()["version"]   # noqa: E731
        before = version()
        for action in ("login_success", "download_report", "change_own_appearance", "logout"):
            self.sql("INSERT INTO audit_logs (username, action, timestamp) VALUES ('pm', ?, ?)", action, datetime.utcnow().isoformat())
        self.assertEqual(version(), before)
        self.sql("INSERT INTO audit_logs (username, action, timestamp) VALUES ('pm', 'add_task', ?)", datetime.utcnow().isoformat())
        self.assertGreater(version(), before)
        # each name is an action the code really writes: a renamed action must not slip back into the change check unnoticed
        source = "".join(open(f, encoding="utf-8").read() for f in glob.glob("*.py") + glob.glob("routes/*.py") + glob.glob("services/**/*.py", recursive=True)
                         if not os.path.basename(f).startswith("test_"))
        written = set(re.findall(r'audit_log\(\s*"([a-z_]+)"', source))
        self.assertEqual([a for a in READ_ONLY_ACTIONS if a not in written], [])

    def statements(self, url):
        """The SQL statements one GET runs (a trace on every connection opened meanwhile)."""
        seen, connect = [], sqlite3.connect
        def traced(*a, **k):
            con = connect(*a, **k)
            con.set_trace_callback(seen.append)
            return con
        with patch("sqlite3.connect", traced):
            self.assertEqual(self.client.get(url).status_code, 200)
        return seen

    def test_the_flow_reads_stage_gates_in_a_fixed_number_of_statements(self):
        """Sim B1: with any stage gate set, /api/flow ran gates.blocked per rollout (3.8 statements each:
        478 at 150 rollouts). preload() reads tasks, documents and categories once for the board."""
        def board(n):
            for i in range(n):
                self.new_project(name=f"Gated {i}", client="C")
            self.sql("UPDATE project_stages SET gate_tasks = 1, required_docs = '[\"Client PO\"]'")
            self.sql("INSERT INTO tasks (project_id, title, created_at) SELECT id, 'Open', ? FROM projects", datetime.utcnow().isoformat())
            return len(self.statements("/api/flow"))
        few = board(2)
        many = board(8)   # ten rollouts now
        self.assertEqual(many, few)
        rows = self.client.get("/api/flow").get_json()["rows"]
        self.assertTrue(all(r["gate_blocked"] for r in rows))
        self.assertIn("1 open task", rows[0]["gate_reasons"])
        # and the dashboard names the stages once, not once per stage on the board (12 calls per request)
        self.assertEqual(sum("GROUP BY name ORDER BY MIN(position)" in s for s in self.statements("/api/dashboard")), 1)

    def test_tasks_done_count_on_the_workspace_day(self):
        """P3-29: 22:30 UTC is already tomorrow in Dubai."""
        from policies import local_today
        self._set_policy(timezone="Asia/Dubai")
        self.new_project()
        with app_module.app.test_request_context():
            today = local_today()
        late_utc = datetime.combine(today - timedelta(days=1), datetime.min.time()) + timedelta(hours=22, minutes=30)
        self.sql("INSERT INTO tasks (project_id, title, done, done_at, created_at) VALUES (1, 't', 1, ?, ?)", late_utc.isoformat(), late_utc.isoformat())
        c, _ = self._api_client()
        days = {d["day"]: d["count"] for d in c.get("/api/dashboard").get_json()["data"]["completion"]}
        self.assertEqual((days[today.isoformat()], days[(today - timedelta(days=1)).isoformat()]), (1, 0))


class LimitsTestCase(OpsBase):
    def test_join_attempts_follow_the_policy(self):
        """P3-31: the sign-up page's limit is the admin's number."""
        self._set_policy(join_attempts="1")
        c = app_module.app.test_client()
        codes = [c.post("/api/join/no-such-link", json={}).status_code for _ in range(2)]
        self.assertNotEqual(codes[0], 429)
        self.assertEqual(codes[1], 429)

    def test_documents_are_read_in_a_child_with_a_time_limit(self):
        """P3-29: a file that would stall the reader is given up on, not waited for."""
        import subprocess
        from services.doctext import extract_isolated
        path = os.path.join(self.data, "plan.txt")
        with open(path, "w") as f:
            f.write("Cut-over weekend plan")
        self.assertEqual(extract_isolated(path, "txt"), ("Cut-over weekend plan", None))
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("python", 60)):
            self.assertEqual(extract_isolated(path, "txt"), ("", "took more than 60 seconds to read"))


if __name__ == "__main__":
    import unittest
    unittest.main()
