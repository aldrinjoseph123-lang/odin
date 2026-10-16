"""v2.0.0 check round, security and data fixes (FXA): what an outsider reads
about the team's tasks, held summary items in the outbox, rule firings after
a failed request, reassigned asks, intake sources, pending intakes, form
answers, the calendar feed, repeating asks, hand-over, sign-in names and the
pending rollout's move. Run with: python -m unittest test_v2_fixes

Dates are relative to the workspace's today, in UTC: nothing here depends on
the weekday or the month."""
import json
from datetime import date, timedelta
from unittest.mock import patch

from flask import jsonify

from test_app import STRONG_PASSWORD, app_module, drain_outbox
from test_fix_logic import FixBase
from test_v2_deps import DepsBase
from test_v2_intake import DEAL, IntakeBase
from test_v2_notify import Base as NotifyBase
from test_v2_selfserve import SelfServeBase

J = {"Accept": "application/json"}


class OutsiderWaitsTestCase(DepsBase):
    """P1: a customer's task waits on an internal one; its title reaches them nowhere."""

    def setUp(self):
        super().setUp()
        self.new_project()
        self._set_policy(external_domains="vendor.example")
        self._invite(1, "cus@vendor.example", "Customer", "Cus")
        self.cid = self.sql("SELECT id FROM users WHERE email = 'cus@vendor.example'")[0][0]
        cur = next(s for s in self.client.get("/api/projects/1/plan").get_json()["stages"] if s["status"] == "current")
        before = date.fromisoformat(cur["forecast_end"])
        self.late = self.task("SECRET internal vendor escalation", due_date=self.day(-5))
        self.mine = self.task("Customer signs form", assignee_id=self.cid, due_date=(before + timedelta(days=1)).isoformat())
        self.edit(self.mine, waits_on=[self.late])
        self.c = self._external_client("cus@vendor.example")

    def current(self, client):
        return next(s for s in client.get("/api/projects/1/plan").get_json()["stages"] if s["status"] == "current")

    def test_the_plan_and_the_reports_drop_the_reason(self):
        self.assertIn("SECRET", self.current(self.client)["forecast_reason"])   # the team still reads why
        self.assertIsNone(self.current(self.c)["forecast_reason"])
        self.ctx()
        from db import get_db
        from services import report_data
        project = get_db().execute("SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.id = 1").fetchone()
        live = report_data.build(project, "customer")
        saved = report_data.customer_view(report_data.snapshot(project))
        for data in (live, saved):
            self.assertNotIn("SECRET", json.dumps(data))
            self.assertTrue(all(s["forecast_reason"] is None for s in data["stages"]))

    def test_flow_and_my_work_name_only_what_the_outsider_may_see(self):
        t = next(x for x in self.c.get("/api/projects/1/flow").get_json()["tasks"] if x["id"] == self.mine)
        self.assertEqual(t["waits_on"], [])
        self.assertEqual(t["blocked_by"], [{"id": 0, "title": "work the team has not finished yet", "late_by": 0}])
        mw = next(x for x in self.c.get("/api/my-work").get_json()["tasks"] if x["id"] == self.mine)
        self.assertEqual(mw["blocked_by"], t["blocked_by"])
        # staff still read the predecessor by name
        self.assertEqual(self.flow_task(self.mine)["blocked_by"][0]["title"], "SECRET internal vendor escalation")
        # a predecessor of their own keeps its name
        own = self.task("Customer sends logo", assignee_id=self.cid)
        self.edit(self.mine, waits_on=[self.late, own])
        t = next(x for x in self.c.get("/api/projects/1/flow").get_json()["tasks"] if x["id"] == self.mine)
        self.assertEqual(t["waits_on"], [own])
        self.assertEqual([w["title"] for w in t["blocked_by"]], ["Customer sends logo", "work the team has not finished yet"])

    def test_the_tick_refusal_is_generic(self):
        csrf = self.c.get("/api/session").get_json()["csrf"]
        r = self.c.post(f"/projects/1/tasks/{self.mine}/toggle", json={"done": True}, headers={"X-CSRF-Token": csrf, **J})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "This waits on work the team has not finished yet")
        self.assertEqual(self.sql("SELECT done FROM tasks WHERE id = ?", self.mine)[0][0], 0)


class HeldSummaryTestCase(NotifyBase):
    """P2: an item held for the daily summary is never sent by the worker, never a failure."""

    def test_the_worker_leaves_held_rows_alone(self):
        sam = self.user("sam")
        self.sql("UPDATE users SET email_summary = 'stage' WHERE id = ?", sam)
        self.notify([sam], "stage", 1, "Alpha moved", "<p>x</p>")
        [row] = self.outbox("held")
        self.assertIsNone(row["next_try_at"])
        # a row queued before the fix carries a time: the worker skips it by kind all the same
        self.sql("UPDATE outbox SET next_try_at = '2000-01-01T00:00:00' WHERE kind = 'held'")
        with patch("graph.send_mail", return_value=(True, None)) as mail:
            drain_outbox()
        [row] = self.outbox("held")
        self.assertEqual((row["attempts"], row["last_error"], row["sent_at"], mail.call_count), (0, None, None, 0))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE kind = 'ops'")[0][0], 0)


class RulesAfterFailureTestCase(FixBase):
    """P2: a firing never commits a request's half-done writes, and a 500 fires nothing."""

    def setUp(self):
        super().setUp()
        self.new_project(name="Globex EDR", client="Globex")
        r = self.client.post("/api/rules", json={"name": "Log it", "event": "rollout_created", "conditions": [],
                                                 "actions": [{"kind": "add_raid", "raid_kind": "issue", "title": "From the rule"}]})
        self.assertEqual(r.status_code, 200, r.get_json())

    def view(self, fail):
        def fake():
            from db import get_db
            from services import rules
            get_db().execute("UPDATE projects SET name = 'HALF' WHERE id = 1")   # written, never committed
            rules.fire("rollout_created", 1, {"source": "form"})
            if fail:
                raise RuntimeError("boom")
            return jsonify(ok=True)
        return patch.dict(app_module.app.view_functions, {"api_rules": fake})

    def counts(self):
        return (self.sql("SELECT name FROM projects WHERE id = 1")[0][0], self.sql("SELECT COUNT(*) FROM rule_runs")[0][0],
                self.sql("SELECT COUNT(*) FROM raid_items")[0][0])

    def test_a_500_fires_nothing_and_keeps_nothing(self):
        with self.view(True), patch.dict(app_module.app.config, {"PROPAGATE_EXCEPTIONS": False}), patch.object(app_module.app.logger, "error"):
            self.assertEqual(self.client.get("/api/rules").status_code, 500)
        self.assertEqual(self.counts(), ("Globex EDR", 0, 0))

    def test_a_firing_commits_only_its_own_writes(self):
        with self.view(False):
            self.assertEqual(self.client.get("/api/rules").status_code, 200)
        self.assertEqual(self.counts(), ("Globex EDR", 1, 1))


class ReassignedAskTestCase(SelfServeBase):
    """P2: a form or upload handed to someone else starts again; nobody reads another's answers."""

    def test_reassigning_clears_the_answers_and_reopens_it(self):
        tid = self.ask("form", questions=[{"label": "Admin password hint", "kind": "text"}])
        self.assertEqual(self.answer(self.ext("Customer"), tid, {"q1": "customer-secret"}).status_code, 200)
        self.assertEqual(self.done(tid), 1)
        r = self.client.post(f"/projects/1/tasks/{tid}/edit", json={"assignee_id": self.people["Contractor"]})
        self.assertEqual(r.status_code, 200, r.get_json())
        [a] = self.ext("Contractor").get("/api/projects/1/asks").get_json()["asks"]
        self.assertEqual((a["answers"], a["answered_by"], a["done"]), ([], None, False))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM task_answers WHERE task_id = ?", tid)[0][0], 0)
        self.assertEqual(self.audits("reset_ask"), 1)
        # a title edit keeps them
        tid2 = self.ask("form", questions=[{"label": "Seats", "kind": "number"}], role="Reseller")
        self.answer(self.ext("Reseller"), tid2, {"q1": "5"})
        self.client.post(f"/projects/1/tasks/{tid2}/edit", json={"title": "Seats, please"})
        self.assertEqual(self.done(tid2), 1)
        self.assertEqual(self.audits("reset_ask"), 1)

    def test_the_listing_shows_only_the_current_assignees_answers(self):
        tid = self.ask("form", questions=[{"label": "Hint", "kind": "text"}])
        self.answer(self.ext("Customer"), tid, {"q1": "customer-secret"})
        self.sql("UPDATE tasks SET assignee_id = ? WHERE id = ?", self.people["Contractor"], tid)   # moved by any other path
        [a] = self.ext("Contractor").get("/api/projects/1/asks").get_json()["asks"]
        self.assertEqual(a["answers"], [])

    def test_a_list_for_a_yes_no_answer_is_refused_not_a_500(self):
        tid = self.ask("form", questions=[{"label": "OK?", "kind": "yesno"}, {"label": "Tier", "kind": "choice", "choices": ["A", "B"]}])
        for bad in ({"q1": [], "q2": "A"}, {"q1": {"x": 1}, "q2": "A"}, {"q1": True, "q2": ["A"]}, {"q1": True, "q2": {}}):
            r = self.answer(self.ext("Customer"), tid, bad)
            self.assertEqual(r.status_code, 400, bad)


class IntakeFixesTestCase(IntakeBase):
    def test_a_deal_id_from_another_source_is_a_conflict_with_nothing_of_the_first(self):
        self.assertEqual(self.post(DEAL, name="crm-a").status_code, 201)
        self.assertEqual(self.post(DEAL).status_code, 200)   # the same source: its rollout again
        r = self.post({"client": "x", "name": "y", "deal_id": DEAL["deal_id"]}, token=self.token("crm-b"))
        self.assertEqual(r.status_code, 409)
        self.assertNotIn("rollout", r.get_json())
        self.assertNotIn("Branch firewalls", r.get_data(as_text=True))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 1)

    def test_a_pending_intake_takes_no_write_but_confirm_or_discard(self):
        pid = self.post(DEAL).get_json()["rollout"]["id"]
        self._set_policy(external_domains="vendor.example")
        tries = {
            "invite": self.client.post(f"/projects/{pid}/participants/invite", data={"email": "c@vendor.example", "name": "C", "role": "Customer"}, headers=J),
            "task": self.client.post(f"/projects/{pid}/tasks", json={"title": "Early"}),
            "signoff": self.client.post(f"/api/projects/{pid}/signoff", json={}),
            "report": self.client.post(f"/api/projects/{pid}/rollout-report", json={"summary": "x", "share": True}),
            "stage": self.client.post(f"/api/projects/{pid}/stage", json={"stage": "Delivery"}),
            "note": self.client.post(f"/projects/{pid}/note", data={"note": "hello"}, headers=J),
        }
        for what, r in tries.items():
            self.assertEqual(r.status_code, 400, what)
            self.assertIn("Confirm this intake first", r.get_json()["error"], what)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tasks WHERE project_id = ?", pid)[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM users WHERE email = 'c@vendor.example'")[0][0], 0)
        # staff still read it, and nobody is offered the move
        self.assertEqual(self.client.get(f"/api/projects/{pid}").status_code, 200)
        self.assertFalse(self.client.get(f"/api/projects/{pid}").get_json()["can"]["move"])
        self.assertFalse(self.client.get(f"/api/projects/{pid}/flow").get_json()["can_move"])
        # an outsider who is on it somehow does not see it
        self.new_project(name="Open one", client="C")
        self._invite(2, "c@vendor.example", "Customer", "C")
        uid = self.sql("SELECT id FROM users WHERE email = 'c@vendor.example'")[0][0]
        self.sql("INSERT INTO project_participants (project_id, user_id, role, added_at) VALUES (?, ?, 'Customer', datetime('now'))", pid, uid)
        self.assertEqual(self._external_client("c@vendor.example").get(f"/api/projects/{pid}").status_code, 404)
        # confirm still works, and then the rollout takes writes
        self.assertEqual(self.confirm(pid=pid).status_code, 200)
        self.assertEqual(self.client.post(f"/projects/{pid}/tasks", json={"title": "Now"}).status_code, 200)
        self.assertTrue(self.client.get(f"/api/projects/{pid}/flow").get_json()["can_move"])

    def test_a_pending_intake_may_be_discarded(self):
        pid = self.post(DEAL).get_json()["rollout"]["id"]
        self.assertIn(self.client.post(f"/projects/{pid}/delete", headers=J).status_code, (200, 302))
        self.assertIsNotNone(self.sql("SELECT deleted_at FROM projects WHERE id = ?", pid)[0][0])

    def test_hand_over_moves_a_pending_intake(self):
        mo = self._make_user("mo", "Member")
        self._set_policy(intake_owner=str(mo))
        pid = self.post(DEAL).get_json()["rollout"]["id"]
        self.assertEqual(self.row(pid)["owner_id"], mo)
        r = self.client.post(f"/users/{mo}/active", data={"active": "0", "handover_to": "1"}, headers=J)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.row(pid)["owner_id"], 1)
        self.assertEqual(self.row(pid)["intake_pending"], 1)


class SmallFixesTestCase(FixBase):
    def test_ics_escapes_a_lone_carriage_return(self):
        from services.ics import _event, _text
        self.assertEqual(_text("a\rb\r\nc\nd"), "a\\nb\\nc\\nd")
        self.assertNotIn("\r", "".join(_event("x", "2026-10-10", "a\rEND:VEVENT\rBEGIN:VEVENT", "d", "u", "s")))

    def test_unknown_feed_tokens_are_throttled_by_address_with_bounded_writes(self):
        self._set_policy(ics_feed_per_hour="5")
        anon = app_module.app.test_client()
        codes = [anon.get(f"/feeds/calendar/made-up-{i}.ics").status_code for i in range(9)]
        self.assertEqual(codes, [404] * 5 + [429] * 4)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM login_attempts WHERE username LIKE 'ics%'")[0][0], 5)
        # a real feed still opens
        self.ctx()
        from db import get_db
        from services import ics
        raw = ics.mint(1)
        get_db().commit()
        self.assertEqual(anon.get(f"/feeds/calendar/{raw}.ics").status_code, 200)

    def test_an_external_cannot_turn_a_feed_off(self):
        self.new_project()
        self._set_policy(external_domains="vendor.example")
        self._invite(1, "c@vendor.example", "Customer", "C")
        c = self._external_client("c@vendor.example")
        csrf = c.get("/api/session").get_json()["csrf"]
        self.assertEqual(c.post("/account/calendar/off", headers={"X-CSRF-Token": csrf, **J}).status_code, 403)
        self.assertEqual(self.audits("revoke_calendar_feed"), 0)

    def test_an_address_names_its_owner_over_a_legacy_username(self):
        self.sql("INSERT INTO users (username, password_hash, name, role, active, email) VALUES ('alice', 'x', 'Alice', 'Member', 1, 'shared@corp.example')")
        self.sql("INSERT INTO users (username, password_hash, name, role, active, email) VALUES ('shared@corp.example', 'x', 'Legacy', 'Member', 1, 'b@corp.example')")
        self.ctx()
        from routes.auth import _account_for
        for typed in ("shared@corp.example", "SHARED@corp.example", " shared@corp.example "):
            self.assertEqual(_account_for(typed)["username"], "alice", typed)
        self.assertEqual(_account_for("b@corp.example")["username"], "shared@corp.example")
        self.assertEqual(_account_for("alice")["username"], "alice")


class RepeatingAsksTestCase(SelfServeBase):
    def setUp(self):
        super().setUp()
        self._set_policy(timezone="UTC")
        self.today = date.today()

    def series(self, tid):
        return self.sql("SELECT id, done, kind, ask_category, ask_form FROM tasks WHERE id = ? OR recur_from IS NOT NULL ORDER BY id", tid)

    def test_the_next_occurrence_is_the_same_ask(self):
        tid = self.ask("form", recurrence="weekly", due_date=self.today.isoformat())
        self.assertEqual(self.client.post(f"/projects/1/tasks/{tid}/toggle", json={"done": True}).status_code, 200)
        first, nxt = self.series(tid)
        self.assertEqual((nxt["kind"], nxt["ask_form"], nxt["done"]), ("form", first["ask_form"], 0))
        up = self.ask("upload", recurrence="weekly", due_date=self.today.isoformat())
        self.client.post(f"/projects/1/tasks/{up}/toggle", json={"done": True})
        made = self.sql("SELECT kind, ask_category FROM tasks WHERE recur_from = ?", up)
        self.assertEqual([tuple(r) for r in made], [("upload", "Deliverable")])

    def test_a_neglected_repeating_task_does_not_pile_up(self):
        r = self.client.post("/projects/1/tasks", json={"title": "Weekly report", "recurrence": "weekly", "due_date": (self.today - timedelta(days=3)).isoformat()})
        first = r.get_json()["id"]
        self.ctx()
        from db import get_db
        from services.recurrence import run_recurring
        db = get_db()
        open_ = lambda: self.sql("SELECT COUNT(*) FROM tasks WHERE title = 'Weekly report' AND done = 0")[0][0]   # noqa: E731
        self.assertEqual(run_recurring(db, self.today), 1)
        for weeks in (2, 3, 5):   # nobody ticks anything for weeks
            run_recurring(db, self.today + timedelta(days=7 * weeks))
        self.assertEqual(open_(), 2, "the neglected one and one next occurrence, no more")
        self.sql("UPDATE tasks SET done = 1, done_at = datetime('now') WHERE id = ?", first)
        self.assertEqual(run_recurring(db, self.today + timedelta(days=7 * 6)), 1)   # the series moves on again
        self.assertEqual(open_(), 2)
