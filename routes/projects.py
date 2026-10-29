"""Project lifecycle routes: the page shells, CSV export, create and edit
(the React form posts here), stage changes, documents, participants, notes,
tasks, delete + undo.

Includes shared helpers (filtered_projects_query, change_stage, save_document).
Imported for route registration side effects.
"""
import io
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta

from flask import (
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    request,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import escape
from werkzeug.utils import secure_filename

import graph
from constants import (
    EXTERNAL_PROJECT_ROLES,
    PROJECT_MANAGER,
    PROJECT_ROLES,
    CLIENT_PO_DOC_CATEGORY,
    DEFAULT_ALERT_TYPE_SETTINGS,
    DELIVERY_MODES,
)
from core import app, as_bool, as_id, json_body, like_any, parse_date, sees_po, text_field, login_required, permission_required, project_allows, project_role_required, role_has_permission, offer_undo, undo_note, project_scope
from security import content_matches_extension, file_stem, upload_problem, valid_email, safe_csv_writer
from policies import local_today, policy
from spa import spa_index
from db import (
    UPLOAD_DIR,
    get_db,
    get_doc_category_names,
    partner_hidden_categories,
    PROJECT_OPEN_SQL,
    copy_template_stages,
    customer_ids,
    insert_task,
    my_project_ids,
    set_project_manager,
    is_customer_on,
    get_stage_names,
    restore_deleted,
    soft_delete,
    touch_project,
)
from services.alerts import get_alert_type_settings
from services import asks
from services import doc_review
from services import fields as custom_fields
from services import recurrence
from services import rules
from services import stages as stage_ops
from services import task_links
from services import template_tasks
from services.audit import audit_log
from services.fmt import plural
from services.notifications import notify_event, notify_participants, notify_users

PROJECTS_PER_PAGE = 25

# Sortable columns, mapped to their SQL expression. SQLite cannot parameterise
# an ORDER BY, so this allowlist is what keeps the column name from ever being
# user-controlled text spliced into the query.
SORT_COLUMNS = {
    "name": "p.name",
    "client": "p.client",
    "po_number": "p.po_number",
    "stage": "(SELECT ps.position FROM project_stages ps WHERE ps.project_id = p.id AND ps.name = p.stage)",   # by place in its own list, not A-Z
    "owner": "u.name",
    "mode": "p.delivery_mode",
    "vendor": "p.vendor_name",
    "product": "p.product_name",
    "updated": "p.updated_at",
}
DEFAULT_SORT = "updated"


# ---- the one door into a project ---------------------------------------------

def load_project(project_id, include_deleted=False):
    """Fetch a project the current user may see, or 404. Every route scoped
    to a project goes through here (a meta-test enforces it), so the
    visibility rule — Admin and internal staff see all, an external account
    only its own projects — lives in exactly one place. Soft-deleted rows
    are invisible except to undo, which exists to bring them back."""
    project = get_db().execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        "WHERE p.id = ?" + ("" if include_deleted else " AND p.deleted_at IS NULL"), (project_id,),
    ).fetchone()
    if project is None or not project_visible(project):
        abort(404)
    if project["intake_pending"] and request.method not in ("GET", "HEAD") and request.endpoint not in PENDING_ALLOWED:
        # a CRM intake is not a rollout until it is confirmed: no team, tasks, sign-off, report or move by URL
        abort(400, description="Confirm this intake first (attach the PO and take ownership)")
    return project


# What may be done to a pending intake (services/intake.py) before it is confirmed:
# correct its details, confirm it, or discard it and undo the discard. Every other write is refused in load_project.
PENDING_ALLOWED = {"intake_edit", "intake_confirm", "project_delete", "undo_project"}


def project_visible(project):
    if session.get("kind") != "external":
        return True
    if project["intake_pending"]:   # staff only until it is confirmed
        return False
    return project["id"] in my_project_ids(session["user_id"])


@app.route("/projects")
@permission_required("view_projects")
def projects_list():
    return spa_index()


def filtered_projects_query(view, stage_filter, show_closed, delivery_mode_filter="", search="", sort=DEFAULT_SORT, direction="desc"):
    query = "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.deleted_at IS NULL"
    scope_sql, params = project_scope()
    query += scope_sql
    # CRM intakes wait in their own view until confirmed (services/intake.py); no other list has them
    query += " AND p.intake_pending = 1" if view == "pending" else " AND p.intake_pending = 0"
    if view == "stale":
        stale_threshold = get_alert_type_settings().get("stale", DEFAULT_ALERT_TYPE_SETTINGS["stale"])["threshold_days"]
        stale_cutoff = (datetime.utcnow() - timedelta(days=stale_threshold)).isoformat()
        query += " AND p.updated_at < ?"
        params.append(stale_cutoff)
        if not show_closed:
            query += f" AND {PROJECT_OPEN_SQL}"
    elif view == "overdue":
        # past target end date, not yet in the terminal stage
        today = local_today().isoformat()
        query += f" AND p.target_end_date IS NOT NULL AND p.target_end_date < ? AND {PROJECT_OPEN_SQL}"
        params.append(today)
    elif view == "at_risk":
        # target end date within the due-soon window (and not already overdue/terminal)
        soon_days = get_alert_type_settings().get("project_due_soon", DEFAULT_ALERT_TYPE_SETTINGS["project_due_soon"])["threshold_days"]
        today = local_today()
        soon = (today + timedelta(days=soon_days)).isoformat()
        query += f" AND p.target_end_date IS NOT NULL AND p.target_end_date >= ? AND p.target_end_date <= ? AND {PROJECT_OPEN_SQL}"
        params.extend([today.isoformat(), soon])
        # one state per rollout, as the Flow counts it: a rollout over its stage SLA is listed there, not here (sim L-8)
        from services.alerts import build_alerts
        live = get_db().execute(
            f"SELECT p.* FROM projects p WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} AND p.target_end_date >= ? AND p.target_end_date <= ?",
            (today.isoformat(), soon)).fetchall()
        over_sla = [p["id"] for p in build_alerts(live)["stage_sla_breach"]]
        if over_sla:
            query += f" AND p.id NOT IN ({','.join('?' * len(over_sla))})"
            params.extend(over_sla)
    elif stage_filter:
        query += " AND p.stage = ?"
        params.append(stage_filter)
    elif not show_closed and view != "pending":
        query += f" AND {PROJECT_OPEN_SQL}"
    if delivery_mode_filter:   # combines with every view and stage (test report FN-13: a stage silently dropped it)
        query += " AND p.delivery_mode = ?"
        params.append(delivery_mode_filter)
    if search:
        # free-text across the fields a user searches by. LIKE is parameterised;
        # the % wrapping is on the value, never interpolated into the SQL.
        like = like_any(search)
        if session.get("kind") == "external":   # partners never see the PO, so they cannot search or sort by it
            query += " AND (p.name LIKE ? ESCAPE '\\' OR p.client LIKE ? ESCAPE '\\')"
            params.extend([like, like])
        else:
            query += " AND (p.name LIKE ? ESCAPE '\\' OR p.client LIKE ? ESCAPE '\\' OR p.po_number LIKE ? ESCAPE '\\')"
            params.extend([like, like, like])
    field_sql, field_params = custom_fields.filter_sql(request.args, customer=session.get("kind") == "external")   # ?field.<id>=<choice>
    query += field_sql
    params += field_params
    if sort == "po_number" and session.get("kind") == "external":
        sort = DEFAULT_SORT
    column = SORT_COLUMNS.get(sort, SORT_COLUMNS[DEFAULT_SORT])
    direction = "ASC" if str(direction).lower() == "asc" else "DESC"
    # NULLs last either way — an empty PO number shouldn't win the top of the list
    query += f" ORDER BY {column} IS NULL, {column} {direction}"
    return query, params


@app.route("/projects/export.csv")
@permission_required("view_projects")
def projects_export_csv():
    db = get_db()
    query, params = filtered_projects_query(
        request.args.get("view", ""), request.args.get("stage", ""), request.args.get("closed") == "1",
        request.args.get("delivery_mode", ""), request.args.get("q", "").strip(),
        request.args.get("sort", DEFAULT_SORT), request.args.get("dir", "desc"),
    )
    projects = db.execute(query, params).fetchall()

    output = io.StringIO()
    writer = safe_csv_writer(output)
    external = session.get("kind") == "external"
    defs = custom_fields.definitions(customer=external)   # partners: only the custom fields marked for them
    values = custom_fields.values_for([p["id"] for p in projects], customer=external)
    writer.writerow(
        [
            "Project Name", "Client", "PO Number", "PO Date", "Stage", "Owner",
            "Delivery Mode", "Outsourcer", "Vendor", "Product",
            "Start Date", "Target End Date", "Updated At",
        ] + [f["name"] for f in defs]
    )
    for p in projects:
        po = sees_po(p["id"])   # partners: no PO, no outsourcer (as the project page)
        writer.writerow(
            [
                p["name"], p["client"], p["po_number"] if po else "", p["po_date"] if po else "", p["stage"],
                p["owner_name"], p["delivery_mode"], "" if external else p["outsourcer_name"], p["vendor_name"],
                p["product_name"], p["start_date"], p["target_end_date"], p["updated_at"],
            ] + ["" if (v := values[p["id"]].get(f["id"])) is None else ("Yes" if v else "No") if isinstance(v, bool) else v for f in defs]
        )
    audit_log("export_projects", details=f"{len(projects)} rollouts")   # it carries PO numbers: an export like the others (P3-17)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=projects.csv"},
    )


def _rollout_csv(project, what, header, rows):
    """One rollout's register as a download: audited like the other exports,
    and formula-safe through safe_csv_writer. Staff only: a partner's cut of the
    RAID and tasks is on the page and in the customer report, not in a file.
    The caller loads the project (load_project) before it reads any rows."""
    project_id = project["id"]
    output = io.StringIO()
    writer = safe_csv_writer(output)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    audit_log(f"export_{what}", "project", project_id, project["name"], f"{len(rows)} rows")
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=odin-{what}-{file_stem(project['name'])}.csv", "Cache-Control": "private, no-store"})


@app.route("/projects/<int:project_id>/raid.csv")
@permission_required("view_project_detail")
def raid_export_csv(project_id):
    if session.get("kind") == "external":
        abort(403)
    from services import raid
    project = load_project(project_id)   # visibility first, then the rows
    rows = [[r["kind"], r["title"], r["detail"], r["impact"], r["likelihood"], r["status"], r["owner_name"], r["due_date"], r["stage"],
             r["resolution"], "yes" if r["customer_visible"] else "", r["created_by"], r["created_at"], r["closed_at"]] for r in raid.items(project_id)]
    return _rollout_csv(project, "raid", ["Kind", "Title", "Detail", "Impact", "Likelihood", "Status", "Owner", "Due date", "Stage",
                                             "Resolution", "Shown to the customer", "Created by", "Created at", "Closed at"], rows)


@app.route("/projects/<int:project_id>/tasks.csv")
@permission_required("view_project_detail")
def tasks_export_csv(project_id):
    if session.get("kind") == "external":
        abort(403)
    db = get_db()
    project = load_project(project_id)
    stages = get_stage_names(project_id)
    tasks = db.execute(
        "SELECT t.*, u.name AS assignee_name FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id "
        "WHERE t.project_id = ? ORDER BY t.done, t.due_date IS NULL, t.due_date, t.id", (project_id,)).fetchall()
    title = {t["id"]: t["title"] for t in tasks}
    links = task_links.links_for(project_id, db)
    rows = [[t["title"], t["stage"] if t["stage"] in stages else project["stage"], t["assignee_name"], t["due_date"], "yes" if t["done"] else "", t["done_at"],
             t["estimate_hours"], t["recurrence"], "; ".join(title.get(i, "") for i in links.get(t["id"], [])), t["kind"] or "task", t["created_by"], t["created_at"]]
            for t in tasks]
    return _rollout_csv(project, "tasks", ["Task", "Stage", "Assignee", "Due date", "Done", "Done at", "Estimate hours", "Repeats", "Waits on", "Kind", "Created by", "Created at"], rows)


@app.route("/reports/all")
@permission_required("view_reports")
def report_all():
    return spa_index()


@app.route("/projects/<int:project_id>/report")
@permission_required("view_reports")
def report_single(project_id):
    load_project(project_id)   # 404 unless the caller may see it, before any page is served
    return spa_index()


def leads(db, keep=None):
    """[{id, name}] of the staff who can be a project manager: those who may move stages
    (`keep`: this owner too, so an edit never swaps them silently)."""
    return [{"id": u["id"], "name": u["name"]} for u in db.execute("SELECT id, name, role FROM users WHERE active = 1 AND kind = 'internal' ORDER BY name")
            if role_has_permission(u["role"], "edit_project_stage") or u["id"] == keep]


def pick_lead(db, raw):
    """(the project manager's id, None) for a new rollout or a confirmed intake, or (None, the words to refuse with).
    A project manager must be able to move stages: someone who can is their own; someone who cannot names one."""
    if role_has_permission(session.get("role"), "edit_project_stage"):
        return session["user_id"], None
    lead = db.execute("SELECT id, role FROM users WHERE id = ? AND active = 1 AND kind = 'internal'", (raw,)).fetchone() if raw.isdigit() else None
    if lead is None or not role_has_permission(lead["role"], "edit_project_stage"):
        return None, "Choose a project manager who can move stages (an Admin or Member)"
    return lead["id"], None


@app.route("/projects/new", methods=["GET", "POST"])
@permission_required("create_project")
def project_new():
    if request.method == "GET":
        return spa_index()
    db = get_db()
    po_document = request.files.get("po_document")
    if not po_document or not po_document.filename:
        flash(f"Upload a '{CLIENT_PO_DOC_CATEGORY}' document to create the rollout", "error")
        return redirect(url_for("project_new"))
    if problem := upload_problem(po_document):
        flash(problem, "error")
        return redirect(url_for("project_new"))
    if not content_matches_extension(po_document):
        flash("That file's contents don't match its extension", "error")
        return redirect(url_for("project_new"))

    template = _chosen_template(db, request.form.get("stage_template_id"))
    if template is None:
        flash("Create a stage template in Settings before adding rollouts", "error")
        return redirect(url_for("project_new"))
    first_stage = db.execute(
        "SELECT name FROM stage_template_stages WHERE template_id = ? ORDER BY position LIMIT 1",
        (template["id"],),
    ).fetchone()
    if first_stage is None:
        flash(f"Template '{template['name']}' has no stages yet", "error")
        return redirect(url_for("project_new"))
    # one stage would be the finish line: the project would be born closed, never signed off (D13)
    if db.execute("SELECT COUNT(*) FROM stage_template_stages WHERE template_id = ?", (template["id"],)).fetchone()[0] < 2:
        flash(f"Template '{template['name']}' needs at least two stages: the work and the finish", "error")
        return redirect(url_for("project_new"))

    if not request.form.get("name", "").strip() or not request.form.get("client", "").strip():
        flash("Project name and client are required", "error")   # test report FN-5: edit refused this, create did not
        return redirect(url_for("project_new"))
    if request.form.get("delivery_mode", DELIVERY_MODES[0]) not in DELIVERY_MODES:
        flash("Pick a delivery mode", "error")
        return redirect(url_for("project_new"))
    if problem := _date_problem(request.form):
        flash(problem, "error")
        return redirect(url_for("project_new"))
    try:   # custom fields: each by its kind, the required ones present (services/fields.py)
        field_values = custom_fields.clean_values(custom_fields.form_items(request.form), creating=True)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("project_new"))
    # Someone who cannot move stages (a Contributor) names a project manager who can and joins as a Coordinator.
    lead_id, problem = pick_lead(db, request.form.get("owner_id", ""))
    if problem:
        flash(problem, "error")
        return redirect(url_for("project_new"))
    now = datetime.utcnow().isoformat()
    name = request.form["name"].strip()[:200]
    cursor = db.execute(
        """INSERT INTO projects
        (name, client, po_number, po_date, stage, owner_id,
         via, account_manager_name, account_manager_email,
         partner_name, partner_account_manager_name, partner_account_manager_email,
         start_date, target_end_date, delivery_mode,
         outsourcer_name, outsourcer_email, vendor_name, product_name,
         access_token, customer_token, stage_template_id, created_at, updated_at, stage_entered_at, customer_approval)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            request.form["client"].strip()[:200],
            request.form.get("po_number") or None,
            parse_date(request.form.get("po_date")),
            first_stage["name"],
            lead_id,
            request.form.get("via") or None,
            request.form.get("account_manager_name") or None,
            request.form.get("account_manager_email") or None,
            request.form.get("partner_name") or None,
            request.form.get("partner_account_manager_name") or None,
            request.form.get("partner_account_manager_email") or None,
            parse_date(request.form.get("start_date")),
            parse_date(request.form.get("target_end_date")),
            request.form.get("delivery_mode", DELIVERY_MODES[0]),
            request.form.get("outsourcer_name") or None,
            request.form.get("outsourcer_email") or None,
            request.form.get("vendor_name") or None,
            request.form.get("product_name") or None,
            secrets.token_urlsafe(16),   # vendor link
            secrets.token_urlsafe(16),   # customer link
            template["id"],
            now,
            now,
            now,
            1 if request.form.get("customer_approval") else 0,
        ),
    )
    project_id = cursor.lastrowid
    copy_template_stages(db, template["id"], project_id)
    field_changes = custom_fields.save(db, project_id, field_values)
    set_project_manager(db, project_id, lead_id, session["user_id"])
    team = request.form.getlist("team_user_ids") + ([str(session["user_id"])] if lead_id != session["user_id"] else [])
    for raw in team:
        if raw.isdigit() and int(raw) != lead_id and db.execute("SELECT 1 FROM users WHERE id = ? AND active = 1 AND kind = 'internal' AND role != 'Viewer'", (raw,)).fetchone():
            db.execute(
                "INSERT OR IGNORE INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, 'Coordinator', ?, ?)",
                (project_id, int(raw), session["user_id"], now),
            )
    # the template's tasks, once the team that takes them is known
    template_tasks.instantiate(db, template["id"], project_id, session["user_name"])
    save_document(project_id, po_document, CLIENT_PO_DOC_CATEGORY, session["user_name"])
    db.commit()
    joined = [r[0] for r in db.execute("SELECT user_id FROM project_participants WHERE project_id = ? AND role = 'Coordinator'", (project_id,))]
    notify_users(joined, "assigned", project_id, f"You are on {escape(name)}",
                 f"{escape(session['user_name'])} added you to <b>{escape(name)}</b> as a Coordinator.", exclude_user_id=session["user_id"], link=f"/projects/{project_id}")
    if lead_id != session["user_id"]:   # test report FN-7: a PM named by someone else heard only by mail, which may be off
        notify_users([lead_id], "assigned", project_id, f"You manage {escape(name)}",
                     f"{escape(session['user_name'])} created <b>{escape(name)}</b> and made you its project manager.", link=f"/projects/{project_id}")
    audit_log("create_project", "project", project_id, name, f"client={request.form['client']}" + (f" manager_id={lead_id}" if lead_id != session["user_id"] else ""))
    if field_changes:
        audit_log("update_field_values", "project", project_id, name, "; ".join(field_changes))
    notify_event(
        {"owner_id": lead_id},
        f"New project: {escape(name)}",
        f"Project '{escape(name)}' for {escape(request.form['client'])} was created"
        + (f" by {escape(session['user_name'])} and assigned to you." if lead_id != session["user_id"] else "."),
        channels={"email": False, "teams": True},   # the named PM already had "You manage …" by email (D12)
    )
    rules.fire("rollout_created", project_id, {"source": "form"})   # automations (services/rules.py)
    flash("Project created")
    return redirect(url_for("project_detail", project_id=project_id))   # straight to the new rollout (P14)


@app.route("/projects/<int:project_id>")
@permission_required("view_project_detail")
def project_detail(project_id):
    load_project(project_id)   # 404 unless the caller may see it, before any page is served
    return spa_index()


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_edit(project_id):
    project = load_project(project_id)
    if request.method == "GET":
        return spa_index()
    db = get_db()
    name = request.form.get("name", "").strip()[:200]
    client = request.form.get("client", "").strip()[:200]
    if not name or not client:
        flash("Project name and client are required", "error")
        return redirect(url_for("project_edit", project_id=project_id))
    if problem := _date_problem(request.form):
        flash(problem, "error")
        return redirect(url_for("project_edit", project_id=project_id))
    try:
        field_values = custom_fields.clean_values(custom_fields.form_items(request.form))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("project_edit", project_id=project_id))

    # Owner reassignment — fall back to the current owner if the submitted
    # id is missing or not a real user (never leave a project ownerless).
    owner_id = as_id(request.form.get("owner_id")) or project["owner_id"]
    # the owner is the project manager: an active staff account that may move stages
    owner = db.execute("SELECT role, active, kind FROM users WHERE id = ?", (owner_id,)).fetchone()
    if not owner or not owner["active"] or owner["kind"] == "external" or not role_has_permission(owner["role"], "edit_project_stage"):
        if owner_id != project["owner_id"]:
            flash("The project manager must be an active Admin or Member; the owner was not changed")
        owner_id = project["owner_id"]

    delivery_mode = request.form.get("delivery_mode", project["delivery_mode"])
    if delivery_mode not in DELIVERY_MODES:
        delivery_mode = project["delivery_mode"]

    now = datetime.utcnow().isoformat()
    db.execute(
        """UPDATE projects SET
            name=?, client=?, owner_id=?, po_number=?, po_date=?,
            via=?, account_manager_name=?, account_manager_email=?,
            partner_name=?, partner_account_manager_name=?, partner_account_manager_email=?,
            start_date=?, target_end_date=?, delivery_mode=?,
            outsourcer_name=?, outsourcer_email=?, vendor_name=?, product_name=?, updated_at=?,
            customer_approval=?
           WHERE id=?""",
        (
            name, client, owner_id,
            request.form.get("po_number") or None,
            parse_date(request.form.get("po_date")),
            request.form.get("via") or None,
            request.form.get("account_manager_name") or None,
            request.form.get("account_manager_email") or None,
            request.form.get("partner_name") or None,
            request.form.get("partner_account_manager_name") or None,
            request.form.get("partner_account_manager_email") or None,
            parse_date(request.form.get("start_date")),
            parse_date(request.form.get("target_end_date")),
            delivery_mode,
            request.form.get("outsourcer_name") or None,
            request.form.get("outsourcer_email") or None,
            request.form.get("vendor_name") or None,
            request.form.get("product_name") or None,
            now, 1 if request.form.get("customer_approval") else 0, project_id,
        ),
    )
    field_changes = custom_fields.save(db, project_id, field_values)
    if owner_id != project["owner_id"]:
        set_project_manager(db, project_id, owner_id, session["user_id"])
    if not request.form.get("customer_approval"):   # no longer asking: an open request is moot (P7)
        db.execute("UPDATE stage_approvals SET status = 'superseded' WHERE project_id = ? AND status = 'pending'", (project_id,))
    db.commit()
    if owner_id != project["owner_id"]:
        notify_users([owner_id], "assigned", project_id, f"You now manage {escape(name)}",
                     f"{escape(session['user_name'])} made you project manager of <b>{escape(name)}</b>.", exclude_user_id=session["user_id"], link=f"/projects/{project_id}")
        notify_users([project["owner_id"]], "activity", project_id, f"{escape(name)} has a new project manager",
                     f"{escape(session['user_name'])} handed <b>{escape(name)}</b> to someone else; you stay on the team as a Coordinator.", exclude_user_id=session["user_id"], link=f"/projects/{project_id}")
    audit_log("update_project", "project", project_id, name, f"client={client}; owner_id={owner_id}")
    if field_changes:
        audit_log("update_field_values", "project", project_id, name, "; ".join(field_changes))
    flash("Project updated")
    return redirect(url_for("project_detail", project_id=project_id))


class StageConflict(str):
    """A refusal because the rollout is not where the caller saw it (the API answers 409)."""


def change_stage(project_id, new_stage, note_text, guest=None, from_stage=None, override=None):
    """The one stage-change path (form, JSON and the vendor's guest link).
    Returns an error message or None; 404s when the project is gone. Staff
    callers must hold edit_project_stage; `guest` is (author, party) for the
    vendor link, which has no session and was checked by the guest route.
    `from_stage` is the stage the caller saw: a move from a stale view is
    refused rather than taking the rollout backwards (P2-26). `override` is
    the typed reason for moving past a stage gate (services/gates.py)."""
    db = get_db()
    # Existence first, then validity: a missing project is a 404, not an
    # "invalid stage" — and its (empty) stage list must never be consulted.
    if guest:
        project = db.execute("SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    else:
        project = load_project(project_id)
    if project is None:
        abort(404)
    actor_name = f"{guest[0]} (vendor link)" if guest else session["user_name"]
    actor_id = None if guest else session["user_id"]
    if project["intake_pending"]:
        return "Confirm this intake first (attach the PO and take ownership); it has no stage until then"
    if new_stage not in get_stage_names(project_id):
        return "Invalid stage"
    if from_stage is not None and from_stage != project["stage"]:
        return StageConflict(f"The rollout has moved on: it is in {project['stage']} now")
    if new_stage == project["stage"]:   # test report FN-8: it reset the SLA clock and re-notified everyone
        return StageConflict(f"The rollout is already in {new_stage}")
    from services.signoff import gate
    if blocked := gate(project, new_stage):
        return blocked
    from services import gates
    held = gates.blocked(project, new_stage)
    if held and guest:   # the vendor link never overrides, and hears no internals
        return StageConflict(gates.GUEST_MESSAGE)
    if held and not override:
        return StageConflict(f"Before leaving {project['stage']}: {gates.summary(held)}")
    if held and not gates.may_override(project):
        return gates.override_refusal()
    now = datetime.utcnow().isoformat()
    # compare-and-set: of two submits racing, only the first moves the project
    # (a double click used to write two notes and notify twice; F-M5)
    moved = db.execute(
        "UPDATE projects SET stage = ?, updated_at = ?, stage_entered_at = ? WHERE id = ? AND stage = ? AND deleted_at IS NULL",
        (new_stage, now, now, project_id, project["stage"]),
    ).rowcount
    if not moved:
        db.rollback()
        return StageConflict(f"The rollout has just moved; it is no longer in {project['stage']}")
    names = get_stage_names(project_id)
    terminal = new_stage == names[-1]
    if project["stage"] == names[-1]:
        # reopened: a signed sign-off no longer speaks for the work to come (P3-24); it stays on
        # file as signed, and the finish waits for a new version. One still out for signature stays live.
        db.execute("UPDATE signoffs SET superseded_at = ? WHERE project_id = ? AND superseded_at IS NULL AND status <> 'sent'", (now, project_id))
    cur = db.execute(
        "INSERT INTO status_notes (project_id, author, note, stage, created_at, guest_visible, author_id, prev_stage, prev_entered_at)"
        " VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
        (
            project_id,
            actor_name,
            note_text or f"Stage changed to {new_stage}",
            new_stage,
            now,
            actor_id,
            project["stage"],
            project["stage_entered_at"],
        ),
    )
    g.stage_note_id = cur.lastrowid
    if held:   # staff only (guest_visible = 0): the customer hears of the move, not of the gate
        db.execute("INSERT INTO status_notes (project_id, author, note, stage, created_at, guest_visible, author_id) VALUES (?, ?, ?, ?, ?, 0, ?)",
                   (project_id, actor_name, f"Moved past the gate: {override} ({gates.summary(held)})", new_stage, now, actor_id))
    g.stage_undo_url = url_for("undo_stage_change", project_id=project_id, note_id=cur.lastrowid)
    # A newer change makes an undecided older request moot; closing asks for
    # no approval (the sign-off is the customer's word on the finish, P7).
    # Only someone in the Customer role can decide, so with nobody in it no
    # request is opened (it would wait for ever and count as waiting, sim L-7).
    ask_customer = bool(project["customer_approval"]) and not terminal and bool(customer_ids(project_id))
    if project["customer_approval"]:
        db.execute("UPDATE stage_approvals SET status = 'superseded' WHERE project_id = ? AND status = 'pending'", (project_id,))
    if ask_customer:
        db.execute(
            "INSERT INTO stage_approvals (project_id, stage, requested_by, requested_at) VALUES (?, ?, ?, ?)",
            (project_id, new_stage, actor_name, now),
        )
    db.commit()
    # The move stands from here: each follow-up is on its own, and a failed one is logged and
    # told to the admins rather than answering 500 for a move that happened (sim A5)
    def follow(step, *args, **kwargs):
        try:
            step(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            app.logger.exception("stage move of project %s to %s: %s failed", project_id, new_stage, step.__name__)
            try:
                from services.notifications import report_mail_failure
                report_mail_failure(f"{step.__name__} for '{project['name']}' (moved to {new_stage}): {exc}", kind="followup")
            except Exception:  # noqa: BLE001 — the bell may be what failed
                db.rollback()
                app.logger.exception("could not tell the admins of the failed follow-up")
    if guest:
        follow(audit_log, "guest_stage_change", "project", project_id, project["name"], f"stage={new_stage}; by={guest[0]}", actor=f"guest:{guest[1]}")
    else:
        follow(audit_log, "update_project_stage", "project", project_id, project["name"], f"stage={new_stage}")
        if held:
            follow(audit_log, "override_stage_gate", "project", project_id, project["name"], f"{project['stage']} -> {new_stage}: {gates.summary(held)}; reason={override}")
    body = (f"Stage moved to <b>{escape(new_stage)}</b> by {escape(actor_name)}."
            + (f"<br>{escape(note_text)}" if note_text else ""))
    ask = "<br>Please review and approve this step."
    follow(notify_event, project, f"Stage changed: {escape(project['name'])}", body + (ask if ask_customer else ""), channels={"email": False, "teams": True})
    # the customer is asked to approve as an approval (their own kind), everyone else hears of the move
    customers = customer_ids(project_id) if ask_customer else []
    team = [r[0] for r in db.execute("SELECT user_id FROM project_participants WHERE project_id = ?", (project_id,)) if r[0] not in customers]
    follow(notify_users, team, "stage", project_id, f"{escape(project['name'])}: now in {escape(new_stage)}", body, exclude_user_id=actor_id)
    if customers:
        follow(notify_users, customers, "approval", project_id, f"{escape(project['name'])}: please approve the move to {escape(new_stage)}", body + ask,
               exclude_user_id=actor_id, link=f"/projects/{project_id}")
    follow(rules.fire, "stage_entered", project_id, {"stage": new_stage, "from": project["stage"]})
    return None


@app.route("/undo/stage/<int:project_id>/<int:note_id>", methods=["POST"])
@permission_required("edit_project_stage")
@project_role_required("move_stage")
def undo_stage_change(project_id, note_id):
    """Put a stage move back, for its author, within the undo window, and only
    while it is still the latest move. The move's note is removed so the
    history and cycle times read as if it never happened; the audit trail keeps
    both rows, and everyone who was told about the move is told it was undone."""
    db = get_db()
    project = load_project(project_id)
    note = db.execute("SELECT * FROM status_notes WHERE id = ? AND project_id = ? AND prev_stage IS NOT NULL", (note_id, project_id)).fetchone()
    cutoff = (datetime.utcnow() - timedelta(minutes=policy("undo_minutes"))).isoformat()
    later_move = note and db.execute(
        "SELECT 1 FROM status_notes WHERE project_id = ? AND prev_stage IS NOT NULL AND id > ?", (project_id, note_id)).fetchone()
    if (note is None or note["author_id"] != session["user_id"] or note["created_at"] < cutoff
            or later_move or project["stage"] != note["stage"] or note["prev_stage"] not in get_stage_names(project_id)):
        flash("That move can no longer be undone: it is too old, was made by someone else, or the rollout has moved since", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    now = datetime.utcnow().isoformat()
    # compare-and-set, as change_stage: of two undos (or an undo and a move) racing, one wins (P3-2)
    if not (db.execute("UPDATE projects SET stage = ?, stage_entered_at = ?, updated_at = ? WHERE id = ? AND stage = ?",
                       (note["prev_stage"], note["prev_entered_at"] or now, now, project_id, note["stage"])).rowcount
            and db.execute("DELETE FROM status_notes WHERE id = ?", (note_id,)).rowcount):
        db.rollback()
        flash("That move can no longer be undone: the rollout has moved since", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    # undoing a reopen brings back the sign-off the reopen set aside (P3-24)
    db.execute("UPDATE signoffs SET superseded_at = NULL WHERE project_id = ? AND superseded_at = ?", (project_id, note["created_at"]))
    # notes written since the move belong to the stage the project is back in;
    # left tagged with the undone stage they made a phantom visit in the history (D8)
    db.execute("UPDATE status_notes SET stage = ? WHERE project_id = ? AND prev_stage IS NULL AND stage = ? AND created_at >= ?",
               (note["prev_stage"], project_id, note["stage"], note["created_at"]))
    # The approval this move asked for goes — unless the customer already
    # decided it: that record stays, superseded. The request of the visit the
    # project returns to comes back, and only that one (it was opened as the
    # project entered the stage: requested_at = that entry), only while the
    # project still asks, and not if that visit was already decided (sim L-1).
    db.execute("DELETE FROM stage_approvals WHERE project_id = ? AND stage = ? AND requested_at = ? AND status = 'pending'", (project_id, note["stage"], note["created_at"]))
    db.execute("UPDATE stage_approvals SET status = 'superseded' WHERE project_id = ? AND stage = ? AND requested_at = ? AND status IN ('approved', 'declined')",
               (project_id, note["stage"], note["created_at"]))
    if project["customer_approval"] and note["prev_entered_at"]:
        db.execute("UPDATE stage_approvals SET status = 'pending' WHERE project_id = ? AND stage = ? AND status = 'superseded' AND requested_at = ?",
                   (project_id, note["prev_stage"], note["prev_entered_at"]))
    db.commit()
    audit_log("undo_project_stage", "project", project_id, project["name"], f"stage={note['prev_stage']} (undid {note['stage']})")
    body = f"{escape(session['user_name'])} undid the move to <b>{escape(note['stage'])}</b>. The rollout is back in <b>{escape(note['prev_stage'])}</b>."
    notify_event(project, f"Stage change undone: {escape(project['name'])}", body, channels={"email": False, "teams": True})
    notify_participants(project_id, f"{escape(project['name'])}: back in {escape(note['prev_stage'])}", body, exclude_user_id=session["user_id"])
    flash(f"Moved back to {note['prev_stage']}")
    return redirect(url_for("project_detail", project_id=project_id))


def decide_approval(project_id, approval_id, decision, comment):
    """The one approval path (form + JSON). The customer contact on the
    project approves or declines the latest stage change; anyone else —
    staff included — is refused, because an approval only means something
    when the customer gave it. Returns an error message or None."""
    project = load_project(project_id)
    db = get_db()
    if not is_customer_on(project_id, session["user_id"]):
        abort(403)
    row = db.execute("SELECT * FROM stage_approvals WHERE id = ? AND project_id = ?", (approval_id, project_id)).fetchone()
    if row is None:
        abort(404)
    if decision not in ("approved", "declined"):
        return "Approve or decline"
    if row["status"] != "pending":
        return "That request is no longer open"
    comment = (comment or "").strip()[:2000]
    now = datetime.utcnow().isoformat()
    if not db.execute(   # only while still open: of two decisions racing, one is recorded (P3-2)
        "UPDATE stage_approvals SET status = ?, decided_by = ?, decided_at = ?, comment = ? WHERE id = ? AND status = 'pending'",
        (decision, session["user_name"], now, comment or None, approval_id),
    ).rowcount:
        db.rollback()
        return "That request is no longer open"
    db.execute(
        "INSERT INTO status_notes (project_id, author, note, stage, created_at, guest_visible, author_id) VALUES (?, ?, ?, ?, ?, 1, ?)",
        (project_id, session["user_name"], f"{decision.capitalize()} {row['stage']}" + (f": {comment}" if comment else ""), project["stage"], now, session["user_id"]),
    )
    touch_project(db, project_id)
    db.commit()
    audit_log("approval_decision", "project", project_id, project["name"], f"{row['stage']} {decision}")
    subject = f"{escape(project['name'])}: {escape(row['stage'])} {decision} by the customer"   # HTML in Teams and mail
    body = f"{escape(session['user_name'])} {decision} <b>{escape(row['stage'])}</b>." + (f"<br>{escape(comment)}" if comment else "")
    notify_event(project, subject, body, channels={"email": False, "teams": True})
    notify_participants(project_id, subject, body, exclude_user_id=session["user_id"], kind="approval")
    if decision == "declined":
        rules.fire("stage_declined", project_id, {"stage": row["stage"]})
    return None


def _date_problem(form):
    """Dates arrive as YYYY-MM-DD from the date pickers; anything else would
    break every page that does arithmetic on them (the routes store
    parse_date(value) once this passes). Then the project form's other
    fields: see _field_problem."""
    dates = {}
    for key, label in (("po_date", "PO date"), ("start_date", "Start date"), ("target_end_date", "Target end date")):
        try:
            dates[key] = parse_date(form.get(key))
        except ValueError as exc:
            return f"{label} must be {exc}"
    if dates["start_date"] and dates["target_end_date"] and dates["target_end_date"] < dates["start_date"]:
        return "The target end date is before the start date"
    return _field_problem(form)


PROJECT_TEXT_FIELDS = (("name", "Project name", 200), ("client", "Client", 200), ("po_number", "PO number", 100),
                       ("account_manager_name", "Account manager", 200), ("partner_name", "Partner", 200),
                       ("partner_account_manager_name", "Partner account manager", 200), ("outsourcer_name", "Outsourcer", 200),
                       ("vendor_name", "Vendor", 200), ("product_name", "Product", 200))
PROJECT_EMAIL_FIELDS = (("account_manager_email", "Account manager email"), ("partner_account_manager_email", "Partner account manager email"),
                        ("outsourcer_email", "Outsourcer email"))


def _field_problem(form):
    """The new / edit project form's text fields: one line each, of a sane
    length; addresses that look like addresses; `via` from its list."""
    from constants import VIA_OPTIONS
    for key, label, limit in PROJECT_TEXT_FIELDS:
        value = form.get(key) or ""
        if len(value) > limit or "\x00" in value or "\n" in value or "\r" in value:
            return f"{label}: one line, at most {limit} characters"
    for key, label in PROJECT_EMAIL_FIELDS:
        value = (form.get(key) or "").strip()
        if value and not valid_email(value):
            return f"{label} does not look like an email address"
    if (form.get("via") or "") not in ("", *VIA_OPTIONS):
        return f"Via is one of: {', '.join(VIA_OPTIONS)}"
    if form.get("via") == "Partner" and not (form.get("partner_name") or "").strip():
        return "Pick the partner the deal came through"
    return None


def save_document(project_id, file, category, uploaded_by, pending=False):
    """Save an uploaded file to disk + documents table (+ OneDrive mirror if
    enabled). Assumes the caller already validated file/category — shared by
    the Documents panel upload and project creation's bundled PO upload.
    `pending`: an outside account's upload, held for staff review and not
    mirrored until accepted (services/doc_review.py).
    Returns (the file's name as given, the documents row id)."""
    # the name people gave the file, in any script (secure_filename kept only ASCII:
    # "日本語の報告.pdf" became "pdf"); on disk it is a random id with a plain extension
    original_name = "".join(ch for ch in os.path.basename(file.filename.replace("\\", "/")) if ch.isprintable()).strip()[:200] or "document"
    ext = os.path.splitext(original_name)[1].lower()
    stored_name = uuid.uuid4().hex + (ext if ext[1:].isascii() and ext[1:].isalnum() else "")
    project_dir = os.path.join(UPLOAD_DIR, str(project_id))
    os.makedirs(project_dir, exist_ok=True)
    file.save(os.path.join(project_dir, stored_name))

    db = get_db()
    now = datetime.utcnow().isoformat()
    doc_id = db.execute(
        """INSERT INTO documents (project_id, category, filename, stored_name, uploaded_by, uploaded_at, review_status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (project_id, category, original_name, stored_name, uploaded_by, now, doc_review.PENDING if pending else doc_review.ACCEPTED),
    ).lastrowid
    touch_project(db, project_id)
    db.commit()
    if not pending:
        mirror_document(project_id, category, original_name, stored_name)
    return original_name, doc_id


def mirror_document(project_id, category, original_name, stored_name):
    """Copy a document to OneDrive when the policy says so (an upload, or a reviewed one accepted)."""
    if not policy("onedrive_mirror_uploads_enabled"):
        return
    project = get_db().execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    remote_path = f"Odin-Documents/{project_id}-{secure_filename(project['name'])}/{category}/{secure_filename(original_name) or stored_name}"
    ok, error = graph.upload_file(os.path.join(UPLOAD_DIR, str(project_id), stored_name), remote_path)
    if not ok:
        app.logger.warning("OneDrive mirror of an upload failed: %s", error)


@app.route("/projects/<int:project_id>/documents", methods=["POST"])
@login_required
def document_upload(project_id):
    """The documents panel's upload (upload_document and the manage_documents
    project role), and the one door for an upload ask (services/asks.py): with
    `ask_id`, the person the ask is on uploads into its category only, rate
    limited, and the ask is done. Nothing else is opened to them."""
    db = get_db()
    if not load_project(project_id):
        abort(404)
    ask = None
    if request.form.get("ask_id"):
        ask = asks.own_ask(project_id, as_id(request.form.get("ask_id")), session["user_id"])
        if ask is None or ask["kind"] != "upload":
            abort(403)
        if asks.limited(session["user_id"]):
            abort(429, description="Too many changes in a minute; wait a moment")
    elif not project_allows(project_id, "manage_documents"):
        abort(403)
    file = request.files.get("file")
    category = ask["ask_category"] if ask else request.form.get("category", "")
    if not file or not file.filename:
        flash("No file selected", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    if problem := upload_problem(file):
        flash(problem, "error")
        return redirect(url_for("project_detail", project_id=project_id))
    if not content_matches_extension(file):
        flash("That file's contents don't match its extension", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    if category not in get_doc_category_names():
        flash("Invalid category", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    # an outside account's file waits for staff review before anyone opens or uses it (services/doc_review.py)
    pending = session.get("kind") == "external"
    original_name, doc_id = save_document(project_id, file, category, session["user_name"], pending=pending)
    audit_log("upload_document", "project", project_id, None, f"{category}: {original_name}" + (" (held for review)" if pending else ""))
    project = load_project(project_id)
    if ask:
        asks.record_upload(db, ask, doc_id, session["user_id"], session["user_name"])
        db.commit()
        audit_log("complete_ask", "project", project_id, None, f"upload: {ask['title'][:80]}")
    _tell_pm(project, f"{'Ask done on' if ask else 'Document added to'} {escape(project['name'])}",
             f"{escape(session['user_name'])} uploaded {'a file for review: ' if pending else ''}<b>{escape(original_name)}</b> ({escape(category)})"
             + (f" for <b>{escape(ask['title'])}</b>." if ask else ".") + (" Accept or reject it under Documents." if pending else ""))
    if not pending:   # a held file counts once it is accepted (document_review)
        rules.fire("document_uploaded", project_id, {"category": category, "file": original_name})

    flash(f"Uploaded {original_name}" + (". The team will review it." if pending else ""))
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/documents/<int:doc_id>/download")
@permission_required("download_document")
def document_download(project_id, doc_id):
    load_project(project_id)   # visibility decided in one place
    db = get_db()
    doc = db.execute(
        "SELECT * FROM documents WHERE id = ? AND project_id = ? AND deleted_at IS NULL", (doc_id, project_id)
    ).fetchone()
    if doc is None or (session.get("kind") == "external" and doc["category"] in partner_hidden_categories(db)):
        abort(404)   # a kind partners never see does not exist for them
    if doc["review_status"] != doc_review.ACCEPTED:   # nobody opens an outside upload before staff accept it (loophole 65)
        abort(409, description="This file has not been reviewed yet: accept it under Documents first")
    # Reads are data access; SOC 2 wants them in the trail as much as writes.
    audit_log("download_document", "document", doc_id, doc["filename"], f"project_id={project_id}")
    project_dir = os.path.join(UPLOAD_DIR, str(project_id))
    # as_attachment forces a download rather than letting the browser render
    # the file inline in this origin — the second half of the stored-XSS guard
    # that starts with the upload extension allowlist.
    return send_from_directory(
        project_dir, doc["stored_name"], download_name=doc["filename"], as_attachment=True
    )


@app.route("/projects/<int:project_id>/documents/<int:doc_id>/review", methods=["POST"])
@permission_required("upload_document")
@project_role_required("manage_documents")
def document_review(project_id, doc_id):
    """Accept or reject a file an outside account uploaded (services/doc_review.py).
    Accept makes it a normal document; reject deletes it, reopens the ask and
    tells whoever uploaded it. Both audited."""
    project = load_project(project_id)
    db = get_db()
    doc = db.execute("SELECT * FROM documents WHERE id = ? AND project_id = ? AND deleted_at IS NULL AND review_status = ?",
                     (doc_id, project_id, doc_review.PENDING)).fetchone()
    if doc is None:
        abort(404)   # no such file waiting for review (or decided a moment ago)
    decision = (json_body() or request.form).get("decision")
    if decision not in ("accept", "reject"):
        abort(400, description="Send decision: accept or reject")
    if decision == "accept":
        if not doc_review.accept(db, doc_id, session["user_name"]):
            abort(404)
        audit_log("accept_document", "project", project_id, None, f"{doc['category']}: {doc['filename']}")
        mirror_document(project_id, doc["category"], doc["filename"], doc["stored_name"])
        rules.fire("document_uploaded", project_id, {"category": doc["category"], "file": doc["filename"]})
        flash(f"Accepted {doc['filename']}")
        return redirect(url_for("project_detail", project_id=project_id))
    done, ask = doc_review.reject(db, doc_id, session["user_name"])
    if not done:
        abort(404)
    audit_log("reject_document", "project", project_id, None, f"{doc['category']}: {doc['filename']}" + (f" for {ask['title'][:80]}, reopened" if ask else ""))
    if ask and ask["by_id"]:
        notify_users([ask["by_id"]], "assigned", project_id, f"Upload again: {escape(ask['title'])}",
                     f"{escape(session['user_name'])} could not accept <b>{escape(doc['filename'])}</b> for <b>{escape(ask['title'])}</b> "
                     f"on {escape(project['name'])}. Please upload the file again.", exclude_user_id=session["user_id"])
    flash(f"Rejected {doc['filename']}" + (f": {ask['title']} is open again" if ask else ""))
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/documents/<int:doc_id>/delete", methods=["POST"])
@permission_required("delete_document")
@project_role_required("manage_documents")
def document_delete(project_id, doc_id):
    load_project(project_id)   # visibility decided in one place
    db = get_db()
    doc = db.execute(
        "SELECT * FROM documents WHERE id = ? AND project_id = ? AND deleted_at IS NULL", (doc_id, project_id)
    ).fetchone()
    if doc is None:
        abort(404)   # nothing to delete is not a success (P3-19)
    if db.execute("SELECT 1 FROM signoffs WHERE document_id = ?", (doc_id,)).fetchone():
        flash("That is the signed sign-off copy — it is the record of acceptance and cannot be deleted", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    touch_project(db, project_id)
    if not soft_delete("documents", doc_id):
        abort(404)   # deleted by another request a moment ago
    audit_log("delete_document", "document", doc_id, doc["filename"], f"project_id={project_id}")
    offer_undo("undo_document", doc_id=doc_id)
    flash(f"Deleted {doc['filename']}. Undo {undo_note()}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
@permission_required("delete_project")
@project_role_required("manage_project")
def project_delete(project_id):
    db = get_db()
    # deleted_at filter matters: re-deleting would re-stamp deleted_at, restarting
    # the undo window and writing a second audit entry for one user action.
    project = load_project(project_id)
    if not project:
        abort(404)
    soft_delete("projects", project_id)
    # its documents carry the project's own stamp, so undo brings back these
    # and not ones deleted on their own before (test report B4)
    db.execute("UPDATE documents SET deleted_at = (SELECT deleted_at FROM projects WHERE id = ?) WHERE project_id = ? AND deleted_at IS NULL",
               (project_id, project_id))
    db.commit()
    audit_log("delete_project", "project", project_id, project["name"])
    offer_undo("undo_project", project_id=project_id)
    flash(f"Project deleted. Undo {undo_note()}")
    return redirect(url_for("board"))


@app.route("/projects/<int:project_id>/rotate-token", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_rotate_token(project_id):
    """Mint a fresh guest access token — instantly revokes any leaked old link."""
    db = get_db()
    project = load_project(project_id)
    if not project:
        abort(404)
    db.execute(   # a rotation also renews the links' life (policy guest_link_days)
        "UPDATE projects SET access_token = ?, customer_token = ?, guest_tokens_at = ? WHERE id = ?",
        (secrets.token_urlsafe(16), secrets.token_urlsafe(16), datetime.utcnow().isoformat(), project_id),
    )
    db.commit()
    audit_log("rotate_guest_token", "project", project_id, project["name"])
    flash("Guest links rotated — the previous vendor and customer links no longer work")
    return redirect(url_for("project_detail", project_id=project_id))


def _chosen_template(db, raw_id):
    """The template a new project copies its stages from: the one chosen on
    the form, else the first one. None only when Settings has no templates."""
    if raw_id:
        row = db.execute("SELECT id, name FROM stage_templates WHERE id = ?", (raw_id,)).fetchone()
        if row:
            return row
    chosen = policy("default_template")
    return (chosen and db.execute("SELECT id, name FROM stage_templates WHERE id = ?", (chosen,)).fetchone()) \
        or db.execute("SELECT id, name FROM stage_templates ORDER BY id LIMIT 1").fetchone()


# ---- participants: who is on the project, and as what ------------------------

_WRONG_KIND = "Customer is for the customer's own account; partners take Customer, Reseller or Contractor"


def _wrong_kind_for_role(user, role):
    # staff never stand in for the customer (stage approvals); partners never hold a staff role (tasks, documents)
    return (role == "Customer" and user["kind"] != "external") or (user["kind"] == "external" and role not in EXTERNAL_PROJECT_ROLES)


@app.route("/projects/<int:project_id>/participants/add", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def participant_add(project_id):
    project = load_project(project_id)
    role = request.form.get("role", "")
    raw = request.form.get("user_id", "")
    db = get_db()
    user = db.execute("SELECT id, name, kind, email FROM users WHERE id = ? AND active = 1", (raw,)).fetchone() if raw.isdigit() else None
    from policies import email_domain_allowed
    if user is None:
        flash("Pick an active user", "error")
    elif user["kind"] == "external" and not email_domain_allowed(user["email"] or ""):
        # adding by id is the invite's second door: the same partner domains apply (P3-14)
        flash(f"Partners can only be added from: {', '.join(policy('external_domains'))} (Settings › Sign-in & security)", "error")
    elif role not in PROJECT_ROLES:
        flash("Pick a role", "error")
    elif _wrong_kind_for_role(user, role):
        flash(_WRONG_KIND, "error")
    elif role == PROJECT_MANAGER and user["id"] != project["owner_id"]:
        flash("The project manager is the owner — change the owner on Edit", "error")
    elif user["id"] == project["owner_id"] and role != PROJECT_MANAGER:
        flash("The owner is the project manager", "error")
    else:
        db.execute(
            "INSERT INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
            (project_id, user["id"], role, session["user_id"], datetime.utcnow().isoformat()),
        )
        moot = _moot_approvals(db, project_id)   # a Customer re-roled away may leave nobody to decide
        db.commit()
        audit_log("add_participant", "project", project_id, project["name"], f"{user['name']} as {role}" + (f"; {moot} pending approval withdrawn" if moot else ""))
        notify_users([user["id"]], "assigned", project_id, f"You are on {escape(project['name'])}",
                     f"{escape(session['user_name'])} added you to <b>{escape(project['name'])}</b> as {escape(role)}.", exclude_user_id=session["user_id"], link=f"/projects/{project_id}")
        flash(f"{user['name']} added as {role}")
    return redirect(url_for("project_detail", project_id=project_id) + "#team")


@app.route("/projects/<int:project_id>/participants/invite", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def participant_invite(project_id):
    """Add an outside party by email. An address already belonging to a staff
    account just joins the team; anyone else becomes an external account
    (no password) and receives a single-use sign-in link."""
    from routes.auth import issue_login_link, send_login_link
    project = load_project(project_id)
    email = request.form.get("email", "").strip().lower()[:200]
    name = request.form.get("name", "").strip()[:80] or email.split("@")[0]
    role = request.form.get("role", "")
    db = get_db()
    from policies import email_domain_allowed, policy
    if not valid_email(email):
        flash("Enter a valid email address", "error")
    elif not db.execute("SELECT 1 FROM users WHERE lower(email) = ? AND kind = 'internal'", (email,)).fetchone() and not email_domain_allowed(email):
        flash(f"Partners can only be invited from: {', '.join(policy('external_domains'))} (Settings › Sign-in & security)", "error")
    elif role not in EXTERNAL_PROJECT_ROLES:
        flash("Pick a role", "error")
    elif db.execute("SELECT 1 FROM users WHERE lower(username) = ? AND lower(COALESCE(email, '')) != ?", (email, email)).fetchone():
        flash("That address is another account's username; ask an admin to change it", "error")   # sign-in takes either
    else:
        user = db.execute("SELECT * FROM users WHERE lower(email) = ?", (email,)).fetchone()
        now = datetime.utcnow().isoformat()
        created = user is None   # only a brand-new account may have its first link carried by hand
        if user is None:
            db.execute(
                "INSERT INTO users (username, password_hash, name, role, active, email, created_at, kind, theme, accent) "
                "VALUES (?, 'external:no-password', ?, 'External', 1, ?, ?, 'external', ?, ?)",
                (email, name, email, now, policy("default_theme"), policy("default_accent")),
            )
            user = db.execute("SELECT * FROM users WHERE lower(email) = ?", (email,)).fetchone()
            audit_log("create_user", "user", user["id"], email, "external, invited")
        if user["id"] == project["owner_id"]:
            flash("That is the project manager", "error")
            return redirect(url_for("project_detail", project_id=project_id) + "#team")
        if _wrong_kind_for_role(user, role):   # the invite is a second way onto the team (system map #14)
            flash(_WRONG_KIND, "error")
            return redirect(url_for("project_detail", project_id=project_id) + "#team")
        db.execute(
            "INSERT INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
            (project_id, user["id"], role, session["user_id"], now),
        )
        db.commit()
        audit_log("invite_participant", "project", project_id, project["name"], f"{email} as {role}")
        if user["kind"] != "external" or not user["active"]:
            flash(f"{user['name']} added as {role}" + ("" if user["active"] else " (account is deactivated)"))
        else:
            raw = issue_login_link(user["id"], session["user_id"])
            ok, error = send_login_link(user, raw, session["user_name"], project["name"], project_id)
            if ok:
                flash(f"{user['name']} added as {role} — sign-in link emailed to {email}")
            elif not created:
                # An account that already existed may be on other projects: a link
                # handed to the inviter would let them act as that person there.
                flash(f"{user['name']} added as {role}. Email could not be sent ({error or 'not configured'}); "
                      "they can ask for a sign-in link on the sign-in page.")
            else:
                # No mail yet (Microsoft 365 not connected) — the inviter carries
                # the link by hand. It still works once and expires in 30 minutes.
                from core import external_url
                link = external_url("auth_link_consume", token=raw, next=url_for("project_detail", project_id=project_id))
                flash(f"{user['name']} added as {role}. Email could not be sent "
                      f"({error or 'not configured'}) — send them this link yourself: {link}")
    return redirect(url_for("project_detail", project_id=project_id) + "#team")


@app.route("/projects/<int:project_id>/participants/<int:participant_id>/remove", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def participant_remove(project_id, participant_id):
    project = load_project(project_id)
    db = get_db()
    row = db.execute(
        "SELECT pp.*, u.name FROM project_participants pp JOIN users u ON u.id = pp.user_id WHERE pp.id = ? AND pp.project_id = ?",
        (participant_id, project_id),
    ).fetchone()
    if row is None:
        abort(404)
    if row["user_id"] == project["owner_id"]:
        flash("The project manager cannot be removed — reassign the owner on Edit", "error")
    else:
        db.execute("DELETE FROM project_participants WHERE id = ?", (participant_id,))
        # their open work comes to the project manager, so its reminders still reach someone (P3-23);
        # a colleague's tasks stay theirs only while they could still see the rollout (staff see every one)
        kind = db.execute("SELECT kind FROM users WHERE id = ?", (row["user_id"],)).fetchone()[0]
        moved = db.execute("UPDATE tasks SET assignee_id = ? WHERE project_id = ? AND assignee_id = ? AND done = 0",
                           (project["owner_id"], project_id, row["user_id"])).rowcount if kind == "external" else 0
        moot = _moot_approvals(db, project_id)
        db.commit()
        said = "".join([f"; {moved} open {plural(moved, 'task')} moved to the project manager" if moved else "",
                        f"; {moot} pending approval withdrawn (no Customer left to decide)" if moot else ""])
        audit_log("remove_participant", "project", project_id, project["name"], f"{row['name']} ({row['role']}){said}")
        if moved:
            notify_users([project["owner_id"]], "assigned", project_id, f"{moved} {plural(moved, 'task')} on {escape(project['name'])} came to you",
                         f"{escape(session['user_name'])} removed {escape(row['name'])} from <b>{escape(project['name'])}</b>; their open tasks are yours now.",
                         exclude_user_id=session["user_id"], link=f"/projects/{project_id}")
        flash(f"{row['name']} removed{said}")
    return redirect(url_for("project_detail", project_id=project_id) + "#team")


def _moot_approvals(db, project_id):
    """With nobody left in the Customer role, a pending approval could never be
    decided (and would count as waiting for ever): withdraw it. The caller commits."""
    if customer_ids(project_id):
        return 0
    return db.execute("UPDATE stage_approvals SET status = 'superseded' WHERE project_id = ? AND status = 'pending'", (project_id,)).rowcount


# ---- a project's own stages: add / rename / reorder / delete / SLAs ---------

def _stage_change(project_id, action, error, detail):
    if error:
        flash(error, "error")
    else:
        audit_log(action, "project", project_id, load_project(project_id)["name"], detail)
    return redirect(url_for("project_detail", project_id=project_id) + "#stages")


@app.route("/projects/<int:project_id>/stages/add", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_add(project_id):
    load_project(project_id)
    name = request.form.get("name", "")
    return _stage_change(project_id, "add_project_stage", stage_ops.add_stage("project", project_id, name), name)


@app.route("/projects/<int:project_id>/stages/<int:stage_id>/rename", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_rename(project_id, stage_id):
    load_project(project_id)
    name = request.form.get("name", "")
    return _stage_change(project_id, "rename_project_stage", stage_ops.rename_stage("project", project_id, stage_id, name), f"stage_id={stage_id} -> {name}")


@app.route("/projects/<int:project_id>/stages/<int:stage_id>/move", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_move(project_id, stage_id):
    load_project(project_id)
    direction = request.form.get("direction", "")
    return _stage_change(project_id, "move_project_stage", stage_ops.move_stage("project", project_id, stage_id, direction), f"stage_id={stage_id} {direction}")


@app.route("/projects/<int:project_id>/stages/<int:stage_id>/delete", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_delete(project_id, stage_id):
    load_project(project_id)
    return _stage_change(project_id, "delete_project_stage", stage_ops.delete_stage("project", project_id, stage_id), f"stage_id={stage_id}")


@app.route("/projects/<int:project_id>/stages/sla", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_sla(project_id):
    load_project(project_id)
    return _stage_change(project_id, "update_project_stage_slas", stage_ops.set_slas("project", project_id, request.form), None)


@app.route("/projects/<int:project_id>/stages/gates", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_gates(project_id):
    """What each stage asks before the rollout leaves it (services/gates.py)."""
    load_project(project_id)
    return _stage_change(project_id, "update_project_stage_gates", stage_ops.set_gates("project", project_id, request.form), None)


@app.route("/undo/project/<int:project_id>", methods=["POST"])
@permission_required("delete_project")
@project_role_required("manage_project")
def undo_project(project_id):
    project = load_project(project_id, include_deleted=True)
    stamp = project["deleted_at"]
    if stamp is None:   # already back (the CRM sent its deal again, services/intake.create)
        flash(f"Project '{project['name']}' is already restored")
        return redirect(url_for("project_detail", project_id=project_id))
    twin = project["intake_deal_id"] and get_db().execute(
        "SELECT id, name FROM projects WHERE intake_deal_id = ? AND deleted_at IS NULL AND id != ?", (project["intake_deal_id"], project_id)).fetchone()
    if twin:   # one live rollout per deal id (idx_projects_intake_deal_live)
        flash(f"Not restored: '{twin['name']}' is the live rollout for deal {project['intake_deal_id']} now", "error")
        return redirect(url_for("project_detail", project_id=twin["id"]))
    if not restore_deleted("projects", project_id):
        flash("Too late to undo — the undo window has passed", "error")
        return redirect(url_for("projects_list"))
    db = get_db()
    # only the documents that went with the project; one deleted on its own stays deleted
    db.execute("UPDATE documents SET deleted_at = NULL WHERE project_id = ? AND deleted_at = ?", (project_id, stamp))
    db.commit()
    project = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    audit_log("restore_project", "project", project_id, project["name"])
    flash(f"Project '{project['name']}' restored")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/undo/document/<int:doc_id>", methods=["POST"])
@permission_required("delete_document")
def undo_document(doc_id):
    db = get_db()
    row = db.execute("SELECT project_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if row is None:
        abort(404)
    load_project(row["project_id"])   # visible to this session, and theirs to manage
    if not project_allows(row["project_id"], "manage_documents"):
        abort(403)
    if not restore_deleted("documents", doc_id):
        flash("Too late to undo — the undo window has passed", "error")
        return redirect(url_for("project_detail", project_id=row["project_id"]))
    doc = db.execute("SELECT project_id, filename FROM documents WHERE id = ? AND deleted_at IS NULL", (doc_id,)).fetchone()
    audit_log("restore_document", "document", doc_id, doc["filename"], f"project_id={doc['project_id']}")
    flash(f"Document '{doc['filename']}' restored")
    return redirect(url_for("project_detail", project_id=doc["project_id"]))


@app.route("/projects/<int:project_id>/note", methods=["POST"])
@permission_required("add_project_note")
def project_note(project_id):
    project = load_project(project_id)
    note_text = request.form.get("note", "").strip()[:5000]
    if not note_text:
        flash("Write the note first", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    db = get_db()
    now = datetime.utcnow().isoformat()
    # An external participant's note is theirs to see again — and the
    # project's other outsiders may see it too. A staff note stays internal
    # unless it was written for the customer (share=1).
    shared = session.get("kind") == "external" or request.form.get("share") == "1"
    db.execute(
        "INSERT INTO status_notes (project_id, author, note, stage, created_at, guest_visible, author_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_id, session["user_name"], note_text, project["stage"], now, 1 if shared else 0, session["user_id"]),
    )
    touch_project(db, project_id)
    db.commit()
    audit_log("add_project_note", "project", project_id, project["name"], ("[shared] " if shared and session.get("kind") != "external" else "") + note_text)
    # an internal note never reaches an outsider, mention or not: they would be mailed words they may not read
    mentioned = mentions_in(project_id, note_text, staff_only=not shared)
    html = f"{escape(session['user_name'])} wrote:<br>{escape(note_text)}"
    if mentioned:
        notify_users(mentioned, "mention", project_id, f"{escape(session['user_name'])} mentioned you on {escape(project['name'])}", html,
                     exclude_user_id=session["user_id"])
    if project["owner_id"] not in mentioned:      # a mention already told the PM
        _tell_pm(project, f"New note on {escape(project['name'])}", html)
    return redirect(url_for("project_detail", project_id=project_id))


def stage_entry_note_ids(project_id):
    """Ids of the notes that record a project entering a stage. The stage
    timeline (days per stage, cycle time, the report) is rebuilt from these,
    so they may be corrected but never deleted."""
    names = get_stage_names(project_id)
    prev = names[0] if names else None
    ids = set()
    for n in get_db().execute("SELECT id, stage FROM status_notes WHERE project_id = ? ORDER BY created_at, id", (project_id,)):
        if n["stage"] != prev:
            ids.add(n["id"])
        prev = n["stage"]
    return ids


def _own_note(project_id, note_id):
    load_project(project_id)   # visibility decided in one place
    note = get_db().execute("SELECT * FROM status_notes WHERE id = ? AND project_id = ?", (note_id, project_id)).fetchone()
    if note is None:
        abort(404)
    if note["author_id"] is None or note["author_id"] != session["user_id"]:
        abort(403)   # only the author corrects their words
    # the note written with a customer's approval decision is part of that record (decide_approval)
    if get_db().execute("SELECT 1 FROM stage_approvals WHERE project_id = ? AND decided_at = ? AND decided_by = ?",
                        (project_id, note["created_at"], note["author"])).fetchone():
        abort(403, description="This note records an approval decision, so it stays as written")
    return note


@app.route("/projects/<int:project_id>/notes/<int:note_id>/edit", methods=["POST"])
@permission_required("add_project_note")   # the matrix's note right, as for writing one (P3-14)
def note_edit(project_id, note_id):
    note = _own_note(project_id, note_id)
    text = request.form.get("note", "").strip()[:5000]
    if not text:
        flash("A note needs some text — delete it instead", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    db = get_db()
    db.execute("UPDATE status_notes SET note = ?, edited_at = ? WHERE id = ?", (text, datetime.utcnow().isoformat(), note_id))
    db.commit()
    audit_log("edit_project_note", "project", project_id, None, f"note {note_id}: {note['note'][:80]} -> {text[:80]}")
    flash("Note updated")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/notes/<int:note_id>/delete", methods=["POST"])
@permission_required("add_project_note")
def note_delete(project_id, note_id):
    note = _own_note(project_id, note_id)
    if note_id in stage_entry_note_ids(project_id):
        flash("This note records a stage change, so it stays in the history — edit its text instead", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    db = get_db()
    db.execute("DELETE FROM status_notes WHERE id = ?", (note_id,))
    db.commit()
    audit_log("delete_project_note", "project", project_id, None, f"note {note_id}: {note['note'][:200]}")
    flash("Note deleted")
    return redirect(url_for("project_detail", project_id=project_id))


def mentions_in(project_id, text, staff_only=False):
    """User ids a note mentions: "@Full Name", "@username", or "@First" when
    only one person on the team has that first name. Only people on the
    project can be mentioned — a mention never reaches an outsider — and
    with `staff_only` (an internal note) only staff."""
    low = (text or "").lower()
    if "@" not in low:
        return []
    team = get_db().execute(
        "SELECT u.id, u.name, u.username FROM project_participants pp JOIN users u ON u.id = pp.user_id "
        "WHERE pp.project_id = ? AND u.active = 1" + (" AND u.kind = 'internal'" if staff_only else ""), (project_id,),
    ).fetchall()
    firsts = {}
    for r in team:
        firsts.setdefault(r["name"].split()[0].lower(), []).append(r["id"])
    found = []
    for r in team:
        first = r["name"].split()[0].lower()
        handles = [r["name"].lower(), r["username"].lower()] + ([first] if len(firsts[first]) == 1 else [])
        # any occurrence that ends at a word boundary: "@annabel and @ann" mentions Ann too (P3-20)
        if any(re.search("@" + re.escape(h) + r"(?![^\W_])", low) for h in handles):
            found.append(r["id"])
    return found


def _tell_pm(project, subject, html):
    """The project manager hears about work done on their project by anyone
    else — a note, a finished task, a document. Email only: the Teams
    channel carries stage changes and alerts, not every note."""
    notify_users([project["owner_id"]], "activity", project["id"], subject, html, exclude_user_id=session.get("user_id"))


def _notify_assignee(assignee_id, project_id, title):
    """Tell someone a task landed on them (never when you assign yourself)."""
    if not assignee_id or int(assignee_id) == session.get("user_id"):
        return
    project = get_db().execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    notify_users(
        [int(assignee_id)], "assigned", project_id,
        f"Task assigned to you: {escape(title)}",
        f"{escape(session.get('user_name', 'Someone'))} assigned you "
        f"\"{escape(title)}\" on rollout {escape(project['name'] if project else '')}.",
        exclude_user_id=session.get("user_id"),
    )


# The task routes serve two front ends: the Jinja project page posts forms
# and expects a redirect, the React flow screen posts JSON and expects JSON.
# One route each — same permission, same audit row, same validation.

def _task_input():
    form = json_body() or request.form
    # a list or number where text belongs is a 400, never a crash on .strip()
    if any(form.get(k) is not None and not isinstance(form.get(k), str) for k in ("title", "due_date", "stage")):
        abort(400, description="Send the title, due date and stage as text")
    return form


def _task_reply(project_id, error=None, **payload):
    if request.is_json:
        return (jsonify(error=error), 400) if error else jsonify(ok=True, **payload)
    if error:
        flash(error, "error")
    return redirect(url_for("project_detail", project_id=project_id) + "#tasks")


def _task_stage(project_id, requested):
    """A stage name from this project's list, or None for 'current stage'."""
    return requested if requested and requested in get_stage_names(project_id) else None


def _assignee(db, project_id, raw):
    """The assignee, or None: an active staff account (staff see every
    project), or a partner on this project — never a partner from elsewhere,
    who would be told the name of a project they cannot open (test report FN-4)."""
    if raw in (None, "", 0, "0"):
        return None
    raw = as_id(raw)
    if not raw:
        return False   # something was picked, but not a person: refused, never quietly unassigned (sim L-21)
    ok = db.execute("SELECT 1 FROM users u WHERE u.id = ? AND u.active = 1 AND (u.kind = 'internal' OR EXISTS "
                    "(SELECT 1 FROM project_participants pp WHERE pp.project_id = ? AND pp.user_id = u.id))", (raw, project_id)).fetchone()
    return raw if ok else False


def _done_state(form):
    """(done, done_at) for a task added back by an undo: the state it was deleted
    in, with its original finish time when that is a real timestamp (else now)."""
    if not as_bool(form.get("done")):
        return 0, None
    at = form.get("done_at")
    try:
        at = datetime.fromisoformat(at).isoformat() if isinstance(at, str) else None
    except ValueError:
        at = None
    return 1, at or datetime.utcnow().isoformat()


def _due_problem(form):
    """A due date the reports can do arithmetic on (test report FN-3); the
    route stores parse_date(form["due_date"]) once this passes."""
    try:
        parse_date(form.get("due_date"))
    except ValueError as exc:
        return f"Due date must be {exc}"
    return None


def _links_and_hours(db, project_id, task_id, form, hours=None):
    """What a posted task waits on (None: not sent, unchanged) and its
    estimate, checked: tasks of this rollout only, never a loop
    (services/task_links.py). Raises ValueError with the reason."""
    waits = None
    if "waits_on" in form:
        raw = form.get("waits_on") if request.is_json else [x for x in form.getlist("waits_on") if x]
        waits = task_links.clean_ids(raw)
        task_links.check(db, project_id, task_id, waits)
    if "estimate_hours" in form:
        hours = template_tasks.clean_hours(form.get("estimate_hours"))
    return waits, hours


@app.route("/projects/<int:project_id>/tasks", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def task_add(project_id):
    db = get_db()
    project = load_project(project_id)
    if not project:
        abort(404)
    form = _task_input()
    try:
        title = text_field(form.get("title"), 200, "Title")   # too long is said, never cut (P2-27)
    except ValueError as exc:
        return _task_reply(project_id, str(exc))
    if not title:
        return _task_reply(project_id, "Task needs a title")
    assignee_id = _assignee(db, project_id, form.get("assignee_id"))
    if assignee_id is False:
        return _task_reply(project_id, "Pick an active colleague or someone on this rollout")
    if problem := _due_problem(form):
        return _task_reply(project_id, problem)
    try:
        waits, hours = _links_and_hours(db, project_id, None, form)
        kind, ask_category, ask_form = asks.clean_spec(form)   # a tick, a document, or a short form (services/asks.py)
    except ValueError as exc:
        return _task_reply(project_id, str(exc))
    done, done_at = _done_state(form)   # undo of a delete brings a finished task back finished
    try:
        every, until, stage = recurrence.clean_repeat(form, parse_date(form.get("due_date")), _task_stage(project_id, form.get("stage")), project["stage"])
    except ValueError as exc:
        return _task_reply(project_id, str(exc))
    task_id = insert_task(db, project_id, title, session["user_name"], assignee_id=assignee_id, due_date=parse_date(form.get("due_date")),
                          stage=_task_stage(project_id, form.get("stage")), done=done, done_at=done_at, estimate_hours=hours,
                          kind=kind, ask_category=ask_category, ask_form=ask_form)
    if every:   # repeats (services/recurrence.py); "until the stage is done" pins the stage it names
        db.execute("UPDATE tasks SET recurrence = ?, recur_until = ?, stage = ? WHERE id = ?", (every, until, stage, task_id))
    if waits:
        task_links.replace(db, project_id, task_id, waits)
    if form.get("blocks"):   # the tasks that wait on this one (the undo of a delete gives their links back)
        try:
            raw = form.get("blocks") if request.is_json else [x for x in form.getlist("blocks") if x]
            task_links.add_successors(db, project_id, task_id, task_links.clean_ids(raw))
        except ValueError as exc:
            db.rollback()
            return _task_reply(project_id, str(exc).replace("waits_on", "blocks"))
    touch_project(db, project_id)
    db.commit()
    _notify_assignee(assignee_id, project_id, title)
    audit_log("add_task", "project", project_id, None, title[:80])
    return _task_reply(project_id, id=task_id)


@app.route("/projects/<int:project_id>/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def task_toggle(project_id, task_id):
    """Anyone who can edit the project, or the person the task is tagged to —
    a contractor ticks off their own work without gaining anything else."""
    project = load_project(project_id)   # visibility decided in one place
    db = get_db()
    task = db.execute("SELECT title, done, assignee_id, kind FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)).fetchone()
    if task is None:
        abort(404)
    manages = project_allows(project_id, "manage_tasks")
    if not (manages or task["assignee_id"] == session["user_id"]):
        abort(403)
    # an upload or a form is done by uploading or answering (services/asks.py); whoever manages the tasks may still tick it
    if not manages and task["kind"] in ("upload", "form"):
        return _task_reply(project_id, "Upload the file or answer the questions to finish this")
    if asks.limited(session["user_id"]):
        abort(429, description="Too many changes in a minute; wait a moment")
    # the page says what it wants (P2-26): a tick from a stale tab sets done, never flips it back open
    wanted = (json_body() if request.is_json else request.form).get("done")
    if wanted is None:
        new_done = 0 if task["done"] else 1   # an old caller that sends nothing: the flip
    elif (done := as_bool(wanted)) is not None:
        new_done = int(done)
    else:
        abort(400, description="Send done as true or false")
    if new_done == task["done"]:
        return _task_reply(project_id, done=bool(new_done))   # already so: nothing changed, nobody told
    # finish-to-start (services/task_links.py): a task waiting on open work is not ticked; an Admin may, on the record
    waits = ", ".join(w["title"] for w in task_links.open_predecessors(db, task_id)) if new_done else ""
    if waits and session.get("kind") == "external":   # the team's task titles stay with the team
        return _task_reply(project_id, f"This waits on {task_links.HIDDEN_WAIT}")
    if waits and session.get("role") != "Admin":
        return _task_reply(project_id, f"{task['title']} waits on {waits}: finish that first")
    # compare-and-set: of two ticks racing, only the first audits, notifies and fires rules (sim A5)
    if not db.execute(
        "UPDATE tasks SET done = ?, done_at = ? WHERE id = ? AND done = ?",
        (new_done, datetime.utcnow().isoformat() if new_done else None, task_id, task["done"]),
    ).rowcount:
        db.rollback()
        return _task_reply(project_id, done=bool(new_done))   # already so, as above
    touch_project(db, project_id)
    db.commit()
    audit_log("toggle_task", "project", project_id, None, f"{'done' if new_done else 'reopened'}: {task['title'][:80]}")
    if new_done:
        recurrence.spawn_next(db, task_id)   # a repeating task makes its next occurrence, once (services/recurrence.py)
    if waits:
        audit_log("override_task_wait", "project", project_id, None, f"{task['title'][:80]} ticked while it waits on {waits[:160]}")
    if new_done:
        _tell_pm(project, f"Task done on {escape(project['name'])}",
                 f"{escape(session['user_name'])} completed <b>{escape(task['title'])}</b>.")
        if asks.is_external(db, task["assignee_id"]):   # an ask ticked (an upload or a form fires from services/asks.save_answers)
            rules.fire("ask_completed", project_id, {"task": task["title"], "kind": task["kind"] or "task"})
    return _task_reply(project_id, done=bool(new_done))


@app.route("/projects/<int:project_id>/tasks/<int:task_id>/delete", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def task_delete(project_id, task_id):
    load_project(project_id)   # visibility decided in one place
    db = get_db()
    task = db.execute("SELECT title FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)).fetchone()
    if task is None:
        abort(404)
    task_links.forget(db, task_id)   # what waited on it is free to go
    db.execute("DELETE FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id))
    touch_project(db, project_id)
    db.commit()
    audit_log("delete_task", "project", project_id, None, task["title"][:80])
    return _task_reply(project_id)


@app.route("/projects/<int:project_id>/tasks/<int:task_id>/edit", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def task_edit(project_id, task_id):
    """Correct a task in place. Fixing a typo previously meant deleting the
    task and retyping it, which also threw away its done state. Only the
    fields sent change (title, assignee_id, due_date, stage, waits_on, estimate_hours): a JSON edit of
    the title keeps the assignee and the due date (L14). Whoever may manage
    tasks changes any field. The person a task is on may tick it (task_toggle)
    but not re-date it: that is managing the work (P2-10, PRODUCT.md: Viewers
    read, partners tick their own tasks)."""
    project = load_project(project_id)   # visibility decided in one place
    db = get_db()
    task = db.execute("SELECT id, title, assignee_id, due_date, stage, estimate_hours, kind, ask_category, ask_form FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)).fetchone()
    if task is None:
        abort(404)
    form = _task_input()
    try:
        title = text_field(form.get("title"), 200, "Title") if "title" in form else task["title"]
    except ValueError as exc:
        return _task_reply(project_id, str(exc))
    if not title:
        return _task_reply(project_id, "Task needs a title")
    assignee_id = _assignee(db, project_id, form.get("assignee_id")) if "assignee_id" in form else task["assignee_id"]
    if assignee_id is False:
        return _task_reply(project_id, "Pick an active colleague or someone on this rollout")
    if problem := _due_problem(form):
        return _task_reply(project_id, problem)
    try:
        waits, hours = _links_and_hours(db, project_id, task_id, form, task["estimate_hours"])
        kind, ask_category, ask_form = asks.clean_spec(form, task)
    except ValueError as exc:
        return _task_reply(project_id, str(exc))
    due = parse_date(form.get("due_date")) if "due_date" in form else task["due_date"]
    stage = _task_stage(project_id, form.get("stage")) if "stage" in form else task["stage"]
    try:   # Repeats (services/recurrence.py): only the keys sent change
        every, until, stage = recurrence.clean_repeat(form, due, stage, project["stage"], existing=db.execute("SELECT recurrence, recur_until FROM tasks WHERE id = ?", (task_id,)).fetchone())
    except ValueError as exc:
        return _task_reply(project_id, str(exc))
    db.execute(
        "UPDATE tasks SET title = ?, assignee_id = ?, due_date = ?, stage = ?, estimate_hours = ?, kind = ?, ask_category = ?, ask_form = ? WHERE id = ?",
        (title, assignee_id, due, stage, hours, kind, ask_category, ask_form, task_id),
    )
    db.execute("UPDATE tasks SET recurrence = ?, recur_until = ?, stage = ? WHERE id = ?", (every, until, stage, task_id))
    if waits is not None:
        task_links.replace(db, project_id, task_id, waits)
    # an upload or a form handed to someone else starts again: the last person's answers are theirs, not the new one's
    reset = kind in ("upload", "form") and str(assignee_id) != str(task["assignee_id"]) and asks.reset(db, task_id)
    touch_project(db, project_id)
    db.commit()
    # only ping on a genuine reassignment, not on every title tweak
    if assignee_id and str(assignee_id) != str(task["assignee_id"]):
        _notify_assignee(assignee_id, project_id, title)
    audit_log("edit_task", "project", project_id, None, title[:80] + (f" (was {task['title'][:60]})" if title != task["title"] else ""))
    if reset:
        audit_log("reset_ask", "project", project_id, None, f"{title[:80]}: reassigned, so the earlier answers were cleared and it is open again")
    return _task_reply(project_id)


@app.route("/api/projects/<int:project_id>/watch", methods=["POST"])
@permission_required("view_project_detail")
def api_project_watch(project_id):
    """Mute this rollout (a participant: no mail or Teams from it, the bell
    still shows it) or follow it (staff not on it: its events reach them).
    Body {on: true|false}. Audited; the answer is the new state."""
    from services.notifications import set_watch, watch_state
    project = load_project(project_id)
    state = watch_state(project_id, session["user_id"], session.get("kind"))
    if not state["can"]:
        return jsonify(error="Only someone on this rollout may mute it, and only staff may follow it"), 403
    on = json_body().get("on") is True
    set_watch(project_id, session["user_id"], state["can"], on)
    get_db().commit()
    audit_log(f"{'' if on else 'un'}{state['can']}_rollout", "project", project_id, project["name"])
    return jsonify(watch_state(project_id, session["user_id"], session.get("kind")))
