"""Odin 2.0, workstream 3: task dependencies (finish-to-start, one rollout)
and the tasks a template's stages bring. Run with: python -m unittest test_v2_deps

Dates are relative to the workspace's today, in UTC, with stage lengths in
calendar days: nothing here depends on the weekday or the month."""
from datetime import datetime, timedelta

from test_app import STRONG_PASSWORD, app_module
from test_fix_logic import FixBase

J = {"Accept": "application/json"}


class DepsBase(FixBase):
    def setUp(self):
        super().setUp()
        self._set_policy(timezone="UTC", count_working_days="0")
        self.today = datetime.utcnow().date()

    def day(self, n):
        return (self.today + timedelta(days=n)).isoformat()

    def task(self, title, pid=1, **fields):
        r = self.client.post(f"/projects/{pid}/tasks", json={"title": title, **fields})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["id"]

    def edit(self, tid, pid=1, **fields):
        return self.client.post(f"/projects/{pid}/tasks/{tid}/edit", json=fields)

    def flow_task(self, tid, client=None):
        return next(t for t in (client or self.client).get("/api/projects/1/flow").get_json()["tasks"] if t["id"] == tid)

    def member(self):
        """A Member coordinating rollout 1: manages its tasks, is not an Admin."""
        uid = self._make_user("mo", "Member")
        self.sql("INSERT INTO project_participants (project_id, user_id, role, added_at) VALUES (1, ?, 'Coordinator', datetime('now'))", uid)
        c, csrf = self._api_client("mo", STRONG_PASSWORD)
        return uid, c, {"X-CSRF-Token": csrf, **J}


class LinkRulesTestCase(DepsBase):
    def test_a_loop_is_refused_directly_and_through_others(self):
        self.new_project()
        a, b, c = self.task("A"), self.task("B"), self.task("C")
        self.assertEqual(self.edit(b, waits_on=[a]).status_code, 200)
        r = self.edit(a, waits_on=[b])
        self.assertEqual(r.status_code, 400)
        self.assertIn("loop", r.get_json()["error"])
        self.assertEqual(self.edit(c, waits_on=[b]).status_code, 200)   # A <- B <- C
        r = self.edit(a, waits_on=[c])
        self.assertEqual(r.status_code, 400)
        self.assertIn("C already waits on this task", r.get_json()["error"])
        self.assertEqual(self.edit(a, waits_on=[a]).get_json()["error"], "A task cannot wait on itself")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM task_links")[0][0], 2)   # nothing refused was kept
        # a refused edit changes nothing else either
        r = self.edit(a, title="A renamed", waits_on=[c])
        self.assertEqual((r.status_code, self.sql("SELECT title FROM tasks WHERE id = ?", a)[0][0]), (400, "A"))
        self.assertEqual(self.edit(c, waits_on=[]).status_code, 200)   # an empty list clears
        self.assertEqual(self.flow_task(c)["waits_on"], [])

    def test_a_task_waits_only_on_tasks_of_its_own_rollout(self):
        self.new_project(name="One"); self.new_project(name="Two")
        theirs = self.task("Elsewhere", pid=2)
        mine = self.task("Here")
        r = self.edit(mine, waits_on=[theirs])
        self.assertEqual((r.status_code, r.get_json()["error"]), (400, "A task can only wait on tasks of the same rollout"))
        r = self.client.post("/projects/1/tasks", json={"title": "New", "waits_on": [theirs]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post("/projects/1/tasks", json={"title": "New", "waits_on": "1"}).status_code, 400)   # not a list
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tasks WHERE title = 'New'")[0][0], 0)

    def test_a_blocked_task_waits_and_only_an_admin_overrides_on_the_record(self):
        self.new_project()
        uid, c, h = self.member()
        first = self.task("Order sensors", due_date=self.day(-3))
        second = self.task("Install sensors", assignee_id=uid, waits_on=[first], estimate_hours=4)
        t = self.flow_task(second, c)
        self.assertEqual((t["waits_on"], t["estimate_hours"]), ([first], 4.0))
        self.assertEqual(t["blocked_by"], [{"id": first, "title": "Order sensors", "late_by": 3}])
        self.assertFalse(c.get("/api/projects/1/flow").get_json()["can_override"])
        r = c.post(f"/projects/1/tasks/{second}/toggle", json={"done": True}, headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("waits on Order sensors", r.get_json()["error"])
        self.assertEqual(self.sql("SELECT done FROM tasks WHERE id = ?", second)[0][0], 0)
        # the Admin may: ticked, and an override row says so
        self.assertEqual(self.client.post(f"/projects/1/tasks/{second}/toggle", json={"done": True}).get_json()["done"], True)
        self.assertEqual(self.audits("override_task_wait"), 1)
        self.assertIn("Order sensors", self.sql("SELECT details FROM audit_logs WHERE action = 'override_task_wait'")[0][0])
        # once the predecessor is done the member ticks freely, with no override
        self.client.post(f"/projects/1/tasks/{second}/toggle", json={"done": False})
        c.post(f"/projects/1/tasks/{first}/toggle", json={"done": True}, headers=h)
        self.assertEqual(c.post(f"/projects/1/tasks/{second}/toggle", json={"done": True}, headers=h).status_code, 200)
        self.assertEqual(self.audits("override_task_wait"), 1)

    def test_deleting_the_predecessor_unblocks(self):
        self.new_project()
        uid, c, h = self.member()
        first = self.task("Order sensors")
        second = self.task("Install sensors", waits_on=[first])
        self.assertTrue(self.flow_task(second)["blocked_by"])
        self.client.post(f"/projects/1/tasks/{first}/delete", json={})
        self.assertEqual((self.flow_task(second)["blocked_by"], self.flow_task(second)["waits_on"]), ([], []))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM task_links")[0][0], 0)
        self.assertEqual(c.post(f"/projects/1/tasks/{second}/toggle", json={"done": True}, headers=h).status_code, 200)

    def test_links_go_with_a_purged_project(self):
        self.new_project()
        self.task("B", waits_on=[self.task("A")])
        self.sql("UPDATE projects SET deleted_at = '2000-01-01T00:00:00'")
        self.ctx()
        from db import cleanup_soft_deletes
        cleanup_soft_deletes()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM task_links")[0][0], 0)
        import reset_data
        self.assertLess(reset_data.WIPE_TABLES.index("task_links"), reset_data.WIPE_TABLES.index("tasks"))

    def test_my_work_sets_blocked_tasks_apart(self):
        self.new_project()
        uid, c, h = self.member()
        first = self.task("Order sensors", due_date=self.day(-2))
        self.task("Install sensors", assignee_id=uid, waits_on=[first])
        self.task("Free task", assignee_id=uid)
        rows = {t["title"]: t for t in c.get("/api/my-work").get_json()["tasks"]}
        self.assertEqual(rows["Install sensors"]["blocked_by"], [{"id": first, "title": "Order sensors", "late_by": 2}])
        self.assertEqual(rows["Free task"]["blocked_by"], [])


class ForecastTestCase(DepsBase):
    def test_a_late_predecessor_moves_the_forecast_and_the_health_names_it(self):
        self.new_project()
        current = lambda: next(s for s in self.client.get("/api/projects/1/plan").get_json()["stages"] if s["status"] == "current")   # noqa: E731
        before = datetime.fromisoformat(current()["forecast_end"]).date()
        late = self.task("Order sensors", due_date=self.day(-5))
        nxt = self.task("Install sensors", due_date=(before + timedelta(days=1)).isoformat())
        self.assertEqual(current()["forecast_end"], before.isoformat())   # no link: dates alone do not move it
        self.edit(nxt, waits_on=[late])
        s = current()
        # the slip carries: Install keeps its gap to Order, and Order finishes today at the earliest
        self.assertEqual(s["forecast_end"], (before + timedelta(days=6)).isoformat())
        self.assertIn("Install sensors", s["forecast_reason"])
        self.assertIn("Order sensors (5 d late)", s["forecast_reason"])
        health = self.client.get("/api/projects/1/plan").get_json()["health"]
        self.assertIn(s["forecast_reason"], health["reasons"])
        self.assertNotEqual(health["rag"], "green")
        self.client.post(f"/projects/1/tasks/{late}/toggle", json={"done": True})   # the predecessor done: back to the plan
        self.assertEqual((current()["forecast_end"], current()["forecast_reason"]), (before.isoformat(), None))

    def test_the_chain_logic(self):
        from datetime import date
        from services.task_links import chained_finish
        today = date(2030, 3, 10)
        t = [{"id": 1, "title": "a", "done": 0, "due_date": "2030-03-05"}, {"id": 2, "title": "b", "done": 0, "due_date": "2030-03-08"},
             {"id": 3, "title": "c", "done": 0, "due_date": None}, {"id": 4, "title": "d", "done": 1, "due_date": "2030-01-01"}]
        out = chained_finish(t, {2: [1], 3: [2], 1: [4]}, today)
        self.assertEqual(out[1], (today, t[0]))                           # late: today at the earliest
        self.assertEqual(out[2], (date(2030, 3, 13), t[0]))               # three days after a, as planned
        self.assertEqual(out[3], (date(2030, 3, 13), t[0]))               # undated: what it waits on
        self.assertNotIn(4, out)
        self.assertEqual(chained_finish(t[:2], {1: [2], 2: [1]}, today)[2][0], today)   # an old loop is cut, never followed


class TemplateTasksTestCase(DepsBase):
    def put(self, tasks, tid=1):
        csrf = self.client.get("/api/session").get_json()["csrf"]
        return self.client.put(f"/api/settings/templates/{tid}/tasks", json={"tasks": tasks}, headers={"X-CSRF-Token": csrf})

    def stage_ids(self):
        return [r[0] for r in self.sql("SELECT id FROM stage_template_stages WHERE template_id = 1 ORDER BY position")]

    def test_a_new_rollout_arrives_with_the_tasks_roles_offsets_and_links(self):
        first, second = self.stage_ids()[:2]
        uid = self._make_user("co", "Member")
        r = self.put([{"key": "a", "stage_id": first, "title": "Confirm scope", "role": "Project manager", "offset_days": 2},
                      {"key": "b", "stage_id": first, "title": "Kick-off pack", "role": "Coordinator", "offset_days": 4, "waits_on": "a", "estimate_hours": 3},
                      {"key": "c", "stage_id": second, "title": "Name a contact", "role": "Customer", "offset_days": 1},
                      {"key": "d", "stage_id": second, "title": "Anyone", "offset_days": 0}])
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual([t["title"] for t in r.get_json()["tasks"]], ["Confirm scope", "Kick-off pack", "Name a contact", "Anyone"])
        self.assertEqual(self.audits("update_template_tasks"), 1)
        self.new_project(start_date="2030-03-04", team_user_ids=str(uid))
        names = self.stages()
        rows = {r["title"]: r for r in self.client.get("/api/projects/1/flow").get_json()["tasks"]}
        self.assertEqual({k: (v["assignee_id"], v["due_date"], v["stage"]) for k, v in rows.items()}, {
            "Confirm scope": (1, "2030-03-06", names[0]),       # the owner
            "Kick-off pack": (uid, "2030-03-08", names[0]),     # the coordinator
            "Name a contact": (None, "2030-03-05", names[1]),   # no customer yet: unassigned
            "Anyone": (None, "2030-03-04", names[1]),
        })
        self.assertEqual(rows["Kick-off pack"]["waits_on"], [rows["Confirm scope"]["id"]])
        self.assertEqual(rows["Kick-off pack"]["estimate_hours"], 3.0)
        # the template list stays as saved; a second rollout gets its own copies
        self.new_project(name="Again")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tasks WHERE project_id = 2")[0][0], 4)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM task_links")[0][0], 2)

    def test_the_editor_refuses_loops_strangers_and_bad_rows(self):
        first = self.stage_ids()[0]
        r = self.put([{"key": "a", "stage_id": first, "title": "A", "waits_on": "b"}, {"key": "b", "stage_id": first, "title": "B", "waits_on": "a"}])
        self.assertEqual(r.status_code, 400)
        self.assertIn("loop", r.get_json()["error"])
        for bad in ([{"key": "a", "stage_id": 99999, "title": "A"}], [{"key": "a", "stage_id": first, "title": " "}],
                    [{"key": "a", "stage_id": first, "title": "A", "role": "Boss"}], [{"key": "a", "stage_id": first, "title": "A", "offset_days": -1}],
                    [{"key": "a", "stage_id": first, "title": "A", "waits_on": "zz"}], "nope"):
            self.assertEqual(self.put(bad).status_code, 400, bad)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM template_tasks")[0][0], 0)
        self.assertEqual(self.put([], tid=999).status_code, 404)

    def test_a_removed_template_stage_takes_its_tasks(self):
        first, second, third = self.stage_ids()[:3]
        self.put([{"key": "a", "stage_id": second, "title": "Goes"}, {"key": "b", "stage_id": third, "title": "Stays", "waits_on": "a"}])
        self.client.post(f"/settings/templates/1/stages/{second}/delete")
        self.assertEqual([(r[0], r[1]) for r in self.sql("SELECT title, waits_on_id FROM template_tasks")], [("Stays", None)])

    def test_only_settings_managers_edit_them(self):
        self._make_user("mo", "Member")
        c, csrf = self._api_client("mo", STRONG_PASSWORD)
        self.assertEqual(c.get("/api/settings/templates/1/tasks").status_code, 403)
        self.assertEqual(c.put("/api/settings/templates/1/tasks", json={"tasks": []}, headers={"X-CSRF-Token": csrf}).status_code, 403)


if __name__ == "__main__":
    import unittest
    unittest.main()
