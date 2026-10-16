"""CRM intake (services/intake.py): the endpoint the CRM posts a won deal to, the
settings page's view of it, and the confirm a project manager makes.

POST /api/v1/intake is Bearer-token only (scope `create`, so no CSRF and no session);
everything else is the signed-in app's. One confirm route, one permission, one audit row."""
import json
from datetime import datetime

from flask import flash, g, jsonify, redirect, request, session, url_for
from markupsafe import escape

from constants import CLIENT_PO_DOC_CATEGORY
from core import app, permission_required, role_has_permission, staff_required, text_field
from db import get_db, set_project_manager
from policies import policy_view
from routes.projects import leads, load_project, pick_lead, save_document
from routes.tokens import token_required
from security import content_matches_extension, upload_problem
from services import intake, template_tasks
from services.audit import audit_log
from services.notifications import notify_users


@app.route("/api/v1/intake", methods=["POST"])
@token_required(scope="create")
def api_v1_intake():
    """A won deal from the CRM → a pending rollout (201), or the one this deal made before (200)."""
    status, body, made = intake.handle(get_db(), g.api_token, request.get_json(force=True, silent=True))
    if made:   # the act is audited under the token's name; every call, made or not, is in intake_calls
        audit_log("intake_create", "project", body["rollout"]["id"], body["rollout"]["name"], made, actor=f"token:{g.api_token}")
    response = jsonify(body)
    response.status_code = status
    if status == 429:
        response.headers["Retry-After"] = "60"
    return response


@app.route("/api/settings/intake")
@permission_required("manage_settings")
def api_settings_intake():
    """Settings › Integrations › Intake: the create-scope tokens, the defaults (policies of the
    area `intake`) and the last calls with their results."""
    db = get_db()
    return jsonify(
        tokens=[dict(r) for r in db.execute("SELECT id, name, created_by, created_at, expires_at, last_used_at, revoked_at FROM api_tokens "
                                            "WHERE scope = 'create' ORDER BY id DESC LIMIT 50")],
        calls=intake.recent_calls(db), policies=policy_view("intake"), keep=intake.LOG_KEEP,
        templates=[{"id": t["id"], "name": t["name"]} for t in db.execute("SELECT id, name FROM stage_templates ORDER BY id")],
        owners=leads(db), endpoint="/api/v1/intake")


@app.route("/api/intake/pending")
@permission_required("view_projects")
@staff_required
def api_intake_pending():
    """The intakes waiting for a project manager (staff only), and who may confirm them."""
    db = get_db()
    return jsonify(rows=intake.pending_rows(db), can_confirm=role_has_permission(session.get("role"), "create_project"),
                   can_lead=role_has_permission(session.get("role"), "edit_project_stage"), leads=leads(db), po_category=CLIENT_PO_DOC_CATEGORY)


@app.route("/projects/<int:project_id>/intake/confirm", methods=["POST"])
@permission_required("create_project")
def intake_confirm(project_id):
    """Attach the PO and take ownership: the rollout leaves the holding lane and starts
    its stage list (with the template's tasks) as any new rollout does."""
    project = load_project(project_id)
    back = url_for("projects_list", view="pending")
    if not project["intake_pending"]:
        flash("That rollout is not waiting for confirmation", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    db = get_db()
    po_document = request.files.get("po_document")
    if not po_document or not po_document.filename:
        flash(f"Attach the '{CLIENT_PO_DOC_CATEGORY}' document to confirm the rollout", "error")
        return redirect(back)
    if problem := upload_problem(po_document):
        flash(problem, "error")
        return redirect(back)
    if not content_matches_extension(po_document):
        flash("That file's contents don't match its extension", "error")
        return redirect(back)
    try:
        po_number = text_field(request.form.get("po_number"), 60, "PO number") or project["po_number"]
    except ValueError as e:
        flash(str(e), "error")
        return redirect(back)
    lead_id, problem = pick_lead(db, request.form.get("owner_id", ""))   # someone who cannot move stages names one, as a new rollout asks
    if problem:
        flash(problem, "error")
        return redirect(back)
    now = datetime.utcnow().isoformat()
    if not db.execute("UPDATE projects SET intake_pending = 0, owner_id = ?, po_number = ?, stage_entered_at = ?, updated_at = ? "
                      "WHERE id = ? AND intake_pending = 1", (lead_id, po_number, now, now, project_id)).rowcount:
        flash("That rollout was confirmed a moment ago", "error")   # two people at once
        return redirect(url_for("project_detail", project_id=project_id))
    set_project_manager(db, project_id, lead_id, session["user_id"])
    # the template's tasks, now the team that takes them is known
    template_tasks.instantiate(db, project["stage_template_id"], project_id, session["user_name"])
    contacts = json.loads(project["intake_contacts"] or "[]")
    if contacts:   # the CRM's customer contacts stay on the rollout as a staff note; the PM invites them from the team panel
        db.execute("INSERT INTO status_notes (project_id, author, note, stage, created_at, guest_visible, author_id) VALUES (?, ?, ?, ?, ?, 0, ?)",
                   (project_id, session["user_name"], "Customer contacts from the CRM: " + ", ".join(contacts), project["stage"], now, session["user_id"]))
    name = project["name"]
    original, _ = save_document(project_id, po_document, CLIENT_PO_DOC_CATEGORY, session["user_name"])   # commits
    audit_log("intake_confirm", "project", project_id, name, f"po={original} manager_id={lead_id} source={project['intake_source']} deal={project['intake_deal_id']}")
    if lead_id != session["user_id"]:
        notify_users([lead_id], "assigned", project_id, f"You manage {escape(name)}",
                     f"{escape(session['user_name'])} confirmed <b>{escape(name)}</b> from the CRM and made you its project manager.", link=f"/projects/{project_id}")
    flash(f"{name} confirmed: it is now an active rollout")
    return redirect(url_for("project_detail", project_id=project_id))
