"""Odin 2.0, workstream 2: enforced stage gates (services/gates.py).

A stage may ask for all its tasks done and some document categories on file
before a rollout leaves it. Every move path refuses a move forward past a
gate; an Admin or the project manager (policy gate_override) may move past
it with a typed reason, audited and kept in the stage history.
"""
import io
import re
import unittest
from unittest.mock import patch

import app as app_module
from test_fix_logic import FixBase


class StageGatesTestCase(FixBase):

    def setUp(self):
        super().setUp()
        self._notify = patch("routes.projects.notify_event")
        self._notify.start()
        self.addCleanup(self._notify.stop)

    # ---- helpers ------------------------------------------------------------

    def stage_id(self, name, pid=1):
        return self.sql("SELECT id FROM project_stages WHERE project_id = ? AND name = ?", pid, name)[0][0]

    def set_gate(self, stage, tasks=True, docs=(), pid=1, client=None):
        sid = self.stage_id(stage, pid)
        return (client or self.client).post(f"/projects/{pid}/stages/gates", data={f"gate::{sid}": "1" if tasks else "", f"docs::{sid}": "\n".join(docs)},
                                            headers={"Accept": "application/json"})

    def add_task(self, title="Survey the site", pid=1, client=None):
        (client or self.client).post(f"/projects/{pid}/tasks", data={"title": title}, headers={"Accept": "application/json"})
        return self.sql("SELECT id FROM tasks WHERE project_id = ? AND title = ?", pid, title)[0][0]

    def move(self, stage, client=None, pid=1, **extra):
        return (client or self.client).post(f"/api/projects/{pid}/stage", json={"stage": stage, **extra})

    def where(self, pid=1):
        return self.sql("SELECT stage FROM projects WHERE id = ?", pid)[0][0]

    # ---- refusals -----------------------------------------------------------

    def test_a_gated_stage_refuses_the_move_and_says_why(self):
        self.new_project()
        s = self.stages()
        self.assertIsNone(self.set_gate(s[0], docs=["Deliverable"]).get_json().get("error"))
        self.add_task()
        r = self.move(s[1])
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"], f"Before leaving {s[0]}: 1 open task · Deliverable missing")
        self.assertEqual(self.where(), s[0])
        gate = self.client.get("/api/projects/1/flow").get_json()["gate"]
        self.assertEqual([g["kind"] for g in gate["blocked"]], ["tasks", "document"])
        self.assertTrue(gate["can_override"])
        # the Client PO uploaded at creation satisfies a gate that asks for it
        self.set_gate(s[0], tasks=False, docs=["Client PO"])
        self.assertEqual(self.move(s[1]).status_code, 200)

    def test_the_gate_clears_when_the_work_is_done(self):
        self.new_project()
        s = self.stages()
        self.set_gate(s[0])
        tid = self.add_task()
        self.assertEqual(self.move(s[1]).status_code, 409)
        self.client.post(f"/projects/1/tasks/{tid}/toggle", data={"done": "1"}, headers={"Accept": "application/json"})
        self.assertEqual(self.sql("SELECT done FROM tasks WHERE id = ?", tid)[0][0], 1)
        self.assertEqual(self.client.get("/api/projects/1/flow").get_json()["gate"]["blocked"], [])
        self.assertEqual(self.move(s[1]).status_code, 200)

    def test_only_a_move_forward_is_gated_and_a_jump_answers_for_every_stage_it_passes(self):
        self.new_project()
        s = self.stages()
        self.assertEqual(self.move(s[1]).status_code, 200)
        self.set_gate(s[1])
        self.set_gate(s[2], tasks=False, docs=["Deliverable"])
        self.add_task()                                    # no stage: it belongs to the current one
        self.assertEqual(self.move(s[0]).status_code, 200)  # back: never gated
        self.assertEqual(self.move(s[1]).status_code, 200)  # s[0] asks nothing
        r = self.move(s[3])                                 # a jump leaves s[1] and s[2] behind
        self.assertEqual(r.get_json()["error"], f"Before leaving {s[1]}: 1 open task · Deliverable missing")

    def test_a_deleted_category_no_longer_holds_the_gate(self):
        self.new_project()
        s = self.stages()
        self.client.post("/settings/doc-categories/add", data={"name": "Site survey"})
        self.set_gate(s[0], tasks=False, docs=["Site survey"])
        self.assertEqual(self.move(s[1]).status_code, 409)
        cid = self.sql("SELECT id FROM doc_categories WHERE name = 'Site survey'")[0][0]
        self.client.post(f"/settings/doc-categories/{cid}/delete")
        self.assertEqual(self.move(s[1]).status_code, 200)

    # ---- override -----------------------------------------------------------

    def test_the_project_manager_moves_past_the_gate_with_a_reason(self):
        pm, c, _ = self.member("pm")
        c.post("/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 x"), "po.pdf"), "name": "P", "client": "C"})
        s = self.stages()
        self.set_gate(s[0], client=c)
        self.add_task(client=c)
        self.assertEqual(self.move(s[1], c, override="").status_code, 409)              # no reason: still the gate
        self.assertEqual(self.move(s[1], c, override="   ").status_code, 409)
        r = self.move(s[1], c, override="Customer accepted the survey by phone")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.where(), s[1])
        self.assertEqual(self.audits("override_stage_gate"), 1)
        note = self.sql("SELECT note, guest_visible, stage FROM status_notes WHERE note LIKE 'Moved past the gate:%'")
        self.assertEqual(len(note), 1)
        self.assertEqual(note[0]["note"], "Moved past the gate: Customer accepted the survey by phone (1 open task)")
        self.assertEqual((note[0]["guest_visible"], note[0]["stage"]), (0, s[1]))   # staff only, in the stage it led to
        self.assertIn("Moved past the gate", [n["note"][:19] for n in c.get("/api/projects/1").get_json()["notes"]])

    def test_an_admin_overrides_and_the_policy_can_take_it_from_the_pm(self):
        pm, c, _ = self.member("pm")
        c.post("/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 x"), "po.pdf"), "name": "P", "client": "C"})
        s = self.stages()
        self.set_gate(s[0])
        self.add_task()
        self._set_policy(gate_override="admin")
        r = self.move(s[1], c, override="I say so")
        self.assertEqual((r.status_code, r.get_json()["error"]), (400, "Only an admin may move past a stage gate"))
        self.assertFalse(c.get("/api/projects/1/flow").get_json()["gate"]["can_override"])
        self.assertEqual(self.where(), s[0])
        self.assertEqual(self.move(s[1], override="Signed off on site").status_code, 200)   # the admin may
        self.assertEqual(self.audits("override_stage_gate"), 1)

    def test_no_one_else_overrides(self):
        self.new_project()
        s = self.stages()
        self.set_gate(s[0])
        self.add_task()
        uid, c, _ = self.member("coord")
        self.client.post("/projects/1/participants/add", data={"user_id": str(uid), "role": "Coordinator"})
        self.assertEqual(self.move(s[1], c, override="please").status_code, 403)   # a Coordinator never moves a stage
        self.assertEqual(self.where(), s[0])
        self.assertEqual(self.audits("override_stage_gate"), 0)

    def test_the_vendor_link_is_refused_without_internals(self):
        self.new_project(delivery_mode="Outsourced", outsourcer_name="VendorCo")
        s = self.stages()
        self.set_gate(s[0], docs=["Deliverable"])
        self.add_task("Secret internal task")
        tok = self.sql("SELECT access_token FROM projects WHERE id = 1")[0][0]
        g = app_module.app.test_client()
        csrf = re.search(r'name="_csrf" value="([^"]+)"', g.get(f"/guest/{tok}").data.decode()).group(1)
        g.post(f"/guest/{tok}/stage", data={"stage": s[1], "author": "Sam", "_csrf": csrf, "override": "x"})
        self.assertEqual(self.where(), s[0])
        page = g.get(f"/guest/{tok}").data.decode()
        self.assertIn("not finished yet", page)
        self.assertNotIn("Deliverable missing", page)

    # ---- the model: template copy and per-rollout edits ----------------------

    def test_a_template_gate_is_copied_to_new_rollouts_and_edited_per_rollout(self):
        tid = self.sql("SELECT id FROM stage_templates ORDER BY id LIMIT 1")[0][0]
        first = self.sql("SELECT id FROM stage_template_stages WHERE template_id = ? ORDER BY position LIMIT 1", tid)[0][0]
        self.client.post(f"/settings/templates/{tid}/gates", data={f"gate::{first}": "1", f"docs::{first}": "Client PO\nDeliverable"})
        self.assertEqual(self.audits("update_template_gates"), 1)
        t = next(t for t in self.client.get("/api/settings").get_json()["templates"] if t["id"] == tid)
        self.assertEqual((t["stages"][0]["gate_tasks"], t["stages"][0]["required_docs"]), (True, ["Client PO", "Deliverable"]))
        self.new_project()
        row = self.client.get("/api/projects/1").get_json()["stage_rows"][0]
        self.assertEqual((row["gate_tasks"], row["required_docs"]), (True, ["Client PO", "Deliverable"]))
        # per rollout: this one asks only for the deliverable; the template keeps its own
        self.set_gate(self.stages()[0], tasks=False, docs=["Deliverable"])
        self.assertEqual(self.audits("update_project_stage_gates"), 1)
        row = self.client.get("/api/projects/1").get_json()["stage_rows"][0]
        self.assertEqual((row["gate_tasks"], row["required_docs"]), (False, ["Deliverable"]))
        self.assertEqual(self.sql("SELECT gate_tasks FROM stage_template_stages WHERE id = ?", first)[0][0], 1)
        # a category that does not exist is refused, and nothing changes
        r = self.set_gate(self.stages()[0], docs=["Nope"])
        self.assertIn("is not a document category", " ".join(r.get_json()["messages"]))
        self.assertEqual(self.client.get("/api/projects/1").get_json()["stage_rows"][0]["required_docs"], ["Deliverable"])

    def test_only_the_project_manager_edits_a_rollouts_gates(self):
        self.new_project()
        uid, c, _ = self.member("coord")
        self.client.post("/projects/1/participants/add", data={"user_id": str(uid), "role": "Coordinator"})
        self.assertEqual(self.set_gate(self.stages()[0], client=c).status_code, 403)

    # ---- the Flow, health and the report ------------------------------------

    def test_the_flow_row_says_the_move_is_blocked_for_staff_only(self):
        self.new_project()
        s = self.stages()
        self.set_gate(s[0], docs=["Deliverable"])
        self.add_task()
        row = self.client.get("/api/flow").get_json()["rows"][0]
        self.assertEqual((row["gate_blocked"], row["gate_reasons"]), (True, ["1 open task", "Deliverable missing"]))
        # the customer: no gate internals on the board or the flow
        self._invite(1, "ann@client.example", "Customer", "Ann")
        ext = self._external_client("ann@client.example")
        row = ext.get("/api/flow").get_json()["rows"][0]
        self.assertEqual((row["gate_blocked"], row["gate_reasons"]), (False, []))
        self.assertIsNone(ext.get("/api/projects/1/flow").get_json()["gate"])
        self.assertEqual(ext.get("/api/projects/1").get_json()["stage_rows"][0]["required_docs"], [])

    def test_a_due_move_held_by_its_gate_is_a_health_reason_but_not_for_the_customer(self):
        self.new_project()
        s = self.stages()
        self.set_gate(s[0])
        self.add_task()
        from services import plan, report_data
        self.ctx()
        self.freeze_clock("services.plan", "services.analytics", "services.report_data")
        long_ago = self.now(days=-40).isoformat()
        self.sql("UPDATE project_stages SET sla_days = 5 WHERE project_id = 1 AND name = ?", s[0])
        project = lambda: self.sql("SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.id = 1")[0]   # noqa: E731
        # not due yet: the gate is work in progress, not a health reason
        self.sql("UPDATE projects SET stage_entered_at = ? WHERE id = 1", self.now().isoformat())
        self.assertFalse(any("gate" in r for r in plan.build(project())["health"]["reasons"]))
        self.sql("UPDATE projects SET stage_entered_at = ? WHERE id = 1", long_ago)
        h = plan.build(project())["health"]
        self.assertIn(f"Due to leave {s[0]}, held by its gate: 1 open task.", h["reasons"])
        self.assertIn(h["rag"], ("amber", "red"))
        internal = report_data.build(project(), "internal")
        self.assertEqual(internal["milestones"][0]["gate"], "1 open task")
        customer = report_data.build(project(), "customer")
        self.assertEqual(customer["health"]["reasons"], [])
        self.assertNotIn("gate", customer["milestones"][0])
        self.assertNotIn("gate", report_data.customer_view(report_data.snapshot(project()))["milestones"][0])


if __name__ == "__main__":
    unittest.main()
