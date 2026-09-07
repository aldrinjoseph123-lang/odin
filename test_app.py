import io
import os
import re
import secrets
import sqlite3
import tempfile
from datetime import datetime
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from flask.testing import FlaskClient

import app as app_module
import db as db_module
import security as app_module_security

# Passwords must now satisfy security.password_problem (12+ chars, mixed).
STRONG_PASSWORD = "Correct-Horse-9"


class CSRFTestClient(FlaskClient):
    """Test client that carries the CSRF token, like a real browser would.

    The app rejects any state-changing request without a valid token. Rather
    than hand-editing every POST in this suite, read the token straight out of
    the session on each call — which also survives login, since logging in
    deliberately clears the session (session-fixation defence) and mints a new
    token on the next render.
    """

    def post(self, *args, **kwargs):
        data = kwargs.get("data")
        # Many routes are POSTed with no body at all (delete/disconnect
        # buttons), so default to an empty dict rather than skipping those.
        if data is None:
            data = {}
        if isinstance(data, dict) and "_csrf" not in data:
            with self.session_transaction() as sess:
                token = sess.get("_csrf_token")
                if not token:
                    token = secrets.token_urlsafe(32)
                    sess["_csrf_token"] = token
            data["_csrf"] = token
            kwargs["data"] = data
        return super().post(*args, **kwargs)


app_module.app.test_client_class = CSRFTestClient




def settle_seed_admin():
    """The seed admin is flagged must_change_password — right for production,
    noise for tests that just need a logged-in admin. Clear it here; the
    forced-change behaviour has its own tests."""
    con = sqlite3.connect(db_module.DB_PATH)
    con.execute("UPDATE users SET must_change_password = 0")
    con.commit(); con.close()


def isolate_uploads(test):
    """Point every upload path at a throwaway directory for one test.

    routes/projects.py did `from db import UPLOAD_DIR`, so it holds the value
    bound at import time — reassigning db_module.UPLOAD_DIR alone never reached
    it, and every test run wrote real files into the repo's uploads/ folder.
    Patching both bindings keeps tests off real data, which matters most for
    cleanup_soft_deletes: it deletes directories for projects absent from the
    database, and a test database plus the real uploads directory is a
    combination that deletes real files.
    """
    import routes.projects as projects_module
    tmp = tempfile.mkdtemp()
    db_module.UPLOAD_DIR = tmp
    patcher = patch.object(projects_module, "UPLOAD_DIR", tmp)
    patcher.start()
    test.addCleanup(patcher.stop)
    return tmp


class PMSTestCase(unittest.TestCase):
    def setUp(self):
        fd, db_module.DB_PATH = tempfile.mkstemp()
        os.close(fd)
        os.remove(db_module.DB_PATH)  # init_db must see a fresh path to seed the admin user
        isolate_uploads(self)
        app_module.init_db()
        settle_seed_admin()
        self.client = app_module.app.test_client()

    def tearDown(self):
        os.unlink(db_module.DB_PATH)

    def login(self, client=None):
        client = client or self.client
        return client.post("/login", data={"username": "admin", "password": "changeme"})

    def test_login_required_redirects_to_login(self):
        resp = self.client.get("/board")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_login_success_reaches_board(self):
        self.login()
        resp = self.client.get("/board")
        self.assertEqual(resp.status_code, 200)

    def test_create_project_and_stage_change_logs_note(self):
        self.login()
        self.client.post(
            "/projects/new",
            data={
                "po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"),
                "name": "Test Proj", "client": "Test Client", "delivery_mode": "Distribution/MSSP",
            },
        )
        resp = self.client.get("/projects")
        self.assertIn(b"Test Proj", resp.data)

        self.client.post("/projects/1/stage", data={"stage": "Kickoff", "note": "started work"})
        resp = self.client.get("/projects/1")
        self.assertIn(b"started work", resp.data)
        self.assertIn(b"Kickoff", resp.data)

    def test_stale_filter_only_shows_stale_projects(self):
        self.login()
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Stale Proj", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Fresh Proj", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        old = (app_module.datetime.utcnow() - app_module.timedelta(days=30)).isoformat()
        db = sqlite3.connect(db_module.DB_PATH)
        db.execute("UPDATE projects SET updated_at = ? WHERE id = 1", (old,))
        db.commit()
        db.close()
        resp = self.client.get("/projects?view=stale")
        self.assertIn(b"Stale Proj", resp.data)
        self.assertNotIn(b"Fresh Proj", resp.data)

    def test_guest_link_works_without_login_bad_token_404s(self):
        self.login()
        self.client.post(
            "/projects/new",
            data={
                "po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"),
                "name": "Guest Proj", "client": "C",
                "delivery_mode": "Outsourced", "outsourcer_name": "Vendor X",
            },
        )
        resp = self.client.get("/projects/1")
        match = re.search(rb"/guest/([\w-]+)", resp.data)
        self.assertIsNotNone(match, "guest link not rendered on project detail page")
        token = match.group(1).decode()

        anon_client = app_module.app.test_client()
        resp_ok = anon_client.get(f"/guest/{token}")
        self.assertEqual(resp_ok.status_code, 200)
        resp_bad = anon_client.get("/guest/not-a-real-token")
        self.assertEqual(resp_bad.status_code, 404)

    def test_new_user_can_log_in(self):
        self.login()
        self.client.post(
            "/users", data={"name": "New User", "username": "newuser", "password": STRONG_PASSWORD}
        )
        new_client = app_module.app.test_client()
        resp = new_client.post("/login", data={"username": "newuser", "password": STRONG_PASSWORD})
        self.assertEqual(resp.status_code, 302)
        resp = new_client.get("/board")
        self.assertEqual(resp.status_code, 200)

    def test_project_delete_removes_it(self):
        self.login()
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Temp", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        self.client.post("/projects/1/delete")
        resp = self.client.get("/projects")
        self.assertNotIn(b"Temp", resp.data)

    def test_viewer_cannot_write_but_can_read(self):
        self.login()
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Viewer Test", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        self.client.post(
            "/users", data={"name": "Vera Viewer", "username": "vera", "password": STRONG_PASSWORD, "role": "Viewer"}
        )
        viewer_client = app_module.app.test_client()
        viewer_client.post("/login", data={"username": "vera", "password": STRONG_PASSWORD})

        resp = viewer_client.get("/projects/1")
        self.assertEqual(resp.status_code, 200)

        resp = viewer_client.post("/projects/1/stage", data={"stage": "Kickoff"})
        self.assertEqual(resp.status_code, 403)
        resp = viewer_client.get("/projects/new")
        self.assertEqual(resp.status_code, 403)
        resp = viewer_client.get("/settings")
        self.assertEqual(resp.status_code, 403)
        resp = viewer_client.get("/users")
        self.assertEqual(resp.status_code, 403)

    def test_member_cannot_access_settings_or_users(self):
        self.login()
        self.client.post(
            "/users", data={"name": "Mo Member", "username": "mo", "password": STRONG_PASSWORD, "role": "Member"}
        )
        member_client = app_module.app.test_client()
        member_client.post("/login", data={"username": "mo", "password": STRONG_PASSWORD})

        resp = member_client.get("/settings")
        self.assertEqual(resp.status_code, 403)
        resp = member_client.get("/users")
        self.assertEqual(resp.status_code, 403)
        # but can still do normal project work
        resp = member_client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Member Proj", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        self.assertEqual(resp.status_code, 302)

    def test_deactivated_user_cannot_log_in(self):
        self.login()
        self.client.post(
            "/users", data={"name": "Gone", "username": "gone", "password": STRONG_PASSWORD, "role": "Member"}
        )
        db = sqlite3.connect(db_module.DB_PATH)
        db.row_factory = sqlite3.Row
        user_id = db.execute("SELECT id FROM users WHERE username = 'gone'").fetchone()["id"]
        db.close()
        self.client.post(f"/users/{user_id}/active", data={"active": "0"})

        fresh_client = app_module.app.test_client()
        resp = fresh_client.post("/login", data={"username": "gone", "password": STRONG_PASSWORD})
        self.assertEqual(resp.status_code, 200)  # re-renders login with flash, no redirect
        resp = fresh_client.get("/board")
        self.assertEqual(resp.status_code, 302)  # never actually logged in

    def test_settings_stage_rename_cascades_to_projects(self):
        self.login()
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Stage Test", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        stages = self.client.get("/settings").data
        self.assertIn(b"PO Received", stages)

        db = sqlite3.connect(db_module.DB_PATH)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT id FROM stages WHERE name = 'PO Received'").fetchone()
        db.close()
        self.client.post(f"/settings/stages/{row['id']}/rename", data={"name": "PO In Hand"})

        resp = self.client.get("/projects/1")
        self.assertIn(b"PO In Hand", resp.data)
        self.assertNotIn(b"PO Received", resp.data)

    def test_settings_stage_delete_blocked_when_in_use(self):
        self.login()
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "In Use", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        db = sqlite3.connect(db_module.DB_PATH)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT id FROM stages WHERE name = 'PO Received'").fetchone()
        db.close()
        self.client.post(f"/settings/stages/{row['id']}/delete")

        db = sqlite3.connect(db_module.DB_PATH)
        db.row_factory = sqlite3.Row
        still_there = db.execute("SELECT 1 FROM stages WHERE name = 'PO Received'").fetchone()
        db.close()
        self.assertIsNotNone(still_there)


class AlertDismissalTestCase(unittest.TestCase):
    def setUp(self):
        fd, db_module.DB_PATH = tempfile.mkstemp()
        os.close(fd)
        os.remove(db_module.DB_PATH)
        isolate_uploads(self)
        app_module.init_db()
        settle_seed_admin()
        self.client = app_module.app.test_client()
        self.client.post("/login", data={"username": "admin", "password": "changeme"})
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Stale Proj", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        self._make_stale(1)

    def tearDown(self):
        os.unlink(db_module.DB_PATH)

    def _make_stale(self, project_id):
        old = (date.today() - timedelta(days=60)).isoformat() + "T00:00:00"
        db = sqlite3.connect(db_module.DB_PATH)
        db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (old, project_id))
        db.commit()
        db.close()

    def test_stale_alert_shows_then_dismiss_clears_it(self):
        resp = self.client.get("/board")
        self.assertIn(b"untouched for a while", resp.data)

        resp = self.client.get("/alerts/1/dismiss/stale?next=board", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/board")
        # the project itself still appears on the board — only the banner entry goes
        self.assertNotIn(b"untouched for a while", resp.data)

    def test_dismiss_without_next_redirects_to_project(self):
        resp = self.client.get("/alerts/1/dismiss/stale")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/projects/1", resp.headers["Location"])

    def test_invalid_alert_type_404s(self):
        resp = self.client.get("/alerts/1/dismiss/not-a-real-type")
        self.assertEqual(resp.status_code, 404)

    def test_alert_reappears_after_relogin_even_with_unchanged_data(self):
        self.client.get("/alerts/1/dismiss/stale?next=board")
        resp = self.client.get("/board")
        self.assertNotIn(b"untouched for a while", resp.data)

        # fresh login must show every real alert again — dismissals are session-only
        self.client.post("/login", data={"username": "admin", "password": "changeme"})
        resp = self.client.get("/board")
        self.assertIn(b"untouched for a while", resp.data)

    def test_dismissal_does_not_touch_database(self):
        self.client.get("/alerts/1/dismiss/stale?next=board")
        db = sqlite3.connect(db_module.DB_PATH)
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("alert_dismissals", tables)
        db.close()


class IntegrationNotificationTestCase(unittest.TestCase):
    def setUp(self):
        fd, db_module.DB_PATH = tempfile.mkstemp()
        os.close(fd)
        os.remove(db_module.DB_PATH)
        isolate_uploads(self)
        app_module.init_db()
        settle_seed_admin()
        self.client = app_module.app.test_client()
        self.client.post("/login", data={"username": "admin", "password": "changeme"})
        self.client.post("/account/email", data={"email": "admin@example.com"})

    def tearDown(self):
        os.unlink(db_module.DB_PATH)

    def enable_notifications(self):
        with app_module.app.test_request_context():
            app_module.set_setting("notify_email_enabled", "1")
            app_module.set_setting("notify_teams_enabled", "1")
            app_module.set_setting("onedrive_mirror_uploads_enabled", "1")

    @patch("app.graph.send_mail", return_value=(True, None))
    @patch("app.graph.send_teams_message", return_value=(True, None))
    def test_notifications_skipped_when_toggles_off(self, mock_teams, mock_mail):
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Quiet Proj", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        self.client.post("/projects/1/stage", data={"stage": "Kickoff"})
        mock_mail.assert_not_called()
        mock_teams.assert_not_called()

    @patch("app.graph.send_mail", return_value=(True, None))
    @patch("app.graph.send_teams_message", return_value=(True, None))
    def test_notifications_fire_when_toggles_on(self, mock_teams, mock_mail):
        self.enable_notifications()
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Loud Proj", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        mock_mail.assert_called_once()
        mock_teams.assert_called_once()

        mock_mail.reset_mock()
        mock_teams.reset_mock()
        self.client.post("/projects/1/stage", data={"stage": "Kickoff"})
        mock_mail.assert_called_once()
        mock_teams.assert_called_once()

    @patch("app.graph.send_mail", return_value=(False, "simulated Graph outage"))
    @patch("app.graph.send_teams_message", return_value=(False, "simulated Graph outage"))
    def test_notification_failure_does_not_break_request(self, mock_teams, mock_mail):
        self.enable_notifications()
        resp = self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Resilient Proj", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get("/projects")
        self.assertIn(b"Resilient Proj", resp.data)

    @patch("app.graph.upload_file", return_value=(True, None))
    def test_document_upload_mirrors_to_onedrive_when_enabled(self, mock_upload):
        self.enable_notifications()
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Doc Proj", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        mock_upload.reset_mock()  # creation itself also mirrors the bundled Client PO upload
        self.client.post(
            "/projects/1/documents",
            data={"category": "Client PO", "file": (io.BytesIO(b"%PDF-1.4 fake pdf bytes"), "po.pdf")},
            content_type="multipart/form-data",
        )
        mock_upload.assert_called_once()
        args, _kwargs = mock_upload.call_args
        self.assertIn("po.pdf", args[1])

    @patch("app.graph.upload_file")
    def test_document_upload_does_not_mirror_when_disabled(self, mock_upload):
        self.client.post(
            "/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Doc Proj 2", "client": "C", "delivery_mode": "Distribution/MSSP"}
        )
        self.client.post(
            "/projects/1/documents",
            data={"category": "Client PO", "file": (io.BytesIO(b"%PDF-1.4 fake pdf bytes"), "po2.pdf")},
            content_type="multipart/form-data",
        )
        mock_upload.assert_not_called()


class MicrosoftOAuthConnectTestCase(unittest.TestCase):
    def setUp(self):
        fd, db_module.DB_PATH = tempfile.mkstemp()
        os.close(fd)
        os.remove(db_module.DB_PATH)
        isolate_uploads(self)
        app_module.init_db()
        settle_seed_admin()
        app_module.graph.DB_PATH = db_module.DB_PATH
        self.client = app_module.app.test_client()
        self.client.post("/login", data={"username": "admin", "password": "changeme"})

    def tearDown(self):
        os.unlink(db_module.DB_PATH)

    def test_azure_app_credentials_save_and_show_masked(self):
        resp = self.client.post(
            "/settings/azure-app",
            data={"client_id": "cid-123", "tenant_id": "tid-456", "client_secret": "super-secret-value"},
        )
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get("/settings")
        self.assertIn(b"cid-123", resp.data)
        self.assertNotIn(b"super-secret-value", resp.data)
        self.assertTrue(app_module.graph.oauth_client_configured())

    def test_azure_app_requires_secret_on_first_save(self):
        resp = self.client.post(
            "/settings/azure-app", data={"client_id": "cid-123", "tenant_id": "tid-456", "client_secret": ""}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(app_module.graph.oauth_client_configured())

    def test_azure_app_blank_secret_keeps_existing_on_update(self):
        self.client.post(
            "/settings/azure-app",
            data={"client_id": "cid-123", "tenant_id": "tid-456", "client_secret": "original-secret"},
        )
        # update just the client_id, leave secret blank
        self.client.post(
            "/settings/azure-app",
            data={"client_id": "cid-999", "tenant_id": "tid-456", "client_secret": ""},
        )
        self.assertEqual(app_module.graph._client_id(), "cid-999")
        self.assertEqual(app_module.graph._client_secret(), "original-secret")

    def test_azure_app_clear_removes_credentials_and_disconnects(self):
        self.client.post(
            "/settings/azure-app",
            data={"client_id": "cid-123", "tenant_id": "tid-456", "client_secret": "super-secret-value"},
        )
        self.client.post("/settings/azure-app/clear")
        self.assertFalse(app_module.graph.oauth_client_configured())

    @patch("app.graph.oauth_client_configured", return_value=False)
    def test_connect_blocked_without_azure_app_registration(self, _mock):
        resp = self.client.get("/integrations/connect")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/settings", resp.headers["Location"])

    @patch("app.graph.build_authorize_url", return_value="https://login.microsoftonline.com/fake-authorize")
    @patch("app.graph.oauth_client_configured", return_value=True)
    def test_connect_redirects_to_microsoft(self, _mock_configured, mock_url):
        resp = self.client.get("/integrations/connect")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["Location"], "https://login.microsoftonline.com/fake-authorize")
        mock_url.assert_called_once()

    def test_callback_rejects_mismatched_state(self):
        resp = self.client.get("/integrations/callback?state=bogus&code=abc")
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get("/settings")
        self.assertIn(b"mismatched", resp.data.lower())

    def test_callback_surfaces_microsoft_error(self):
        resp = self.client.get("/integrations/callback?error=access_denied&error_description=User+declined")
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get("/settings")
        self.assertIn(b"User declined", resp.data)

    @patch("app.graph.complete_connection", return_value=(True, "admin@company.com"))
    @patch("app.graph.build_authorize_url", return_value="https://login.microsoftonline.com/fake-authorize")
    @patch("app.graph.oauth_client_configured", return_value=True)
    def test_full_connect_flow_succeeds(self, _mock_configured, _mock_url, mock_complete):
        connect_resp = self.client.get("/integrations/connect")
        with self.client.session_transaction() as sess:
            state = sess["ms_oauth_state"]
        callback_resp = self.client.get(f"/integrations/callback?state={state}&code=fake-code")
        self.assertEqual(callback_resp.status_code, 302)
        mock_complete.assert_called_once()
        resp = self.client.get("/settings")
        self.assertIn(b"admin@company.com", resp.data)

    @patch("app.graph.disconnect")
    def test_disconnect_calls_graph_disconnect(self, mock_disconnect):
        self.client.post("/integrations/disconnect")
        mock_disconnect.assert_called_once()

    @patch("app.graph.set_channel")
    @patch("app.graph.list_channels", return_value=([{"id": "chan1", "name": "General"}], None))
    @patch("app.graph.list_joined_teams", return_value=([{"id": "team1", "name": "MSSP Delivery"}], None))
    def test_set_channel_saves_selection(self, _mock_teams, _mock_channels, mock_set):
        self.client.post("/integrations/channel", data={"team_id": "team1", "channel_id": "chan1"})
        mock_set.assert_called_once_with("team1", "MSSP Delivery", "chan1", "General")

    def test_viewer_and_member_cannot_reach_integration_routes(self):
        self.client.post(
            "/users", data={"name": "Mo", "username": "mo2", "password": STRONG_PASSWORD, "role": "Member"}
        )
        member_client = app_module.app.test_client()
        member_client.post("/login", data={"username": "mo2", "password": STRONG_PASSWORD})
        for path in ["/integrations/connect", "/integrations/callback", "/settings"]:
            resp = member_client.get(path)
            self.assertEqual(resp.status_code, 403)
        resp = member_client.post("/integrations/disconnect")
        self.assertEqual(resp.status_code, 403)


class ContactsAndProjectMetaTestCase(unittest.TestCase):
    def setUp(self):
        fd, db_module.DB_PATH = tempfile.mkstemp()
        os.close(fd)
        os.remove(db_module.DB_PATH)
        isolate_uploads(self)
        app_module.init_db()
        settle_seed_admin()
        self.client = app_module.app.test_client()
        self.client.post("/login", data={"username": "admin", "password": "changeme"})

    def tearDown(self):
        os.unlink(db_module.DB_PATH)

    def new_project(self, **fields):
        data = {"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Proj", "client": "C"}
        data.update(fields)
        return self.client.post("/projects/new", data=data)

    def raw_db(self):
        conn = sqlite3.connect(db_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def test_project_edit_updates_fields_and_reassigns_owner(self):
        self.new_project(name="Orig", client="OldClient", delivery_mode="Distribution/MSSP")
        with self.raw_db() as db:
            db.execute("INSERT INTO users (username, password_hash, name, role, active) VALUES ('bob','x','Bob','Member',1)")
            db.commit()
            bob_id = db.execute("SELECT id FROM users WHERE username='bob'").fetchone()["id"]
        resp = self.client.post("/projects/1/edit", data={
            "name": "Renamed", "client": "NewClient", "owner_id": str(bob_id),
            "via": "Direct", "delivery_mode": "Distribution/MSSP", "target_end_date": "2027-01-01",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.raw_db() as db:
            row = db.execute("SELECT name, client, owner_id, target_end_date FROM projects WHERE id=1").fetchone()
            audit = db.execute("SELECT 1 FROM audit_logs WHERE action='update_project' AND resource_id=1").fetchone()
        self.assertEqual(row["name"], "Renamed")
        self.assertEqual(row["client"], "NewClient")
        self.assertEqual(row["owner_id"], bob_id)
        self.assertEqual(row["target_end_date"], "2027-01-01")
        self.assertIsNotNone(audit)

    def test_project_edit_rejects_blank_name(self):
        self.new_project(name="Keep", client="C")
        self.client.post("/projects/1/edit", data={"name": "", "client": "C", "via": "Direct", "delivery_mode": "Distribution/MSSP"}, follow_redirects=True)
        with self.raw_db() as db:
            row = db.execute("SELECT name FROM projects WHERE id=1").fetchone()
        self.assertEqual(row["name"], "Keep")

    def test_project_edit_falls_back_to_current_owner_on_bad_id(self):
        self.new_project(name="Owned", client="C")
        with self.raw_db() as db:
            orig_owner = db.execute("SELECT owner_id FROM projects WHERE id=1").fetchone()["owner_id"]
        self.client.post("/projects/1/edit", data={
            "name": "Owned", "client": "C", "owner_id": "9999",
            "via": "Direct", "delivery_mode": "Distribution/MSSP",
        }, follow_redirects=True)
        with self.raw_db() as db:
            row = db.execute("SELECT owner_id FROM projects WHERE id=1").fetchone()
        self.assertEqual(row["owner_id"], orig_owner)

    def test_project_edit_get_prefills_form(self):
        self.new_project(name="Prefill Me", client="C")
        resp = self.client.get("/projects/1/edit")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Prefill Me", resp.data)
        self.assertIn(b"Save Changes", resp.data)

    def test_search_matches_name_client_and_po(self):
        self.new_project(name="Alpha Rollout", client="Acme")
        self.new_project(name="Beta Audit", client="Zeta Corp", po_number="PO-XYZ")
        r = self.client.get("/projects?q=Alpha")
        self.assertIn(b"Alpha Rollout", r.data)
        self.assertNotIn(b"Beta Audit", r.data)
        r = self.client.get("/projects?q=Zeta")
        self.assertIn(b"Beta Audit", r.data)
        self.assertNotIn(b"Alpha Rollout", r.data)
        r = self.client.get("/projects?q=PO-XYZ")
        self.assertIn(b"Beta Audit", r.data)
        self.assertNotIn(b"Alpha Rollout", r.data)

    @patch("routes.projects.PROJECTS_PER_PAGE", 1)
    def test_pagination_splits_pages(self):
        self.new_project(name="First Proj", client="C")
        self.new_project(name="Second Proj", client="C")
        r = self.client.get("/projects")
        self.assertIn(b"Page 1 of 2", r.data)
        r1 = self.client.get("/projects?page=1")
        r2 = self.client.get("/projects?page=2")
        # each project appears on exactly one page
        self.assertTrue((b"First Proj" in r1.data) != (b"First Proj" in r2.data))
        self.assertIn(b"Second Proj", r1.data + r2.data)

    def test_task_add_toggle_delete(self):
        self.new_project(name="TaskProj", client="C")
        self.client.post("/projects/1/tasks", data={"title": "Write SOW", "due_date": "2027-01-01"})
        with self.raw_db() as db:
            t = db.execute("SELECT * FROM tasks WHERE project_id=1").fetchone()
        self.assertEqual(t["title"], "Write SOW")
        self.assertEqual(t["done"], 0)
        self.assertIn(b"Write SOW", self.client.get("/projects/1").data)

        self.client.post(f"/projects/1/tasks/{t['id']}/toggle")
        with self.raw_db() as db:
            t2 = db.execute("SELECT done, done_at FROM tasks WHERE id=?", (t["id"],)).fetchone()
        self.assertEqual(t2["done"], 1)
        self.assertIsNotNone(t2["done_at"])

        self.client.post(f"/projects/1/tasks/{t['id']}/toggle")
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT done FROM tasks WHERE id=?", (t["id"],)).fetchone()["done"], 0)

        self.client.post(f"/projects/1/tasks/{t['id']}/delete")
        with self.raw_db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM tasks WHERE id=?", (t["id"],)).fetchone())

    def test_task_blank_title_rejected(self):
        self.new_project(name="P", client="C")
        self.client.post("/projects/1/tasks", data={"title": "   "})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"], 0)

    def test_task_overdue_flagged_on_detail(self):
        self.new_project(name="P", client="C")
        self.client.post("/projects/1/tasks", data={"title": "Late task", "due_date": "2020-01-01"})
        self.assertIn(b"countdown-overdue", self.client.get("/projects/1").data)

    def test_schedule_overdue_alert_filter_and_badge(self):
        self.new_project(name="LateProj", client="C", target_end_date="2020-01-01")
        board = self.client.get("/board").data
        self.assertIn(b"project(s) overdue", board)
        self.assertIn(b"LateProj", board)
        self.assertIn(b"LateProj", self.client.get("/projects?view=overdue").data)
        self.assertIn("Overdue — target".encode(), self.client.get("/projects/1").data)

    def test_schedule_due_soon_alert_and_filter(self):
        soon = (date.today() + timedelta(days=2)).isoformat()
        self.new_project(name="SoonProj", client="C", target_end_date=soon)
        self.assertIn(b"project(s) due soon", self.client.get("/board").data)
        self.assertIn(b"SoonProj", self.client.get("/projects?view=at_risk").data)

    def test_overdue_filter_excludes_terminal_stage(self):
        self.new_project(name="ClosedLate", client="C", target_end_date="2020-01-01")
        with self.raw_db() as db:
            terminal = db.execute("SELECT name FROM stages ORDER BY position DESC LIMIT 1").fetchone()["name"]
            db.execute("UPDATE projects SET stage=? WHERE id=1", (terminal,))
            db.commit()
        self.assertNotIn(b"ClosedLate", self.client.get("/projects?view=overdue").data)

    def test_my_work_shows_owned_projects_and_assigned_open_tasks(self):
        self.new_project(name="MineProj", client="C", target_end_date="2020-01-01")
        self.client.post("/projects/1/tasks", data={"title": "My Task", "assignee_id": "1"})
        self.client.post("/projects/1/tasks", data={"title": "Unassigned Task"})
        r = self.client.get("/my-work").data
        self.assertIn(b"MineProj", r)
        self.assertIn(b"My Task", r)
        self.assertNotIn(b"Unassigned Task", r)
        self.assertIn(b"Overdue", r)

    def test_my_work_excludes_others_projects_and_done_tasks(self):
        self.new_project(name="AdminProj", client="C")
        with self.raw_db() as db:
            db.execute("INSERT INTO users (username,password_hash,name,role,active) VALUES ('carol','x','Carol','Member',1)")
            db.commit()
            cid = db.execute("SELECT id FROM users WHERE username='carol'").fetchone()["id"]
            db.execute("UPDATE projects SET owner_id=? WHERE id=1", (cid,))
            db.execute("INSERT INTO tasks (project_id,title,done,assignee_id,created_at) VALUES (1,'Done Task',1,1,'2026-01-01')")
            db.commit()
        r = self.client.get("/my-work").data
        self.assertNotIn(b"AdminProj", r)
        self.assertNotIn(b"Done Task", r)

    def test_localdt_marks_timestamps_for_browser_localisation(self):
        from core import localdt
        out = str(localdt("2026-08-04T21:30:00.123456"))
        self.assertIn('class="localdt"', out)
        # the stored value has no zone marker; the tag must assert UTC
        self.assertIn('datetime="2026-08-04T21:30:00.123456Z"', out)
        self.assertIn(">2026-08-04 21:30<", out)   # JS-off fallback still readable
        self.assertIn('data-mode="date"', str(localdt("2026-08-04T21:30:00", "date")))
        self.assertEqual(localdt(""), "—")

    def test_nav_shows_my_open_task_count(self):
        self.new_project(name="P", client="C")
        self.assertNotIn(b"My Work (", self.client.get("/board").data)
        self.client.post("/projects/1/tasks", data={"title": "t1", "assignee_id": "1"})
        self.assertIn(b"My Work (1)", self.client.get("/board").data)
        with self.raw_db() as db:
            tid = db.execute("SELECT id FROM tasks WHERE project_id=1").fetchone()["id"]
        self.client.post(f"/projects/1/tasks/{tid}/toggle")
        # completed work shouldn't keep nagging from the nav
        self.assertNotIn(b"My Work (", self.client.get("/board").data)

    def test_empty_list_offers_create_but_filtered_empty_offers_clear(self):
        empty = self.client.get("/projects").data
        self.assertIn(b"No projects yet", empty)
        self.assertIn(b"Create the first one", empty)
        self.new_project(name="Alpha", client="C")
        filtered = self.client.get("/projects?q=zzzznope").data
        self.assertIn(b"No projects match", filtered)
        self.assertIn(b"Clear filters", filtered)

    def test_task_inline_edit_updates_without_losing_done_state(self):
        self.new_project(name="P", client="C")
        self.client.post("/projects/1/tasks", data={"title": "Typo taks", "due_date": "2027-01-01"})
        with self.raw_db() as db:
            tid = db.execute("SELECT id FROM tasks WHERE project_id=1").fetchone()["id"]
        self.client.post(f"/projects/1/tasks/{tid}/toggle")   # mark done first
        self.client.post(f"/projects/1/tasks/{tid}/edit",
                         data={"title": "Typo task", "assignee_id": "1", "due_date": "2027-02-02"})
        with self.raw_db() as db:
            t = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        self.assertEqual(t["title"], "Typo task")
        self.assertEqual(t["due_date"], "2027-02-02")
        self.assertEqual(t["assignee_id"], 1)
        self.assertEqual(t["done"], 1)   # editing must not resurrect a finished task

    def test_task_inline_edit_rejects_blank_title(self):
        self.new_project(name="P", client="C")
        self.client.post("/projects/1/tasks", data={"title": "Keep me"})
        with self.raw_db() as db:
            tid = db.execute("SELECT id FROM tasks WHERE project_id=1").fetchone()["id"]
        self.client.post(f"/projects/1/tasks/{tid}/edit", data={"title": "  "})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT title FROM tasks WHERE id=?", (tid,)).fetchone()["title"], "Keep me")

    def test_clear_completed_removes_only_finished_tasks(self):
        self.new_project(name="P", client="C")
        self.client.post("/projects/1/tasks", data={"title": "done one"})
        self.client.post("/projects/1/tasks", data={"title": "still open"})
        with self.raw_db() as db:
            tid = db.execute("SELECT id FROM tasks WHERE title='done one'").fetchone()["id"]
        self.client.post(f"/projects/1/tasks/{tid}/toggle")
        self.client.post("/projects/1/tasks/clear-completed")
        with self.raw_db() as db:
            rows = [r["title"] for r in db.execute("SELECT title FROM tasks WHERE project_id=1")]
        self.assertEqual(rows, ["still open"])

    def test_column_sort_orders_and_rejects_unknown_columns(self):
        self.new_project(name="Bravo", client="Zulu")
        self.new_project(name="Alpha", client="Yankee")
        order = lambda body: [n for n in (b"Alpha", b"Bravo") if n in body]

        asc = self.client.get("/projects?sort=name&dir=asc").data
        self.assertLess(asc.index(b"Alpha"), asc.index(b"Bravo"))
        desc = self.client.get("/projects?sort=name&dir=desc").data
        self.assertLess(desc.index(b"Bravo"), desc.index(b"Alpha"))

        # an unknown column must fall back, never reach the SQL
        fallback = self.client.get("/projects?sort=p.name);DROP+TABLE+projects;--&dir=asc")
        self.assertEqual(fallback.status_code, 200)
        with self.raw_db() as db:
            self.assertIsNotNone(
                db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='projects'").fetchone()
            )

    def test_sort_survives_filters_and_pagination_links(self):
        self.new_project(name="Alpha", client="C")
        body = self.client.get("/projects?sort=client&dir=asc&q=Alpha").data.decode()
        self.assertIn("sort=client", body)      # header links keep the active sort
        self.assertIn("q=Alpha", body)          # and keep the filter

    def test_nav_link_restores_last_project_filter(self):
        self.new_project(name="Alpha", client="C")
        # a plain visit leaves the nav link unfiltered
        self.assertIn(b'href="/projects"', self.client.get("/board").data)
        # after filtering, the nav link carries the filter back
        self.client.get("/projects?view=stale&sort=name&dir=asc")
        nav = self.client.get("/board").data.decode()
        self.assertIn("view=stale", nav)
        self.assertIn("sort=name", nav)
        # and Clear resets it
        self.client.get("/projects")
        self.assertIn('href="/projects"', self.client.get("/board").data.decode())

    def test_remembered_filter_ignores_unknown_params_and_page(self):
        self.new_project(name="Alpha", client="C")
        self.client.get("/projects?q=Alpha&page=2&evil=1")
        nav = self.client.get("/board").data.decode()
        self.assertIn("q=Alpha", nav)
        self.assertNotIn("evil=1", nav)   # only known filter keys are stored
        self.assertNotIn("page=2", nav)   # returning starts at the first page

    @patch("routes.projects.notify_event")
    def test_assigning_a_task_notifies_that_person_but_not_yourself(self, mock_notify):
        self.new_project(name="P", client="C")
        with self.raw_db() as db:
            db.execute("INSERT INTO users (username,password_hash,name,role,active) VALUES ('dana','x','Dana','Member',1)")
            db.commit()
            dana = db.execute("SELECT id FROM users WHERE username='dana'").fetchone()["id"]
        mock_notify.reset_mock()   # project creation notifies the owner; ignore that here

        # assigning to yourself is silent — you already know
        self.client.post("/projects/1/tasks", data={"title": "mine", "assignee_id": "1"})
        mock_notify.assert_not_called()

        self.client.post("/projects/1/tasks", data={"title": "theirs", "assignee_id": str(dana)})
        mock_notify.assert_called_once()
        self.assertEqual(mock_notify.call_args[0][0], {"owner_id": dana})

        # editing the title alone must not re-notify
        with self.raw_db() as db:
            tid = db.execute("SELECT id FROM tasks WHERE title='theirs'").fetchone()["id"]
        mock_notify.reset_mock()
        self.client.post(f"/projects/1/tasks/{tid}/edit",
                         data={"title": "theirs, renamed", "assignee_id": str(dana)})
        mock_notify.assert_not_called()

        # but a genuine reassignment does
        self.client.post(f"/projects/1/tasks/{tid}/edit",
                         data={"title": "theirs, renamed", "assignee_id": "1"})
        mock_notify.assert_not_called()   # reassigned to self — still silent

    def test_every_rbac_permission_is_actually_enforced_somewhere(self):
        """The RBAC matrix must not grow decorative toggles.

        A permission that no route checks renders as a switch that silently
        does nothing — an admin thinks they restricted something they didn't.
        This has regressed twice (once when RBAC was first wired up, once when
        the commercial routes were deleted and left their permissions behind),
        so it gets a guard rather than a code review.
        """
        import pathlib
        sources = "\n".join(
            path.read_text() for path in pathlib.Path("routes").glob("*.py")
        )
        unenforced = [
            perm for perm in app_module.PERMISSIONS
            if f'permission_required("{perm}")' not in sources
        ]
        self.assertEqual(unenforced, [], f"permissions in the matrix that no route checks: {unenforced}")

    def test_task_cannot_be_assigned_to_a_deactivated_user(self):
        self.new_project(name="P", client="C")
        with self.raw_db() as db:
            db.execute("INSERT INTO users (username,password_hash,name,role,active) VALUES ('gone','x','Gone','Member',0)")
            db.commit()
            gone = db.execute("SELECT id FROM users WHERE username='gone'").fetchone()["id"]
        # the dropdown never offers them, but a hand-crafted POST tries anyway
        self.client.post("/projects/1/tasks", data={"title": "orphan", "assignee_id": str(gone)})
        with self.raw_db() as db:
            self.assertIsNone(db.execute("SELECT assignee_id FROM tasks WHERE title='orphan'").fetchone()["assignee_id"])

    def test_weak_password_terms_are_rejected_even_with_padding(self):
        from security import password_problem
        # exact-match blocklisting let the app's own default through with digits
        # stapled on, which is exactly what a user rotating off the seed types
        for bad in ["changeme1234", "MyPassword99", "Odin-Admin-01", "letmein12345"]:
            self.assertIsNotNone(password_problem(bad), f"{bad!r} should be rejected")
        self.assertIsNone(password_problem("Correct-Horse-9"))

    def test_no_nested_forms_in_rendered_pages(self):
        """Nested <form> is invalid HTML and browsers resolve it destructively:
        the inner form is dropped and its buttons are reassigned to the outer
        one. Bulk task actions shipped with exactly this bug — every route test
        passed because they POST directly and never parse the markup — so the
        structure gets its own guard.
        """
        import html.parser

        class FormNesting(html.parser.HTMLParser):
            def __init__(self):
                super().__init__()
                self.depth = 0
                self.nested = False

            def handle_starttag(self, tag, attrs):
                if tag == "form":
                    if self.depth:
                        self.nested = True
                    self.depth += 1

            def handle_endtag(self, tag):
                if tag == "form" and self.depth:
                    self.depth -= 1

        self.new_project(name="FormStructure", client="C")
        self.client.post("/projects/1/tasks", data={"title": "t1"})
        for path in ["/projects/1", "/projects/1/edit", "/projects/new", "/board",
                     "/projects", "/my-work", "/settings", "/analytics", "/users"]:
            parser = FormNesting()
            parser.feed(self.client.get(path).data.decode())
            self.assertFalse(parser.nested, f"nested <form> in {path}")

    # ---- scale: unbounded page growth ------------------------------------

    def _bulk_projects(self, n, **cols):
        """Insert projects directly — the create route needs a file upload per
        project, which is far too slow for a volume test."""
        import datetime, secrets
        now = datetime.datetime.utcnow().isoformat()
        with self.raw_db() as db:
            uid = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()["id"]
            for i in range(n):
                db.execute(
                    "INSERT INTO projects (name, client, stage, owner_id, delivery_mode, "
                    "target_end_date, access_token, created_at, updated_at, stage_entered_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (f"Bulk {i:03d}", "C", "Kickoff", uid, "Distribution/MSSP",
                     cols.get("target_end_date"), secrets.token_urlsafe(8), now, now, now),
                )
            db.commit()

    @patch("routes.board.BANNER_NAMES", 5)
    def test_board_banner_caps_names_and_offers_a_drill_down(self):
        """Uncapped, the banner listed every alerting project: at 431 projects
        it was 2,443px — 3.4 screens — of names above the first number."""
        self._bulk_projects(12, target_end_date="2020-01-01")
        body = self.client.get("/board").data.decode()
        inline = body.count('class="alert-item"')
        self.assertLessEqual(inline, 5 * len(app_module.PERMISSIONS and ["overdue"]) + 20,
                             "banner should not list every project")
        self.assertIn("more &rarr;", body)
        self.assertIn("/alerts?type=project_overdue", body.replace("&amp;", "&"))

    def test_board_payload_does_not_grow_linearly_with_alerts(self):
        self._bulk_projects(3, target_end_date="2020-01-01")
        small = len(self.client.get("/board").data)
        self._bulk_projects(60, target_end_date="2020-01-01")
        large = len(self.client.get("/board").data)
        # kanban cards still grow; the banner must not add per-project weight
        growth_per_project = (large - small) / 60
        self.assertLess(growth_per_project, 400,
                        f"board grew {growth_per_project:.0f} bytes/project — banner likely uncapped")

    @patch("routes.board.COLUMN_CARDS", 5)
    def test_kanban_columns_cap_cards_and_link_to_the_full_stage_list(self):
        """One column held 73 cards and stood 7,407px tall at 431 projects.
        The header count must still show the true total, so capping the render
        cannot be mistaken for losing projects."""
        self._bulk_projects(12)          # all land in Kickoff
        body = self.client.get("/board").data.decode()
        cards_block = body.split('<div class="cards">')[1].split("</div>\n    </div>")[0]
        self.assertLessEqual(cards_block.count('class="card"'), 5)
        self.assertIn("more in", body)
        self.assertIn("/projects?stage=Kickoff", body.replace("&amp;", "&").replace("+", " ").replace(" ", "+"))
        # the true count stays visible in the column header
        self.assertIn(">12</span>", body)
        # drag-and-drop survives the cap
        self.assertIn("ondrop=", body)

    @patch("routes.board.ALERTS_PER_PAGE", 10)
    def test_alerts_log_paginates_and_filters_by_type(self):
        self._bulk_projects(25, target_end_date="2020-01-01")
        self.client.get("/board")   # sync alerts
        body = self.client.get("/alerts").data.decode()
        self.assertIn("Page 1 of", body)
        self.assertLessEqual(body.count("<tr>"), 12, "page should be capped")

        filtered = self.client.get("/alerts?type=project_overdue").data.decode()
        self.assertIn("Project overdue", filtered)
        self.assertNotIn("Project inactive</td>", filtered)

        # an unknown type must be ignored, not injected
        self.assertEqual(self.client.get("/alerts?type=bogus%27--").status_code, 200)
        for bad in ["?page=99999", "?page=-3", "?page=abc"]:
            self.assertEqual(self.client.get("/alerts" + bad).status_code, 200, bad)

    # ---- accessibility regressions ---------------------------------------

    def test_every_form_control_has_an_accessible_name(self):
        """A control with no programmatic label is announced as an unnamed edit
        field. The app wrote `<label>Text</label>` next to inputs without a for
        or wrapper, so el.labels was empty on every form including login."""
        import re as _re
        from html.parser import HTMLParser

        class Names(HTMLParser):
            def __init__(self, for_ids):
                super().__init__()
                self.for_ids, self.in_label, self.unnamed = for_ids, False, []
            def handle_starttag(self, tag, attrs):
                d = dict(attrs)
                if tag == "label":
                    self.in_label = True
                if tag in ("input", "select", "textarea"):
                    if d.get("type") in ("hidden", "submit", "button"):
                        return
                    named = ("aria-label" in d or "aria-labelledby" in d or self.in_label
                             or d.get("id") in self.for_ids)
                    if not named:
                        self.unnamed.append(f'{tag}[{d.get("name", "?")}]')
            def handle_endtag(self, tag):
                if tag == "label":
                    self.in_label = False

        self.new_project(name="A11y", client="C")
        self.client.post("/projects/1/tasks", data={"title": "t"})
        for path in ["/login", "/board", "/my-work", "/projects", "/projects/1",
                     "/projects/1/edit", "/projects/new", "/analytics", "/alerts",
                     "/settings", "/settings/rbac", "/settings/contacts",
                     "/audit-logs", "/users", "/account"]:
            body = self.client.get(path).data.decode()
            parser = Names(set(_re.findall(r'<label[^>]*\bfor="([^"]+)"', body)))
            parser.feed(body)
            self.assertEqual(parser.unnamed, [], f"unnamed controls on {path}")

    def test_heading_levels_never_skip(self):
        """h1 -> h3 leaves a gap that screen-reader heading navigation exposes."""
        import re as _re
        self.new_project(name="A11y", client="C")
        for path in ["/board", "/my-work", "/projects/1", "/analytics", "/settings",
                     "/settings/contacts", "/users", "/account"]:
            levels = [int(h) for h in _re.findall(r"<h([1-6])\b", self.client.get(path).data.decode())]
            gaps = [(levels[i], levels[i + 1]) for i in range(len(levels) - 1)
                    if levels[i + 1] - levels[i] > 1]
            self.assertEqual(gaps, [], f"heading level skipped on {path}: {gaps}")

    def test_no_navigation_depends_on_a_mouse_click(self):
        """Row-level onclick is unreachable by keyboard; rows must carry a real
        anchor instead."""
        self.new_project(name="A11y", client="C")
        for path in ["/board", "/projects", "/my-work"]:
            html = self.client.get(path).data.decode()
            self.assertNotIn("<tr onclick", html, f"onclick-only row on {path}")

    # ---- audit fixes: roles, sessions, evidence, operations ----------------

    def _make_user(self, username, role, password=STRONG_PASSWORD):
        self.client.post("/users", data={"username": username, "name": username, "password": password, "role": role})
        with self.raw_db() as db:
            return db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]

    def test_contributor_creates_and_comments_but_never_moves_a_stage(self):
        self._make_user("sales", "Contributor")
        c = app_module.app.test_client(); c.post("/login", data={"username": "sales", "password": STRONG_PASSWORD})
        c.post("/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 x"), "po.pdf"), "name": "S", "client": "C"})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)
            stages = [r[0] for r in db.execute("SELECT name FROM stages ORDER BY position")]
        self.assertEqual(c.post("/projects/1/note", data={"note": "hi"}).status_code, 302)
        self.assertEqual(c.post("/projects/1/stage", data={"stage": stages[-1]}).status_code, 403)
        self.assertEqual(c.post("/projects/1/delete").status_code, 403)

    def test_admin_cannot_strip_its_own_view_rights(self):
        self.client.post("/settings/rbac", data={"manage_settings::Admin": "on"})   # everything else unticked
        self.assertEqual(self.client.get("/projects").status_code, 200)
        self.assertEqual(self.client.get("/board").status_code, 200)

    def test_deactivating_a_user_ends_their_live_session(self):
        uid = self._make_user("temp", "Member")
        c = app_module.app.test_client(); c.post("/login", data={"username": "temp", "password": STRONG_PASSWORD})
        self.assertEqual(c.get("/board").status_code, 200)
        self.client.post(f"/users/{uid}/active", data={"active": "0"})
        self.assertEqual(c.get("/board").status_code, 302)                # dead, not just next-login-dead

    def test_session_has_an_absolute_lifetime(self):
        with self.client.session_transaction() as sess:
            sess["login_at"] = "2020-01-01T00:00:00"
        resp = self.client.get("/board")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_users_page_and_export_carry_access_review_evidence(self):
        self._make_user("newbie", "Viewer")
        page = self.client.get("/users").data.decode()
        self.assertIn("Last login", page); self.assertIn("Created", page)
        resp = self.client.get("/users/export.csv")
        self.assertEqual(resp.status_code, 200)
        body = resp.data.decode()
        self.assertIn("last_login_at", body.splitlines()[0])
        self.assertIn("newbie", body)
        with self.raw_db() as db:
            self.assertIsNotNone(db.execute("SELECT last_login_at FROM users WHERE username='admin'").fetchone()[0])
            self.assertIsNotNone(db.execute("SELECT created_at FROM users WHERE username='newbie'").fetchone()[0])

    def test_local_backup_is_written_even_without_onedrive(self):
        import backup
        self.new_project(name="B", client="C")
        with patch.object(db_module, "DATA_DIR", tempfile.mkdtemp()), patch("backup.graph.onedrive_configured", return_value=False):
            ok, message = backup.run_backup()
            self.assertTrue(ok, message)
            written = [f for f in os.listdir(os.path.join(db_module.DATA_DIR, "backups")) if f.endswith(".zip")]
        self.assertEqual(len(written), 1)
        self.assertIn("OneDrive not configured", message)

    def test_healthz_and_robots(self):
        anon = app_module.app.test_client()
        self.assertEqual(anon.get("/healthz").data, b"ok")
        self.assertIn(b"Disallow: /", anon.get("/robots.txt").data)

    def test_error_pages_are_branded(self):
        resp = self.client.get("/no-such-page")
        self.assertEqual(resp.status_code, 404)
        self.assertIn(b"Page not found", resp.data)
        self.assertIn(b"style.css", resp.data)
        anon = app_module.app.test_client()
        self.assertIn(b"Sign in", anon.get("/nope").data)

    def test_long_inputs_are_capped_server_side(self):
        self.new_project(name="N" * 5000, client="C")
        self.client.post("/projects/1/note", data={"note": "x" * 20000})
        with self.raw_db() as db:
            self.assertEqual(len(db.execute("SELECT name FROM projects WHERE id=1").fetchone()[0]), 200)
            self.assertEqual(db.execute("SELECT MAX(LENGTH(note)) FROM status_notes").fetchone()[0], 5000)

    def test_fresh_install_stages_are_a_delivery_lifecycle(self):
        with self.raw_db() as db:
            names = [r[0] for r in db.execute("SELECT name FROM stages ORDER BY position")]
        for commercial in ("Invoiced", "Payment Pending"):
            self.assertNotIn(commercial, names)
        self.assertEqual(names[-1], "Closed")

    def test_database_runs_in_wal_mode(self):
        with self.raw_db() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_mobile_nav_has_a_toggle(self):
        page = self.client.get("/board").data.decode()
        self.assertIn('id="nav-toggle"', page)
        self.assertIn('class="nav-burger"', page)

    def test_migration_flags_an_existing_seed_admin_and_backfills_customer_tokens(self):
        """Fresh test databases never exercise the upgrade path: the admin row
        does not exist yet when migrate_db runs. A real install does, and the
        first version of this migration crashed on it."""
        self.new_project(name="Old", client="C")
        with self.raw_db() as db:
            db.execute("UPDATE users SET must_change_password = 0")
            db.execute("UPDATE projects SET customer_token = NULL")
            db.execute("ALTER TABLE users DROP COLUMN must_change_password")
            db.commit()
        app_module.init_db()          # upgrade path, admin row present
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT must_change_password FROM users WHERE username='admin'").fetchone()[0], 1)
            self.assertIsNotNone(db.execute("SELECT customer_token FROM projects WHERE id=1").fetchone()[0])

    # ---- audit fixes: perimeter, guest links, evidence trail -------------

    def _flag_admin(self):
        with self.raw_db() as db:
            db.execute("UPDATE users SET must_change_password = 1 WHERE username='admin'"); db.commit()

    def test_seed_admin_is_forced_to_change_password_before_anything_else(self):
        self._flag_admin()
        c = app_module.app.test_client()
        c.post("/login", data={"username": "admin", "password": "changeme"})
        resp = c.get("/board")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/account", resp.headers["Location"])
        self.assertEqual(c.get("/account").status_code, 200)            # the one page allowed
        c.post("/account", data={"current_password": "changeme", "new_password": STRONG_PASSWORD})
        self.assertEqual(c.get("/board").status_code, 200)              # gate lifted

    def test_admin_password_reset_forces_change_at_next_login(self):
        self.client.post("/users", data={"username": "u2", "name": "U", "password": STRONG_PASSWORD, "role": "Member"})
        with self.raw_db() as db:
            uid = db.execute("SELECT id FROM users WHERE username='u2'").fetchone()["id"]
        self.client.post(f"/users/{uid}/reset-password", data={"new_password": "Reset-By-Admin-2026"})
        c = app_module.app.test_client()
        c.post("/login", data={"username": "u2", "password": "Reset-By-Admin-2026"})
        self.assertIn("/account", c.get("/board").headers.get("Location", ""))

    def test_vendor_link_advances_exactly_one_stage_and_never_closes(self):
        from unittest.mock import patch as _patch
        self.new_project(name="V", client="C", delivery_mode="Outsourced", outsourcer_name="VendorCo")
        with self.raw_db() as db:
            tok = db.execute("SELECT access_token FROM projects WHERE id=1").fetchone()[0]
            stages = [r[0] for r in db.execute("SELECT name FROM stages ORDER BY position")]
        g = app_module.app.test_client()
        page = g.get(f"/guest/{tok}").data.decode()
        self.assertIn(f"Advance to {stages[1]}", page)
        self.assertNotIn("Closed", page.split("Update Progress")[1].split("</form>")[0])
        csrf = re.search(r'name="_csrf" value="([^"]+)"', page).group(1)
        with _patch("routes.guest.notify_event") as notify:
            g.post(f"/guest/{tok}/stage", data={"stage": stages[-1], "author": "Sam", "_csrf": csrf})
            with self.raw_db() as db:
                self.assertEqual(db.execute("SELECT stage FROM projects WHERE id=1").fetchone()[0], stages[0])
            g.post(f"/guest/{tok}/stage", data={"stage": stages[2], "author": "Sam", "_csrf": csrf})   # skipping
            with self.raw_db() as db:
                self.assertEqual(db.execute("SELECT stage FROM projects WHERE id=1").fetchone()[0], stages[0])
            g.post(f"/guest/{tok}/stage", data={"stage": stages[1], "author": "Sam", "_csrf": csrf})
            with self.raw_db() as db:
                self.assertEqual(db.execute("SELECT stage FROM projects WHERE id=1").fetchone()[0], stages[1])
                row = db.execute("SELECT username, details FROM audit_logs WHERE action='guest_stage_change'").fetchone()
            self.assertEqual(row["username"], "guest:vendor")
            self.assertIn("Sam · VendorCo", row["details"])
            self.assertTrue(notify.called)                               # owner hears about it

    def test_customer_link_is_view_and_comment_only(self):
        self.new_project(name="V", client="Acme", delivery_mode="Outsourced", outsourcer_name="VendorCo", po_number="PO-77")
        with self.raw_db() as db:
            vendor, customer = db.execute("SELECT access_token, customer_token FROM projects WHERE id=1").fetchone()
        g = app_module.app.test_client()
        page = g.get(f"/guest/{customer}").data.decode()
        self.assertNotIn("Advance to", page)
        self.assertIn("PO-77", page)                                     # the customer's own PO
        self.assertNotIn("PO-77", g.get(f"/guest/{vendor}").data.decode())   # not the vendor's business
        csrf = re.search(r'name="_csrf" value="([^"]+)"', page).group(1)
        with self.raw_db() as db:
            first = db.execute("SELECT stage FROM projects WHERE id=1").fetchone()[0]
        self.assertEqual(g.post(f"/guest/{customer}/stage", data={"stage": "x", "author": "Ann", "_csrf": csrf}).status_code, 403)
        g.post(f"/guest/{customer}/note", data={"note": "looks good", "author": "Ann", "_csrf": csrf})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT stage FROM projects WHERE id=1").fetchone()[0], first)
            self.assertEqual(db.execute("SELECT author FROM status_notes ORDER BY id DESC LIMIT 1").fetchone()[0], "Ann · Acme")
        # rotation kills both links
        self.client.post("/projects/1/rotate-token")
        self.assertEqual(g.get(f"/guest/{customer}").status_code, 404)
        self.assertEqual(g.get(f"/guest/{vendor}").status_code, 404)

    def test_guest_writes_require_a_name_and_are_throttled(self):
        self.new_project(name="V", client="C", delivery_mode="Outsourced", outsourcer_name="VendorCo")
        with self.raw_db() as db:
            tok = db.execute("SELECT customer_token FROM projects WHERE id=1").fetchone()[0]
        g = app_module.app.test_client()
        csrf = re.search(r'name="_csrf" value="([^"]+)"', g.get(f"/guest/{tok}").data.decode()).group(1)
        g.post(f"/guest/{tok}/note", data={"note": "anon", "_csrf": csrf})   # no author
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM status_notes WHERE note='anon'").fetchone()[0], 0)
        codes = [g.post(f"/guest/{tok}/note", data={"note": f"n{i}", "author": "A", "_csrf": csrf}).status_code for i in range(12)]
        self.assertIn(429, codes)
        self.assertEqual(codes[0], 302)

    def test_upload_contents_must_match_the_extension(self):
        self.new_project(name="U", client="C")
        for name, body, stored in [("real.pdf", b"%PDF-1.4 ok", True), ("fake.pdf", b"<html><script>", False),
                                   ("sheet.xlsx", b"PK\x03\x04", True), ("notes.txt", b"anything", True)]:
            self.client.post("/projects/1/documents", data={"category": "Deliverable", "file": (io.BytesIO(body), name)},
                             content_type="multipart/form-data")
            with self.raw_db() as db:
                n = db.execute("SELECT COUNT(*) FROM documents WHERE filename=?", (name,)).fetchone()[0]
            self.assertEqual(n == 1, stored, name)

    def test_auth_and_data_access_events_reach_the_audit_trail(self):
        c = app_module.app.test_client()
        c.post("/login", data={"username": "admin", "password": "nope"})
        c.post("/login", data={"username": "admin", "password": "changeme"})
        self.new_project(name="D", client="C")
        self.client.post("/projects/1/documents", data={"category": "Deliverable", "file": (io.BytesIO(b"%PDF-1.4 x"), "d.pdf")},
                         content_type="multipart/form-data")
        with self.raw_db() as db:
            doc = db.execute("SELECT id FROM documents WHERE project_id=1").fetchone()["id"]
        self.client.get(f"/projects/1/documents/{doc}/download")
        c.get("/logout")
        with self.raw_db() as db:
            actions = {r[0] for r in db.execute("SELECT action FROM audit_logs")}
        for a in ("login_failure", "login_success", "download_document", "upload_document", "logout", "create_project"):
            self.assertIn(a, actions)

    def test_audit_log_is_append_only(self):
        self.new_project(name="A", client="C")
        with self.raw_db() as db:
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("DELETE FROM audit_logs")
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("UPDATE audit_logs SET username='x'")

    def test_audit_log_exports_csv_with_filters(self):
        self.new_project(name="A", client="C")
        resp = self.client.get("/audit-logs/export.csv?action=create_project")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp.headers["Content-Disposition"])
        body = resp.data.decode()
        self.assertIn("create_project", body)
        self.assertNotIn("login_success", body)

    def test_every_state_changing_route_writes_to_the_audit_trail(self):
        """Meta-guard, like the RBAC one: a POST route with no audit_log call
        is a gap an auditor will find before we do."""
        import inspect
        missing = []
        for rule in app_module.app.url_map.iter_rules():
            if "POST" not in rule.methods or rule.endpoint == "static":
                continue
            src = inspect.getsource(app_module.app.view_functions[rule.endpoint])
            if "audit_log(" not in src:
                missing.append(rule.rule)
        self.assertEqual(missing, [], f"POST routes without an audit entry: {missing}")

    def test_nginx_passes_cloudflares_client_ip_and_hides_server(self):
        conf = open(os.path.join(os.path.dirname(app_module.__file__), "deploy", "nginx.conf")).read()
        self.assertIn("$http_cf_connecting_ip", conf)
        self.assertIn("proxy_set_header X-Forwarded-For   $client_ip", conf)
        self.assertIn("server_tokens off", conf)
        self.assertIn("proxy_hide_header Server", conf)

    def test_login_failure_records_the_calling_address(self):
        c = app_module.app.test_client()
        c.post("/login", data={"username": "admin", "password": "nope"}, environ_base={"REMOTE_ADDR": "203.0.113.77"})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT ip_address FROM audit_logs WHERE action='login_failure'").fetchone()[0], "203.0.113.77")

    # ---- review fixes: guards, races and data-integrity -------------------

    def _soft_delete(self, project_id):
        with self.raw_db() as db:
            db.execute("UPDATE projects SET deleted_at='2026-01-01T00:00:00' WHERE id=?", (project_id,))
            db.commit()

    def test_writes_to_a_deleted_project_404_instead_of_corrupting_it(self):
        """A stale tab must not be able to mutate a project someone else just
        deleted. project_stage previously updated the deleted row and wrote an
        orphan status note before crashing on its own follow-up lookup."""
        self.new_project(name="Doomed", client="C")
        with self.raw_db() as db:
            before = db.execute("SELECT stage, stage_entered_at FROM projects WHERE id=1").fetchone()
            notes_before = db.execute("SELECT COUNT(*) AS c FROM status_notes WHERE project_id=1").fetchone()["c"]
        self._soft_delete(1)

        for path, data in [("/projects/1/stage", {"stage": "Kickoff", "note": "x"}),
                           ("/projects/1/note", {"note": "y"}),
                           ("/projects/1/tasks", {"title": "z"})]:
            self.assertEqual(self.client.post(path, data=data).status_code, 404, path)

        with self.raw_db() as db:
            after = db.execute("SELECT stage, stage_entered_at FROM projects WHERE id=1").fetchone()
            notes_after = db.execute("SELECT COUNT(*) AS c FROM status_notes WHERE project_id=1").fetchone()["c"]
        self.assertEqual(after["stage"], before["stage"])                    # untouched
        self.assertEqual(after["stage_entered_at"], before["stage_entered_at"])
        self.assertEqual(notes_after, notes_before)                          # no orphan note

    def test_upload_to_a_deleted_project_is_refused(self):
        self.new_project(name="Doomed", client="C")
        self._soft_delete(1)
        resp = self.client.post(
            "/projects/1/documents",
            data={"category": "Deliverable", "file": (io.BytesIO(b"%PDF-1.4 ghost"), "ghost.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 404)
        with self.raw_db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) AS c FROM documents WHERE filename='ghost.pdf'").fetchone()["c"], 0)

    def test_deleting_twice_does_not_restart_the_undo_window(self):
        self.new_project(name="Doomed", client="C")
        self.client.post("/projects/1/delete")
        with self.raw_db() as db:
            first = db.execute("SELECT deleted_at FROM projects WHERE id=1").fetchone()[0]
        self.assertEqual(self.client.post("/projects/1/delete").status_code, 404)
        with self.raw_db() as db:
            second = db.execute("SELECT deleted_at FROM projects WHERE id=1").fetchone()[0]
            audits = db.execute(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE action='delete_project' AND resource_id=1"
            ).fetchone()["c"]
        self.assertEqual(first, second)   # undo window not re-stamped
        self.assertEqual(audits, 1)       # one action, one audit entry

    def test_only_one_open_alert_per_project_and_type(self):
        """Concurrent board loads used to insert duplicate alerts, which also
        meant duplicate notification emails."""
        from services.alerts import create_alert
        self.new_project(name="P", client="C")
        with app_module.app.test_request_context():
            with self.client.session_transaction():
                pass
        with app_module.app.app_context():
            first = create_alert("stale", 1, "Project inactive", severity="warning")
            second = create_alert("stale", 1, "Project inactive", severity="warning")
        self.assertTrue(first)     # inserted
        self.assertFalse(second)   # race loser inserts nothing -> no second email
        with self.raw_db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) AS c FROM alerts WHERE alert_type='stale' AND project_id=1 AND resolved=0"
            ).fetchone()["c"], 1)

    def test_adding_a_stage_does_not_reopen_closed_projects(self):
        """The last stage is terminal everywhere. Appending a new stage would
        hand that role over and put every closed project back on the board."""
        with self.raw_db() as db:
            terminal_before = db.execute("SELECT name FROM stages ORDER BY position DESC LIMIT 1").fetchone()["name"]
        self.new_project(name="Finished", client="C")
        self.client.post("/projects/1/stage", data={"stage": terminal_before, "note": "done"})
        self.assertNotIn(b"Finished", self.client.get("/projects").data)   # closed = hidden

        self.client.post("/settings/stages/add", data={"name": "Post-Mortem"})
        with self.raw_db() as db:
            terminal_after = db.execute("SELECT name FROM stages ORDER BY position DESC LIMIT 1").fetchone()["name"]
        self.assertEqual(terminal_after, terminal_before)                  # still the closed stage
        self.assertNotIn(b"Finished", self.client.get("/projects").data)   # still closed

    def test_refresh_without_a_rotated_token_keeps_the_stored_one(self):
        """Microsoft may return an access token with no new refresh_token. The
        old UPSERT wrote NULL over the stored one, silently killing M365."""
        import graph
        graph.DB_PATH = db_module.DB_PATH
        graph._save_tokens({"access_token": "a1", "refresh_token": "r1", "expires_in": 3600})
        graph._save_tokens({"access_token": "a2", "expires_in": 3600})   # no refresh_token
        with self.raw_db() as db:
            row = db.execute("SELECT access_token, refresh_token FROM ms_connection WHERE id=1").fetchone()
        self.assertEqual(row["access_token"], "a2")   # access token still rotates
        self.assertEqual(row["refresh_token"], "r1")  # refresh token preserved
        self.assertTrue(graph.is_connected())

    def test_purging_a_project_removes_its_children_and_files(self):
        """Purging used to delete only the projects row, leaving notes and tasks
        pointing at a dead id (PRAGMA foreign_key_check flagged them) and every
        uploaded file on disk — where it still got swept into each backup."""
        import os
        self.new_project(name="Doomed", client="C")
        self.client.post("/projects/1/tasks", data={"title": "t"})
        self.client.post("/projects/1/note", data={"note": "n"})
        self.client.post(
            "/projects/1/documents",
            data={"category": "Deliverable", "file": (io.BytesIO(b"%PDF-1.4 bytes"), "d.pdf")},
            content_type="multipart/form-data",
        )
        with self.raw_db() as db:
            stored = db.execute("SELECT project_id, stored_name FROM documents").fetchone()
        # routes/projects.py did `from db import UPLOAD_DIR`, so it holds the
        # value bound at import time — reassigning db_module.UPLOAD_DIR in setUp
        # never reached it. Read the binding the route actually writes through.
        upload_dir = db_module.UPLOAD_DIR   # isolated in setUp; never the real folder
        path = os.path.join(upload_dir, str(stored["project_id"]), stored["stored_name"])
        self.assertTrue(os.path.exists(path), f"upload not found at {path}")

        # delete and push it past the undo window, then purge
        self.client.post("/projects/1/delete")
        with self.raw_db() as db:
            db.execute("UPDATE projects SET deleted_at='2020-01-01T00:00:00' WHERE id=1")
            db.execute("UPDATE documents SET deleted_at='2020-01-01T00:00:00' WHERE project_id=1")
            db.commit()
            db_module.cleanup_soft_deletes(db)

        with self.raw_db() as db:
            for table in ("projects", "status_notes", "tasks", "documents", "alerts"):
                where = "id=1" if table == "projects" else "project_id=1"
                self.assertEqual(
                    db.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {where}").fetchone()["c"], 0,
                    f"{table} rows survived the purge")
            self.assertEqual(db.execute("SELECT COUNT(*) AS c FROM pragma_foreign_key_check").fetchone()["c"], 0)
        self.assertFalse(os.path.exists(path), "uploaded file survived the purge")

    # ---- duplicate / global search / bulk tasks --------------------------

    def test_duplicate_prefills_the_create_form_without_a_second_write_path(self):
        """Duplicate reuses project_new, so the PO-required rule still holds for
        the copy and there's no parallel create path that can drift."""
        self.new_project(name="Original", client="Acme", target_end_date="2027-03-01")
        form = self.client.get("/projects/1?").data  # ensure it exists
        page = self.client.get("/projects/new?from=1").data
        self.assertIn(b"Duplicate Project", page)
        self.assertIn(b"Original (copy)", page)   # name nudged, not silently identical
        self.assertIn(b"Acme", page)
        self.assertIn(b"po_document", page)       # PO still required on the copy
        self.assertNotIn(b"Save Changes", page)   # it creates, it doesn't update

    def test_duplicate_of_missing_project_falls_back_to_a_blank_form(self):
        page = self.client.get("/projects/new?from=9999").data
        self.assertIn(b"New Project", page)
        self.assertNotIn(b"Duplicate Project", page)

    def test_global_nav_search_targets_the_project_list(self):
        self.new_project(name="Findable", client="C")
        nav = self.client.get("/board").data
        self.assertIn(b'class="nav-search"', nav)
        self.assertIn(b'name="q"', nav)
        # and the target actually filters
        self.assertIn(b"Findable", self.client.get("/projects?q=Findable").data)

    def test_bulk_complete_and_delete_only_touch_this_projects_tasks(self):
        self.new_project(name="A", client="C")
        self.new_project(name="B", client="C")
        self.client.post("/projects/1/tasks", data={"title": "a1"})
        self.client.post("/projects/1/tasks", data={"title": "a2"})
        self.client.post("/projects/2/tasks", data={"title": "b1"})
        with self.raw_db() as db:
            ids = {r["title"]: r["id"] for r in db.execute("SELECT id,title FROM tasks")}

        # a doctored form naming another project's task must not reach it
        self.client.post("/projects/1/tasks/bulk", data={
            "action": "complete", "task_ids": [str(ids["a1"]), str(ids["b1"])]})
        with self.raw_db() as db:
            rows = {r["title"]: r["done"] for r in db.execute("SELECT title,done FROM tasks")}
        self.assertEqual(rows["a1"], 1)
        self.assertEqual(rows["b1"], 0)   # other project's task untouched

        self.client.post("/projects/1/tasks/bulk", data={"action": "reopen", "task_ids": [str(ids["a1"])]})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT done FROM tasks WHERE id=?", (ids["a1"],)).fetchone()[0], 0)

        self.client.post("/projects/1/tasks/bulk", data={
            "action": "delete", "task_ids": [str(ids["a1"]), str(ids["a2"])]})
        with self.raw_db() as db:
            left = [r["title"] for r in db.execute("SELECT title FROM tasks")]
        self.assertEqual(left, ["b1"])

    def test_bulk_rejects_bad_action_and_non_numeric_ids(self):
        self.new_project(name="A", client="C")
        self.client.post("/projects/1/tasks", data={"title": "t"})
        self.assertEqual(self.client.post("/projects/1/tasks/bulk",
                         data={"action": "drop-table", "task_ids": ["1"]}).status_code, 400)
        self.assertEqual(self.client.post("/projects/1/tasks/bulk",
                         data={"action": "delete", "task_ids": ["1; DROP TABLE tasks"]}).status_code, 400)
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"], 1)

    def test_sla_from_measured_only_sets_stages_with_evidence(self):
        self.new_project(name="Measured", client="C")
        # give PO Received a real completed visit by moving the project on
        self.client.post("/projects/1/stage", data={"stage": "Kickoff", "note": "moved"})
        self.client.post("/settings/stages/sla/from-measured")
        with self.raw_db() as db:
            rows = {r["name"]: r["sla_days"] for r in db.execute("SELECT name, sla_days FROM stages")}
        self.assertIsNotNone(rows["PO Received"])     # has a completed visit
        self.assertGreaterEqual(rows["PO Received"], 1)   # never rounds down to zero
        self.assertIsNone(rows["Kickoff"])           # nothing has left Kickoff yet
        self.assertIsNone(rows["Closed"])            # terminal stage is never given an SLA

    # ---- stage SLAs ------------------------------------------------------

    def test_stage_sla_state_flags_only_real_breaches(self):
        from services.analytics import stage_sla_state
        from datetime import datetime
        now = datetime(2026, 1, 20)
        base = {"stage": "Kickoff", "stage_entered_at": "2026-01-01T00:00:00"}

        breached = stage_sla_state(base, {"Kickoff": 7}, "Closed", now=now)
        self.assertTrue(breached["breached"])
        self.assertAlmostEqual(breached["days"], 19.0, places=3)
        self.assertAlmostEqual(breached["over_by"], 12.0, places=3)

        within = stage_sla_state(base, {"Kickoff": 30}, "Closed", now=now)
        self.assertFalse(within["breached"])

        # no SLA on the stage -> not measured at all
        self.assertIsNone(stage_sla_state(base, {}, "Closed", now=now))
        # finished work isn't "stuck", even if it sat there a long time
        done = {"stage": "Closed", "stage_entered_at": "2026-01-01T00:00:00"}
        self.assertIsNone(stage_sla_state(done, {"Closed": 1}, "Closed", now=now))
        # unknown entry time -> no guessing
        unknown = {"stage": "Kickoff", "stage_entered_at": None}
        self.assertIsNone(stage_sla_state(unknown, {"Kickoff": 7}, "Closed", now=now))

    def test_stage_change_stamps_stage_entered_at(self):
        self.new_project(name="P", client="C")
        with self.raw_db() as db:
            before = db.execute("SELECT stage_entered_at FROM projects WHERE id=1").fetchone()[0]
        self.assertIsNotNone(before)     # set at creation
        self.client.post("/projects/1/stage", data={"stage": "Kickoff", "note": "go"})
        with self.raw_db() as db:
            after = db.execute("SELECT stage, stage_entered_at FROM projects WHERE id=1").fetchone()
        self.assertEqual(after["stage"], "Kickoff")
        self.assertGreater(after["stage_entered_at"], before)

    def test_editing_a_project_does_not_restart_the_sla_clock(self):
        """updated_at is bumped by any edit — that's exactly why the SLA clock
        needs its own column rather than reusing it."""
        self.new_project(name="P", client="C")
        with self.raw_db() as db:
            entered = db.execute("SELECT stage_entered_at FROM projects WHERE id=1").fetchone()[0]
        self.client.post("/projects/1/edit", data={
            "name": "P renamed", "client": "C", "via": "Direct", "delivery_mode": "Distribution/MSSP"})
        with self.raw_db() as db:
            row = db.execute("SELECT stage_entered_at, updated_at FROM projects WHERE id=1").fetchone()
        self.assertEqual(row["stage_entered_at"], entered)     # SLA clock untouched
        self.assertGreaterEqual(row["updated_at"], entered)    # but the row was touched

    def test_backfill_derives_stage_entry_from_note_history(self):
        """Existing installs have no stage_entered_at. The migration reconstructs
        it, including the case where the only note repeats the current stage —
        that project never left its first stage, so entry is its creation."""
        self.new_project(name="Backfilled", client="C")
        with self.raw_db() as db:
            first_stage = db.execute("SELECT name FROM stages ORDER BY position LIMIT 1").fetchone()["name"]
            db.execute("UPDATE projects SET created_at='2026-01-01T00:00:00', stage_entered_at=NULL WHERE id=1")
            db.execute(
                "INSERT INTO status_notes (project_id,author,note,stage,created_at) VALUES (1,'x','n',?,?)",
                (first_stage, "2026-01-20T00:00:00"),
            )
            db.commit()
        with self.raw_db() as db:
            app_module.migrate_db(db); db.commit()
            got = db.execute("SELECT stage_entered_at FROM projects WHERE id=1").fetchone()[0]
        # a plain note in the same stage is not a re-entry
        self.assertEqual(got, "2026-01-01T00:00:00")

    def test_sla_breach_raises_an_alert_and_clears_when_stage_moves(self):
        self.new_project(name="Stuck", client="C")
        with self.raw_db() as db:
            db.execute("UPDATE stages SET sla_days=1 WHERE name='Kickoff'")
            db.execute("UPDATE projects SET stage='Kickoff', stage_entered_at='2026-01-01T00:00:00' WHERE id=1")
            db.commit()
        board = self.client.get("/board").data
        self.assertIn(b"over their stage SLA", board)
        self.assertIn(b"Stuck", board)
        with self.raw_db() as db:
            self.assertIsNotNone(db.execute(
                "SELECT 1 FROM alerts WHERE alert_type='stage_sla_breach' AND resolved=0").fetchone())
        # moving stage resets the clock, so the breach clears
        self.client.post("/projects/1/stage", data={"stage": "Deployment", "note": "moved"})
        self.assertNotIn(b"over their stage SLA", self.client.get("/board").data)

    def test_settings_sla_saves_and_blank_clears(self):
        with self.raw_db() as db:
            sid = db.execute("SELECT id FROM stages WHERE name='Kickoff'").fetchone()["id"]
        self.client.post("/settings/stages/sla", data={f"sla::{sid}": "5"})
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT sla_days FROM stages WHERE id=?", (sid,)).fetchone()[0], 5)
        self.client.post("/settings/stages/sla", data={f"sla::{sid}": ""})
        with self.raw_db() as db:
            self.assertIsNone(db.execute("SELECT sla_days FROM stages WHERE id=?", (sid,)).fetchone()[0])

    def test_settings_sla_rejects_junk_and_zero(self):
        with self.raw_db() as db:
            sid = db.execute("SELECT id FROM stages WHERE name='Kickoff'").fetchone()["id"]
            db.execute("UPDATE stages SET sla_days=9 WHERE id=?", (sid,)); db.commit()
        for bad in ["abc", "0", "-3"]:
            self.client.post("/settings/stages/sla", data={f"sla::{sid}": bad})
            with self.raw_db() as db:
                self.assertEqual(db.execute("SELECT sla_days FROM stages WHERE id=?", (sid,)).fetchone()[0], 9,
                                 f"{bad!r} should have been rejected")

    # ---- cycle-time analytics -------------------------------------------

    def _cycle(self, project, notes, stages=None, terminal=None, now=None):
        from services.analytics import build_cycle_times
        from datetime import datetime
        stages = stages or ["A", "B", "C"]
        return build_cycle_times(
            [project], {project["id"]: notes}, stages, terminal or stages[-1],
            now=now or datetime(2026, 1, 31),
        )

    def test_cycle_time_uses_created_at_as_the_first_stage_entry(self):
        """Creating a project writes no note, so the opening stage has no row
        to derive its start from — it has to come from the project itself."""
        from datetime import datetime
        project = {"id": 1, "name": "P", "stage": "B", "created_at": "2026-01-01T00:00:00",
                   "updated_at": "2026-01-11T00:00:00"}
        notes = [{"stage": "B", "created_at": "2026-01-11T00:00:00"}]
        stats = self._cycle(project, notes, now=datetime(2026, 1, 21))
        by_stage = {s["stage"]: s for s in stats["stages"]}
        self.assertEqual(by_stage["A"]["visits"], 1)
        self.assertAlmostEqual(by_stage["A"]["avg_days"], 10.0, places=3)  # created -> first note
        self.assertEqual(by_stage["B"]["visits"], 0)      # still in B, not a finished visit
        self.assertEqual(by_stage["B"]["in_stage_now"], 1)
        self.assertAlmostEqual(stats["aging"][0]["days"], 10.0, places=3)

    def test_cycle_time_collapses_repeat_notes_in_the_same_stage(self):
        """Plain status notes carry the current stage. Three notes while sitting
        in one stage is one visit, not three."""
        project = {"id": 1, "name": "P", "stage": "A", "created_at": "2026-01-01T00:00:00",
                   "updated_at": "2026-01-05T00:00:00"}
        notes = [{"stage": "A", "created_at": f"2026-01-0{d}T00:00:00"} for d in (2, 3, 4)]
        stats = self._cycle(project, notes)
        by_stage = {s["stage"]: s for s in stats["stages"]}
        self.assertEqual(by_stage["A"]["visits"], 0)       # never left A
        self.assertEqual(by_stage["A"]["in_stage_now"], 1)

    def test_cycle_time_handles_project_with_no_notes_at_all(self):
        from datetime import datetime
        project = {"id": 1, "name": "P", "stage": "A", "created_at": "2026-01-01T00:00:00",
                   "updated_at": "2026-01-01T00:00:00"}
        stats = self._cycle(project, [], now=datetime(2026, 1, 6))
        self.assertAlmostEqual(stats["aging"][0]["days"], 5.0, places=3)
        self.assertIsNone(stats["lead_avg"])

    def test_cycle_time_counts_revisits_separately(self):
        """A project can move backwards. Both visits to a stage are real."""
        project = {"id": 1, "name": "P", "stage": "C", "created_at": "2026-01-01T00:00:00",
                   "updated_at": "2026-01-20T00:00:00"}
        notes = [
            {"stage": "B", "created_at": "2026-01-03T00:00:00"},   # A: 2 days
            {"stage": "A", "created_at": "2026-01-05T00:00:00"},   # B: 2 days
            {"stage": "B", "created_at": "2026-01-11T00:00:00"},   # A again: 6 days
            {"stage": "C", "created_at": "2026-01-15T00:00:00"},   # B again: 4 days
        ]
        stats = self._cycle(project, notes)
        by_stage = {s["stage"]: s for s in stats["stages"]}
        self.assertEqual(by_stage["A"]["visits"], 2)
        self.assertAlmostEqual(by_stage["A"]["avg_days"], 4.0, places=3)   # (2+6)/2
        self.assertAlmostEqual(by_stage["A"]["max_days"], 6.0, places=3)
        self.assertEqual(by_stage["B"]["visits"], 2)
        self.assertAlmostEqual(by_stage["B"]["median_days"], 3.0, places=3)  # median(2,4)

    def test_cycle_time_lead_time_only_counts_projects_that_reached_terminal(self):
        closed = {"id": 1, "name": "Done", "stage": "C", "created_at": "2026-01-01T00:00:00",
                  "updated_at": "2026-01-09T00:00:00"}
        stats = self._cycle(closed, [{"stage": "C", "created_at": "2026-01-09T00:00:00"}])
        self.assertEqual(stats["completed_count"], 1)
        self.assertAlmostEqual(stats["lead_avg"], 8.0, places=3)
        self.assertEqual(stats["throughput"], [("2026-01", 1)])
        # a project still in flight contributes no lead time
        open_p = {"id": 2, "name": "WIP", "stage": "B", "created_at": "2026-01-01T00:00:00",
                  "updated_at": "2026-01-02T00:00:00"}
        self.assertIsNone(self._cycle(open_p, [])["lead_avg"])

    def test_cycle_time_terminal_stage_is_not_reported_as_ageing(self):
        closed = {"id": 1, "name": "Done", "stage": "C", "created_at": "2026-01-01T00:00:00",
                  "updated_at": "2026-01-09T00:00:00"}
        stats = self._cycle(closed, [{"stage": "C", "created_at": "2026-01-09T00:00:00"}])
        self.assertEqual(stats["aging"], [])   # finished work isn't "stuck"

    def test_cycle_time_ignores_notes_predating_their_project(self):
        project = {"id": 1, "name": "P", "stage": "A", "created_at": "2026-01-10T00:00:00",
                   "updated_at": "2026-01-10T00:00:00"}
        stats = self._cycle(project, [{"stage": "B", "created_at": "2020-01-01T00:00:00"}])
        by_stage = {s["stage"]: s for s in stats["stages"]}
        self.assertEqual(by_stage["A"]["in_stage_now"], 1)   # corrupt row skipped, not negative
        self.assertTrue(all(s["avg_days"] is None or s["avg_days"] >= 0 for s in stats["stages"]))

    def test_analytics_page_renders_and_respects_view_reports(self):
        self.new_project(name="CycleProj", client="C")
        self.client.post("/projects/1/stage", data={"stage": "Kickoff", "note": "moved"})
        body = self.client.get("/analytics").data
        self.assertIn(b"Cycle Time", body)
        self.assertIn(b"Time In Stage", body)
        self.assertIn(b"CycleProj", body)          # ageing list picks it up
        with self.raw_db() as db:
            db.execute("UPDATE role_permissions SET allowed=0 WHERE permission='view_reports' AND role='Admin'")
            db.commit()
        self.assertEqual(self.client.get("/analytics").status_code, 403)

    def test_board_card_shows_task_progress_badge(self):
        self.new_project(name="BadgeProj", client="C")
        self.client.post("/projects/1/tasks", data={"title": "t1"})
        self.client.post("/projects/1/tasks", data={"title": "t2"})
        with self.raw_db() as db:
            tid = db.execute("SELECT id FROM tasks WHERE project_id=1 LIMIT 1").fetchone()["id"]
        self.client.post(f"/projects/1/tasks/{tid}/toggle")
        self.assertIn("1/2 tasks".encode(), self.client.get("/board").data)

    def test_viewer_sees_no_task_controls(self):
        self.new_project(name="P", client="C")
        with self.raw_db() as db:
            db.execute("INSERT INTO users (username,password_hash,name,role,active) VALUES ('vv','x','Vv','Viewer',1)")
            db.commit()
            vid = db.execute("SELECT id FROM users WHERE username='vv'").fetchone()["id"]
        vc = app_module.app.test_client()
        with vc.session_transaction() as s:
            s["user_id"] = vid
            s["user_name"] = "Vv"
            s["role"] = "Viewer"
        self.assertNotIn(b"Add Task", vc.get("/projects/1").data)

    def test_contact_list_add_and_delete(self):
        for list_key in ["account-managers", "vendors", "products", "outsourcers"]:
            self.client.post(f"/settings/contacts/{list_key}/add", data={"name": "Alice", "email": "alice@x.com"})
            resp = self.client.get("/settings/contacts")
            self.assertIn(b"Alice", resp.data)
            with self.raw_db() as db:
                row = db.execute(
                    f"SELECT id FROM {app_module.CONTACT_LISTS[list_key]['table']} WHERE name = 'Alice'"
                ).fetchone()
            self.client.post(f"/settings/contacts/{list_key}/{row['id']}/delete")
            resp = self.client.get("/settings/contacts")
            self.assertNotIn(b"Alice", resp.data)

    def test_partner_delete_cascades_account_managers(self):
        self.client.post("/settings/contacts/partners/add", data={"name": "Acme Partner"})
        with self.raw_db() as db:
            partner_id = db.execute("SELECT id FROM partners WHERE name = 'Acme Partner'").fetchone()["id"]
        self.client.post(f"/settings/contacts/partners/{partner_id}/managers/add", data={"name": "Bob", "email": "bob@x.com"})
        resp = self.client.get("/settings/contacts")
        self.assertIn(b"Bob", resp.data)

        self.client.post(f"/settings/contacts/partners/{partner_id}/delete")
        with self.raw_db() as db:
            self.assertIsNotNone(db.execute("SELECT 1 FROM partners WHERE id = ? AND deleted_at IS NOT NULL", (partner_id,)).fetchone())
            self.assertIsNotNone(db.execute("SELECT 1 FROM partner_account_managers WHERE partner_id = ? AND deleted_at IS NOT NULL", (partner_id,)).fetchone())

    def test_via_direct_stores_account_manager_snapshot(self):
        self.new_project(via="Direct", account_manager_name="Jane", account_manager_email="jane@x.com")
        with self.raw_db() as db:
            project = db.execute("SELECT * FROM projects WHERE name = 'Proj'").fetchone()
        self.assertEqual(project["via"], "Direct")
        self.assertEqual(project["account_manager_name"], "Jane")
        self.assertEqual(project["account_manager_email"], "jane@x.com")
        self.assertIsNone(project["partner_name"])

    def test_via_partner_stores_partner_snapshot(self):
        self.new_project(
            via="Partner", partner_name="Acme Partner",
            partner_account_manager_name="Bob", partner_account_manager_email="bob@x.com",
        )
        with self.raw_db() as db:
            project = db.execute("SELECT * FROM projects WHERE name = 'Proj'").fetchone()
        self.assertEqual(project["via"], "Partner")
        self.assertEqual(project["partner_name"], "Acme Partner")
        self.assertEqual(project["partner_account_manager_name"], "Bob")
        self.assertEqual(project["partner_account_manager_email"], "bob@x.com")
        self.assertIsNone(project["account_manager_name"])

    def test_delivery_mode_distribution_stores_vendor_and_product(self):
        self.new_project(delivery_mode="Distribution/MSSP", vendor_name="Vendor A", product_name="Product X")
        with self.raw_db() as db:
            project = db.execute("SELECT * FROM projects WHERE name = 'Proj'").fetchone()
        self.assertEqual(project["delivery_mode"], "Distribution/MSSP")
        self.assertEqual(project["vendor_name"], "Vendor A")
        self.assertEqual(project["product_name"], "Product X")
        self.assertIsNone(project["outsourcer_name"])

    def test_delivery_mode_outsourced_stores_outsourcer(self):
        self.new_project(delivery_mode="Outsourced", outsourcer_name="Outsource Co", outsourcer_email="out@x.com")
        with self.raw_db() as db:
            project = db.execute("SELECT * FROM projects WHERE name = 'Proj'").fetchone()
        self.assertEqual(project["delivery_mode"], "Outsourced")
        self.assertEqual(project["outsourcer_name"], "Outsource Co")
        self.assertEqual(project["outsourcer_email"], "out@x.com")
        self.assertIsNone(project["vendor_name"])

    def test_inhouse_delivery_mode_migrates_to_distribution_mssp(self):
        self.new_project(delivery_mode="Distribution/MSSP")
        with self.raw_db() as db:
            db.execute("UPDATE projects SET delivery_mode = 'In-house' WHERE name = 'Proj'")
            db.commit()
        with self.raw_db() as db:
            app_module.migrate_db(db)
            db.commit()
        with self.raw_db() as db:
            project = db.execute("SELECT delivery_mode FROM projects WHERE name = 'Proj'").fetchone()
        self.assertEqual(project["delivery_mode"], "Distribution/MSSP")

    def test_alert_sync_resolves_cleared_alerts(self):
        self.new_project()
        old = (date.today() - timedelta(days=60)).isoformat() + "T00:00:00"
        with self.raw_db() as db:
            db.execute("UPDATE projects SET updated_at = ? WHERE name = 'Proj'", (old,))
            db.commit()
        # First board load creates the stale alert
        self.client.get("/board")
        # Project touched again — no longer stale
        with self.raw_db() as db:
            db.execute("UPDATE projects SET updated_at = ? WHERE name = 'Proj'", (date.today().isoformat() + "T12:00:00",))
            db.commit()
        # Second board load should resolve it
        self.client.get("/board")
        with self.raw_db() as db:
            alert = db.execute("SELECT * FROM alerts WHERE alert_type = 'stale'").fetchone()
        self.assertEqual(alert["resolved"], 1)
        self.assertIsNotNone(alert["resolved_at"])

    def test_settings_alerts_saves_threshold_severity_and_channels(self):
        resp = self.client.post("/settings/alerts", data={
            "threshold::stale": "14",
            "severity::stale": "critical",
            "notify_email::stale": "on",
            "notify_teams::stale": "on",
            "notify_inapp::stale": "on",
        })
        self.assertEqual(resp.status_code, 302)
        with self.raw_db() as db:
            row = db.execute("SELECT * FROM alert_type_settings WHERE alert_type = 'stale'").fetchone()
        self.assertEqual(row["threshold_days"], 14)
        self.assertEqual(row["severity"], "critical")
        self.assertEqual(row["notify_email"], 1)
        self.assertEqual(row["notify_teams"], 1)
        self.assertEqual(row["notify_inapp"], 1)

    def test_settings_alerts_disabling_inapp_turns_off_notify_event(self):
        # disable in-app for stale entirely (omit its notify_inapp checkbox)
        self.client.post("/settings/alerts", data={
            "threshold::stale": "7", "severity::stale": "warning",  # notify_inapp omitted = off
        })
        with self.raw_db() as db:
            row = db.execute("SELECT notify_inapp FROM alert_type_settings WHERE alert_type = 'stale'").fetchone()
        self.assertEqual(row["notify_inapp"], 0)

        self.new_project()
        old = (date.today() - timedelta(days=60)).isoformat() + "T00:00:00"
        with self.raw_db() as db:
            db.execute("UPDATE projects SET updated_at = ? WHERE name = 'Proj'", (old,))
            db.commit()
        self.client.get("/board")
        with self.raw_db() as db:
            alert = db.execute("SELECT * FROM alerts WHERE alert_type = 'stale'").fetchone()
        self.assertIsNone(alert)

    @patch("app.graph.send_mail", return_value=(True, None))
    def test_new_alert_fires_email_when_type_channel_enabled(self, mock_send_mail):
        self.client.post("/account/email", data={"email": "admin@example.com"})
        self.client.post("/settings/alerts", data={
            "threshold::stale": "7",
            "severity::stale": "warning",
            "notify_email::stale": "on",
            "notify_inapp::stale": "on",
        })
        self.client.post("/settings/integrations", data={"notify_email_enabled": "on"})
        self.new_project()
        old = (date.today() - timedelta(days=60)).isoformat() + "T00:00:00"
        with self.raw_db() as db:
            db.execute("UPDATE projects SET updated_at = ? WHERE name = 'Proj'", (old,))
            db.commit()
        self.client.get("/board")
        mock_send_mail.assert_any_call("admin@example.com", "Project inactive", "Project: Proj (C)")

    def test_audit_logs_filter_by_user_action_and_project(self):
        # admin creates one project, priya creates another
        self.new_project(name="Admin Proj")
        with self.raw_db() as db:
            db.execute(
                "INSERT INTO users (username, password_hash, name, role, active) VALUES ('priya2', 'x', 'Priya', 'Member', 1)"
            )
            db.commit()
            priya_id = db.execute("SELECT id FROM users WHERE username = 'priya2'").fetchone()["id"]
        priya_client = app_module.app.test_client()
        with priya_client.session_transaction() as sess:
            sess["user_id"] = priya_id
            sess["login_at"] = datetime.utcnow().isoformat()
            sess["epoch"] = 0
            sess["user_name"] = "Priya"
            sess["role"] = "Admin"
        priya_client.post(
            "/projects/new",
            data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Priya Proj", "client": "C"},
        )

        with self.raw_db() as db:
            admin_proj_id = db.execute("SELECT id FROM projects WHERE name = 'Admin Proj'").fetchone()["id"]
            priya_proj_id = db.execute("SELECT id FROM projects WHERE name = 'Priya Proj'").fetchone()["id"]

        # filter by user (row link text, not the filter dropdown's <option> text)
        resp = self.client.get("/audit-logs?user=Priya")
        self.assertIn(b">Priya Proj</a>", resp.data)
        self.assertNotIn(b">Admin Proj</a>", resp.data)

        # filter by action
        resp = self.client.get("/audit-logs?action=create_project")
        self.assertIn(b">Admin Proj</a>", resp.data)
        self.assertIn(b">Priya Proj</a>", resp.data)

        # filter by project
        resp = self.client.get(f"/audit-logs?project_id={admin_proj_id}")
        self.assertIn(b">Admin Proj</a>", resp.data)
        self.assertNotIn(b">Priya Proj</a>", resp.data)


class BoardCraftTestCase(unittest.TestCase):
    """Pins the design fixes from the /impeccable critique of the Board, so a
    later refactor can't quietly undo them."""

    def setUp(self):
        fd, db_module.DB_PATH = tempfile.mkstemp()
        os.close(fd)
        os.remove(db_module.DB_PATH)
        isolate_uploads(self)
        app_module.init_db()
        settle_seed_admin()
        self.client = app_module.app.test_client()
        self.client.post("/login", data={"username": "admin", "password": "changeme"})

    def tearDown(self):
        os.unlink(db_module.DB_PATH)

    def _make_project(self):
        """One project on the board, for markup/a11y assertions."""
        self.client.post(
            "/projects/new",
            data={"po_document": (io.BytesIO(b"%PDF-1.4 po"), "po.pdf"), "name": "Late Proj", "client": "C"},
        )

    def test_board_has_no_click_handlers_without_a_keyboard_equivalent(self):
        """Every project on the board must be reachable by keyboard. Rows and
        cards used to be onclick-only, which excluded keyboard and AT users
        from the primary task entirely."""
        self._make_project()
        html = self.client.get("/board").data.decode()
        # no onclick navigation left on non-interactive elements
        self.assertNotIn("<tr onclick", html)
        self.assertNotIn('<div class="card" onclick', html)
        # and a real anchor carries the card's primary action
        self.assertIn('class="card-link"', html)

    def test_skip_link_precedes_the_navigation(self):
        html = self.client.get("/board").data.decode()
        self.assertIn('class="skip-link" href="#main"', html)
        self.assertLess(html.index("skip-link"), html.index("<nav>"))


class SecurityTestCase(unittest.TestCase):
    """Each test here pins one security control. If a control is ever removed
    or weakened, the matching test fails rather than the app silently
    regressing into an exploitable state."""

    def setUp(self):
        fd, db_module.DB_PATH = tempfile.mkstemp()
        os.close(fd)
        os.remove(db_module.DB_PATH)
        isolate_uploads(self)
        app_module.init_db()
        settle_seed_admin()
        self.client = app_module.app.test_client()

    def tearDown(self):
        os.unlink(db_module.DB_PATH)

    def login(self):
        return self.client.post("/login", data={"username": "admin", "password": "changeme"})

    # --- request layer: CSRF -------------------------------------------------

    def test_csrf_rejects_post_without_token(self):
        # raw client: no auto-injected token, i.e. what a forged cross-site
        # form submission actually looks like
        raw = app_module.app.test_client()
        FlaskClient.post(raw, "/login", data={"username": "admin", "password": "changeme"})
        resp = FlaskClient.post(raw, "/login", data={"username": "admin", "password": "changeme"})
        self.assertEqual(resp.status_code, 400)

    def test_csrf_rejects_wrong_token(self):
        self.login()
        resp = self.client.post(
            "/projects/1/delete", data={"_csrf": "not-the-right-token"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_csrf_token_is_rendered_into_forms(self):
        resp = self.client.get("/login")
        self.assertIn(b'name="_csrf"', resp.data)

    # --- transport layer: headers + cookie ----------------------------------

    def test_security_headers_present(self):
        resp = self.client.get("/login")
        self.assertEqual(resp.headers["X-Frame-Options"], "DENY")
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", resp.headers["Content-Security-Policy"])
        self.assertIn("object-src 'none'", resp.headers["Content-Security-Policy"])

    def test_session_cookie_is_hardened(self):
        resp = self.client.get("/login")
        cookie = resp.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    # --- auth layer ---------------------------------------------------------

    def test_login_locks_out_after_repeated_failures(self):
        for _ in range(app_module_security.MAX_LOGIN_FAILURES):
            self.client.post("/login", data={"username": "admin", "password": "wrong"})
        # even the *correct* password is now refused for this username+IP
        self.client.post("/login", data={"username": "admin", "password": "changeme"})
        resp = self.client.get("/board")
        self.assertEqual(resp.status_code, 302, "locked-out login should not have succeeded")

    def test_weak_passwords_rejected(self):
        for weak in ["short", "alllowercaseletters", "123456789012"]:
            self.assertIsNotNone(
                app_module_security.password_problem(weak), f"{weak!r} should be rejected"
            )
        self.assertIsNone(app_module_security.password_problem(STRONG_PASSWORD))

    def test_login_does_not_honour_absolute_redirect(self):
        # ?next=https://evil.example must not become an open redirect
        resp = self.client.post(
            "/login?next=https://evil.example/steal",
            data={"username": "admin", "password": "changeme"},
        )
        self.assertNotIn("evil.example", resp.headers.get("Location", ""))

    # --- data layer ---------------------------------------------------------

    def test_table_identifier_allowlist_blocks_injection(self):
        with self.assertRaises(ValueError):
            db_module.assert_safe_table("users; DROP TABLE projects")
        with self.assertRaises(ValueError):
            db_module.assert_safe_table("users")  # real table, but not soft-deletable
        self.assertEqual(db_module.assert_safe_table("projects"), "projects")

    # --- file layer ---------------------------------------------------------

    def test_upload_extension_allowlist(self):
        for bad in ["evil.html", "evil.svg", "shell.php", "x.js", "noextension"]:
            self.assertFalse(app_module_security.allowed_upload(bad), f"{bad} should be blocked")
        for ok in ["po.pdf", "sheet.XLSX", "photo.jpg"]:
            self.assertTrue(app_module_security.allowed_upload(ok), f"{ok} should be allowed")

    def test_active_content_upload_is_refused_by_the_route(self):
        self.login()
        self.client.post(
            "/projects/new",
            data={
                "po_document": (io.BytesIO(b"%PDF-1.4 fake PO"), "po.pdf"),
                "name": "Sec Proj", "client": "C",
            },
        )
        resp = self.client.post(
            "/projects/1/documents",
            data={"category": "Deliverable", "file": (io.BytesIO(b"<script>alert(1)</script>"), "xss.html")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"isn&#39;t allowed", resp.data)
        with sqlite3.connect(db_module.DB_PATH) as db:
            rows = db.execute("SELECT COUNT(*) FROM documents WHERE filename = 'xss.html'").fetchone()[0]
        self.assertEqual(rows, 0, "blocked upload must not reach the documents table")

    def test_downloads_are_forced_as_attachments(self):
        self.login()
        self.client.post(
            "/projects/new",
            data={
                "po_document": (io.BytesIO(b"%PDF-1.4 fake PO"), "po.pdf"),
                "name": "DL Proj", "client": "C",
            },
        )
        resp = self.client.get("/projects/1/documents/1/download")
        self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))


if __name__ == "__main__":
    unittest.main()
