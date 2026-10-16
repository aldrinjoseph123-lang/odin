"""v2.0.0 small items: the admin switches that are policies now, the hashed Python
lock, and the reason for declining a sign-up. Run with: python -m unittest test_v2_small"""
import pathlib
import re
import subprocess
import sys
from unittest.mock import patch

import db as db_module
from test_app import app_module
from test_fix_logic import FixBase

ROOT = pathlib.Path(__file__).resolve().parent
J = {"Accept": "application/json"}
SWITCHES = ("notify_email_enabled", "notify_teams_enabled", "notify_teams_chat_enabled", "onedrive_mirror_uploads_enabled", "guest_links_enabled")


class SwitchPolicyTestCase(FixBase):
    def policy_rows(self):
        return {r[0]: r[1] for r in self.sql("SELECT key, value FROM settings WHERE key LIKE 'policy.%'")}

    def test_a_saved_legacy_choice_is_carried_over_once_and_the_policy_wins_after(self):
        self.sql("DELETE FROM settings WHERE key IN ({})".format(",".join(f"'policy.{k}'" for k in SWITCHES)))
        for k, v in (("notify_email_enabled", "1"), ("guest_links_enabled", "0"), ("onedrive_mirror_uploads_enabled", "0")):
            self.sql("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", k, v)
        self.sql("DELETE FROM settings WHERE key IN ('notify_teams_enabled', 'notify_teams_chat_enabled')")   # never saved: stays at the default
        with self.raw_db() as db:
            db_module.migrate_db(db)
        rows = self.policy_rows()
        self.assertEqual((rows["policy.notify_email_enabled"], rows["policy.guest_links_enabled"], rows["policy.onedrive_mirror_uploads_enabled"]), ("1", "0", "0"))
        self.assertNotIn("policy.notify_teams_enabled", rows)
        self.assertNotIn("policy.notify_teams_chat_enabled", rows)
        # the admin changes it through the policy form; the next boot must not bring the old value back
        self.client.post("/settings/policies/notifications", data={"notify_email_enabled": "0"}, headers=J)
        with self.raw_db() as db:
            db_module.migrate_db(db)
        self.assertEqual(self.policy_rows()["policy.notify_email_enabled"], "0")
        self.assertEqual(self.sql("SELECT value FROM settings WHERE key = 'notify_email_enabled'")[0][0], "1", "the old row stays for a rollback")

    def test_the_settings_page_draws_them_and_the_audit_row_names_the_switch(self):
        d = self.client.get("/api/settings").get_json()
        self.assertNotIn("toggles", d)
        by = {p["key"]: p for p in d["policies"]}
        self.assertEqual([by[k]["area"] for k in SWITCHES], ["notifications", "notifications", "notifications", "integrations", "security"])
        self.assertEqual((by["guest_links_enabled"]["value"], by["notify_email_enabled"]["value"]), (True, False))   # defaults as before
        self.assertIn(self.client.post("/settings/integrations", headers=J).status_code, (404, 405), "the old save route is gone")
        self.client.post("/settings/policies/notifications", data={"notify_teams_chat_enabled": "on"}, headers=J)
        row = self.sql("SELECT details FROM audit_logs WHERE action = 'update_policies' ORDER BY id DESC LIMIT 1")[0][0]
        self.assertEqual(row, "notify_teams_chat_enabled=1")

    def test_readers_follow_the_policy(self):
        from policies import policy
        self.new_project(name="P", client="C")
        tok = self.sql("SELECT customer_token FROM projects WHERE id = 1")[0][0]
        anon = app_module.app.test_client()
        self.assertEqual(anon.get(f"/guest/{tok}").status_code, 200)
        self._set_policy(guest_links_enabled="0")
        self.assertEqual(anon.get(f"/guest/{tok}").status_code, 404)
        self.assertFalse(self.client.get("/api/projects/1").get_json()["guest_links_enabled"])
        self._set_policy(notify_email_enabled="1")
        self.assertTrue(self.client.get("/api/account").get_json()["mail_enabled"])
        with app_module.app.app_context():
            self.assertTrue(policy("notify_email_enabled"))

    def test_no_reader_still_looks_for_the_old_rows(self):
        old = re.compile(r"""get_setting\(\s*["'](%s)["']""" % "|".join(SWITCHES))
        hits = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*.py") if not {"venv", "node_modules"} & set(p.parts) and not p.name.startswith("test_") and old.search(p.read_text())]
        self.assertEqual(hits, [])


class DeclineReasonTestCase(FixBase):
    def pending(self, name="stan"):
        self.sql("INSERT INTO users (username, password_hash, name, role, active, pending, email) VALUES (?, 'x', ?, 'Viewer', 0, 1, ?)", name, name.title(), f"{name}@corp.example")
        return self.sql("SELECT id FROM users WHERE username = ?", name)[0][0]

    def test_the_reason_is_kept_on_the_account_and_in_the_audit_row(self):
        uid = self.pending()
        r = self.client.post(f"/users/{uid}/decline", data={"reason": "  not on the\nrollout team  "}, headers=J)
        self.assertEqual(r.get_json()["messages"], ["Declined Stan"])
        self.assertEqual([tuple(x) for x in self.sql("SELECT active, pending, declined_reason FROM users WHERE id = ?", uid)], [(0, 0, "not on the rollout team")])
        self.assertEqual(self.sql("SELECT details FROM audit_logs WHERE action = 'decline_access'")[0][0], "reason: not on the rollout team")
        shown = next(u for u in self.client.get("/api/users").get_json()["users"] if u["id"] == uid)
        self.assertEqual(shown["declined_reason"], "not on the rollout team")

    def test_a_reason_is_optional_and_capped_and_nobody_is_emailed(self):
        plain, long = self.pending("pat"), self.pending("lou")
        with patch("graph.send_mail") as mail:
            self.client.post(f"/users/{plain}/decline", headers=J)
            r = self.client.post(f"/users/{long}/decline", data={"reason": "x" * 301}, headers=J)
        mail.assert_not_called()
        self.assertIsNone(self.sql("SELECT declined_reason FROM users WHERE id = ?", plain)[0][0])
        self.assertEqual(self.sql("SELECT details FROM audit_logs WHERE action = 'decline_access'")[0][0], None)
        self.assertEqual(self.sql("SELECT pending FROM users WHERE id = ?", long)[0][0], 1, "refused, still waiting")
        self.assertIn("300", str(r.get_json()))
        self.assertEqual(self.client.post(f"/users/{long}/decline", data={"reason": "x" * 300}, headers=J).status_code, 200)


class LockTestCase(FixBase):
    def test_the_lock_holds_every_pin_with_a_hash(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import make_lock
        finally:
            sys.path.pop(0)
        locked = {}
        for line in (ROOT / "requirements.lock").read_text().splitlines():
            if m := re.match(r"([A-Za-z0-9_.-]+)==(\S+) \\$", line):
                locked[m[1].lower()] = [m[2], 0]
                last = locked[m[1].lower()]
            elif re.fullmatch(r"\s+--hash=sha256:[0-9a-f]{64}( \\)?", line):
                last[1] += 1
        pins = make_lock.pins()
        self.assertEqual(set(locked), set(pins), "requirements.lock is stale: python3 scripts/make_lock.py")
        for name, version in pins.items():
            self.assertEqual(locked[name][0], version, name)
            self.assertGreaterEqual(locked[name][1], 1, name)

    def test_the_image_installs_from_the_lock_with_hashes_required(self):
        docker = (ROOT / "Dockerfile").read_text()
        self.assertIn("pip install --no-cache-dir --require-hashes -r requirements.lock", docker)
        self.assertIn("COPY requirements.lock", docker)
        self.assertIn("make_lock.py", (ROOT / "docs" / "RELEASING.md").read_text())
