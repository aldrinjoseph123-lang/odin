"""Release safety: preflight (it decides a production rollback, review P2-55)
and the schema version that keeps a rollback from deleting a newer release's
settings (P2-15). Run with: python -m unittest test_release_safety"""
import contextlib
import io
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from test_app import app_module, db_module
from test_fix_logic import FixBase
import preflight

GOOD_ENV = {"SECRET_KEY": "k" * 64, "PMS_HTTPS": "1", "PMS_TRUST_PROXY": "1"}


class Base(FixBase):
    def version(self):
        return self.sql("PRAGMA user_version")[0][0]


class PreflightTestCase(Base):
    def setUp(self):
        super().setUp()
        # a production-ready database: seed password changed, public address set
        self.sql("UPDATE users SET password_hash = ?", generate_password_hash("a-real-one", method="pbkdf2:sha256"))
        self.sql("INSERT OR REPLACE INTO settings (key, value) VALUES ('policy.public_url', 'https://odin.example.com')")

    def run_preflight(self, **env):
        merged = {k: v for k, v in {**GOOD_ENV, **env}.items() if v is not None}
        out = io.StringIO()
        with patch.dict(os.environ, merged, clear=True), contextlib.redirect_stdout(out):
            code = preflight.main()
        return code, out.getvalue()

    def line(self, output, name):
        """The status of one check: PASS, FAIL or WARN."""
        before = output.split(f"] {name}")[0]
        return before[before.rindex("[") + 1:]

    def test_good_env_passes(self):
        code, out = self.run_preflight()
        self.assertEqual(code, 0, out)
        self.assertNotIn("[FAIL]", out)
        self.assertNotIn("[WARN]", out)
        self.assertIn("Ready to serve.", out)

    def test_secret_key_missing_default_or_short_fails(self):
        for key in (None, "", "dev-secret-change-me", "short"):
            code, out = self.run_preflight(SECRET_KEY=key)
            self.assertEqual(code, 1, key)
            self.assertEqual(self.line(out, "SECRET_KEY is set"), "FAIL", key)

    def test_https_proxy_and_debug_flags(self):
        for env, check in (
            ({"PMS_HTTPS": None}, "Session cookie marked Secure"),
            ({"PMS_HTTPS": "0"}, "Session cookie marked Secure"),
            ({"PMS_TRUST_PROXY": None}, "Proxy headers trusted"),
            ({"FLASK_DEBUG": "1"}, "Debug mode off"),
            ({"FLASK_ENV": "development"}, "Debug mode off"),
        ):
            code, out = self.run_preflight(**env)
            self.assertEqual(code, 1, env)
            self.assertEqual(self.line(out, check), "FAIL", env)

    def test_seed_admin_password_fails(self):
        self.sql("UPDATE users SET password_hash = ? WHERE username = 'admin'",
                 generate_password_hash("changeme", method="pbkdf2:sha256"))
        code, out = self.run_preflight()
        self.assertEqual(code, 1)
        self.assertEqual(self.line(out, "Default admin password changed"), "FAIL")
        self.assertIn("admin", out)

    def test_inactive_seed_admin_is_ignored(self):
        self.sql("UPDATE users SET password_hash = ?, active = 0",
                 generate_password_hash("changeme", method="pbkdf2:sha256"))
        code, out = self.run_preflight()
        self.assertEqual(code, 0, out)

    def test_public_url_unset_fails(self):
        self.sql("DELETE FROM settings WHERE key = 'policy.public_url'")
        code, out = self.run_preflight()
        self.assertEqual(code, 1)
        self.assertEqual(self.line(out, "Public web address is set"), "FAIL")

    def test_data_dir_not_writable_fails(self):
        with patch.object(db_module, "DATA_DIR", "/nonexistent-odin-data"):
            code, out = self.run_preflight()
        self.assertEqual(code, 1)
        self.assertEqual(self.line(out, "Data directory is writable"), "FAIL")

    def test_damaged_database_fails_and_other_checks_still_run(self):
        with open(db_module.DB_PATH, "wb") as f:
            f.write(b"not a database" * 200)
        code, out = self.run_preflight()
        self.assertEqual(code, 1)
        self.assertEqual(self.line(out, "Database opens"), "FAIL")
        self.assertEqual(self.line(out, "SECRET_KEY is set"), "PASS")   # one broken check masks none

    def test_no_database_yet_passes_and_creates_none(self):
        os.remove(db_module.DB_PATH)
        code, out = self.run_preflight()
        missing = not os.path.exists(db_module.DB_PATH)
        open(db_module.DB_PATH, "w").close()   # for tearDown
        self.assertTrue(missing, "preflight created a database")
        self.assertEqual(code, 0, out)
        self.assertIn("no database yet", out)

    def test_m365_configured_is_a_note_not_a_failure(self):
        self.sql("INSERT OR REPLACE INTO settings (key, value) VALUES ('ms_client_id', 'abc')")
        code, out = self.run_preflight()
        self.assertEqual(code, 0, out)
        self.assertIn("AADSTS50011", out)

    def test_schema_newer_than_code_warns_but_passes(self):
        """A rollback (older code on a newer database) must still pass, or the
        update script's rollback would fail its own preflight."""
        self.sql(f"PRAGMA user_version = {db_module.SCHEMA_VERSION + 1}")
        code, out = self.run_preflight()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.line(out, "Database schema matches this code"), "WARN")
        self.assertIn("rollback", out)
        self.assertIn("1 warning(s)", out)

    def test_schema_older_or_equal_passes(self):
        self.assertEqual(self.line(self.run_preflight()[1], "Database schema matches this code"), "PASS")
        self.sql("PRAGMA user_version = 0")
        code, out = self.run_preflight()
        self.assertEqual(code, 0, out)
        self.assertIn("migrated to", out)


class SchemaVersionTestCase(Base):
    def migrate(self):
        con = sqlite3.connect(db_module.DB_PATH)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            app_module.migrate_db(con)
        con.commit(); con.close()
        return err.getvalue()

    def plant(self, permission, alert_type):
        self.sql("INSERT INTO role_permissions (permission, role, allowed) VALUES (?, 'Admin', 1)", permission)
        self.sql("INSERT INTO alert_type_settings (alert_type, severity) VALUES (?, 'info')", alert_type)
        self.sql("INSERT INTO alerts (alert_type, title, created_at) VALUES (?, 't', '2026-10-01')", alert_type)

    def survives(self, permission, alert_type):
        return (bool(self.sql("SELECT 1 FROM role_permissions WHERE permission = ?", permission)),
                bool(self.sql("SELECT 1 FROM alert_type_settings WHERE alert_type = ?", alert_type)),
                bool(self.sql("SELECT 1 FROM alerts WHERE alert_type = ?", alert_type)))

    def test_boot_stamps_the_schema_version(self):
        self.assertEqual(self.version(), db_module.SCHEMA_VERSION)
        self.sql("PRAGMA user_version = 0")      # a database from v1.7.0 or earlier
        self.migrate()
        self.assertEqual(self.version(), db_module.SCHEMA_VERSION)

    def test_names_this_code_does_not_know_survive_a_boot(self):
        """A newer release's permission or alert type is not this code's to delete."""
        self.plant("future_permission", "future_alert")
        self.migrate()
        self.assertEqual(self.survives("future_permission", "future_alert"), (True, True, True))

    def test_retired_names_are_deleted(self):
        retired = db_module.RETIRED_ALERT_TYPES[0]
        self.plant("unused", retired)
        with patch.object(db_module, "RETIRED_PERMISSIONS", ("unused",)):
            self.migrate()
        self.assertEqual(self.survives("unused", retired), (False, False, False))

    def test_rollback_skips_destructive_steps_and_keeps_the_newer_version(self):
        newer = db_module.SCHEMA_VERSION + 1
        self.sql(f"PRAGMA user_version = {newer}")
        retired = db_module.RETIRED_ALERT_TYPES[0]
        self.plant("unused", retired)
        with patch.object(db_module, "RETIRED_PERMISSIONS", ("unused",)):
            warning = self.migrate()
        self.assertIn("newer than this code", warning)
        self.assertEqual(self.survives("unused", retired), (True, True, True))
        self.assertEqual(self.version(), newer)    # never lowered: re-upgrade sees its own schema


if __name__ == "__main__":
    unittest.main()
