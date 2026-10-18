"""v2.0.0, the lead's own fixes: what an outside party sees of the team's tasks
(found by the self-service build), and the Flow's next step skipping waiting work.
Run with: python -m unittest test_v2_lead

The clock is frozen (FixBase.NOW) and every date is written from it, so nothing here
depends on the weekday or the month of the day it runs."""
from test_v2_selfserve import SelfServeBase


class OutsiderTaskCutTestCase(SelfServeBase):
    def setUp(self):
        super().setUp()
        self.freeze_clock()

    def test_a_partner_sees_only_their_own_tasks_on_the_calendar_and_the_flow(self):
        self.task("Internal firewall review", due_date=self.day(6))
        self.ask("task", title="Send the asset list", due_date=self.day(7))
        c = self.ext("Customer")
        cal = c.get(f"/api/calendar?month={self.day(0)[:7]}").get_json()
        self.assertEqual([t["title"] for t in cal["tasks"]], ["Send the asset list"])
        row = next(r for r in c.get("/api/flow").get_json()["rows"] if r["id"] == 1)
        self.assertEqual((row["next_task"] or {}).get("title"), "Send the asset list")
        staff = next(r for r in self.client.get("/api/flow").get_json()["rows"] if r["id"] == 1)
        self.assertEqual(staff["next_task"]["title"], "Internal firewall review")   # staff still see the team's work

    def test_the_next_step_is_never_a_task_still_waiting_on_open_work(self):
        first = self.task("First", due_date=self.day(11))
        self.task("Second", due_date=self.day(6), waits_on=[first])   # due sooner, but waits on First
        staff = next(r for r in self.client.get("/api/flow").get_json()["rows"] if r["id"] == 1)
        self.assertEqual(staff["next_task"]["title"], "First")
