"""v2.0.2, the 28-29 Oct simulation's lifecycle and atomicity findings: a partial
role-matrix post, a CRM re-send after a discard, a sign-off rejection whose issue
fails, a stage move whose follow-up fails, double waives, double ticks and a lost
AI job claim. Run with: python -m unittest test_v2_atomic"""
import sqlite3
from unittest.mock import patch

import db as db_module
from test_app import AITestBase, app_module
from test_fix_logic import FixBase
from test_v2_intake import DEAL, J, IntakeBase


class Base(FixBase):
    _signoff_setup = FixBase._Meta._signoff_setup
    _ext = FixBase._Meta._ext


class RbacPostTestCase(Base):
    def matrix(self, c):
        return c.get("/api/settings/rbac").get_json()["matrix"]

    def test_a_partial_post_changes_nothing_and_a_wholesale_turn_off_needs_confirm(self):
        c, csrf = self._api_client()
        h = {"X-CSRF-Token": csrf, "Accept": "application/json"}
        before = self.matrix(c)
        # an API caller naming one box used to switch off every grant it left out
        r = c.post("/settings/rbac", data={"edit_project::Member": "on"}, headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("whole matrix", r.get_json()["error"])
        self.assertEqual(self.matrix(c), before)
        # the page's own post (matrix=full) still saves
        fields = {f"{p}::{role}": "on" for p, roles in before.items() for role, ok in roles.items() if ok}
        fields.pop("edit_project_stage::Member")
        r = c.post("/settings/rbac", data={**fields, "matrix": "full"}, headers=h)
        self.assertEqual(r.get_json()["messages"], ["Permissions updated"])
        self.assertFalse(self.matrix(c)["edit_project_stage"]["Member"])
        # switching off more than half of what is on is refused with the count, then saved with confirm=1
        now = self.matrix(c)
        r = c.post("/settings/rbac", data={"matrix": "full"}, headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("would switch off", r.get_json()["error"])
        self.assertEqual(self.matrix(c), now)
        r = c.post("/settings/rbac", data={"matrix": "full", "confirm": "1"}, headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self.matrix(c)["edit_project"]["Member"])
        self.assertTrue(self.matrix(c)["manage_users"]["Admin"])   # the Admin floor holds


class IntakeUndoTestCase(IntakeBase):
    def live(self):
        return self.tuples("SELECT id, intake_pending FROM projects WHERE intake_deal_id = ? AND deleted_at IS NULL", DEAL["deal_id"])

    def test_discard_resend_undo_leaves_one_pending_rollout(self):
        pid = self.post(DEAL).get_json()["rollout"]["id"]
        self.client.post(f"/projects/{pid}/delete", headers=J)
        again = self.post(DEAL)
        self.assertEqual((again.status_code, again.get_json()["created"], again.get_json()["rollout"]["id"]), (200, False, pid))
        self.assertEqual(self.live(), [(pid, 1)])
        self.assertEqual(self.client.post(f"/undo/project/{pid}", headers=J).status_code, 200)
        self.assertEqual(self.live(), [(pid, 1)])
        self.assertEqual(self.audits("intake_create"), 1)

    def test_undo_is_refused_while_a_live_twin_holds_the_deal(self):
        pid = self.post(DEAL, name="crm-a").get_json()["rollout"]["id"]
        self.client.post(f"/projects/{pid}/delete", headers=J)
        twin = self.post(DEAL, token=self.token("crm-b")).get_json()["rollout"]["id"]   # another source: a rollout of its own
        r = self.client.post(f"/undo/project/{pid}", headers=J)
        self.assertEqual(r.status_code, 400)
        self.assertIn("live rollout for deal", r.get_json()["error"])
        self.assertEqual(self.live(), [(twin, 1)])
        with self.assertRaises(sqlite3.IntegrityError), self.raw_db() as db:   # the database holds the rule too
            db.execute("UPDATE projects SET deleted_at = NULL WHERE id = ?", (pid,))


class RejectAtomicTestCase(Base):
    def test_a_failed_issue_leaves_the_version_waiting(self):
        c, h, ann, _ = self._signoff_setup()
        c.post("/api/projects/1/signoff", json={"summary": "Done.", "signer_id": ann, "counter_id": 1, "delivered": ["Everything"]}, headers=h)
        e, eh = self._ext("ann@globex.example")
        with patch("services.raid.create", side_effect=sqlite3.OperationalError("disk I/O error")):
            r = e.post("/api/projects/1/signoff/1/reject", json={"comment": "Runbook missing"}, headers=eh)
        self.assertEqual(r.status_code, 400)
        self.assertIn("did not save", r.get_json()["error"])
        self.assertEqual(self.tuples("SELECT status, reject_comment FROM signoffs"), [("sent", None)])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM raid_items")[0][0], 0)
        self.assertEqual(self.audits("signoff_reject"), 0)
        # and the customer's retry goes through, with its issue
        self.assertEqual(e.post("/api/projects/1/signoff/1/reject", json={"comment": "Runbook missing"}, headers=eh).status_code, 200)
        self.assertEqual(self.tuples("SELECT status FROM signoffs"), [("rejected",)])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM raid_items WHERE kind = 'issue'")[0][0], 1)


class StageFollowUpTestCase(Base):
    def test_a_failed_follow_up_still_answers_the_move(self):
        self.new_project(name="P", client="C")
        s = self.stages()
        pm = self._make_user("pm2", "Member")
        self.sql("UPDATE users SET email = 'pm2@corp.example' WHERE id = ?", pm)
        self.sql("INSERT INTO project_participants (project_id, user_id, role, added_at) VALUES (1, ?, 'Engineer', datetime('now'))", pm)
        self._set_policy(notify_email_enabled="1")
        with patch("services.outbox.add", side_effect=RuntimeError("outbox down")), self.assertLogs(app_module.app.logger, "ERROR") as logged:
            r = self.client.post("/api/projects/1/stage", json={"stage": s[1]})
            again = self.client.post("/api/projects/1/stage", json={"stage": s[2]})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertTrue(r.get_json()["undo"])
        self.assertEqual(again.status_code, 200)
        self.assertEqual(self.sql("SELECT stage FROM projects WHERE id = 1")[0][0], s[2])
        self.assertEqual(self.audits("update_project_stage"), 2)   # one per move
        self.assertTrue(any("notify_users failed" in line for line in logged.output))
        # the admins hear of it in the bell, once a day
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE kind = 'ops' AND user_id = 1")[0][0], 1)


class DoubleClickTestCase(Base):
    def test_two_waives_make_one_version_and_a_400(self):
        from services import signoff
        self.new_project(name="P", client="C")
        self.sql("UPDATE projects SET stage = ?", self.stages()[-2])
        other, csrf = self._api_client()
        real, answers = signoff.sendable, []

        def racing(project):   # the other click lands while this one is between its check and its insert
            if not answers:
                answers.append(None)   # set first: the other click runs this too
                answers[0] = (other.post("/api/projects/1/signoff/waive", json={"reason": "Signed on paper at the site"}, headers={"X-CSRF-Token": csrf}))
            return real(project)
        with patch("services.signoff.sendable", side_effect=racing):
            r = self.client.post("/api/projects/1/signoff/waive", json={"reason": "Signed on paper at the site"})
        self.assertEqual(answers[0].status_code, 200)
        self.assertEqual(r.status_code, 400)
        self.assertIn("already waived", r.get_json()["error"])
        self.assertEqual(self.tuples("SELECT version, status FROM signoffs"), [(1, "waived")])
        again = self.client.post("/api/projects/1/signoff/waive", json={"reason": "Signed on paper at the site"})
        self.assertEqual((again.status_code, again.get_json()["error"]), (400, "The sign-off is already waived"))

    def test_a_double_tick_audits_once(self):
        from services import task_links
        self.new_project(name="P", client="C")
        tid = self.client.post("/projects/1/tasks", json={"title": "Rack the sensors"}).get_json()["id"]
        other, csrf = self._api_client()
        real, answers = task_links.open_predecessors, []

        def racing(db, task_id):   # the other tab's tick commits between this one's read and its write
            if not answers:
                answers.append(None)   # set first: the other click runs this too
                answers[0] = (other.post(f"/projects/1/tasks/{tid}/toggle", json={"done": True}, headers={"X-CSRF-Token": csrf}))
            return real(db, task_id)
        with patch("services.task_links.open_predecessors", side_effect=racing):
            r = self.client.post(f"/projects/1/tasks/{tid}/toggle", json={"done": True})
        self.assertEqual((answers[0].status_code, r.status_code), (200, 200))
        self.assertEqual(self.audits("toggle_task"), 1)
        self.assertEqual(self.sql("SELECT done FROM tasks WHERE id = ?", tid)[0][0], 1)


class AIClaimTestCase(AITestBase):
    def test_a_lost_claim_runs_nothing(self):
        from services.ai import health

        class Racing:   # another worker claims the job between this one's look and its claim
            def __init__(self, db):
                self.db = db

            def __getattr__(self, name):
                return getattr(self.db, name)

            def execute(self, sql, *args):
                cur = self.db.execute(sql, *args)
                if sql.startswith("SELECT * FROM ai_jobs WHERE status = 'queued'"):
                    row = cur.fetchone()
                    other = sqlite3.connect(db_module.DB_PATH)
                    other.execute("UPDATE ai_jobs SET status = 'running', started_at = 'the other worker' WHERE id = ?", (row["id"],))
                    other.commit()
                    other.close()
                    return type("Cur", (), {"fetchone": lambda _s: row})()
                return cur
        with self._ctx():
            from db import get_db
            jid = health.queue(get_db(), "validate")
            with patch("services.ai.health.validate_all") as ran:
                self.assertIsNone(health.work_once(Racing(get_db())))
            ran.assert_not_called()
            self.assertEqual(tuple(get_db().execute("SELECT status, started_at FROM ai_jobs WHERE id = ?", (jid,)).fetchone()), ("running", "the other worker"))
