"""v1.8.0 fixes to projects, the API and the lifecycle (review 14 Oct 2026:
P2-6, P2-10, P2-18, P2-26, P2-27, P2-28, P3-2, P3-14, P3-17 to P3-24, P3-29,
A12). Run with: python -m unittest test_v18_projects"""
import io
from datetime import datetime, timedelta

import test_app
from test_app import STRONG_PASSWORD, app_module
from test_fix_logic import FixBase

J = {"Accept": "application/json"}


class V18Base(FixBase):
    _make_user = test_app.ContactsAndProjectMetaTestCase._make_user

    def client_for(self, username):
        c, csrf = self._api_client(username, STRONG_PASSWORD)
        return c, {"X-CSRF-Token": csrf, **J}

    def put(self, url, body):
        return self.client.put(url, json=body, headers={"X-CSRF-Token": self.client.get("/api/session").get_json()["csrf"]})

    def audits(self, action):
        return self.sql("SELECT COUNT(*) FROM audit_logs WHERE action = ?", action)[0][0]

    def task(self, title="T", assignee=None, due=None):
        self.client.post("/projects/1/tasks", json={"title": title, "assignee_id": assignee, "due_date": due})
        return self.sql("SELECT MAX(id) FROM tasks")[0][0]


class GuestLinkExpiryTestCase(V18Base):   # P2-6
    def test_links_expire_and_a_rotation_renews_them(self):
        self.new_project(name="P", client="C")
        token = self.sql("SELECT customer_token FROM projects")[0][0]
        anon = app_module.app.test_client()
        self.assertEqual(anon.get(f"/guest/{token}").status_code, 200)
        self.assertTrue(self.client.get("/api/projects/1").get_json()["guest_links_expire"])
        self.sql("UPDATE projects SET created_at = ?", (datetime.utcnow() - timedelta(days=181)).isoformat())
        r = anon.get(f"/guest/{token}")
        self.assertEqual(r.status_code, 410); self.assertIn(b"expired", r.data)
        self.client.post("/projects/1/rotate-token")
        token = self.sql("SELECT customer_token FROM projects")[0][0]
        self.assertEqual(anon.get(f"/guest/{token}").status_code, 200)   # rotated: a fresh 180 days
        self._set_policy(guest_link_days="0")
        self.sql("UPDATE projects SET guest_tokens_at = '2000-01-01T00:00:00'")
        self.assertEqual(anon.get(f"/guest/{token}").status_code, 200)   # 0: never
        self.assertIsNone(self.client.get("/api/projects/1").get_json()["guest_links_expire"])


class TaskRulesTestCase(V18Base):   # P2-10, P2-26, P3-18
    def test_an_assignee_ticks_but_only_a_task_manager_re_dates(self):
        self.new_project(name="P", client="C")
        vw = self._make_user("vw", "Viewer")
        tid = self.task(assignee=vw, due="2026-11-01")
        c, h = self.client_for("vw")
        self.assertEqual(c.post(f"/projects/1/tasks/{tid}/edit", json={"due_date": "2026-12-01"}, headers=h).status_code, 403)
        self.assertEqual(c.post(f"/projects/1/tasks/{tid}/toggle", json={"done": True}, headers=h).get_json()["done"], True)
        cal = c.get("/api/calendar?month=2026-11").get_json()["tasks"]
        self.assertFalse(any(t["can_edit"] for t in cal))
        # the manager may move a done task, and the calendar says so (P3-18)
        self.assertTrue(all(t["can_edit"] for t in self.client.get("/api/calendar?month=2026-11").get_json()["tasks"]))
        self.assertEqual(self.client.post(f"/projects/1/tasks/{tid}/edit", json={"due_date": "2026-11-02"}, headers=J).status_code, 200)

    def test_a_tick_sets_the_state_it_was_sent(self):
        self.new_project(name="P", client="C")
        tid = self.task()
        for _ in range(2):   # two tabs both ticking: done, once
            self.assertEqual(self.client.post(f"/projects/1/tasks/{tid}/toggle", json={"done": True}).get_json(), {"ok": True, "done": True})
        self.assertEqual(self.audits("toggle_task"), 1)
        self.assertEqual(self.client.post(f"/projects/1/tasks/{tid}/toggle", json={"done": False}).get_json()["done"], False)
        self.assertEqual(self.client.post(f"/projects/1/tasks/{tid}/toggle", json={"done": "yes"}).status_code, 400)


class StageMoveTestCase(V18Base):   # P2-26, P3-2, P3-24
    def test_a_move_from_a_stale_view_is_a_409(self):
        self.new_project(name="P", client="C")
        s = self.stages()
        ok = self.client.post("/api/projects/1/stage", json={"stage": s[2], "from_stage": s[0]})
        self.assertEqual(ok.status_code, 200)
        stale = self.client.post("/api/projects/1/stage", json={"stage": s[1], "from_stage": s[0]})   # a tab still showing the first stage
        self.assertEqual(stale.status_code, 409); self.assertIn("moved on", stale.get_json()["error"])
        self.assertEqual(self.sql("SELECT stage FROM projects")[0][0], s[2])
        self.assertEqual(self.client.post("/api/projects/1/stage", json={"stage": s[2]}).status_code, 409)   # already there

    def test_an_undo_runs_once(self):
        self.new_project(name="P", client="C")
        s = self.stages()
        undo = self.client.post("/api/projects/1/stage", json={"stage": s[1]}).get_json()["undo"]
        self.client.post(undo)
        self.assertEqual(self.client.post(undo, headers=J).status_code, 400)
        self.assertEqual((self.sql("SELECT stage FROM projects")[0][0], self.audits("undo_project_stage")), (s[0], 1))

    def test_reopening_sets_the_sign_off_aside(self):
        from services import signoff
        self.new_project(name="P", client="C")
        s = self.stages()
        self.sql("UPDATE projects SET stage = ?", s[-2])
        self.assertEqual(self.client.post("/api/projects/1/signoff/waive", json={"reason": "Signed on paper at the site"}).status_code, 200)
        self.assertEqual(self.client.post("/api/projects/1/stage", json={"stage": s[-1]}).status_code, 200)
        undo = self.client.post("/api/projects/1/stage", json={"stage": s[1]}).get_json()["undo"]   # reopened
        self.ctx()
        self.assertIsNone(signoff.completed(1))
        self.assertTrue(self.sql("SELECT superseded_at FROM signoffs")[0][0])   # kept, set aside
        self.client.post(undo)   # undoing the reopen brings it back
        self.assertIsNotNone(signoff.completed(1))
        self.client.post("/api/projects/1/stage", json={"stage": s[-2]})
        r = self.client.post("/api/projects/1/stage", json={"stage": s[-1]})
        self.assertEqual(r.status_code, 400); self.assertIn("sign-off", r.get_json()["error"])   # the gate asks for a new one


class ShapesTestCase(V18Base):   # P2-27, P2-28
    def test_wrong_shapes_are_400s_not_repr_truncation_or_500s(self):
        self.new_project(name="P", client="C")
        sid = self.sql("SELECT id FROM project_stages ORDER BY position")[0][0]
        post = self.client.post
        self.assertEqual(post("/api/projects/1/scope", json={"title": ["a", "b"]}).status_code, 400)
        self.assertEqual(post("/api/projects/1/scope", json={"title": "x" * 5000}).status_code, 400)
        self.assertEqual(post("/projects/1/tasks", json={"title": "x" * 300}).status_code, 400)
        self.assertEqual(post("/api/projects/1/raid", json={"kind": "risk", "title": "x" * 300}).status_code, 400)
        for body in ({"stages": "x"}, {"stages": [{"id": [sid]}]}, {"stages": [{"id": 99999}]}, {"stages": [], "reason": ["r"]}):
            r = self.put("/api/projects/1/plan", body)
            self.assertEqual(r.status_code, 400, body); self.assertNotIn("CSRF", r.get_json()["error"])
        self.assertEqual(self.put("/api/dashboard/layout", {"layout": [{"id": ["kpis"]}, {"id": "kpis", "w": 10 ** 400}]}).get_json()["layout"][0]["w"], 3)
        self.assertEqual(self.client.get(f"/api/projects/1/signoff?v={10 ** 30}").status_code, 200)   # no such version: the latest
        self.assertEqual(self.client.get(f"/projects/1/signoff.pdf?v={10 ** 30}").status_code, 404)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM scope_items")[0][0], 0)

    def test_stored_python_lists_are_spelled_as_text(self):
        import db as db_module
        self.new_project(name="P", client="C")
        self.sql("INSERT INTO scope_items (project_id, position, title, detail, status, note, created_by, created_at, updated_at) "
                 "VALUES (1, 0, \"['a', 'b']\", '[Phase 1]', 'agreed', NULL, 'x', 'now', 'now')")
        with self.raw_db() as db:
            db_module._migrate_scope_repr(db); db.commit()
        self.assertEqual(tuple(self.sql("SELECT title, detail FROM scope_items")[0]), ("a, b", "[Phase 1]"))

    def test_v1_report_carries_the_whole_report(self):
        self.new_project(name="P", client="C")
        self.client.post("/api/projects/1/rollout-report", json={"summary": "On track", "next_steps": "Ship", "asks": "Access"})
        with self.raw_db() as db:
            db.execute("INSERT INTO api_tokens (name, token_hash, created_by, created_at, expires_at) VALUES ('t', ?, 'admin', '2026-01-01', '2100-01-01')",
                       (__import__("security").token_hash("secret-token"),))
            db.commit()
        r = app_module.app.test_client().get("/api/v1/projects/1/report", headers={"Authorization": "Bearer secret-token"}).get_json()
        self.assertEqual((r["summary"], r["next_steps"], r["asks"]), ("On track", "Ship", "Access"))
        self.assertIn("health", r["data"])


class AccessTestCase(V18Base):   # P3-14, P3-17, P3-19
    def test_small_permission_gaps_are_closed(self):
        self.new_project(name="P", client="C")
        self._invite(1, "jane@vendor.example", "Contractor", "Jane")
        jane = self._external_client("jane@vendor.example")
        self.assertEqual(jane.get("/api/doc-templates/choices?kind=rollout").status_code, 403)
        self.assertEqual(jane.get("/api/dashboard/version").status_code, 403)
        # a viewer whose note predates the role change cannot edit it: the matrix's note right applies
        vw = self._make_user("vw", "Viewer")
        self.sql("INSERT INTO status_notes (project_id, author, note, stage, created_at, author_id) VALUES (1, 'vw', 'hi', 'x', 'now', ?)", vw)
        nid = self.sql("SELECT MAX(id) FROM status_notes")[0][0]
        c, h = self.client_for("vw")
        self.assertEqual(c.post(f"/projects/1/notes/{nid}/edit", data={"note": "changed"}, headers=h).status_code, 403)
        # an external account added by id passes the partner-domain rule, as an invite does
        uid = self.sql("SELECT id FROM users WHERE email = 'jane@vendor.example'")[0][0]
        self.new_project(name="Q", client="C")
        self._set_policy(external_domains="partner.example")
        r = self.client.post("/projects/2/participants/add", data={"user_id": uid, "role": "Contractor"}, headers=J)
        self.assertEqual(r.status_code, 400); self.assertIn("partner.example", r.get_json()["error"])

    def test_exports_and_pdfs_are_audited(self):
        self.new_project(name="P", client="C")
        self.client.get("/projects/export.csv")
        self.client.get("/projects/1/report.pdf")
        self.client.get("/reports/all.pdf")
        self.assertEqual([self.audits(a) for a in ("export_projects", "download_report", "download_portfolio_report")], [1, 1, 1])

    def test_nothing_to_delete_or_restore_is_not_a_success(self):
        self.new_project(name="P", client="C")
        self.assertEqual(self.client.post("/projects/1/documents/999/delete", headers=J).status_code, 404)
        self.assertEqual(self.client.post("/undo/contact/vendors/999", headers=J).status_code, 404)
        self.client.post("/settings/contacts/vendors/add", data={"name": "Acme"})
        vid = self.sql("SELECT id FROM vendors")[0][0]
        self.client.post(f"/settings/contacts/vendors/{vid}/delete")
        self.sql("UPDATE vendors SET deleted_at = '2000-01-01T00:00:00'")
        self.assertEqual(self.client.post(f"/undo/contact/vendors/{vid}", headers=J).status_code, 409)
        self.assertEqual(self.audits("restore_contact"), 0)

    def test_a_deleted_name_can_be_used_again(self):   # P2-18
        self.client.post("/settings/contacts/vendors/add", data={"name": "Acme"})
        vid = self.sql("SELECT id FROM vendors")[0][0]
        self.client.post(f"/settings/contacts/vendors/{vid}/delete")
        self.assertEqual(self.client.post("/settings/contacts/vendors/add", data={"name": "acme"}, headers=J).status_code, 200)
        self.assertEqual(self.client.post(f"/undo/contact/vendors/{vid}", headers=J).status_code, 200)   # the old one still comes back
        self.assertEqual(len(self.sql("SELECT 1 FROM vendors WHERE deleted_at IS NULL")), 2)


class TeamAndSignalsTestCase(V18Base):   # P3-20, P3-21, P3-22, P3-23, P3-29, A12
    def test_every_mention_counts(self):
        from routes.projects import mentions_in
        self.new_project(name="P", client="C")
        ann = self._make_user("ann", "Member"); annabel = self._make_user("annabel", "Member")
        for uid in (ann, annabel):
            self.sql("INSERT INTO project_participants (project_id, user_id, role, added_at) VALUES (1, ?, 'Coordinator', 'now')", uid)
        self.ctx()
        self.assertEqual(set(mentions_in(1, "@annabel and @ann, please")), {ann, annabel})

    def test_baseline_slip_turns_amber_past_the_amber_line(self):
        from datetime import date
        from services.plan import _health
        self.ctx()
        h = _health({}, [], 0, {"vs_target_days": None, "target": None, "vs_baseline_days": 3}, [], date(2026, 10, 15), False, True)
        self.assertEqual(h["rag"], "amber")

    def test_the_longest_wait_on_the_customer_comes_first(self):
        from services import dashboard
        for name in ("Alpha", "Beta"):
            self.new_project(name=name, client="C")
        old, new = [(datetime.utcnow() - timedelta(days=d)).isoformat() for d in (9, 2)]
        self.sql("INSERT INTO stage_approvals (project_id, stage, requested_by, requested_at) VALUES (1, (SELECT stage FROM projects WHERE id = 1), 'x', ?), "
                 "(2, (SELECT stage FROM projects WHERE id = 2), 'x', ?)", new, old)
        self.sql("UPDATE projects SET customer_approval = 1")
        self.ctx()
        att = [e["name"] for e in dashboard.build(("", []), 1)["data"]["attention"] if e["worst"] == "awaiting"]
        self.assertEqual(att, ["Beta", "Alpha"])

    def test_removing_a_partner_or_the_customer_leaves_nothing_hanging(self):
        self.new_project(name="P", client="C", customer_approval="1")
        self._invite(1, "jane@vendor.example", "Contractor", "Jane")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        jane = self.sql("SELECT id FROM users WHERE email = 'jane@vendor.example'")[0][0]
        tid = self.task(assignee=jane)
        self.client.post("/api/projects/1/stage", json={"stage": self.stages()[1]})
        for email in ("jane@vendor.example", "ann@acme.example"):
            pid = self.sql("SELECT pp.id FROM project_participants pp JOIN users u ON u.id = pp.user_id WHERE u.email = ?", email)[0][0]
            self.client.post(f"/projects/1/participants/{pid}/remove")
        self.assertEqual(self.sql("SELECT assignee_id FROM tasks WHERE id = ?", tid)[0][0], 1)   # to the project manager
        self.assertEqual(self.sql("SELECT status FROM stage_approvals")[0][0], "superseded")
        self.assertIn("moved to the project manager", self.sql("SELECT details FROM audit_logs WHERE action = 'remove_participant' ORDER BY id")[0][0])

    def test_the_signed_copy_is_found_by_id(self):
        from services import signoff
        self.new_project(name="P", client="C")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        s = self.stages()
        self.sql("UPDATE projects SET stage = ?", s[-2])
        ann = self.sql("SELECT id FROM users WHERE email = 'ann@acme.example'")[0][0]
        r = self.client.post("/api/projects/1/signoff", json={"signer_id": ann, "counter_id": 1, "summary": "Done", "delivered": ["All of it"]})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.client.post("/projects/1/documents", data={"file": (io.BytesIO(b"%PDF-1.4 x"), "signed.pdf"), "category": "Deliverable"})
        today = datetime.utcnow().date().isoformat()
        self.client.post("/api/projects/1/signoff/1/upload", data={"file": (io.BytesIO(b"%PDF-1.4 y"), "signed.pdf"), "signer_name": "Ann", "signed_on": today})
        self.ctx()
        doc = signoff.completed(1)["document_id"]
        self.assertEqual(self.sql("SELECT category FROM documents WHERE id = ?", doc)[0][0], "Sign-off")

    def test_partner_accounts_end_when_their_work_ends(self):
        from services.partner_access import end_dormant
        self.new_project(name="P", client="C")
        self._invite(1, "jane@vendor.example", "Contractor", "Jane")
        s = self.stages()
        self.sql("UPDATE projects SET stage = ?, stage_entered_at = ?", s[-1], (datetime.utcnow() - timedelta(days=40)).isoformat())
        self.ctx()
        self.assertEqual(end_dormant(), 0)   # off by default
        self._set_policy(external_access_days_after_close="30")
        self.assertEqual(end_dormant(), 1)
        self.assertEqual(self.sql("SELECT active FROM users WHERE email = 'jane@vendor.example'")[0][0], 0)
        self.assertEqual(self.audits("set_user_active"), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
