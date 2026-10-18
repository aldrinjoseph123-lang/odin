"""Odin 2.0, workstream 4: customer self-service (services/asks.py).

A task assigned to an outside party is an ask: a tick, an upload into one
document category, or a short form. The person it is on does it from the
rollout page and nothing else opens to them; the project manager hears; the
daily reminder carries a fresh sign-in link; the signer rates the rollout
once per sign-off version, and the averages stay internal.
"""
import io
import json
import unittest
from unittest.mock import patch

import app as app_module
from test_app import drain_outbox
from test_fix_logic import FixBase

FORM = [{"label": "Seats", "kind": "number"}, {"label": "Go-live", "kind": "date"},
        {"label": "Tier", "kind": "choice", "choices": ["Gold", "Silver"]}, {"label": "SSO", "kind": "yesno"},
        {"label": "Anything else", "kind": "text", "required": False}]
GOOD = {"q1": "1200", "q2": "2026-11-02", "q3": "Gold", "q4": True}
PDF = b"%PDF-1.4 signed scope"


class SelfServeBase(FixBase):

    def setUp(self):
        super().setUp()
        for p in ("routes.projects.notify_event",):
            patcher = patch(p)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.new_project(name="Globex EDR", client="Globex")
        self.people = {}
        for role in ("Customer", "Contractor", "Reseller"):
            email = f"{role.lower()}@outside.example"
            self._invite(1, email, role, f"{role} Person")
            self.people[role] = self.sql("SELECT id FROM users WHERE email = ?", email)[0][0]
        self.clients = {}

    def ext(self, role):
        if role not in self.clients:
            self.clients[role] = self._external_client(f"{role.lower()}@outside.example")
        return self.clients[role]

    def ask(self, kind, role="Customer", title=None, **extra):
        body = {"title": title or f"{kind} for {role}", "assignee_id": self.people[role], "kind": kind, **extra}
        if kind == "upload":
            body.setdefault("ask_category", "Deliverable")
        if kind == "form":
            body.setdefault("questions", FORM)
        r = self.client.post("/projects/1/tasks", json=body)
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["id"]

    def upload(self, client, tid, name="scope.pdf", data=PDF, **form):
        return client.post("/projects/1/documents", data={"file": (io.BytesIO(data), name), "ask_id": str(tid), **form},
                           headers={"Accept": "application/json"})

    def answer(self, client, tid, answers):
        return client.post(f"/api/projects/1/asks/{tid}/answers", json={"answers": answers})

    def tick(self, client, tid):
        return client.post(f"/projects/1/tasks/{tid}/toggle", json={"done": True})

    def done(self, tid):
        return self.sql("SELECT done FROM tasks WHERE id = ?", tid)[0][0]


class AskKindsTestCase(SelfServeBase):

    def test_each_kind_as_each_outside_role(self):
        for role in ("Customer", "Contractor", "Reseller"):
            c = self.ext(role)
            t, u, f = self.ask("task", role), self.ask("upload", role), self.ask("form", role)
            mine = c.get("/api/projects/1/asks").get_json()["asks"]
            self.assertEqual({a["id"]: a["kind"] for a in mine}, {t: "task", u: "upload", f: "form"}, role)
            self.assertEqual(next(a for a in mine if a["id"] == u)["category"], "Deliverable")
            self.assertEqual([q["key"] for q in next(a for a in mine if a["id"] == f)["questions"]], ["q1", "q2", "q3", "q4", "q5"])
            self.assertEqual(self.tick(c, t).status_code, 200)
            self.assertEqual(self.upload(c, u).status_code, 200)
            self.assertEqual(self.answer(c, f, GOOD).status_code, 200)
            self.assertEqual([self.done(x) for x in (t, u, f)], [1, 1, 1], role)
            got = {a["id"]: a for a in c.get("/api/projects/1/asks").get_json()["asks"]}
            self.assertEqual(got[u]["file"]["filename"], "scope.pdf")
            self.assertEqual({a["key"]: a["value"] for a in got[f]["answers"]}, {"q1": "1200", "q2": "2026-11-02", "q3": "Gold", "q4": "yes"})
        self.assertEqual(self.audits("complete_ask"), 6)
        # staff see every ask with what came back
        staff = self.client.get("/api/projects/1/asks").get_json()["asks"]
        self.assertEqual(len(staff), 9)
        self.assertEqual({a["assignee_role"] for a in staff}, {"Customer", "Contractor", "Reseller"})

    def test_upload_and_form_asks_are_done_by_doing_them(self):
        c = self.ext("Customer")
        u, f = self.ask("upload"), self.ask("form")
        for tid in (u, f):
            r = self.tick(c, tid)
            self.assertEqual(r.status_code, 400)
            self.assertIn("Upload the file or answer", r.get_json()["error"])
        self.assertEqual(self.tick(self.client, u).status_code, 200)   # whoever manages the tasks may tick it

    def test_a_form_is_checked_question_by_question(self):
        c = self.ext("Customer")
        f = self.ask("form")
        for bad, words in (({"q1": "lots"}, "Seats: a number"), ({"q2": "next week"}, "Go-live: a date"), ({"q3": "Bronze"}, "Tier: pick one"),
                           ({"q4": "maybe"}, "SSO: yes or no"), ({"q1": ""}, "Answer: Seats"), ({"q1": "1e400"}, "Seats: a number")):
            r = self.answer(c, f, {**GOOD, **bad})
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn(words, r.get_json()["error"])
        self.assertEqual(self.done(f), 0)
        self.assertEqual(self.answer(c, f, {**GOOD, "q1": "12.5", "q5": "Branch office later"}).status_code, 200)
        self.assertEqual(dict(self.sql("SELECT question_key, value FROM task_answers WHERE task_id = ?", f)),
                         {"q1": "12.5", "q2": "2026-11-02", "q3": "Gold", "q4": "yes", "q5": "Branch office later"})

    def test_the_question_editor_is_checked_and_capped_by_policy(self):
        def add(questions):
            return self.client.post("/projects/1/tasks", json={"title": "Form", "kind": "form", "questions": questions})
        self.assertIn("at least one", add([]).get_json()["error"])
        self.assertIn("one of text", add([{"label": "x", "kind": "colour"}]).get_json()["error"])
        self.assertIn("between 2 and 20", add([{"label": "x", "kind": "choice", "choices": ["only"]}]).get_json()["error"])
        self.assertIn("at most 12", add([{"label": f"Q{i}", "kind": "text"} for i in range(13)]).get_json()["error"])
        self.assertEqual(add([{"label": f"Q{i}", "kind": "text"} for i in range(12)]).status_code, 200)
        self._set_policy(ask_form_max_questions="3")
        self.assertIn("at most 3", add([{"label": f"Q{i}", "kind": "text"} for i in range(4)]).get_json()["error"])
        self.assertIn("Pick the kind of document", self.client.post("/projects/1/tasks", json={"title": "U", "kind": "upload", "ask_category": "Nope"}).get_json()["error"])
        self.assertIn("Kind is one of", self.client.post("/projects/1/tasks", json={"title": "U", "kind": "survey"}).get_json()["error"])

    def test_an_edit_keeps_the_kind_and_the_keys(self):
        f = self.ask("form")
        qs = self.client.get("/api/projects/1/flow").get_json()["tasks"][0]["questions"]
        qs.insert(0, {"label": "New first", "kind": "text"})
        self.assertEqual(self.client.post(f"/projects/1/tasks/{f}/edit", json={"kind": "form", "questions": qs}).status_code, 200)
        self.assertEqual([q["key"] for q in json.loads(self.sql("SELECT ask_form FROM tasks WHERE id = ?", f)[0][0])], ["q6", "q1", "q2", "q3", "q4", "q5"])
        self.client.post(f"/projects/1/tasks/{f}/edit", json={"title": "Renamed"})
        self.assertEqual(self.sql("SELECT kind, title FROM tasks WHERE id = ?", f)[0][:], ("form", "Renamed"))


class AskSafetyTestCase(SelfServeBase):

    def test_upload_goes_only_into_the_asks_category_and_only_for_their_own_ask(self):
        c = self.ext("Customer")
        u = self.ask("upload")
        # the category is the ask's, whatever is posted
        self.assertEqual(self.upload(c, u, category="Client PO").status_code, 200)
        self.assertEqual(self.sql("SELECT category FROM documents WHERE filename = 'scope.pdf'")[0][0], "Deliverable")
        # someone else's ask, a plain task, or no ask at all: refused, as before
        other = self.ask("upload", "Contractor")
        plain = self.ask("task")
        for tid in (other, plain):
            self.assertEqual(self.upload(c, tid).status_code, 403)
        r = c.post("/projects/1/documents", data={"file": (io.BytesIO(PDF), "x.pdf"), "category": "Deliverable"}, headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 403)
        # the checks on the file stay: contents must match the extension
        u2 = self.ask("upload", title="Second")
        r = self.upload(c, u2, name="evil.pdf", data=b"MZ not a pdf")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.done(u2), 0)
        # another rollout's ask is not reachable through this one
        self.assertEqual(c.post("/api/projects/1/asks/999/answers", json={"answers": GOOD}).status_code, 404)

    def test_another_external_cannot_act_on_or_see_someone_elses_ask(self):
        f, t = self.ask("form", "Customer"), self.ask("task", "Customer")
        internal = self.client.post("/projects/1/tasks", json={"title": "Internal: price the renewal"}).get_json()["id"]
        con = self.ext("Contractor")
        self.assertEqual(self.answer(con, f, GOOD).status_code, 404)
        self.assertEqual(self.tick(con, t).status_code, 403)
        self.assertEqual(con.get("/api/projects/1/asks").get_json()["asks"], [])
        self.assertEqual(con.get("/api/projects/1/asks").get_json()["ratings"], [])
        # the cut: the project's flow lists only their own tasks, never the team's
        cust = self.ext("Customer")
        self.assertEqual({x["id"] for x in cust.get("/api/projects/1/flow").get_json()["tasks"]}, {f, t})
        self.assertNotIn(internal, {x["id"] for x in con.get("/api/projects/1/flow").get_json()["tasks"]})
        self.assertEqual(len(self.client.get("/api/projects/1/flow").get_json()["tasks"]), 3)   # staff see all

    def test_external_writes_are_rate_limited(self):
        self._set_policy(guest_writes_per_minute="2")
        c = self.ext("Customer")
        tasks = [self.ask("task", title=f"T{i}") for i in range(3)]
        self.assertEqual([self.tick(c, t).status_code for t in tasks], [200, 200, 429])
        self.assertEqual(self.answer(c, self.ask("form"), GOOD).status_code, 429)

    def test_the_project_manager_hears_when_an_ask_is_done(self):
        c = self.ext("Customer")
        f, u = self.ask("form"), self.ask("upload")
        self.answer(c, f, GOOD)
        self.upload(c, u)
        bell = [r[0] for r in self.sql("SELECT title FROM notifications WHERE user_id = 1 AND kind = 'activity' ORDER BY id")]
        self.assertEqual(bell, ["Ask done on Globex EDR", "Ask done on Globex EDR"])
        self._set_policy(notify_email_enabled="1")
        self.sql("UPDATE users SET email = 'admin@odin.example' WHERE id = 1")
        self.sql("DELETE FROM outbox")
        self.client.post(f"/projects/1/tasks/{f}/toggle", json={"done": False})
        self.answer(c, f, GOOD)
        with patch("graph.send_mail", return_value=(True, None)) as mail:
            drain_outbox()
        self.assertEqual([x.args[0] for x in mail.call_args_list], ["admin@odin.example"])
        self.assertIn("answered", mail.call_args.args[2])


class RemindersTestCase(SelfServeBase):

    def test_an_external_with_an_overdue_ask_gets_a_fresh_link_to_the_rollout(self):
        from send_daily_alerts import send_due_reminders
        self._set_policy(notify_email_enabled="1")
        self.ask("upload", due_date="2026-01-05")
        self.sql("DELETE FROM outbox")
        with app_module.app.test_request_context():
            from db import get_db
            self.assertEqual(send_due_reminders(get_db()), 1)
        payload = json.loads(self.sql("SELECT payload FROM outbox")[0][0])
        self.assertNotIn("/auth/link/", json.dumps(payload))   # no live token sits in the queue
        self.assertEqual(payload["signin"]["path"], "/projects/1")
        with patch("graph.send_mail", return_value=(True, None)) as mail:
            drain_outbox()
            self.sql("UPDATE outbox SET sent_at = NULL, next_try_at = '2000-01-01'")
            drain_outbox()
        links = [x.args[2].split('href="')[1].split('"')[0] for x in mail.call_args_list]
        self.assertEqual(len(links), 2)
        self.assertIn("/auth/link/", links[0])
        self.assertIn("next=/projects/1", links[0])
        self.assertNotEqual(links[0], links[1])   # minted at each send
        self.assertEqual(mail.call_args.args[0], "customer@outside.example")


class CsatTestCase(SelfServeBase):
    DRAWN = {"kind": "drawn", "strokes": [[[100, 150], [200, 100], [300, 200], [400, 120], [500, 180]]]}

    def send(self):
        stages = self.stages()
        self.sql("UPDATE projects SET stage = ? WHERE id = 1", stages[-2])
        r = self.client.post("/api/projects/1/signoff", json={"summary": "Done.", "signer_id": self.people["Customer"], "counter_id": 1, "delivered": ["All"]})
        self.assertEqual(r.status_code, 200, r.get_json())

    def sign(self, client, version=1, **extra):
        return client.post(f"/api/projects/1/signoff/{version}/sign", json={"name": "Customer Person", "accept": True, "signature": self.DRAWN, **extra})

    def test_the_signer_rates_once_per_version_and_only_the_signer(self):
        self.send()
        c = self.ext("Customer")
        self.assertIn("1 to 5", self.sign(c, rating=6).get_json()["error"])
        self.assertEqual(self.sql("SELECT status FROM signoffs")[0][0], "sent")   # a bad rating signs nothing
        self.assertEqual(self.sign(self.ext("Contractor"), rating=1).status_code, 403)
        self.assertEqual(self.sign(c, rating=4, rating_comment="Smooth cutover").status_code, 200)
        self.assertEqual(self.sql("SELECT signoff_version, rating, comment, by_id FROM csat")[0][:], (1, 4, "Smooth cutover", self.people["Customer"]))
        self.assertEqual(self.audits("rate_rollout"), 1)
        # signed already: no second rating for the version
        self.assertEqual(self.sign(c, rating=1).status_code, 400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM csat")[0][0], 1)
        with app_module.app.test_request_context():
            from db import get_db
            from services.asks import save_rating
            self.assertFalse(save_rating(get_db(), 1, 1, 2, None, 1, "x"))   # the table holds once per version too

    def test_rating_is_optional_and_the_averages_stay_internal(self):
        self.send()
        self.assertEqual(self.sign(self.ext("Customer")).status_code, 200)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM csat")[0][0], 0)
        self.sql("INSERT INTO csat (project_id, signoff_version, rating, by_name, at) VALUES (1, 1, 5, 'Customer Person', '2026-10-01T10:00:00')")
        self.assertEqual(self.client.get("/api/reports/all").get_json()["summary"]["csat"], 5.0)
        self.assertEqual(self.client.get("/api/projects/1/asks").get_json()["ratings"][0]["rating"], 5)
        people = {p["id"]: p for p in self.client.get("/api/people").get_json()["people"]}
        self.assertEqual(people[1]["csat"], 5.0)
        self.assertEqual(self.client.get("/api/people/1").get_json()["kpis"]["csat"], 5.0)
        internal = self.client.get("/api/projects/1/rollout-report").get_json()
        self.assertEqual(internal["data"]["csat"][0]["rating"], 5)
        customer = self.ext("Customer")
        cut = customer.get("/api/reports/all").get_json()
        self.assertIsNone(cut["summary"]["csat"])
        self.assertTrue(all("csat" not in r for r in cut["rows"]))
        self.assertEqual(customer.get("/api/projects/1/asks").get_json()["ratings"], [])


class WiringTestCase(SelfServeBase):

    def test_answers_and_ratings_go_with_a_purged_rollout(self):
        c = self.ext("Customer")
        self.answer(c, self.ask("form"), GOOD)
        self.sql("INSERT INTO csat (project_id, signoff_version, rating, by_name, at) VALUES (1, 1, 3, 'x', '2026-10-01')")
        self.sql("UPDATE projects SET deleted_at = '2000-01-01' WHERE id = 1")
        with app_module.app.app_context():
            from db import cleanup_soft_deletes
            cleanup_soft_deletes()
        self.assertEqual(self.sql("SELECT (SELECT COUNT(*) FROM task_answers) + (SELECT COUNT(*) FROM csat)")[0][0], 0)

    def test_reset_wipes_them_before_their_parents(self):
        import reset_data
        w = reset_data.WIPE_TABLES
        self.assertLess(w.index("task_answers"), w.index("tasks"))
        self.assertLess(w.index("csat"), w.index("projects"))


if __name__ == "__main__":
    unittest.main()
