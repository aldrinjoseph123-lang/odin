"""Sign-in mail through Resend (16 Oct 2026): links, resets, confirmations and
invitations; notifications stay on Microsoft 365. Never a real send: Resend's
HTTP call (services.resend._post) is patched.
Run with: python -m unittest test_v18_resend"""
import io
import json
import urllib.error
from unittest.mock import patch

from test_app import STRONG_PASSWORD, app_module, flashed
from test_fix_logic import FixBase

J = {"Accept": "application/json"}
KEY = "re_test_key_not_real_0123456789"


class ResendBase(FixBase):
    def setUp(self):
        FixBase.setUp(self)
        self.sql("UPDATE users SET email = 'admin@corp.example' WHERE id = 1")
        self.pm = self._make_user("pm", "Member")
        self.sql("UPDATE users SET email = 'pm@corp.example' WHERE id = ?", self.pm)

    def resend_on(self, key=KEY):
        r = self.client.post("/settings/policies/notifications", data={"resend_enabled": "1", "resend_api_key": key}, headers=J)
        self.assertEqual(r.status_code, 200)


class ResendTestCase(ResendBase):
    def test_off_by_default_sign_in_mail_stays_on_microsoft(self):
        self.sql("INSERT INTO settings (key, value) VALUES ('policy.notify_email_enabled', '1') ON CONFLICT(key) DO UPDATE SET value = '1'")
        with patch("services.resend._post") as post, patch("graph.send_mail", return_value=(True, None)) as mail:
            app_module.app.test_client().post("/auth/reset", data={"email": "pm@corp.example"})
        post.assert_not_called()
        self.assertEqual(mail.call_args.args[0], "pm@corp.example")

    def test_on_a_reset_goes_through_resend_even_with_microsoft_mail_off(self):
        self.resend_on()   # Microsoft 365 is not connected and email notifications are off
        with patch("services.resend._post", return_value={"id": "x"}) as post, patch("graph.send_mail") as mail:
            app_module.app.test_client().post("/auth/reset", data={"email": "pm@corp.example"})
        mail.assert_not_called()
        payload, key = post.call_args.args
        self.assertEqual(key, KEY)
        self.assertEqual(payload["to"], ["pm@corp.example"])
        self.assertEqual(payload["from"], "Odin PMS <odin-pms@protect24x7.com>")
        self.assertEqual(payload["reply_to"], ["notifications@protect24x7.com"])
        self.assertEqual(payload["subject"], "Reset your Odin password")
        self.assertIn("/auth/reset/", payload["html"])
        self.assertIn("EVERY PROJECT. ON WATCH.", payload["html"])   # the branded shell, as Microsoft mail wears

    def test_a_partner_invite_link_goes_through_resend(self):
        self.resend_on()
        self.new_project(name="P", client="C")
        with patch("services.resend._post", return_value={"id": "x"}) as post:
            self.client.post("/projects/1/participants/invite", data={"email": "ann@customer.example", "name": "Ann", "role": "Customer"})
        self.assertEqual(post.call_args.args[0]["to"], ["ann@customer.example"])
        self.assertEqual(post.call_args.args[0]["subject"], "Your Odin sign-in link")

    def test_notifications_never_use_resend(self):
        self.resend_on()
        from services.notifications import notify_users
        with patch("services.resend._post") as post, app_module.app.test_request_context():
            notify_users([self.pm], "nudge", None, "Hello", "A note")
        post.assert_not_called()

    def test_the_daily_limit_is_named_and_the_admins_are_told_once(self):
        self.resend_on()
        quota = urllib.error.HTTPError("https://api.resend.com/emails", 429, "Too Many Requests", {},
                                       io.BytesIO(json.dumps({"name": "daily_quota_exceeded", "message": "You have reached your daily email quota"}).encode()))
        from services import resend
        with patch("services.resend._post", side_effect=quota), app_module.app.test_request_context():
            ok, error = resend.send_account_mail("pm@corp.example", "Your Odin sign-in link", "<p>x</p>")
            self.assertFalse(ok)
            self.assertIn("daily limit", error)
            resend.send_account_mail("pm@corp.example", "Your Odin sign-in link", "<p>x</p>")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE kind = 'ops' AND title LIKE '%Resend%'")[0][0], 1)

    def test_a_refusal_falls_back_to_microsoft_when_it_is_connected(self):
        self.resend_on()
        from services import resend
        with patch("services.resend._post", side_effect=OSError("network down")), \
                patch("graph.is_connected", return_value=True), patch("graph.send_mail", return_value=(True, None)) as mail, \
                app_module.app.test_request_context():
            self.assertEqual(resend.send_account_mail("pm@corp.example", "s", "<p>x</p>"), (True, None))
        self.assertEqual(mail.call_args.args[0], "pm@corp.example")

    def test_the_key_is_sealed_write_only_and_audited_as_set(self):
        self.resend_on()
        stored = self.sql("SELECT value FROM settings WHERE key = 'policy.resend_api_key'")[0][0]
        self.assertNotIn(KEY, stored)
        page = json.dumps(self.client.get("/api/settings?section=notifications").get_json())
        self.assertNotIn(KEY, page)
        self.assertNotIn(KEY, json.dumps([list(r) for r in self.sql("SELECT details FROM audit_logs")]))

    def test_the_settings_test_button_sends_through_resend_alone(self):
        self.assertIn("API key", self.client.post("/settings/notifications/test-resend", headers=J).get_json()["messages"][-1])
        self.resend_on()
        with patch("services.resend._post", return_value={"id": "x"}) as post, patch("graph.send_mail") as mail:
            r = self.client.post("/settings/notifications/test-resend", headers=J).get_json()
        mail.assert_not_called()
        self.assertEqual(post.call_args.args[0]["to"], ["admin@corp.example"])
        self.assertIn("Sent to admin@corp.example", r["messages"][-1])
        member = app_module.app.test_client()
        member.post("/login", data={"username": "pm", "password": STRONG_PASSWORD})
        csrf = member.get("/api/session").get_json()["csrf"]
        self.assertEqual(member.post("/settings/notifications/test-resend", headers={**J, "X-CSRF-Token": csrf}).status_code, 403)
