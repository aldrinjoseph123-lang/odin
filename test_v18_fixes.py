"""v1.8.0 fix round FX1: server security, data and server code quality.
Run with: python -m unittest test_v18_fixes"""
import json
import logging
from datetime import datetime, timedelta
from unittest.mock import patch

import test_app
from test_app import STRONG_PASSWORD, app_module, db_module, drain_outbox
from test_fix_logic import FixBase

J = {"Accept": "application/json"}


class Base(FixBase):
    _make_user = test_app.ContactsAndProjectMetaTestCase._make_user
    _mail_on = test_app.ContactsAndProjectMetaTestCase._mail_on
    DRAWN = test_app.ContactsAndProjectMetaTestCase.DRAWN

    def boot_from_v171(self):
        self.sql("PRAGMA user_version = 1")
        with self.raw_db() as db:
            db_module.migrate_db(db)

    def login(self, username, password=STRONG_PASSWORD, ip="127.0.0.1"):
        c = app_module.app.test_client()
        c.post("/login", data={"username": username, "password": password}, environ_base={"REMOTE_ADDR": ip})
        return c


class UpgradeOnceTestCase(Base):   # items 1-3
    def _scope(self, title):
        self.new_project(name="P", client="C")
        now = datetime.utcnow().isoformat()
        self.sql("INSERT INTO scope_items (project_id, position, title, status, created_by, created_at, updated_at) VALUES (1, 1, ?, 'agreed', 'a', ?, ?)",
                 title, now, now)

    def test_odd_scope_text_never_stops_a_boot_and_is_rewritten_only_once(self):
        self._scope("[{[]: 1}]")   # literal_eval raised TypeError: every boot crashed
        self.boot_from_v171()
        self.assertEqual(self.sql("SELECT title FROM scope_items")[0][0], "[{[]: 1}]")
        self.sql("UPDATE scope_items SET title = ?", "['eth0', 'eth1']")   # typed after the upgrade, on purpose
        with self.raw_db() as db:
            db_module.migrate_db(db)   # the next boot: user_version is 2 now
        self.assertEqual(self.sql("SELECT title FROM scope_items")[0][0], "['eth0', 'eth1']")

    def test_only_microsoft_only_and_bound_accounts_count_as_proven(self):
        for name, pw, oid, pending in (("pwd", "pbkdf2:sha256$x", None, 0), ("msonly", "microsoft:no-password", None, 0),
                                        ("bound", "pbkdf2:sha256$x", "oid-1", 0), ("waiting", "microsoft:no-password", None, 1)):
            self.sql("INSERT INTO users (username, password_hash, name, role, active, email, ms_oid, pending) VALUES (?, ?, ?, 'Member', 1, ?, ?, ?)",
                     name, pw, name, f"{name}@corp.example", oid, pending)
        self.sql("UPDATE users SET email_verified_at = NULL")
        self.boot_from_v171()
        proven = {r[0] for r in self.sql("SELECT username FROM users WHERE email_verified_at IS NOT NULL")}
        self.assertEqual(proven, {"msonly", "bound"})
        self.sql("UPDATE users SET email_verified_at = NULL WHERE username = 'msonly'")   # e.g. the address changed later
        with self.raw_db() as db:
            db_module.migrate_db(db)
        self.assertEqual({r[0] for r in self.sql("SELECT username FROM users WHERE email_verified_at IS NOT NULL")}, {"bound"})

    def test_guest_links_count_from_the_upgrade(self):
        self.new_project(name="P", client="C")
        self.sql("UPDATE projects SET guest_tokens_at = NULL, created_at = '2020-01-01T00:00:00'")
        self.boot_from_v171()
        at = self.sql("SELECT guest_tokens_at FROM projects")[0][0]
        self.assertTrue(at and at > (datetime.utcnow() - timedelta(minutes=5)).isoformat())


class OutboxTokenTestCase(Base):   # item 4
    def setUp(self):
        Base.setUp(self)
        self.sql("INSERT INTO users (username, password_hash, name, role, active, email, kind) VALUES ('ext', 'x', 'Ext', 'External', 1, 'ext@acme.example', 'external')")
        self.ext = self.sql("SELECT id FROM users WHERE username = 'ext'")[0][0]
        self._mail_on()

    def _notify(self):
        from services.notifications import notify_users
        with app_module.app.test_request_context():
            notify_users([self.ext], "due", None, "Due", "<p>x</p>", link="/my-work")

    def test_the_queue_holds_an_intent_and_the_link_is_minted_at_send_time(self):
        self._notify()
        payload = self.sql("SELECT payload FROM outbox")[0][0]
        self.assertNotIn("/auth/link/", payload)
        self.assertEqual(json.loads(payload)["signin"], {"user_id": self.ext, "path": "/my-work", "label": "Open in Odin"})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM login_links")[0][0], 0)
        with patch("graph.send_mail", return_value=(True, None)) as mail:
            drain_outbox()
        self.assertIn("/auth/link/", mail.call_args.args[2])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM login_links")[0][0], 1)

    def test_a_row_older_than_the_policy_is_given_up_and_the_admins_told(self):
        self.sql("UPDATE users SET email = 'admin@corp.example' WHERE id = 1")
        self._notify()
        self.sql("UPDATE outbox SET created_at = ?", (datetime.utcnow() - timedelta(hours=25)).isoformat())
        with patch("graph.send_mail", return_value=(True, None)) as mail:
            drain_outbox()
        mail.assert_not_called()
        self.assertEqual(tuple(self.sql("SELECT next_try_at, last_error FROM outbox")[0]), (None, "too old to send"))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE user_id = 1 AND kind = 'ops'")[0][0], 1)


class ThrottleTestCase(Base):   # items 5-8
    def test_an_office_behind_one_address_is_not_paused_by_its_own_typos(self):
        self._set_policy(login_ip_max="10", login_max_attempts="20")
        for _ in range(15):   # one person, many typos: one username
            self.login("admin", "Wrong-Password-1", ip="10.0.0.9")
        self.assertIsNotNone(self.login("admin", "changeme", ip="10.0.0.9").get("/api/session").get_json()["user"])

    @patch("graph.send_mail", return_value=(True, None))
    def test_strangers_using_up_the_sign_in_page_do_not_block_the_account_page(self, mail):
        self._mail_on()
        self._set_policy(mail_link_max="3")
        pm = self._make_user("pm", "Member")
        self.sql("UPDATE users SET email = 'pm@corp.example' WHERE id = ?", pm)
        for i in range(4):
            app_module.app.test_client().post("/auth/reset", data={"email": "pm@corp.example"}, environ_base={"REMOTE_ADDR": f"10.0.2.{i}"})
        self.assertEqual(self.login("pm").post("/account/email/verify", headers=J).status_code, 200)

    def test_notes_count_per_pair_and_a_refused_one_counts_nowhere(self):
        self._set_policy(nudge_max="10", nudge_pair_max="2")
        self._make_user("pm", "Member"); self._make_user("sam", "Member")
        pm, h = self._api_client("pm", STRONG_PASSWORD)
        r = [pm.post("/api/people/1/notify", json={"message": "hi"}, headers={"X-CSRF-Token": h}) for _ in range(3)]
        self.assertEqual([x.status_code for x in r], [200, 200, 429])
        self.assertEqual(r[2].headers["Retry-After"], "3600")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM login_attempts WHERE username LIKE 'nudge-%'")[0][0], 4)   # the refusal recorded nothing
        sam, h2 = self._api_client("sam", STRONG_PASSWORD)
        self.assertEqual(sam.post("/api/people/1/notify", json={"message": "hi"}, headers={"X-CSRF-Token": h2}).status_code, 200)   # pm used up nothing of sam's

    def test_every_429_says_when_to_come_back(self):
        self._set_policy(login_max_attempts="3", login_window_minutes="15")
        c = app_module.app.test_client()
        csrf = c.get("/api/session").get_json()["csrf"]
        for _ in range(4):
            r = c.post("/api/login", json={"username": "admin", "password": "nope"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual((r.status_code, r.headers["Retry-After"]), (429, "900"))
        with app_module.app.test_request_context():
            resp = app_module.app.make_response(("", 429))
            self.assertEqual(app_module.app.process_response(resp).headers["Retry-After"], "60")   # the default for any other throttle


class HealthTestCase(Base):   # item 9
    def test_only_this_machine_reads_the_details(self):
        local = app_module.app.test_client().get("/healthz").get_data(as_text=True)
        self.assertIn("database: writable", local)
        away = app_module.app.test_client().get("/healthz", environ_base={"REMOTE_ADDR": "203.0.113.7"})
        self.assertEqual((away.status_code, away.get_data(as_text=True)), (200, "ok\n"))


class ClientErrorsTestCase(Base):   # item 10
    def test_no_control_character_reaches_the_log(self):
        with self.assertLogs(app_module.app.logger, logging.WARNING) as logs:
            app_module.app.test_client().post("/api/client-errors", data=json.dumps({"message": "a\x1b[31mred\rforged line", "stack": "x\ny"}))
        line = logs.output[-1]
        for ch in ("\x1b", "\r", " ", "\n"):
            self.assertNotIn(ch, line)
        self.assertIn("x | y", line)


class TextFieldTestCase(Base):   # item 11
    def test_a_single_line_field_folds_line_breaks_and_keeps_the_length_check(self):
        from core import text_field
        self.assertEqual(text_field("Fit\r\n  the sensors\nnow", 200, "Title"), "Fit the sensors now")
        self.assertEqual(text_field("a\nb", 200, "Note", multiline=True), "a\nb")
        with self.assertRaises(ValueError):
            text_field("x" * 201, 200, "Title")


class SignoffReopenTestCase(Base):   # item 12
    def _sent(self):
        self.new_project(name="P", client="C")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        ann = self.sql("SELECT id FROM users WHERE email = 'ann@acme.example'")[0][0]
        s = self.stages()
        self.sql("UPDATE projects SET stage = ?", s[-2])
        r = self.client.post("/api/projects/1/signoff", json={"signer_id": ann, "counter_id": 1, "summary": "Done", "delivered": ["All"]})
        self.assertEqual(r.status_code, 200, r.get_json())
        return s

    def test_a_reopen_leaves_a_version_still_out_for_signature_live(self):
        s = self._sent()
        self.sql("UPDATE projects SET stage = ?", s[-1])   # closed by hand, the version still out
        self.assertEqual(self.client.post("/api/projects/1/stage", json={"stage": s[1]}).status_code, 200)   # reopened
        self.assertIsNone(self.sql("SELECT superseded_at FROM signoffs")[0][0])
        e = self._external_client("ann@acme.example")
        eh = {"X-CSRF-Token": e.get("/api/session").get_json()["csrf"]}
        self.assertEqual(e.post("/api/projects/1/signoff/1/sign", json={"name": "Ann", "accept": True, "signature": self.DRAWN}, headers=eh).status_code, 200)

    def test_sign_refuses_a_superseded_version(self):
        from services import signoff
        self._sent()
        self.sql("UPDATE signoffs SET superseded_at = '2026-10-15T00:00:00'")
        row = self.sql("SELECT * FROM signoffs")[0]
        with app_module.app.test_request_context():
            with self.assertRaises(ValueError):
                signoff.sign(row, {"name": "Ann", "accept": True, "signature": self.DRAWN}, "127.0.0.1", "ua")
        self.assertEqual(self.sql("SELECT status FROM signoffs")[0][0], "sent")


class ExternalAccountTestCase(Base):   # item 13
    def test_an_external_account_sees_no_staff_only_kinds(self):
        self.new_project(name="P", client="C")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        keys = {k["key"] for k in self._external_client("ann@acme.example").get("/api/account").get_json()["email_kinds"]}
        self.assertFalse(keys & {"nudge", "brief"})
        self.assertIn("stage", keys)
        self.assertIn("nudge", {k["key"] for k in self.client.get("/api/account").get_json()["email_kinds"]})


class CodeQualityTestCase(Base):   # item 14
    def test_dormant_partners_are_audited_through_the_helper(self):
        from services.partner_access import end_dormant
        self.new_project(name="P", client="C")
        self._invite(1, "jane@vendor.example", "Contractor", "Jane")
        self.sql("UPDATE projects SET stage = ?, stage_entered_at = ?", self.stages()[-1], (datetime.utcnow() - timedelta(days=40)).isoformat())
        self._set_policy(external_access_days_after_close="30")
        with app_module.app.app_context():   # as the scheduler runs it: no request
            self.assertEqual(end_dormant(), 1)
        row = self.sql("SELECT username, ip_address FROM audit_logs WHERE action = 'set_user_active'")[0]
        self.assertEqual(tuple(row), ("scheduler", None))

    def test_as_bool(self):
        from core import as_bool
        self.assertEqual([as_bool(v) for v in (True, "1", "true", False, "0", "false", 1, "yes", None)],
                         [True, True, True, False, False, False, None, None, None])

    def test_local_now_is_in_the_workspace_zone(self):
        from policies import local_now
        self._set_policy(timezone="Asia/Dubai")
        with app_module.app.app_context():
            self.assertEqual(str(local_now().tzinfo), "Asia/Dubai")


if __name__ == "__main__":
    import unittest
    unittest.main()


class SignInByEmailTestCase(Base):
    """16 Oct 2026: people who joined by sign-up link chose a username, typed their
    email at the sign-in form and heard "Bad username or password"."""

    def _signed_in(self, c):
        return (c.get("/api/session").get_json().get("user") or {}).get("name")   # _make_user names the account after its username

    def test_the_email_or_any_case_of_the_username_signs_in(self):
        uid = self._make_user("ajoseph", "Member")
        self.sql("UPDATE users SET email = 'AJoseph@Example.com' WHERE id = ?", uid)
        for typed in ("ajoseph", "AJOSEPH", "ajoseph@example.com", " AJoseph@Example.COM "):
            with self.subTest(typed=typed):
                self.assertEqual(self._signed_in(self.login(typed)), "ajoseph")
        self.assertIsNone(self._signed_in(self.login("ajoseph@example.com", "wrong-password-1")))

    def test_an_address_two_accounts_could_mean_signs_in_neither(self):
        a = self._make_user("one", "Member")
        self._make_user("ONE@example.com", "Member")   # a username that is someone else's address
        self.sql("UPDATE users SET email = 'one@example.com' WHERE id = ?", a)
        self.assertIsNone(self._signed_in(self.login("one@EXAMPLE.com")))
        self.assertEqual(self._signed_in(self.login("one")), "one")   # the exact name still works

    def test_a_failure_by_email_counts_against_the_real_account(self):
        uid = self._make_user("ajoseph", "Member")
        self.sql("UPDATE users SET email = 'aj@example.com' WHERE id = ?", uid)
        self.login("aj@example.com", "wrong-password-1")
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM login_attempts WHERE username = 'ajoseph'").fetchone()[0], 1)

    def test_no_username_may_be_another_accounts_email_and_back(self):
        """The access test of 16 Oct: a username equal to a colleague's email broke that
        colleague's sign-in by email, and a sign-up link could be used to do it."""
        uid = self._make_user("ajoseph", "Member")
        self.sql("UPDATE users SET email = 'aj@corp.example' WHERE id = ?", uid)
        # the Users page: no username that is someone's address, no address that is someone's username
        self.client.post("/users", data={"username": "AJ@corp.example", "name": "Squat", "password": STRONG_PASSWORD, "role": "Member"})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users WHERE lower(username) = 'aj@corp.example'")[0][0], 0)
        self._make_user("boss@corp.example", "Member")   # a username that looks like an address
        other = self._make_user("other", "Member")
        self.client.post(f"/users/{other}/email", data={"email": "BOSS@corp.example"})
        self.assertIsNone(self.sql("SELECT email FROM users WHERE id = ?", other)[0][0])
        # a sign-up link: the same two refusals
        self.ctx()
        from services import signup
        raw = signup.create("Staff", "Member", None, None, 7, 5, "admin")
        anon = app_module.app.test_client()
        form = {"name": "Sam", "username": "aj@corp.example", "email": "sam@corp.example", "password": STRONG_PASSWORD}
        self.assertEqual(anon.post(f"/api/join/{raw}", json=form).status_code, 400)
        self.assertEqual(anon.post(f"/api/join/{raw}", json={**form, "username": "sam", "email": "boss@corp.example"}).status_code, 400)
        self.assertEqual(anon.post(f"/api/join/{raw}", json={**form, "username": "sam"}).status_code, 200)
        # and the real owner still signs in by email
        self.assertEqual(self._signed_in(self.login("aj@corp.example")), "ajoseph")
