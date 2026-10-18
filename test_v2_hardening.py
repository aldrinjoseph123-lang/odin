"""Odin 2.0 hardening (17 Oct 2026, the user's decisions): intake tokens expire and may be
held to an address list (loophole 64), duplicate and refused intakes are audited (bounded),
a pending intake's details can be corrected before the confirm, and an unread calendar
feed switches itself off (loophole 66). Run with: python -m unittest test_v2_hardening"""
import inspect
from datetime import datetime, timedelta
from unittest.mock import patch

from test_app import STRONG_PASSWORD, app_module
from test_v2_intake import CLOCK, DEAL, J, IntakeBase


def iso(**delta):
    return (datetime.utcnow() + timedelta(**delta)).isoformat()


class TokenExpiryTestCase(IntakeBase):
    def test_an_intake_token_lives_as_long_as_the_policy_says(self):
        self._set_policy(intake_token_days="10")
        self.token()   # posts days=30: the policy wins for the create scope
        expires = datetime.fromisoformat(self.sql("SELECT expires_at FROM api_tokens")[0][0])
        self.assertAlmostEqual((expires - datetime.utcnow()).total_seconds() / 86400, 10, delta=0.01)
        self.assertIn("10 days", self.sql("SELECT details FROM audit_logs WHERE action = 'create_api_token'")[0][0])

    def test_an_expired_token_is_401_in_its_own_words_logged_and_audited(self):
        t = self.token()
        self.sql("UPDATE api_tokens SET expires_at = ?", iso(days=-1))
        r = self.post(DEAL, token=t)
        self.assertEqual(r.status_code, 401)
        self.assertIn("expired on", r.get_json()["error"])
        self.assertIn("renew it under Settings › Integrations › Intake", r.get_json()["error"])
        self.assertEqual(self.tuples("SELECT status, result FROM intake_calls"), [(401, "refused")])
        self.assertEqual(self.audits("intake_refused"), 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 0)

    def test_renew_extends_from_today_and_the_same_secret_works_again(self):
        self._set_policy(intake_token_days="20")
        t = self.token()
        self.sql("UPDATE api_tokens SET expires_at = ?", iso(days=-5))
        tid = self.sql("SELECT id FROM api_tokens")[0][0]
        r = self.client.post(f"/settings/api-tokens/{tid}/renew", headers=J)
        self.assertEqual(r.status_code, 200, r.get_json())
        expires = datetime.fromisoformat(self.sql("SELECT expires_at FROM api_tokens")[0][0])
        self.assertAlmostEqual((expires - datetime.utcnow()).total_seconds() / 86400, 20, delta=0.01)
        self.assertIn("→", self.sql("SELECT details FROM audit_logs WHERE action = 'renew_api_token'")[0][0])
        self.assertEqual(self.post(DEAL, token=t).status_code, 201)

    def test_only_an_admin_renews_and_only_an_intake_token(self):
        self.token("bi", "read")
        read_id = self.sql("SELECT id FROM api_tokens")[0][0]
        self.assertEqual(self.client.post(f"/settings/api-tokens/{read_id}/renew", headers=J).status_code, 404)
        self.token()
        tid = self.sql("SELECT id FROM api_tokens WHERE scope = 'create'")[0][0]
        self._make_user("member1", "Member")
        c, csrf = self._api_client("member1", STRONG_PASSWORD)
        self.assertEqual(c.post(f"/settings/api-tokens/{tid}/renew", headers={"X-CSRF-Token": csrf, **J}).status_code, 403)
        self.assertEqual(self.audits("renew_api_token"), 0)

    def test_an_expired_intake_token_stays_until_90_days_after_it_expired(self):
        self.token("old")
        self.sql("UPDATE api_tokens SET created_at = ?, expires_at = ?", iso(days=-400), iso(days=-30))
        self.token("new")   # making a token sweeps the long-dead ones
        self.assertEqual(sorted(r[0] for r in self.sql("SELECT name FROM api_tokens")), ["new", "old"])


class AddressTestCase(IntakeBase):
    def call(self, ip, token, body=DEAL, **headers):
        return app_module.app.test_client().post("/api/v1/intake", json=body, environ_base={"REMOTE_ADDR": ip},
                                                 headers={"Authorization": f"Bearer {token}", **headers})

    def test_a_call_from_outside_the_list_is_403_logged_and_audited(self):
        t = self.token()
        self._set_policy(intake_allowed_ips="203.0.113.0/24, 198.51.100.7")
        r = self.call("192.0.2.1", t)
        self.assertEqual(r.status_code, 403)
        self.assertIn("192.0.2.1", r.get_json()["error"])
        self.assertEqual(self.tuples("SELECT status, result FROM intake_calls"), [(403, "refused")])
        self.assertEqual(self.audits("intake_refused"), 1)
        self.assertEqual(self.call("203.0.113.40", t).status_code, 201)
        self.assertEqual(self.call("198.51.100.7", t, dict(DEAL, deal_id="D-2")).status_code, 201)
        self.assertEqual(self.call("::ffff:203.0.113.41", t, dict(DEAL, deal_id="D-3")).status_code, 201)

    def test_a_forwarded_for_header_is_not_believed_without_the_proxy_setting(self):
        t = self.token()
        self._set_policy(intake_allowed_ips="203.0.113.0/24")
        self.assertEqual(self.call("192.0.2.1", t, **{"X-Forwarded-For": "203.0.113.9"}).status_code, 403)

    def test_refusals_by_address_do_not_use_up_the_minute(self):
        t = self.token()
        self._set_policy(intake_allowed_ips="203.0.113.0/24", intake_rate_per_min="2")
        with patch("services.intake._now", return_value=CLOCK):
            for _ in range(5):
                self.assertEqual(self.call("192.0.2.1", t).status_code, 403)
            self.assertEqual(self.call("203.0.113.40", t).status_code, 201)

    def test_the_list_is_checked_when_saved(self):
        bad = self.client.post("/settings/policies/intake", data={"intake_allowed_ips": "203.0.113.0/24, not-an-ip"}, headers=J)
        self.assertEqual(bad.status_code, 400)
        self.assertIn("not-an-ip", " ".join(bad.get_json()["messages"]))
        ok = self.client.post("/settings/policies/intake", data={"intake_allowed_ips": "203.0.113.0/24 2001:db8::/32"}, headers=J)
        self.assertEqual(ok.status_code, 200, ok.get_json())


class RetryAuditTestCase(IntakeBase):
    def rows(self, action):
        return self.tuples("SELECT username, details FROM audit_logs WHERE action = ? ORDER BY id", action)

    def test_a_duplicate_is_audited_once_a_minute(self):
        self.post(DEAL)
        for _ in range(3):
            self.assertEqual(self.post(DEAL).status_code, 200)
        self.assertEqual(self.rows("intake_duplicate"), [("token:crm", "HTTP 200: deal D-1001 already made rollout 1")])
        with patch("services.intake.AUDIT_EVERY", 0):   # the minute is over
            self.post(DEAL)
        self.assertEqual(len(self.rows("intake_duplicate")), 2)

    def test_refusals_are_audited_once_a_minute_per_status(self):
        self._set_policy(intake_rate_per_min="100")
        for _ in range(4):
            self.assertEqual(self.post({"client": "C"}).status_code, 400)
        self._set_policy(intake_sources="someone-else")
        self.assertEqual(self.post(DEAL).status_code, 403)
        self.assertEqual(self.post(DEAL).status_code, 403)
        got = self.rows("intake_refused")
        self.assertEqual([(u, d[:9]) for u, d in got], [("token:crm", "HTTP 400:"), ("token:crm", "HTTP 403:")])
        self.assertIn("is required", got[0][1])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM intake_calls")[0][0], 6)   # the call log keeps every one

    def test_the_bound_is_per_token(self):
        other = self.token("other")
        self.post({"client": "C"})
        self.post({"client": "C"}, token=other)
        self.assertEqual([u for u, _ in self.rows("intake_refused")], ["token:crm", "token:other"])

    def test_a_rate_limited_call_is_audited_as_refused(self):
        self._set_policy(intake_rate_per_min="1")
        with patch("services.intake._now", return_value=CLOCK):
            self.post(DEAL)
            self.assertEqual(self.post(dict(DEAL, deal_id="D-2")).status_code, 429)
        self.assertTrue(self.rows("intake_refused")[0][1].startswith("HTTP 429:"))


class EditPendingTestCase(IntakeBase):
    def edit(self, pid=1, **form):
        return self.client.post(f"/projects/{pid}/intake/edit", data=form, headers=J)

    def test_staff_correct_the_details_before_confirming_audited_old_to_new(self):
        region = self.client.post("/api/fields", json={"name": "Region", "kind": "choice", "choices": ["UAE", "KSA"]}).get_json()["id"]
        self.post(DEAL)
        r = self.edit(name="Branch firewalls (phase 1)", client="Acme Bank", vendor_name="Palo Alto", product_name="PA-440",
                      delivery_mode="Distribution/MSSP", target_end_date="2027-07-15", po_number="PO-78", **{f"field_{region}": "UAE"})
        self.assertEqual(r.status_code, 200, r.get_json())
        p = self.row()
        self.assertEqual((p["name"], p["vendor_name"], p["product_name"], p["delivery_mode"], p["target_end_date"], p["po_number"], p["intake_pending"]),
                         ("Branch firewalls (phase 1)", "Palo Alto", "PA-440", "Distribution/MSSP", "2027-07-15", "PO-78", 1))
        details = self.sql("SELECT details FROM audit_logs WHERE action = 'intake_edit'")[0][0]
        for words in ("name: Branch firewalls → Branch firewalls (phase 1)", "vendor_name: Fortinet → Palo Alto", "target_end_date: 2027-06-30 → 2027-07-15", "Region: — → UAE"):
            self.assertIn(words, details)
        self.assertNotIn("client:", details)   # unchanged keys are not in the row
        self.assertEqual(self.confirm().status_code, 200)

    def test_a_key_left_out_keeps_its_value_and_bad_values_are_refused(self):
        self.post(DEAL)
        self.assertEqual(self.edit(po_number="PO-9").status_code, 200)
        self.assertEqual((self.row()["po_number"], self.row()["name"]), ("PO-9", "Branch firewalls"))
        self.assertEqual(self.edit(delivery_mode="Teleport").status_code, 400)
        self.assertEqual(self.edit(name="  ").status_code, 400)
        self.assertEqual(self.edit(target_end_date="soon").status_code, 400)
        self.assertEqual(self.edit(vendor_name="x" * 121).status_code, 400)
        self.assertEqual(self.row()["delivery_mode"], "Outsourced")
        self.assertEqual(self.audits("intake_edit"), 1)

    def test_a_viewer_cannot_and_a_confirmed_rollout_is_not_an_intake(self):
        self.post(DEAL)
        self._make_user("watcher", "Viewer")
        v, csrf = self._api_client("watcher", STRONG_PASSWORD)
        self.assertEqual(v.post("/projects/1/intake/edit", data={"name": "Mine"}, headers={"X-CSRF-Token": csrf, **J}).status_code, 403)
        self.confirm()
        self.assertEqual(self.edit(name="Late").status_code, 400)
        self.assertEqual(self.row()["name"], "Branch firewalls")

    def test_other_writes_are_still_refused_while_pending(self):
        self.post(DEAL)
        self.assertEqual(self.client.post("/projects/1/edit", data={"name": "X", "client": "Y"}, headers=J).status_code, 400)


class CalendarIdleTestCase(IntakeBase):
    def feed(self):
        url = self.client.post("/account/calendar", headers=J).get_json()["url"]
        return url[url.index("/feeds/"):]

    def last_read(self):
        return self.sql("SELECT ics_last_read_at FROM users WHERE id = 1")[0][0]

    def test_a_read_is_noted_at_most_once_an_hour(self):
        path = self.feed()
        self.assertIsNone(self.last_read())
        self.assertEqual(app_module.app.test_client().get(path).status_code, 200)
        first = self.last_read()
        self.assertTrue(first)
        self.sql("UPDATE users SET ics_last_read_at = ? WHERE id = 1", iso(minutes=-30))
        half = self.last_read()
        app_module.app.test_client().get(path)
        self.assertEqual(self.last_read(), half)   # within the hour: no write
        self.sql("UPDATE users SET ics_last_read_at = ? WHERE id = 1", iso(hours=-2))
        app_module.app.test_client().get(path)
        self.assertGreater(self.last_read(), half)

    def test_the_nightly_step_switches_off_feeds_nobody_reads(self):
        from services import ics
        pat = self._make_user("pat", "Member")
        self.feed()
        self.sql("UPDATE users SET ics_token_hash = 'h-pat', ics_created_at = ?, ics_last_read_at = ? WHERE id = ?", iso(days=-90), iso(days=-5), pat)
        self.sql("UPDATE users SET ics_created_at = ?, ics_last_read_at = ? WHERE id = 1", iso(days=-90), iso(days=-31))
        self.ctx()
        self.assertEqual(ics.switch_off_idle(), 1)
        self.assertEqual(self.tuples("SELECT id, ics_token_hash IS NULL FROM users WHERE id IN (1, ?) ORDER BY id", pat), [(1, 1), (pat, 0)])
        self.assertEqual(self.tuples("SELECT username, details FROM audit_logs WHERE action = 'revoke_calendar_feed'"),
                         [("scheduler", "calendar feed switched off: unused 30 days")])

    def test_a_feed_never_read_counts_from_when_it_was_made_and_0_is_never(self):
        from services import ics
        self.feed()
        self.ctx()
        self.assertEqual(ics.switch_off_idle(), 0)   # made today
        self.sql("UPDATE users SET ics_created_at = ? WHERE id = 1", iso(days=-40))
        self._set_policy(ics_idle_days="0")
        self.assertEqual(ics.switch_off_idle(), 0)
        self._set_policy(ics_idle_days="30")
        self.assertEqual(ics.switch_off_idle(), 1)

    def test_the_housekeeping_runs_it_and_the_account_page_says_so(self):
        import scheduler
        self.assertIn("idle_calendar_feeds", inspect.getsource(scheduler))
        path = self.feed()
        app_module.app.test_client().get(path)
        cal = self.client.get("/api/account").get_json()["calendar"]
        self.assertEqual((cal["idle_days"], bool(cal["last_read_at"])), (30, True))
        self.feed()   # a new address starts unread
        self.assertIsNone(self.client.get("/api/account").get_json()["calendar"]["last_read_at"])


if __name__ == "__main__":
    import unittest
    unittest.main()
