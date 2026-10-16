"""Odin 2.0, workstream 9: the integration pass.

The build round's pieces meet the surfaces that read everything: the report
PDFs, the weekly email, the /api/v1 read API, the project page's pending
intake, the undo of a deleted task, a repeating task's next occurrence, and
the customer's view of every project route (no gate internals).
"""
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

import app as app_module
from test_fix_logic import FixBase


class IntegrationTestCase(FixBase):

    def setUp(self):
        super().setUp()
        self._notify = patch("routes.projects.notify_event")
        self._notify.start()
        self.addCleanup(self._notify.stop)

    def today(self):
        from policies import local_today
        with app_module.app.test_request_context():
            return local_today()

    def task(self, pid=1, **body):
        r = self.client.post(f"/projects/{pid}/tasks", json={"stage": self.stages(pid)[0], **body})
        self.assertEqual(r.status_code, 200, r.data)
        return r.get_json()["id"]

    def links(self, pid=1):
        return sorted(tuple(r) for r in self.sql("SELECT task_id, depends_on_task_id FROM task_links WHERE project_id = ?", pid))

    def token(self, scope="read"):
        from security import token_hash
        self.sql("INSERT INTO api_tokens (name, token_hash, created_by, created_at, expires_at, scope) "
                 "VALUES ('bi', ?, 'Admin', datetime('now'), datetime('now', '+1 day'), ?)", token_hash("odin_test"), scope)
        return {"Authorization": "Bearer odin_test"}

    def ask_world(self):
        """One rollout with a customer, an upload ask, a milestone each way, and a rating."""
        self.new_project(name="Firewalls", client="Acme")
        self._invite(1, "ann@client.example", "Customer", "Ann")
        ann = self.sql("SELECT id FROM users WHERE email = 'ann@client.example'")[0][0]
        self.task(title="Upload the network diagram", kind="upload", ask_category="Deliverable", assignee_id=ann)
        day = (self.today() + timedelta(days=2)).isoformat()
        for name, shown in (("Cut-over weekend", True), ("Internal dry run", False)):
            self.assertEqual(self.client.post("/api/projects/1/milestones", json={"name": name, "date": day, "customer_visible": shown}).status_code, 200)
        self.sql("INSERT INTO csat (project_id, signoff_version, rating, comment, by_id, by_name, at) VALUES (1, 1, 4, 'Smooth cut-over', ?, 'Ann', datetime('now'))", ann)
        return ann

    # ---- the PDFs -------------------------------------------------------------

    def test_the_internal_pdf_prints_asks_and_rating_and_the_customer_copy_does_not(self):
        self.ask_world()
        internal = self.client.get("/projects/1/report.pdf").data
        for text in (b"Asked of the customer and partners", b"Upload the network diagram", b"Smooth cut-over", b"Cut-over weekend", b"Internal dry run"):
            self.assertIn(text, internal)
        customer = self.client.get("/projects/1/report.pdf?audience=customer").data
        self.assertIn(b"Cut-over weekend", customer)
        for text in (b"Asked of the customer and partners", b"Smooth cut-over", b"Internal dry run"):
            self.assertNotIn(text, customer)
        # the template can switch the section off like any other
        from services.doc_templates import KINDS
        self.assertIn("asks", [k for k, _ in KINDS["rollout"]["sections"]])

    def test_the_portfolio_pdf_names_each_rollouts_next_milestone(self):
        self.ask_world()
        pdf = self.client.get("/reports/all.pdf").data
        self.assertIn(b"Next milestone", pdf)
        self.assertIn(b"(Cut-over", pdf)   # the earliest open one (both share a day; the first by id), fitted to its column
        self.assertIn(b"Customer rating", pdf)

    # ---- the weekly email -----------------------------------------------------

    def test_the_weekly_email_carries_milestones_and_who_is_over_capacity(self):
        self.ask_world()
        admin = self.sql("SELECT id FROM users WHERE username = 'admin'")[0][0]
        self.task(title="Rebuild the rule base", assignee_id=admin, due_date=self.today().isoformat(), estimate_hours=60)
        from services import weekly_report
        self.ctx()
        _, html, summary, _ = weekly_report.build()
        self.assertIn("Milestones", html)
        self.assertIn("Cut-over weekend", html)
        self.assertIn("Over capacity", html)
        self.assertRegex(html, r"<b>Admin</b>: \d+(\.\d)? h of 30 h")
        self.assertIn("2 milestones missed or due this week, 1 person over capacity", summary)

    # ---- /api/v1 --------------------------------------------------------------

    def test_v1_project_carries_task_links_milestones_asks_and_ratings(self):
        self.ask_world()
        first = self.task(title="Survey the site")
        second = self.task(title="Rack the firewalls", waits_on=[first], estimate_hours=6)
        c = app_module.app.test_client()
        body = c.get("/api/v1/projects/1", headers=self.token()).get_json()
        tasks = {t["title"]: t for t in body["tasks"]}
        self.assertEqual((tasks["Rack the firewalls"]["id"], tasks["Rack the firewalls"]["waits_on"], tasks["Rack the firewalls"]["estimate_hours"]), (second, [first], 6))
        self.assertEqual(tasks["Upload the network diagram"]["kind"], "upload")
        self.assertEqual(sorted(m["name"] for m in body["milestones"]), ["Cut-over weekend", "Internal dry run"])   # the token sees what staff see
        self.assertEqual([(a["title"], a["assignee_role"], a["done"]) for a in body["asks"]], [("Upload the network diagram", "Customer", False)])
        self.assertEqual([(r["rating"], r["comment"]) for r in body["csat"]], [(4, "Smooth cut-over")])
        self.assertEqual(body["project"]["fields"], {})

    def test_v1_projects_pages_with_limit_and_offset_and_keeps_the_whole_set_by_default(self):
        for i in range(5):
            self.new_project(name=f"R{i}", client="C")
        c = app_module.app.test_client()
        h = self.token()
        whole = c.get("/api/v1/projects", headers=h).get_json()
        self.assertEqual(([p["name"] for p in whole["projects"]], whole["total"], whole["limit"], whole["offset"]), ([f"R{i}" for i in range(5)], 5, None, 0))
        page = c.get("/api/v1/projects?limit=2&offset=2", headers=h).get_json()
        self.assertEqual(([p["name"] for p in page["projects"]], page["total"], page["limit"], page["offset"]), (["R2", "R3"], 5, 2, 2))
        self.assertEqual([p["name"] for p in c.get("/api/v1/projects?offset=4", headers=h).get_json()["projects"]], ["R4"])
        self.assertEqual(c.get("/api/v1/projects?offset=9&limit=1", headers=h).get_json()["projects"], [])
        for bad, words in (("limit=0", "limit: 1 to 500"), ("limit=501", "limit: 1 to 500"), ("offset=-1", "offset: 0 or more"), ("limit=x", "whole numbers")):
            r = c.get(f"/api/v1/projects?{bad}", headers=h)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn(words, r.get_json()["error"])

    # ---- the pending intake on the project page --------------------------------

    def test_the_project_page_knows_a_pending_intake_and_the_customer_never_does(self):
        self.new_project(name="From the CRM", client="Acme")
        self.assertFalse(self.client.get("/api/projects/1").get_json()["intake_pending"])
        self._invite(1, "ann@client.example", "Customer", "Ann")
        ext = self._external_client("ann@client.example")
        self.sql("UPDATE projects SET intake_pending = 1 WHERE id = 1")
        self.assertTrue(self.client.get("/api/projects/1").get_json()["intake_pending"])
        self.assertEqual([r["id"] for r in self.client.get("/api/intake/pending").get_json()["rows"]], [1])
        for path in ("/api/projects/1/flow", "/api/projects/1/activity", "/api/projects/1/plan", "/projects/1"):   # what the page loads
            self.assertEqual(self.client.get(path).status_code, 200, path)
        r = ext.get("/api/projects/1")
        self.assertTrue(r.status_code == 404 or r.get_json()["intake_pending"] is False)

    # ---- links: a repeat copies them, an undo gives them back --------------------

    def test_a_repeating_tasks_next_occurrence_waits_on_what_it_waited_on(self):
        self.new_project()
        before = self.task(title="Pull the change list")
        weekly = self.task(title="Weekly status call", due_date=self.today().isoformat(), recurrence="weekly", waits_on=[before])
        self.client.post(f"/projects/1/tasks/{before}/toggle", json={"done": True})
        self.client.post(f"/projects/1/tasks/{weekly}/toggle", json={"done": True})
        nxt = self.sql("SELECT id FROM tasks WHERE recur_from = ?", weekly)[0][0]
        self.assertEqual(self.links(), [(weekly, before), (nxt, before)])

    def test_undoing_a_deleted_task_gives_back_the_links_of_the_tasks_that_waited_on_it(self):
        self.new_project()
        base = self.task(title="Survey the site")
        a = self.task(title="Rack", waits_on=[base])
        b = self.task(title="Cable", waits_on=[base, a])
        self.client.post(f"/projects/1/tasks/{base}/delete")
        self.assertEqual(self.links(), [(b, a)])
        # the page's Undo: the same task again, and the ones that waited on it (blocks)
        back = self.task(title="Survey the site", blocks=[a, b])
        self.assertEqual(self.links(), sorted([(a, back), (b, a), (b, back)]))
        # a loop or a task of another rollout is refused, and nothing is made
        self.new_project(name="Other", client="C")
        other = self.task(pid=2, title="Elsewhere")
        r = self.client.post("/projects/1/tasks", json={"title": "Loop", "stage": self.stages()[0], "waits_on": [b], "blocks": [a]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("loop", r.get_json()["error"])
        r = self.client.post("/projects/1/tasks", json={"title": "Stray", "stage": self.stages()[0], "blocks": [other]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tasks WHERE title IN ('Loop', 'Stray')")[0][0], 0)

    # ---- the customer sees no gate internals, on any project route ----------------

    def test_no_project_route_shows_the_customer_a_gate(self):
        self.new_project()
        s = self.stages()
        sid = self.sql("SELECT id FROM project_stages WHERE project_id = 1 AND name = ?", s[0])[0][0]
        self.client.post("/projects/1/stages/gates", data={f"gate::{sid}": "1", f"docs::{sid}": "Deliverable"}, headers={"Accept": "application/json"})
        self.task(title="Survey the site")
        self.assertIn("Deliverable missing", json.dumps(self.client.get("/api/projects/1/flow").get_json()))   # staff see it
        self._invite(1, "ann@client.example", "Customer", "Ann")
        ext = self._external_client("ann@client.example")
        seen = 0
        for rule in app_module.app.url_map.iter_rules():
            if "GET" not in rule.methods or set(rule.arguments) != {"project_id"}:
                continue
            r = ext.get(rule.rule.replace("<int:project_id>", "1"))
            if r.status_code != 200:
                continue
            seen += 1
            body = r.get_data(as_text=True)
            for leak in ("Deliverable missing", "1 open task", '"gate_tasks": true', "Moved past the gate"):
                self.assertNotIn(leak, body, f"{rule.rule} shows the customer {leak!r}")
        self.assertGreater(seen, 5)


if __name__ == "__main__":
    unittest.main()
