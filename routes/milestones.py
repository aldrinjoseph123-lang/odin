"""A rollout's milestones (services/milestones.py): the Milestones panel on the
project page. Whoever manages the rollout's tasks adds, edits, marks one reached
and reopens it; deleting is the project manager's, as for the RAID register.
Partners and customers read only the ones marked for the customer."""

from flask import abort, jsonify, request, session

from core import app, json_body, permission_required, project_allows, project_role_required
from db import get_db, get_stage_names, touch_project
from routes.projects import load_project
from services import milestones
from services.audit import audit_log


@app.route("/api/projects/<int:project_id>/milestones")
@permission_required("view_project_detail")
def api_milestones(project_id):
    load_project(project_id)
    external = session.get("kind") == "external"
    return jsonify(items=milestones.items(project_id, customer=external), stages=get_stage_names(project_id),
                   can_edit=not external and project_allows(project_id, "manage_tasks"),
                   can_delete=not external and project_allows(project_id, "manage_project"))


@app.route("/api/projects/<int:project_id>/milestones", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def api_milestone_create(project_id):
    project = load_project(project_id)
    try:
        fields = milestones.clean(json_body(), project_id)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    mid = milestones.create(project_id, fields, session["user_name"])
    touch_project(get_db(), project_id)
    get_db().commit()   # create() committed the row; this the rollout's "not idle"
    audit_log("add_milestone", "project", project_id, project["name"],
              f"{fields['name'][:80]} on {fields['date']}" + (" (shown to the customer)" if fields["customer_visible"] else ""))
    return jsonify(ok=True, id=mid)


@app.route("/api/projects/<int:project_id>/milestones/<int:milestone_id>", methods=["PUT", "DELETE"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def api_milestone_item(project_id, milestone_id):
    project = load_project(project_id)
    db = get_db()
    item = db.execute("SELECT * FROM milestones WHERE id = ? AND project_id = ?", (milestone_id, project_id)).fetchone()
    if item is None:
        abort(404)
    if request.method == "DELETE":
        if not project_allows(project_id, "manage_project"):
            abort(403)
        db.execute("DELETE FROM milestones WHERE id = ?", (milestone_id,))
        touch_project(db, project_id)
        db.commit()
        audit_log("delete_milestone", "project", project_id, project["name"], f"{item['name'][:80]} ({item['date']})")
        return jsonify(ok=True)
    try:
        fields = milestones.clean(json_body(), project_id, existing=item)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    milestones.update(item, fields)
    touch_project(db, project_id)
    db.commit()
    said = [f"{fields['name'][:60]} on {fields['date']}"]
    if "done" in fields and fields["done"] != (item["done_at"] is not None):
        said.append("reached" if fields["done"] else "reopened")
    if fields["customer_visible"] != item["customer_visible"]:
        said.append("shown to the customer" if fields["customer_visible"] else "hidden from the customer")
    audit_log("update_milestone", "project", project_id, project["name"], "; ".join(said))
    return jsonify(ok=True)
