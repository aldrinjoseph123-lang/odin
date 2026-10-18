"""Odin 2.0, workstream 8: CRM intake (services/intake.py, routes/intake.py).
Run with: python -m unittest test_v2_intake"""
import io
import json
from unittest.mock import patch

from test_app import STRONG_PASSWORD, app_module
from test_fix_logic import FixBase

J = {"Accept": "application/json"}
CLOCK = __import__("datetime").datetime(2027, 3, 1, 9, 0, 0)   # a fixed minute: the rate limit counts the last 60 seconds

DEAL = {"client": "Acme Bank", "name": "Branch firewalls", "deal_id": "D-1001", "product": "FortiGate", "vendor": "Fortinet",
        "delivery_mode": "Outsourced", "target_date": "2027-06-30", "po_number": "PO-77"}


class IntakeBase(FixBase):
    def token(self, name="crm", scope="create", client=None):
        r = (client or self.client).post("/settings/api-tokens", data={"name": name, "days": "30", "scope": scope}, headers=J)
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["token"]

    def post(self, body, token=None, name="crm"):
        token = token or getattr(self, "_t", None) or self.token(name)
        self._t = token
        return app_module.app.test_client().post("/api/v1/intake", json=body, headers={"Authorization": f"Bearer {token}"})

    def names(self, query=""):
        return [r["name"] for r in self.client.get("/api/projects" + query).get_json()["rows"]]

    def row(self, pid=1):
        return self.sql("SELECT * FROM projects WHERE id = ?", pid)[0]

    def confirm(self, client=None, pid=1, **form):
        data = {"po_document": (io.BytesIO(b"%PDF-1.4 fake PO"), "po.pdf"), **form}
        return (client or self.client).post(f"/projects/{pid}/intake/confirm", data=data, headers=J, content_type="multipart/form-data")


class CreateTestCase(IntakeBase):
    def test_a_deal_becomes_a_pending_rollout_with_the_template_stages(self):
        r = self.post(DEAL)
        self.assertEqual(r.status_code, 201, r.get_json())
        body = r.get_json()
        self.assertEqual((body["created"], body["rollout"]["status"], body["rollout"]["deal_id"], body["warnings"]), (True, "pending", "D-1001", []))
        p = self.row(body["rollout"]["id"])
        self.assertEqual((p["intake_pending"], p["client"], p["name"], p["vendor_name"], p["product_name"], p["delivery_mode"], p["target_end_date"], p["po_number"], p["intake_source"]),
                         (1, "Acme Bank", "Branch firewalls", "Fortinet", "FortiGate", "Outsourced", "2027-06-30", "PO-77", "crm"))
        self.assertEqual(p["stage"], self.stages()[0])
        self.assertGreater(len(self.stages()), 1)
        self.assertEqual(self.sql("SELECT role FROM project_participants WHERE project_id = 1")[0][0], "Project manager")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tasks")[0][0], 0, "template tasks wait for the confirm")

    def test_only_the_three_required_keys_are_needed(self):
        r = self.post({"client": "C", "name": "N", "deal_id": "D-2"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.row()["delivery_mode"], "Distribution/MSSP")

    def test_a_repeat_deal_answers_200_with_the_same_rollout(self):
        first = self.post(DEAL).get_json()["rollout"]["id"]
        again = self.post(dict(DEAL, name="A different name", client="Other")).get_json()
        self.assertEqual((again["created"], again["rollout"]["id"], again["rollout"]["name"]), (False, first, "Branch firewalls"))
        self.assertEqual(self.post(DEAL).status_code, 200)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 1)
        self.assertEqual(self.audits("intake_create"), 1)
        self.assertEqual(self.post(dict(DEAL, deal_id="D-1002")).status_code, 201)   # another deal is another rollout
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 2)

    def test_calls_for_one_deal_at_the_same_moment_make_one_rollout(self):
        import threading
        token = self.token()
        codes = []

        def call():
            r = app_module.app.test_client().post("/api/v1/intake", json=DEAL, headers={"Authorization": f"Bearer {token}"})
            codes.append(r.status_code)
        threads = [threading.Thread(target=call) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(codes), [200] * 5 + [201])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 1)

    def test_a_confirmed_deal_still_answers_with_its_rollout_and_a_deleted_one_may_come_again(self):
        self.post(DEAL)
        self.assertEqual(self.confirm().status_code, 200)
        r = self.post(DEAL)
        self.assertEqual((r.status_code, r.get_json()["rollout"]["status"]), (200, "confirmed"))
        self.client.post("/projects/1/delete")
        again = self.post(DEAL)
        self.assertEqual((again.status_code, again.get_json()["rollout"]["id"]), (201, 2))

    def test_the_intake_is_audited_under_the_tokens_name(self):
        self.post(DEAL, name="crm-prod")
        row = self.sql("SELECT username, resource_type, resource_id, details FROM audit_logs WHERE action = 'intake_create'")[0]
        self.assertEqual((row["username"], row["resource_type"], row["resource_id"]), ("token:crm-prod", "project", 1))
        self.assertIn("source=crm-prod", row["details"])
        self.assertIn("deal=D-1001", row["details"])

    def test_the_default_owner_hears_of_it_and_the_policy_picks_who(self):
        member = self._make_user("pm2", "Member")
        self._set_policy(intake_owner=str(member))
        self.post(DEAL)
        self.assertEqual(self.row()["owner_id"], member)
        self.assertEqual(self.sql("SELECT user_id FROM notifications WHERE kind = 'assigned'")[0][0], member)
        self._set_policy(intake_owner="9999")   # gone: the first Admin holds it
        self.post(dict(DEAL, deal_id="D-9"))
        self.assertEqual(self.row(2)["owner_id"], 1)

    def test_the_template_policy_picks_the_stage_list(self):
        self.client.post("/settings/templates/add", data={"name": "Quick"})
        tid = self.sql("SELECT id FROM stage_templates WHERE name = 'Quick'")[0][0]
        self._set_policy(intake_template=str(tid))
        self.post(DEAL)
        self.assertEqual(self.row()["stage_template_id"], tid)


class ScopeTestCase(IntakeBase):
    def test_a_read_token_cannot_post_and_a_create_token_cannot_read(self):
        read, create = self.token("bi", "read"), self.token("crm", "create")
        self.assertEqual(self.post(DEAL, token=read).status_code, 403)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 0)
        bearer = app_module.app.test_client()
        for path in ("/api/v1/projects", "/api/v1/projects/1", "/api/v1/projects/1/report"):
            r = bearer.get(path, headers={"Authorization": f"Bearer {create}"})
            self.assertEqual(r.status_code, 403, path)
            self.assertIn("needs a token with the read scope", r.get_json()["error"])
        self.assertEqual(bearer.get("/api/v1/projects", headers={"Authorization": f"Bearer {read}"}).status_code, 200)
        self.assertEqual(self.post(DEAL, token=create).status_code, 201)

    def test_no_token_a_bad_token_and_a_revoked_token_are_401(self):
        anon = app_module.app.test_client()
        self.assertEqual(anon.post("/api/v1/intake", json=DEAL).status_code, 401)
        self.assertEqual(anon.post("/api/v1/intake", json=DEAL, headers={"Authorization": "Bearer odin_nope"}).status_code, 401)
        self.assertEqual(anon.get("/api/v1/intake", headers={"Authorization": "Bearer odin_nope"}).status_code, 405)
        token = self.token()
        tid = self.client.get("/api/settings/intake").get_json()["tokens"][0]["id"]
        self.client.post(f"/settings/api-tokens/{tid}/revoke")
        self.assertEqual(self.post(DEAL, token=token).status_code, 401)

    def test_a_session_alone_does_not_open_the_endpoint_and_the_scope_is_audited(self):
        self.assertEqual(self.client.post("/api/v1/intake", json=DEAL).status_code, 401)
        self.token()
        self.assertIn("create (intake)", self.sql("SELECT details FROM audit_logs WHERE action = 'create_api_token'")[0][0])
        self.assertEqual(self.client.post("/settings/api-tokens", data={"name": "x", "days": "30", "scope": "admin"}, headers=J).status_code, 400)

    def test_a_pending_rollout_is_not_in_the_read_api(self):
        self.post(DEAL)
        read = self.token("bi", "read")
        h = {"Authorization": f"Bearer {read}"}
        bearer = app_module.app.test_client()
        self.assertEqual(bearer.get("/api/v1/projects?all=1", headers=h).get_json()["projects"], [])
        self.assertEqual(bearer.get("/api/v1/projects/1", headers=h).status_code, 404)
        self.assertEqual(bearer.get("/api/v1/projects/1/report", headers=h).status_code, 404)

    def test_sources_limit_which_tokens_may_send(self):
        self._set_policy(intake_sources="CRM-Prod, other")
        self.assertEqual(self.post(DEAL, name="crm").status_code, 403)
        self.assertEqual(self.post(DEAL, token=self.token("crm-prod")).status_code, 201)
        calls = self.client.get("/api/settings/intake").get_json()["calls"]
        self.assertEqual([(c["token_name"], c["status"], c["result"]) for c in calls], [("crm-prod", 201, "created"), ("crm", 403, "refused")])


class ConfirmTestCase(IntakeBase):
    def test_confirming_needs_the_po_and_takes_ownership(self):
        self.post(DEAL)
        stage_id = self.sql("SELECT s.id FROM stage_template_stages s JOIN projects p ON p.stage_template_id = s.template_id AND s.name = p.stage WHERE p.id = 1")[0][0]
        self.sql("INSERT INTO template_tasks (stage_id, title, role, offset_days) VALUES (?, 'Kick-off call', 'Project manager', 2)", stage_id)
        member = self._make_user("pm3", "Member")
        c, _ = self._api_client("pm3", STRONG_PASSWORD)
        no_po = c.post("/projects/1/intake/confirm", data={}, headers=J)
        self.assertEqual(no_po.status_code, 400)
        self.assertIn("Attach", no_po.get_json()["messages"][0])
        self.assertEqual(self.row()["intake_pending"], 1)
        ok = self.confirm(c, po_number="PO-88")
        self.assertEqual(ok.status_code, 200, ok.get_json())
        self.assertEqual(ok.get_json()["location"], "/projects/1")
        p = self.row()
        self.assertEqual((p["intake_pending"], p["owner_id"], p["po_number"]), (0, member, "PO-88"))
        self.assertEqual(self.sql("SELECT category FROM documents WHERE project_id = 1")[0][0], "Client PO")
        self.assertEqual(self.sql("SELECT role FROM project_participants WHERE project_id = 1 AND role = 'Project manager'")[0][0], "Project manager")
        self.assertEqual(self.sql("SELECT assignee_id FROM tasks WHERE project_id = 1 AND title = 'Kick-off call'")[0][0], member)
        row = self.sql("SELECT username, details FROM audit_logs WHERE action = 'intake_confirm'")[0]
        self.assertIn("po=po.pdf", row["details"])
        self.assertIn("source=crm", row["details"])
        again = self.confirm(c)
        self.assertEqual(again.status_code, 400)
        self.assertIn("not waiting", again.get_json()["messages"][0])

    def test_a_contributor_names_a_manager_who_can_move_stages(self):
        self.post(DEAL)
        self._make_user("sales", "Contributor")
        c, _ = self._api_client("sales", STRONG_PASSWORD)
        self.assertEqual(self.confirm(c).status_code, 400)
        self.assertEqual(self.row()["intake_pending"], 1)
        self.assertEqual(self.confirm(c, owner_id="1").status_code, 200)
        self.assertEqual(self.row()["owner_id"], 1)

    def test_a_viewer_cannot_confirm_and_a_bad_file_is_refused(self):
        self.post(DEAL)
        self._make_user("watcher", "Viewer")
        v, _ = self._api_client("watcher", STRONG_PASSWORD)
        self.assertEqual(self.confirm(v).status_code, 403)
        bad = self.client.post("/projects/1/intake/confirm", data={"po_document": (io.BytesIO(b"not a pdf at all"), "po.pdf")},
                               headers=J, content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.row()["intake_pending"], 1)

    def test_the_crm_contacts_stay_on_the_rollout_as_a_staff_note(self):
        self.post(dict(DEAL, contacts=["Ann@Acme.example", "bob@acme.example"]))
        self.assertEqual(json.loads(self.row()["intake_contacts"]), ["ann@acme.example", "bob@acme.example"])
        self.confirm()
        note = self.sql("SELECT note, guest_visible FROM status_notes WHERE project_id = 1")[0]
        self.assertEqual(note["guest_visible"], 0)
        self.assertIn("ann@acme.example, bob@acme.example", note["note"])

    def test_a_pending_rollout_cannot_move_stage_or_open_a_guest_link(self):
        self.post(dict(DEAL, delivery_mode="Outsourced"))
        moved = self.client.post("/api/projects/1/stage", json={"stage": self.stages()[1]})
        self.assertEqual(moved.status_code, 400)
        self.assertIn("Confirm this intake first", moved.get_json()["error"])
        p = self.row()
        self.assertEqual(app_module.app.test_client().get(f"/guest/{p['access_token']}").status_code, 404)
        self.assertEqual(app_module.app.test_client().get(f"/guest/{p['customer_token']}").status_code, 404)

    def test_discarding_a_pending_intake_is_the_ordinary_delete(self):
        self.post(DEAL)
        self.assertEqual(self.client.post("/projects/1/delete", headers=J).status_code, 200)
        self.assertEqual(self.client.get("/api/intake/pending").get_json()["rows"], [])


class ExcludedTestCase(IntakeBase):
    """Pending is not open and not closed: no lane, count, alert, dashboard figure or report has it."""

    def world(self):
        self.new_project(name="Real", client="C", target_end_date="2020-01-01")   # overdue: an alert, a lane
        self.post(dict(DEAL, target_date="2020-01-01"))                              # would be overdue too, were it live

    def test_the_flow_the_lists_and_the_counts_do_not_have_it(self):
        self.world()
        flow = self.client.get("/api/flow").get_json()
        self.assertEqual([r["name"] for r in flow["rows"]], ["Real"])
        self.assertEqual(sum(flow["counts"][k] for k in ("overdue", "over_sla", "due_soon", "on_track")), 1)
        for q, want in (("", ["Real"]), ("?closed=1", ["Real"]), ("?view=overdue", ["Real"]), ("?view=stale", []), ("?view=at_risk", []),
                        ("?stage=" + self.stages()[0], ["Real"])):
            self.assertEqual(self.names(q), want, q)
        listing = self.client.get("/api/projects").get_json()
        self.assertEqual((listing["total"], listing["pending"]), (1, 1))
        self.assertNotIn("Branch firewalls", self.client.get("/projects/export.csv").data.decode())
        self.assertNotIn("Branch firewalls", [r["name"] for r in self.client.get("/api/flow/plan").get_json()["rows"]])
        cal = self.client.get("/api/calendar?month=2020-01").get_json()
        self.assertNotIn("Branch firewalls", json.dumps(cal))

    def test_the_dashboard_alerts_and_reports_do_not_have_it(self):
        self.world()
        __import__("scheduler").sync_alerts()
        alerts = self.sql("SELECT project_id FROM alerts WHERE resolved = 0")
        self.assertEqual({a[0] for a in alerts}, {1})
        self.assertEqual({a["project_name"] for a in self.client.get("/api/alerts").get_json()["rows"]}, {"Real"})
        self.assertNotIn("Branch firewalls", json.dumps(self.client.get("/api/dashboard").get_json()))
        folio = self.client.get("/api/reports/all").get_json()
        self.assertEqual([r["name"] for r in folio["rows"]], ["Real"])
        nav = self.client.get("/api/session").get_json()["user"]["nav"]
        self.assertEqual(nav["active_alert_count"], len(alerts))
        people = self.client.get("/api/people").get_json()
        self.assertEqual(sum(p["projects"] for p in people["people"]), 1)

    def test_confirming_brings_it_into_every_one_of_them(self):
        self.world()
        self.assertEqual(self.confirm(pid=2).status_code, 200)
        __import__("scheduler").sync_alerts()
        self.assertEqual({r["name"] for r in self.client.get("/api/flow").get_json()["rows"]}, {"Real", "Branch firewalls"})
        self.assertEqual({a[0] for a in self.sql("SELECT project_id FROM alerts WHERE resolved = 0")}, {1, 2})
        self.assertEqual(self.client.get("/api/projects").get_json()["pending"], 0)
        self.assertEqual(len(self.client.get("/api/reports/all").get_json()["rows"]), 2)

    def test_the_pending_view_lists_only_the_intakes(self):
        self.world()
        self.assertEqual(self.names("?view=pending"), ["Branch firewalls"])
        self.assertEqual(self.names("?view=pending&closed=1"), ["Branch firewalls"])
        pend = self.client.get("/api/intake/pending").get_json()
        self.assertEqual([(r["name"], r["source"], r["deal_id"], r["owner_name"]) for r in pend["rows"]], [("Branch firewalls", "crm", "D-1001", "Admin")])
        self.assertTrue(pend["can_confirm"] and pend["can_lead"])
        self.assertEqual(pend["po_category"], "Client PO")

    def test_a_partner_never_sees_pending_intakes(self):
        self.world()
        self._invite(1, "cee@cust.example", "Customer")
        c = self._external_client("cee@cust.example")
        self.assertEqual(c.get("/api/intake/pending").status_code, 403)
        self.assertEqual(c.get("/api/projects?view=pending").get_json()["rows"], [])
        self.assertEqual(c.get("/api/projects").get_json()["pending"], 0)
        self.assertEqual(c.get("/api/projects/2").status_code, 404)


class ValidationTestCase(IntakeBase):
    def refused(self, body, words, status=400):
        r = self.post(body)
        self.assertEqual(r.status_code, status, r.get_json())
        self.assertIn(words, r.get_json()["error"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 0)

    def test_required_keys_types_and_lengths(self):
        self.refused({}, "client is required")
        self.refused({"client": "C", "name": "N"}, "deal_id is required")
        self.refused(dict(DEAL, client=12), "client: send text")
        self.refused(dict(DEAL, name=["x"]), "name: send text")
        self.refused(dict(DEAL, client="x" * 201), "client: at most 200 characters")
        self.refused(dict(DEAL, deal_id="d" * 81), "deal_id: at most 80 characters")
        self.refused(dict(DEAL, po_number="p" * 61), "po_number: at most 60")
        self.refused(dict(DEAL, product="p" * 121), "product: at most 120")
        self.refused(dict(DEAL, name="bad\x00name"), "plain text")
        self.refused(dict(DEAL, delivery_mode="Teleport"), "delivery_mode")
        self.refused(dict(DEAL, target_date="30/06/2027"), "target_date")
        self.refused(dict(DEAL, target_date=20270630), "target_date")

    def test_unknown_keys_and_bodies_that_are_not_objects(self):
        self.refused(dict(DEAL, budget=5), "Unknown field: budget")
        self.refused(dict(DEAL, budget=5, margin=1), "Unknown fields: budget, margin")
        token = self.token()
        h = {"Authorization": f"Bearer {token}"}
        c = app_module.app.test_client()
        self.assertEqual(c.post("/api/v1/intake", data="not json", headers=h).status_code, 400)
        self.assertEqual(c.post("/api/v1/intake", json=["a"], headers=h).status_code, 400)
        self.assertEqual(c.post("/api/v1/intake", headers=h).status_code, 400)

    def field(self, name, kind="text", **extra):
        r = self.client.post("/api/fields", json={"name": name, "kind": kind, **extra})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["id"]

    def test_custom_fields_by_name_or_id_typed_and_unknown_ones_refused(self):
        region = self.field("Region", "choice", choices=["UAE", "KSA"])
        seats = self.field("Seats", "number")
        r = self.post(dict(DEAL, fields={"region": "KSA", str(seats): "1,200"}))
        self.assertEqual(r.status_code, 201, r.get_json())
        vals = {f["name"]: f["value"] for f in self.client.get("/api/projects/1/fields").get_json()["fields"]}
        self.assertEqual(vals, {"Region": "KSA", "Seats": 1200})
        self.assertIn("Region: — → KSA", self.sql("SELECT details FROM audit_logs WHERE action = 'intake_create'")[0][0])
        bad = self.post(dict(DEAL, deal_id="D-2", fields={"Colour": "red"}))
        self.assertEqual(bad.status_code, 400)
        self.assertIn("unknown custom field Colour", bad.get_json()["error"])
        self.assertEqual(self.post(dict(DEAL, deal_id="D-3", fields={"999": "x"})).status_code, 400)
        self.assertIn("Region: pick one of", self.post(dict(DEAL, deal_id="D-4", fields={"Region": "Mars"})).get_json()["error"])
        self.assertIn("Seats: a number", self.post(dict(DEAL, deal_id="D-5", fields={"Seats": "many"})).get_json()["error"])
        self.assertEqual(self.post(dict(DEAL, deal_id="D-6", fields=[1])).status_code, 400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 1)

    def test_a_required_custom_field_must_be_sent(self):
        self.field("Region", "text", required=True)
        self.refused(DEAL, "Region is required")
        self.assertEqual(self.post(dict(DEAL, fields={"Region": "UAE"})).status_code, 201)

    def test_contacts_follow_the_external_domain_policy(self):
        self._set_policy(external_domains="acme.example")
        r = self.post(dict(DEAL, contacts=["ann@acme.example", "spy@evil.example", "ann@ACME.example"]))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(json.loads(self.row()["intake_contacts"]), ["ann@acme.example"])
        self.assertEqual(len(r.get_json()["warnings"]), 1)
        self.assertIn("spy@evil.example was dropped", r.get_json()["warnings"][0])
        self.assertEqual(self.post(dict(DEAL, deal_id="D-2")).get_json()["warnings"], [])
        self.refused_contacts(["not an email"], "not an email address")
        self.refused_contacts("ann@acme.example", "a list of at most 10")
        self.refused_contacts([f"a{i}@acme.example" for i in range(11)], "a list of at most 10")
        self.refused_contacts([5], "a list of at most 10")

    def refused_contacts(self, contacts, words):
        r = self.post(dict(DEAL, deal_id="D-x", contacts=contacts))
        self.assertEqual(r.status_code, 400)
        self.assertIn(words, r.get_json()["error"])

    def test_with_no_domain_policy_any_well_formed_contact_is_kept(self):
        r = self.post(dict(DEAL, contacts=["x@anywhere.example"]))
        self.assertEqual((r.get_json()["warnings"], json.loads(self.row()["intake_contacts"])), ([], ["x@anywhere.example"]))

    def test_no_stage_template_means_a_clear_409(self):
        self.sql("DELETE FROM stage_template_stages WHERE template_id = (SELECT MIN(id) FROM stage_templates)")
        r = self.post(DEAL)
        self.assertEqual(r.status_code, 409)
        self.assertIn("Intake is not set up", r.get_json()["error"])


class RateAndLogTestCase(IntakeBase):
    def test_a_token_is_limited_per_minute_and_another_is_not(self):
        self._set_policy(intake_rate_per_min="2")
        other = self.token("other")
        mine = self.token("crm")
        with patch("services.intake._now", return_value=CLOCK):
            codes = [self.post(dict(DEAL, deal_id=f"D-{i}"), token=mine).status_code for i in range(4)]
            self.assertEqual(codes, [201, 201, 429, 429])
            r = self.post(dict(DEAL, deal_id="D-9"), token=mine)
            self.assertEqual((r.status_code, r.headers["Retry-After"]), (429, "60"))
            self.assertIn("at most 2 a minute", r.get_json()["error"])
            self.assertEqual(self.post(dict(DEAL, deal_id="D-other"), token=other).status_code, 201)
        with patch("services.intake._now", return_value=CLOCK.replace(minute=2)):
            self.assertEqual(self.post(dict(DEAL, deal_id="D-late"), token=mine).status_code, 201)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 4)   # the refused ones made nothing

    def test_a_refused_call_counts_towards_the_limit_and_a_repeat_too(self):
        self._set_policy(intake_rate_per_min="2")
        with patch("services.intake._now", return_value=CLOCK):
            self.assertEqual(self.post({"client": "C"}).status_code, 400)
            self.assertEqual(self.post(DEAL).status_code, 201)
            self.assertEqual(self.post(DEAL).status_code, 429)

    def test_the_rate_policy_has_limits(self):
        r = self.client.post("/settings/policies/intake", data={"intake_rate_per_min": "500"}, headers=J)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post("/settings/policies/intake", data={"intake_rate_per_min": "5"}, headers=J).status_code, 200)
        self.assertEqual(self.audits("update_policies"), 1)

    def test_the_log_keeps_the_newest_rows_and_the_page_shows_ten(self):
        with patch("services.intake.LOG_KEEP", 12), patch("services.intake._now", return_value=CLOCK):
            self._set_policy(intake_rate_per_min="100")
            for i in range(15):
                self.post(dict(DEAL, deal_id=f"D-{i}"))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM intake_calls")[0][0], 12)   # the newest LOG_KEEP
        page = self.client.get("/api/settings/intake").get_json()
        self.assertEqual(len(page["calls"]), 10)
        self.assertEqual(page["calls"][0]["deal_id"], "D-14")
        self.assertEqual(page["calls"][0]["result"], "created")
        self.assertEqual(page["calls"][0]["project_id"], 15)

    def test_results_are_logged_for_every_outcome(self):
        self.post(DEAL)
        self.post(DEAL)
        self.post({"client": "C", "name": "N", "deal_id": "D-b", "wat": 1})
        got = [(c["status"], c["result"]) for c in self.client.get("/api/settings/intake").get_json()["calls"]]
        self.assertEqual(got, [(400, "refused"), (200, "duplicate"), (201, "created")])
        self.assertIn("Unknown field: wat", self.client.get("/api/settings/intake").get_json()["calls"][0]["detail"])


class SettingsTestCase(IntakeBase):
    def test_the_settings_page_lists_create_tokens_only_and_is_for_admins(self):
        self.token("crm", "create")
        self.token("bi", "read")
        page = self.client.get("/api/settings/intake").get_json()
        self.assertEqual([t["name"] for t in page["tokens"]], ["crm"])
        self.assertEqual({p["key"] for p in page["policies"]}, {"intake_template", "intake_owner", "intake_sources", "intake_rate_per_min", "intake_token_days", "intake_allowed_ips"})
        self.assertEqual(page["endpoint"], "/api/v1/intake")
        self.assertEqual([t["name"] for t in self.client.get("/api/settings?section=api").get_json()["api_tokens"]], ["bi"])
        self._make_user("member1", "Member")
        c, _ = self._api_client("member1", STRONG_PASSWORD)
        self.assertEqual(c.get("/api/settings/intake").status_code, 403)

    def test_the_defaults_save_through_the_one_policy_route(self):
        owner = self._make_user("lead", "Member")
        r = self.client.post("/settings/policies/intake", data={"intake_owner": str(owner), "intake_sources": "crm, crm-test", "intake_template": "", "intake_rate_per_min": "10"}, headers=J)
        self.assertEqual(r.status_code, 200, r.get_json())
        page = self.client.get("/api/settings/intake").get_json()
        self.assertEqual({p["key"]: p["value"] for p in page["policies"]}, {"intake_owner": str(owner), "intake_sources": "crm, crm-test", "intake_template": "", "intake_rate_per_min": 10,
                                                                          "intake_token_days": 365, "intake_allowed_ips": ""})
        self.assertIn(owner, [o["id"] for o in page["owners"]])
        bad = self.client.post("/settings/policies/intake", data={"intake_owner": "99999"}, headers=J)
        self.assertEqual(bad.status_code, 400)
