"""Odin 2.0, workstream 5: milestones and repeating tasks.
Run with: python -m unittest test_v2_milestones

The clock is frozen at TODAY for every module (FixBase.freeze_clock), and every
date in a test is written out, so nothing here depends on the weekday or the month of the day it runs."""
import json
import secrets
from datetime import date, timedelta
from unittest.mock import patch

import scheduler
from test_fix_logic import FixBase

TODAY = FixBase.NOW.date()
J = {"Accept": "application/json"}


def iso(n):
    return (TODAY + timedelta(days=n)).isoformat()


class MilestoneBase(FixBase):
    def setUp(self):
        super().setUp()
        self._set_policy(timezone="UTC", count_working_days="0")
        # policies.local_now, which every module's local_today reads: a module patched by name alone
        # (services.gates was missed) ran on the real day and failed once that passed TODAY + 3
        self.freeze_clock()

    def _csrf(self):
        with self.client.session_transaction() as sess:   # the test client adds the token to POSTs only
            return {"X-CSRF-Token": sess.setdefault("_csrf_token", secrets.token_urlsafe(32))}

    def put(self, url, json):
        return self.client.put(url, json=json, headers=self._csrf())

    def delete(self, url):
        return self.client.delete(url, headers=self._csrf())

    def add(self, name="Pilot live", day=None, pid=1, **fields):
        r = self.client.post(f"/api/projects/{pid}/milestones", json={"name": name, "date": day or iso(10), **fields})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["id"]

    def listed(self, client=None, pid=1):
        return (client or self.client).get(f"/api/projects/{pid}/milestones").get_json()

    def tick(self, tid, pid=1, done=True):
        r = self.client.post(f"/projects/{pid}/tasks/{tid}/toggle", json={"done": done})
        self.assertEqual(r.status_code, 200, r.get_json())

    def tasks(self, where="1 = 1"):
        with self.raw_db() as db:
            return db.execute(f"SELECT id, title, due_date, done, recurrence, recur_until, recur_from, recur_spawned, stage FROM tasks WHERE {where} ORDER BY id").fetchall()


class MilestoneCrudTestCase(MilestoneBase):
    def test_add_edit_reach_reopen_delete_each_audited(self):
        self.new_project()
        stage = self.stages()[1]
        mid = self.add("Pilot live", iso(10), stage=stage, customer_visible=True)
        d = self.listed()
        self.assertEqual([(m["name"], m["date"], m["stage"], m["customer_visible"], m["done"], m["missed"]) for m in d["items"]],
                         [("Pilot live", iso(10), stage, True, False, False)])
        self.assertTrue(d["can_edit"] and d["can_delete"])
        r = self.put(f"/api/projects/1/milestones/{mid}", json={"name": "Pilot go-live", "date": iso(12)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.put(f"/api/projects/1/milestones/{mid}", json={"done": True}).status_code, 200)
        first = self.tuples("SELECT done_at FROM milestones WHERE id = ?", mid)[0][0]
        self.assertTrue(first)
        self.put(f"/api/projects/1/milestones/{mid}", json={"done": True})   # still done: the first time stays
        self.assertEqual(self.tuples("SELECT done_at FROM milestones WHERE id = ?", mid)[0][0], first)
        self.put(f"/api/projects/1/milestones/{mid}", json={"done": False})
        self.assertIsNone(self.tuples("SELECT done_at FROM milestones WHERE id = ?", mid)[0][0])
        self.assertEqual(self.listed()["items"][0]["name"], "Pilot go-live")   # a done-only edit kept the rest
        self.assertEqual(self.delete(f"/api/projects/1/milestones/{mid}").status_code, 200)
        self.assertEqual(self.listed()["items"], [])
        self.assertEqual((self.audits("add_milestone"), self.audits("update_milestone"), self.audits("delete_milestone")), (1, 4, 1))
        said = [r[0] for r in self.tuples("SELECT details FROM audit_logs WHERE action = 'update_milestone' ORDER BY id")]
        self.assertTrue(any("reached" in s for s in said) and any("reopened" in s for s in said))

    def test_a_stage_renamed_carries_its_milestones(self):
        self.new_project()
        name = self.stages()[1]
        self.add("Pilot live", iso(10), stage=name)
        self.ctx()
        from db import get_db
        from services import stages as stage_ops
        sid = get_db().execute("SELECT id FROM project_stages WHERE project_id = 1 AND name = ?", (name,)).fetchone()[0]
        self.assertIsNone(stage_ops.rename_stage("project", 1, sid, "Discovery"))
        self.assertEqual(self.tuples("SELECT stage FROM milestones"), [("Discovery",)])

    def test_what_is_refused(self):
        self.new_project()
        post = lambda **b: self.client.post("/api/projects/1/milestones", json=b)   # noqa: E731
        self.assertIn("name", post(name=" ", date=iso(1)).get_json()["error"])
        self.assertEqual(post(name="x").status_code, 400)                                  # no date
        self.assertEqual(post(name="x", date="2026-02-31").status_code, 400)               # not a calendar day
        self.assertEqual(post(name="x", date=iso(1), stage="Nowhere").status_code, 400)    # not one of its stages
        self.assertEqual(post(name="x" * 201, date=iso(1)).status_code, 400)
        self.assertEqual(post(name="x", date=iso(1), customer_visible="maybe").status_code, 400)
        self.assertEqual(self.client.get("/api/projects/9/milestones").status_code, 404)
        self.assertEqual(self.put("/api/projects/1/milestones/99", json={"done": True}).status_code, 404)
        self.assertEqual(self.tuples("SELECT COUNT(*) FROM milestones")[0][0], 0)

    def test_a_coordinator_edits_the_project_manager_deletes(self):
        self.new_project()
        mid = self.add()
        _, c, h = self.member("co", pid=1)   # manages its tasks, does not manage the rollout
        self.assertEqual(c.put(f"/api/projects/1/milestones/{mid}", json={"done": True}, headers=h).status_code, 200)
        self.assertEqual(c.delete(f"/api/projects/1/milestones/{mid}", headers=h).status_code, 403)
        d = c.get("/api/projects/1/milestones").get_json()
        self.assertEqual((d["can_edit"], d["can_delete"]), (True, False))
        # a rollout it is not on: neither
        self.new_project(name="Other")
        self.assertEqual(c.post("/api/projects/2/milestones", json={"name": "x", "date": iso(1)}, headers=h).status_code, 403)


class MilestoneCutTestCase(MilestoneBase):
    """Hidden ones never reach an outsider, the customer report or the sign-off."""

    def setUp(self):
        super().setUp()
        self.new_project(name="Cut", client="Globex")
        self.add("Internal checkpoint", iso(5))
        self.add("Go-live", iso(20), customer_visible=True)
        done = self.add("Kick-off held", iso(-6), customer_visible=True)
        self.put(f"/api/projects/1/milestones/{done}", json={"done": True})
        self.add("Secret rehearsal", iso(-4))
        self._invite(1, "ann@globex.example", "Customer", "Ann")
        self.ann = self._external_client("ann@globex.example")

    def test_an_outsider_reads_only_the_ones_marked_for_the_customer(self):
        d = self.ann.get("/api/projects/1/milestones").get_json()
        self.assertEqual(sorted(m["name"] for m in d["items"]), ["Go-live", "Kick-off held"])
        self.assertEqual((d["can_edit"], d["can_delete"]), (False, False))
        self.assertNotIn("Secret", json.dumps(d))
        self.assertEqual(self.ann.post("/api/projects/1/milestones", json={"name": "x", "date": iso(1)}).status_code, 403)
        self.assertEqual(len(self.listed()["items"]), 4)   # staff see all four

    def test_the_calendar_and_the_dashboard_follow_the_cut(self):
        staff = self.client.get("/api/calendar?month=2026-10").get_json()["milestones"]
        self.assertEqual(sorted(m["name"] for m in staff), ["Go-live", "Internal checkpoint", "Kick-off held", "Secret rehearsal"])
        got = {m["name"]: (m["day"], m["done"], m["project"]) for m in staff}
        self.assertEqual(got["Go-live"], (iso(20), 0, "Cut"))
        self.assertEqual(got["Kick-off held"][1], 1)
        out = self.ann.get("/api/calendar?month=2026-10").get_json()["milestones"]
        self.assertEqual(sorted(m["name"] for m in out), ["Go-live", "Kick-off held"])
        self.assertEqual(self.client.get("/api/calendar?month=2026-01").get_json()["milestones"], [])   # a month with none
        tl = self.client.get("/api/dashboard").get_json()["data"]["timeline"]
        marks = next(r for r in tl if r["id"] == 1)["milestones"]
        self.assertEqual({m["name"]: (m["done"], m["missed"]) for m in marks}["Secret rehearsal"], (False, True))

    def test_the_customer_report_and_its_saved_copy_carry_only_the_visible_ones(self):
        r = self.client.get("/api/projects/1/rollout-report").get_json()["data"]
        self.assertEqual(len(r["project_milestones"]), 4)
        cu = self.client.get("/api/projects/1/rollout-report?audience=customer").get_json()["data"]
        self.assertEqual(sorted(m["name"] for m in cu["project_milestones"]), ["Go-live", "Kick-off held"])
        v = self.client.post("/api/projects/1/rollout-report", json={"summary": "On track."}).get_json()["version"]
        saved = self.client.get(f"/api/projects/1/rollout-report?v={v}").get_json()["data"]
        self.assertEqual(len(saved["project_milestones"]), 4)   # the internal snapshot keeps them all…
        seen = self.ann.get(f"/api/projects/1/rollout-report?v={v}").get_json()["data"]
        self.assertEqual(sorted(m["name"] for m in seen["project_milestones"]), ["Go-live", "Kick-off held"])   # …the customer's cut of it does not
        self.assertNotIn("Secret", json.dumps(seen))
        self.assertIn(b"Secret rehearsal", self.client.get("/projects/1/report.pdf").data)   # the team's copy lists all of them…
        for url in (f"/projects/1/report.pdf?audience=customer&v={v}", "/projects/1/report.pdf?audience=customer"):
            pdf = self.client.get(url).data
            self.assertIn(b"Go-live", pdf)
            self.assertNotIn(b"Secret rehearsal", pdf)   # …the customer's does not

    def test_the_project_managers_words_for_the_customer_do_not_name_a_hidden_milestone(self):
        self.ctx()
        from services.report_data import customer_words
        said = customer_words(1, {"summary": "The Secret rehearsal went well. Go-live is set for next week."})["summary"]
        self.assertEqual(said, "Go-live is set for next week.")

    def test_the_portfolio_row_counts_by_audience(self):
        row = lambda c: next(x for x in c.get("/api/reports/all").get_json()["rows"] if x["id"] == 1)["milestones"]   # noqa: E731
        self.assertEqual(row(self.client), {"total": 4, "done": 1, "missed": 1, "next": {"name": "Internal checkpoint", "date": iso(5)}})
        self.assertEqual(row(self.ann), {"total": 2, "done": 1, "missed": 0, "next": {"name": "Go-live", "date": iso(20)}})

    def test_the_signoff_draft_lists_the_visible_milestones_reached(self):
        self.ctx()
        from db import get_db
        from services import signoff
        project = get_db().execute("SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.id = 1").fetchone()
        delivered = signoff.draft(project)["delivered"]
        lines = [x for x in delivered if x.startswith("Milestone reached")]
        self.assertEqual(len(lines), 1)
        self.assertIn("Kick-off held", lines[0])
        self.assertNotIn("Secret rehearsal", " ".join(delivered))


class MilestoneMissedAlertTestCase(MilestoneBase):
    def sync(self):
        self.ctx()
        from db import get_db
        from services.alerts import build_alerts, sync_alerts_to_db
        rows = get_db().execute("SELECT * FROM projects WHERE deleted_at IS NULL").fetchall()
        sync_alerts_to_db(build_alerts(rows))

    def alerts(self):
        return self.tuples("SELECT resolved FROM alerts WHERE alert_type = 'milestone_missed' ORDER BY id")

    def test_raised_once_and_cleared_when_it_is_done(self):
        self.new_project()
        mid = self.add("Security review", iso(-1))
        self.add("Later one", iso(3))
        self.sync()
        self.sync()                                                          # a second pass raises nothing new
        self.assertEqual(self.alerts(), [(0,)])
        told = self.tuples("SELECT kind, title, link FROM notifications WHERE kind = 'milestone'")
        self.assertEqual(len(told), 1)
        self.assertIn("Milestone missed", told[0][1])
        self.assertEqual(told[0][2], "/projects/1#milestones")
        self.assertEqual(self.tuples("SELECT COUNT(*) FROM notifications WHERE kind = 'alert' AND title LIKE 'Milestone missed%'")[0][0], 0)
        self.put(f"/api/projects/1/milestones/{mid}", json={"done": True})
        self.sync()
        self.assertEqual(self.alerts(), [(1,)])                              # cleared, not deleted
        self.put(f"/api/projects/1/milestones/{mid}", json={"done": False})
        self.sync()
        self.assertEqual(self.alerts(), [(1,), (0,)])                        # reopened and still past: raised again

    def test_a_new_date_clears_it_and_the_grace_days_delay_it(self):
        self.new_project()
        mid = self.add("Security review", iso(-1))
        self.sync()
        self.assertEqual(self.alerts(), [(0,)])
        self.put(f"/api/projects/1/milestones/{mid}", json={"date": iso(7)})
        self.sync()
        self.assertEqual(self.alerts(), [(1,)])
        self.sql("UPDATE alert_type_settings SET threshold_days = 3 WHERE alert_type = 'milestone_missed'")
        self.put(f"/api/projects/1/milestones/{mid}", json={"date": iso(-2)})
        self.sync()
        self.assertEqual(self.alerts(), [(1,)])                              # two days late, three days' grace
        self.put(f"/api/projects/1/milestones/{mid}", json={"date": iso(-4)})
        self.sync()
        self.assertEqual(self.alerts(), [(1,), (0,)])

    def test_the_type_is_in_the_settings_and_the_digest(self):
        self.assertEqual(self.tuples("SELECT severity, threshold_days, notify_inapp FROM alert_type_settings WHERE alert_type = 'milestone_missed'"), [("warning", 0, 1)])
        keys = [a["key"] for a in self.client.get("/api/settings").get_json()["alerts"]]
        self.assertIn("milestone_missed", keys)
        self.assertIn("milestone", {k["key"] for k in self.client.get("/api/account").get_json()["email_kinds"]})
        self.new_project()
        self.add("Security review", iso(-1))
        import send_daily_alerts
        self.ctx()
        from db import get_db
        from services.alerts import build_alerts
        alerts = build_alerts(get_db().execute("SELECT * FROM projects").fetchall())
        self.assertIn("Milestones missed (1)", send_daily_alerts._format_alerts_html(alerts))


class RepeatTestCase(MilestoneBase):
    def test_the_dates(self):
        from services.recurrence import add_months, next_due
        d = date
        self.assertEqual(next_due(d(2026, 10, 14), "weekly", d(2026, 10, 14)), d(2026, 10, 21))
        self.assertEqual(next_due(d(2026, 10, 14), "fortnightly", d(2026, 10, 14)), d(2026, 10, 28))
        self.assertEqual(next_due(d(2026, 1, 31), "monthly", d(2026, 1, 31)), d(2026, 2, 28))       # clamped to the month's end
        self.assertEqual(next_due(d(2026, 1, 31), "monthly", d(2026, 2, 1)), d(2026, 2, 28))
        self.assertEqual(next_due(d(2026, 1, 31), "monthly", d(2026, 3, 1)), d(2026, 3, 31))        # steps count from the 31st, not from 28 Feb
        self.assertEqual(add_months(d(2026, 12, 15), 1), d(2027, 1, 15))
        # ticked weeks late: the next one is not already in the past
        self.assertEqual(next_due(d(2026, 9, 1), "weekly", TODAY), d(2026, 9, 1) + timedelta(days=49))

    def test_a_tick_makes_exactly_one_next_and_it_carries_the_rest(self):
        self.new_project()
        uid = self._make_user("eng", "Member")
        t = self.task("Weekly call", due_date=iso(0), recurrence="weekly", assignee_id=uid, estimate_hours=2)
        self.assertEqual(len(self.tasks()), 1)
        self.tick(t)
        rows = self.tasks()
        self.assertEqual(len(rows), 2)
        parent, child = rows
        self.assertEqual((child["title"], child["due_date"], child["done"], child["recurrence"], child["recur_from"]), ("Weekly call", iso(7), 0, "weekly", t))
        self.assertEqual(parent["recur_spawned"], 1)
        self.assertEqual(self.tuples("SELECT assignee_id, estimate_hours, created_by FROM tasks WHERE id = ?", child["id"])[0], (uid, 2.0, "Odin (repeats)"))
        self.tick(t, done=False)
        self.tick(t)                                                         # untick and tick again: still one
        from services.recurrence import run_recurring
        self.ctx()
        self.assertEqual(run_recurring(today=TODAY), 0)
        self.assertEqual(len(self.tasks()), 2)
        self.assertEqual(self.audits("repeat_task"), 1)

    def test_a_pass_makes_the_next_when_the_due_date_passes_and_never_twice(self):
        self.new_project()
        late = self.task("Backup check", due_date=iso(-1), recurrence="weekly")
        today_ = self.task("Due today", due_date=iso(0), recurrence="weekly")
        ahead = self.task("Not yet", due_date=iso(3), recurrence="weekly")
        plain = self.task("No repeat", due_date=iso(-5))
        self.ctx()
        from db import get_db
        from services.recurrence import run_recurring
        self.assertEqual(run_recurring(get_db(), TODAY), 1)                  # only the one past its day
        self.assertEqual(run_recurring(get_db(), TODAY), 0)
        made = self.tasks("recur_from IS NOT NULL")
        self.assertEqual([(m["recur_from"], m["due_date"]) for m in made], [(late, iso(6))])
        self.assertEqual({r["id"] for r in self.tasks("recur_spawned = 0")} - {m["id"] for m in made}, {today_, ahead, plain})
        self.assertEqual(self.audits("repeat_task"), 1)
        # and a task ticked by another route (the customer's form, say) is found by the pass
        self.sql("UPDATE tasks SET done = 1 WHERE id = ?", ahead)
        self.assertEqual(run_recurring(get_db(), TODAY), 1)
        self.assertEqual(self.tuples("SELECT due_date FROM tasks WHERE recur_from = ?", ahead), [(iso(10),)])

    def test_the_nightly_housekeeping_runs_the_pass(self):
        self.new_project()
        self.task("Backup check", due_date=iso(-1), recurrence="fortnightly")
        with patch("scheduler.due_jobs", return_value=["housekeeping"]), patch("services.retention.run_audit_retention", return_value=(0, None)):
            scheduler.run_due()
        self.assertEqual(self.tuples("SELECT due_date FROM tasks WHERE recur_from IS NOT NULL"), [(iso(13),)])
        self.assertEqual(self.tuples("SELECT username FROM audit_logs WHERE action = 'repeat_task'"), [("scheduler",)])

    def test_it_stops_at_the_until_date(self):
        self.new_project()
        t = self.task("Status call", due_date=iso(0), recurrence="weekly", recur_until=iso(14))
        self.tick(t)
        second = self.tasks("recur_from IS NOT NULL")[0]
        self.assertEqual((second["due_date"], second["recur_until"]), (iso(7), iso(14)))
        self.tick(second["id"])
        third = self.tasks("recur_from = %d" % second["id"])[0]
        self.assertEqual(third["due_date"], iso(14))                         # on the last day is still in
        self.tick(third["id"])
        self.assertEqual(len(self.tasks()), 3)                               # iso(21) is past it: nothing more
        self.assertEqual(self.tuples("SELECT recur_spawned FROM tasks WHERE id = ?", third["id"]), [(1,)])

    def test_until_the_stage_is_done(self):
        self.new_project()
        names = self.stages()
        t = self.task("Weekly sync", due_date=iso(0), recurrence="weekly", recur_until="stage")
        self.assertEqual(self.tasks()[0]["stage"], names[0])                 # pinned to the stage it was made in
        self.tick(t)
        child = self.tasks("recur_from IS NOT NULL")[0]
        self.assertEqual((child["stage"], child["recur_until"]), (names[0], "stage"))
        self.sql("UPDATE projects SET stage = ? WHERE id = 1", names[1])     # the rollout moves on: that stage is done
        self.tick(child["id"])
        self.assertEqual(len(self.tasks()), 2)
        # a task of the current stage goes on repeating
        other = self.task("Daily huddle", due_date=iso(1), recurrence="weekly", recur_until="stage")
        self.assertEqual(self.tasks("id = %d" % other)[0]["stage"], names[1])
        self.tick(other)
        self.assertEqual(len(self.tasks("recur_from = %d" % other)), 1)

    def test_a_repeating_task_never_holds_a_stage_gate(self):
        self.new_project()
        names = self.stages()
        self.sql("UPDATE project_stages SET gate_tasks = 1 WHERE project_id = 1 AND name = ?", names[0])
        self.task("Weekly sync", due_date=iso(3), recurrence="weekly", recur_until="stage")
        self.ctx()
        from db import get_db
        from services import gates
        project = get_db().execute("SELECT * FROM projects WHERE id = 1").fetchone()
        self.assertEqual(gates.blocked(project, names[1]), [])
        self.task("One-off")
        self.assertEqual([r["count"] for r in gates.blocked(project, names[1])], [1])   # the plain open task still holds it

    def test_a_closed_rollout_repeats_nothing(self):
        self.new_project()
        t = self.task("Weekly call", due_date=iso(0), recurrence="weekly")
        self.sql("UPDATE projects SET stage = ? WHERE id = 1", self.stages()[-1])
        self.tick(t)
        self.assertEqual(len(self.tasks()), 1)

    def test_the_form_rules(self):
        self.new_project()
        add = lambda **b: self.client.post("/projects/1/tasks", json={"title": "T", **b})   # noqa: E731
        self.assertIn("due date", add(recurrence="weekly").get_json()["error"])
        self.assertIn("weekly, fortnightly or monthly", add(due_date=iso(1), recurrence="daily").get_json()["error"])
        self.assertIn("on or after the due date", add(due_date=iso(5), recurrence="weekly", recur_until=iso(2)).get_json()["error"])
        self.assertEqual(add(due_date=iso(5), recurrence="weekly", recur_until="soon").status_code, 400)
        self.assertEqual(add(due_date=iso(5), recurrence=["weekly"]).status_code, 400)
        self.assertEqual(self.tasks(), [])
        # an edit that sends neither keeps the repeat; "" turns it off; a due date cannot be cleared under it
        t = self.task("Weekly call", due_date=iso(5), recurrence="monthly", recur_until=iso(100))
        edit = lambda **b: self.client.post(f"/projects/1/tasks/{t}/edit", json=b)   # noqa: E731
        self.assertEqual(edit(title="Monthly call").status_code, 200)
        self.assertEqual(self.tasks()[0]["recurrence"], "monthly")
        self.assertEqual(edit(due_date="").status_code, 400)
        self.assertEqual(edit(recurrence="fortnightly", recur_until="").status_code, 200)
        self.assertEqual((self.tasks()[0]["recurrence"], self.tasks()[0]["recur_until"]), ("fortnightly", None))
        self.assertEqual(edit(recurrence="").status_code, 200)
        self.assertEqual((self.tasks()[0]["recurrence"], self.tasks()[0]["recur_until"]), (None, None))
        flow = self.client.get("/api/projects/1/flow").get_json()["tasks"][0]
        self.assertEqual((flow["recurrence"], flow["recur_until"]), (None, None))
        self.assertEqual(edit(recurrence="weekly").status_code, 200)
        self.assertEqual(self.client.get("/api/projects/1/flow").get_json()["tasks"][0]["recurrence"], "weekly")

    def test_a_deleted_rollout_takes_its_milestones_and_a_reset_wipes_them(self):
        self.new_project()
        self.add()
        import reset_data
        self.assertIn("milestones", reset_data.WIPE_TABLES)
        self.sql("UPDATE projects SET deleted_at = '2000-01-01T00:00:00' WHERE id = 1")
        self.ctx()
        from db import cleanup_soft_deletes, get_db
        cleanup_soft_deletes(get_db())
        self.assertEqual(self.tuples("SELECT COUNT(*) FROM milestones")[0][0], 0)
