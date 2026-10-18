"""Security and robustness fixes (October 2026 test round): one test per
finding, named after it. Uses test_app's harness; run with
`python -m unittest test_fix_security`."""
import io
import json
import sqlite3
import unittest
from datetime import datetime
from unittest.mock import patch

import app as app_module
import db as db_module
import test_app as T
from test_app import STRONG_PASSWORD, FakeAIServer, flashed


class Base(unittest.TestCase):
    setUp = T.ContactsAndProjectMetaTestCase.setUp
    tearDown = T.ContactsAndProjectMetaTestCase.tearDown
    new_project = T.ContactsAndProjectMetaTestCase.new_project
    raw_db = T.ContactsAndProjectMetaTestCase.raw_db
    _make_user = T.ContactsAndProjectMetaTestCase._make_user
    _invite = T.ContactsAndProjectMetaTestCase._invite
    _link_for = T.ContactsAndProjectMetaTestCase._link_for
    _external_client = T.ContactsAndProjectMetaTestCase._external_client
    _api_client = T.ContactsAndProjectMetaTestCase._api_client
    _signoff_setup = T.ContactsAndProjectMetaTestCase._signoff_setup

    def csrf(self, client=None):
        return {"X-CSRF-Token": (client or self.client).get("/api/session").get_json()["csrf"]}

    def login_as(self, username, password=STRONG_PASSWORD):
        c = app_module.app.test_client()
        c.post("/login", data={"username": username, "password": password})
        return c

    def uid(self, email):
        with self.raw_db() as db:
            return db.execute("SELECT id FROM users WHERE lower(email)=?", (email,)).fetchone()[0]


class SharedHelpersTest(Base):
    def test_parse_date(self):
        from core import parse_date
        self.assertEqual(parse_date(" 2026-10-31 "), "2026-10-31")
        self.assertIsNone(parse_date("")); self.assertIsNone(parse_date(None)); self.assertIsNone(parse_date("  "))
        for bad in ("2026-13-01", "20261031", "2026-W44", "1999-12-31", "2101-01-01", "٢٠٢٦-١٠-٣١", ["2026-10-31"], 5):
            with self.assertRaises(ValueError):
                parse_date(bad)

    def test_as_id(self):
        from core import as_id
        self.assertEqual(as_id("7"), 7); self.assertEqual(as_id(7), 7)
        for bad in (True, False, 0, -1, 2 ** 63, "²", "1.5", 1.0, [1], None, "", "abc"):
            self.assertIsNone(as_id(bad), bad)

    def test_huge_int_in_url_is_a_404(self):   # F-H3
        self.assertEqual(self.client.get(f"/api/projects/{2 ** 70}").status_code, 404)
        self.assertEqual(self.client.get(f"/projects/{2 ** 64}").status_code, 404)

    def test_json_body_that_is_not_an_object_is_a_400(self):   # F-M1
        h = self.csrf()
        for body in ([1], "x", 5):
            r = self.client.post("/api/notifications/read", json=body, headers=h)
            self.assertEqual(r.status_code, 400)
            self.assertIn("error", r.get_json())

    def test_api_errors_are_json_and_csrf_failure_carries_a_token(self):   # F-M9
        r = self.client.get("/api/projects/999")
        self.assertEqual(r.status_code, 404); self.assertIn("error", r.get_json())
        r = self.client.post("/api/notifications/read", json={"all": True}, headers={"X-CSRF-Token": "wrong"})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertTrue(body["csrf"]); self.assertIn("CSRF", body["error"])
        self.assertEqual(self.client.post("/api/notifications/read", json={"all": True}, headers={"X-CSRF-Token": body["csrf"]}).status_code, 200)
        # a non-ASCII token is a 400, not a 500
        self.assertEqual(self.client.post("/api/notifications/read", json={"all": True}, headers={"X-CSRF-Token": "é"}).status_code, 400)

    def test_refused_form_is_an_error_for_fetch_callers(self):   # F-M10
        r = self.client.post("/projects/new", data={"name": "", "client": "C", "po_document": (io.BytesIO(b"%PDF-1.4"), "po.pdf")},
                             headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"]); self.assertIn("required", r.get_json()["error"])
        r = self.new_project(name="Fine", client="C")
        r = self.client.post("/projects/new", data={"name": "Ok", "client": "C", "po_document": (io.BytesIO(b"%PDF-1.4"), "po.pdf")},
                             headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 200); self.assertTrue(r.get_json()["ok"])

    def test_bad_values_in_bodies_are_400s_not_500s(self):   # F-M2, F-M3
        self.new_project(name="P", client="C")
        h = self.csrf()
        c = self.client
        anon = app_module.app.test_client()
        ah = self.csrf(anon)
        for body in ({"username": ["a"], "password": "x"}, {"username": "a", "password": 5}):
            self.assertEqual(anon.post("/api/login", json=body, headers=ah).status_code, 400)
        self.assertEqual(c.post("/projects/1/tasks", json={"title": ["x"]}, headers=h).status_code, 400)
        self.assertEqual(c.post("/projects/1/tasks", json={"title": "ok", "assignee_id": 2 ** 70}, headers=h).status_code, 400)   # refused, not dropped
        self.assertEqual(c.post("/projects/1/tasks", json={"title": "ok", "assignee_id": True}, headers=h).status_code, 400)   # a bool is not a person
        self.assertEqual(c.post("/api/notifications/read", json={"id": 2 ** 70}, headers=h).status_code, 400)
        for q in ("v=99999999999999999999999", "v=%C2%B2", "template=99999999999999999999999"):
            self.assertIn(c.get(f"/api/projects/1/rollout-report?{q}").status_code, (200, 404), q)
        self.assertEqual(c.get("/api/project-form?edit=99999999999999999999999").status_code, 200)
        self.assertEqual(c.post("/api/signup-links", json={"label": ["x"], "role": "Member"}, headers=h).status_code, 400)
        self.assertEqual(c.post("/api/doc-templates", json={"kind": "rollout", "name": ["x"]}, headers=h).status_code, 400)
        self.assertEqual(c.post("/api/doc-templates", json={"kind": ["rollout"], "name": "x"}, headers=h).status_code, 400)
        self.assertEqual(c.post("/api/doc-templates", json={"kind": "rollout", "name": "x", "config": {"texts": []}}, headers=h).status_code, 400)
        self.assertEqual(c.post("/api/account/two-step/setup", json={"password": ["x"]}, headers=h).status_code, 400)
        self.assertEqual(c.post("/api/projects/1/rollout-report", json={"summary": ["x"]}, headers=h).status_code, 400)
        self.assertEqual(c.get("/api/calendar?month=0001-01").status_code, 200)

    def test_form_keys_missing_are_not_500s(self):   # R13 / F-L6
        self.new_project(name="P", client="C")
        self.assertEqual(self.client.post("/api/projects/1/stage", json={}).status_code, 400)
        self.assertEqual(self.client.post("/projects/1/note", data={}).status_code, 302)
        self.assertEqual(self.client.post("/users", data={}).status_code, 302)
        self.assertEqual(self.client.post("/account", data={}).status_code, 302)


class DatesAndFieldsTest(Base):   # B1, F-H1, F-L2/L3
    def test_project_and_task_dates_are_stored_canonical(self):
        self.new_project(name="P", client="C", start_date=" 2026-10-01", target_end_date="2026-12-01 ")
        with self.raw_db() as db:
            self.assertEqual(tuple(db.execute("SELECT start_date, target_end_date FROM projects").fetchone()), ("2026-10-01", "2026-12-01"))
        for bad in ("0001-01-01", "2026-1-1", "20261201"):
            self.new_project(name="Bad", client="C", target_end_date=bad)
        self.client.post("/projects/1/tasks", data={"title": "T", "due_date": " 2026-11-02 "})
        self.client.post("/projects/1/tasks", data={"title": "Bad", "due_date": "9999-01-01"})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)
            self.assertEqual([r[0] for r in db.execute("SELECT due_date FROM tasks")], ["2026-11-02"])
        self.assertEqual(self.client.get("/api/flow").status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard").status_code, 200)

    def test_project_fields_are_checked(self):
        for fields in ({"via": "Carrier pigeon"}, {"account_manager_email": "x@y.z>"}, {"po_number": "9" * 101}, {"vendor_name": "a\x00b"}):
            self.new_project(name="Bad", client="C", **fields)
        self.new_project(name="Good", client="C", via="Partner", partner_name="Redington", account_manager_email="am@acme.example")
        with self.raw_db() as db:
            self.assertEqual([r[0] for r in db.execute("SELECT name FROM projects")], ["Good"])

    def test_user_create_is_checked(self):
        for form in ({"username": "a b", "name": "A", "password": STRONG_PASSWORD, "role": "Member"},
                     {"username": "ok1", "name": "x" * 121, "password": STRONG_PASSWORD, "role": "Member"},
                     {"username": "ok2", "name": "A", "password": STRONG_PASSWORD, "role": "Overlord"},
                     {"username": "ok3", "name": "A", "password": STRONG_PASSWORD, "role": "Member", "email": "a@b.c>"}):
            self.client.post("/users", data=form)
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)

    def test_valid_email(self):
        from security import valid_email
        self.assertTrue(valid_email("ann@acme.example"))
        for bad in ("ann@acme.example\n", "a\x00@b.c", "<a@b.c>", "a@b", ["a@b.c"]):
            self.assertFalse(valid_email(bad), bad)

    def test_contacts_and_categories_are_checked(self):
        h = {"Accept": "application/json"}
        self.assertEqual(self.client.post("/settings/contacts/partners/add", data={"name": "x" * 121}, headers=h).status_code, 400)
        self.assertEqual(self.client.post("/settings/doc-categories/add", data={"name": "a\x00b"}, headers=h).status_code, 400)
        self.assertEqual(self.client.post("/settings/contacts/vendors/add", data={"name": "CrowdStrike"}, headers=h).status_code, 200)


class ExposureTest(Base):
    def test_existing_external_invited_gets_no_link_by_hand(self):   # S1
        self.new_project(name="A", client="Acme"); self.new_project(name="B", client="Acme")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        self.assertIn("send them this link yourself", flashed(self.client))     # a brand-new account: by hand is fine
        self._invite(2, "ann@acme.example", "Customer", "Ann")
        said = flashed(self.client)
        self.assertNotIn("/auth/link/", said); self.assertIn("ask for a sign-in link", said)

    def test_signoff_link_for_a_signer_on_other_projects_is_emailed_not_returned(self):   # S1
        c, h, ann, _ = self._signoff_setup()
        c.post("/api/projects/1/signoff", json={"summary": "Done.", "signer_id": ann, "counter_id": 1, "delivered": ["Everything"]}, headers=h)
        with patch("routes.auth.send_login_link", return_value=(True, None)):
            self.assertIsNone(c.post("/api/projects/1/signoff/1/link", headers=h).get_json()["link"])   # on this project only, too
        self.new_project(name="Other", client="Globex")
        self._invite(2, "ann@globex.example", "Customer", "Ann")
        with patch("routes.auth.send_login_link", return_value=(True, None)) as sent:
            r = c.post("/api/projects/1/signoff/1/link", headers=h).get_json()
        self.assertIsNone(r["link"]); self.assertTrue(r["emailed"]); self.assertTrue(sent.called)

    def test_plain_report_is_internal(self):   # S2
        self.new_project(name="P", client="Acme")
        self.client.post("/projects/1/note", data={"note": "internal margin"})
        self.client.post("/projects/1/report/save", data={"body": "internal margin po.pdf"})
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        ann = self._external_client("ann@acme.example")
        self.assertEqual(ann.get("/api/projects/1/report").status_code, 404)
        self.assertEqual(ann.get("/api/projects/1/report?v=1").status_code, 404)

    def test_customer_cut_hides_internal_register_words_and_colour(self):   # D1
        self.new_project(name="P", client="Acme", target_end_date="2027-06-30")
        c, csrf = self._api_client()
        h = {"X-CSRF-Token": csrf}
        c.post("/api/projects/1/raid", json={"kind": "blocker", "title": "Secret firewall fight", "impact": "high"}, headers=h)
        live = c.get("/api/projects/1/rollout-report").get_json()
        self.assertEqual(live["data"]["health"]["rag"], "red")
        self.assertNotIn("Secret firewall fight", live["words"]["suggested"]["summary"])   # the suggestion is customer-safe
        v = c.post("/api/projects/1/rollout-report", json={"summary": "On track. Blocked by: Secret firewall fight. 3 days behind the baseline.",
                                                           "next_steps": "Fix Secret firewall fight\nCable racks"}, headers=h).get_json()["version"]
        cu = c.get(f"/api/projects/1/rollout-report?audience=customer&v={v}").get_json()
        self.assertEqual(cu["words"]["summary"], "On track."); self.assertEqual(cu["words"]["next_steps"], "Cable racks")
        self.assertNotEqual(cu["data"]["health"]["rag"], "red")                    # the hidden blocker does not colour it
        self.assertNotIn("Secret", json.dumps(cu))
        self.assertIn("Secret firewall fight", c.get(f"/api/projects/1/rollout-report?v={v}").get_json()["words"]["summary"])   # internal keeps it

    def test_internal_note_never_reaches_an_external_by_mention(self):   # R1, R7
        self.new_project(name="P", client="Acme")
        self._invite(1, "ann@acme.example", "Customer", "Ann Customer")
        ann = self.uid("ann@acme.example")
        self.client.post("/projects/1/note", data={"note": "@Ann margin is thin"})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND kind = 'mention'", (ann,)).fetchone()[0], 0)
        self.client.post("/projects/1/note", data={"note": "@Ann the window is Saturday", "share": "1"})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND kind = 'mention'", (ann,)).fetchone()[0], 1)
            self.assertEqual([r[0] for r in db.execute("SELECT guest_visible FROM status_notes ORDER BY id")], [0, 1])
        notes = self._external_client("ann@acme.example").get("/api/projects/1").get_json()["notes"]
        self.assertEqual([n["note"] for n in notes], ["@Ann the window is Saturday"])

    def test_approval_note_is_immutable(self):   # R3
        self.new_project(name="P", client="Acme", customer_approval="1")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        with self.raw_db() as db:
            stages = [r[0] for r in db.execute("SELECT name FROM project_stages WHERE project_id = 1 ORDER BY position")]
        self.client.post("/api/projects/1/stage", json={"stage": stages[1]})
        ann = self._external_client("ann@acme.example")
        h = self.csrf(ann)
        aid = ann.get("/api/projects/1/flow").get_json()["approval"]["id"]
        self.assertEqual(ann.post(f"/api/projects/1/approvals/{aid}", json={"decision": "approved", "comment": "fine"}, headers=h).status_code, 200)
        with self.raw_db() as db:
            nid = db.execute("SELECT id FROM status_notes WHERE note LIKE 'Approved%'").fetchone()[0]
        self.assertEqual(ann.post(f"/projects/1/notes/{nid}/edit", data={"note": "Declined"}, headers=h).status_code, 403)
        self.assertEqual(ann.post(f"/projects/1/notes/{nid}/delete", headers=h).status_code, 403)

    def test_alerts_and_analytics_are_staff_only(self):   # R6
        self.new_project(name="Late", client="Acme", target_end_date="2020-01-01")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        ann = self._external_client("ann@acme.example")
        for path in ("/api/alerts", "/alerts", "/api/analytics", "/analytics"):
            self.assertEqual(ann.get(path).status_code, 403, path)
        self.assertEqual(ann.get("/api/session").get_json()["user"]["nav"]["active_alert_count"], 0)
        self.assertEqual(self.client.get("/api/alerts").status_code, 200)

    def test_legacy_guest_links_only_for_managers(self):   # S11
        self.new_project(name="P", client="Acme")
        self._make_user("viewer", "Viewer")
        self.assertEqual(self.login_as("viewer").get("/api/projects/1").get_json()["guest_links"], {"customer": None, "vendor": None})
        self.assertIn("/guest/", self.client.get("/api/projects/1").get_json()["guest_links"]["customer"])


class AccessControlTest(Base):
    def test_rbac_caps_external_and_audits_the_diff(self):   # R4, R5
        c, csrf = self._api_client()
        h = {"X-CSRF-Token": csrf, "Accept": "application/json"}
        d = c.get("/api/settings/rbac").get_json()
        self.assertEqual(d["forbidden"]["manage_users"], ["External"]); self.assertEqual(d["forbidden"]["view_board"], [])
        fields = {f"{p}::{r}": "on" for p, roles in d["matrix"].items() for r, ok in roles.items() if ok}
        r = c.post("/settings/rbac", data={**fields, "manage_users::External": "on"}, headers=h)
        self.assertEqual(r.status_code, 400)
        fields.pop("edit_project_stage::Member")
        c.post("/settings/rbac", data=fields, headers=h)
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT allowed FROM role_permissions WHERE permission='manage_users' AND role='External'").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT details FROM audit_logs WHERE action='update_role_permissions' ORDER BY id DESC").fetchone()[0],
                             "edit_project_stage: Member off")

    def test_viewer_cannot_dismiss_others_ai_drafts(self):   # S7
        self.new_project(name="P", client="Acme")
        self._make_user("viewer", "Viewer")
        with self.raw_db() as db:
            db.execute("INSERT INTO ai_jobs (kind, feature, project_id, status, requested_by, created_at) VALUES ('feature', 'catch_up', 1, 'queued', 'Admin', ?)",
                       (datetime.utcnow().isoformat(),))
            db.execute("INSERT INTO ai_suggestions (project_id, feature, payload, status, created_at, job_id) VALUES (1, 'catch_up', '{}', 'new', ?, 1)",
                       (datetime.utcnow().isoformat(),))
            db.commit()
        v = self.login_as("viewer")
        h = self.csrf(v)
        self.assertEqual(v.post("/api/projects/1/ai/suggestions/1/dismiss", json={}, headers=h).status_code, 403)
        self.assertEqual(v.post("/api/projects/1/ai/jobs/1/cancel", json={}, headers=h).status_code, 403)
        self.assertEqual(v.post("/api/projects/1/ai/suggestions/1/close", json={"taken": 0}, headers=h).status_code, 403)
        self.assertEqual(self.client.post("/api/projects/1/ai/suggestions/1/dismiss", json={}, headers=self.csrf()).status_code, 200)

    def test_raid_owner_must_be_staff_or_on_this_project(self):   # D10/S5
        self.new_project(name="A", client="Acme"); self.new_project(name="B", client="Acme")
        self._invite(2, "raj@vendor.example", "Contractor", "Raj")
        raj = self.uid("raj@vendor.example")
        h = self.csrf()
        r = self.client.post("/api/projects/1/raid", json={"kind": "risk", "title": "x", "owner_id": raj}, headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post("/api/projects/2/raid", json={"kind": "risk", "title": "x", "owner_id": raj, "due_date": " 2026-11-01"}, headers=h).status_code, 200)
        self.assertEqual(self.client.post("/api/projects/2/raid", json={"kind": "risk", "title": "x", "due_date": "1900-01-01"}, headers=h).status_code, 400)

    def test_removed_partner_gets_no_reminders(self):   # D11
        from send_daily_alerts import send_due_reminders
        self.new_project(name="P", client="Acme")
        self._invite(1, "raj@vendor.example", "Contractor", "Raj")
        raj = self.uid("raj@vendor.example")
        self.client.post("/projects/1/tasks", data={"title": "Rack it", "assignee_id": raj, "due_date": "2020-01-01"})
        with self.raw_db() as db:
            db.execute("DELETE FROM project_participants WHERE user_id = ?", (raj,)); db.commit()
        with app_module.app.test_request_context():
            from db import get_db
            self.assertEqual(send_due_reminders(get_db()), 0)

    def test_creator_is_not_mailed_about_their_own_project(self):   # D12 (the part in notify_event)
        with self.raw_db() as db:
            db.execute("UPDATE users SET email = 'admin@odin.example' WHERE id = 1")
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('policy.notify_email_enabled', '1')"); db.commit()
        with patch("graph.send_mail", return_value=(True, None)) as mail:
            self.new_project(name="Mine", client="C")
            T.drain_outbox()
        self.assertNotIn("admin@odin.example", [c.args[0] for c in mail.call_args_list])

    def test_approval_subject_is_escaped_for_teams(self):   # S9
        self.new_project(name="<b>P</b>", client="Acme", customer_approval="1")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        with self.raw_db() as db:
            stages = [r[0] for r in db.execute("SELECT name FROM project_stages WHERE project_id = 1 ORDER BY position")]
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('policy.notify_teams_enabled', '1')"); db.commit()
        self.client.post("/api/projects/1/stage", json={"stage": stages[1]})
        ann = self._external_client("ann@acme.example")
        aid = ann.get("/api/projects/1/flow").get_json()["approval"]["id"]
        with patch("graph.send_teams_message", return_value=(True, None)) as teams:
            ann.post(f"/api/projects/1/approvals/{aid}", json={"decision": "approved"}, headers=self.csrf(ann))
            T.drain_outbox()
        self.assertIn("&lt;b&gt;P&lt;/b&gt;", teams.call_args.args[0]); self.assertNotIn("<b>P</b>", teams.call_args.args[0])


class SignInTest(Base):
    def test_code_endpoint_without_a_pending_login_keeps_the_session(self):   # F-L5
        h = self.csrf()
        self.assertEqual(self.client.post("/api/login/code", json={"code": "123456"}, headers=h).status_code, 400)
        self.assertIsNotNone(self.client.get("/api/session").get_json()["user"])

    def test_replacing_the_authenticator_needs_a_code_and_ends_other_sessions(self):   # D4
        import time
        from services import mfa
        self._make_user("pm", "Member")
        c, csrf = self._api_client("pm", STRONG_PASSWORD)
        other, _ = self._api_client("pm", STRONG_PASSWORD)
        h = {"X-CSRF-Token": csrf}
        secret = c.post("/api/account/two-step/setup", json={"password": STRONG_PASSWORD}, headers=h).get_json()["secret"]
        step = int(time.time() // mfa.STEP)
        codes = c.post("/api/account/two-step/confirm", json={"code": mfa.code_at(secret, step)}, headers=h).get_json()["recovery_codes"]
        r = c.post("/api/account/two-step/setup", json={"password": STRONG_PASSWORD}, headers=h)
        self.assertEqual(r.status_code, 400); self.assertIn("current authenticator", r.get_json()["error"])
        new = c.post("/api/account/two-step/setup", json={"password": STRONG_PASSWORD, "code": codes[0]}, headers=h).get_json()["secret"]
        self.assertEqual(c.post("/api/account/two-step/confirm", json={"code": mfa.code_at(new, step)}, headers=h).status_code, 200)
        self.assertIsNotNone(c.get("/api/session").get_json()["user"])
        self.assertIsNone(other.get("/api/session").get_json()["user"])        # the other session ended

    def test_ai_check_keeps_the_saved_key_and_switch(self):   # D2
        server = FakeAIServer()
        with patch("services.ai.client.requests.request", server):
            with self.raw_db() as db:
                for k, v in (("ai_base_url", "http://192.168.1.238:11434/v1"), ("ai_model", "P24-AI")):
                    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"policy.{k}", v))
                db.commit()
            self.client.post("/settings/ai/key", data={"api_key": "sk-secret"})
            self.client.post("/settings/ai/check", data={"ai_base_url": "http://192.168.1.238:11434/v1", "ai_model": "P24-AI"})
            self.assertEqual(server.calls[-1][2].get("Authorization"), "Bearer sk-secret")
            self.client.post("/settings/ai/check", data={"ai_base_url": "http://10.9.9.9/v1", "ai_model": "P24-AI"})
            self.assertNotIn("Authorization", server.calls[-1][2])                   # another address never gets the saved key
            n = len(server.calls)
            with patch("services.ai.client.socket.getaddrinfo", return_value=[(None, None, None, None, ("104.18.6.192", 443))]):
                r = self.client.post("/settings/ai/check", data={"ai_base_url": "https://api.example.com/v1", "ai_model": "x", "ai_allow_external": "on"}).get_json()
            self.assertFalse(r["result"]["ok"]); self.assertEqual(len(server.calls), n)   # the form's tick is not the saved switch

    def test_ai_address_guard_reads_shorthand_ips_and_resolves_names(self):   # D3
        from services.ai.client import is_local
        for url in ("http://134744072/v1", "http://0x08080808/v1", "http://8.8.8.8/v1"):
            self.assertFalse(is_local(url), url)
        self.assertTrue(is_local("http://167772161/v1"))   # 10.0.0.1
        with patch("services.ai.client.socket.getaddrinfo", return_value=[(None, None, None, None, ("104.18.6.192", 443))]):
            self.assertFalse(is_local("http://ai.p24.lan/v1"))   # a .lan name pointed outside
        with patch("services.ai.client.socket.getaddrinfo", side_effect=OSError):
            self.assertTrue(is_local("http://ollama:11434/v1")); self.assertFalse(is_local("http://ai.example.com/v1"))


class PoliciesTest(Base):
    def test_webhook_url_with_query_and_partial_saves(self):   # 22, F-M11, L6, F-L1, L18
        from policies import policy
        h = {"Accept": "application/json"}
        url = "https://prod-1.westeurope.logic.azure.com:443/workflows/abc/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers&sig=Zx-9"
        self.assertEqual(self.client.post("/settings/policies/notifications", data={"teams_webhook_url": url}, headers=h).status_code, 200)
        self.client.post("/settings/policies/general", data={"working_days": "Sun,Mon,Tue,Wed,Thu"}, headers=h)
        self.client.post("/settings/policies/general", data={"company_name": "Acme"}, headers=h)    # working_days not sent: kept
        with app_module.app.app_context():
            self.assertEqual(policy("teams_webhook_url"), url)
            self.assertEqual(policy("working_days"), ["Mon", "Tue", "Wed", "Thu", "Sun"])
        for area, form in (("general", {"working_days": ""}), ("general", {"company_name": "a\nb"}), ("general", {"public_url": "https://-"}),
                           ("general", {"public_url": "https://odin.example.com/?x=1"}), ("security", {"external_domains": "-.-"}),
                           ("workflow", {"rag_amber_days": "9", "rag_red_days": "7"}), ("security", {"undo_minutes": "abc"})):
            r = self.client.post(f"/settings/policies/{area}", data=form, headers=h)
            self.assertEqual(r.status_code, 400, form); self.assertNotIn("invalid literal", r.get_json()["error"])

    def test_alert_thresholds_are_bounded(self):   # F-H2, L7
        h = {"Accept": "application/json"}
        self.assertEqual(self.client.post("/settings/alerts", data={"threshold::stale": "99999999999999999999"}, headers=h).status_code, 400)
        self.assertEqual(self.client.post("/settings/alerts", data={"threshold::stale": "366"}, headers=h).status_code, 400)
        self.assertEqual(self.client.post("/settings/alerts", data={"threshold::stale": "30"}, headers=h).status_code, 200)


class RobustnessTest(Base):
    def test_single_use_signup_link_cannot_be_used_twice(self):   # F-S1
        from services import signup
        with self.raw_db() as db:
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('policy.signup_enabled', '1')"); db.commit()
        raw = self.client.post("/api/signup-links", json={"label": "one", "role": "Member"}, headers=self.csrf()).get_json()["link"].rsplit("/", 1)[1]
        with app_module.app.test_request_context():
            link = signup.lookup(raw)                     # both requests read the link before either writes
            signup.register(link, {"name": "A", "username": "a1", "email": "a1@acme.example", "password": STRONG_PASSWORD})
            with self.assertRaises(ValueError):
                signup.register(link, {"name": "B", "username": "b1", "email": "b1@acme.example", "password": STRONG_PASSWORD})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users WHERE pending = 1").fetchone()[0], 1)

    def test_report_versions_number_inside_the_insert(self):   # F-M6
        self.new_project(name="P", client="C")
        h = self.csrf()
        save = lambda: self.client.post("/api/projects/1/rollout-report", json={"summary": "x"}, headers=h).get_json()["version"]   # noqa: E731
        self.assertEqual([save(), save()], [1, 2])

    def test_lessons_save_is_one_commit_with_its_audit_row(self):   # F-M7
        self.new_project(name="P", client="C")
        h = self.csrf()
        r = self.client.post("/api/projects/1/lessons", json={"items": [{"kind": "avoid", "text": "Ask early."}], "ai_suggestion": ["x"]}, headers=h)
        self.assertEqual(r.status_code, 200)
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM lessons").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'save_lessons'").fetchone()[0], 1)
        self.assertEqual(self.client.post("/api/projects/1/lessons", json={"items": [{"text": ["x"]}]}, headers=h).status_code, 400)

    def test_malformed_logo_is_a_400(self):   # F-M8
        import struct
        import zlib
        h = self.csrf()
        def png(w, h_, idat=b""):
            ihdr = struct.pack(">IIBBBBB", w, h_, 8, 2, 0, 0, 0)
            chunk = lambda k, d: struct.pack(">I", len(d)) + k + d + b"\0\0\0\0"   # noqa: E731
            return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
        for data in (b"\x89PNG\r\n\x1a\n\0\0", png(100000, 100000, zlib.compress(b"\0" * 1000)), png(10, 10, b"not zlib"),
                     png(10, 10, zlib.compress(b"\0")), b"\xff\xd8\xff\xc0\0\x05", b"\x89PNG\r\n\x1a\n" + b"\0\0\0\x04IDATabcd\0\0\0\0"):
            r = self.client.post("/api/doc-templates/logo", data={"file": (io.BytesIO(data), "x.png")}, headers=h)
            self.assertEqual(r.status_code, 400, data[:40])

    def test_retention_archive_defuses_formulas(self):   # S13
        import glob
        from services.retention import archive_dir, run_audit_retention
        with self.raw_db() as db:
            db.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete")
            db.execute("INSERT INTO audit_logs (username, action, details, timestamp) VALUES ('=cmd', 'x', '@SUM(1)', '2000-01-01T00:00:00')")
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('policy.audit_keep', '1')"); db.commit()
        n, path = run_audit_retention()
        self.assertTrue(n)
        text = open(path).read()
        self.assertIn("'=cmd", text); self.assertIn("'@SUM(1)", text)



class ExternalRoleTest(Base):
    def test_session_names_a_customer_and_a_partner(self):
        self.new_project(name="P1", client="C")
        self.new_project(name="P2", client="C")
        self._invite(1, "vendor@example.com", role="Contractor")
        self._invite(1, "cust@example.com", role="Contractor")
        self._invite(2, "cust@example.com", role="Customer")
        user = lambda email: self._external_client(email).get("/api/session").get_json()["user"]
        self.assertEqual(user("cust@example.com")["external_role"], "Customer")     # customer anywhere wins
        self.assertEqual(user("vendor@example.com")["external_role"], "Contractor")
        self.assertIsNone(self.client.get("/api/session").get_json()["user"]["external_role"])   # staff


class SimulationFindingsTest(Base):
    """The 10 Oct 2026 user simulations: what partners could see, refusals
    that read as success, and inputs that crashed the server."""

    def test_a_contractor_never_sees_the_po_or_the_outsourcer(self):
        self.new_project(name="Firewall", client="Acme", po_number="PO-SECRET-1", delivery_mode="Outsourced", outsourcer_name="VendorCo")
        self._invite(1, "raj@vendor.example", "Contractor", "Raj")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        raj, ann = self._external_client("raj@vendor.example"), self._external_client("ann@acme.example")
        self.assertIsNone(raj.get("/api/projects").get_json()["rows"][0]["po_number"])
        self.assertEqual(ann.get("/api/projects").get_json()["rows"][0]["po_number"], "PO-SECRET-1")   # the customer's own PO
        csv = raj.get("/projects/export.csv").data.decode()
        self.assertNotIn("PO-SECRET-1", csv); self.assertNotIn("VendorCo", csv)
        self.assertEqual(raj.get("/api/projects?q=SECRET").get_json()["total"], 0)
        self.assertEqual(raj.get("/api/search?q=SECRET").get_json()["projects"], [])
        self.assertIsNone(raj.get("/api/projects/1/flow").get_json()["outsourcer_name"])
        self.assertEqual(self.client.get("/api/projects/1/flow").get_json()["outsourcer_name"], "VendorCo")
        # the hidden Client PO is not counted for them
        self.assertEqual(raj.get("/api/projects/1/flow").get_json()["documents"], 0)
        # a saved report's customer copy: no PO for the contractor, no baseline for anyone outside
        self.client.post("/api/projects/1/rollout-report", json={"summary": "On track."}, headers=self.csrf())
        r = raj.get("/api/projects/1/rollout-report").get_json()
        self.assertIsNone(r["data"]["project"]["po_number"]); self.assertIsNone(r["data"]["baseline_at"])
        self.assertEqual(ann.get("/api/projects/1/rollout-report").get_json()["data"]["project"]["po_number"], "PO-SECRET-1")

    def test_a_hidden_blocker_never_turns_the_customer_red(self):
        self.new_project(name="P", client="Acme", target_end_date="2030-01-01")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        self.client.post("/api/projects/1/raid", json={"kind": "blocker", "title": "Internal fight", "customer_visible": False}, headers=self.csrf())
        self.assertEqual(self.client.get("/api/projects/1/plan").get_json()["health"]["rag"], "red")   # staff see it
        ann = self._external_client("ann@acme.example")
        self.assertNotEqual(ann.get("/api/projects/1/plan").get_json()["health"]["rag"], "red")
        self.assertNotEqual([r["rag"] for r in ann.get("/api/reports/all").get_json()["rows"]], ["red"])

    def test_a_refused_form_action_is_a_400_not_ok(self):
        self.new_project(name="P", client="C")
        h = {"Accept": "application/json"}
        r = self.client.post("/projects/1/documents", data={"category": "Deliverable", "file": (io.BytesIO(b"<script>"), "x.html")},
                             headers=h, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400); self.assertFalse(r.get_json()["ok"])
        self.assertEqual(self.client.post("/projects/1/documents", data={"category": "Deliverable"}, headers=h).status_code, 400)

    def test_bad_json_is_a_400_never_a_500(self):
        self.new_project(name="P", client="C")
        h = self.csrf()
        self.assertEqual(self.client.post("/api/projects/1/stage", json={"note": 5}, headers=h).status_code, 400)
        self.assertEqual(self.client.post("/api/projects/1/stage", json=[1], headers=h).status_code, 400)
        self.assertEqual(self.client.put("/api/projects/1/plan", json=[1], headers=h).status_code, 400)
        self.assertEqual(self.client.post("/api/projects/1/plan/baseline", json=[1], headers=h).status_code, 400)
        from services.signoff import clean_signature
        for bad in ({"signature": "abc"}, {"signature": {"kind": "drawn", "strokes": [[[None, 1]] * 9]}}):
            with self.assertRaises(ValueError):
                clean_signature(bad)

    def test_search_treats_percent_and_underscore_as_text(self):
        self.new_project(name="Alpha", client="C")
        self.assertEqual(self.client.get("/api/projects?q=%25%25").get_json()["total"], 0)
        self.assertEqual(self.client.get("/api/search?q=%25%25").get_json()["projects"], [])


class IdentityTest(Base):   # test round 14 Oct 2026: P2-1 to P2-4, P2-9
    TENANT, CLIENT = T.ContactsAndProjectMetaTestCase.TENANT, T.ContactsAndProjectMetaTestCase.CLIENT
    _sso_setup = T.ContactsAndProjectMetaTestCase._sso_setup
    _ms_sign_in = T.ContactsAndProjectMetaTestCase._ms_sign_in

    def staff(self, username, role="Member", **cols):
        uid = self._make_user(username, role)
        with self.raw_db() as db:
            db.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (uid,))
            for k, v in cols.items():
                db.execute(f"UPDATE users SET {k} = ? WHERE id = ?", (v, uid))
            db.commit()
        return uid

    def test_delegated_rights_cannot_make_an_admin(self):   # P2-1
        pm = self.staff("pm")
        waiting = self.staff("waiting", "Viewer", pending=1, active=0)
        with self.raw_db() as db:
            db.execute("UPDATE role_permissions SET allowed = 1 WHERE role = 'Member' AND permission IN ('manage_users', 'manage_settings')"); db.commit()
        c, csrf = self._api_client("pm", STRONG_PASSWORD)
        h = {"X-CSRF-Token": csrf, "Accept": "application/json"}
        fields = {f"{p}::{r}": "on" for p, roles in c.get("/api/settings/rbac").get_json()["matrix"].items() for r, ok in roles.items() if ok}
        self.assertEqual(c.post("/settings/rbac", data={**fields, "edit_project_stage::Viewer": "on"}, headers=h).status_code, 400)
        for url, form in ((f"/users/{pm}/role", {"role": "Admin"}), (f"/users/{pm}/role", {"role": "Viewer"}), ("/users/1/role", {"role": "Member"}),
                          (f"/users/{waiting}/approve", {"role": "Admin"}), ("/users/1/reset-password", {"new_password": STRONG_PASSWORD + "x"}),
                          ("/users/1/email", {"email": "pm@corp.example"}),
                          ("/users", {"username": "boss", "name": "Boss", "password": STRONG_PASSWORD, "role": "Admin"})):
            with self.subTest(url=url, form=form):
                self.assertEqual(c.post(url, data=form, headers=h).status_code, 400)
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT role FROM users WHERE id = ?", (pm,)).fetchone()[0], "Member")
            self.assertEqual(db.execute("SELECT allowed FROM role_permissions WHERE role = 'Viewer' AND permission = 'edit_project_stage'").fetchone()[0], 0)
            self.assertIsNone(db.execute("SELECT 1 FROM users WHERE role = 'Admin' AND id != 1").fetchone())
        # delegated work on everyone else still works, and an admin can still make an admin
        self.assertEqual(c.post(f"/users/{waiting}/approve", data={"role": "Viewer"}, headers=h).status_code, 200)
        self.client.post(f"/users/{pm}/role", data={"role": "Admin"})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT role FROM users WHERE id = ?", (pm,)).fetchone()[0], "Admin")

    def test_microsoft_account_cannot_mint_a_password_and_email_change_kills_links(self):   # P2-2
        from security import issue_login_link, reset_link_row
        ms = self.staff("ms1", email="ms1@corp.example")
        m = self.login_as("ms1")
        with self.raw_db() as db:
            db.execute("UPDATE users SET ms_oid = 'oid-ms1', password_hash = 'microsoft:no-password' WHERE id = ?", (ms,))
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('policy.notify_email_enabled', '1')"); db.commit()
        r = m.post("/account/email", data={"email": "me@evil.example"}, headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 400)
        with patch("graph.send_mail", return_value=(True, None)) as mail:
            app_module.app.test_client().post("/auth/reset", data={"email": "ms1@corp.example"})
        mail.assert_not_called()
        # a password account: the change ends other sessions and every outstanding link
        pw = self.staff("pw1", email="pw1@corp.example")
        a, b = self.login_as("pw1"), self.login_as("pw1")
        with app_module.app.test_request_context():
            raw = issue_login_link(pw, purpose="reset")
        self.assertEqual(a.post("/account/email", data={"email": "pw1@new.example", "password": STRONG_PASSWORD}, headers={"Accept": "application/json"}).status_code, 200)
        self.assertIsNotNone(a.get("/api/session").get_json()["user"]); self.assertIsNone(b.get("/api/session").get_json()["user"])
        with app_module.app.test_request_context():
            self.assertIsNone(reset_link_row(raw))

    def test_delegated_rights_cannot_act_on_an_admins_account(self):   # P2-1 follow-up
        self.staff("pm")
        boss = self.staff("boss", "Admin")
        with self.raw_db() as db:
            db.execute("UPDATE role_permissions SET allowed = 1 WHERE role = 'Member' AND permission = 'manage_users'"); db.commit()
            db.execute("UPDATE users SET password_login = 0 WHERE id = ?", (boss,)); db.commit()
        c, csrf = self._api_client("pm", STRONG_PASSWORD)
        routes = ((f"/users/{boss}/active", {"active": "0"}), (f"/users/{boss}/two-step-reset", {}),
                  (f"/users/{boss}/password-login", {"allowed": "on"}))
        for url, form in routes:
            with self.subTest(url=url, by="delegated"):
                r = c.post(url, data=dict(form), headers={"X-CSRF-Token": csrf, "Accept": "application/json"})
                self.assertEqual((r.status_code, r.get_json()["error"][:18]), (400, "Only an admin can "))
        with self.raw_db() as db:
            self.assertEqual(tuple(db.execute("SELECT active, password_login FROM users WHERE id = ?", (boss,)).fetchone()), (1, 0))
        for url, form in routes:
            with self.subTest(url=url, by="admin"):
                self.assertEqual(self.client.post(url, data=dict(form), headers={"Accept": "application/json"}).status_code, 200)
        with self.raw_db() as db:
            self.assertEqual(tuple(db.execute("SELECT active, password_login FROM users WHERE id = ?", (boss,)).fetchone()), (0, 1))

    def _ms_finish(self, client, oid, email):
        """Microsoft's half of a flow already started on `client` (its session holds the state)."""
        import base64, time
        with client.session_transaction() as s:
            state, nonce = s["sso"]["state"], s["sso"]["nonce"]
        claims = {"tid": self.TENANT, "iss": f"https://login.microsoftonline.com/{self.TENANT}/v2.0", "aud": self.CLIENT,
                  "nonce": nonce, "exp": time.time() + 600, "oid": oid, "preferred_username": email, "name": email}
        enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
        with patch("routes.sso.requests.post") as post:
            post.return_value.json.return_value = {"id_token": f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"}
            return client.get(f"/auth/microsoft/callback?code=abc&state={state}")

    def test_first_microsoft_sign_in_never_takes_a_password_account(self):   # P2-3
        self._sso_setup()
        squat = self.staff("squat", email="ceo@corp.example")
        c = app_module.app.test_client()
        self._ms_sign_in(c, "oid-ceo", "CEO@corp.example", "The CEO")
        self.assertIsNone(c.get("/api/session").get_json()["user"])
        with self.raw_db() as db:
            self.assertIsNone(db.execute("SELECT ms_oid FROM users WHERE id = ?", (squat,)).fetchone()[0])
            self.assertIsNone(db.execute("SELECT 1 FROM users WHERE ms_oid = 'oid-ceo'").fetchone())   # no request row holding the oid
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'link_microsoft_refused'").fetchone()[0], 1)
            self.assertIn("not confirmed that address", db.execute("SELECT body FROM notifications WHERE user_id = 1 AND kind = 'access'").fetchone()[0])   # v1.8.0: an unproven address never binds
        # the real person signs in with the password and links Microsoft from the Account page
        me = self.login_as("squat")
        self.assertEqual(me.get("/api/account/microsoft").get_json(), {"available": True, "linked": False})
        start = me.post("/account/microsoft", headers={"Accept": "application/json"}).get_json()
        self.assertIn("login.microsoftonline.com", start["location"])
        self.assertEqual(self._ms_finish(me, "oid-ceo", "ceo@corp.example").headers["Location"], "/account")
        self.assertTrue(me.get("/api/account/microsoft").get_json()["linked"])
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT ms_oid FROM users WHERE id = ?", (squat,)).fetchone()[0], "oid-ceo")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'link_microsoft_account'").fetchone()[0], 1)
        self.assertEqual(self._ms_sign_in(app_module.app.test_client(), "oid-ceo", "ceo@corp.example").headers["Location"], "/board")
        # an oid another account holds is never moved
        other = self.staff("other")
        o = self.login_as("other")
        o.post("/account/microsoft")
        self._ms_finish(o, "oid-ceo", "ceo@corp.example")
        with self.raw_db() as db:
            self.assertIsNone(db.execute("SELECT ms_oid FROM users WHERE id = ?", (other,)).fetchone()[0])
        # once passwords cannot sign in (Microsoft only, no flag), the binding happens and the password is retired
        mem = self.staff("mem", email="mem@corp.example")
        with self.raw_db() as db:
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('sso_enforced', '1')")
            db.execute("UPDATE users SET email_verified_at = '2026-10-15' WHERE id = ?", (mem,)); db.commit()   # v1.8.0: only a proven address binds
        self.assertEqual(self._ms_sign_in(c, "oid-mem", "mem@corp.example").headers["Location"], "/board")
        with self.raw_db() as db:
            self.assertEqual(tuple(db.execute("SELECT ms_oid, password_hash FROM users WHERE id = ?", (mem,)).fetchone()), ("oid-mem", "microsoft:no-password"))

    def test_two_step_codes_are_limited_per_account_across_addresses(self):   # P2-4
        import time
        from policies import policy
        from services import mfa
        from security import failed_attempts
        uid = self.staff("ts")
        c, csrf = self._api_client("ts", STRONG_PASSWORD)
        secret = c.post("/api/account/two-step/setup", json={"password": STRONG_PASSWORD}, headers={"X-CSRF-Token": csrf}).get_json()["secret"]
        step = int(time.time() // mfa.STEP)
        clock = patch("services.mfa.time")   # frozen: a 30 s rollover mid-test must not move the codes
        clock.start().time.return_value = step * mfa.STEP + 1
        self.addCleanup(clock.stop)
        c.post("/api/account/two-step/confirm", json={"code": mfa.code_at(secret, step)}, headers={"X-CSRF-Token": csrf})
        wrong = "000000" if mfa.code_at(secret, step + 1) != "000000" else "111111"

        def code_from(ip, code):
            x = app_module.app.test_client(); x.environ_base["REMOTE_ADDR"] = ip
            r = x.post("/api/login", json={"username": "ts", "password": STRONG_PASSWORD}, headers=self.csrf(x)).get_json()
            return x.post("/api/login/code", json={"code": code}, headers={"X-CSRF-Token": r["csrf"]}).status_code

        with app_module.app.app_context():
            limit = policy("login_max_attempts")
        for i in range(limit - 1):
            self.assertEqual(code_from(f"10.0.0.{i}", wrong), 401)
        self.assertEqual(code_from("10.0.1.1", mfa.code_at(secret, step + 1)), 200)   # a success clears the count
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM login_attempts WHERE username = ?", (f"mfa:{uid}",)).fetchone()[0], 0)
        for i in range(limit):
            self.assertEqual(code_from(f"10.0.2.{i}", wrong), 401)
        with app_module.app.test_request_context():
            self.assertEqual(failed_attempts(f"mfa:{uid}"), limit)
        self.assertEqual(code_from("10.0.3.1", mfa.code_at(secret, step + 1)), 429)   # one address each: still locked

    def test_teams_webhook_is_sealed_and_write_only(self):   # P2-9
        from policies import policy
        h = {"Accept": "application/json"}
        url = "https://prod-1.westeurope.logic.azure.com/workflows/abc/triggers/manual/paths/invoke?sp=x&sig=TOPSECRET"
        with self.raw_db() as db:   # a value saved before sealing still works
            db.execute("INSERT INTO settings (key, value) VALUES ('policy.teams_webhook_url', 'https://hook.example/old')"); db.commit()
        with app_module.app.app_context():
            self.assertEqual(policy("teams_webhook_url"), "https://hook.example/old")
        self.client.post("/settings/policies/notifications", data={"teams_webhook_url": url}, headers=h)
        self.client.post("/settings/policies/notifications", data={"teams_webhook_url": ""}, headers=h)   # blank keeps it
        with app_module.app.app_context():
            self.assertEqual(policy("teams_webhook_url"), url)
        with self.raw_db() as db:
            self.assertTrue(db.execute("SELECT value FROM settings WHERE key = 'policy.teams_webhook_url'").fetchone()[0].startswith("sealed:"))
        item = next(p for p in self.client.get("/api/settings").get_json()["policies"] if p["key"] == "teams_webhook_url")
        self.assertEqual((item["value"], item["secret"], item["saved"]), ("", True, True))
        self.client.post("/settings/policies/notifications", data={"teams_webhook_url": "", "clear": "teams_webhook_url"}, headers=h)
        with app_module.app.app_context():
            self.assertEqual(policy("teams_webhook_url"), "")
        with self.raw_db() as db:
            details = [r[0] for r in db.execute("SELECT details FROM audit_logs WHERE action = 'update_policies' ORDER BY id")]
        self.assertEqual(details, ["teams_webhook_url=set", "teams_webhook_url=cleared"])


class SecretKeyTest(Base):   # review 15 Oct 2026
    def test_the_public_dev_key_counts_as_no_key(self):
        import os, subprocess, sys, tempfile
        env = {**os.environ, "SECRET_KEY": "dev-secret-change-me", "ODIN_DATA_DIR": tempfile.mkdtemp()}
        out = subprocess.run([sys.executable, "-c", "import core; print(core.app.config['USING_DEV_SECRET'])"],
                             env=env, capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(out.stdout.strip(), "True", out.stderr)

    def test_a_second_first_boot_reads_the_key_the_first_one_writes(self):
        import core, os, tempfile, threading
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "secret_key")
        open(path, "w").close()   # the other process has created it, not yet written it
        theirs = "k" * 64

        def write():
            with open(path, "w") as f:
                f.write(theirs)
        threading.Timer(0.1, write).start()
        with patch.object(db_module, "DATA_DIR", tmp):
            self.assertEqual(core._local_secret_key(), theirs)

    def test_two_step_secrets_open_through_the_one_legacy_fallback(self):
        import base64, hashlib, core
        from cryptography.fernet import Fernet
        from services import mfa
        old = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"odin-totp:" + core.DEV_SECRET.encode()).digest())).encrypt(b"JBSWY3DP").decode()
        with app_module.app.app_context():
            self.assertEqual(mfa.unseal(mfa.seal("JBSWY3DP")), "JBSWY3DP")
            self.assertEqual(mfa.unseal(old), "JBSWY3DP")
            with patch.dict(app_module.app.config, {"LEGACY_SECRET_KEY": None}):
                self.assertIsNone(mfa.unseal(old))

    def test_boot_seals_a_plain_teams_webhook_once(self):
        with self.raw_db() as db:
            db.execute("INSERT INTO settings (key, value) VALUES ('policy.teams_webhook_url', 'https://hook.example/old?sig=x')"); db.commit()
            db_module.migrate_db(db)
            first = db.execute("SELECT value FROM settings WHERE key = 'policy.teams_webhook_url'").fetchone()[0]
            db_module.migrate_db(db)
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key = 'policy.teams_webhook_url'").fetchone()[0], first)
        self.assertTrue(first.startswith("sealed:"))
        with app_module.app.app_context():
            from policies import policy
            self.assertEqual(policy("teams_webhook_url"), "https://hook.example/old?sig=x")


if __name__ == "__main__":
    unittest.main()
