"""v1.8.0 small server leftovers (review 14 Oct 2026: P3-38 undo of a done task,
P3-4 audit details, notify error, My work can_edit, the PDF opening month).
Run with: python -m unittest test_v18_leftovers"""
from datetime import date, datetime

import test_app
from test_app import STRONG_PASSWORD
from test_fix_logic import FixBase


class LeftoversTestCase(FixBase):
    def test_undo_of_a_deleted_done_task_keeps_it_done(self):
        self.new_project(name="P", client="C")
        self.client.post("/projects/1/tasks", json={"title": "Back", "done": True, "done_at": "2026-10-01T09:30:00"})
        self.client.post("/projects/1/tasks", json={"title": "Open"})
        self.client.post("/projects/1/tasks", json={"title": "Junk", "done": True, "done_at": "yesterday"})   # unreadable: now
        rows = {r["title"]: r for r in self.sql("SELECT title, done, done_at FROM tasks")}
        self.assertEqual((rows["Back"]["done"], rows["Back"]["done_at"]), (1, "2026-10-01T09:30:00"))
        self.assertEqual((rows["Open"]["done"], rows["Open"]["done_at"]), (0, None))
        self.assertEqual(rows["Junk"]["done"], 1); self.assertTrue(rows["Junk"]["done_at"].startswith(str(datetime.utcnow().year)))
        self.assertEqual({t["title"]: t["done_at"] for t in self.client.get("/api/projects/1/flow").get_json()["tasks"]}["Back"], "2026-10-01T09:30:00")

    def test_notify_with_no_message_says_so(self):
        pm = self._make_user("pm", "Member")
        csrf = self.client.get("/api/session").get_json()["csrf"]
        r = self.client.post(f"/api/people/{pm}/notify", json={"message": "  "}, headers={"X-CSRF-Token": csrf})
        self.assertEqual((r.status_code, r.get_json()), (400, {"error": "Write a message first"}))

    def test_my_work_says_which_tasks_the_person_may_redate(self):
        self.new_project(name="Mine", client="C")
        self.new_project(name="Managed", client="C")
        pm = self._make_user("pm", "Member")
        with self.raw_db() as db:
            for pid, role in ((1, "Sales"), (2, "Project manager")):
                db.execute("INSERT INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, ?, 1, datetime('now'))", (pid, pm, role))
            db.commit()
        for pid in (1, 2):
            self.client.post(f"/projects/{pid}/tasks", json={"title": f"On {pid}", "assignee_id": pm, "due_date": "2030-01-01"})
        c, _ = self._api_client("pm", STRONG_PASSWORD)
        can = {t["title"]: t["can_edit"] for t in c.get("/api/my-work").get_json()["tasks"]}
        self.assertEqual(can, {"On 1": False, "On 2": True})

    def test_audit_details_are_capped_and_cleaned(self):
        from services.audit import DETAILS_MAX
        self.new_project(name="P", client="C")
        self.client.post("/projects/1/tasks", json={"title": "x"})
        self.ctx()
        from services.audit import audit_log
        from flask import session
        session["user_id"], session["user_name"] = 1, "admin"
        audit_log("probe", details="a\nb\x1b[31m" + "z" * 5000)
        audit_log("probe_none")
        d = self.sql("SELECT details FROM audit_logs WHERE action = 'probe' ")[0][0]
        self.assertEqual(len(d), DETAILS_MAX); self.assertTrue(d.endswith("…"))
        self.assertTrue(d.startswith("a b [31m"))
        self.assertIsNone(self.sql("SELECT details FROM audit_logs WHERE action = 'probe_none'")[0][0])

    def test_pdf_names_the_opening_month(self):
        from datetime import timedelta
        from services.report_pdf import _opening_month
        t1 = date(2026, 12, 31)
        self.assertEqual(_opening_month(date(2026, 10, 3), t1), date(2026, 10, 3))   # the 1st of next month is 28 d in
        self.assertIsNone(_opening_month(date(2026, 10, 30), t1 + timedelta(days=0)))   # Nov 1 is 2 d in: that tick names it
        self.assertIsNone(_opening_month(date(2026, 10, 1), t1))                        # starts on the 1st
