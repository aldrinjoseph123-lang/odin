"""v1.8.0: notifications, Microsoft 365, Teams and the AI plumbing (review
advice A2 and P2-19, P2-21..24, P3-1, P3-6..8, P3-28, P3-33, P3-53).
Run with: python -m unittest test_v18_notify"""
import json
from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from test_app import STRONG_PASSWORD, app_module, drain_outbox
from test_fix_logic import FixBase


class NotifyBase(FixBase):
    def setUp(self):
        FixBase.setUp(self)
        self.sql("UPDATE users SET email = 'admin@corp.example' WHERE id = 1")

    def on(self, *keys):
        for k in keys:
            self.sql("INSERT INTO settings (key, value) VALUES (?, '1') ON CONFLICT(key) DO UPDATE SET value = '1'", k)

    def user(self, username, kind="internal", role="Member"):
        self.sql("INSERT INTO users (username, password_hash, name, role, active, email, kind) VALUES (?, 'x', ?, ?, 1, ?, ?)",
                 username, username.title(), role, f"{username}@corp.example", kind)
        return self.sql("SELECT id FROM users WHERE username = ?", username)[0][0]

    def notify(self, *args, **kw):
        from services.notifications import notify_users
        with app_module.app.test_request_context():
            notify_users(*args, **kw)

    def outbox(self):
        return [dict(r) for r in self.sql("SELECT * FROM outbox ORDER BY id")]


class OutboxTestCase(NotifyBase):
    """A2: the request writes the bell and queues; the scheduler sends, retries and gives up."""

    def test_the_request_never_calls_microsoft_and_the_drain_sends(self):
        self.on("notify_email_enabled", "notify_teams_chat_enabled")
        sam = self.user("sam")
        with patch("graph.send_mail", return_value=(True, None)) as mail, patch("services.teams_bot.send", return_value=(True, None)) as chat:
            self.notify([sam], "stage", None, "Moved", "<p>x</p>", link="/board")
            mail.assert_not_called(); chat.assert_not_called()
            self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE user_id = ?", sam)[0][0], 1)   # the bell at once
            self.assertEqual([r["kind"] for r in self.outbox()], ["mail", "teams"])
            drain_outbox()
        self.assertEqual(mail.call_args.args[0], "sam@corp.example"); self.assertEqual(chat.call_args.args[0], "sam@corp.example")
        self.assertTrue(all(r["sent_at"] for r in self.outbox()))
        drain_outbox()   # nothing twice
        self.assertEqual((mail.call_count, chat.call_count), (1, 1))

    def test_a_failure_waits_longer_each_time_then_the_admins_hear_once(self):
        self.on("notify_email_enabled")
        self._set_policy(outbox_attempts="3")
        sam, pat = self.user("sam"), self.user("pat")
        self.notify([sam, pat], "stage", None, "Moved", "<p>x</p>")
        with patch("graph.send_mail", return_value=(False, "429 too many requests")) as mail:
            drain_outbox()
            rows = self.outbox()
            self.assertEqual([r["attempts"] for r in rows], [1, 1])
            self.assertGreater(rows[0]["next_try_at"], datetime.utcnow().isoformat())   # not again at once
            self.assertEqual(mail.call_args.kwargs, {"report": False})
            for tries in (2, 3):
                self.sql("UPDATE outbox SET next_try_at = ? WHERE next_try_at IS NOT NULL", "2000-01-01T00:00:00")
                drain_outbox()
        rows = self.outbox()
        self.assertEqual([(r["attempts"], r["next_try_at"]) for r in rows], [(3, None), (3, None)])   # given up
        self.assertIn("429", rows[0]["last_error"])
        notices = self.sql("SELECT kind, title, body FROM notifications WHERE user_id = 1")
        self.assertEqual([(n[0], n[1]) for n in notices], [("ops", "Odin could not send email")])   # once a day, as kind ops
        self.assertIn("after 3 tries", notices[0][2])

    def test_waits_double(self):
        self.on("notify_email_enabled")
        self.notify([self.user("sam")], "stage", None, "Moved", "x")
        waits = []
        with patch("graph.send_mail", return_value=(False, "503")):
            for _ in range(4):
                self.sql("UPDATE outbox SET next_try_at = ?", "2000-01-01T00:00:00")
                before = datetime.utcnow()
                drain_outbox()
                waits.append(round((datetime.fromisoformat(self.outbox()[0]["next_try_at"]) - before).total_seconds() / 60))
        self.assertEqual(waits, [1, 2, 4, 8])

    def test_housekeeping_trims_sent_rows_and_old_given_up_ones(self):
        from services.outbox import trim
        old = (datetime.utcnow() - timedelta(days=400)).isoformat()
        now = datetime.utcnow().isoformat()
        for sent, nxt, created in ((now, None, now), (None, None, old), (None, None, now), (None, now, old)):
            self.sql("INSERT INTO outbox (kind, payload, sent_at, next_try_at, created_at) VALUES ('mail', '{}', ?, ?, ?)", sent, nxt, created)
        with app_module.app.app_context():
            trim()
        self.assertEqual([(r["sent_at"], r["created_at"]) for r in self.outbox()], [(None, now), (None, old)])   # a fresh give-up and a waiting one stay
        import scheduler
        self.assertIn("trim_outbox", open(scheduler.__file__).read())

    def test_channel_and_webhook_are_queued_and_the_webhook_address_is_not(self):
        self.on("notify_teams_enabled")
        self._set_policy(teams_webhook_url="https://hook.example/x?sig=secret")
        self.new_project(name="P", client="C")
        self.sql("DELETE FROM outbox")
        from services.notifications import notify_event
        with app_module.app.test_request_context():
            from db import get_db
            notify_event(get_db().execute("SELECT * FROM projects WHERE id = 1").fetchone(), "Stage changed: P", "<p>moved</p>")
        rows = self.outbox()
        self.assertEqual([json.loads(r["payload"])["to"] for r in rows], ["channel", "webhook"])
        self.assertNotIn("secret", json.dumps(rows))                                 # read at send time, never queued
        self.assertIn('/projects/1">Open in Odin</a>', json.loads(rows[0]["payload"])["html"])   # channel posts link the rollout (P3-1)
        with patch("graph.send_teams_message", return_value=(True, None)), patch("graph.post_teams_webhook", return_value=(True, None)) as hook:
            drain_outbox()
        self.assertEqual(hook.call_args.args[0], "https://hook.example/x?sig=secret")


class MailLinksTestCase(NotifyBase):
    """P2-21: every mail links into Odin, with or without a rollout."""

    def test_mail_without_a_project_links_the_page(self):
        self.on("notify_email_enabled")
        sam, ext = self.user("sam"), self.user("ext", kind="external", role="External")
        self.notify([sam, ext], "due", None, "2 tasks need you today", "<ul><li>x</li></ul>", link="/my-work")
        html = {json.loads(r["payload"])["to"]: json.loads(r["payload"])["html"] for r in self.outbox()}
        self.assertIn('<a href="http://localhost/my-work">Open in Odin</a>', html["sam@corp.example"])
        self.assertIn("/auth/link/", html["ext@corp.example"]); self.assertIn("next=/my-work", html["ext@corp.example"])   # no password: a one-time link


class TeamsChatTestCase(NotifyBase):
    """P2-22, P2-23, P3-6, P3-8."""

    def test_a_card_for_every_notification_even_when_it_is_not_mailed(self):
        self.on("notify_teams_chat_enabled")
        sam = self.user("sam")
        self.notify([sam], "alert", None, "Rollout overdue: P", "Rollout: P", email=False)
        self.assertEqual([(r["kind"], json.loads(r["payload"])["to"]) for r in self.outbox()], [("teams", "sam@corp.example")])
        self.sql("DELETE FROM outbox")
        self.notify([sam], "ops", None, "x", "y", email=False, teams=False)   # the notices about failing delivery stay in the bell
        self.assertEqual(self.outbox(), [])

    def test_alerts_reach_the_teams_chat_with_email_off(self):
        self.on("notify_teams_chat_enabled")
        self.new_project(name="Late", client="C", target_end_date="2020-01-01")
        self.sql("DELETE FROM outbox")
        from services.alerts import build_alerts, sync_alerts_to_db
        with app_module.app.test_request_context():
            from db import get_db
            sync_alerts_to_db(build_alerts(get_db().execute("SELECT * FROM projects").fetchall()))
        cards = [json.loads(r["payload"]) for r in self.outbox() if r["kind"] == "teams"]
        self.assertTrue(any(c["to"] == "admin@corp.example" and "overdue" in c["title"] for c in cards))
        self.assertTrue(all(c["link"].startswith("http://localhost/") for c in cards))   # "Open in Odin" even without a public address

    def test_missing_consent_is_named_and_the_address_is_quoted(self):
        import graph
        with patch("graph.is_connected", return_value=True), patch("graph._headers", return_value=({}, None)), \
             patch("graph.requests.get", return_value=MagicMock(status_code=403, text="Authorization_RequestDenied")) as get:
            uid, error = graph.user_id("a/../me@corp.example")
        self.assertIsNone(uid); self.assertIn("User.ReadBasic.All", error); self.assertIn("Disconnect and Connect again", error)
        self.assertIn("/users/a%2F..%2Fme%40corp.example?", get.call_args.args[0])

    def test_outsider_markdown_is_escaped_in_cards(self):
        import graph
        from services import teams_bot
        card = teams_bot.card("New note on **P**", "Guest: [Reset your password](https://evil.example)\n- item")
        self.assertEqual(card["body"][0]["text"], "New note on \\*\\*P\\*\\*")
        self.assertEqual(card["body"][1]["text"], "Guest: \\[Reset your password\\](https://evil.example)\n\\- item")
        with patch("graph.requests.post", return_value=MagicMock(status_code=202)) as post:
            graph.post_teams_webhook("https://hook.example/x", "T_1", ["[x](y)"])
        body = post.call_args.kwargs["json"]["attachments"][0]["content"]["body"]
        self.assertEqual([b["text"] for b in body], ["T\\_1", "\\[x\\](y)"])


class GraphMailTestCase(NotifyBase):
    """P3-53: the alias fallback only on Microsoft's "send as denied"."""

    def test_throttling_is_not_an_alias_refusal(self):
        import graph
        self.on("notify_email_enabled")
        self._set_policy(mail_from="odin-pms@corp.example")
        for code in (429, 503):
            with app_module.app.app_context(), patch("graph.is_connected", return_value=True), patch("graph._headers", return_value=({}, None)), \
                 patch("graph.requests.post", return_value=MagicMock(status_code=code, text="busy")) as post:
                ok, error = graph.send_mail("a@corp.example", "Hi", "x", report=False)
            self.assertFalse(ok); self.assertEqual(post.call_count, 1, code); self.assertIn(str(code), error)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications")[0][0], 0)   # no "refused the alias" notice


class PublicAddressTestCase(NotifyBase):
    """P3-1: links never come from the Host header."""

    def test_links_ignore_the_host_header(self):
        from core import external_url
        with app_module.app.test_request_context(base_url="http://evil.example:5051"):
            self.assertEqual(external_url("project_detail", project_id=1), "http://localhost:5051/projects/1")
        self._set_policy(public_url="https://odin.example.com")
        with app_module.app.test_request_context(base_url="http://evil.example"):
            self.assertEqual(external_url("project_detail", project_id=1), "https://odin.example.com/projects/1")

    def test_microsoft_redirect_and_guest_links_use_the_public_address(self):
        self._set_policy(public_url="https://odin.example.com")
        evil, E = app_module.app.test_client(), "http://evil.example"   # an admin who reached Odin by another name
        csrf = evil.get("/api/session", base_url=E).get_json()["csrf"]
        evil.post("/api/login", json={"username": "admin", "password": "changeme"}, headers={"X-CSRF-Token": csrf}, base_url=E)
        with patch("graph.oauth_client_configured", return_value=True), patch("graph._client_id", return_value="app"):
            r = evil.get("/integrations/connect", base_url=E)
        self.assertIn("redirect_uri=https%3A%2F%2Fodin.example.com%2Fintegrations%2Fcallback", r.headers["Location"])
        self.new_project(name="P", client="C")
        links = evil.get("/api/projects/1", base_url=E).get_json()["guest_links"]
        self.assertTrue(links["customer"].startswith("https://odin.example.com/guest/"))


class WeeklyReportTestCase(NotifyBase):
    """P2-19 and P3-28."""

    def _build(self, **patches):
        from services import weekly_report
        with app_module.app.test_request_context(), patch.multiple(weekly_report, **patches) if patches else nullcontext():
            return weekly_report.build()

    def test_a_rollout_overdue_and_over_sla_is_counted_once(self):
        self.new_project(name="P", client="C")
        with app_module.app.test_request_context():
            from db import get_db
            p = get_db().execute("SELECT * FROM projects WHERE id = 1").fetchone()
        alerts = {k: [] for k in ("project_overdue", "project_due_soon", "stage_sla_breach", "stale", "approval_waiting", "blocker_open", "task_unowned", "customer_quiet")}
        alerts.update(project_overdue=[p], stage_sla_breach=[p])
        _subject, html, summary, _ = self._build(build_alerts=lambda projects: alerts)
        self.assertIn("<b>1</b> overdue · <b>0</b> over SLA · <b>0</b> due soon", html)
        self.assertTrue(summary[0].endswith("1 overdue · 0 over SLA · 0 due soon"))

    def test_attachments_stay_under_the_mail_limit(self):
        self._set_policy(report_attach="1")
        for name in ("A", "B"):
            self.new_project(name=name, client="C")
        self.sql("INSERT INTO project_reports (project_id, version, kind, body, created_at, created_by) VALUES (1, 1, 'text', 'x', '2026-10-01', 'admin'), (2, 1, 'text', 'y', '2026-10-01', 'admin')")
        _s, html, _sum, files = self._build()
        self.assertEqual(len(files), 3)
        limit = len(files[0][1]) + len(files[1][1])   # room for the portfolio and one rollout
        _s, html, _sum, files = self._build(ATTACH_LIMIT=limit)
        self.assertEqual(len(files), 2); self.assertTrue(files[0][0].startswith("portfolio-report-"))
        self.assertIn("1 PDF report was left off to stay under Microsoft's 4 MB mail limit", html)


class AIPlumbingTestCase(NotifyBase):
    """P3-7 and P2-24."""

    def test_the_ai_client_does_not_follow_redirects(self):
        from services.ai.client import AIError, list_models
        resp = MagicMock(status_code=302, text="")
        with patch("services.ai.client.requests.request", return_value=resp) as req:
            with self.assertRaises(AIError) as err:
                list_models({"base_url": "http://192.168.1.238:11434/v1", "allow_external": False})
        self.assertFalse(req.call_args.kwargs["allow_redirects"]); self.assertIn("redirect", err.exception.reason)

    def test_a_draft_is_decided_by_account_not_by_name(self):
        self.new_project(name="P", client="C")
        a, b = self.user("sam1"), self.user("sam2")
        self.sql("UPDATE users SET name = 'Sam', password_hash = ? WHERE id IN (?, ?)",
                 __import__("werkzeug.security", fromlist=["x"]).generate_password_hash(STRONG_PASSWORD, method="pbkdf2:sha256"), a, b)
        self.sql("INSERT INTO ai_jobs (kind, feature, project_id, payload, status, requested_by, created_at) VALUES ('feature', 'ask_rollout', 1, ?, 'done', 'Sam', '2026-10-15')",
                 json.dumps({"requested_by_id": a}))
        self.sql("INSERT INTO ai_suggestions (project_id, feature, payload, job_id, created_at) VALUES (1, 'ask_rollout', '{}', 1, '2026-10-15')")
        for uid, name, code in ((b, "sam2", 403), (a, "sam1", 200)):
            c, csrf = self._api_client(name, STRONG_PASSWORD)
            self.assertEqual(c.post("/api/projects/1/ai/suggestions/1/dismiss", json={}, headers={"X-CSRF-Token": csrf}).status_code, code, name)

    def test_a_second_persons_words_are_refused_not_dropped(self):
        from services.ai.health import queue
        self.new_project(name="P", client="C")
        with app_module.app.test_request_context():
            from db import get_db
            first = queue(get_db(), "feature", feature="customer_words", project_id=1, payload={"input": {"summary": "a"}})
            second = queue(get_db(), "feature", feature="customer_words", project_id=1, payload={"input": {"summary": "b"}})
        self.assertNotEqual(first, second)   # never merged into someone else's job
        c, csrf = self._api_client()
        with patch("services.ai.gate", return_value=None):
            r = c.post("/api/projects/1/ai/customer_words", json={"input": {"summary": "c"}}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.status_code, 409); self.assertIn("already drafting", r.get_json()["error"])

    def test_customer_words_never_carry_a_health_colour(self):
        from services.ai.client import AIError
        from services.ai.features import customer_words, morning_brief, weekly_words
        for f in (weekly_words.FEATURE, customer_words.FEATURE, morning_brief.FEATURE):
            fx = f.fixture()
            self.assertNotRegex(json.dumps(fx).lower(), r"\b(amber|red|green)\b", f.key)   # never fed the colours
            said = {"summary": "The rollout is amber.", "brief": "Firewall refresh is red.", "next_steps": [], "asks": [], "first_move": "x"}
            self.assertTrue([g for g in f.graders if g(fx, said)], f.key)
            with self.assertRaises(AIError):
                f.refine(fx, said)
        self.assertEqual(customer_words.FEATURE.refine({"n": "Red Team"}, {"summary": "Red Team done"}), {"summary": "Red Team done"})


class TeamsAppTestCase(NotifyBase):
    """P3-33: the manifest's privacy and terms point at a public page that exists."""

    def test_manifest_points_at_the_about_page(self):
        from services import teams_bot
        with patch("graph._client_id", return_value="app-1"):
            m = json.loads(teams_bot.manifest("1.8.0", "https://odin.example.com"))
        self.assertEqual(m["developer"]["privacyUrl"], "https://odin.example.com/static/teams/about.html#privacy")
        self.assertEqual(m["developer"]["termsOfUseUrl"], "https://odin.example.com/static/teams/about.html#terms")
        page = app_module.app.test_client().get("/static/teams/about.html")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'id="privacy"', page.data); self.assertIn(b'id="terms"', page.data)
