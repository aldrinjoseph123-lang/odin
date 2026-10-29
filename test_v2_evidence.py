"""Deleting a signed-off rollout (product decision, 29 Oct 2026): a reason is
required, the admins are told, and the signed record is kept through the
nightly purge for the audit retention period.
Run with: python -m unittest test_v2_evidence"""
import io
import json
import os
import zipfile
from datetime import datetime, timedelta

import backup
import db as db_module
import test_app
from test_app import app_module
from test_fix_logic import FixBase

J = {"Accept": "application/json"}
REASON = "Created in error: duplicate of rollout 7"


class EvidenceTestCase(FixBase):
    def evidence_dir(self):
        return os.path.join(db_module.DATA_DIR, "signoff-archive")

    def files(self):
        folder = self.evidence_dir()
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def waived(self):
        """A rollout closed the fast way: the admin waives the sign-off."""
        self.new_project(name="Signed Co / Rollout", client="C")
        self.sql("UPDATE projects SET stage = ?", self.stages()[-2])
        self.assertEqual(self.client.post("/api/projects/1/signoff/waive", json={"reason": "Signed on paper at the site"}).status_code, 200)

    def test_no_reason_no_delete(self):
        self.waived()
        r = self.client.post("/projects/1/delete", headers=J)
        self.assertEqual(r.status_code, 400, r.get_data())
        self.assertIn("Give a reason", r.get_data(as_text=True))
        short = self.client.post("/projects/1/delete", data={"reason": "oops"}, headers=J)
        self.assertEqual(short.status_code, 400)
        self.assertIsNone(self.sql("SELECT deleted_at FROM projects")[0][0])
        self.assertEqual((self.files(), self.audits("delete_project")), ([], 0))

    def test_the_pack_is_written_audited_and_the_admins_told(self):
        self.waived()
        r = self.client.post("/projects/1/delete", data={"reason": REASON}, headers=J)
        self.assertEqual(r.status_code, 200, r.get_data())
        self.assertIsNotNone(self.sql("SELECT deleted_at FROM projects")[0][0])
        names = self.files()
        self.assertEqual(names, ["1-Signed-Co-Rollout-v1.json", "1-Signed-Co-Rollout-v1.pdf"])
        with open(os.path.join(self.evidence_dir(), names[1]), "rb") as fh:
            self.assertTrue(fh.read().startswith(b"%PDF"))
        with open(os.path.join(self.evidence_dir(), names[0]), encoding="utf-8") as fh:
            pack = json.load(fh)
        self.assertEqual((pack["reason"], pack["status"], pack["waiver_reason"], pack["deleted_by"]["id"], pack["csat"]),
                         (REASON, "waived", "Signed on paper at the site", 1, None))
        self.assertTrue(pack["content_hash"] and pack["content"]["project"]["name"] == "Signed Co / Rollout" and pack["deleted_at"])
        detail = self.sql("SELECT details FROM audit_logs WHERE action = 'delete_project'")[0][0]
        self.assertIn(REASON, detail)
        self.assertIn("1-Signed-Co-Rollout-v1.pdf", detail)
        bell = self.tuples("SELECT user_id, project_id, title FROM notifications WHERE kind = 'ops'")
        self.assertEqual(bell, [(1, None, "Signed-off rollout deleted: Signed Co / Rollout")])
        # the purge removes the rows and the bell item stays; the files stay
        self.sql("UPDATE projects SET deleted_at = '2020-01-01T00:00:00'")
        with self.raw_db() as db:
            db.execute("PRAGMA foreign_keys = ON")
            db_module.cleanup_soft_deletes(db)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM signoffs").fetchone()[0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE kind = 'ops'")[0][0], 1)
        self.assertEqual(self.files(), names)

    def test_the_paper_copy_and_the_rating_are_kept(self):
        self.new_project(name="P", client="C")
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        self.sql("UPDATE projects SET stage = ?", self.stages()[-2])
        ann = self.sql("SELECT id FROM users WHERE email = 'ann@acme.example'")[0][0]
        self.assertEqual(self.client.post("/api/projects/1/signoff", json={"signer_id": ann, "counter_id": 1, "summary": "Done", "delivered": ["All of it"]}).status_code, 200)
        with app_module.app.app_context():
            from policies import local_today
            today = local_today().isoformat()
        self.client.post("/api/projects/1/signoff/1/upload", data={"file": (io.BytesIO(b"%PDF-1.4 paper copy"), "signed.pdf"), "signer_name": "Ann", "signed_on": today})
        self.sql("INSERT INTO csat (project_id, signoff_version, rating, comment, by_id, by_name, at) VALUES (1, 1, 5, 'Smooth', ?, 'Ann', ?)", ann, datetime.utcnow().isoformat())
        self.assertEqual(self.client.post("/projects/1/delete", data={"reason": REASON}, headers=J).status_code, 200)
        names = self.files()
        self.assertEqual(names, ["1-P-v1-paper.pdf", "1-P-v1.json", "1-P-v1.pdf"])
        with open(os.path.join(self.evidence_dir(), "1-P-v1-paper.pdf"), "rb") as fh:
            self.assertEqual(fh.read(), b"%PDF-1.4 paper copy")
        with open(os.path.join(self.evidence_dir(), "1-P-v1.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["csat"]["rating"], 5)

    def test_an_unsigned_rollout_deletes_as_before(self):
        self.new_project(name="Plain", client="C")
        r = self.client.post("/projects/1/delete", headers=J)
        self.assertEqual(r.status_code, 200, r.get_data())
        self.assertEqual((self.files(), self.sql("SELECT COUNT(*) FROM notifications WHERE kind = 'ops'")[0][0]), ([], 0))
        self.assertIn(self.sql("SELECT details FROM audit_logs WHERE action = 'delete_project'")[0][0], (None, ""))

    def test_undo_leaves_the_pack(self):
        self.waived()
        undo = self.client.post("/projects/1/delete", data={"reason": REASON}, headers=J).get_json()["undo"]
        names = self.files()
        self.assertEqual(self.client.post(undo, headers=J).status_code, 200)
        self.assertIsNone(self.sql("SELECT deleted_at FROM projects")[0][0])
        self.assertEqual(self.files(), names)

    def test_a_set_aside_version_is_kept_too(self):
        self.waived()
        self.sql("UPDATE signoffs SET superseded_at = '2026-10-01T00:00:00'")   # the rollout was reopened
        self.assertEqual(self.client.post("/projects/1/delete", headers=J).status_code, 400)   # still signed evidence
        self.assertEqual(self.client.post("/projects/1/delete", data={"reason": REASON}, headers=J).status_code, 200)
        self.assertEqual(len(self.files()), 2)

    def test_backup_includes_the_folder(self):
        self.waived()
        self.client.post("/projects/1/delete", data={"reason": REASON}, headers=J)
        ok, message = backup.run_backup(trigger="test")
        self.assertTrue(ok, message)
        archive = [f for f in os.listdir(os.path.join(db_module.DATA_DIR, "backups")) if f.endswith(".zip")][0]
        inside = zipfile.ZipFile(os.path.join(db_module.DATA_DIR, "backups", archive)).namelist()
        self.assertIn("signoff-archive/1-Signed-Co-Rollout-v1.pdf", inside)

    def test_retention_trims_old_evidence_and_keeps_young(self):
        from services import retention
        self.waived()
        self.client.post("/projects/1/delete", data={"reason": REASON}, headers=J)
        old = os.path.join(self.evidence_dir(), "9-Old-v1.json")
        with open(old, "w") as fh:
            fh.write("{}")
        long_ago = (datetime.utcnow() - timedelta(days=365 * 4)).timestamp()   # audit_keep is 3 years by default
        os.utime(old, (long_ago, long_ago))
        retention.run_audit_retention()
        self.assertNotIn("9-Old-v1.json", self.files())
        self.assertEqual(len(self.files()), 2)
        self.sql("INSERT INTO settings (key, value) VALUES ('policy.audit_keep', 'forever')")
        with open(old, "w") as fh:
            fh.write("{}")
        os.utime(old, (long_ago, long_ago))
        retention.run_audit_retention()
        self.assertIn("9-Old-v1.json", self.files())   # forever keeps everything

    def test_settings_lists_the_pack(self):
        self.waived()
        self.client.post("/projects/1/delete", data={"reason": REASON}, headers=J)
        rows = self.client.get("/api/settings?section=audit").get_json()["audit_archives"]
        self.assertEqual(sorted((r["name"], r["kind"]) for r in rows),
                         [("1-Signed-Co-Rollout-v1.json", "Sign-off evidence"), ("1-Signed-Co-Rollout-v1.pdf", "Sign-off evidence")])
        self.assertTrue(all(r["size"] > 0 for r in rows))


if __name__ == "__main__":
    import unittest
    unittest.main()
