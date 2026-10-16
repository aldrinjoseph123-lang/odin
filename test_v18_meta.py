"""v1.8.0 test hygiene (review 14 Oct 2026: P2-54 meta-tests that could not fail, P2-56 role
branches, P2-57 untested paths, P3-52 guards) and the golden role x route table (advice A15).
Run with: python -m unittest test_v18_meta

The golden file is tests/golden_routes.json. When a route is added, removed or its
permission changes, this module fails and prints what moved; if the change is wanted,
regenerate it with   ODIN_WRITE_GOLDEN=1 python -m unittest test_v18_meta.GoldenRoutesTestCase
and commit the file with the change."""
import io
import json
import logging
import os
import re
import sqlite3
import shutil
import tempfile
import time
import unittest
from contextlib import closing
from unittest.mock import MagicMock, patch

import test_app
from test_app import STRONG_PASSWORD, app_module, db_module
from test_fix_logic import FixBase

HERE = os.path.dirname(os.path.abspath(__file__))
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class Meta(FixBase):
    def _on(self, project_id, user_id, role):
        with self.raw_db() as db:
            db.execute("INSERT OR REPLACE INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, ?, 1, datetime('now'))",
                       (project_id, user_id, role))
            db.commit()


class FlowRoleBranchesTestCase(Meta):
    """P2-56: can_move and can_edit are two checks, the global permission and the role on that
    rollout. Each test below fails if either half is deleted."""

    def _world(self):
        self.new_project(name="One", client="C")                      # Admin manages it
        self.pm = self._make_user("pm", "Member")
        pm_client, _ = self._api_client("pm", STRONG_PASSWORD)           # a Member who creates a rollout manages it
        pm_client.post("/projects/new", data={"po_document": (io.BytesIO(b"%PDF-1.4 fake PO bytes"), "po.pdf"), "name": "Two", "client": "C"})
        self.coord = self._make_user("coord", "Member")
        self.con = self._make_user("con", "Contributor")
        self._on(1, self.coord, "Coordinator")
        self._on(1, self.con, "Project manager")   # a Contributor named manager: may edit the plan, never move the stage

    def _rows(self, who, path, key):
        c, _ = self._api_client(who, STRONG_PASSWORD)
        d = c.get(path).get_json()
        return {r["name"]: r[key] for r in d["rows"]}

    def test_can_move_needs_the_permission_and_the_project_manager_role(self):
        self._world()
        admin, _ = self._api_client()
        self.assertEqual({r["name"]: r["can_move"] for r in admin.get("/api/flow").get_json()["rows"]}, {"One": True, "Two": True})
        self.assertEqual(self._rows("pm", "/api/flow", "can_move"), {"One": False, "Two": True})        # manager of Two only
        self.assertEqual(self._rows("coord", "/api/flow", "can_move"), {"One": False, "Two": False})    # Coordinator: tasks, not the stage
        self.assertEqual(self._rows("con", "/api/flow", "can_move"), {"One": False, "Two": False})      # manager of One, but no permission to move
        # the page-level flag is the global permission alone
        c, _ = self._api_client("coord", STRONG_PASSWORD)
        self.assertTrue(c.get("/api/flow").get_json()["can_move"])
        c, _ = self._api_client("con", STRONG_PASSWORD)
        self.assertFalse(c.get("/api/flow").get_json()["can_move"])

    def test_can_edit_the_plan_needs_the_permission_and_the_project_manager_role(self):
        self._world()
        admin, _ = self._api_client()
        self.assertEqual({r["name"]: r["can_edit"] for r in admin.get("/api/flow/plan").get_json()["rows"]}, {"One": True, "Two": True})
        self.assertEqual(self._rows("pm", "/api/flow/plan", "can_edit"), {"One": False, "Two": True})
        self.assertEqual(self._rows("coord", "/api/flow/plan", "can_edit"), {"One": False, "Two": False})
        self.assertEqual(self._rows("con", "/api/flow/plan", "can_edit"), {"One": True, "Two": False})   # edit_project is theirs, and so is One
        self._on(1, self._make_user("vic", "Viewer"), "Project manager")
        self.assertEqual(self._rows("vic", "/api/flow/plan", "can_edit"), {"One": False, "Two": False})  # the role without the permission

    def test_the_flow_and_its_plan_follow_an_external_to_their_own_rollout(self):
        self._world()
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        ann = self._external_client("ann@acme.example")
        flow = ann.get("/api/flow")
        self.assertEqual(flow.status_code, 200)
        self.assertEqual([r["name"] for r in flow.get_json()["rows"]], ["One"])                        # scoped to what she is on
        self.assertEqual({r["can_move"] for r in flow.get_json()["rows"]}, {False})
        self.assertEqual(ann.get("/api/flow/plan").status_code, 403)                                   # staff only: the customer cut is the report's


class CsrfExemptionsTestCase(Meta):
    """P3-52: one place lists what skips the CSRF check; a new exemption fails here until it is listed."""

    # Teams posts installs without a session; browsers post crash reports; /api/v1 is Bearer-token only.
    from security import CSRF_EXEMPT
    EXEMPT = {("POST", path) for path in CSRF_EXEMPT}
    BEARER_PREFIX = "/api/v1/"

    @staticmethod
    def _url(rule):
        return re.sub(r"<(?:int:)(\w+)>", "1", re.sub(r"<(?!int:)(?:\w+:)?\w+>", "x", rule))

    def test_every_state_changing_route_refuses_a_request_with_no_token(self):
        from flask.testing import FlaskClient
        plain = FlaskClient(app_module.app, app_module.app.response_class)   # not CSRFTestClient, which adds tokens
        skipped, checked = set(), 0
        logging.disable(logging.WARNING)   # /api/client-errors logs the empty report it is sent
        self.addCleanup(logging.disable, logging.NOTSET)
        for rule in app_module.app.url_map.iter_rules():
            for method in rule.methods & MUTATING:
                if rule.endpoint == "static":
                    continue
                status = plain.open(self._url(rule.rule), method=method).status_code
                checked += 1
                if status != 400:
                    skipped.add((method, rule.rule))
        listed = self.EXEMPT | {(m, r) for m, r in skipped if r.startswith(self.BEARER_PREFIX)}
        self.assertEqual(skipped - listed, set(), "routes that skip the CSRF check without being listed here")
        self.assertEqual(self.EXEMPT - skipped, set(), "listed exemptions that the check no longer skips: delete them")
        self.assertGreater(checked, 100)

    def test_the_bearer_prefix_holds_only_token_routes(self):
        import ast
        import inspect
        import textwrap
        wrong = []
        for rule in app_module.app.url_map.iter_rules():
            if not rule.rule.startswith(self.BEARER_PREFIX):
                continue
            tree = ast.parse(textwrap.dedent(inspect.getsource(app_module.app.view_functions[rule.endpoint])))
            decorators = {ast.unparse(d).split("(")[0] for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) for d in n.decorator_list}
            if "token_required" not in decorators:
                wrong.append(rule.rule)
        self.assertEqual(wrong, [], "/api/v1 routes skip CSRF, so each must authenticate by Bearer token")


class JinjaPagesTestCase(Meta):
    """P2-54: the four 'rendered page' tests parsed the React stub, which has no markup to fail on.
    These pages are still server-rendered, so the structure is checked where it exists."""

    def _structure(self, html):
        from html.parser import HTMLParser

        class P(HTMLParser):
            def __init__(self):
                super().__init__()
                self.depth, self.nested, self.levels, self.unnamed, self.in_label = 0, False, [], [], False
                self.ids = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', html))

            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                if tag == "form":
                    self.nested |= self.depth > 0
                    self.depth += 1
                if tag == "label":
                    self.in_label = True
                if re.fullmatch(r"h[1-6]", tag):
                    self.levels.append(int(tag[1]))
                if tag in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit", "button"):
                    if not ("aria-label" in a or "aria-labelledby" in a or self.in_label or a.get("id") in self.ids):
                        self.unnamed.append(f'{tag}[{a.get("name", "?")}]')

            def handle_endtag(self, tag):
                if tag == "form" and self.depth:
                    self.depth -= 1
                if tag == "label":
                    self.in_label = False

        p = P()
        p.feed(html)
        gaps = [(p.levels[i], p.levels[i + 1]) for i in range(len(p.levels) - 1) if p.levels[i + 1] - p.levels[i] > 1]
        return p, gaps

    def test_the_guest_pages_and_the_sign_in_fallback_are_well_formed(self):
        self.new_project(name="V", client="Acme", delivery_mode="Outsourced", outsourcer_name="VendorCo")
        with self.raw_db() as db:
            vendor, customer = db.execute("SELECT access_token, customer_token FROM projects WHERE id=1").fetchone()
        guest = app_module.app.test_client()
        pages = {"guest (vendor)": guest.get(f"/guest/{vendor}").data.decode(),
                 "guest (customer)": guest.get(f"/guest/{customer}").data.decode(),
                 "sign-in fallback": guest.post("/login", data={"username": "nobody", "password": "x"}).data.decode()}
        for name, html in pages.items():
            self.assertIn("<form", html, f"{name} lost its form: the test would check nothing")
            parsed, gaps = self._structure(html)
            self.assertFalse(parsed.nested, f"nested <form> on {name}")
            self.assertEqual(parsed.unnamed, [], f"unnamed controls on {name}")
            self.assertEqual(gaps, [], f"heading level skipped on {name}")
            self.assertTrue(parsed.levels, f"{name} has no heading")


class TeamsBotTestCase(Meta):
    """P2-57: the bot's token and failure replies, and the once-a-day notice that follows them."""

    def setUp(self):
        super().setUp()
        from services import teams_bot
        self.bot = teams_bot
        saved = dict(teams_bot._token)
        teams_bot._token.update(key=None, value=None, until=0.0)   # no token from another test
        self.addCleanup(lambda: teams_bot._token.update(saved))
        for target, value in (("graph._tenant", "tenant-1"), ("graph._client_id", "app-1"), ("graph._client_secret", "secret-1")):
            p = patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch("services.teams_bot.configured", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def _reply(code, body=None, text=""):
        return MagicMock(status_code=code, text=text, json=MagicMock(return_value=body or {}))

    def test_the_token_is_kept_until_the_app_or_the_secret_changes(self):
        with patch("services.teams_bot.requests.post", return_value=self._reply(200, {"access_token": "t1", "expires_in": 3600})) as post:
            self.assertEqual(self.bot._bot_token(), ("t1", None))
            self.assertEqual(self.bot._bot_token(), ("t1", None))
            self.assertEqual(post.call_count, 1, "a second call within the hour reuses the token")
            with patch("graph._client_secret", return_value="secret-2"):
                self.bot._bot_token()
            self.assertEqual(post.call_count, 2, "a changed secret must not reuse the old app's token")
            with patch("graph._tenant", return_value="tenant-2"):
                self.bot._bot_token()
            self.assertEqual(post.call_count, 3)
        self.assertEqual(post.call_args.kwargs["data"]["scope"], "https://api.botframework.com/.default")
        # an expiring token is renewed a minute early
        self.bot._token.update(key=("tenant-1", "app-1", "secret-1"), value="old", until=time.time() + 30)
        with patch("services.teams_bot.requests.post", return_value=self._reply(200, {"access_token": "t2", "expires_in": 3600})):
            self.assertEqual(self.bot._bot_token(), ("t2", None))

    def test_a_refused_sign_in_is_a_reply_not_an_exception(self):
        with patch("services.teams_bot.requests.post", return_value=self._reply(401, text="invalid_client " + "x" * 400)) as post:
            token, error = self.bot._bot_token()
            self.assertIsNone(token)
            self.assertTrue(error.startswith("Teams app sign-in failed: 401 invalid_client"))
            self.assertLess(len(error), 260, "the body is cut")
            ok, said = self.bot.send("tina@corp.example", "Title", "Text")
            self.assertEqual((ok, said[:34]), (False, "Teams app sign-in failed: 401 inva"))
            self.assertEqual(post.call_count, 2, "a failed sign-in is not cached")
        self.assertIsNone(self.bot._token["value"])

    def test_every_failure_comes_back_as_text(self):
        self.bot._token.update(key=("tenant-1", "app-1", "secret-1"), value="tok", until=time.time() + 3600)
        user = patch("graph.user_id", return_value=("aad-1", None))
        user.start()
        self.addCleanup(user.stop)
        cases = [
            ("not installed", [self._reply(403)], "The Odin PMS app is not installed in Teams for tina@corp.example"),
            ("opening refused", [self._reply(500, text="boom")], "Teams message failed: 500 boom"),
            ("network down", [ConnectionError("no route")], "Teams message failed: no route"),
            ("post refused", [self._reply(201, {"id": "c1"}), self._reply(500, text="down")], "Teams message failed: 500 down"),
            ("twice gone", [self._reply(201, {"id": "c1"}), self._reply(404), self._reply(201, {"id": "c2"}), self._reply(404, text="gone")], "Teams message failed: 404 gone"),
        ]
        for name, replies, expected in cases:
            with self.subTest(name), patch("services.teams_bot.requests.post", side_effect=replies):
                with app_module.app.app_context():
                    graph_set = patch("graph._set_db_setting")
                    graph_get = patch("graph._db_setting", return_value=None)
                    with graph_set, graph_get:
                        self.assertEqual(self.bot.send("tina@corp.example", "T", "x"), (False, expected))
        with patch("graph.user_id", return_value=(None, "No Microsoft 365 user found for nobody@corp.example")):
            with app_module.app.app_context(), patch("graph._db_setting", return_value=None):
                self.assertEqual(self.bot.send("nobody@corp.example", "T", "x"), (False, "No Microsoft 365 user found for nobody@corp.example"))

    def test_unconfigured_says_what_is_missing(self):
        with patch("services.teams_bot.configured", return_value=False):
            ok, error = self.bot.send("a@b.example", "T", "x")
        self.assertFalse(ok)
        self.assertIn("Azure app's id, secret and tenant", error)

    def test_the_admins_hear_of_failing_teams_messages_once_a_day(self):
        from services import outbox
        self._set_policy(outbox_attempts=1)
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications WHERE kind = 'ops'").fetchone()[0], 0)
        with app_module.app.app_context():
            for to in ("a@corp.example", "b@corp.example", "c@corp.example"):
                outbox.add("teams", to=to, title="T", text="x")
        with patch("services.teams_bot.send", return_value=(False, "The Odin PMS app is not installed in Teams for a@corp.example")):
            test_app.drain_outbox()
        with self.raw_db() as db:
            notes = db.execute("SELECT title, body FROM notifications WHERE kind = 'ops'").fetchall()
            given_up = db.execute("SELECT COUNT(*) FROM outbox WHERE next_try_at IS NULL AND sent_at IS NULL").fetchone()[0]
        self.assertEqual(given_up, 3)
        self.assertEqual([n["title"] for n in notes], ["Odin could not send a Teams message"], "three failures, one notice")
        self.assertIn("not installed in Teams", notes[0]["body"])
        with app_module.app.app_context():   # a day later it speaks again
            from db import set_setting
            set_setting("teams_failure_reported_at", "2000-01-01T00:00:00")
            outbox.add("teams", to="d@corp.example", title="T", text="x")
        with patch("services.teams_bot.send", return_value=(False, "down")):
            test_app.drain_outbox()
        with self.raw_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications WHERE kind = 'ops'").fetchone()[0], 2)


class UnexecutedRoutesTestCase(Meta):
    """P2-57: routes no other test ran (found by recording every request of the whole suite, 15 Oct
    2026). The riskiest first: new recovery codes must kill the old ones, and a withdrawn sign-off
    must stop being signable. Each test runs the route, checks what it changed and that it was audited."""

    _signoff_setup = test_app.ContactsAndProjectMetaTestCase._signoff_setup
    _ext = test_app.ContactsAndProjectMetaTestCase._ext
    DRAWN = test_app.ContactsAndProjectMetaTestCase.DRAWN

    def _admin(self):
        c, csrf = self._api_client()
        return c, {"X-CSRF-Token": csrf, "Accept": "application/json"}

    def _audited(self, action, like=False):
        return self.sql(f"SELECT COUNT(*) FROM audit_logs WHERE action {'LIKE' if like else '='} ?", action)[0][0]

    # ---- two-step sign-in --------------------------------------------------------

    def _with_two_step(self):
        from services import mfa
        self._make_user("pm", "Member")
        c, csrf = self._api_client("pm", STRONG_PASSWORD)
        h = {"X-CSRF-Token": csrf}
        secret = c.post("/api/account/two-step/setup", json={"password": STRONG_PASSWORD}, headers=h).get_json()["secret"]
        step = int(time.time() // mfa.STEP)
        codes = c.post("/api/account/two-step/confirm", json={"code": mfa.code_at(secret, step)}, headers=h).get_json()["recovery_codes"]
        clock = patch("services.mfa.time")   # frozen: a 30 s rollover mid-test must not move the codes
        clock.start().time.return_value = step * mfa.STEP + 1
        self.addCleanup(clock.stop)
        return c, h, secret, step, codes, mfa

    def _recovery_works(self, mfa, code):
        with app_module.app.app_context():
            user = db_module.get_db().execute("SELECT * FROM users WHERE username = 'pm'").fetchone()
            return mfa.check(user, code) is not None

    def test_new_recovery_codes_need_the_password_and_a_code_and_kill_the_old_ones(self):
        c, h, secret, step, old, mfa = self._with_two_step()
        url = "/api/account/two-step/recovery-codes"
        self.assertEqual(old and len(old) > 3, True)
        self.assertEqual(c.post(url, json={"password": "not-the-password-1", "code": mfa.code_at(secret, step + 1)}, headers=h).get_json()["error"], "Your password is not right")
        self.assertEqual(c.post(url, json={"password": STRONG_PASSWORD, "code": "000000"}, headers=h).get_json()["error"], "That code is not right")
        self.assertTrue(self._recovery_works(mfa, old[1]), "refused requests change nothing")
        r = c.post(url, json={"password": STRONG_PASSWORD, "code": mfa.code_at(secret, step + 1)}, headers=h)
        self.assertEqual(r.status_code, 200)
        new = r.get_json()["recovery_codes"]
        self.assertEqual(len(new), len(old))
        self.assertFalse(set(new) & set(old))
        self.assertFalse(self._recovery_works(mfa, old[0]), "an old code must die the moment new ones are made")
        self.assertFalse(self._recovery_works(mfa, old[2]))
        self.assertTrue(self._recovery_works(mfa, new[0]))
        self.assertEqual(c.get("/api/account/two-step").get_json()["recovery_left"], len(new) - 1)   # new[0] was just used
        self.assertEqual(self._audited("mfa_recovery_codes"), 1)

    def test_recovery_codes_for_an_account_without_two_step_are_refused(self):
        self._make_user("pm", "Member")
        c, csrf = self._api_client("pm", STRONG_PASSWORD)
        self.assertEqual(c.post("/api/account/two-step/recovery-codes", json={"password": STRONG_PASSWORD, "code": "123456"}, headers={"X-CSRF-Token": csrf}).status_code, 400)
        self.assertEqual(self._audited("mfa_recovery_codes"), 0)

    def test_turning_two_step_off_needs_proof_and_is_audited_either_way(self):
        c, h, secret, step, codes, mfa = self._with_two_step()
        url = "/api/account/two-step/off"
        self.assertEqual(c.post(url, json={"password": STRONG_PASSWORD, "code": "000000"}, headers=h).status_code, 400)
        self.assertEqual(self._audited("mfa_disable_refused"), 1)
        self.assertTrue(c.get("/api/account/two-step").get_json()["enabled"])
        with patch("services.mfa.required", return_value=True):   # the workspace requires it: it cannot be turned off
            r = c.post(url, json={"password": STRONG_PASSWORD, "code": mfa.code_at(secret, step + 1)}, headers=h)
        self.assertEqual((r.status_code, r.get_json()["error"]), (400, "Two-step sign-in is required for your account"))
        self.assertEqual(c.post(url, json={"password": STRONG_PASSWORD, "code": mfa.code_at(secret, step + 1)}, headers=h).get_json(), {"ok": True})
        self.assertFalse(c.get("/api/account/two-step").get_json()["enabled"])
        self.assertEqual(self._audited("mfa_disable"), 1)

    # ---- sign-off and scope -----------------------------------------------------------

    def _send_signoff(self, c, h, ann):
        return c.post("/api/projects/1/signoff", json={"summary": "Done.", "signer_id": ann, "counter_id": 1, "delivered": ["All"], "terms": ["Support"]}, headers=h)

    def test_withdrawing_a_sign_off_stops_it_being_signed_and_frees_the_scope(self):
        c, h, ann, _ = self._signoff_setup()
        item = c.post("/api/projects/1/scope", json={"title": "Deploy sensors"}, headers=h).get_json()["id"]
        c.put(f"/api/projects/1/scope/{item}", json={"status": "delivered"}, headers=h)
        self.assertEqual(self._send_signoff(c, h, ann).get_json()["version"], 1)
        frozen = self.sql("SELECT content FROM signoffs WHERE version = 1")[0][0]
        e, eh = self._ext("ann@globex.example")
        self.assertEqual(c.delete(f"/api/projects/1/scope/{item}", headers=h).status_code, 409)   # frozen while out for signature
        # only the project manager withdraws: the customer cannot, and a stranger version is not there
        self.assertEqual(e.post("/api/projects/1/signoff/1/withdraw", headers=eh).status_code, 403)
        self.assertEqual(c.post("/api/projects/1/signoff/9/withdraw", headers=h).status_code, 404)
        self.assertEqual(c.post("/api/projects/1/signoff/1/withdraw", headers=h).get_json(), {"ok": True})
        self.assertEqual(self.sql("SELECT status FROM signoffs WHERE version = 1")[0][0], "withdrawn")
        self.assertEqual(self.sql("SELECT content FROM signoffs WHERE version = 1")[0][0], frozen, "a withdrawn version keeps its frozen content")
        self.assertEqual(self._audited("signoff_withdraw"), 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND title LIKE '%withdrawn%'", ann)[0][0], 1, "the signer is told")
        signed = e.post("/api/projects/1/signoff/1/sign", json={"name": "Ann", "title": "CISO", "accept": True, "signature": self.DRAWN}, headers=eh)
        self.assertNotEqual(signed.status_code, 200, "a withdrawn sign-off cannot be signed")
        self.assertEqual(c.post("/api/projects/1/signoff/1/withdraw", headers=h).status_code, 400)   # nothing left to withdraw
        # the scope is free again, and a revised version goes out as version 2
        self.assertEqual(c.delete(f"/api/projects/1/scope/{item}", headers=h).get_json(), {"ok": True})
        self.assertEqual(self._audited("delete_scope_item"), 1)
        self.assertEqual(self._send_signoff(c, h, ann).get_json()["version"], 2)

    def test_deleting_scope_that_is_not_the_rollouts_is_a_404(self):
        c, h, _, _ = self._signoff_setup(customer=False)
        self.new_project(name="Other", client="C")
        other = c.post("/api/projects/2/scope", json={"title": "Theirs"}, headers=h).get_json()["id"]
        self.assertEqual(c.delete(f"/api/projects/1/scope/{other}", headers=h).status_code, 404)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM scope_items")[0][0], 1)

    # ---- lessons, document templates, the AI check ----------------------------------

    def test_a_lesson_is_deleted_by_the_manager_and_only_from_its_own_rollout(self):
        self.new_project(name="One", client="C")
        self.new_project(name="Two", client="C")
        coord = self._make_user("coord", "Member")
        self._on(1, coord, "Coordinator")
        c, h = self._admin()
        for pid in (1, 2):
            c.post(f"/api/projects/{pid}/lessons", json={"items": [{"kind": "avoid", "text": f"Lesson on {pid}", "evidence": "e"}]}, headers=h)
        mine, theirs = [r[0] for r in self.sql("SELECT id FROM lessons ORDER BY project_id")]
        k, kh = self._api_client("coord", STRONG_PASSWORD)
        self.assertEqual(k.post(f"/api/projects/1/lessons/{mine}/delete", headers={"X-CSRF-Token": kh}).status_code, 403)
        self.assertEqual(c.post(f"/api/projects/1/lessons/{theirs}/delete", headers=h).status_code, 404)
        self.assertEqual(c.post(f"/api/projects/1/lessons/{mine}/delete", headers=h).get_json(), {"ok": True})
        self.assertEqual([r[0] for r in self.sql("SELECT text FROM lessons")], ["Lesson on 2"])
        self.assertEqual(self._audited("delete_lesson"), 1)

    def test_document_templates_can_be_made_default_and_deleted(self):
        c, h = self._admin()
        cfg = {"title": "Certificate", "accent": "teal", "company_line": "Protect24x7", "footer": "", "sections": [], "texts": {}}
        first = c.post("/api/doc-templates", json={"kind": "signoff", "name": "First", "config": cfg}, headers=h).get_json()["id"]
        second = c.post("/api/doc-templates", json={"kind": "signoff", "name": "Second", "config": cfg}, headers=h).get_json()["id"]
        default = lambda: {t["name"]: t["is_default"] for t in c.get("/api/doc-templates").get_json()["templates"]}   # noqa: E731
        self.assertEqual(default(), {"First": True, "Second": False})
        self.assertEqual(c.post(f"/api/doc-templates/{second}/default", headers=h).get_json(), {"ok": True})
        self.assertEqual(default(), {"First": False, "Second": True})
        self.assertEqual(c.post("/api/doc-templates/999/default", headers=h).status_code, 404)
        self.assertEqual(c.delete(f"/api/doc-templates/{second}", headers=h).get_json(), {"ok": True})
        self.assertEqual(default(), {"First": True}, "deleting the default hands it to another of the kind")
        self.assertEqual(c.delete(f"/api/doc-templates/{second}", headers=h).status_code, 404)
        self.assertEqual((self._audited("doc_template_default"), self._audited("doc_template_delete")), (1, 1))
        self.assertEqual(first, self.sql("SELECT id FROM doc_templates")[0][0])

    def test_validating_the_ai_server_queues_one_check_and_says_when_ai_is_off(self):
        c, h = self._admin()
        c.post("/settings/ai/validate", headers=h)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM ai_jobs")[0][0], 0, "AI is off: nothing queued")
        self._set_policy(ai_enabled="1", ai_base_url="http://192.168.1.238/v1", ai_model="P24-AI")
        c.post("/settings/ai/validate", headers=h)
        c.post("/settings/ai/validate", headers=h)
        self.assertEqual([tuple(r) for r in self.sql("SELECT kind, status FROM ai_jobs")], [("validate", "queued")], "asked twice, queued once")
        self.assertEqual(self._audited("validate_ai"), 2)

    # ---- the admin's test buttons: offline, so they say what failed ------------------

    def test_the_test_buttons_report_instead_of_raising(self):
        c, h = self._admin()
        r = c.post("/settings/integrations/test-email", headers=h)   # no email on the admin yet
        self.assertIn("Set your email on the Account page first", " ".join(r.get_json()["messages"]))
        self.sql("UPDATE users SET email = 'admin@odin.example' WHERE id = 1")
        with patch("graph.send_mail", return_value=(False, "not connected")):
            self.assertIn("Test email failed: not connected", " ".join(c.post("/settings/integrations/test-email", headers=h).get_json()["messages"]))
        with patch("graph.send_mail", return_value=(True, None)):
            self.assertIn("Test email sent to admin@odin.example", " ".join(c.post("/settings/integrations/test-email", headers=h).get_json()["messages"]))
        with patch("services.teams_bot.send", return_value=(False, "not installed")), patch("graph.teams_configured", return_value=False):
            self.assertIn("failed (not installed)", " ".join(c.post("/settings/integrations/test-teams", headers=h).get_json()["messages"]))
        with patch("services.teams_bot.send", return_value=(True, None)), patch("graph.teams_configured", return_value=True), patch("graph.send_teams_message", return_value=(True, None)):
            said = " ".join(c.post("/settings/integrations/test-teams", headers=h).get_json()["messages"])
        self.assertIn("Odin PMS to admin@odin.example: sent", said)
        self.assertIn("Channel: posted", said)
        self.assertEqual(self._audited("test_email"), 3)
        self.assertEqual(self._audited("test_teams"), 2)

    def test_the_webhook_and_share_buttons_check_before_they_post(self):
        c, h = self._admin()
        self.assertIn("Save a Teams Workflows webhook address first", " ".join(c.post("/settings/notifications/test-webhook", headers=h).get_json()["messages"]))
        self._set_policy(teams_webhook_url="https://hooks.example/x")
        with patch("graph.post_teams_webhook", return_value=(False, "HTTP 400")) as post:
            self.assertIn("The webhook refused it: HTTP 400", " ".join(c.post("/settings/notifications/test-webhook", headers=h).get_json()["messages"]))
        self.assertEqual(post.call_args.args[0], "https://hooks.example/x")
        self.assertEqual(self._audited("test_teams_webhook"), 2)
        # the share folder: unset, missing, then writable
        self.assertIn("Set the share folder path", " ".join(c.post("/settings/backups/test-share", headers=h).get_json()["messages"]))
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        self._set_policy(share_path=os.path.join(folder, "missing"))
        self.assertIn("doesn't exist on the server", " ".join(c.post("/settings/backups/test-share", headers=h).get_json()["messages"]))
        self._set_policy(share_path=folder)
        self.assertIn("is reachable and writable", " ".join(c.post("/settings/backups/test-share", headers=h).get_json()["messages"]))
        self.assertEqual(os.listdir(folder), [], "the probe file is removed")
        self.assertEqual(self._audited("backup_test_share"), 3)

    # ---- settings lists ------------------------------------------------------------------

    def test_a_document_category_goes_unless_a_document_uses_it(self):
        self.new_project(name="P", client="C")
        c, h = self._admin()
        c.post("/settings/doc-categories/add", data={"name": "Runbook"}, headers=h)
        c.post("/settings/doc-categories/add", data={"name": "Scratch"}, headers=h)
        ids = {r["name"]: r["id"] for r in self.sql("SELECT id, name FROM doc_categories")}
        self.client.post("/projects/1/documents", data={"category": "Runbook", "file": (io.BytesIO(b"hello"), "notes.txt")}, content_type="multipart/form-data")
        self.assertIn("document(s) use it", " ".join(c.post(f"/settings/doc-categories/{ids['Runbook']}/delete", headers=h).get_json()["messages"]))
        self.assertIn("deleted", " ".join(c.post(f"/settings/doc-categories/{ids['Scratch']}/delete", headers=h).get_json()["messages"]))
        names = {r["name"] for r in self.sql("SELECT name FROM doc_categories")}
        self.assertIn("Runbook", names)
        self.assertNotIn("Scratch", names)
        self.assertEqual(c.post("/settings/doc-categories/999/delete", headers=h).status_code, 404)
        self.assertEqual(self._audited("delete_doc_category"), 1)

    def test_a_partner_manager_deleted_comes_back_with_undo(self):
        c, h = self._admin()
        c.post("/settings/contacts/partners/add", data={"name": "Redington"}, headers=h)
        pid = c.get("/api/settings/contacts").get_json()["partners"][0]["id"]
        c.post(f"/settings/contacts/partners/{pid}/managers/add", data={"name": "Meera", "email": "meera@redington.example"}, headers=h)
        mid = c.get("/api/settings/contacts").get_json()["partners"][0]["managers"][0]["id"]
        r = c.post(f"/settings/contacts/partner-managers/{mid}/delete", headers=h).get_json()
        self.assertEqual(r["undo"], f"/undo/partner-manager/{mid}")
        self.assertEqual(c.get("/api/settings/contacts").get_json()["partners"][0]["managers"], [])
        self.assertEqual(c.post(r["undo"], headers=h).get_json()["messages"], ["Account manager restored"])
        self.assertEqual(c.get("/api/settings/contacts").get_json()["partners"][0]["managers"][0]["name"], "Meera")
        self.assertEqual(c.post(r["undo"], headers=h).status_code, 404, "nothing left to undo")
        self.assertEqual(c.post("/settings/contacts/partner-managers/999/delete", headers=h).status_code, 404)
        self.assertEqual((self._audited("delete_partner_manager"), self._audited("restore_partner_manager")), (1, 1))

    def test_a_stage_template_is_renamed_and_its_stages_reordered(self):
        c, h = self._admin()
        tpl = c.get("/api/settings").get_json()["templates"][0]
        tid, stages = tpl["id"], [s["name"] for s in tpl["stages"]]
        ids = [s["id"] for s in tpl["stages"]]
        self.assertIn("Template name required", " ".join(c.post(f"/settings/templates/{tid}/rename", data={"name": " "}, headers=h).get_json().get("messages", [])))
        c.post("/settings/templates/add", data={"name": "SIEM"}, headers=h)
        self.assertIn("already in use", " ".join(c.post(f"/settings/templates/{tid}/rename", data={"name": "SIEM"}, headers=h).get_json().get("messages", [])))
        c.post(f"/settings/templates/{tid}/rename", data={"name": "EDR standard"}, headers=h)
        self.assertEqual(c.get("/api/settings").get_json()["templates"][0]["name"], "EDR standard")
        c.post(f"/settings/templates/{tid}/stages/{ids[1]}/move", data={"direction": "up"}, headers=h)
        after = [s["name"] for s in c.get("/api/settings").get_json()["templates"][0]["stages"]]
        self.assertEqual(after[:2], [stages[1], stages[0]])
        self.assertEqual(after[2:], stages[2:])
        c.post(f"/settings/templates/{tid}/stages/{ids[1]}/move", data={"direction": "up"}, headers=h)   # now the first: it cannot go higher
        self.assertEqual([s["name"] for s in c.get("/api/settings").get_json()["templates"][0]["stages"]], after)
        self.assertEqual(c.post("/settings/templates/999/rename", data={"name": "x"}, headers=h).status_code, 404)
        self.assertEqual(self._audited("rename_stage_template"), 1, "only the rename that happened is audited")
        self.assertEqual(self._audited("move_template_stage"), 2)

    def test_declining_an_access_request_keeps_the_person_inactive(self):
        c, h = self._admin()
        self.sql("INSERT INTO users (username, password_hash, name, role, active, pending, email) VALUES ('stranger', 'x', 'Stan Ger', 'Viewer', 0, 1, 'stan@corp.example')")
        sid = self.sql("SELECT id FROM users WHERE username = 'stranger'")[0][0]
        self.assertEqual(c.post("/users/999/decline", headers=h).status_code, 404)
        self.assertEqual(c.post(f"/users/{sid}/decline", headers=h).get_json()["messages"], ["Declined Stan Ger"])
        self.assertEqual([tuple(r) for r in self.sql("SELECT active, pending FROM users WHERE id = ?", sid)], [(0, 0)])
        self.assertEqual(c.post(f"/users/{sid}/decline", headers=h).status_code, 404, "no longer pending")
        self.assertEqual(self._audited("decline_access"), 1)


class GoldenRoutesTestCase(Meta):
    """A15: every rule in the URL map, as every kind of caller, and the status it answers. The first
    gate (sign-in, permission, project role) decides most of these, so a changed permission, a
    route that lost its decorator or a new route shows up as a diff against tests/golden_routes.json."""

    GOLDEN = os.path.join(HERE, "tests", "golden_routes.json")
    ROLES = ["anon", "Admin", "Member", "Contributor", "Viewer", "Customer", "Reseller", "Contractor"]

    def _world(self):
        """Rollout 1 managed by Admin, with a task and a note; one account per role. Member and Contributor
        are on the rollout (Coordinator, Sales); the three outside parties are invited to it."""
        self.new_project(name="One", client="C")
        self.client.post("/projects/1/tasks", data={"title": "t"})
        self.client.post("/projects/1/note", data={"note": "n"})
        member, con = self._make_user("mem", "Member"), self._make_user("con", "Contributor")
        self._make_user("vie", "Viewer")
        self._on(1, member, "Coordinator")
        self._on(1, con, "Sales")
        anon = app_module.app.test_client()   # signed out, but with a session and its token, so a refusal is the route's, not the CSRF check's
        csrf = anon.get("/api/session").get_json()["csrf"]
        cookies = {"anon": (anon.get_cookie("session").value, csrf)}
        for role, username in (("Admin", "admin"), ("Member", "mem"), ("Contributor", "con"), ("Viewer", "vie")):
            c, csrf = self._api_client(username, "changeme" if username == "admin" else STRONG_PASSWORD)
            cookies[role] = (c.get_cookie("session").value, csrf)
        for role in ("Customer", "Reseller", "Contractor"):
            email = f"{role.lower()}@outside.example"
            self._invite(1, email, role, role)
            c = self._external_client(email)
            csrf = c.get("/api/session").get_json()["csrf"]   # first: it is what puts the token into the cookie
            cookies[role] = (c.get_cookie("session").value, csrf)
        return cookies

    @staticmethod
    def _url(rule):
        return CsrfExemptionsTestCase._url(rule)

    def _table(self):
        import requests
        from flask.testing import FlaskClient
        cookies = self._world()
        snap = sqlite3.connect(":memory:")   # the world, to put back after every request that may have changed it
        self.addCleanup(snap.close)
        with closing(self.raw_db()) as live:
            live.backup(snap)
        rules = sorted(((m, r.rule) for r in app_module.app.url_map.iter_rules() for m in r.methods
                        if m not in ("HEAD", "OPTIONS") and r.endpoint != "static"), key=lambda x: (x[1], x[0]))
        table = {}
        offline = patch.object(requests.sessions.Session, "request", side_effect=requests.ConnectionError("offline in tests"))
        quiet = patch("graph.send_mail", return_value=(False, "offline"))
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)
        with offline, quiet:
            for method, rule in rules:
                codes = []
                for role in self.ROLES:
                    client = FlaskClient(app_module.app, app_module.app.response_class)
                    headers = {}
                    if cookies[role]:
                        client.set_cookie("session", cookies[role][0])
                        headers["X-CSRF-Token"] = cookies[role][1]
                    kwargs = {"headers": headers}
                    if method in MUTATING:
                        kwargs["json"] = {}
                    response = client.open(self._url(rule), method=method, **kwargs)
                    codes.append(response.status_code)
                    response.close()
                    if method != "GET":
                        with closing(sqlite3.connect(db_module.DB_PATH)) as live:
                            snap.backup(live)
                table[f"{method} {rule}"] = " ".join(str(c) for c in codes)
        return table

    def test_roles_by_routes_match_the_golden_table(self):
        table = self._table()
        self.assertGreater(len(table), 200)
        if os.environ.get("ODIN_WRITE_GOLDEN"):
            os.makedirs(os.path.dirname(self.GOLDEN), exist_ok=True)
            with open(self.GOLDEN, "w") as fh:
                fh.write('{\n  "roles": ' + json.dumps(self.ROLES) + ',\n  "routes": {\n'
                         + ",\n".join(f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in table.items()) + "\n  }\n}\n")
            self.skipTest(f"golden table written: {len(table)} rows")
        with open(self.GOLDEN) as fh:
            golden = json.load(fh)
        self.assertEqual(golden["roles"], self.ROLES)
        old = golden["routes"]
        lines = [f"+ new route {k}: {table[k]}" for k in sorted(table.keys() - old.keys())]
        lines += [f"- route gone {k}" for k in sorted(old.keys() - table.keys())]
        for k in sorted(old.keys() & table.keys()):
            if old[k] != table[k]:
                moved = [f"{role} {a}->{b}" for role, a, b in zip(self.ROLES, old[k].split(), table[k].split()) if a != b]
                lines.append(f"~ {k}: {', '.join(moved)}")
        self.assertEqual(lines, [], "\nthe role x route table moved (" + str(len(lines)) + " rows). If that is intended, regenerate:\n"
                         "  ODIN_WRITE_GOLDEN=1 venv/bin/python -m unittest test_v18_meta.GoldenRoutesTestCase\n" + "\n".join(lines))
        self.assertNotIn("500", " ".join(table.values()).split(), "a route answered 500 to an empty request")


class ApiContractTestCase(Meta):
    """A14: the GET answers frontend/src/lib/api.ts depends on, from the seeded UAT world, kept as
    frontend/src/lib/__contract__/<TypeName>.json. This test fails when the server's answer changes
    shape from the file; src/lib/contract.test.ts fails when the file stops matching the TypeScript
    type of the same name. Between them the server and the client types cannot drift apart unseen.
    A deliberate change: regenerate with
        ODIN_WRITE_CONTRACT=1 venv/bin/python -m unittest test_v18_meta.ApiContractTestCase
    then fix api.ts until `npm --prefix frontend test` passes, and commit both."""

    DIR = os.path.join(HERE, "frontend", "src", "lib", "__contract__")
    ADMIN_PASSWORD = "Glacier-Harbour-4471"   # the seed's (scripts/seed_uat.py), a throw-away database
    KEEP = 2                                   # array items kept per list: enough to show each field's shape
    # (TypeScript type in api.ts, GET path, key to pick from the answer)
    ENDPOINTS = [
        ("User", "/api/session", "user"),
        ("FlowData", "/api/flow", None), ("FlowDetail", "/api/projects/1/flow", None),
        ("PlanData", "/api/projects/1/plan", None), ("GanttData", "/api/flow/plan", None),
        ("RolloutReport", "/api/projects/1/rollout-report?audience=internal", None),
        ("RaidData", "/api/projects/1/raid", None), ("MilestonesData", "/api/projects/1/milestones", None), ("ScopeData", "/api/projects/1/scope", None),
        ("SignoffData", "/api/projects/1/signoff", None), ("CalendarData", "/api/calendar?month={month}", None),
        ("DashboardData", "/api/dashboard", None), ("ProjectsData", "/api/projects", None),
        ("ProjectExtras", "/api/projects/1", None), ("SettingsData", "/api/settings?section=general", None),
        ("AIView", "/api/settings/ai", None), ("RbacData", "/api/settings/rbac", None),
        ("ContactsData", "/api/settings/contacts", None), ("UsersData", "/api/users", None),
        ("AuditData", "/api/audit", None), ("ReportAllData", "/api/reports/all", None),
        ("SignupLinks", "/api/signup-links", None), ("DocTemplatesData", "/api/doc-templates", None),
        ("MyWorkData", "/api/my-work", None), ("PeopleData", "/api/people", None),
        ("PersonData", "/api/people/2", None), ("WorkloadData", "/api/workload", None), ("AlertsData", "/api/alerts", None),
        ("AnalyticsData", "/api/analytics", None), ("SearchResults", "/api/search?q=a", None),
        ("ProjectFormData", "/api/project-form", None), ("LessonsData", "/api/projects/1/lessons", None),
        ("TwoStep", "/api/account/two-step", None),
        ("IntakeSettingsData", "/api/settings/intake", None), ("PendingIntake", "/api/intake/pending", None),
    ]

    @classmethod
    def _trim(cls, value):
        if isinstance(value, dict):
            return {k: cls._trim(v) for k, v in value.items()}
        if isinstance(value, list):
            return [cls._trim(v) for v in value[:cls.KEEP]]
        return value

    @classmethod
    def _paths(cls, value, at=""):
        """Every key path, arrays merged: 'rows[].id'. Values and types are the client test's business."""
        if isinstance(value, dict):
            out = {at} if at else set()
            for k, v in value.items():
                out |= cls._paths(v, f"{at}.{k}" if at else k)
            return out
        if isinstance(value, list):
            out = {at + "[]"} if value else {at + "[]?"}
            for v in value:
                out |= cls._paths(v, at + "[]")
            return out
        return {at}

    def _seeded_client(self):
        import subprocess
        import sys
        data = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, data, True)
        env = dict(os.environ, ODIN_DATA_DIR=data, SECRET_KEY="contract-not-secret")
        subprocess.run([sys.executable, os.path.join(HERE, "scripts", "seed_uat.py")], env=env, cwd=HERE, check=True, capture_output=True)
        with sqlite3.connect(os.path.join(data, "odin.db")) as seeded:   # its own file, WAL folded in
            seeded.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with sqlite3.connect(os.path.join(data, "odin.db")) as src, sqlite3.connect(db_module.DB_PATH) as dst:
            src.backup(dst)
        c, _ = self._api_client("admin", self.ADMIN_PASSWORD)
        return c

    def test_the_answers_api_ts_reads_keep_their_shape(self):
        from datetime import datetime
        c = self._seeded_client()
        month = datetime.utcnow().strftime("%Y-%m")   # the server's clock is UTC
        writing = bool(os.environ.get("ODIN_WRITE_CONTRACT"))
        if writing:
            os.makedirs(self.DIR, exist_ok=True)
        drift = []
        for type_name, path, pick in self.ENDPOINTS:
            r = c.get(path.format(month=month))
            self.assertEqual(r.status_code, 200, f"{path} answered {r.status_code}")
            body = r.get_json()
            sample = self._trim(body[pick] if pick else body)
            file = os.path.join(self.DIR, f"{type_name}.json")
            if writing:
                with open(file, "w") as fh:
                    json.dump(sample, fh, indent=1, sort_keys=True)
                    fh.write("\n")
                continue
            with open(file) as fh:
                kept = json.load(fh)
            old, new = self._paths(kept), self._paths(sample)
            if old != new:
                drift.append(f"{type_name} ({path}): " + ", ".join([f"+{p}" for p in sorted(new - old)] + [f"-{p}" for p in sorted(old - new)]))
        if writing:
            self.skipTest(f"{len(self.ENDPOINTS)} contract files written")
        self.assertEqual(drift, [], "\nthe server's answers changed shape. If that is intended, regenerate the files:\n"
                         "  ODIN_WRITE_CONTRACT=1 venv/bin/python -m unittest test_v18_meta.ApiContractTestCase\n")

    def test_every_endpoint_listed_has_a_type_in_api_ts(self):
        with open(os.path.join(HERE, "frontend", "src", "lib", "api.ts")) as fh:
            api = fh.read()
        for type_name, path, _ in self.ENDPOINTS:
            self.assertRegex(api, rf"export type {type_name}\b", f"{type_name} is not an exported type of api.ts")


class TestModulesListedTestCase(unittest.TestCase):
    """A test module that CI never runs is a test that cannot fail. Every top-level test_*.py is named
    in the CI workflow, in scripts/ci_local.sh and in CLAUDE.md."""

    def test_every_test_module_is_run_by_ci_and_by_the_local_gate(self):
        modules = sorted(f[:-3] for f in os.listdir(HERE) if re.fullmatch(r"test_\w+\.py", f))
        self.assertIn("test_v18_meta", modules)
        for where in (".github/workflows/ci.yml", "scripts/ci_local.sh", "CLAUDE.md"):
            with open(os.path.join(HERE, where)) as fh:
                text = fh.read()
            missing = [m for m in modules if not re.search(rf"\b{m}\b", text)]
            self.assertEqual(missing, [], f"{where} does not run {missing}")


if __name__ == "__main__":
    unittest.main()
