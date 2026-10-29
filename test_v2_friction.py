"""Friction the 28 Oct simulation's directors felt (docs/simulation-2026-10-28.md). Run with: python -m unittest test_v2_friction

1. Missing notices: a held upload accepted, an existing account invited, customer approval switched on,
   a chaser that reached chase_max.
2. The approval API names the two words it takes.
3. Creating a rollout and then setting a team member's role says "You are on …" once.
4. An outsider keeps the rollouts that closed (/api/flow "closed"); staff do not get the key.
5. Alerts take mine=1.
6. No plan saved: health is "none" (No plan yet) unless something real is wrong.
"""
from datetime import date, timedelta

import app as app_module
from test_v2_review import ReviewBase

J = {"Accept": "application/json"}


class MissingNoticesTestCase(ReviewBase):

    def titles(self, uid, like):
        return [r[0] for r in self.sql("SELECT title FROM notifications WHERE user_id = ? AND title LIKE ? ORDER BY id", uid, like)]

    def test_the_uploader_hears_when_a_held_upload_is_accepted(self):
        cus = self.people["Customer"]
        self.assertEqual(self.titles(cus, "Accepted:%"), [])
        self.assertEqual(self.review("accept").status_code, 200)
        self.assertEqual(self.titles(cus, "Accepted:%"), ["Accepted: scope.pdf"])

    def test_inviting_an_existing_account_leaves_a_bell_item_but_a_new_one_has_its_link(self):
        self.assertEqual(self.new_project(name="Second", client="Initech").status_code, 302)
        self._invite(2, "customer@outside.example", "Customer", "Customer Person")   # already an account, from rollout 1
        self.assertEqual(self.titles(self.people["Customer"], "You are on Second%"), ["You are on Second"])
        self._invite(2, "brandnew@outside.example", "Customer", "Brand New")
        new = self.sql("SELECT id FROM users WHERE email = 'brandnew@outside.example'")[0][0]
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE user_id = ?", new)[0][0], 0)

    def test_switching_customer_approval_on_tells_the_customers_once(self):
        form = {"name": "Globex EDR", "client": "Globex", "owner_id": "1", "delivery_mode": "Distribution/MSSP"}
        cus = self.people["Customer"]
        self.client.post("/projects/1/edit", data=form)
        self.assertEqual(self.titles(cus, "Your approval will be asked%"), [])
        self.client.post("/projects/1/edit", data={**form, "customer_approval": "1"})
        self.assertEqual(self.titles(cus, "Your approval will be asked%"), ["Your approval will be asked on Globex EDR"])
        self.client.post("/projects/1/edit", data={**form, "customer_approval": "1"})   # saved again, still on: no second notice
        self.assertEqual(len(self.titles(cus, "Your approval will be asked%")), 1)

    def run_on(self, day):
        from services import chasers
        with app_module.app.test_request_context():
            return chasers.run(today=day)

    def test_the_project_manager_hears_once_when_the_last_reminder_goes(self):
        cus = self.people["Customer"]
        self.sql("INSERT INTO signoffs (project_id, version, status, content, content_hash, created_by, created_at, signer_id) "
                 "VALUES (1, 1, 'sent', '{}', 'h', 'admin', '2026-11-02T09:00:00', ?)", cus)
        self._set_policy(chase_after_days="3", chase_max="2")
        pm = "SELECT COUNT(*) FROM notifications WHERE user_id = 1 AND title LIKE 'No answer%'"
        self.assertEqual(self.run_on(date(2026, 11, 5)), 1)
        self.assertEqual(self.sql(pm)[0][0], 0)                       # one of two sent: still chasing
        self.sql("UPDATE signoffs SET chased_at = '2026-11-05T08:00:00'")
        self.assertEqual(self.run_on(date(2026, 11, 10)), 1)
        self.assertEqual(self.sql(pm)[0][0], 1)                       # the cap: the PM is told
        self.assertEqual(self.run_on(date(2026, 11, 30)), 0)          # nothing more goes, so nothing more is said
        self.assertEqual(self.sql(pm)[0][0], 1)

    def test_an_unanswered_approval_tells_the_project_manager_too(self):
        stage = self.sql("SELECT stage FROM projects WHERE id = 1")[0][0]
        self.sql("INSERT INTO stage_approvals (project_id, stage, requested_by, requested_at) VALUES (1, ?, 'admin', '2026-11-02T09:00:00')", stage)
        self._set_policy(chase_after_days="3", chase_max="1")
        self.assertEqual(self.run_on(date(2026, 11, 5)), 1)
        self.assertEqual(self.sql("SELECT title FROM notifications WHERE user_id = 1 AND title LIKE 'No answer%'")[0][0],
                         "No answer to the approval of Globex EDR")


class WordsAndDuplicatesTestCase(ReviewBase):

    def test_the_approval_error_names_the_two_words(self):
        stage = self.sql("SELECT stage FROM projects WHERE id = 1")[0][0]
        self.sql("INSERT INTO stage_approvals (project_id, stage, requested_by, requested_at) VALUES (1, ?, 'admin', '2026-11-02T09:00:00')", stage)
        aid = self.sql("SELECT id FROM stage_approvals")[0][0]
        r = self.ext("Customer").post(f"/api/projects/1/approvals/{aid}", json={"decision": "maybe"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("approved", r.get_json()["error"])
        self.assertIn("declined", r.get_json()["error"])

    def test_create_then_set_the_role_says_you_are_on_once(self):
        uid, _, _ = self.member("mo")
        self.new_project(name="Third", client="Initech", team_user_ids=[str(uid)])
        like = "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND title LIKE 'You are on Third%'"
        self.assertEqual(self.sql(like, uid)[0][0], 1)                                    # at create, as a Coordinator
        self.client.post("/projects/2/participants/add", data={"user_id": str(uid), "role": "Sales"})
        self.assertEqual(self.sql("SELECT role FROM project_participants WHERE project_id = 2 AND user_id = ?", uid)[0][0], "Sales")
        self.assertEqual(self.sql(like, uid)[0][0], 1)                                    # the role change in the same minute is not a second
        self.sql("UPDATE notifications SET created_at = '2020-01-01T00:00:00' WHERE user_id = ?", uid)
        self.client.post("/projects/2/participants/add", data={"user_id": str(uid), "role": "Coordinator"})
        self.assertEqual(self.sql(like, uid)[0][0], 2)                                    # a change long after still is told


class ClosedForOutsidersTestCase(ReviewBase):

    def close_it(self):
        c, csrf = self._api_client()
        self.sql("INSERT INTO settings (key, value) VALUES ('policy.signoff_required', '0')")
        r = c.post("/api/projects/1/stage", json={"stage": self.stages()[-1]}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 200, r.get_json())

    def test_an_outsider_sees_their_closed_rollouts_and_staff_get_no_such_key(self):
        before = self.ext("Customer").get("/api/flow").get_json()
        self.assertEqual([r["id"] for r in before["rows"]], [1])
        self.assertEqual(before["closed"], [])
        self.close_it()
        after = self.ext("Customer").get("/api/flow").get_json()
        self.assertEqual(after["rows"], [])
        self.assertEqual([(c["id"], c["name"], c["signed_off"], c["report"]) for c in after["closed"]], [(1, "Globex EDR", False, False)])
        self.assertRegex(after["closed"][0]["closed_on"], r"^\d{4}-\d\d-\d\d$")
        self.assertNotIn("closed", self.client.get("/api/flow").get_json())
        # off the team, it is no longer theirs to list
        self.sql("DELETE FROM project_participants WHERE project_id = 1 AND user_id = ?", self.people["Customer"])
        self.assertEqual(self.ext("Customer").get("/api/flow").get_json()["closed"], [])


class AlertsMineTestCase(ReviewBase):

    def test_mine_narrows_the_alerts_to_rollouts_the_reader_is_on(self):
        self.sql("INSERT INTO alerts (alert_type, project_id, title, severity, created_at) VALUES ('overdue', 1, 'Late', 'critical', '2026-10-01T00:00:00')")
        _, other, _ = self.member("mo")
        self.assertEqual(self.client.get("/api/alerts?mine=1").get_json()["total"], 1)     # the owner's
        self.assertEqual(other.get("/api/alerts").get_json()["total"], 1)
        self.assertEqual(other.get("/api/alerts?mine=1").get_json()["total"], 0)           # not on it
        uid = self.sql("SELECT id FROM users WHERE username = 'mo'")[0][0]
        self.sql("INSERT INTO project_participants (project_id, user_id, role, added_at) VALUES (1, ?, 'Coordinator', datetime('now'))", uid)
        self.assertEqual(other.get("/api/alerts?mine=1").get_json()["total"], 1)


class NoPlanYetTestCase(ReviewBase):

    def plan(self, client=None):
        return (client or self.client).get("/api/projects/1/plan").get_json()

    def test_health_waits_for_a_plan_but_real_trouble_still_shows(self):
        soon = (date.today() + timedelta(days=1)).isoformat()
        self.sql("UPDATE projects SET target_end_date = ? WHERE id = 1", soon)
        p = self.plan()
        self.assertFalse(p["has_plan"])
        self.assertEqual(p["health"]["rag"], "none")          # the template's default lengths overshoot a near target: not "Off track"
        self.assertEqual(self.plan(self.ext("Customer"))["health"]["rag"], "none")   # the customer's page reads the same word
        # a plan, and the forecast speaks again
        for i, (sid,) in enumerate(self.sql("SELECT id FROM project_stages WHERE project_id = 1 ORDER BY position")):
            day = (date.today() + timedelta(days=i)).isoformat()
            self.sql("UPDATE project_stages SET plan_start = ?, plan_end = ? WHERE id = ?", day, day, sid)
        self.assertNotEqual(self.plan()["health"]["rag"], "none")
        # no plan, but a date already past is a fact
        self.sql("UPDATE project_stages SET plan_start = NULL, plan_end = NULL WHERE project_id = 1")
        self.sql("UPDATE projects SET target_end_date = ? WHERE id = 1", (date.today() - timedelta(days=3)).isoformat())
        self.assertEqual(self.plan()["health"]["rag"], "red")
