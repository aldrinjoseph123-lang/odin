"""v2.0.0, the lead's own fixes: what an outside party sees of the team's tasks
(found by the self-service build), and the Flow's next step skipping waiting work.
Run with: python -m unittest test_v2_lead"""
from test_v2_selfserve import SelfServeBase


class OutsiderTaskCutTestCase(SelfServeBase):
    def test_a_partner_sees_only_their_own_tasks_on_the_calendar_and_the_flow(self):
        self.client.post("/projects/1/tasks", json={"title": "Internal firewall review", "due_date": "2026-10-20"})
        mine = self.ask("task", title="Send the asset list", due_date="2026-10-21")
        c = self.ext("Customer")
        cal = c.get("/api/calendar?month=2026-10").get_json()
        self.assertEqual([t["title"] for t in cal["tasks"]], ["Send the asset list"])
        row = next(r for r in c.get("/api/flow").get_json()["rows"] if r["id"] == 1)
        self.assertEqual((row["next_task"] or {}).get("title"), "Send the asset list")
        staff = next(r for r in self.client.get("/api/flow").get_json()["rows"] if r["id"] == 1)
        self.assertEqual(staff["next_task"]["title"], "Internal firewall review")   # staff still see the team's work
        self.assertTrue(mine)

    def test_the_next_step_is_never_a_task_still_waiting_on_open_work(self):
        first = self.client.post("/projects/1/tasks", json={"title": "First", "due_date": "2026-10-25"}).get_json()["id"]
        r = self.client.post("/projects/1/tasks", json={"title": "Second", "due_date": "2026-10-20", "waits_on": [first]})
        self.assertEqual(r.status_code, 200, r.get_json())
        staff = next(r for r in self.client.get("/api/flow").get_json()["rows"] if r["id"] == 1)
        self.assertEqual(staff["next_task"]["title"], "First")   # Second is due sooner but waits on First
