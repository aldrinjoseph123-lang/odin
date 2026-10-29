"""v2.0.0 notifications and reports (review B2, B3, B8, B9, B10, B13, B15, B18):
daily summaries, mute and follow, sharing a report, chasers, "since you last
looked", the calendar feed, what's new, and each mail's next step.
Run with: python -m unittest test_v2_notify"""
import json
from datetime import date
from unittest.mock import patch

from test_app import STRONG_PASSWORD, app_module, drain_outbox
from test_fix_logic import FixBase

J = {"Accept": "application/json"}


class Base(FixBase):
    def setUp(self):
        FixBase.setUp(self)
        self._set_policy(timezone="UTC", notify_email_enabled="1")
        self.sql("UPDATE users SET email = 'admin@corp.example' WHERE id = 1")
        self.new_project(name="Alpha", client="C")

    def user(self, username, kind="internal", role="Member"):
        self.sql("INSERT INTO users (username, password_hash, name, role, active, email, kind) VALUES (?, 'x', ?, ?, 1, ?, ?)",
                 username, username.title(), role, f"{username}@corp.example", kind)
        return self.sql("SELECT id FROM users WHERE username = ?", username)[0][0]

    def join(self, uid, role="Coordinator", pid=1):
        self.sql("INSERT INTO project_participants (project_id, user_id, role, added_at) VALUES (?, ?, ?, ?)", pid, uid, role, "2026-10-01T00:00:00")

    def notify(self, *args, **kw):
        from services.notifications import notify_users
        with app_module.app.test_request_context():
            notify_users(*args, **kw)

    def outbox(self, kind=None):
        rows = [dict(r) for r in self.sql("SELECT * FROM outbox ORDER BY id")]
        return [dict(r, payload=json.loads(r["payload"])) for r in rows if kind is None or r["kind"] == kind]

    def client_for(self, username):
        c, csrf = self._api_client(username, STRONG_PASSWORD)
        return c, {"X-CSRF-Token": csrf}


class SummaryTestCase(Base):
    """B2: instant, daily summary or off per kind; the bell is always at once."""

    def test_a_summary_kind_is_held_then_sent_as_one_mail_grouped_by_rollout(self):
        sam = self.user("sam")
        self.sql("UPDATE users SET email_summary = 'stage,activity' WHERE id = ?", sam)
        self.new_project(name="Beta", client="C")
        self.notify([sam], "stage", 1, "Alpha moved", "<p>to Deploy</p>")
        self.notify([sam], "activity", 2, "Note on Beta", "<p>hello</p>")
        self.notify([sam], "assigned", 1, "A task for you", "<p>x</p>")   # instant
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE user_id = ?", sam)[0][0], 3)   # the bell at once
        self.assertEqual([r["kind"] for r in self.outbox()], ["held", "held", "mail"])
        from services.notifications import send_summaries
        with app_module.app.test_request_context():
            self.assertEqual(send_summaries(), 1)
            self.assertEqual(send_summaries(), 0)   # never twice
        mails = self.outbox("mail")
        self.assertEqual(len(mails), 2)
        summary = mails[1]["payload"]
        self.assertIn("2 updates on 2 rollouts", summary["subject"])
        self.assertLess(summary["html"].index("Alpha"), summary["html"].index("Beta"))
        self.assertIn("Alpha moved", summary["html"]); self.assertIn("Note on Beta", summary["html"])
        self.assertTrue(all(r["sent_at"] for r in self.outbox("held")))
        with patch("graph.send_mail", return_value=(True, None)) as mail:
            drain_outbox()
        self.assertEqual(mail.call_count, 2)

    def test_off_sends_nothing_and_the_old_switches_read_as_instant_or_off(self):
        sam = self.user("sam")
        self.sql("UPDATE users SET email_off = 'stage' WHERE id = ?", sam)   # a choice saved before B2
        self.notify([sam], "stage", 1, "Moved", "<p>x</p>")
        self.notify([sam], "activity", 1, "Note", "<p>x</p>")
        self.assertEqual([r["kind"] for r in self.outbox()], ["mail"])

    def test_the_account_page_saves_three_choices_audited(self):
        self._make_user("pat", "Member")
        c, h = self.client_for("pat")
        r = c.post("/account/notifications", data={"stage": "summary", "activity": "instant", "assigned": "on"}, headers={**h, **J})
        self.assertEqual(r.status_code, 200)
        row = self.sql("SELECT email_off, email_summary FROM users WHERE username = 'pat'")[0]
        self.assertEqual(row[1], "stage")
        self.assertNotIn("activity", row[0].split(",")); self.assertNotIn("assigned", row[0].split(",")); self.assertIn("mention", row[0].split(","))
        kinds = {k["key"]: k["mode"] for k in c.get("/api/account").get_json()["email_kinds"]}
        self.assertEqual((kinds["stage"], kinds["activity"], kinds["mention"]), ("summary", "instant", "off"))
        self.assertNotIn("access", kinds)   # admins only
        self.assertEqual(self.audits("change_own_notification_prefs"), 1)

    def test_the_digest_job_sends_the_summaries(self):
        import scheduler
        sam = self.user("sam")
        self.sql("UPDATE users SET email_summary = 'stage' WHERE id = ?", sam)
        self.notify([sam], "stage", 1, "Moved", "<p>x</p>")
        with patch("send_daily_alerts.main"), patch("policies.is_working_day", return_value=True):
            scheduler._run_job("digest", False)
        self.assertEqual(len(self.outbox("mail")), 1)


class WatchTestCase(Base):
    """B3: a participant mutes a rollout; staff not on it follow it."""

    def test_mute_keeps_the_bell_marked_and_stops_mail_and_teams(self):
        self._set_policy(notify_teams_chat_enabled="1")
        pid = self._make_user("pat", "Member"); self.join(pid)
        self.sql("UPDATE users SET email = 'pat@corp.example' WHERE id = ?", pid)
        c, h = self.client_for("pat")
        self.assertEqual(c.get("/api/projects/1/flow").get_json()["watch"], {"can": "mute", "on": False})
        self.assertEqual(c.post("/api/projects/1/watch", json={"on": True}, headers=h).get_json(), {"can": "mute", "on": True})
        self.notify([pid], "stage", 1, "Moved", "<p>x</p>")
        self.assertEqual(self.outbox(), [])
        self.assertEqual(self.sql("SELECT muted FROM notifications WHERE user_id = ?", pid)[0][0], 1)
        bell = c.get("/api/notifications").get_json()["rows"]
        self.assertTrue(bell[0]["muted"])
        c.post("/api/projects/1/watch", json={"on": False}, headers=h)
        self.notify([pid], "stage", 1, "Moved again", "<p>x</p>")
        self.assertEqual([r["kind"] for r in self.outbox()], ["mail", "teams"])
        self.assertEqual((self.audits("mute_rollout"), self.audits("unmute_rollout")), (1, 1))

    def test_the_owner_who_muted_gets_no_event_mail(self):
        from services.notifications import notify_event, set_watch
        with app_module.app.test_request_context():
            from db import get_db
            set_watch(1, 1, "mute", True); get_db().commit()
            notify_event(get_db().execute("SELECT * FROM projects WHERE id = 1").fetchone(), "Stage changed", "<p>x</p>")
        self.assertEqual(self.outbox("mail"), [])

    def test_a_follower_hears_the_rollouts_events_not_personal_ones(self):
        fid = self._make_user("fay", "Viewer")
        c, h = self.client_for("fay")
        self.assertEqual(c.get("/api/projects/1/flow").get_json()["watch"], {"can": "follow", "on": False})
        self.assertTrue(c.post("/api/projects/1/watch", json={"on": True}, headers=h).get_json()["on"])
        self.notify([1], "stage", 1, "Moved", "<p>x</p>")
        self.notify([1], "assigned", 1, "Yours", "<p>x</p>")
        self.notify([1], "stage", 1, "Fay moved it", "<p>x</p>", exclude_user_id=fid)
        self.assertEqual([r[0] for r in self.sql("SELECT title FROM notifications WHERE user_id = ? ORDER BY id", fid)], ["Moved"])
        self.assertEqual(self.audits("follow_rollout"), 1)

    def test_a_partner_may_mute_but_never_follow(self):
        self._invite(1, "ext@vendor.example", "Contractor")
        ext = self._external_client("ext@vendor.example")
        csrf = ext.get("/api/session").get_json()["csrf"]
        self.assertEqual(ext.post("/api/projects/1/watch", json={"on": True}, headers={"X-CSRF-Token": csrf}).get_json()["can"], "mute")
        self.new_project(name="Other", client="C")
        self.assertEqual(ext.post("/api/projects/2/watch", json={"on": True}, headers={"X-CSRF-Token": csrf}).status_code, 404)


class ShareReportTestCase(Base):
    """B8: Save and share tells the rollout's Customer contacts, with a sign-in link to their copy."""

    def test_sharing_notifies_customers_with_a_link_to_that_version(self):
        self._invite(1, "cus@client.example", "Customer", "Cus")
        self._invite(1, "ven@vendor.example", "Contractor", "Ven")
        self.sql("DELETE FROM outbox"); self.sql("DELETE FROM notifications")
        csrf = self.client.get("/api/session").get_json()["csrf"]
        r = self.client.post("/api/projects/1/rollout-report", json={"summary": "All good", "next_steps": "", "asks": "", "share": True}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.get_json()["shared"], 1)
        cus = self.sql("SELECT id FROM users WHERE email = 'cus@client.example'")[0][0]
        self.assertEqual(self.tuples("SELECT user_id, kind, link FROM notifications"), [(cus, "report", "/projects/1/report?v=1")])
        mail = self.outbox("mail")[0]["payload"]
        self.assertEqual(mail["signin"]["path"], "/projects/1/report?v=1")   # the link is minted as it is sent
        self.assertIn("shared with 1 customer contact", self.sql("SELECT details FROM audit_logs WHERE action = 'save_report'")[0][0])
        r = self.client.post("/api/projects/1/rollout-report", json={"summary": "Again", "next_steps": "", "asks": ""}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.get_json()["shared"], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications")[0][0], 1)


class ChaserTestCase(Base):
    """B9: one reminder after N working days, then every N, at most chase_max."""
    MON = "2026-11-02T09:00:00"   # a Monday

    def run_on(self, day):
        from services import chasers
        with app_module.app.test_request_context():
            return chasers.run(today=day)

    def test_a_waiting_signoff_is_chased_on_working_days_up_to_the_cap(self):
        self._invite(1, "cus@client.example", "Customer", "Cus")
        cus = self.sql("SELECT id FROM users WHERE email = 'cus@client.example'")[0][0]
        self.sql("INSERT INTO signoffs (project_id, version, status, content, content_hash, created_by, created_at, signer_id) "
                 "VALUES (1, 1, 'sent', '{}', 'h', 'admin', ?, ?)", self.MON, cus)
        self._set_policy(chase_after_days="3", chase_max="2")
        self.assertEqual(self.run_on(date(2026, 11, 4)), 0)   # Wednesday: two working days
        self.assertEqual(self.run_on(date(2026, 11, 5)), 1)   # Thursday: three
        self.sql("UPDATE signoffs SET chased_at = '2026-11-05T08:00:00'")
        self.assertEqual(self.run_on(date(2026, 11, 9)), 0)   # Monday: the weekend does not count
        self.assertEqual(self.run_on(date(2026, 11, 10)), 1)
        self.sql("UPDATE signoffs SET chased_at = '2026-11-10T08:00:00'")
        self.assertEqual(self.run_on(date(2026, 11, 30)), 0)   # the cap
        self.assertEqual(self.sql("SELECT chase_count FROM signoffs")[0][0], 2)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND title LIKE 'Reminder%'", cus)[0][0], 2)
        self.assertEqual(self.audits("chase_signoff"), 2)
        self.assertEqual(self.client.get("/api/projects/1/flow").get_json()["signoff_chases"], 2)   # the PM sees the count

    def test_a_pending_approval_is_chased_and_zero_switches_it_off(self):
        self._invite(1, "cus@client.example", "Customer", "Cus")
        stage = self.sql("SELECT stage FROM projects WHERE id = 1")[0][0]
        self.sql("INSERT INTO stage_approvals (project_id, stage, requested_by, requested_at) VALUES (1, ?, 'admin', ?)", stage, self.MON)
        self._set_policy(chase_after_days="0")
        self.assertEqual(self.run_on(date(2026, 11, 20)), 0)
        self._set_policy(chase_after_days="3")
        self.assertEqual(self.run_on(date(2026, 11, 5)), 1)
        self.assertEqual(self.client.get("/api/projects/1/flow").get_json()["approval"]["chases"], 1)
        self.assertEqual(self.audits("chase_approval"), 1)


class SinceTestCase(Base):
    """B10: the dashboard's "Since you last looked" on the person's own rollouts."""

    def test_the_window_starts_at_the_previous_visit(self):
        pat = self._make_user("pat", "Member"); self.join(pat)
        c, h = self.client_for("pat")
        self.freeze_clock("services.dashboard")
        long_ago = self.now(hours=-5).isoformat()
        self.sql("UPDATE users SET since_from = ?, since_seen_at = ? WHERE id = ?", long_ago, long_ago, pat)
        self.sql("INSERT INTO raid_items (project_id, kind, title, created_by, created_at, updated_at) VALUES (1, 'blocker', 'No VPN', 'Admin', ?, ?)",
                 self.now().isoformat(), self.now().isoformat())
        since = c.get("/api/dashboard").get_json()["data"]["since"]
        self.assertEqual(since["from"], long_ago)
        self.assertEqual([(i["kind"], i["text"]) for i in since["items"]], [("raid_blocker", "No VPN")])
        again = c.get("/api/dashboard").get_json()["data"]["since"]   # the same visit: the same window
        self.assertEqual(again["from"], long_ago)
        self.assertIn("since", {w["id"] for w in c.get("/api/dashboard").get_json()["catalogue"]})

    def test_my_own_acts_and_other_rollouts_are_left_out(self):
        pat = self._make_user("pat", "Member")
        c, h = self.client_for("pat")
        self.freeze_clock("services.dashboard")
        self.sql("INSERT INTO raid_items (project_id, kind, title, created_by, created_at, updated_at) VALUES (1, 'risk', 'Not mine', 'Admin', ?, ?)",
                 self.now().isoformat(), self.now().isoformat())
        self.assertEqual(c.get("/api/dashboard").get_json()["data"]["since"]["items"], [])


class CalendarFeedTestCase(Base):
    """B13: a secret, read-only, rotatable feed of my tasks and my rollouts' dates."""

    def test_make_read_rotate_and_turn_off(self):
        pat = self._make_user("pat", "Member"); self.join(pat)
        self.sql("INSERT INTO tasks (project_id, title, assignee_id, due_date, created_at) VALUES (1, 'Rack, the; switch', ?, '2026-11-12', '2026-11-01')", pat)
        self.sql("UPDATE projects SET target_end_date = '2026-12-01' WHERE id = 1")
        c, h = self.client_for("pat")
        url = c.post("/account/calendar", headers=h).get_json()["url"]
        path = url[url.index("/feeds/"):]
        anon = app_module.app.test_client()
        r = anon.get(path)
        self.assertEqual((r.status_code, r.mimetype), (200, "text/calendar"))
        body = r.get_data(as_text=True)
        self.assertIn("SUMMARY:Rack\\, the\\; switch (Alpha)", body)
        self.assertIn("DTSTART;VALUE=DATE:20261112", body); self.assertIn("SUMMARY:Target: Alpha", body)
        self.assertTrue(body.endswith("END:VCALENDAR\r\n"))
        token = path.split("/")[-1][:-4]
        self.assertNotIn(token, json.dumps([list(r) for r in self.sql("SELECT * FROM users")]))   # only the hash is kept
        self.assertTrue(c.get("/api/account").get_json()["calendar"]["created_at"])
        url2 = c.post("/account/calendar", headers=h).get_json()["url"]
        self.assertEqual(anon.get(path).status_code, 404)   # rotated: the old address is dead
        self.assertEqual(anon.get(url2[url2.index("/feeds/"):]).status_code, 200)
        c.post("/account/calendar/off", headers=h)
        self.assertEqual(anon.get(url2[url2.index("/feeds/"):]).status_code, 404)
        self.assertEqual((self.audits("create_calendar_feed"), self.audits("rotate_calendar_feed"), self.audits("revoke_calendar_feed")), (1, 1, 1))

    def test_reads_are_limited_and_partners_get_no_feed(self):
        self._set_policy(ics_feed_per_hour="5")
        anon = app_module.app.test_client()
        codes = [anon.get("/feeds/calendar/nope.ics").status_code for _ in range(6)]
        self.assertEqual(codes, [404] * 5 + [429])
        self._invite(1, "ext@vendor.example", "Contractor")
        ext = self._external_client("ext@vendor.example")
        csrf = ext.get("/api/session").get_json()["csrf"]
        self.assertEqual(ext.post("/account/calendar", headers={"X-CSRF-Token": csrf}).status_code, 403)
        self.assertIsNone(ext.get("/api/account").get_json()["calendar"])

    def test_text_folds_at_75_octets_without_splitting_a_character(self):
        from services.ics import _fold
        line = "SUMMARY:" + "é" * 60
        folded = _fold(line)
        self.assertTrue(all(len(part.encode()) <= 75 for part in folded.split("\r\n")))
        self.assertEqual(folded.replace("\r\n ", ""), line)


class WhatsNewTestCase(Base):
    """B15: staff see the release's change log once; subjects only, no paths."""
    LOG = {"releases": [{"version": "v9.9.0", "title": "Big one", "commits": [
        {"subject": "Version 9.9.0", "area": "Deployment"},
        {"subject": "Daily summaries on the Account page (services/notifications.py)", "area": "Server"},
        {"subject": "Kanban drags faster in Flow.tsx", "area": "Screens"},
        {"subject": "More tests", "area": "Tests"},
    ]}]}

    def test_the_summary_keeps_app_changes_and_drops_paths(self):
        from services.whats_new import summary
        s = summary("9.9.0", self.LOG)
        self.assertEqual(s["items"], ["Daily summaries on the Account page", "Kanban drags faster in"])
        self.assertIsNone(summary("1.0.0", self.LOG))

    def test_shown_once_per_release_to_staff(self):
        news = {"version": "9.9.0", "title": "Big one", "items": ["A thing"]}
        with patch("routes.client.app_version", return_value="9.9.0"), patch("services.whats_new.summary", return_value=news):
            csrf = self.client.get("/api/session").get_json()["csrf"]
            self.assertTrue(self.client.get("/api/whats-new").get_json()["show"])
            self.client.post("/api/whats-new/seen", headers={"X-CSRF-Token": csrf})
            self.assertFalse(self.client.get("/api/whats-new").get_json()["show"])
            self._invite(1, "ext@vendor.example", "Contractor")
            self.assertFalse(self._external_client("ext@vendor.example").get("/api/whats-new").get_json()["show"])
        self.assertEqual(self.audits("dismiss_whats_new"), 1)


class NextStepTestCase(Base):
    """B18: a mail about a rollout ends with the reader's own open tasks there."""

    def test_staff_get_their_tasks_and_a_customer_what_we_need(self):
        sam = self.user("sam")
        for i, due in enumerate(("2026-11-03", None, "2026-11-01", "2026-11-02")):
            self.sql("INSERT INTO tasks (project_id, title, assignee_id, due_date, created_at) VALUES (1, ?, ?, ?, '2026-10-01')", f"T{i}", sam, due)
        self.notify([sam], "stage", 1, "Moved", "<p>x</p>")
        html = self.outbox("mail")[0]["payload"]["html"]
        self.assertIn("Your next step on this rollout", html)
        self.assertLess(html.index("T2"), html.index("T3")); self.assertLess(html.index("T3"), html.index("T0"))
        self.assertNotIn("T1", html.split("Your next step")[1].split("and more")[0])   # three shown, the undated one waits
        self.assertIn("and more", html)
        cus = self.user("cus", kind="external")
        self.join(cus, "Customer")
        self.sql("INSERT INTO tasks (project_id, title, assignee_id, created_at) VALUES (1, 'Sign the PO', ?, '2026-10-01')", cus)
        self.notify([cus], "stage", 1, "Moved", "<p>x</p>")
        self.assertIn("What we need from you", self.outbox("mail")[1]["payload"]["html"])
        self.notify([1], "stage", 1, "Moved", "<p>x</p>")
        self.assertNotIn("next step", self.outbox("mail")[2]["payload"]["html"])   # nothing open: no block


class WordsTestCase(Base):
    def test_a_message_keeps_its_lines_in_the_bell(self):
        """Sim P3: _plain ran paragraphs and list items together ("One Two a b")."""
        from services.notifications import _plain
        self.assertEqual(_plain("<p>One</p><p>Two &amp; more</p><ul><li>a</li><li> b </li></ul>x<br>y<BR/>z"), "One\nTwo & more\na\nb\nx\ny\nz")
        self.notify([self.user("pm")], "stage", 1, "Moved", "<p>First</p><p>Second</p>")
        self.assertEqual(self.sql("SELECT body FROM notifications ORDER BY id DESC LIMIT 1")[0][0], "First\nSecond")

    def test_a_raid_status_refusal_reads_as_english(self):
        from services import raid
        with app_module.app.test_request_context():
            for kind, words in (("issue", "An issue's status is open or closed"), ("risk", "A risk's status is open, mitigating or closed")):
                with self.assertRaises(ValueError) as said:
                    raid.clean({"kind": kind, "title": "x", "status": "nonsense"}, 1)
                self.assertEqual(str(said.exception), words)
