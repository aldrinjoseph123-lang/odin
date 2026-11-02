"""A repeating task nobody ticks keeps the two-open cap (services/recurrence.spawn_next) but is
visible: stalled on the rollout's flow, an amber reason in its health, and a `task_stalled` alert.
Run with: python -m unittest test_v2_repeats"""
import send_daily_alerts
from test_v2_milestones import MilestoneBase, iso


class StalledSeriesTestCase(MilestoneBase):
    def series(self, second_due=-1):
        """An overdue weekly task, its next occurrence made, and that one moved to `second_due`."""
        self.new_project()
        first = self.task("Weekly call", due_date=iso(-10), recurrence="weekly")
        self.ctx()
        from db import get_db
        from services.recurrence import run_recurring
        self.assertEqual(run_recurring(get_db(), self.NOW.date()), 1)
        second = self.tuples("SELECT id FROM tasks WHERE recur_from = ?", first)[0][0]
        self.sql("UPDATE tasks SET due_date = ? WHERE id = ?", iso(second_due), second)
        return first, second

    def sync(self):
        self.ctx()
        from db import get_db
        from services.alerts import build_alerts, sync_alerts_to_db
        sync_alerts_to_db(build_alerts(get_db().execute("SELECT * FROM projects WHERE deleted_at IS NULL").fetchall()))
        get_db().commit()   # release the read the pass leaves open, so the test's raw connection can write

    def alerts(self):
        return self.tuples("SELECT resolved FROM alerts WHERE alert_type = 'task_stalled' ORDER BY id")

    def flags(self):
        return {t["id"]: t["stalled"] for t in self.client.get("/api/projects/1/flow").get_json()["tasks"]}

    def reasons(self):
        return self.client.get("/api/projects/1/plan").get_json()["health"]["reasons"]

    def test_the_second_one_passing_with_the_first_open_is_stalled_everywhere(self):
        first, second = self.series()
        self.assertEqual(self.flags(), {first: False, second: True})            # the earlier one is late, not stalled
        self.assertIn("Repeating task stalled: Weekly call.", self.reasons())
        self.assertEqual(self.client.get("/api/projects/1/plan").get_json()["health"]["rag"], "amber")
        self.sync()
        self.sync()                                                              # once, however often the pass runs
        self.assertEqual(self.alerts(), [(0,)])
        self.assertEqual(self.tuples("SELECT COUNT(*) FROM notifications WHERE title LIKE 'Repeating task stalled%'")[0][0], 1)
        self.tick(first)                                                         # an occurrence is ticked: the series moves on
        self.assertEqual(self.flags()[second], False)
        self.assertNotIn("Repeating task stalled: Weekly call.", self.reasons())
        self.sync()
        self.assertEqual(self.alerts(), [(1,)])

    def test_not_stalled_while_the_second_is_on_time_or_only_one_is_open(self):
        first, second = self.series(second_due=3)
        self.assertEqual(self.flags(), {first: False, second: False})            # the earlier is overdue, the next is not
        self.sync()
        self.assertEqual(self.alerts(), [])
        self.assertFalse([r for r in self.reasons() if "stalled" in r])

    def test_one_open_occurrence_past_due_is_late_not_stalled(self):
        self.new_project()
        only = self.task("Weekly call", due_date=iso(-1), recurrence="weekly")   # nothing earlier, nothing made yet
        self.assertEqual(self.flags(), {only: False})
        self.sync()
        self.assertEqual(self.alerts(), [])

    def test_the_cap_is_unchanged(self):
        first, second = self.series()
        self.ctx()
        from db import get_db
        from services.recurrence import spawn_next
        self.assertIsNone(spawn_next(get_db(), second, self.NOW.date()))
        self.assertEqual(self.tuples("SELECT COUNT(*) FROM tasks WHERE done = 0")[0][0], 2)

    def test_the_type_is_in_the_settings_and_the_digest(self):
        self.assertEqual(self.tuples("SELECT severity, threshold_days, notify_inapp FROM alert_type_settings WHERE alert_type = 'task_stalled'"), [("warning", 0, 1)])
        self.series()
        self.ctx()
        from db import get_db
        from services.alerts import build_alerts
        alerts = build_alerts(get_db().execute("SELECT * FROM projects").fetchall())
        self.assertIn("Repeating tasks stalled (1)", send_daily_alerts._format_alerts_html(alerts))
