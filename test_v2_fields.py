"""Odin 2.0, workstream 1: custom fields per rollout (services/fields.py,
routes/fields.py). Run with: python -m unittest test_v2_fields"""
import csv
import io
import json

from test_app import STRONG_PASSWORD, app_module
from test_fix_logic import FixBase

J = {"Accept": "application/json"}


class FieldsBase(FixBase):
    def send(self, method, url, body, client=None):
        """PUT / DELETE with the session's CSRF token (the shared test client adds it to POSTs only)."""
        c = client or self.client
        with c.session_transaction() as sess:
            token = sess.setdefault("_csrf_token", "t" * 43)
        return c.open(url, method=method, json=body, headers={"X-CSRF-Token": token})

    def field(self, name, kind="text", **extra):
        r = self.client.post("/api/fields", json={"name": name, "kind": kind, **extra})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["id"]

    def set_values(self, values, pid=1, client=None):
        return self.send("PUT", f"/api/projects/{pid}/fields", {"values": values}, client)

    def world(self):
        """A rollout with a field the customer sees (Region) and one they never do (Margin note)."""
        self.region = self.field("Region", "choice", choices=["UAE", "KSA"], customer_visible=True, show_in_list=True)
        self.secret = self.field("Internal ref", "text", show_in_list=True)
        self.new_project(name="P", client="C")
        self.assertEqual(self.set_values({str(self.region): "UAE", str(self.secret): "hush-42"}).status_code, 200)

    def customer(self):
        self._invite(1, "cee@cust.example", "Customer")
        return self._external_client("cee@cust.example")


class KindsTestCase(FieldsBase):
    def test_each_kind_parses_or_refuses(self):
        from services.fields import parse_value
        self.ctx()
        f = lambda kind, **x: {"name": "F", "kind": kind, "choices": ["A", "B"], **x}   # noqa: E731
        ok = [("text", "  one line\nmore ", "one line more"), ("number", "1,200", "1200"), ("number", 4.5, "4.5"), ("number", "12.0", "12"),
              ("date", "2026-11-03", "2026-11-03"), ("choice", "B", "B"), ("yesno", True, "1"), ("yesno", "no", "0"), ("yesno", "1", "1"),
              ("text", "", None), ("number", None, None)]
        for kind, raw, want in ok:
            self.assertEqual(parse_value(f(kind), raw), want, (kind, raw))
        bad = [("text", "x" * 201), ("text", ["a"]), ("number", "twelve"), ("number", "nan"), ("number", True), ("date", "3 Nov 2026"),
               ("date", "1999-01-01"), ("choice", "C"), ("yesno", "maybe"), ("yesno", 2)]
        for kind, raw in bad:
            with self.assertRaises(ValueError, msg=(kind, raw)) as e:
                parse_value(f(kind), raw)
            self.assertTrue(str(e.exception).startswith("F: "), str(e.exception))   # the field's name leads the words

    def test_values_read_back_typed(self):
        self.world()
        seats = self.field("Seats", "number"); live = self.field("Live", "yesno"); due = self.field("Go-live", "date")
        self.assertEqual(self.set_values({seats: "120", live: "yes", due: "2026-12-01"}).status_code, 200)
        got = {f["name"]: f["value"] for f in self.client.get("/api/projects/1/fields").get_json()["fields"]}
        self.assertEqual(got, {"Region": "UAE", "Internal ref": "hush-42", "Seats": 120, "Live": True, "Go-live": "2026-12-01"})

    def test_unknown_field_ids_and_bad_values_are_refused(self):
        self.world()
        self.assertEqual(self.set_values({"999": "x"}).status_code, 400)
        self.assertEqual(self.set_values({"abc": "x"}).status_code, 400)
        r = self.set_values({str(self.region): "Mars"})
        self.assertEqual(r.status_code, 400); self.assertIn("Region: pick one of UAE, KSA", r.get_json()["error"])
        self.assertEqual(self.send("PUT", "/api/projects/1/fields", {"values": ["x"]}).status_code, 400)
        self.assertEqual(self.sql("SELECT value FROM project_field_values WHERE field_id = ?", self.region)[0][0], "UAE")   # nothing changed


class DefinitionsTestCase(FieldsBase):
    def test_cap_is_a_policy(self):
        self._set_policy(custom_fields_max="2")
        self.field("A"); self.field("B")
        r = self.client.post("/api/fields", json={"name": "C", "kind": "text"})
        self.assertEqual(r.status_code, 400); self.assertIn("At most 2", r.get_json()["error"])
        self.assertEqual(self.client.get("/api/fields").get_json()["max"], 2)

    def test_definitions_are_checked(self):
        self.field("Region")
        for body, words in [({"name": "region", "kind": "text"}, "already"), ({"name": "X", "kind": "colour"}, "Pick a kind"),
                            ({"name": "{bad}", "kind": "text"}, "cannot hold"), ({"name": "", "kind": "text"}, "Name the field"),
                            ({"name": "Y", "kind": "choice", "choices": []}, "choices")]:
            r = self.client.post("/api/fields", json=body)
            self.assertEqual(r.status_code, 400, body); self.assertIn(words, r.get_json()["error"])

    def test_only_admins_define_fields(self):
        self._make_user("mem", "Member")
        c, csrf = self._api_client("mem", STRONG_PASSWORD)
        self.assertEqual(c.post("/api/fields", json={"name": "A", "kind": "text"}, headers={"X-CSRF-Token": csrf}).status_code, 403)
        self.assertEqual(c.get("/api/fields").status_code, 403)

    def test_rename_keeps_values_and_a_used_choice_stays(self):
        self.world()
        self.assertEqual(self.send("PUT", f"/api/fields/{self.region}", {"name": "Country", "choices": ["UAE", "KSA", "Oman"]}).status_code, 200)
        self.assertEqual({f["name"]: f["value"] for f in self.client.get("/api/projects/1/fields").get_json()["fields"]}["Country"], "UAE")
        self.assertIn("renamed from Region", self.sql("SELECT details FROM audit_logs WHERE action = 'update_custom_field'")[0][0])
        r = self.send("PUT", f"/api/fields/{self.region}", {"name": "Country", "choices": ["KSA"]})
        self.assertEqual(r.status_code, 400); self.assertIn("still use UAE", r.get_json()["error"])
        r = self.send("PUT", f"/api/fields/{self.region}", {"name": "Country", "kind": "text"})
        self.assertEqual(r.status_code, 400); self.assertIn("kind cannot change", r.get_json()["error"])

    def test_delete_needs_the_typed_name_and_archives_the_values(self):
        self.world()
        r = self.send("DELETE", f"/api/fields/{self.secret}", {"confirm": "internal ref"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.send("DELETE", f"/api/fields/{self.secret}", {"confirm": "Internal ref"}).status_code, 200)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM project_field_values WHERE field_id = ?", self.secret)[0][0], 0)
        archive = json.loads(self.sql("SELECT details FROM audit_logs WHERE action = 'delete_custom_field'")[0][0])
        self.assertEqual(archive, {"field": "Internal ref", "kind": "text", "count": 1, "values": [[1, "hush-42"]]})

    def test_move_reorders(self):
        a, b = self.field("A"), self.field("B")
        self.client.post(f"/api/fields/{b}/move", json={"step": -1})
        self.assertEqual([f["name"] for f in self.client.get("/api/fields").get_json()["fields"]], ["B", "A"])
        self.assertEqual(self.client.post(f"/api/fields/{a}/move", json={"step": 5}).status_code, 400)


class FormsTestCase(FieldsBase):
    def test_required_at_create_is_enforced_by_the_server(self):
        fid = self.field("Region", "choice", choices=["UAE", "KSA"], required=True)
        self.new_project(name="P", client="C")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 0)
        self.new_project(name="P", client="C", **{f"field_{fid}": "Mars"})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 0)
        self.new_project(name="P", client="C", **{"field_999": "x", f"field_{fid}": "KSA"})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM projects")[0][0], 0)   # an unknown field id is refused
        self.new_project(name="P", client="C", **{f"field_{fid}": "KSA"})
        self.assertEqual(self.sql("SELECT value FROM project_field_values WHERE project_id = 1")[0][0], "KSA")
        form = self.client.get("/api/project-form?edit=1").get_json()["custom_fields"]
        self.assertEqual([(f["name"], f["value"], f["required"]) for f in form], [("Region", "KSA", True)])

    def test_a_value_change_is_audited_with_old_and_new(self):
        self.world()
        self.client.post("/projects/1/edit", data={"name": "P", "client": "C", f"field_{self.region}": "KSA", f"field_{self.secret}": ""})
        rows = [r[0] for r in self.sql("SELECT details FROM audit_logs WHERE action = 'update_field_values' ORDER BY id")]
        self.assertEqual(rows[-1], "Region: UAE → KSA; Internal ref: hush-42 → —")
        self.set_values({str(self.region): "KSA"})   # no change, no row
        self.assertEqual(self.audits("update_field_values"), len(rows))

    def test_only_who_may_edit_the_rollout_sets_values(self):
        self.world()
        self._make_user("vw", "Viewer")
        c, csrf = self._api_client("vw", STRONG_PASSWORD)
        self.assertEqual(c.open("/api/projects/1/fields", method="PUT", json={"values": {}}, headers={"X-CSRF-Token": csrf}).status_code, 403)
        self.assertFalse(c.get("/api/projects/1/fields").get_json()["can_edit"])


class CustomerCutTestCase(FieldsBase):
    def test_externals_see_only_customer_visible_fields(self):
        self.world()
        ext = self.customer()
        self.assertEqual([f["name"] for f in ext.get("/api/projects/1/fields").get_json()["fields"]], ["Region"])
        self.assertFalse(ext.get("/api/projects/1/fields").get_json()["can_edit"])
        listing = ext.get("/api/projects").get_json()
        self.assertEqual([c["name"] for c in listing["fields"]], ["Region"]); self.assertEqual(listing["rows"][0]["fields"], ["UAE"])
        self.assertNotIn(b"hush-42", ext.get("/api/projects").data)
        # a filter on a field they cannot see is ignored, not a way to probe its values
        self.assertEqual(ext.get(f"/api/projects?field.{self.secret}=nope").get_json()["total"], 1)
        self.assertEqual(self.set_values({str(self.region): "KSA"}, client=ext).status_code, 403)
        csv_text = ext.get("/projects/export.csv").data.decode()
        self.assertIn("Region", csv_text); self.assertNotIn("Internal ref", csv_text); self.assertNotIn("hush-42", csv_text)
        port = ext.get("/api/reports/all").get_json()["rows"][0]["fields"]
        self.assertEqual(port, {"Region": "UAE"})

    def test_the_customer_report_never_carries_hidden_fields(self):
        self.world()
        inner = self.client.get("/api/projects/1/rollout-report?audience=internal").get_json()["data"]["fields"]
        self.assertEqual({f["name"] for f in inner}, {"Region", "Internal ref"})
        cut = self.client.get("/api/projects/1/rollout-report?audience=customer").get_json()["data"]["fields"]
        self.assertEqual([(f["name"], f["value"]) for f in cut], [("Region", "UAE")])
        # a saved version is cut again when the customer reads it
        self.ctx()
        from services.report_data import customer_view
        snap = {"health": {"rag": "green", "reasons": []}, "history": {"notes": []}, "work": {}, "stages": [],
                "fields": [{"name": "Region", "value": "UAE", "customer_visible": True}, {"name": "Internal ref", "value": "x", "customer_visible": False}]}
        self.assertEqual([f["name"] for f in customer_view(snap)["fields"]], ["Region"])

    def test_signoff_placeholders_fill_only_customer_fields(self):
        self.world()
        self.ctx()
        from flask import session
        session.update(user_id=1, kind="internal", role="Admin")
        from routes.projects import load_project
        from services.doc_templates import fill
        from services.signoff import _values
        values = _values(load_project(1))
        self.assertEqual(fill("For {client} in {field:Region}; ref {field:Internal ref}.", values), "For C in UAE; ref {field:Internal ref}.")


class ListExportApiTestCase(FieldsBase):
    def test_list_columns_and_choice_filter(self):
        self.world()
        self.new_project(name="Q", client="D")
        self.set_values({str(self.region): "KSA"}, pid=2)
        d = self.client.get("/api/projects").get_json()
        self.assertEqual([c["name"] for c in d["fields"]], ["Region", "Internal ref"])
        self.assertEqual([f["name"] for f in d["field_filters"]], ["Region"])
        self.assertEqual({r["name"]: r["fields"] for r in d["rows"]}, {"P": ["UAE", "hush-42"], "Q": ["KSA", None]})
        self.assertEqual([r["name"] for r in self.client.get(f"/api/projects?field.{self.region}=KSA").get_json()["rows"]], ["Q"])
        self.assertEqual(self.client.get(f"/api/projects?field.{self.region}=Mars").get_json()["total"], 2)   # not a choice: no filter

    def test_export_carries_a_column_per_field(self):
        self.world()
        rows = list(csv.reader(io.StringIO(self.client.get("/projects/export.csv").data.decode())))
        self.assertEqual(rows[0][-2:], ["Region", "Internal ref"])
        self.assertEqual(rows[1][-2:], ["UAE", "hush-42"])

    def test_api_v1_has_a_fields_object(self):
        self.world()
        token = self.client.post("/settings/api-tokens", data={"name": "bi", "days": "30"}, headers=J).get_json()["token"]
        bearer = app_module.app.test_client()
        h = {"Authorization": f"Bearer {token}"}
        self.assertEqual(bearer.get("/api/v1/projects", headers=h).get_json()["projects"][0]["fields"], {"Region": "UAE", "Internal ref": "hush-42"})
        self.assertEqual(bearer.get("/api/v1/projects/1", headers=h).get_json()["project"]["fields"]["Region"], "UAE")

    def test_values_die_with_the_rollout(self):
        self.world()
        self.client.post("/projects/1/delete")
        self.sql("UPDATE projects SET deleted_at = '2000-01-01T00:00:00'")
        with app_module.app.app_context():
            __import__("db").cleanup_soft_deletes()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM project_field_values")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM custom_fields")[0][0], 2)   # the definitions stay
