"""Odin 2.0, workstream 6: automations (services/rules.py, routes/rules.py).
Run with: python -m unittest test_v2_rules

The clock is frozen: the rules' own clock (services.rules._now) and the days
the alert pass and the rules read (local_today) stand at TODAY, and every date
in a test is written relative to it, so nothing depends on the weekday or the
month of the day it runs."""
import io
import json
import secrets
from datetime import timedelta
from unittest.mock import patch

import scheduler
from test_app import STRONG_PASSWORD, app_module
from test_fix_logic import FixBase

NOW = FixBase.NOW
TODAY = NOW.date()
J = {"Accept": "application/json"}


def iso(n):
    return (TODAY + timedelta(days=n)).isoformat()


class RulesBase(FixBase):
    def setUp(self):
        super().setUp()
        self._set_policy(timezone="UTC", count_working_days="0")
        self.freeze_clock()   # local_today in every module, not only the ones a test names
        p = patch("services.rules._now", return_value=NOW)
        p.start()
        self.addCleanup(p.stop)
        self.new_project(name="Globex EDR", client="Globex")
        self.co = self._make_user("co", "Member")   # a coordinator on the rollout: who the rules tell
        self.sql("INSERT INTO project_participants (project_id, user_id, role, added_at) VALUES (1, ?, 'Coordinator', datetime('now'))", self.co)

    def _csrf(self):
        with self.client.session_transaction() as sess:   # the test client adds the token to POSTs only
            return {"X-CSRF-Token": sess.setdefault("_csrf_token", secrets.token_urlsafe(32))}

    def rule(self, event="stage_entered", actions=None, conditions=(), name="Tell the team", **extra):
        body = {"name": name, "event": event, "conditions": list(conditions),
                "actions": actions or [{"kind": "notify", "user_ids": [self.co], "email": False}], **extra}
        r = self.client.post("/api/rules", json=body)
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["id"]

    def move(self, stage, pid=1, client=None):
        r = (client or self.client).post(f"/api/projects/{pid}/stage", json={"stage": stage})
        self.assertEqual(r.status_code, 200, r.get_json())

    def runs(self, rid=None):
        if rid is None:
            return self.sql("SELECT COUNT(*) FROM rule_runs")[0][0]
        return self.client.get(f"/api/rules/{rid}/runs").get_json()["runs"]

    def told(self, uid=None):
        return self.sql("SELECT COUNT(*) FROM notifications WHERE kind = 'automation' AND user_id = ?", uid or self.co)[0][0]

    def field(self, name="Region", kind="choice", choices=("UAE", "KSA")):
        r = self.client.post("/api/fields", json={"name": name, "kind": kind, "choices": list(choices)})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["id"]

    def set_values(self, values, pid=1):
        r = self.client.put(f"/api/projects/{pid}/fields", json={"values": values}, headers=self._csrf())
        self.assertEqual(r.status_code, 200, r.get_json())

    def customer(self, email="cust@globex.example"):
        self._invite(1, email, "Customer", "Cust")
        return self.sql("SELECT id FROM users WHERE email = ?", email)[0][0], self._external_client(email)


class TriggersTestCase(RulesBase):
    def test_a_rollout_created_from_the_form_and_from_the_crm(self):
        # a CRM intake fires when staff confirm it, so the rule reaches the confirmed project manager,
        # never the placeholder owner of the pending intake (the user's call, 18 Oct 2026)
        rid = self.rule("rollout_created", actions=[{"kind": "notify", "roles": ["Project manager"], "email": False}])
        self.new_project(name="Initech SIEM", client="Initech")
        token = self.client.post("/settings/api-tokens", data={"name": "crm", "days": "30", "scope": "create"}, headers=J).get_json()["token"]
        r = app_module.app.test_client().post("/api/v1/intake", json={"client": "Hooli", "name": "SD-WAN", "deal_id": "D-1"},
                                              headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual([x["what"] for x in self.runs(rid)], ["Rollout created"])   # the pending intake fires nothing yet
        pid = self.sql("SELECT id FROM projects WHERE intake_pending = 1")[0][0]
        pm, pm_client, h = self.member("pm")   # a Member confirms it and so becomes its project manager
        done = pm_client.post(f"/projects/{pid}/intake/confirm", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO"), "po.pdf")},
                              headers=h, content_type="multipart/form-data")
        self.assertEqual(done.status_code, 200, done.get_json())
        self.assertEqual(self.sql("SELECT owner_id FROM projects WHERE id = ?", pid)[0][0], pm)
        self.assertEqual([x["what"] for x in self.runs(rid)], ["Rollout created from crm", "Rollout created"])
        self.assertEqual(self.runs(rid)[0]["actions"][0]["said"], "nobody to tell (the roles are empty, or only the person who did it)")
        self.assertEqual(self.told(1), 0)   # the placeholder owner (the first admin) is told nothing about the intake

    def test_a_stage_entered_fires_once_per_move(self):
        stages = self.stages()
        rid = self.rule(conditions=[{"kind": "stage", "value": stages[2]}])
        self.move(stages[1])
        self.assertEqual(self.runs(), 0)
        self.move(stages[2])
        run = self.runs(rid)
        self.assertEqual([(x["what"], x["ok"], x["project"]) for x in run], [(f"Entered {stages[2]}", True, "Globex EDR")])
        self.assertEqual(run[0]["actions"], [{"kind": "notify", "ok": True, "said": "told 1 person"}])
        self.assertEqual((self.told(), self.audits("rule_fired")), (1, 1))
        self.assertEqual(self.tuples("SELECT title, link FROM notifications WHERE kind = 'automation'")[0], ("Tell the team: Globex EDR", "/projects/1"))

    def test_a_document_uploaded_in_its_category(self):
        rid = self.rule("document_uploaded", event_config={"category": "Deliverable"})
        for category in ("Client PO", "Deliverable"):
            r = self.client.post("/projects/1/documents", data={"file": (io.BytesIO(b"%PDF-1.4 x"), "design.pdf"), "category": category}, headers=J)
            self.assertEqual(r.status_code, 200)
        self.assertEqual([x["what"] for x in self.runs(rid)], ["Document uploaded: design.pdf (Deliverable)"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM documents")[0][0], 3)   # the PO at creation fired nothing either

    def test_a_field_set_to_a_value(self):
        fid = self.field()
        rid = self.rule("field_set", event_config={"field_id": fid, "value": "KSA"})
        self.set_values({fid: "UAE"})
        self.assertEqual(self.runs(), 0)
        self.set_values({fid: "KSA"})
        self.set_values({fid: "KSA"})   # unchanged: no firing
        self.assertEqual([x["what"] for x in self.runs(rid)], ["Region set to KSA"])
        self.rule("field_set", name="Any region", event_config={"field_id": fid})   # no value: any value
        self.set_values({fid: "UAE"})
        self.assertEqual(self.runs(), 2)

    def test_the_customer_declines_a_stage(self):
        stages = self.stages()
        self.sql("UPDATE projects SET customer_approval = 1")
        _, cust = self.customer()
        rid = self.rule("stage_declined")
        self.move(stages[1])
        aid = self.sql("SELECT id FROM stage_approvals")[0][0]
        self.assertEqual(self.runs(), 0)
        r = cust.post(f"/api/projects/1/approvals/{aid}", json={"decision": "declined", "comment": "Not yet"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual([x["what"] for x in self.runs(rid)], [f"Customer declined {stages[1]}"])

    def test_an_ask_completed_by_answering_or_ticking(self):
        uid, cust = self.customer()
        rid = self.rule("ask_completed")
        form = self.client.post("/projects/1/tasks", json={"title": "Seats", "assignee_id": uid, "kind": "form",
                                                           "questions": [{"label": "How many seats", "kind": "number"}]}).get_json()["id"]
        tick = self.client.post("/projects/1/tasks", json={"title": "Open the firewall", "assignee_id": uid}).get_json()["id"]
        staff = self.client.post("/projects/1/tasks", json={"title": "Internal work", "assignee_id": self.co}).get_json()["id"]
        self.assertEqual(cust.post(f"/api/projects/1/asks/{form}/answers", json={"answers": {"q1": "40"}}).status_code, 200)
        self.assertEqual(cust.post(f"/projects/1/tasks/{tick}/toggle", json={"done": True}).status_code, 200)
        self.assertEqual(self.client.post(f"/projects/1/tasks/{staff}/toggle", json={"done": True}).status_code, 200)   # not an ask
        self.assertEqual([x["what"] for x in self.runs(rid)], ["Ask completed: Open the firewall", "Ask completed: Seats"])

    def test_what_time_brings_fires_once_and_never_for_the_past(self):
        """The alert pass: an overdue task, a missed milestone, a stage over its SLA. Each
        fires once per rule, and only for what arose after the rule was made."""
        tasks = self.rule("task_overdue", name="Late task")
        miles = self.rule("milestone_missed", name="Missed")
        sla = self.rule("stage_sla_breached", name="Over SLA")
        for title, due in (("Yesterday's", iso(-1)), ("Last week's", iso(-5)), ("Tomorrow's", iso(1))):
            self.assertEqual(self.client.post("/projects/1/tasks", json={"title": title, "due_date": due}).status_code, 200)
        for name, day in (("Pilot live", iso(-1)), ("Design signed", iso(-6))):
            self.assertEqual(self.client.post("/api/projects/1/milestones", json={"name": name, "date": day}).status_code, 200)
        self.sql("UPDATE project_stages SET sla_days = 1 WHERE project_id = 1")
        self.sql("UPDATE projects SET stage_entered_at = ?", self.now(days=-10).isoformat())
        scheduler.sync_alerts()
        scheduler.sync_alerts()   # the next quarter hour: nothing again
        self.assertEqual([x["what"] for x in self.runs(tasks)], [f"Task overdue: Yesterday's (due {iso(-1)})"])
        self.assertEqual([x["what"] for x in self.runs(miles)], [f"Milestone missed: Pilot live ({iso(-1)})"])
        self.assertEqual([x["what"] for x in self.runs(sla)], [f"Over the SLA in {self.stages()[0]}"])
        self.assertEqual(self.told(), 3)

    def test_old_overdue_tasks_that_already_fired_never_crowd_out_a_new_one(self):
        """The scan's cap counts firings, and what already ran is not a candidate again."""
        rid = self.rule("task_overdue", name="Late task")
        self.sql("UPDATE rules SET armed_at = ?", iso(-30))
        for n in range(3):
            self.client.post("/projects/1/tasks", json={"title": f"Old {n}", "due_date": iso(-10 + n)})
        with patch("services.rules.SCAN_MAX", 3):
            scheduler.sync_alerts()
            self.assertEqual(len(self.runs(rid)), 3)
            self.client.post("/projects/1/tasks", json={"title": "Fresh", "due_date": iso(-1)})
            scheduler.sync_alerts()
        self.assertEqual(len(self.runs(rid)), 4)
        self.assertIn("Fresh", self.runs(rid)[0]["what"])

    def test_a_breach_with_its_alert_off_dates_from_the_sla_not_today(self):
        """With the SLA alert off there is no alert row to date the breach: it is the day the SLA ran
        out, so a breach older than the run log is never fired again once its run is trimmed."""
        sla = self.rule("stage_sla_breached", name="Over SLA")
        self.sql("UPDATE rules SET armed_at = ?", iso(-200))
        self.sql("UPDATE project_stages SET sla_days = 1 WHERE project_id = 1")
        self.sql("UPDATE projects SET stage_entered_at = ?", self.now(days=-101).isoformat())
        self.ctx()
        from db import get_db
        from services import rules
        p = get_db().execute("SELECT * FROM projects WHERE id = 1").fetchone()
        rules.scan({"stage_sla_breach": [p]})
        self.assertEqual(self.runs(sla), [])
        self.sql("UPDATE projects SET stage_entered_at = ?", self.now(days=-5).isoformat())
        rules.scan({"stage_sla_breach": [get_db().execute("SELECT * FROM projects WHERE id = 1").fetchone()]})
        self.assertEqual(len(self.runs(sla)), 1)


class ConditionsTestCase(RulesBase):
    def test_each_condition_must_hold(self):
        stages = self.stages()
        fid = self.field()
        self.set_values({fid: "UAE"})
        cases = {
            "stage yes": {"kind": "stage", "value": stages[1]}, "stage no": {"kind": "stage", "value": stages[3]},
            "mode yes": {"kind": "delivery_mode", "value": "Distribution/MSSP"}, "mode no": {"kind": "delivery_mode", "value": "Outsourced"},
            "field yes": {"kind": "field", "field_id": fid, "value": "UAE"}, "field no": {"kind": "field", "field_id": fid, "value": "KSA"},
            "client yes": {"kind": "client", "value": " globex "}, "client no": {"kind": "client", "value": "Initech"},
        }
        ids = {name: self.rule(name=name, conditions=[c]) for name, c in cases.items()}
        both = self.rule(name="both", conditions=[cases["stage yes"], cases["client no"]])   # all must hold
        self.move(stages[1])
        ran = {r[0] for r in self.sql("SELECT rule_id FROM rule_runs")}
        self.assertEqual({n for n, i in ids.items() if i in ran}, {"stage yes", "mode yes", "field yes", "client yes"})
        self.assertNotIn(both, ran)


class ActionsTestCase(RulesBase):
    def test_notify_reaches_staff_by_role_and_by_name_never_the_customer(self):
        other = self._make_user("ops", "Viewer")
        cust, _ = self.customer()
        self.rule(actions=[{"kind": "notify", "roles": ["Project manager", "Coordinator"], "user_ids": [other], "email": True}])
        self.move(self.stages()[1])
        got = {r[0] for r in self.sql("SELECT user_id FROM notifications WHERE kind = 'automation'")}
        self.assertEqual(got, {self.co, other})   # the admin moved it (and is told nothing of their own act); never the customer
        self.assertNotIn(cust, got)
        r = self.client.post("/api/rules", json={"name": "x", "event": "stage_entered", "actions": [{"kind": "notify", "roles": ["Customer"]}]})
        self.assertIn("never reach the customer", r.get_json()["error"])
        r = self.client.post("/api/rules", json={"name": "x", "event": "stage_entered", "actions": [{"kind": "notify", "user_ids": [cust]}]})
        self.assertEqual(r.status_code, 400)

    def test_add_a_task_from_a_template_task(self):
        self.ctx()
        from services import template_tasks
        tid, stage = self.sql("SELECT s.template_id, s.id FROM stage_template_stages s ORDER BY s.position LIMIT 1")[0]
        template_tasks.save(tid, [{"key": "a", "stage_id": stage, "title": "Book the change window", "role": "Coordinator", "offset_days": 2, "estimate_hours": 3},
                                  {"key": "b", "stage_id": stage, "title": "Customer sends the export", "role": "Customer", "offset_days": 0}])
        self.customer()
        a, b = [r[0] for r in self.sql("SELECT id FROM template_tasks ORDER BY id")]
        self.rule(actions=[{"kind": "add_task", "template_task_id": a}, {"kind": "add_task", "template_task_id": b}])
        self.move(self.stages()[1])
        rows = self.tuples("SELECT title, assignee_id, due_date, estimate_hours, created_by FROM tasks WHERE created_by LIKE 'Automation:%' ORDER BY id")
        self.assertEqual(rows, [("Book the change window", self.co, iso(2), 3.0, "Automation: Tell the team"),
                                ("Customer sends the export", None, iso(0), None, "Automation: Tell the team")])   # never the customer's

    def test_editing_the_template_tasks_keeps_the_rules_pointing_at_them(self):
        """A save keeps the id of every task it was sent back (the editor's key), so an add_task
        rule still finds it; only a task left out goes."""
        self.ctx()
        from services import template_tasks
        tid, stage = self.sql("SELECT s.template_id, s.id FROM stage_template_stages s ORDER BY s.position LIMIT 1")[0]
        template_tasks.save(tid, [{"key": "a", "stage_id": stage, "title": "Book the window", "offset_days": 2},
                                  {"key": "b", "stage_id": stage, "title": "Old step", "offset_days": 0}])
        a, b = [r[0] for r in self.sql("SELECT id FROM template_tasks ORDER BY id")]
        rid = self.rule(actions=[{"kind": "add_task", "template_task_id": a}])
        template_tasks.save(tid, [{"key": "new-1", "stage_id": stage, "title": "First step", "offset_days": 0},
                                  {"key": str(a), "stage_id": stage, "title": "Book the change window", "offset_days": 3, "waits_on": "new-1"}])
        rows = self.tuples("SELECT id, title, waits_on_id FROM template_tasks ORDER BY position")
        self.assertEqual([r[1] for r in rows], ["First step", "Book the change window"])
        self.assertEqual(rows[1][0], a)                      # kept its id
        self.assertEqual(rows[1][2], rows[0][0])             # and waits on the new one
        self.assertNotIn(b, [r[0] for r in rows])            # the one left out is gone
        self.move(self.stages()[1])
        self.assertTrue(self.runs(rid)[0]["ok"], self.runs(rid))
        self.assertEqual(self.tuples("SELECT title, due_date FROM tasks WHERE created_by LIKE 'Automation:%'"), [("Book the change window", iso(3))])
        with self.assertRaises(ValueError):                  # the loop check still holds
            template_tasks.save(tid, [{"key": str(a), "stage_id": stage, "title": "X", "waits_on": str(rows[0][0])},
                                      {"key": str(rows[0][0]), "stage_id": stage, "title": "Y", "waits_on": str(a)}])

    def test_add_a_raid_item(self):
        self.rule(actions=[{"kind": "add_raid", "raid_kind": "risk", "title": "Change freeze ahead", "impact": "high"}])
        self.move(self.stages()[1])
        self.assertEqual(self.tuples("SELECT kind, title, impact, status, customer_visible, created_by FROM raid_items"),
                         [("risk", "Change freeze ahead", "high", "open", 0, "Automation: Tell the team")])

    def test_set_a_field_and_the_loop_guard(self):
        """A rule's actions never start another rule (depth 1); a person's change does."""
        fid = self.field()
        setter = self.rule(name="Setter", actions=[{"kind": "set_field", "field_id": fid, "value": "KSA"}])
        watcher = self.rule("field_set", name="Watcher", event_config={"field_id": fid, "value": "KSA"})
        self.move(self.stages()[1])
        self.assertEqual(self.sql("SELECT value FROM project_field_values")[0][0], "KSA")
        self.assertEqual([x["actions"][0]["said"] for x in self.runs(setter)], ["set Region to KSA"])
        self.assertEqual(self.runs(watcher), [])
        self.set_values({fid: "UAE"})
        self.set_values({fid: "KSA"})
        self.assertEqual(len(self.runs(watcher)), 1)

    def test_post_to_teams_and_say_so_when_teams_is_off(self):
        rid = self.rule(name="Ping the channel", actions=[{"kind": "teams", "message": "Deployment starts"}])
        self.move(self.stages()[1])
        self.assertEqual(self.runs(rid)[0]["actions"], [{"kind": "teams", "ok": False, "said": "Teams posts are switched off (Settings › Notifications)"}])
        self._set_policy(notify_teams_enabled="1", teams_webhook_url="https://example.webhook.office.com/hook")
        self.move(self.stages()[2])
        self.assertTrue(self.runs(rid)[0]["ok"])
        sent = [json.loads(r[0]) for r in self.sql("SELECT payload FROM outbox WHERE kind = 'teams'")]
        mine = [p["to"] for p in sent if "Ping the channel" in (p.get("html") or p.get("title") or "")]
        self.assertEqual(sorted(mine), ["channel", "webhook"])


class EngineTestCase(RulesBase):
    def put(self, url, body):
        return self.client.put(url, json=body, headers=self._csrf())

    def test_pause_and_resume(self):
        rid = self.rule()
        self.assertEqual(self.client.post(f"/api/rules/{rid}/pause", json={"paused": True}).status_code, 200)
        self.move(self.stages()[1])
        self.assertEqual(self.runs(), 0)
        self.client.post(f"/api/rules/{rid}/pause", json={"paused": False})
        self.move(self.stages()[2])
        self.assertEqual(self.runs(), 1)
        self.assertEqual((self.audits("pause_rule"), self.audits("resume_rule")), (1, 1))
        self.assertEqual(self.client.post(f"/api/rules/{rid}/pause", json={"paused": "yes"}).status_code, 400)

    def test_the_cap_is_a_policy(self):
        self._set_policy(rules_max="2")
        self.rule()
        self.rule()
        r = self.client.post("/api/rules", json={"name": "Third", "event": "stage_entered", "actions": [{"kind": "notify", "user_ids": [self.co]}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("At most 2 rules", r.get_json()["error"])
        listed = self.client.get("/api/rules").get_json()
        self.assertEqual((len(listed["rules"]), listed["max"]), (2, 2))

    def test_edit_delete_each_audited_and_the_run_log_listed(self):
        rid = self.rule()
        self.move(self.stages()[1])
        r = self.put(f"/api/rules/{rid}", {"name": "Renamed", "event": "stage_entered", "actions": [{"kind": "notify", "roles": ["Coordinator"]}]})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.move(self.stages()[2])
        listed = self.client.get("/api/rules").get_json()["rules"][0]
        self.assertEqual((listed["name"], listed["runs"], listed["last_run"]["ok"], listed["actions"][0]["roles"]), ("Renamed", 2, True, ["Coordinator"]))
        self.assertEqual(self.audits("rule_fired"), 2)
        actor = self.sql("SELECT username FROM audit_logs WHERE action = 'rule_fired' ORDER BY id DESC LIMIT 1")[0][0]
        self.assertEqual(actor, "rule: Renamed")
        self.assertEqual(self.client.delete(f"/api/rules/{rid}", headers=self._csrf()).status_code, 200)
        self.assertEqual((self.runs(), self.client.get(f"/api/rules/{rid}/runs").status_code), (0, 404))
        self.assertEqual((self.audits("create_rule"), self.audits("update_rule"), self.audits("delete_rule")), (1, 1, 1))

    def test_a_failing_action_is_logged_and_never_breaks_the_move(self):
        fid = self.field()
        rid = self.rule(actions=[{"kind": "set_field", "field_id": fid, "value": "KSA"},
                                 {"kind": "add_raid", "raid_kind": "issue", "title": "Still runs"},
                                 {"kind": "notify", "user_ids": [self.co]}])
        self.client.delete(f"/api/fields/{fid}", json={"confirm": "Region"}, headers=self._csrf())
        with patch("services.notifications.notify_users", side_effect=RuntimeError("mail down")):
            self.move(self.stages()[1])   # 200: the user's action stands
        run = self.runs(rid)[0]
        self.assertFalse(run["ok"])
        self.assertEqual([(a["kind"], a["ok"]) for a in run["actions"]], [("set_field", False), ("add_raid", True), ("notify", False)])
        self.assertIn("no longer exists", run["actions"][0]["said"])
        self.assertEqual(run["actions"][2]["said"], "failed: see the server log")
        self.assertEqual(self.sql("SELECT stage FROM projects")[0][0], self.stages()[1])
        self.assertIn("FAILED", self.sql("SELECT details FROM audit_logs WHERE action = 'rule_fired'")[0][0])

    def test_the_run_log_is_trimmed_by_policy(self):
        self.rule()
        self.move(self.stages()[1])
        self.sql("UPDATE rule_runs SET at = ?", (NOW - timedelta(days=91)).isoformat())
        self.ctx()
        from services import rules
        rules.trim()
        self.assertEqual(self.runs(), 0)

    def test_what_is_refused(self):
        def refused(**body):
            r = self.client.post("/api/rules", json={"name": "x", "event": "stage_entered", "actions": [{"kind": "notify", "user_ids": [self.co]}], **body})
            self.assertEqual(r.status_code, 400, body)
            return r.get_json()["error"]
        self.assertIn("starts", refused(event="every_hour"))
        self.assertIn("at least one action", refused(actions=[]))
        self.assertIn("At most 10 actions", refused(actions=[{"kind": "teams"}] * 11))
        self.assertIn("pick what it does", refused(actions=[{"kind": "move_stage", "stage": "Closed"}]))   # rules never move stages
        self.assertIn("delivery mode", refused(conditions=[{"kind": "delivery_mode", "value": "Teleport"}]))
        fid = self.field()
        self.assertIn("Region", refused(conditions=[{"kind": "field", "field_id": fid, "value": "Mars"}]))
        self.assertIn("template tasks", refused(actions=[{"kind": "add_task", "template_task_id": 999}]))
        self.assertIn("Name", refused(name=""))


class DryRunTestCase(RulesBase):
    def test_it_replays_the_last_30_days_and_changes_nothing(self):
        stages = self.stages()
        self.move(stages[1])
        self.move(stages[2])
        self.assertEqual(self.client.post("/projects/1/tasks", json={"title": "Late", "due_date": iso(-3)}).status_code, 200)
        before = (self.runs(), self.sql("SELECT COUNT(*) FROM notifications")[0][0])
        r = self.client.post("/api/rules/dry-run", json={"name": "Try", "event": "stage_entered", "conditions": [{"kind": "stage", "value": stages[2]}],
                                                         "actions": [{"kind": "notify", "user_ids": [self.co]}]})
        out = r.get_json()
        self.assertEqual([(m["name"], m["times"], m["last"]) for m in out["matches"]], [("Globex EDR", 1, f"Entered {stages[2]}")])
        self.assertIn("stage history", out["replayed"])
        self.assertIn("as it is now", out["caveat"])
        late = self.client.post("/api/rules/dry-run", json={"name": "Try", "event": "task_overdue", "actions": [{"kind": "teams"}]}).get_json()
        self.assertEqual([m["last"] for m in late["matches"]], [f"Task overdue: Late (due {iso(-3)})"])
        none = self.client.post("/api/rules/dry-run", json={"name": "Try", "event": "stage_entered", "conditions": [{"kind": "client", "value": "Initech"}],
                                                            "actions": [{"kind": "teams"}]}).get_json()
        self.assertEqual(none["total"], 0)
        self.assertEqual((self.runs(), self.sql("SELECT COUNT(*) FROM notifications")[0][0]), before)
        self.assertEqual(self.audits("dry_run_rule"), 0)   # a read: nothing to audit

    def test_a_field_change_is_replayed_from_the_audit_trail(self):
        fid = self.field()
        self.set_values({fid: "KSA"})
        out = self.client.post("/api/rules/dry-run", json={"name": "Try", "event": "field_set", "event_config": {"field_id": fid, "value": "KSA"},
                                                           "actions": [{"kind": "teams"}]}).get_json()
        self.assertEqual([m["last"] for m in out["matches"]], ["Region set to KSA"])


class PermissionTestCase(RulesBase):
    def test_every_rules_route_needs_manage_rules(self):
        rid = self.rule()
        c, csrf = self._api_client("co", STRONG_PASSWORD)
        h = {"X-CSRF-Token": csrf}
        body = {"name": "x", "event": "stage_entered", "actions": [{"kind": "teams"}]}
        calls = [c.get("/api/rules"), c.post("/api/rules", json=body, headers=h), c.put(f"/api/rules/{rid}", json=body, headers=h),
                 c.post(f"/api/rules/{rid}/pause", json={"paused": True}, headers=h), c.delete(f"/api/rules/{rid}", headers=h),
                 c.get(f"/api/rules/{rid}/runs"), c.post("/api/rules/dry-run", json=body, headers=h), c.get("/settings/automations")]
        self.assertEqual([r.status_code for r in calls], [403] * len(calls))
        self.assertEqual(self.client.get("/settings/automations").status_code, 200)
        self.sql("UPDATE role_permissions SET allowed = 1 WHERE permission = 'manage_rules' AND role = 'Member'")   # the matrix decides
        self.assertEqual(c.get("/api/rules").status_code, 200)
        self.assertIn("manage_rules", app_module.PERMISSIONS)


class WiringTestCase(RulesBase):
    def test_the_run_log_goes_with_a_purged_rollout_and_a_reset(self):
        import reset_data
        self.rule()
        self.move(self.stages()[1])
        self.assertEqual(self.runs(), 1)
        self.assertLess(reset_data.WIPE_TABLES.index("rule_runs"), reset_data.WIPE_TABLES.index("projects"))
        self.assertNotIn("rules", reset_data.WIPE_TABLES)   # the rules are configuration, as the templates are
        self.sql("UPDATE projects SET deleted_at = '2020-01-01T00:00:00'")
        self.ctx()
        from db import cleanup_soft_deletes
        cleanup_soft_deletes()
        self.assertEqual((self.runs(), self.sql("SELECT COUNT(*) FROM rules")[0][0]), (0, 1))

    def test_a_vendor_guest_link_move_fires_too(self):
        """change_stage is the one stage path: the vendor's guest link enters a stage as staff do."""
        rid = self.rule()
        with app_module.app.test_request_context():
            from routes.projects import change_stage
            from services import rules
            from flask import g
            g.rules_later = []
            self.assertIsNone(change_stage(1, self.stages()[1], "", guest=("Vendor Vic", "vendor")))
            rules.flush()
        self.assertEqual(len(self.runs(rid)), 1)
