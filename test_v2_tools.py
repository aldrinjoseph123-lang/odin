"""Odin 2.0 quality-of-life tools (advice B11, B16, B17, B19, B20): the Users access
review, the quick-add on My work, the RAID and tasks CSV of a rollout.
Run with: python -m unittest test_v2_tools

Every date is an offset from a fixed `now` or from the real one, so no test
depends on the weekday or the month."""
import io
from datetime import datetime, timedelta
from unittest.mock import patch

from test_app import STRONG_PASSWORD, app_module
from test_fix_logic import FixBase

J = {"Accept": "application/json"}
NOW = datetime(2026, 11, 4, 12, 0)


def ago(days):
    return (datetime.utcnow() - timedelta(days=days)).isoformat()


class AccessReviewTestCase(FixBase):
    def staff(self, name, last_login=None, created=None, active=1):
        uid = self._make_user(name, "Member")
        self.sql("UPDATE users SET last_login_at = ?, created_at = ?, active = ? WHERE id = ?", last_login, created or ago(400), active, uid)
        return uid

    def flagged(self):
        d = self.client.get("/api/users").get_json()
        return {u["username"]: u["review"] for u in d["users"] if u["review"]}

    def test_the_review_service_with_a_fixed_clock(self):
        from db import get_db
        from services.access_review import review
        self.ctx()
        quiet = self.staff("quiet", last_login=(NOW - timedelta(days=91)).isoformat())
        busy = self.staff("busy", last_login=(NOW - timedelta(days=89)).isoformat())
        never = self.staff("never", created=(NOW - timedelta(days=120)).isoformat())
        fresh = self.staff("fresh", created=(NOW - timedelta(days=5)).isoformat())   # made inside the window: not yet quiet
        gone = self.staff("gone", last_login=(NOW - timedelta(days=300)).isoformat(), active=0)   # already deactivated
        flagged = review(get_db(), 90, now=NOW)
        self.assertEqual(flagged[quiet], ["No sign-in for 90+ days"])
        self.assertEqual(flagged[never], ["Never signed in, made over 90 days ago"])
        for uid in (busy, fresh, gone):
            self.assertNotIn(uid, flagged)
        self.assertEqual(review(get_db(), 30, now=NOW)[busy], ["No sign-in for 30+ days"])   # the window is the argument

    def test_externals_whose_rollouts_have_all_closed_are_flagged(self):
        self.new_project(name="Live", client="C")
        self.new_project(name="Done", client="C")
        self._invite(1, "open@acme.example", "Customer", "Open")
        self._invite(2, "shut@acme.example", "Customer", "Shut")
        self._invite(2, "both@acme.example", "Customer", "Both")
        self._invite(1, "both@acme.example", "Customer", "Both")
        self._invite(2, "none@acme.example", "Contractor", "None")
        last = self.stages(2)[-1]
        self.sql("UPDATE projects SET stage = ? WHERE id = 2", last)
        self.sql("DELETE FROM project_participants WHERE user_id = (SELECT id FROM users WHERE email = 'none@acme.example')")
        self.sql("UPDATE users SET last_login_at = ? WHERE kind = 'external'", ago(1))   # all signed in lately: only the rollouts speak
        got = self.flagged()
        self.assertEqual(got["shut@acme.example"], ["All their rollouts have closed"])
        self.assertEqual(got["none@acme.example"], ["On no rollout"])
        self.assertNotIn("open@acme.example", got)
        self.assertNotIn("both@acme.example", got, "one open rollout keeps the account in use")

    def test_the_window_is_a_policy_and_the_csv_carries_the_reason(self):
        self.staff("quiet", last_login=ago(100))
        self.assertEqual(self.flagged(), {"quiet": ["No sign-in for 90+ days"]})
        self.assertEqual(self.client.get("/api/users").get_json()["review_days"], 90)
        self._set_policy(access_review_days="120")
        self.assertEqual(self.flagged(), {})
        self._set_policy(access_review_days="30")
        d = self.client.get("/api/users").get_json()
        self.assertEqual(d["review_days"], 30)
        self.assertEqual(self.flagged()["quiet"], ["No sign-in for 30+ days"])
        rows = self.client.get("/users/export.csv").data.decode().splitlines()
        self.assertTrue(rows[0].endswith(",review"))
        self.assertTrue(any(r.startswith("quiet,") and r.endswith("No sign-in for 30+ days") for r in rows))

    def test_the_policy_is_on_the_people_settings_with_its_limits(self):
        by = {p["key"]: p for p in self.client.get("/api/settings").get_json()["policies"]}
        p = by["access_review_days"]
        self.assertEqual((p["area"], p["value"]), ("people", 90))
        r = self.client.post("/settings/policies/people", data={"access_review_days": "3"}, headers=J)
        self.assertNotEqual(r.get_json().get("messages"), [])   # under the minimum: refused, said
        self.assertEqual(self.client.get("/api/users").get_json()["review_days"], 90)

    def test_one_click_deactivate_is_the_audited_route_and_pending_accounts_are_not_reviewed(self):
        quiet = self.staff("quiet", last_login=ago(200))
        self.sql("INSERT INTO users (username, password_hash, name, role, active, pending, created_at) VALUES ('wait', 'x', 'Wait', 'Viewer', 0, 1, ?)", ago(300))
        self.assertEqual(set(self.flagged()), {"quiet"})
        r = self.client.post(f"/users/{quiet}/active", data={"active": "0"}, headers=J)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.sql("SELECT active FROM users WHERE id = ?", quiet)[0][0], 0)
        self.assertEqual(self.audits("set_user_active"), 1)
        self.assertEqual(self.flagged(), {}, "a deactivated account leaves the review")

    def test_only_manage_users_sees_it(self):
        self._make_user("viewer", "Viewer")
        c, _ = self._api_client("viewer", STRONG_PASSWORD)
        self.assertEqual(c.get("/api/users").status_code, 403)


class QuickAddTestCase(FixBase):
    def make_as(self, c, name):
        """A rollout the signed-in person creates: she is its project manager."""
        c.post("/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": name, "client": "C"})

    def test_my_work_marks_the_rollouts_a_task_may_be_added_to(self):
        pm = self._make_user("pm", "Member")
        self.new_project(name="Helped", client="C")   # the admin's rollout, rollout 1
        self.sql("INSERT INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (1, ?, 'Sales', 1, '2026-11-01T00:00:00')", pm)
        c, csrf = self._api_client("pm", STRONG_PASSWORD)
        self.make_as(c, "Mine")
        flags = {p["name"]: p["can_add_task"] for p in c.get("/api/my-work").get_json()["projects"]}
        self.assertEqual(flags, {"Mine": True, "Helped": False})

    def test_the_task_lands_on_the_current_stage_through_the_ordinary_route_and_is_audited(self):
        pm = self._make_user("pm", "Member")
        c, csrf = self._api_client("pm", STRONG_PASSWORD)
        self.make_as(c, "Mine")
        stage = c.get("/api/my-work").get_json()["projects"][0]["stage"]
        r = c.post("/projects/1/tasks", json={"title": "Book the crane", "stage": stage, "assignee_id": pm, "due_date": "2026-12-01"},
                   headers={"X-CSRF-Token": csrf, "Accept": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([tuple(x) for x in self.sql("SELECT title, stage, assignee_id, due_date FROM tasks")], [("Book the crane", stage, pm, "2026-12-01")])
        self.assertEqual(self.audits("add_task"), 1)
        mine = c.get("/api/my-work").get_json()
        self.assertEqual([t["title"] for t in mine["tasks"]], ["Book the crane"])

    def test_a_rollout_flagged_false_refuses_the_add(self):
        pm = self._make_user("pm", "Member")
        self.new_project(name="Helped", client="C")
        self.sql("INSERT INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (1, ?, 'Sales', 1, '2026-11-01T00:00:00')", pm)
        c, csrf = self._api_client("pm", STRONG_PASSWORD)
        r = c.post("/projects/1/tasks", json={"title": "No", "stage": "x", "assignee_id": pm}, headers={"X-CSRF-Token": csrf, "Accept": "application/json"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tasks")[0][0], 0)


class RolloutCsvTestCase(FixBase):
    def setUp(self):
        super().setUp()
        self.new_project(name="Alpha / Phase 2", client="C")
        c, csrf = self._api_client()
        self.h = {"X-CSRF-Token": csrf, "Accept": "application/json"}
        c.post("/api/projects/1/raid", json={"kind": "risk", "title": "=HYPERLINK(\"http://evil.example\")", "impact": "high", "likelihood": "medium", "detail": "Line one, with a comma"}, headers=self.h)
        c.post("/api/projects/1/raid", json={"kind": "issue", "title": "Gate stuck", "impact": "low", "customer_visible": True}, headers=self.h)
        c.post("/projects/1/tasks", json={"title": "+cmd|' /C calc'!A0", "stage": self.stages()[0], "due_date": "2026-12-01"}, headers=self.h)
        c.post("/projects/1/tasks", json={"title": "Survey the site", "stage": self.stages()[0], "assignee_id": 1, "estimate_hours": 3}, headers=self.h)
        self.c = c

    def rows(self, path, client=None):
        import csv, io
        r = (client or self.c).get(path)
        self.assertEqual(r.status_code, 200)
        return r, list(csv.reader(io.StringIO(r.data.decode())))

    def test_raid_csv_has_the_columns_the_register_shows(self):
        r, rows = self.rows("/projects/1/raid.csv")
        self.assertEqual(r.mimetype, "text/csv")
        self.assertIn("odin-raid-Alpha-Phase-2.csv", r.headers["Content-Disposition"])
        self.assertEqual(r.headers["Cache-Control"], "private, no-store")
        self.assertEqual(rows[0], ["Kind", "Title", "Detail", "Impact", "Likelihood", "Status", "Owner", "Due date", "Stage",
                                   "Resolution", "Shown to the customer", "Created by", "Created at", "Closed at"])
        by_kind = {x[0]: x for x in rows[1:]}
        self.assertEqual(sorted(by_kind), ["issue", "risk"])
        self.assertEqual((by_kind["issue"][1], by_kind["issue"][3], by_kind["issue"][5], by_kind["issue"][10]), ("Gate stuck", "low", "open", "yes"))
        self.assertEqual(by_kind["risk"][2], "Line one, with a comma", "a comma stays in its cell")

    def test_tasks_csv_has_the_columns_the_task_list_shows(self):
        r, rows = self.rows("/projects/1/tasks.csv")
        self.assertIn("odin-tasks-Alpha-Phase-2.csv", r.headers["Content-Disposition"])
        self.assertEqual(rows[0], ["Task", "Stage", "Assignee", "Due date", "Done", "Done at", "Estimate hours", "Repeats", "Waits on", "Kind", "Created by", "Created at"])
        survey = next(x for x in rows[1:] if x[0] == "Survey the site")
        admin = self.sql("SELECT name FROM users WHERE id = 1")[0][0]
        self.assertEqual((survey[1], survey[2], survey[4], survey[6], survey[9]), (self.stages()[0], admin, "", "3.0", "task"))
        self.assertEqual(len(rows), 3)

    def test_a_cell_that_starts_like_a_formula_is_neutralised(self):
        for path, col in (("/projects/1/raid.csv", 1), ("/projects/1/tasks.csv", 0)):
            _, rows = self.rows(path)
            evil = [x[col] for x in rows[1:] if x[col][:2] in ("'=", "'+")]
            self.assertEqual(len(evil), 1, path)
            self.assertFalse(any(x[col][:1] in "=+-@" for x in rows[1:]), path)

    def test_each_export_is_one_audit_row_naming_the_rollout(self):
        self.rows("/projects/1/raid.csv"); self.rows("/projects/1/tasks.csv")
        got = {r[0]: (r[1], r[2]) for r in self.sql("SELECT action, resource_name, details FROM audit_logs WHERE action LIKE 'export_%'")}
        self.assertEqual(got["export_raid"], ("Alpha / Phase 2", "2 rows"))
        self.assertEqual(got["export_tasks"], ("Alpha / Phase 2", "2 rows"))

    def test_partners_and_customers_get_neither_and_a_stranger_gets_not_found(self):
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        ann = self._external_client("ann@acme.example")
        for path in ("raid", "tasks"):
            self.assertEqual(ann.get(f"/projects/1/{path}.csv").status_code, 403)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM audit_logs WHERE action IN ('export_raid', 'export_tasks')")[0][0], 0)
        self.assertEqual(self.c.get("/projects/99/raid.csv").status_code, 404)
        self.assertEqual(app_module.app.test_client().get("/projects/1/tasks.csv").status_code, 302)   # signed out: the sign-in page

    def test_a_viewer_who_may_read_the_rollout_may_download_it(self):
        self._make_user("viewer", "Viewer")
        v, _ = self._api_client("viewer", STRONG_PASSWORD)
        self.assertEqual(v.get("/projects/1/raid.csv").status_code, 200)
