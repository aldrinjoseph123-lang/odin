"""Custom fields (services/fields.py): the definitions under Settings ›
Rollouts & workflow (admins), and a rollout's values on its project page
(whoever may edit the rollout). The create and edit forms post values with
the rest of the project (routes/projects.py)."""

from flask import abort, jsonify, session

from core import app, json_body, permission_required, project_allows, project_role_required
from db import get_db, touch_project
from policies import policy
from routes.projects import load_project
from services import fields
from services.audit import audit_log


@app.route("/api/fields")
@permission_required("manage_settings")
def api_fields():
    return jsonify(fields=fields.definitions(), kinds=fields.KINDS, max=policy("custom_fields_max"))


@app.route("/api/fields", methods=["POST"])
@permission_required("manage_settings")
def api_field_create():
    try:
        fid, d = fields.create(json_body())
    except ValueError as e:
        return jsonify(error=str(e)), 400
    audit_log("create_custom_field", "custom_field", fid, d["name"], f"kind={d['kind']}")
    return jsonify(ok=True, id=fid)


def _field(field_id):
    f = fields.get(field_id)
    if f is None:
        abort(404)
    return f


@app.route("/api/fields/<int:field_id>", methods=["PUT"])
@permission_required("manage_settings")
def api_field_update(field_id):
    old = _field(field_id)
    try:
        d = fields.update(old, json_body())
    except ValueError as e:
        return jsonify(error=str(e)), 400
    said = [f"renamed from {old['name']}"] if d["name"] != old["name"] else []
    said += [f"{k}={d[k]}" for k in ("kind", "choices", "required", "customer_visible", "show_in_list") if d[k] != old[k]]
    audit_log("update_custom_field", "custom_field", field_id, d["name"], "; ".join(said) or "no change")
    return jsonify(ok=True)


@app.route("/api/fields/<int:field_id>/move", methods=["POST"])
@permission_required("manage_settings")
def api_field_move(field_id):
    f = _field(field_id)
    step = json_body().get("step")
    if step not in (-1, 1):
        return jsonify(error="Move up (-1) or down (1)"), 400
    fields.move(f, step)
    audit_log("move_custom_field", "custom_field", field_id, f["name"], "up" if step < 0 else "down")
    return jsonify(ok=True)


@app.route("/api/fields/<int:field_id>", methods=["DELETE"])
@permission_required("manage_settings")
def api_field_delete(field_id):
    """Deleting takes every rollout's value with it, so the admin types the
    field's name; the values (the first few) are kept in the audit row."""
    f = _field(field_id)
    if str(json_body().get("confirm", "")).strip() != f["name"]:
        return jsonify(error=f"Type the field's name, {f['name']}, to delete it and every rollout's value"), 400
    archive = fields.delete(f)
    audit_log("delete_custom_field", "custom_field", field_id, f["name"], archive)
    return jsonify(ok=True)


@app.route("/api/projects/<int:project_id>/fields")
@permission_required("view_project_detail")
def api_project_fields(project_id):
    """This rollout's values. Partners and customers get the fields marked for them, and never edit."""
    load_project(project_id)
    external = session.get("kind") == "external"
    return jsonify(fields=fields.for_project(project_id, customer=external),
                   can_edit=not external and project_allows(project_id, "manage_project"))


@app.route("/api/projects/<int:project_id>/fields", methods=["PUT"])
@permission_required("edit_project")
@project_role_required("manage_project")
def api_project_fields_save(project_id):
    project = load_project(project_id)
    items = json_body().get("values")
    if not isinstance(items, dict):
        return jsonify(error="Send the values as {field id: value}"), 400
    try:
        values = fields.clean_values(items)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    db = get_db()
    changes = fields.save(db, project_id, values)
    if changes:
        touch_project(db, project_id)
    db.commit()
    if changes:
        audit_log("update_field_values", "project", project_id, project["name"], "; ".join(changes))
    return jsonify(ok=True, changed=len(changes))
