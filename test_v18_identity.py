"""v1.8.0 identity and sign-in fixes (review 14 Oct 2026): P2-3, P3-2 to P3-5,
P3-10 to P3-13, P3-15, A11, A22. Run with: python -m unittest test_v18_identity"""
import io
import json
import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from flask.testing import FlaskClient

import test_app
from test_app import STRONG_PASSWORD, app_module, db_module, flashed
from test_fix_logic import FixBase

JSON = {"Accept": "application/json"}


class Base(FixBase):
    _mail_on = test_app.ContactsAndProjectMetaTestCase._mail_on
    _sso_setup = test_app.ContactsAndProjectMetaTestCase._sso_setup
    _ms_sign_in = test_app.ContactsAndProjectMetaTestCase._ms_sign_in
    TENANT, CLIENT = test_app.ContactsAndProjectMetaTestCase.TENANT, test_app.ContactsAndProjectMetaTestCase.CLIENT

    def login(self, username, password=STRONG_PASSWORD, ip="127.0.0.1"):
        c = app_module.app.test_client()
        c.post("/login", data={"username": username, "password": password}, environ_base={"REMOTE_ADDR": ip})
        return c

    def verified(self, uid):
        return self.sql("SELECT email_verified_at FROM users WHERE id = ?", uid)[0][0] is not None


class AddressCheckTest(Base):   # P2-3
    @patch("graph.send_mail", return_value=(True, None))
    def test_a_new_address_waits_for_its_link_and_only_a_proven_one_binds_microsoft(self, mail):
        self._mail_on()
        self._sso_setup()
        pm = self._make_user("pm", "Member")
        c = self.login("pm")
        r = c.post("/account/email", data={"email": "pm@corp.example", "password": STRONG_PASSWORD}, headers=JSON).get_json()
        self.assertIn("open the link", r["messages"][0])
        self.assertEqual(c.get("/api/account/email").get_json(), {"email": "pm@corp.example", "verified": False, "checkable": True})
        token = re.search(r"/auth/link/([A-Za-z0-9_-]+)\?verify=1", mail.call_args.args[2]).group(1)
        # unproven: a first Microsoft sign-in with that address links nothing and makes no account
        self.sql("INSERT OR REPLACE INTO settings (key, value) VALUES ('sso_enforced', '1')")   # Microsoft only: pm's password cannot sign in
        ms = app_module.app.test_client()
        self._ms_sign_in(ms, "oid-pm", "pm@corp.example")
        self.assertIsNone(ms.get("/api/session").get_json()["user"])
        self.assertIsNone(self.sql("SELECT ms_oid FROM users WHERE id = ?", pm)[0][0])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users WHERE ms_oid = 'oid-pm'")[0][0], 0)
        # opening the link shows the Continue page and changes nothing; a scanner's GET proves nothing
        anon = app_module.app.test_client()
        self.assertEqual(anon.get(f"/auth/link/{token}?verify=1").status_code, 200)
        self.assertFalse(self.verified(pm))
        # it is no sign-in link, and that refusal does not spend it
        self.assertIn("/auth/link", anon.post(f"/auth/link/{token}").headers["Location"])
        self.assertIsNone(anon.get("/api/session").get_json()["user"])
        r = anon.post(f"/auth/link/{token}?verify=1")
        self.assertEqual(r.headers["Location"], "/login")
        self.assertTrue(self.verified(pm))
        self.assertIsNone(anon.get("/api/session").get_json()["user"])   # it signs nobody in
        anon.post(f"/auth/link/{token}?verify=1")
        self.assertIn("invalid or has expired", flashed(anon))
        # proven: the next Microsoft sign-in binds, with the UPN kept beside the oid
        self.assertEqual(self._ms_sign_in(ms, "oid-pm", "PM@corp.example").headers["Location"], "/board")
        self.assertEqual(tuple(self.sql("SELECT ms_oid, ms_upn FROM users WHERE id = ?", pm)[0]), ("oid-pm", "pm@corp.example"))
        acts = [r[0] for r in self.sql("SELECT action FROM audit_logs WHERE action LIKE 'email_veri%' ORDER BY id")]
        self.assertEqual(acts, ["email_verification_sent", "email_verified", "email_verify_rejected"])

    @patch("graph.send_mail", return_value=(True, None))
    def test_an_admin_change_and_a_sign_up_are_unproven_too(self, mail):
        self._mail_on()
        pm = self._make_user("pm", "Member")
        self.sql("UPDATE users SET email = 'pm@corp.example', email_verified_at = '2026-10-01' WHERE id = ?", pm)
        r = self.client.post(f"/users/{pm}/email", data={"email": "pm@corp.example"}, headers=JSON).get_json()
        self.assertEqual(r["messages"][-1], "Email unchanged")   # re-saving a proven address keeps it proven
        self.assertTrue(self.verified(pm))
        r = self.client.post(f"/users/{pm}/email", data={"email": "pm@new.example"}, headers=JSON).get_json()
        self.assertIn("confirm the address", r["messages"][-1])
        self.assertFalse(self.verified(pm))
        self.assertEqual(mail.call_args.args[0], "pm@new.example")
        mail.reset_mock()
        self.client.post(f"/users/{pm}/email", data={"email": "pm@new.example"}, headers=JSON)   # saving it again resends
        self.assertEqual(mail.call_count, 1)
        # a sign-up: pending, unproven, link mailed; its username must be plain ASCII (P3-13)
        self.ctx()
        from services import signup
        raw = signup.create("New staff", "Member", None, None, 7, 5, "admin")
        anon = app_module.app.test_client()
        form = {"name": "Paul", "username": "pаul", "email": "paul@corp.example", "password": STRONG_PASSWORD}
        self.assertEqual(anon.post(f"/api/join/{raw}", json=form).status_code, 400)   # a Cyrillic "а"
        mail.reset_mock()
        self.assertEqual(anon.post(f"/api/join/{raw}", json={**form, "username": "paul"}).status_code, 200)
        uid = self.sql("SELECT id FROM users WHERE username = 'paul'")[0][0]
        self.assertFalse(self.verified(uid))
        token = re.search(r"/auth/link/([A-Za-z0-9_-]+)\?verify=1", mail.call_args.args[2]).group(1)
        anon.post(f"/auth/link/{token}?verify=1")
        self.assertTrue(self.verified(uid))   # before approval: the request still waits
        # P3-15: the active switch never approves a pending request
        r = self.client.post(f"/users/{uid}/active", data={"active": "1"}, headers=JSON)
        self.assertEqual(r.status_code, 400); self.assertIn("Approve", r.get_json()["error"])
        self.assertEqual(tuple(self.sql("SELECT active, pending FROM users WHERE id = ?", uid)[0]), (0, 1))

    def test_addresses_on_file_before_the_upgrade_count_as_proven(self):
        # FX1: only where Microsoft binding needs it; an account with a working password confirms from Account
        self.sql("UPDATE users SET email = 'admin@corp.example' WHERE id = 1")
        self.sql("INSERT INTO users (username, password_hash, name, role, active, email) VALUES ('ms', 'microsoft:no-password', 'Ms', 'Member', 1, 'ms@corp.example')")
        self.sql("ALTER TABLE users DROP COLUMN email_verified_at")
        self.sql("PRAGMA user_version = 1")   # a v1.7.1 database
        with self.raw_db() as db:
            db_module.migrate_db(db)
        self.assertFalse(self.verified(1))
        self.assertTrue(self.verified(self.sql("SELECT id FROM users WHERE username = 'ms'")[0][0]))

    @patch("graph.send_mail", return_value=(True, None))
    def test_send_link_from_the_account_page(self, mail):
        pm = self._make_user("pm", "Member")
        self.sql("UPDATE users SET email = 'pm@corp.example' WHERE id = ?", pm)
        c = self.login("pm")
        self.assertIn("does not send email", c.post("/account/email/verify", headers=JSON).get_json()["error"])
        self._mail_on()
        self._set_policy(mail_link_max="3")
        for _ in range(3):
            self.assertEqual(c.post("/account/email/verify", headers=JSON).status_code, 200)
        self.assertIn("Too many links", c.post("/account/email/verify", headers=JSON).get_json()["error"])
        self.assertEqual(mail.call_count, 3)


class SingleUseTest(Base):   # P3-2
    def test_two_requests_with_one_link_cannot_both_win(self):
        from security import issue_login_link, reset_link_row, take_link
        pm = self._make_user("pm", "Member")
        self.ctx()
        raw = issue_login_link(pm, purpose="reset")
        stale = reset_link_row(raw)
        self.sql("UPDATE login_links SET used_at = '2026-10-15T00:00:00'")   # the other request won meanwhile
        anon = app_module.app.test_client()
        with patch("routes.auth.reset_link_row", return_value=stale):
            anon.post(f"/auth/reset/{raw}", data={"new_password": "Granite-Harbour-Lantern-7"})
        self.assertIn("invalid or has expired", flashed(anon))
        self.assertIsNotNone(self.login("pm").get("/api/session").get_json()["user"])   # the old password still works
        self.assertFalse(take_link(stale))


class ThrottleTest(Base):   # P3-3
    def test_one_address_spraying_many_names_is_paused(self):
        self._set_policy(login_ip_max="10")
        for i in range(10):
            self.login(f"guess{i}", "Wrong-Password-1", ip="10.0.0.9")
        self.assertIsNone(self.login("admin", "changeme", ip="10.0.0.9").get("/api/session").get_json()["user"])
        self.assertIsNotNone(self.login("admin", "changeme", ip="10.0.0.8").get("/api/session").get_json()["user"])

    @patch("graph.send_mail", return_value=(True, None))
    def test_links_to_one_address_are_capped_from_every_machine(self, mail):
        self._mail_on()
        self._set_policy(mail_link_max="3")
        pm = self._make_user("pm", "Member")
        self.sql("UPDATE users SET email = 'pm@corp.example' WHERE id = ?", pm)
        anon = app_module.app.test_client()
        for i in range(4):
            anon.post("/auth/reset", data={"email": "pm@corp.example"}, environ_base={"REMOTE_ADDR": f"10.0.1.{i}"})
        self.assertIn("Too many requests", flashed(anon))
        self.assertEqual(mail.call_count, 3)

    def test_reset_mail_goes_after_the_reply(self):
        self._mail_on()
        pm = self._make_user("pm", "Member")
        self.sql("UPDATE users SET email = 'pm@corp.example' WHERE id = ?", pm)
        anon = app_module.app.test_client()
        with patch.dict(app_module.app.config, {"SEND_MAIL_INLINE": False}), patch("graph.send_mail", return_value=(True, None)) as mail:
            reply = anon.post("/auth/reset", data={"email": "pm@corp.example"})
            mail.assert_not_called()          # the reply is out before the mail is sent
            reply.close()
            self.assertEqual(mail.call_args.args[0], "pm@corp.example")

    def test_notes_to_colleagues_are_capped(self):
        self._set_policy(nudge_max="2")
        self._make_user("pm", "Member")
        c, csrf = self._api_client("pm", STRONG_PASSWORD)
        codes = [c.post("/api/people/1/notify", json={"message": "hi"}, headers={"X-CSRF-Token": csrf}).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_a_stolen_session_cannot_guess_the_current_password(self):
        self._set_policy(login_max_attempts="3")
        self._make_user("pm", "Member")
        c = self.login("pm")
        said = [c.post("/account", data={"current_password": f"Guess-{i}-x", "new_password": "Granite-Harbour-Lantern-7"}, headers=JSON).get_json()["error"]
                for i in range(3)]
        self.assertEqual(said[:2], ["Current password is wrong"] * 2)
        self.assertIn("signed out", said[2])
        self.assertIsNone(c.get("/api/session").get_json()["user"])
        # the owner signs in again and starts afresh
        c = self.login("pm")
        r = c.post("/account", data={"current_password": "nope-nope-1", "new_password": "Granite-Harbour-Lantern-7"}, headers=JSON).get_json()
        self.assertEqual(r["error"], "Current password is wrong")


class OutsideTextTest(Base):   # P3-4
    def test_the_microsoft_callback_never_echoes_its_query(self):
        self._sso_setup()
        anon = app_module.app.test_client()
        anon.get("/auth/microsoft/callback?error=access_denied%0Aevil&error_description=Call+1-800-PHISH+now")
        said = flashed(anon)
        self.assertNotIn("PHISH", said)
        self.assertIn("Microsoft did not sign you in", said)
        details = self.sql("SELECT details FROM audit_logs WHERE action = 'login_failure'")[0][0]
        self.assertNotIn("\n", details); self.assertNotIn("PHISH", details)

    def test_an_unknown_username_is_kept_as_a_mark(self):
        self.login("My-Secret-Pa55word", "whatever-1")
        row = self.sql("SELECT username, resource_name, details FROM audit_logs WHERE action = 'login_failure'")[0]
        self.assertTrue(row[0].startswith("unknown#")); self.assertEqual(row[1], row[0]); self.assertEqual(row[2], "unknown username")
        for table, col in (("audit_logs", "username"), ("audit_logs", "resource_name"), ("login_attempts", "username")):
            self.assertEqual(self.sql(f"SELECT COUNT(*) FROM {table} WHERE {col} LIKE '%Secret%'")[0][0], 0)


class RecoveryCodeTest(Base):   # P3-5
    def test_codes_are_long_salted_and_old_ones_still_work(self):
        from services import mfa
        self.ctx()
        codes, stored = mfa.new_recovery_codes()
        self.assertTrue(all(re.fullmatch(r"[a-z2-7]{4}(-[a-z2-7]{4}){3}", c) for c in codes))   # 16 base32 characters: 80 bits
        entries = json.loads(stored)
        self.assertTrue(all(e.startswith("v2:") for e in entries))
        self.assertEqual(len({e.split(":")[1] for e in entries}), len(entries))   # a salt each
        legacy = mfa._hash("abcd-ef0123")
        self.sql("UPDATE users SET recovery_codes = ? WHERE id = 1", json.dumps(entries + [legacy]))
        from db import get_db
        self.assertEqual(mfa.check(get_db().execute("SELECT * FROM users WHERE id = 1").fetchone(), codes[3].upper()), "recovery")
        self.assertEqual(mfa.check(get_db().execute("SELECT * FROM users WHERE id = 1").fetchone(), codes[3]), None)   # once
        self.assertEqual(mfa.check(get_db().execute("SELECT * FROM users WHERE id = 1").fetchone(), "ABCD-EF0123"), "recovery")
        self.assertEqual(mfa.recovery_left(get_db().execute("SELECT * FROM users WHERE id = 1").fetchone()), 9)


class EdgesTest(Base):   # P3-10, P3-11, P3-12
    def test_csrf_reads_no_body_without_a_token_and_api_errors_are_json(self):
        import flask
        raw = FlaskClient(app_module.app)
        with patch.object(flask.Request, "_load_form_data", side_effect=AssertionError("the body was parsed")):
            r = raw.post("/projects/new", data={"po_document": (io.BytesIO(b"%PDF" + b"0" * 4096), "po.pdf")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        # /api/v1 is Bearer-only: no CSRF answer for a token client, and its errors are JSON
        r = raw.post("/api/v1/projects", headers={"Authorization": "Bearer nope"})
        self.assertEqual((r.status_code, r.is_json), (405, True))
        c, csrf = self._api_client()
        r = c.post("/api/dashboard", json={}, headers={"X-CSRF-Token": csrf})
        self.assertEqual((r.status_code, r.is_json), (405, True))
        self.assertIn("error", r.get_json())

    def test_account_data_is_never_cached_and_the_list_query_is_capped(self):
        c, _ = self._api_client()
        self.assertEqual(c.get("/api/session").headers["Cache-Control"], "private, no-store")
        self.assertEqual(c.get("/users/export.csv").headers["Cache-Control"], "private, no-store")
        c.get("/api/projects?q=" + "x" * 3000 + "&sort=nonsense")
        with c.session_transaction() as s:
            self.assertEqual(len(s["projects_query"]["q"]), 100)


class SecretKeyRotationTest(Base):   # A11
    def test_old_keys_keep_sessions_and_sealed_values_until_the_reseal(self):
        from services import sealed
        c, _ = self._api_client()
        old = app_module.app.config["SECRET_KEY"]
        with app_module.app.app_context():
            self.sql("INSERT INTO settings (key, value) VALUES ('ms_client_secret', ?)", sealed.seal("shh"))
        with patch.dict(app_module.app.config, {"SECRET_KEY": "n" * 64, "SECRET_KEY_FALLBACKS": [old]}):
            self.assertIsNotNone(c.get("/api/session").get_json()["user"])   # signed with the old key, still in
            with app_module.app.app_context():
                self.assertEqual(sealed.unseal(self.sql("SELECT value FROM settings WHERE key = 'ms_client_secret'")[0][0]), "shh")
                with self.raw_db() as db:
                    self.assertEqual(sealed.reseal(db), 1)
        with patch.dict(app_module.app.config, {"SECRET_KEY": "n" * 64, "SECRET_KEY_FALLBACKS": [], "LEGACY_SECRET_KEY": None}):
            with app_module.app.app_context():   # the old key gone: the resealed value still opens
                self.assertEqual(sealed.unseal(self.sql("SELECT value FROM settings WHERE key = 'ms_client_secret'")[0][0]), "shh")
            self.assertIsNone(app_module.app.test_client().get("/api/session").get_json()["user"])


class FirstBootTest(Base):   # A22
    def test_the_first_admin_gets_a_random_password_shown_once(self):
        keep = db_module.DB_PATH
        fd, db_module.DB_PATH = tempfile.mkstemp()
        os.close(fd); os.remove(db_module.DB_PATH)
        try:
            out = io.StringIO()
            env = {k: v for k, v in os.environ.items() if k != "ODIN_ADMIN_PASSWORD"}
            with patch.dict(os.environ, env, clear=True), redirect_stdout(out):
                app_module.init_db()
            password = re.search(r"admin / (\S+)", out.getvalue()).group(1)
            self.assertNotEqual(password, "changeme"); self.assertGreaterEqual(len(password), 16)
            con = sqlite3.connect(db_module.DB_PATH)
            self.assertEqual(con.execute("SELECT must_change_password FROM users WHERE username = 'admin'").fetchone()[0], 1)
            con.close()
            c = app_module.app.test_client()
            c.post("/login", data={"username": "admin", "password": password})
            self.assertTrue(c.get("/api/session").get_json()["user"]["must_change_password"])
        finally:
            os.unlink(db_module.DB_PATH)
            db_module.DB_PATH = keep


if __name__ == "__main__":
    unittest.main()
