"""Business-logic fixes (time in stage, plan, counts, sign-off, lifecycle,
data integrity). Run with: python -m unittest test_fix_logic"""
import unittest
from datetime import datetime, timedelta

import test_app
from test_app import app_module



class FixBase(unittest.TestCase):
    """The shared harness of test_app, without inheriting its tests (a
    TestCase bound at module level would run here too)."""
    _Meta = test_app.ContactsAndProjectMetaTestCase
    setUp = _Meta.setUp
    tearDown = _Meta.tearDown
    new_project = _Meta.new_project
    raw_db = _Meta.raw_db
    _api_client = _Meta._api_client
    _set_policy = _Meta._set_policy
    _invite = _Meta._invite
    _link_for = _Meta._link_for
    _external_client = _Meta._external_client

    def ctx(self):
        c = app_module.app.test_request_context()
        c.push()
        self.addCleanup(c.pop)

    def sql(self, query, *args):
        with self.raw_db() as db:
            rows = db.execute(query, args).fetchall()
            db.commit()
        return rows

    def stages(self, pid=1):
        return [r[0] for r in self.sql("SELECT name FROM project_stages WHERE project_id = ? ORDER BY position", pid)]


class TimeInStageTestCase(FixBase):
    """L1: only the hours on working days count, so the SLA clock never runs backwards."""

    def _days(self, entered, now):
        from services.analytics import days_in_stage
        self.ctx()
        return days_in_stage(entered, now)

    def test_weekend_never_runs_the_clock_backwards(self):
        self._set_policy(timezone="UTC")
        thu = "2026-11-26T10:00:00"   # a Thursday
        fri_late = self._days(thu, datetime(2026, 11, 27, 23))
        sat_early = self._days(thu, datetime(2026, 11, 28, 1))
        sun = self._days(thu, datetime(2026, 11, 29, 16))
        self.assertAlmostEqual(fri_late, 37 / 24, places=3)          # 1.54: breached a 1-day SLA
        self.assertAlmostEqual(sat_early, 38 / 24, places=3)         # not cleared: Friday's last hour, nothing more
        self.assertAlmostEqual(sun, sat_early, places=6)             # the weekend adds nothing
        self.assertAlmostEqual(self._days("2026-11-28T10:00:00", datetime(2026, 11, 30, 10)), 10 / 24, places=3)   # Sat → Mon: 0.42

    def test_sla_breach_fires_once_across_a_weekend(self):
        from services.analytics import stage_sla_state
        self._set_policy(timezone="UTC")
        self.ctx()
        p = {"stage": "Kickoff", "stage_entered_at": "2026-11-26T10:00:00"}
        seen = [stage_sla_state(p, {"Kickoff": 1}, "Closed", now=datetime(2026, 11, 27, 10) + timedelta(hours=h))["breached"] for h in range(0, 80, 3)]
        self.assertEqual(seen[0], False)
        self.assertEqual(seen.index(True), 1)
        self.assertTrue(all(seen[1:]))   # once breached, it stays breached

    def test_cycle_times_and_sla_from_measured_count_working_days(self):
        from services.analytics import build_cycle_times, clock
        self._set_policy(timezone="UTC")
        self.ctx()
        project = {"id": 1, "name": "P", "stage": "B", "created_at": "2026-11-27T00:00:00", "updated_at": "2026-11-27T00:00:00"}
        notes = [{"stage": "B", "created_at": "2026-12-01T00:00:00"}]   # Fri → Tue: 4 calendar days, 2 working
        stats = build_cycle_times([project], {1: notes}, ["A", "B", "C"], "C", now=datetime(2026, 12, 1), clock=clock())
        self.assertAlmostEqual(stats["stages"][0]["avg_days"], 2.0, places=3)


class FlowAndPlanAgreeTestCase(FixBase):
    """L2/L4/P19/L16: the Flow, the project flow, the plan and the report read one clock."""

    def test_current_stage_measured_from_this_visit(self):
        self.new_project(name="R", client="C")
        s = self.stages()
        c, _ = self._api_client()
        h = {"X-CSRF-Token": c.get("/api/session").get_json()["csrf"]}
        c.post("/api/projects/1/stage", json={"stage": s[1]}, headers=h)
        c.post("/api/projects/1/stage", json={"stage": s[0]}, headers=h)   # back again: a revisit
        # the first visit was long ago; this one began two days back
        self.sql("UPDATE projects SET created_at = datetime('now', '-40 days'), stage_entered_at = strftime('%Y-%m-%dT%H:%M:%S', 'now', '-2 days') WHERE id = 1")
        self.sql("UPDATE status_notes SET created_at = strftime('%Y-%m-%dT%H:%M:%S', 'now', '-30 days') WHERE id = (SELECT MIN(id) FROM status_notes)")
        self.sql("UPDATE status_notes SET created_at = strftime('%Y-%m-%dT%H:%M:%S', 'now', '-2 days') WHERE id = (SELECT MAX(id) FROM status_notes)")
        plan = c.get("/api/projects/1/plan").get_json()
        cur = next(x for x in plan["stages"] if x["status"] == "current")
        row = c.get("/api/flow").get_json()["rows"][0]
        detail = c.get("/api/projects/1/flow").get_json()["stages"][0]
        self.assertAlmostEqual(cur["actual_days"], row["days_in_stage"], delta=0.1)
        self.assertAlmostEqual(detail["days"], row["days_in_stage"], delta=0.1)
        self.assertLess(cur["actual_days"], 3)
        self.assertEqual(sum(1 for v in plan["visits"] if v["stage"] == s[0]), 2)   # the revisit is in the history
        dwell = c.get("/api/projects/1/rollout-report").get_json()["data"]["history"]["dwell"]
        self.assertEqual([d["stage"] for d in dwell], [s[0], s[1], s[0]])
        self.assertEqual(dwell[-1]["status"], "current")
        self.assertAlmostEqual(dwell[-1]["days"], row["days_in_stage"], delta=0.1)
        pdf = c.get("/projects/1/report.pdf")
        self.assertEqual(pdf.status_code, 200)

    def test_idle_is_not_flagged_early(self):
        self.new_project(name="I", client="C")
        days = 14
        self.sql("UPDATE alert_type_settings SET threshold_days = ? WHERE alert_type = 'stale'", days)
        # 13.96 days idle rounds to 14.0 but is not yet 14
        self.sql("UPDATE projects SET updated_at = strftime('%Y-%m-%dT%H:%M:%S', 'now', '-13 days', '-23 hours') WHERE id = 1")
        c, _ = self._api_client()
        row = c.get("/api/flow").get_json()["rows"][0]
        self.assertEqual(row["idle_days"], 14.0)
        self.assertFalse(row["stale"])


class CountsAgreeTestCase(FixBase):
    """L10/B8/P4/L20: the tile, the chip and the widget count one state per rollout."""

    def _late_and_over(self):
        self.new_project(name="Both", client="C", target_end_date="2020-01-01")
        self.new_project(name="Over", client="C")
        self.sql("UPDATE project_stages SET sla_days = 1")
        self.sql("UPDATE projects SET stage_entered_at = strftime('%Y-%m-%dT%H:%M:%S', 'now', '-20 days')")

    def test_dashboard_tile_matches_the_flow_chips(self):
        self._late_and_over()
        c, _ = self._api_client()
        flow = c.get("/api/flow").get_json()["counts"]
        kpis = c.get("/api/dashboard").get_json()["data"]["kpis"]
        self.assertEqual((flow["overdue"], flow["over_sla"]), (1, 1))
        self.assertEqual((kpis["counts"]["overdue"], kpis["counts"]["over_sla"]), (1, 1))
        self.assertEqual([r["name"] for r in kpis["detail"]["over_sla"]], ["Over"])
        # today's trend point is the live count, not this morning's snapshot
        self.assertEqual(kpis["series"]["over_sla"][-1]["v"], 1)
        self.sql("UPDATE projects SET stage_entered_at = strftime('%Y-%m-%dT%H:%M:%S', 'now') WHERE name = 'Over'")
        kpis = c.get("/api/dashboard").get_json()["data"]["kpis"]
        self.assertEqual(kpis["counts"]["over_sla"], 0)
        self.assertEqual(kpis["series"]["over_sla"][-1]["v"], 0)
        self.assertEqual(sum(1 for p in kpis["series"]["over_sla"] if p["day"] == kpis["series"]["over_sla"][-1]["day"]), 1)

    def test_my_work_rollouts_carry_the_flow_fields(self):
        self._late_and_over()
        c, _ = self._api_client()
        rows = {r["name"]: r for r in c.get("/api/my-work").get_json()["projects"]}
        self.assertEqual(rows["Over"]["state"], "over_sla")
        self.assertGreater(rows["Over"]["over_by"], 5)
        self.assertGreater(rows["Over"]["days_in_stage"], rows["Over"]["over_by"])
        self.assertEqual(rows["Over"]["sla_days"], 1)
        self.assertEqual(rows["Both"]["target_end_date"], "2020-01-01")

    def test_people_count_moves_by_author_id_not_name(self):
        self.new_project(name="P", client="C")
        c, csrf = self._api_client()
        c.post("/api/projects/1/stage", json={"stage": self.stages()[1]}, headers={"X-CSRF-Token": csrf})
        self.sql("UPDATE users SET name = 'Renamed' WHERE id = 1")   # the note keeps the old name
        self.sql("INSERT INTO users (username, password_hash, name, role, active) VALUES ('twin', 'x', 'Admin', 'Member', 1)")
        me = c.get("/api/people/1").get_json()
        self.assertEqual(me["contribution"]["moves_30d"], 1)
        twin = self.sql("SELECT id FROM users WHERE username = 'twin'")[0][0]
        self.assertEqual(c.get(f"/api/people/{twin}").get_json()["contribution"]["moves_30d"], 0)

    def test_calendar_month_out_of_range_falls_back(self):
        c, _ = self._api_client()
        for bad in ("0001-01", "9999-12", "abc"):
            self.assertEqual(c.get(f"/api/calendar?month={bad}").status_code, 200, bad)


class AlertsTestCase(FixBase):
    """B9/L17/B7/L15: reads stay reads; dismissals have a context; badges equal the pages."""

    def test_board_load_writes_no_alerts(self):
        self.new_project(name="Late", client="C", target_end_date="2020-01-01")
        c, _ = self._api_client()
        c.get("/api/board"); self.client.get("/board")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM alerts")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE kind = 'alert'")[0][0], 0)
        import scheduler
        scheduler.sync_alerts()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM alerts WHERE resolved = 0")[0][0], 1)

    def test_badges_leave_out_deleted_and_closed_projects(self):
        self.new_project(name="Late", client="C", target_end_date="2020-01-01")
        self.new_project(name="Done", client="C")
        c, csrf = self._api_client()
        self.sql("INSERT INTO tasks (project_id, title, assignee_id, created_at) VALUES (2, 'left over', 1, '2026-01-01T00:00:00')")
        import scheduler
        scheduler.sync_alerts()
        nav = lambda: c.get("/api/session").get_json()["user"]["nav"]   # noqa: E731
        self.assertEqual((nav()["active_alert_count"], nav()["my_open_task_count"]), (1, 1))
        self.sql("UPDATE projects SET stage = (SELECT name FROM project_stages WHERE project_id = 2 ORDER BY position DESC LIMIT 1) WHERE id = 2")
        self.sql("UPDATE projects SET deleted_at = strftime('%Y-%m-%dT%H:%M:%S', 'now') WHERE id = 1")
        self.assertEqual((nav()["active_alert_count"], nav()["my_open_task_count"]), (0, 0))
        self.assertEqual(c.get("/api/alerts").get_json()["total"], 0)

    def test_scheduler_quarters(self):
        from scheduler import alert_quarter
        self.assertEqual(alert_quarter(datetime(2026, 1, 1, 10, 16, 59)), datetime(2026, 1, 1, 10, 15))
        self.assertNotEqual(alert_quarter(datetime(2026, 1, 1, 10, 14)), alert_quarter(datetime(2026, 1, 1, 10, 16)))   # a late pass still syncs


class PurgeAndResetTestCase(FixBase):
    """B3/#39/B8: the purge is one transaction in the right order; reset leaves nothing behind."""

    def test_purge_of_a_partner_with_managers_and_signup_pointer(self):
        self.new_project(name="P", client="C")
        old = "2000-01-01T00:00:00"
        self.sql("INSERT INTO partners (name, deleted_at) VALUES ('Gone', ?)", old)
        self.sql("INSERT INTO partner_account_managers (partner_id, name) VALUES ((SELECT id FROM partners WHERE name = 'Gone'), 'Mo')")
        self.sql("UPDATE projects SET deleted_at = ? WHERE id = 1", old)
        self.sql("UPDATE users SET signup_project_id = 1 WHERE id = 1")
        from db import cleanup_soft_deletes, get_db
        with app_module.app.app_context():
            cleanup_soft_deletes()   # foreign keys are on in the app's connection
            get_db().close()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM partners WHERE name = 'Gone'")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM partner_account_managers")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 0)
        self.assertIsNone(self.sql("SELECT signup_project_id FROM users WHERE id = 1")[0][0])

    def test_failed_purge_rolls_back(self):
        self.new_project(name="P", client="C")
        self.sql("UPDATE projects SET deleted_at = '2000-01-01T00:00:00' WHERE id = 1")
        from unittest.mock import patch
        import db as db_module
        with app_module.app.app_context(), patch.object(db_module, "_purge_orphans", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                db_module.cleanup_soft_deletes()
            db_module.get_db().close()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 1)
        self.assertGreater(self.sql("SELECT COUNT(*) FROM project_stages WHERE project_id = 1")[0][0], 0)

    def test_reset_wipes_snapshots_ai_words_and_signup_pointers(self):
        import reset_data
        from unittest.mock import patch
        self.new_project(name="P", client="C")
        self.sql("INSERT INTO portfolio_snapshots (day, active, overdue, over_sla, due_soon, awaiting, idle) VALUES ('2026-01-01', 1, 0, 0, 0, 0, 0)")
        self.sql("INSERT INTO settings (key, value) VALUES ('ai.latest.portfolio_narrative', '{}')")
        self.sql("UPDATE users SET signup_project_id = 1")
        with patch("sys.argv", ["reset_data.py", "--yes"]), patch.object(reset_data, "DB_PATH", test_app.db_module.DB_PATH):
            self.assertEqual(reset_data.main(), 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM portfolio_snapshots")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM settings WHERE key LIKE 'ai.latest.%'")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users WHERE signup_project_id IS NOT NULL")[0][0], 0)

    def test_indexes_exist(self):
        names = {r[0] for r in self.sql("SELECT name FROM sqlite_master WHERE type = 'index'")}
        for n in ("idx_audit_logs_time", "idx_tasks_assignee", "idx_projects_deleted", "idx_signoffs_document"):
            self.assertIn(n, names)


class LifecycleTestCase(FixBase):
    """D8/P7/F-M5/D13/R14/B5/F-H2/P21/L9/B4: stage moves, undo, templates."""

    def _client(self):
        c, csrf = self._api_client()
        return c, {"X-CSRF-Token": csrf}

    def test_undo_retags_later_notes_and_keeps_a_decided_approval(self):
        self.new_project(name="U", client="C", customer_approval="1")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        s = self.stages()
        self.client.post("/api/projects/1/stage", json={"stage": s[1]})
        e = self._external_client("ann@acme.example")
        aid = self.sql("SELECT id FROM stage_approvals WHERE status = 'pending'")[0][0]
        e.post(f"/api/projects/1/approvals/{aid}", json={"decision": "approved"})
        self.client.post("/projects/1/note", data={"note": "after the move"})
        self.assertEqual(self.sql("SELECT stage FROM status_notes WHERE note = 'after the move'")[0][0], s[1])
        move = self.sql("SELECT id FROM status_notes WHERE prev_stage IS NOT NULL")[0][0]
        self.client.post(f"/undo/stage/1/{move}")
        self.assertEqual(self.sql("SELECT stage FROM projects")[0][0], s[0])
        self.assertEqual({r[0] for r in self.sql("SELECT stage FROM status_notes")}, {s[0]})   # no phantom visit
        self.assertEqual(self.sql("SELECT status, decided_by FROM stage_approvals WHERE id = ?", aid)[0][:], ("superseded", "Ann"))

    def test_closing_asks_no_approval_and_supersedes_the_open_one(self):
        self.new_project(name="P", client="C", customer_approval="1")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        self.sql("INSERT INTO settings (key, value) VALUES ('policy.signoff_required', '0')")
        s = self.stages()
        c, h = self._client()
        c.post("/api/projects/1/stage", json={"stage": s[1]}, headers=h)
        self.assertEqual(c.post("/api/projects/1/stage", json={"stage": s[-1]}, headers=h).status_code, 200)
        self.assertEqual([r[0] for r in self.sql("SELECT status FROM stage_approvals ORDER BY id")], ["superseded"])
        # turning customer approval off on edit supersedes an open request
        self.new_project(name="Q", client="C", customer_approval="1")
        self._invite(2, "ann@acme.example", "Customer", "Ann")
        c.post("/api/projects/2/stage", json={"stage": s[1]}, headers=h)
        self.client.post("/projects/2/edit", data={"name": "Q", "client": "C", "owner_id": "1", "delivery_mode": "Distribution/MSSP"})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM stage_approvals WHERE project_id = 2 AND status = 'pending'")[0][0], 0)

    def test_a_stale_move_is_refused_once(self):
        self.new_project(name="P", client="C")
        s = self.stages()
        c, h = self._client()
        import routes.projects as rp
        stale = None
        with app_module.app.test_request_context():
            stale = dict(self.sql("SELECT p.*, 'Admin' AS owner_name FROM projects p")[0])
        c.post("/api/projects/1/stage", json={"stage": s[1]}, headers=h)
        from unittest.mock import patch
        with patch.object(rp, "load_project", return_value=stale):   # the second click read the project before the first moved it
            r = c.post("/api/projects/1/stage", json={"stage": s[2]}, headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("just moved", r.get_json()["error"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM status_notes WHERE prev_stage IS NOT NULL")[0][0], 1)

    def test_templates_keep_two_stages(self):
        tid = 1
        ids = [r[0] for r in self.sql("SELECT id FROM stage_template_stages WHERE template_id = ? ORDER BY position", tid)]
        for sid in ids[:-2]:
            self.client.post(f"/settings/templates/{tid}/stages/{sid}/delete")
        self.assertEqual(len(self.sql("SELECT id FROM stage_template_stages WHERE template_id = ?", tid)), 2)
        self.client.post(f"/settings/templates/{tid}/stages/{ids[-1]}/delete")
        self.assertIn("at least two stages", test_app.flashed(self.client))
        self.assertEqual(len(self.sql("SELECT id FROM stage_template_stages WHERE template_id = ?", tid)), 2)
        # a template cut to one stage outside the app cannot give birth to a closed project
        self.sql("DELETE FROM stage_template_stages WHERE id = ?", ids[-2])
        self.new_project(name="Born closed", client="C")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 0)

    def test_rename_reaches_every_row_naming_the_stage(self):
        self.new_project(name="P", client="C", customer_approval="1")
        self._invite(1, "ann@acme.example", "Customer", "Ann")   # a request opens only when a customer can decide it
        s = self.stages()
        c, h = self._client()
        c.post("/api/projects/1/stage", json={"stage": s[1]}, headers=h)
        c.post("/api/projects/1/raid", json={"kind": "risk", "title": "R", "stage": s[1]}, headers=h)
        sid = self.sql("SELECT id FROM project_stages WHERE project_id = 1 AND name = ?", s[1])[0][0]
        self.client.post(f"/projects/1/stages/{sid}/rename", data={"name": "Renamed"})
        self.assertEqual(self.sql("SELECT stage FROM stage_approvals")[0][0], "Renamed")
        self.assertNotIn(s[1], {r[0] for r in self.sql("SELECT stage FROM raid_items")})

    def test_sla_bounds(self):
        sid = self.sql("SELECT id FROM stage_template_stages WHERE template_id = 1 ORDER BY position")[0][0]
        for bad in ("3000000", str(2 ** 70), "366"):
            self.client.post("/settings/templates/1/sla", data={f"sla::{sid}": bad})
            self.assertIn("between 1 and 365", test_app.flashed(self.client), bad)
        self.client.post("/settings/templates/1/sla", data={f"sla::{sid}": "365"})
        self.assertEqual(self.sql("SELECT sla_days FROM stage_template_stages WHERE id = ?", sid)[0][0], 365)

    def test_stage_sort_follows_the_list(self):
        for n in ("A", "B", "C"):
            self.new_project(name=n, client="C")
        s = self.stages()
        self.sql("UPDATE projects SET stage = ? WHERE name = 'A'", s[2])   # alphabetically these would sort otherwise
        self.sql("UPDATE projects SET stage = ? WHERE name = 'B'", s[0])
        self.sql("UPDATE projects SET stage = ? WHERE name = 'C'", s[1])
        c, _ = self._api_client()
        rows = c.get("/api/projects?sort=stage&dir=asc").get_json()
        names = [r["name"] for r in rows.get("projects", rows.get("rows", []))]
        self.assertEqual(names, ["B", "C", "A"])

    def test_work_resets_idle(self):
        self.new_project(name="P", client="C")
        self.sql("UPDATE projects SET updated_at = '2026-01-01T00:00:00'")
        self.client.post("/projects/1/tasks", data={"title": "t"})
        self.assertGreater(self.sql("SELECT updated_at FROM projects")[0][0], "2026-02")

    def test_undo_delete_restores_only_the_documents_that_went_with_it(self):
        import io
        self.new_project(name="P", client="C")
        self.client.post("/projects/1/documents", data={"category": "Deliverable", "file": (io.BytesIO(b"%PDF-1.4 x"), "x.pdf")}, content_type="multipart/form-data")
        doc = self.sql("SELECT id FROM documents WHERE filename = 'x.pdf'")[0][0]
        self.client.post(f"/projects/1/documents/{doc}/delete")   # deleted on its own, before the project
        self.assertIsNotNone(self.sql("SELECT deleted_at FROM documents WHERE id = ?", doc)[0][0])
        self.client.post("/projects/1/delete")
        self.client.post("/undo/project/1")
        self.assertIsNone(self.sql("SELECT deleted_at FROM projects")[0][0])
        self.assertEqual({r[0]: r[1] is None for r in self.sql("SELECT filename, deleted_at FROM documents")}, {"po.pdf": True, "x.pdf": False})


class TasksTestCase(FixBase):
    """L13/L14/V29."""

    def test_partial_json_edit_keeps_assignee_and_due_date(self):
        self.new_project(name="P", client="C")
        c, csrf = self._api_client()
        h = {"X-CSRF-Token": csrf}
        c.post("/projects/1/tasks", json={"title": "t", "assignee_id": 1, "due_date": "2026-12-01"}, headers=h)
        r = c.post("/projects/1/tasks/1/edit", json={"title": "renamed"}, headers=h)
        self.assertEqual(r.get_json(), {"ok": True})
        self.assertEqual(tuple(self.sql("SELECT title, assignee_id, due_date FROM tasks")[0]), ("renamed", 1, "2026-12-01"))
        self.assertEqual(c.post("/projects/1/tasks/1/edit", json={"due_date": "1/12/2026"}, headers=h).status_code, 400)
        c.post("/projects/1/tasks/1/edit", json={"due_date": None}, headers=h)
        self.assertIsNone(self.sql("SELECT due_date FROM tasks")[0][0])
        details = [r[0] for r in self.sql("SELECT details FROM audit_logs WHERE action IN ('edit_task', 'toggle_task') ORDER BY id")]
        self.assertTrue(details and all("task_id" not in d for d in details))
        c.post("/projects/1/tasks/1/toggle", headers=h)
        self.assertIn("done: renamed", self.sql("SELECT details FROM audit_logs WHERE action = 'toggle_task'")[0][0])

    def test_assignee_may_move_only_their_own_due_date(self):
        self.new_project(name="P", client="C")
        self._invite(1, "kim@vendor.example", "Contractor", "Kim")
        kim = self.sql("SELECT id FROM users WHERE email = 'kim@vendor.example'")[0][0]
        self.client.post("/projects/1/tasks", data={"title": "mine", "assignee_id": str(kim), "due_date": "2026-12-01"})
        self.client.post("/projects/1/tasks", data={"title": "not mine", "due_date": "2026-12-01"})
        e = self._external_client("kim@vendor.example")
        h = {"X-CSRF-Token": e.get("/api/session").get_json()["csrf"]}
        whole = {"title": "mine", "assignee_id": kim, "due_date": "2026-12-15"}   # the page sends the whole task
        self.assertEqual(e.post("/projects/1/tasks/1/edit", json=whole, headers=h).status_code, 200)
        self.assertEqual(self.sql("SELECT due_date FROM tasks WHERE id = 1")[0][0], "2026-12-15")
        self.assertEqual(e.post("/projects/1/tasks/1/edit", json={**whole, "title": "renamed"}, headers=h).status_code, 403)
        self.assertEqual(e.post("/projects/1/tasks/2/edit", json={"due_date": "2026-12-20"}, headers=h).status_code, 403)
        self.assertEqual(self.sql("SELECT title FROM tasks WHERE id = 1")[0][0], "mine")

class SignoffRulesTestCase(FixBase):
    """D5/D6/L12/L19/F-M4/F-M5/F-M7."""

    def _setup(self):
        self.new_project(name="Close me", client="Globex")
        self._invite(1, "ann@globex.example", "Customer", "Ann")
        ann = self.sql("SELECT id FROM users WHERE email = 'ann@globex.example'")[0][0]
        c, csrf = self._api_client()
        return c, {"X-CSRF-Token": csrf}, ann

    def body(self, ann, **extra):
        return {"summary": "Done.", "signer_id": ann, "counter_id": 1, "delivered": ["Everything"], **extra}

    def test_sent_only_from_the_stage_before_the_finish(self):
        c, h, ann = self._setup()
        r = c.post("/api/projects/1/signoff", json=self.body(ann), headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("the stage before", r.get_json()["error"])
        self.sql("UPDATE projects SET stage = ?", self.stages()[-2])
        self.assertEqual(c.post("/api/projects/1/signoff", json=self.body(ann), headers=h).get_json()["version"], 1)
        # a double submit sends one version
        self.assertEqual(c.post("/api/projects/1/signoff", json=self.body(ann), headers=h).status_code, 400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM signoffs")[0][0], 1)

    def test_long_lists_refused_not_cut(self):
        c, h, ann = self._setup()
        self.sql("UPDATE projects SET stage = ?", self.stages()[-2])
        r = c.post("/api/projects/1/signoff", json=self.body(ann, outstanding=[f"item {i}" for i in range(41)]), headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("At most 40", r.get_json()["error"])

    def test_bad_ai_suggestion_writes_nothing(self):
        c, h, ann = self._setup()
        self.sql("UPDATE projects SET stage = ?", self.stages()[-2])
        r = c.post("/api/projects/1/signoff", json=self.body(ann, ai_suggestion={"x": 1}), headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM signoffs")[0][0], 0)

    def test_scope_frozen_while_out_and_paper_date_and_reject_after_sign(self):
        import io
        c, h, ann = self._setup()
        self.sql("UPDATE projects SET stage = ?", self.stages()[-2])
        c.post("/api/projects/1/scope", json={"title": "Sensors", "status": "delivered"}, headers=h)
        c.post("/api/projects/1/signoff", json=self.body(ann), headers=h)
        self.assertEqual(c.post("/api/projects/1/scope", json={"title": "Late"}, headers=h).status_code, 409)
        item = self.sql("SELECT id FROM scope_items")[0][0]
        self.assertEqual(c.put(f"/api/projects/1/scope/{item}", json={"status": "partial", "note": "x"}, headers=h).status_code, 409)
        for day in ("2099-01-01", "2000-01-01"):
            r = c.post("/api/projects/1/signoff/1/upload", data={"signer_name": "Ann", "signed_on": day, "file": (io.BytesIO(b"%PDF-1.4 s"), "s.pdf")},
                       headers=h, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 400, day)
        # the customer signs; a stale reject afterwards changes nothing
        e = self._external_client("ann@globex.example")
        eh = {"X-CSRF-Token": e.get("/api/session").get_json()["csrf"]}
        drawn = {"kind": "drawn", "strokes": [[[100, 150], [200, 100], [300, 200], [400, 120], [500, 180]]]}
        row = self.sql("SELECT * FROM signoffs")[0]
        self.assertEqual(e.post("/api/projects/1/signoff/1/sign", json={"name": "Ann", "accept": True, "signature": drawn}, headers=eh).status_code, 200)
        from services import signoff
        with app_module.app.test_request_context():
            with self.assertRaises(ValueError):
                signoff.reject({"id": 1, "owner_id": 1, "stage": "x"}, row, "too late", "Ann")   # `row` was read while it was still 'sent'
        self.assertEqual(self.sql("SELECT status FROM signoffs")[0][0], "signed")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM raid_items")[0][0], 0)


class ReportPdfAndAITestCase(FixBase):
    """P8/P23/D15/F-H1."""

    def test_one_bad_date_does_not_take_the_pdf_down(self):
        self.new_project(name="P", client="C", customer_approval="1")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        s = self.stages()
        self.client.post("/api/projects/1/stage", json={"stage": s[1]})   # an approval waits on the customer
        self.client.post("/projects/1/tasks", data={"title": "t"})
        self.sql("UPDATE tasks SET due_date = 'not-a-date'")
        self.sql("UPDATE project_stages SET base_start = 'garbage', base_end = '9999-12-31', plan_start = '2026-10-01', plan_end = '9999-12-31' WHERE position = 0")
        pdf = self.client.get("/projects/1/report.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertIn(b"What we need from the customer", pdf.data)   # the internal copy says it too
        c, _ = self._api_client()
        self.assertEqual(c.get("/api/reports/all").status_code, 200)

    def test_plan_dates_outside_the_window_are_refused(self):
        self.new_project(name="P", client="C")
        c, csrf = self._api_client()
        sid = self.sql("SELECT id FROM project_stages WHERE project_id = 1 ORDER BY position")[0][0]
        r = c.put("/api/projects/1/plan", json={"stages": [{"id": sid, "plan_start": "2026-10-01", "plan_end": "9999-12-31"}]}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 400)
        self.assertIn("between 2000 and 2100", r.get_json()["error"])

    def test_plan_reason_warning_and_first_baseline(self):
        self.new_project(name="P", client="C", target_end_date="2026-11-01")
        c, csrf = self._api_client()
        h = {"X-CSRF-Token": csrf}
        sid = self.sql("SELECT id FROM project_stages WHERE project_id = 1 ORDER BY position")[0][0]
        self.assertEqual(c.post("/api/projects/1/plan/baseline", json={"reason": "early"}, headers=h).status_code, 400)   # nothing to baseline (L11)
        r = c.put("/api/projects/1/plan", json={"stages": [{"id": sid, "plan_start": "2026-10-01", "plan_end": "2026-12-01"}]}, headers=h).get_json()
        self.assertTrue(r["baselined"])
        self.assertIn("after the target date", r["warning"])
        self.assertIn("after the target date", c.get("/api/projects/1/plan").get_json()["warning"])
        moved = {"stages": [{"id": sid, "plan_start": "2026-10-02", "plan_end": "2026-12-01"}]}
        self.assertEqual(c.put("/api/projects/1/plan", json=moved, headers=h).get_json()["error"], "Say why the dates move")
        self.assertEqual(c.put("/api/projects/1/plan", json={**moved, "reason": "vendor late"}, headers=h).status_code, 200)

    def test_stale_ai_heartbeat_closes_the_gate(self):
        import json as _json
        from services.ai import gate, status
        for k, v in (("ai_enabled", "1"), ("ai_base_url", "http://192.168.1.238:11434/v1")):
            self.sql("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", f"policy.{k}", v)
        old = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        self.sql("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai.status', ?)", _json.dumps({"state": "up", "checked_at": old, "fingerprint": "m@1"}))
        with app_module.app.test_request_context():
            st = status()
            self.assertTrue(st["stale"])
            self.assertEqual(st["no_heartbeat_since"], old)
            self.assertIn("No heartbeat", gate("anything"))


if __name__ == "__main__":
    unittest.main()


class AIJobProgressTest(test_app.AITestBase):
    """A queued draft tells the page where it stands, so the progress bar is not blind."""
    isolate_features = False
    GOOD = test_app.WeeklyWordsTestCase.GOOD
    _project = test_app.WeeklyWordsTestCase._project
    _ready = test_app.WeeklyWordsTestCase._ready

    def test_queued_job_reports_its_place_and_expected_time(self):
        self._project()
        self._ready()
        with self._db() as con:   # another rollout's draft is already running
            con.execute("INSERT INTO ai_jobs (kind, feature, project_id, status, created_at, started_at) VALUES ('feature', 'weekly_words', NULL, 'running', '2026-10-09T00:00:00', '2026-10-09T00:00:00')")
        self.assertEqual(self.client.post("/api/projects/1/ai/weekly_words", json={}, headers=self._csrf()).status_code, 200)
        job = self.client.get("/api/projects/1/ai/weekly_words").get_json()["job"]
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["progress"]["ahead"], 1)
        self.assertGreater(job["progress"]["expected_s"], 0)          # from the feature's last test
        self.assertIsNone(job["progress"]["started_at"])


class SimulationLogicTestCase(FixBase):
    """The 10 Oct 2026 end-to-end logic simulation."""

    def _move(self, stage, client=None):
        return (client or self.client).post("/api/projects/1/stage", json={"stage": stage}).get_json()

    def _undo(self, undo):
        return self.client.post(undo, headers={"Accept": "application/json"})

    def test_undo_brings_back_only_that_visits_request_and_only_while_asking(self):   # L-1
        self.new_project(name="U", client="C", customer_approval="1")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        s = self.stages()
        self._move(s[1])
        # switched off, then a move and its undo: nothing pending comes back
        self.client.post("/projects/1/edit", data={"name": "U", "client": "C", "via": "Direct", "delivery_mode": "Distribution/MSSP"})
        undo = self._move(s[2])["undo"]
        self._undo(undo)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM stage_approvals WHERE status = 'pending'")[0][0], 0)

    def test_a_decided_visit_is_not_reopened_by_an_undo(self):   # L-1 variant B
        self.new_project(name="U", client="C", customer_approval="1")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        s = self.stages()
        self._move(s[1]); self._move(s[2]); self._move(s[1])
        ann = self._external_client("ann@acme.example")
        aid = self.sql("SELECT id FROM stage_approvals WHERE status = 'pending'")[0][0]
        self.assertEqual(ann.post(f"/api/projects/1/approvals/{aid}", json={"decision": "approved"}).status_code, 200)
        self._undo(self._move(s[2])["undo"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM stage_approvals WHERE status = 'pending'")[0][0], 0)

    def test_no_request_when_nobody_can_decide_it(self):   # L-7
        self.new_project(name="U", client="C", customer_approval="1")
        self._move(self.stages()[1])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM stage_approvals")[0][0], 0)

    def test_reordering_cannot_reopen_a_closed_project(self):   # L-6
        self.new_project(name="P", client="C")
        s = self.stages()
        self.sql("UPDATE projects SET stage = ? WHERE id = 1", s[-1])
        last = self.sql("SELECT id FROM project_stages WHERE project_id = 1 ORDER BY position DESC LIMIT 1")[0][0]
        r = self.client.post(f"/projects/1/stages/{last}/move", data={"direction": "up"}, headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 400); self.assertIn("closed", r.get_json()["error"])
        self.assertEqual(self.stages()[-1], s[-1])

    def test_a_waiver_needs_the_stage_before_the_finish(self):   # L-12
        self.new_project(name="P", client="C")
        c, csrf = self._api_client()
        r = c.post("/api/projects/1/signoff/waive", json={"reason": "Customer signed on paper last week"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 400); self.assertIn("Waive the sign-off once", r.get_json()["error"])

    def test_sla_save_keeps_stages_the_form_does_not_name(self):   # L-26
        self.new_project(name="P", client="C")
        ids = [r[0] for r in self.sql("SELECT id FROM project_stages WHERE project_id = 1 ORDER BY position")]
        self.client.post("/projects/1/stages/sla", data={f"sla::{ids[0]}": "5", f"sla::{ids[1]}": "6"})
        self.client.post("/projects/1/stages/sla", data={f"sla::{ids[0]}": "9"})
        self.assertEqual([r[0] for r in self.sql("SELECT sla_days FROM project_stages WHERE id IN (?, ?) ORDER BY position", ids[0], ids[1])], [9, 6])

    def test_inputs_are_refused_not_quietly_changed(self):   # L-18, L-20, L-21
        self.new_project(name="P", client="C")
        h = {"Accept": "application/json"}
        self.assertEqual(self.client.post("/settings/contacts/vendors/9999/delete", headers=h).status_code, 404)
        self.assertEqual(self.client.post("/projects/1/edit", data={"name": "Two\nlines", "client": "C"}, headers=h).status_code, 400)
        self.assertEqual(self.client.post("/projects/1/edit", data={"name": "x" * 201, "client": "C"}, headers=h).status_code, 400)
        self.assertEqual(self.client.post("/projects/1/tasks", json={"title": "t", "assignee_id": 9999}).status_code, 400)
        self.assertEqual(self.client.post("/projects/1/tasks/9999/delete", headers=h).status_code, 404)
        self.client.post("/settings/contacts/vendors/add", data={"name": "SimVendor"})
        self.assertEqual(self.client.post("/settings/contacts/vendors/add", data={"name": "simvendor"}, headers=h).status_code, 400)

    def test_a_deleted_projects_bell_goes_quiet_and_its_alerts_leave_the_dashboard(self):   # L-11, L-16
        self.new_project(name="P", client="C", target_end_date="2020-01-01")
        self.sql("INSERT INTO notifications (user_id, kind, project_id, title, body, created_at) VALUES (1, 'stage', 1, 't', 'b', '2026-10-01')")
        c, _ = self._api_client()
        before = c.get("/api/session").get_json()["user"]["nav"]["unread_notifications"]
        self.client.post("/projects/1/delete")
        self.assertEqual(c.get("/api/session").get_json()["user"]["nav"]["unread_notifications"], before - 1)

    def test_due_soon_lists_each_rollout_once(self):   # L-8
        from datetime import date, timedelta
        soon = (date.today() + timedelta(days=2)).isoformat()
        self.new_project(name="Both", client="C", target_end_date=soon)
        self.sql("UPDATE project_stages SET sla_days = 1 WHERE project_id = 1")
        self.sql("UPDATE projects SET stage_entered_at = '2026-01-01T00:00:00' WHERE id = 1")
        c, _ = self._api_client()
        self.assertEqual(c.get("/api/projects/1/flow").get_json()["state"], "over_sla")
        self.assertEqual(c.get("/api/projects?view=at_risk").get_json()["total"], 0)

    def test_the_audit_filter_finds_a_person_by_name_or_sign_in(self):   # roles-10
        c, _ = self._api_client()
        names = c.get("/api/audit").get_json()["usernames"]
        self.assertEqual(len([n for n in names if n.lower() == "admin"]), 1)
        self.assertGreater(c.get("/api/audit?user=Admin").get_json()["total"], c.get("/api/audit?action=login_success").get_json()["total"] - 1)
