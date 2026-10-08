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
from test_app import STRONG_PASSWORD, FakeAIServer


class Base(unittest.TestCase):
    setUp = T.ContactsAndProjectMetaTestCase.setUp
    tearDown = T.ContactsAndProjectMetaTestCase.tearDown
    new_project = T.ContactsAndProjectMetaTestCase.new_project
    raw_db = T.ContactsAndProjectMetaTestCase.raw_db
    _make_user = T.ContactsAndProjectMetaTestCase._make_user
    _invite = T.ContactsAndProjectMetaTestCase._invite
    _link_for = T.ContactsAndProjectMetaTestCase._link_for
    _external_client = T.ContactsAndProjectMetaTestCase._external_client

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


if __name__ == "__main__":
    unittest.main()
