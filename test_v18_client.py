"""v1.8.0: what the browser tells the server (routes/client.py): the release on
/api/session and the crash reports. Run with: python -m unittest test_v18_client"""
import os

from test_app import app_module
from test_fix_logic import FixBase


class ClientReportTestCase(FixBase):
    def setUp(self):
        FixBase.setUp(self)
        import routes.client
        routes.client._recent.clear()

    def post(self, client, body, **kw):
        return client.post("/api/client-errors", data=body, content_type="application/json", **kw)

    def test_session_names_the_release(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as fh:
            version = fh.read().strip()
        self.assertEqual(app_module.app.test_client().get("/api/session").get_json()["version"], version)

    def test_a_report_is_logged_without_a_token_or_a_sign_in_and_stored_nowhere(self):
        before = self.sql("SELECT COUNT(*) FROM audit_logs")[0][0]
        with self.assertLogs(app_module.app.logger, "WARNING") as logs:
            r = self.post(app_module.app.test_client(), '{"kind":"render","message":"boom\\nline","path":"/board","version":"1.8.0"}')
        self.assertEqual(r.status_code, 204)
        self.assertIn("kind=render path=/board version=1.8.0: boom | line", logs.output[0])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM audit_logs")[0][0], before)

    def test_signed_in_reports_name_the_person(self):
        c, _ = self._api_client()
        with self.assertLogs(app_module.app.logger, "WARNING") as logs:
            self.post(c, '{"message":"x"}')
        self.assertIn("user:1", logs.output[0])

    def test_rate_limited_size_capped_and_junk_tolerated(self):
        c = app_module.app.test_client()
        with self.assertLogs(app_module.app.logger, "WARNING") as logs:
            for _ in range(15):
                self.post(c, '{"message":"again"}')
            self.post(c, "x" * 9000)   # over the cap: dropped (and the limit is spent anyway)
        self.assertEqual(len(logs.output), 10)
        import routes.client
        routes.client._recent.clear()
        with self.assertLogs(app_module.app.logger, "WARNING") as logs:
            self.assertEqual(self.post(c, "not json").status_code, 204)
            self.assertEqual(self.post(c, "[1, 2]").status_code, 204)
        self.assertEqual(len(logs.output), 2)

    def test_other_posts_still_need_the_token(self):
        c, _ = self._api_client()
        self.assertEqual(self.post(c, '{"all": true}').status_code, 204)   # this door: no token needed
        self.assertEqual(c.post("/api/notifications/read", data='{"all": true}', content_type="application/json").status_code, 400)
