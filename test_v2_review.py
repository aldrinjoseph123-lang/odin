"""v2.0.0, the user's decisions of 17 Oct 2026. Run with: python -m unittest test_v2_review

1. A file an outside account uploads waits for staff review (services/doc_review.py,
   system-map loophole 65): nobody opens it, and nothing uses it, until the project
   manager accepts it; a reject deletes it, reopens the ask and tells the partner.
2. A partner waiting on the team's work sees nothing about it; only a tick is refused.
3. A repeating task holds a stage gate only while its current occurrence is overdue.

Dates are relative to the frozen clock's today (FixBase.NOW)."""
import io
from unittest.mock import patch

from test_v2_deps import DepsBase
from test_v2_selfserve import PDF, SelfServeBase

J = {"Accept": "application/json"}


class ReviewBase(SelfServeBase):
    def setUp(self):
        super().setUp()
        self.u = self.ask("upload")
        self.c = self.ext("Customer")
        self.assertEqual(self.upload(self.c, self.u).status_code, 200)
        self.doc = self.sql("SELECT id FROM documents WHERE filename = 'scope.pdf'")[0][0]

    def review(self, decision, client=None):
        return (client or self.client).post(f"/projects/1/documents/{self.doc}/review", data={"decision": decision}, headers=J)

    def status(self):
        return self.sql("SELECT review_status FROM documents WHERE id = ?", self.doc)[0][0]

    def download(self, client=None):
        return (client or self.client).get(f"/projects/1/documents/{self.doc}/download")


class HeldUploadTestCase(ReviewBase):

    def test_an_outside_upload_is_held_and_the_ask_is_answered(self):
        self.assertEqual(self.status(), "pending")
        self.assertEqual(self.done(self.u), 1)
        # staff see it marked, the partner's list leaves it out, the ask says it waits
        staff = {d["id"]: d for d in self.client.get("/api/projects/1").get_json()["documents"]}
        self.assertEqual(staff[self.doc]["review"], "pending")
        self.assertNotIn(self.doc, [d["id"] for d in self.c.get("/api/projects/1").get_json()["documents"]])
        self.assertEqual(self.c.get("/api/projects/1/flow").get_json()["documents"], 0)
        ask = next(a for a in self.c.get("/api/projects/1/asks").get_json()["asks"] if a["id"] == self.u)
        self.assertEqual(ask["file"]["review"], "pending")
        # nobody opens it yet, not even an Admin
        self.assertEqual(self.download().status_code, 409)
        self.assertEqual(self.download(self.c).status_code, 409)
        # the project manager hears, worded for review
        body = self.sql("SELECT body FROM notifications WHERE user_id = (SELECT owner_id FROM projects WHERE id = 1) ORDER BY id DESC")[0][0]
        self.assertIn("uploaded a file for review", body)

    def test_a_staff_upload_is_not_held(self):
        r = self.client.post("/projects/1/documents", data={"file": (io.BytesIO(PDF), "ours.pdf"), "category": "Deliverable"}, headers=J)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.sql("SELECT review_status FROM documents WHERE filename = 'ours.pdf'")[0][0], "accepted")
        self.assertEqual(self.sql("SELECT review_status FROM documents WHERE category = 'Client PO'")[0][0], "accepted")

    def test_a_held_file_is_kept_out_of_reports_signoff_gates_search_and_onedrive(self):
        self.ctx()
        from db import get_db
        from services import doctext, gates, report_data, signoff
        project = get_db().execute("SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.id = 1").fetchone()
        self.assertNotIn("scope.pdf", [d["filename"] for d in report_data.build(project, "internal")["documents"]])
        self.assertEqual(doctext.text_of(self.doc), ("", "not reviewed yet"))
        names = self.stages()
        self.sql("UPDATE project_stages SET required_docs = '[\"Deliverable\"]' WHERE project_id = 1 AND name = ?", names[0])
        self.assertEqual([r["text"] for r in gates.blocked(project, names[1])], ["Deliverable awaiting review"])
        self.assertNotIn("scope.pdf", str(signoff.draft(project)))   # the sign-off's "Delivered:" lines
        self.assertEqual(self.review("accept").status_code, 200)
        self.assertEqual(gates.blocked(project, names[1]), [])

    def test_a_held_file_reaches_onedrive_only_once_accepted(self):
        self._set_policy(onedrive_mirror_uploads_enabled="1")
        with patch("routes.projects.graph.upload_file", return_value=(True, None)) as up:
            self.upload(self.c, self.ask("upload", title="Second file"), name="two.pdf")
            self.assertEqual(up.call_count, 0)
            self.assertEqual(self.review("accept").status_code, 200)
            self.assertEqual(up.call_count, 1)


class DecisionTestCase(ReviewBase):

    def test_accept_makes_it_a_normal_document(self):
        self.assertEqual(self.review("accept").status_code, 200)
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.sql("SELECT reviewed_by IS NOT NULL, reviewed_at IS NOT NULL FROM documents WHERE id = ?", self.doc)[0][:], (1, 1))
        self.assertEqual(self.download().status_code, 200)
        self.assertEqual(self.download(self.c).status_code, 200)
        self.assertIn(self.doc, [d["id"] for d in self.c.get("/api/projects/1").get_json()["documents"]])
        self.assertEqual(self.audits("accept_document"), 1)
        self.assertEqual(self.review("accept").status_code, 404)   # decided once

    def test_reject_deletes_it_reopens_the_ask_and_tells_the_partner(self):
        self.assertEqual(self.review("reject").status_code, 200)
        self.assertIsNotNone(self.sql("SELECT deleted_at FROM documents WHERE id = ?", self.doc)[0][0])
        self.assertEqual(self.done(self.u), 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM task_answers WHERE task_id = ?", self.u)[0][0], 0)
        told = self.sql("SELECT title FROM notifications WHERE user_id = ?", self.people["Customer"])
        self.assertTrue(any("Upload again" in r[0] for r in told))
        self.assertEqual(self.audits("reject_document"), 1)
        self.assertEqual(self.review("reject").status_code, 404)
        self.assertEqual(self.upload(self.c, self.u, name="again.pdf").status_code, 200)   # they upload again

    def test_only_who_manages_the_documents_decides(self):
        self.assertEqual(self.review("accept", self.c).status_code, 403)
        _, member, headers = self.member("mo")
        self.assertEqual(member.post(f"/projects/1/documents/{self.doc}/review", data={"decision": "accept"}, headers=headers).status_code, 403)
        self.assertEqual(self.review("maybe").status_code, 400)
        self.assertEqual(self.status(), "pending")

    def test_documents_from_before_count_as_accepted(self):
        import db as db_module
        with self.raw_db() as con:
            con.execute("ALTER TABLE documents DROP COLUMN reviewed_at")
            con.execute("ALTER TABLE documents DROP COLUMN reviewed_by")
            con.execute("ALTER TABLE documents DROP COLUMN review_status")
            db_module.migrate_db(con)
            con.commit()
            self.assertEqual({r[0] for r in con.execute("SELECT review_status FROM documents")}, {"accepted"})


class HiddenWaitTestCase(DepsBase):
    """2: the team's work that holds a partner's task is not shown to them at all."""

    def test_the_partner_sees_the_task_normally_and_only_the_tick_says_why(self):
        self.new_project()
        self._set_policy(external_domains="vendor.example")
        self._invite(1, "cus@vendor.example", "Customer", "Cus")
        cid = self.sql("SELECT id FROM users WHERE email = 'cus@vendor.example'")[0][0]
        team = self.task("Internal escalation")
        mine = self.task("Customer signs form", assignee_id=cid)
        self.edit(mine, waits_on=[team])
        c = self._external_client("cus@vendor.example")
        self.assertEqual(self.flow_task(mine, c)["blocked_by"], [])
        self.assertEqual(next(t for t in c.get("/api/my-work").get_json()["tasks"] if t["id"] == mine)["blocked_by"], [])
        self.assertEqual([w["title"] for w in self.flow_task(mine)["blocked_by"]], ["Internal escalation"])   # staff still see it
        csrf = c.get("/api/session").get_json()["csrf"]
        r = c.post(f"/projects/1/tasks/{mine}/toggle", json={"done": True}, headers={"X-CSRF-Token": csrf, **J})
        self.assertEqual(r.get_json()["error"], "This waits on work the team has not finished yet")


class RepeatGateTestCase(DepsBase):
    """3: a repeating task holds the gate only while its current occurrence is overdue."""

    def test_overdue_repeat_holds_the_gate_with_its_name(self):
        self.new_project()
        names = self.stages()
        self.sql("UPDATE project_stages SET gate_tasks = 1 WHERE project_id = 1 AND name = ?", names[0])
        t = self.task("Weekly status call", due_date=self.day(2), recurrence="weekly")
        self.ctx()
        from db import get_db
        from services import gates
        project = get_db().execute("SELECT * FROM projects WHERE id = 1").fetchone()
        self.assertEqual(gates.blocked(project, names[1]), [])            # due ahead: it does not hold
        self.sql("UPDATE tasks SET due_date = ? WHERE id = ?", self.day(0), t)
        self.assertEqual(gates.blocked(project, names[1]), [])            # due today is not overdue yet
        self.sql("UPDATE tasks SET due_date = ? WHERE id = ?", self.day(-1), t)
        self.assertEqual([r["text"] for r in gates.blocked(project, names[1])], ["Weekly status call is overdue"])
        self.task("One-off")
        self.assertEqual([r["text"] for r in gates.blocked(project, names[1])], ["1 open task", "Weekly status call is overdue"])


if __name__ == "__main__":
    import unittest
    unittest.main()
