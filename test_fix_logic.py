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


if __name__ == "__main__":
    unittest.main()
