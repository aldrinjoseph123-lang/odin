"""Customer approval, the user's calls of 29 Oct 2026. Run with: python -m unittest test_v2_approver

1. A customer's decline pauses the stage: the next move waits until they approve, unless the
   project manager overrides with a typed reason. "Re-request" asks the approver again. A move
   while a request is still pending goes ahead, but the request is withdrawn and the approver told.
2. One named approver per rollout (projects.approver_id; unset or stale = the first Customer on
   the team): only they decide, and only they hear the requests, the chasers and the switch-on notice.
"""
from datetime import date, timedelta

from test_app import app_module
from test_fix_logic import FixBase

FORM = {"name": "P", "client": "Globex", "customer_approval": "1"}


class ApproverBase(FixBase):
    def setUp(self):
        super().setUp()
        self.new_project(name="P", client="Globex", customer_approval="1")
        self._invite(1, "ann@globex.example", "Customer", "Ann")
        self._invite(1, "bob@globex.example", "Customer", "Bob")
        self._invite(1, "raj@vendor.example", "Contractor", "Raj")
        self.ann, self.bob, self.raj = (self.uid(e) for e in ("ann@globex.example", "bob@globex.example", "raj@vendor.example"))
        self.s = self.stages()

    def uid(self, email):
        return self.sql("SELECT id FROM users WHERE email = ?", email)[0][0]

    def ext(self, email):
        c = self._external_client(email)
        c.environ_base["HTTP_X_CSRF_TOKEN"] = c.get("/api/session").get_json()["csrf"]
        return c

    def move(self, stage, **extra):
        return self.client.post("/api/projects/1/stage", json={"stage": stage, **extra})

    def bells(self, uid, like):
        return self.sql("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND (title LIKE ? OR body LIKE ?)", uid, like, like)[0][0]

    def statuses(self):
        return [r[0] for r in self.sql("SELECT status FROM stage_approvals ORDER BY id")]

    def latest(self):
        return self.sql("SELECT id FROM stage_approvals ORDER BY id DESC LIMIT 1")[0][0]


class OneApproverTestCase(ApproverBase):

    def test_the_first_customer_approves_and_another_customer_waits_on_them(self):
        self.assertEqual(self.client.get("/api/projects/1").get_json()["approver"], {"id": self.ann, "name": "Ann"})
        self.assertEqual(self.move(self.s[1]).status_code, 200)
        self.assertEqual(self.bells(self.ann, "%please approve%"), 1)
        self.assertEqual(self.bells(self.bob, "%please approve%"), 0)     # only the approver is asked
        bob = self.ext("bob@globex.example")
        d = bob.get("/api/projects/1/flow").get_json()
        self.assertEqual((d["can_approve"], d["approver"]["name"], d["approval"]["status"]), (False, "Ann", "pending"))
        self.assertEqual(bob.post(f"/api/projects/1/approvals/{self.latest()}", json={"decision": "approved"}).status_code, 403)
        ann = self.ext("ann@globex.example")
        self.assertTrue(ann.get("/api/projects/1/flow").get_json()["can_approve"])
        self.assertEqual(ann.post(f"/api/projects/1/approvals/{self.latest()}", json={"decision": "approved"}).status_code, 200)

    def test_the_edit_form_names_the_approver_from_the_customer_contacts(self):
        form = self.client.get("/api/project-form?edit=1").get_json()
        self.assertEqual(form["customers"], [{"id": self.ann, "name": "Ann"}, {"id": self.bob, "name": "Bob"}])
        self.assertIsNone(form["project"]["approver_id"])
        self.client.post("/projects/1/edit", data={**FORM, "approver_id": str(self.bob)})
        self.assertEqual(self.sql("SELECT approver_id FROM projects")[0][0], self.bob)
        self.assertEqual(self.client.get("/api/projects/1").get_json()["approver"]["name"], "Bob")
        self.client.post("/projects/1/edit", data={**FORM, "approver_id": str(self.raj)})   # not a Customer: refused
        self.assertEqual(self.sql("SELECT approver_id FROM projects")[0][0], self.bob)
        self.client.post("/projects/1/edit", data=dict(FORM))                                      # no field: kept
        self.assertEqual(self.sql("SELECT approver_id FROM projects")[0][0], self.bob)
        self.client.post("/projects/1/edit", data={**FORM, "approver_id": ""})              # empty: the first Customer
        self.assertIsNone(self.sql("SELECT approver_id FROM projects")[0][0])
        self.assertEqual(self.client.get("/api/projects/1").get_json()["approver"]["name"], "Ann")

    def test_a_new_approver_takes_over_the_open_request(self):
        self.move(self.s[1])
        self.client.post("/projects/1/edit", data={**FORM, "approver_id": str(self.bob)})
        self.assertEqual(self.statuses(), ["superseded", "pending"])
        self.assertEqual(self.bells(self.ann, "No longer needed%"), 1)
        self.assertEqual(self.bells(self.bob, "%please approve%"), 1)

    def test_switching_approval_on_tells_the_approver_only(self):
        self.client.post("/projects/1/edit", data={"name": "P", "client": "Globex"})
        self.client.post("/projects/1/edit", data={**FORM, "approver_id": str(self.bob)})
        self.assertEqual(self.bells(self.bob, "Your approval will be asked%"), 1)
        self.assertEqual(self.bells(self.ann, "Your approval will be asked%"), 0)

    def test_the_approver_leaving_withdraws_the_request_and_clears_the_setting(self):
        self.client.post("/projects/1/edit", data={**FORM, "approver_id": str(self.bob)})
        self.move(self.s[1])
        pp = self.sql("SELECT id FROM project_participants WHERE user_id = ?", self.bob)[0][0]
        self.client.post(f"/projects/1/participants/{pp}/remove")
        self.assertEqual(self.statuses(), ["superseded"])
        self.assertEqual(self.bells(self.bob, "No longer needed: the approver left%"), 1)
        self.assertIsNone(self.sql("SELECT approver_id FROM projects")[0][0])
        self.assertEqual(self.client.get("/api/projects/1").get_json()["approver"]["name"], "Ann")   # the first Customer again

    def test_re_roling_the_approver_away_is_the_same_as_removing_them(self):
        self.move(self.s[1])
        self.client.post("/projects/1/participants/add", data={"user_id": str(self.ann), "role": "Contractor"})
        self.assertEqual(self.statuses(), ["superseded"])
        self.assertEqual(self.bells(self.ann, "No longer needed%"), 1)

    def test_the_chaser_reminds_the_approver_only(self):
        from services import chasers
        self.move(self.s[1])
        self._set_policy(chase_after_days="1", chase_max="3")
        with app_module.app.test_request_context():
            self.assertEqual(chasers.run(today=date.today() + timedelta(days=10)), 1)
        self.assertEqual(self.bells(self.ann, "Reminder%"), 1)
        self.assertEqual(self.bells(self.bob, "Reminder%"), 0)


class DeclinePausesTestCase(ApproverBase):

    def decline(self, comment="Not ready."):
        r = self.ext("ann@globex.example").post(f"/api/projects/1/approvals/{self.latest()}", json={"decision": "declined", "comment": comment})
        self.assertEqual(r.status_code, 200)

    def test_a_decline_holds_the_move_until_overridden_with_a_reason(self):
        self.move(self.s[1])
        self.decline()
        r = self.move(self.s[2])
        self.assertEqual(r.status_code, 409)
        self.assertIn(f"The customer declined {self.s[1]}: Not ready. Ask again, or override with a reason", r.get_json()["error"])
        gate = self.client.get("/api/projects/1/flow").get_json()["gate"]["blocked"]
        self.assertEqual([g["kind"] for g in gate], ["declined"])
        self.assertTrue(any(g["gate_blocked"] for g in self.client.get("/api/flow").get_json()["rows"]))
        self.assertIn(f"The customer declined {self.s[1]}.", self.client.get("/api/projects/1/plan").get_json()["health"]["reasons"])
        self.assertEqual(self.move(self.s[0]).status_code, 200)     # a move back is never held
        self.move(self.s[1])
        self.decline("Still no")
        self.assertEqual(self.move(self.s[2], override="Agreed on the call").status_code, 200)
        self.assertEqual(self.audits("override_stage_gate"), 1)

    def test_re_request_asks_the_approver_again_and_their_approval_lifts_the_hold(self):
        self.move(self.s[1])
        self.decline()
        r = self.client.post("/api/projects/1/approvals/request")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.get_json()["status"], r.get_json()["chases"]), ("pending", 0))
        self.assertEqual(self.statuses(), ["declined", "pending"])
        self.assertEqual(self.bells(self.ann, "%please approve%"), 2)     # the move, then the re-request
        self.assertEqual(self.bells(self.bob, "%please approve%"), 0)
        self.assertEqual(self.audits("approval_requested"), 1)
        self.assertEqual(self.client.post("/api/projects/1/approvals/request").status_code, 400)   # one is open already
        self.assertEqual(self.move(self.s[2]).status_code, 409)     # asked again is not approved: still held
        r = self.ext("ann@globex.example").post(f"/api/projects/1/approvals/{self.latest()}", json={"decision": "approved"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.move(self.s[2]).status_code, 200)

    def test_re_request_is_refused_without_approval_or_an_approver_or_on_the_last_stage(self):
        self.client.post("/projects/1/edit", data={"name": "P", "client": "Globex"})
        self.assertEqual(self.client.post("/api/projects/1/approvals/request").status_code, 400)
        self.client.post("/projects/1/edit", data=dict(FORM))
        self.assertEqual(self.client.post("/api/projects/1/approvals/request").status_code, 200)
        self.sql("DELETE FROM stage_approvals")
        self.sql("DELETE FROM project_participants WHERE role = 'Customer'")
        r = self.client.post("/api/projects/1/approvals/request")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Customer", r.get_json()["error"])

    def test_moving_on_while_pending_withdraws_the_request_and_tells_the_approver(self):
        self.move(self.s[1])
        self.assertEqual(self.move(self.s[2]).status_code, 200)
        self.assertEqual(self.statuses(), ["superseded", "pending"])
        self.assertEqual(self.bells(self.ann, f"No longer needed: the rollout moved on to {self.s[2]}%"), 1)
        self.assertEqual(self.bells(self.bob, "No longer needed%"), 0)

    def test_the_vendor_link_hears_the_customer_declined_not_the_internals(self):
        from services import gates
        self.assertIn("customer declined", gates.guest_message([{"kind": "declined"}]))
        self.assertEqual(gates.guest_message([{"kind": "tasks"}]), gates.GUEST_MESSAGE)
