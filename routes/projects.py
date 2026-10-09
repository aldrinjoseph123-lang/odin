"""Project lifecycle routes: list/filter, CSV export, reports, create, detail,
stage/invoice/vendor-invoice updates, documents, notes, delete + undo.

Includes three shared helpers (filtered_projects_query, has_required_document,
save_document). Imported for route registration side effects.
"""
import csv
import io
import os
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
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup, escape
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
from core import app, as_id, json_body, parse_date, login_required, permission_required, project_allows, project_role_required, role_has_permission, undo_button, undo_note, write_required, project_scope
from security import content_matches_extension, upload_problem, valid_email, safe_csv_writer
from policies import local_today, policy
from spa import spa_index, spa_serves
from db import (
    UPLOAD_DIR,
    get_contact_lists,
    get_db,
    get_doc_category_names,
    get_setting,
    partner_hidden_categories,
    PROJECT_OPEN_SQL,
    copy_template_stages,
    my_project_ids,
    participants_for,
    set_project_manager,
    current_approval,
    is_customer_on,
    get_stage_names,
    get_terminal_stage,
    sla_for_project,
    stage_rows,
    restore_deleted,
    soft_delete,
    touch_project,
)
from services.alerts import get_alert_type_settings, schedule_status
from services.analytics import sla_by_stage, stage_sla_state
from services import stages as stage_ops
from services.audit import audit_log
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
    return project


def project_visible(project):
    if session.get("kind") != "external":
        return True
    return project["id"] in my_project_ids(session["user_id"])


@app.route("/projects")
@permission_required("view_projects")
def projects_list():
    if spa_serves("projects_list"):
        return spa_index()
    db = get_db()
    stage_filter = request.args.get("stage", "")
    show_closed = request.args.get("closed") == "1"
    view = request.args.get("view", "")
    delivery_mode_filter = request.args.get("delivery_mode", "")
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", DEFAULT_SORT)
    if sort not in SORT_COLUMNS:
        sort = DEFAULT_SORT
    direction = "asc" if request.args.get("dir") == "asc" else "desc"
    page = max(1, request.args.get("page", 1, type=int))

    # Remember how this list was filtered so the nav link can put the user back
    # where they were. Page is deliberately not stored — returning to the list
    # should start at the top of the result set, not mid-scroll.
    session["projects_query"] = {
        key: value for key, value in request.args.items()
        if key in ("view", "stage", "delivery_mode", "closed", "q", "sort", "dir") and value
    }

    query, params = filtered_projects_query(
        view, stage_filter, show_closed, delivery_mode_filter, search, sort, direction
    )

    total = db.execute(f"SELECT COUNT(*) AS c FROM ({query})", params).fetchone()["c"]
    total_pages = max(1, (total + PROJECTS_PER_PAGE - 1) // PROJECTS_PER_PAGE)
    page = min(page, total_pages)
    offset = (page - 1) * PROJECTS_PER_PAGE
    projects = db.execute(query + " LIMIT ? OFFSET ?", (*params, PROJECTS_PER_PAGE, offset)).fetchall()

    return render_template(
        "projects_list.html",
        projects=projects,
        stage_filter=stage_filter,
        show_closed=show_closed,
        view=view,
        delivery_mode_filter=delivery_mode_filter,
        search=search,
        sort=sort,
        direction=direction,
        page=page,
        total_pages=total_pages,
        total=total,
    )


def filtered_projects_query(view, stage_filter, show_closed, delivery_mode_filter="", search="", sort=DEFAULT_SORT, direction="desc"):
    query = "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.deleted_at IS NULL"
    scope_sql, params = project_scope()
    query += scope_sql
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
    elif stage_filter:
        query += " AND p.stage = ?"
        params.append(stage_filter)
    elif not show_closed:
        query += f" AND {PROJECT_OPEN_SQL}"
    if delivery_mode_filter:   # combines with every view and stage (test report FN-13: a stage silently dropped it)
        query += " AND p.delivery_mode = ?"
        params.append(delivery_mode_filter)
    if search:
        # free-text across the fields a user searches by. LIKE is parameterised;
        # the % wrapping is on the value, never interpolated into the SQL.
        query += " AND (p.name LIKE ? OR p.client LIKE ? OR p.po_number LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
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
    writer.writerow(
        [
            "Project Name", "Client", "PO Number", "PO Date", "Stage", "Owner",
            "Delivery Mode", "Outsourcer", "Vendor", "Product",
            "Start Date", "Target End Date", "Updated At",
        ]
    )
    for p in projects:
        writer.writerow(
            [
                p["name"], p["client"], p["po_number"], p["po_date"], p["stage"],
                p["owner_name"], p["delivery_mode"], p["outsourcer_name"], p["vendor_name"],
                p["product_name"], p["start_date"], p["target_end_date"], p["updated_at"],
            ]
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=projects.csv"},
    )


@app.route("/reports/all")
@permission_required("view_reports")
def report_all():
    if spa_serves("report_all"):
        return spa_index()
    db = get_db()
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE {PROJECT_OPEN_SQL} AND p.deleted_at IS NULL{project_scope()[0]} ORDER BY p.client, p.name",
        project_scope()[1],
    ).fetchall()
    return render_template(
        "report_all.html",
        projects=projects,
        generated_at=datetime.utcnow(),
    )


@app.route("/projects/<int:project_id>/report")
@permission_required("view_reports")
def report_single(project_id):
    """The project report. Editors see the latest saved version, or a fresh
    draft when nothing is saved yet (?draft=1 forces a fresh draft into the
    editor). Everyone else — partners, customers, viewers — sees only what
    was saved: the draft is built from internal notes and is the PM's to
    trim before it goes out."""
    if spa_serves("report_single"):
        return spa_index()
    return render_template("report_single.html", **report_context(project_id))


def report_context(project_id):
    """The report page's data, for Jinja and JSON alike. The plain-text
    report is internal (drafted from every note and the document list, the
    Client PO among them): partners and customers read the customer cut of
    a saved version on the rollout report instead."""
    from services.reports import draft_report, render_blocks, report_versions
    db = get_db()
    project = load_project(project_id)
    if session.get("kind") == "external":
        abort(404)
    can_edit = project_allows(project_id, "manage_project")
    versions = report_versions(project_id)
    wanted = request.args.get("v", type=as_id)
    current = None
    if versions:
        current = db.execute(
            "SELECT * FROM project_reports WHERE project_id = ? AND version = ?",
            (project_id, wanted or versions[0]["version"]),
        ).fetchone() or abort(404)
    draft = draft_report(project) if can_edit and (current is None or request.args.get("draft")) else None
    body = current["body"] if current else (draft or "")
    return dict(
        project=project, versions=versions, current=current, can_edit=can_edit,
        blocks=render_blocks(body), editor_text=draft if draft is not None else body,
        is_draft=current is None or bool(request.args.get("draft")),
    )


@app.route("/projects/<int:project_id>/report/save", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def report_save(project_id):
    from services.reports import save_report
    project = load_project(project_id)
    body = request.form.get("body", "").strip()[:50000]
    if not body:
        flash("The report is empty")
        return redirect(url_for("report_single", project_id=project_id))
    version = save_report(project_id, body, session["user_name"])
    audit_log("save_report", "project", project_id, project["name"], f"version {version}")
    flash(f"Report version {version} saved")
    return redirect(url_for("report_single", project_id=project_id))


@app.route("/projects/new", methods=["GET", "POST"])
@permission_required("create_project")
def project_new():
    if request.method == "GET" and spa_serves("project_new"):
        return spa_index()
    db = get_db()
    if request.method == "POST":
        po_document = request.files.get("po_document")
        if not po_document or not po_document.filename:
            flash(f"Upload a '{CLIENT_PO_DOC_CATEGORY}' document to create the project", "error")
            return redirect(url_for("project_new"))
        if problem := upload_problem(po_document):
            flash(problem, "error")
            return redirect(url_for("project_new"))
        if not content_matches_extension(po_document):
            flash("That file's contents don't match its extension", "error")
            return redirect(url_for("project_new"))

        template = _chosen_template(db, request.form.get("stage_template_id"))
        if template is None:
            flash("Create a stage template in Settings before adding projects", "error")
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
            flash(f"Template '{template['name']}' needs at least two stages: the work and the finish")
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
        # The project manager must be able to move stages. Someone who cannot
        # (a Contributor) names one and joins as a Coordinator.
        lead_id = session["user_id"]
        if not role_has_permission(session.get("role"), "edit_project_stage"):
            raw = request.form.get("owner_id", "")
            lead = db.execute("SELECT id, role FROM users WHERE id = ? AND active = 1 AND kind = 'internal'", (raw,)).fetchone() if raw.isdigit() else None
            if lead is None or not role_has_permission(lead["role"], "edit_project_stage"):
                flash("Choose a project manager who can move stages (an Admin or Member)", "error")
                return redirect(url_for("project_new"))
            lead_id = lead["id"]
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
        set_project_manager(db, project_id, lead_id, session["user_id"])
        team = request.form.getlist("team_user_ids") + ([str(session["user_id"])] if lead_id != session["user_id"] else [])
        for raw in team:
            if raw.isdigit() and int(raw) != lead_id and db.execute("SELECT 1 FROM users WHERE id = ? AND active = 1 AND kind = 'internal'", (raw,)).fetchone():
                db.execute(
                    "INSERT OR IGNORE INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, 'Coordinator', ?, ?)",
                    (project_id, int(raw), session["user_id"], now),
                )
        save_document(project_id, po_document, CLIENT_PO_DOC_CATEGORY, session["user_name"])
        db.commit()
        joined = [r[0] for r in db.execute("SELECT user_id FROM project_participants WHERE project_id = ? AND role = 'Coordinator'", (project_id,))]
        notify_users(joined, "assigned", project_id, f"You are on {escape(name)}",
                     f"{escape(session['user_name'])} added you to <b>{escape(name)}</b> as a Coordinator.", exclude_user_id=session["user_id"], link=f"/projects/{project_id}")
        if lead_id != session["user_id"]:   # test report FN-7: a PM named by someone else heard only by mail, which may be off
            notify_users([lead_id], "assigned", project_id, f"You manage {escape(name)}",
                         f"{escape(session['user_name'])} created <b>{escape(name)}</b> and made you its project manager.", link=f"/projects/{project_id}")
        audit_log("create_project", "project", project_id, name, f"client={request.form['client']}" + (f" manager_id={lead_id}" if lead_id != session["user_id"] else ""))
        notify_event(
            {"owner_id": lead_id},
            f"New project: {escape(name)}",
            f"Project '{escape(name)}' for {escape(request.form['client'])} was created"
            + (f" by {escape(session['user_name'])} and assigned to you." if lead_id != session["user_id"] else "."),
            channels={"email": False, "teams": True},   # the named PM already had "You manage …" by email (D12)
        )
        flash("Project created")
        return redirect(url_for("project_detail", project_id=project_id))   # straight to the new rollout (P14)
    users = db.execute("SELECT * FROM users ORDER BY name").fetchall()
    source = None
    duplicate_of = request.args.get("from", type=as_id)
    # only a project you may see can be duplicated; a stale link gives a blank form, not a 404
    if duplicate_of and db.execute("SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL", (duplicate_of,)).fetchone():
        source = load_project(duplicate_of)
    return render_template(
        "project_form.html",
        stage_templates=get_db().execute("SELECT id, name FROM stage_templates ORDER BY name").fetchall(), users=users, project=source, duplicating=bool(source),
        **get_contact_lists()
    )


@app.route("/projects/<int:project_id>")
@permission_required("view_project_detail")
def project_detail(project_id):
    if spa_serves("project_detail"):
        return spa_index()
    db = get_db()
    project = load_project(project_id)
    if project is None:
        flash("Project not found")
        return redirect(url_for("board"))
    notes = db.execute(
        "SELECT * FROM status_notes WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    ).fetchall()
    hidden = partner_hidden_categories(db) if session.get("kind") == "external" else set()
    documents = [d for d in db.execute(
        "SELECT * FROM documents WHERE project_id = ? AND deleted_at IS NULL ORDER BY uploaded_at DESC",
        (project_id,),
    ).fetchall() if d["category"] not in hidden]
    if not project["access_token"]:
        token = secrets.token_urlsafe(16)
        db.execute("UPDATE projects SET access_token = ? WHERE id = ?", (token, project_id))
        db.commit()
        project = load_project(project_id)
    tasks = db.execute(
        "SELECT t.*, u.name AS assignee_name FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id "
        "WHERE t.project_id = ? ORDER BY t.done ASC, t.due_date IS NULL, t.due_date ASC, t.id ASC",
        (project_id,),
    ).fetchall()
    task_users = db.execute("SELECT id, name FROM users WHERE active = 1 ORDER BY name").fetchall()
    return render_template(
        "project_detail.html",
        project=project,
        notes=notes,
        documents=documents,
        tasks=tasks,
        task_users=task_users,
        participants=participants_for(project_id),
        project_roles=PROJECT_ROLES,
        stages=stage_rows(project_id),
        schedule=schedule_status(project),
        sla=stage_sla_state(project, sla_for_project(project_id), get_terminal_stage(project_id)),
        today=local_today().isoformat(),
        has_client_po_doc=has_required_document(project_id, CLIENT_PO_DOC_CATEGORY),
        approval=current_approval(project_id),
        can_approve=is_customer_on(project_id, session["user_id"]),
        can_move=project_allows(project_id, "move_stage"),
        can_manage=project_allows(project_id, "manage_project"),
        can_tasks=project_allows(project_id, "manage_tasks"),
        can_docs=project_allows(project_id, "manage_documents"),
        **get_contact_lists(),
    )


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_edit(project_id):
    if request.method == "GET" and spa_serves("project_edit"):
        return spa_index()
    db = get_db()
    project = load_project(project_id)
    if project is None:
        flash("Project not found")
        return redirect(url_for("board"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()[:200]
        client = request.form.get("client", "").strip()[:200]
        if not name or not client:
            flash("Project name and client are required", "error")
            return redirect(url_for("project_edit", project_id=project_id))
        if problem := _date_problem(request.form):
            flash(problem, "error")
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
        flash("Project updated")
        return redirect(url_for("project_detail", project_id=project_id))

    users = db.execute("SELECT * FROM users ORDER BY name").fetchall()
    return render_template(
        "project_form.html",
        stage_templates=get_db().execute("SELECT id, name FROM stage_templates ORDER BY name").fetchall(), project=project, users=users, **get_contact_lists())


@app.route("/projects/<int:project_id>/stage", methods=["POST"])
@permission_required("edit_project_stage")
@project_role_required("move_stage")
def project_stage(project_id):
    stage = request.form.get("stage", "")
    error = change_stage(project_id, stage, request.form.get("note", "").strip()[:5000])
    if error:
        flash(error, "error")
        return redirect(url_for("project_detail", project_id=project_id))
    flash(Markup(f"Moved to {escape(stage)}. {undo_button('Undo', 'undo_stage_change', project_id=project_id, note_id=g.stage_note_id)} {undo_note()}"))
    if request.form.get("redirect") == "board":
        return redirect(url_for("board"))
    return redirect(url_for("project_detail", project_id=project_id))


def change_stage(project_id, new_stage, note_text, guest=None):
    """The one stage-change path (form, JSON and the vendor's guest link).
    Returns an error message or None; 404s when the project is gone. Staff
    callers must hold edit_project_stage; `guest` is (author, party) for the
    vendor link, which has no session and was checked by the guest route."""
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
    if new_stage not in get_stage_names(project_id):
        return "Invalid stage"
    if new_stage == project["stage"]:   # test report FN-8: it reset the SLA clock and re-notified everyone
        return f"The project is already in {new_stage}"
    from services.signoff import gate
    if blocked := gate(project, new_stage):
        return blocked
    now = datetime.utcnow().isoformat()
    # compare-and-set: of two submits racing, only the first moves the project
    # (a double click used to write two notes and notify twice; F-M5)
    moved = db.execute(
        "UPDATE projects SET stage = ?, updated_at = ?, stage_entered_at = ? WHERE id = ? AND stage = ? AND deleted_at IS NULL",
        (new_stage, now, now, project_id, project["stage"]),
    ).rowcount
    if not moved:
        db.rollback()
        return f"The project has just moved; it is no longer in {project['stage']}"
    terminal = new_stage == get_stage_names(project_id)[-1]
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
    g.stage_undo_url = url_for("undo_stage_change", project_id=project_id, note_id=cur.lastrowid)
    # A newer change makes an undecided older request moot; closing asks for
    # no approval (the sign-off is the customer's word on the finish, P7).
    ask_customer = bool(project["customer_approval"]) and not terminal
    if project["customer_approval"]:
        db.execute("UPDATE stage_approvals SET status = 'superseded' WHERE project_id = ? AND status = 'pending'", (project_id,))
    if ask_customer:
        db.execute(
            "INSERT INTO stage_approvals (project_id, stage, requested_by, requested_at) VALUES (?, ?, ?, ?)",
            (project_id, new_stage, actor_name, now),
        )
    db.commit()
    if guest:
        audit_log("guest_stage_change", "project", project_id, project["name"], f"stage={new_stage}; by={guest[0]}", actor=f"guest:{guest[1]}")
    else:
        audit_log("update_project_stage", "project", project_id, project["name"], f"stage={new_stage}")
    body = (f"Stage moved to <b>{escape(new_stage)}</b> by {escape(actor_name)}."
            + (f"<br>{escape(note_text)}" if note_text else ""))
    ask = "<br>Please review and approve this step."
    notify_event(project, f"Stage changed: {escape(project['name'])}", body + (ask if ask_customer else ""), channels={"email": False, "teams": True})
    # the customer is asked to approve as an approval (their own kind), everyone else hears of the move
    customers = [r[0] for r in db.execute("SELECT user_id FROM project_participants WHERE project_id = ? AND role = 'Customer'", (project_id,))] \
        if ask_customer else []
    team = [r[0] for r in db.execute("SELECT user_id FROM project_participants WHERE project_id = ?", (project_id,)) if r[0] not in customers]
    notify_users(team, "stage", project_id, f"{escape(project['name'])}: now in {escape(new_stage)}", body, exclude_user_id=actor_id)
    if customers:
        notify_users(customers, "approval", project_id, f"{escape(project['name'])}: please approve the move to {escape(new_stage)}", body + ask,
                     exclude_user_id=actor_id, link=f"/projects/{project_id}")
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
    if project is None:
        abort(404)
    note = db.execute("SELECT * FROM status_notes WHERE id = ? AND project_id = ? AND prev_stage IS NOT NULL", (note_id, project_id)).fetchone()
    cutoff = (datetime.utcnow() - timedelta(minutes=policy("undo_minutes"))).isoformat()
    later_move = note and db.execute(
        "SELECT 1 FROM status_notes WHERE project_id = ? AND prev_stage IS NOT NULL AND id > ?", (project_id, note_id)).fetchone()
    if (note is None or note["author_id"] != session["user_id"] or note["created_at"] < cutoff
            or later_move or project["stage"] != note["stage"] or note["prev_stage"] not in get_stage_names(project_id)):
        flash("That move can no longer be undone: it is too old, was made by someone else, or the project has moved since")
        return redirect(url_for("project_detail", project_id=project_id))
    now = datetime.utcnow().isoformat()
    db.execute("UPDATE projects SET stage = ?, stage_entered_at = ?, updated_at = ? WHERE id = ?",
               (note["prev_stage"], note["prev_entered_at"] or now, now, project_id))
    db.execute("DELETE FROM status_notes WHERE id = ?", (note_id,))
    # notes written since the move belong to the stage the project is back in;
    # left tagged with the undone stage they made a phantom visit in the history (D8)
    db.execute("UPDATE status_notes SET stage = ? WHERE project_id = ? AND prev_stage IS NULL AND stage = ? AND created_at >= ?",
               (note["prev_stage"], project_id, note["stage"], note["created_at"]))
    # The approval this move asked for goes — unless the customer already
    # decided it: that record stays, superseded. The one it superseded comes back.
    db.execute("DELETE FROM stage_approvals WHERE project_id = ? AND stage = ? AND requested_at = ? AND status = 'pending'", (project_id, note["stage"], note["created_at"]))
    db.execute("UPDATE stage_approvals SET status = 'superseded' WHERE project_id = ? AND stage = ? AND requested_at = ? AND status IN ('approved', 'declined')",
               (project_id, note["stage"], note["created_at"]))
    db.execute(
        "UPDATE stage_approvals SET status = 'pending' WHERE id = (SELECT id FROM stage_approvals WHERE project_id = ? AND stage = ?"
        " AND status = 'superseded' AND requested_at < ? ORDER BY requested_at DESC LIMIT 1)",
        (project_id, note["prev_stage"], note["created_at"]))
    db.commit()
    audit_log("undo_project_stage", "project", project_id, project["name"], f"stage={note['prev_stage']} (undid {note['stage']})")
    body = f"{escape(session['user_name'])} undid the move to <b>{escape(note['stage'])}</b>. The project is back in <b>{escape(note['prev_stage'])}</b>."
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
    if row["status"] != "pending" or decision not in ("approved", "declined"):
        return "That request is no longer open"
    comment = (comment or "").strip()[:2000]
    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE stage_approvals SET status = ?, decided_by = ?, decided_at = ?, comment = ? WHERE id = ?",
        (decision, session["user_name"], now, comment or None, approval_id),
    )
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
    return None


@app.route("/projects/<int:project_id>/approvals/<int:approval_id>/decide", methods=["POST"])
@login_required
def approval_decide(project_id, approval_id):
    error = decide_approval(project_id, approval_id, request.form.get("decision"), request.form.get("comment"))
    flash(error or "Thank you — your decision is recorded")
    return redirect(url_for("project_detail", project_id=project_id))


def has_required_document(project_id, category):
    db = get_db()
    return (
        db.execute(
            "SELECT 1 FROM documents WHERE project_id = ? AND category = ? AND deleted_at IS NULL LIMIT 1", (project_id, category)
        ).fetchone()
        is not None
    )


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


PROJECT_TEXT_FIELDS = (("po_number", "PO number", 100),   # name and client are capped where they are stored
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
    return None


def save_document(project_id, file, category, uploaded_by):
    """Save an uploaded file to disk + documents table (+ OneDrive mirror if
    enabled). Assumes the caller already validated file/category — shared by
    the Documents panel upload and project creation's bundled PO upload."""
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
    db.execute(
        """INSERT INTO documents (project_id, category, filename, stored_name, uploaded_by, uploaded_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (project_id, category, original_name, stored_name, uploaded_by, now),
    )
    touch_project(db, project_id)
    db.commit()

    if get_setting("onedrive_mirror_uploads_enabled") == "1":
        project = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
        remote_path = f"Odin-Documents/{project_id}-{secure_filename(project['name'])}/{category}/{secure_filename(original_name) or stored_name}"
        ok, error = graph.upload_file(os.path.join(project_dir, stored_name), remote_path)
        if not ok:
            print(f"[save_document] OneDrive mirror failed: {error}")
    return original_name


@app.route("/projects/<int:project_id>/documents", methods=["POST"])
@permission_required("upload_document")
@project_role_required("manage_documents")
def document_upload(project_id):
    db = get_db()
    if not load_project(project_id):
        abort(404)
    file = request.files.get("file")
    category = request.form.get("category", "")
    if not file or not file.filename:
        flash("No file selected")
        return redirect(url_for("project_detail", project_id=project_id))
    if problem := upload_problem(file):
        flash(problem)
        return redirect(url_for("project_detail", project_id=project_id))
    if not content_matches_extension(file):
        flash("That file's contents don't match its extension")
        return redirect(url_for("project_detail", project_id=project_id))
    if category not in get_doc_category_names():
        flash("Invalid category")
        return redirect(url_for("project_detail", project_id=project_id))
    original_name = save_document(project_id, file, category, session["user_name"])
    audit_log("upload_document", "project", project_id, None, f"{category}: {original_name}")
    project = load_project(project_id)
    _tell_pm(project, f"Document added to {escape(project['name'])}",
             f"{escape(session['user_name'])} uploaded <b>{escape(original_name)}</b> ({escape(category)}).")

    flash(f"Uploaded {original_name}")
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
    # Reads are data access; SOC 2 wants them in the trail as much as writes.
    audit_log("download_document", "document", doc_id, doc["filename"], f"project_id={project_id}")
    project_dir = os.path.join(UPLOAD_DIR, str(project_id))
    # as_attachment forces a download rather than letting the browser render
    # the file inline in this origin — the second half of the stored-XSS guard
    # that starts with the upload extension allowlist.
    return send_from_directory(
        project_dir, doc["stored_name"], download_name=doc["filename"], as_attachment=True
    )


@app.route("/projects/<int:project_id>/documents/<int:doc_id>/delete", methods=["POST"])
@permission_required("delete_document")
@project_role_required("manage_documents")
def document_delete(project_id, doc_id):
    load_project(project_id)   # visibility decided in one place
    db = get_db()
    doc = db.execute(
        "SELECT * FROM documents WHERE id = ? AND project_id = ? AND deleted_at IS NULL", (doc_id, project_id)
    ).fetchone()
    if doc is not None and db.execute("SELECT 1 FROM signoffs WHERE document_id = ?", (doc_id,)).fetchone():
        flash("That is the signed sign-off copy — it is the record of acceptance and cannot be deleted")
        return redirect(url_for("project_detail", project_id=project_id))
    if doc is not None:
        touch_project(db, project_id)
        soft_delete("documents", doc_id)
        audit_log("delete_document", "document", doc_id, doc["filename"], f"project_id={project_id}")
        flash(Markup(f"Deleted {escape(doc['filename'])}. {undo_button('Undo', 'undo_document', doc_id=doc_id)} {undo_note()}"))
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
    flash(Markup(f"Project deleted. {undo_button('Undo', 'undo_project', project_id=project_id)} {undo_note()}"))
    return redirect(url_for("board"))


@app.route("/projects/<int:project_id>/rotate-token", methods=["POST"])
@write_required
@project_role_required("manage_project")
def project_rotate_token(project_id):
    """Mint a fresh guest access token — instantly revokes any leaked old link."""
    db = get_db()
    project = load_project(project_id)
    if not project:
        abort(404)
    db.execute(
        "UPDATE projects SET access_token = ?, customer_token = ? WHERE id = ?",
        (secrets.token_urlsafe(16), secrets.token_urlsafe(16), project_id),
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
    user = db.execute("SELECT id, name, kind FROM users WHERE id = ? AND active = 1", (raw,)).fetchone() if raw.isdigit() else None
    if user is None:
        flash("Pick an active user")
    elif role not in PROJECT_ROLES:
        flash("Pick a role")
    elif _wrong_kind_for_role(user, role):
        flash(_WRONG_KIND)
    elif role == PROJECT_MANAGER and user["id"] != project["owner_id"]:
        flash("The project manager is the owner — change the owner on Edit")
    elif user["id"] == project["owner_id"] and role != PROJECT_MANAGER:
        flash("The owner is the project manager")
    else:
        db.execute(
            "INSERT INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
            (project_id, user["id"], role, session["user_id"], datetime.utcnow().isoformat()),
        )
        db.commit()
        audit_log("add_participant", "project", project_id, project["name"], f"{user['name']} as {role}")
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
        flash(f"Partners can only be invited from: {', '.join(policy('external_domains'))} (Settings → Sign-in & security)", "error")
    elif role not in EXTERNAL_PROJECT_ROLES:
        flash("Pick a role", "error")
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
                flash(Markup(f"{escape(user['name'])} added as {escape(role)}. Email could not be sent "
                             f"({escape(error or 'not configured')}) — send them this link yourself: "
                             f"<code>{escape(link)}</code>"))
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
        flash("The project manager cannot be removed — reassign the owner on Edit")
    else:
        db.execute("DELETE FROM project_participants WHERE id = ?", (participant_id,))
        db.commit()
        audit_log("remove_participant", "project", project_id, project["name"], f"{row['name']} ({row['role']})")
        flash(f"{row['name']} removed")
    return redirect(url_for("project_detail", project_id=project_id) + "#team")


# ---- a project's own stages: add / rename / reorder / delete / SLAs ---------

def _live_project(project_id):
    project = load_project(project_id)
    if project is None:
        abort(404)
    return project


def _stage_change(project_id, action, error, detail):
    if error:
        flash(error)
    else:
        audit_log(action, "project", project_id, _live_project(project_id)["name"], detail)
    return redirect(url_for("project_detail", project_id=project_id) + "#stages")


@app.route("/projects/<int:project_id>/stages/add", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_add(project_id):
    _live_project(project_id)
    name = request.form.get("name", "")
    return _stage_change(project_id, "add_project_stage", stage_ops.add_stage("project", project_id, name), name)


@app.route("/projects/<int:project_id>/stages/<int:stage_id>/rename", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_rename(project_id, stage_id):
    _live_project(project_id)
    name = request.form.get("name", "")
    return _stage_change(project_id, "rename_project_stage", stage_ops.rename_stage("project", project_id, stage_id, name), f"stage_id={stage_id} -> {name}")


@app.route("/projects/<int:project_id>/stages/<int:stage_id>/move", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_move(project_id, stage_id):
    _live_project(project_id)
    direction = request.form.get("direction", "")
    return _stage_change(project_id, "move_project_stage", stage_ops.move_stage("project", project_id, stage_id, direction), f"stage_id={stage_id} {direction}")


@app.route("/projects/<int:project_id>/stages/<int:stage_id>/delete", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_delete(project_id, stage_id):
    _live_project(project_id)
    return _stage_change(project_id, "delete_project_stage", stage_ops.delete_stage("project", project_id, stage_id), f"stage_id={stage_id}")


@app.route("/projects/<int:project_id>/stages/sla", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def project_stage_sla(project_id):
    _live_project(project_id)
    return _stage_change(project_id, "update_project_stage_slas", stage_ops.set_slas("project", project_id, request.form), None)


@app.route("/undo/project/<int:project_id>", methods=["POST"])
@permission_required("delete_project")
@project_role_required("manage_project")
def undo_project(project_id):
    stamp = load_project(project_id, include_deleted=True)["deleted_at"]   # the row is deleted by definition
    if not restore_deleted("projects", project_id):
        flash("Too late to undo — the undo window has passed")
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
        flash("Too late to undo — the undo window has passed")
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
@login_required
def note_edit(project_id, note_id):
    note = _own_note(project_id, note_id)
    text = request.form.get("note", "").strip()[:5000]
    if not text:
        flash("A note needs some text — delete it instead")
        return redirect(url_for("project_detail", project_id=project_id))
    db = get_db()
    db.execute("UPDATE status_notes SET note = ?, edited_at = ? WHERE id = ?", (text, datetime.utcnow().isoformat(), note_id))
    db.commit()
    audit_log("edit_project_note", "project", project_id, None, f"note {note_id}: {note['note'][:80]} -> {text[:80]}")
    flash("Note updated")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def note_delete(project_id, note_id):
    note = _own_note(project_id, note_id)
    if note_id in stage_entry_note_ids(project_id):
        flash("This note records a stage change, so it stays in the history — edit its text instead")
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
        for h in handles:
            i = low.find("@" + h)
            end = i + 1 + len(h)
            if i >= 0 and (end == len(low) or not low[end].isalnum()):
                found.append(r["id"])
                break
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
        f"\"{escape(title)}\" on project {escape(project['name'] if project else '')}.",
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
    raw = as_id(raw)
    if not raw:
        return None
    ok = db.execute("SELECT 1 FROM users u WHERE u.id = ? AND u.active = 1 AND (u.kind = 'internal' OR EXISTS "
                    "(SELECT 1 FROM project_participants pp WHERE pp.project_id = ? AND pp.user_id = u.id))", (raw, project_id)).fetchone()
    return raw if ok else None


def _due_problem(form):
    """A due date the reports can do arithmetic on (test report FN-3); the
    route stores parse_date(form["due_date"]) once this passes."""
    try:
        parse_date(form.get("due_date"))
    except ValueError as exc:
        return f"Due date must be {exc}"
    return None


@app.route("/projects/<int:project_id>/tasks", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def task_add(project_id):
    db = get_db()
    if not load_project(project_id):
        abort(404)
    form = _task_input()
    title = (form.get("title") or "").strip()[:200]
    if not title:
        return _task_reply(project_id, "Task needs a title")
    assignee_id = _assignee(db, project_id, form.get("assignee_id"))
    if problem := _due_problem(form):
        return _task_reply(project_id, problem)
    cur = db.execute(
        "INSERT INTO tasks (project_id, title, assignee_id, due_date, created_at, created_by, stage) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_id, title, assignee_id, parse_date(form.get("due_date")),
         datetime.utcnow().isoformat(), session["user_name"], _task_stage(project_id, form.get("stage"))),
    )
    touch_project(db, project_id)
    db.commit()
    _notify_assignee(assignee_id, project_id, title)
    audit_log("add_task", "project", project_id, None, title[:80])
    return _task_reply(project_id, id=cur.lastrowid)


@app.route("/projects/<int:project_id>/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def task_toggle(project_id, task_id):
    """Anyone who can edit the project, or the person the task is tagged to —
    a contractor ticks off their own work without gaining anything else."""
    project = load_project(project_id)   # visibility decided in one place
    db = get_db()
    task = db.execute("SELECT title, done, assignee_id FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)).fetchone()
    if task is None:
        abort(404)
    if not (project_allows(project_id, "manage_tasks") or task["assignee_id"] == session["user_id"]):
        abort(403)
    new_done = 0 if task["done"] else 1
    db.execute(
        "UPDATE tasks SET done = ?, done_at = ? WHERE id = ?",
        (new_done, datetime.utcnow().isoformat() if new_done else None, task_id),
    )
    touch_project(db, project_id)
    db.commit()
    audit_log("toggle_task", "project", project_id, None, f"{'done' if new_done else 'reopened'}: {task['title'][:80]}")
    if new_done:
        _tell_pm(project, f"Task done on {escape(project['name'])}",
                 f"{escape(session['user_name'])} completed <b>{escape(task['title'])}</b>.")
    return _task_reply(project_id, done=bool(new_done))


@app.route("/projects/<int:project_id>/tasks/<int:task_id>/delete", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def task_delete(project_id, task_id):
    load_project(project_id)   # visibility decided in one place
    db = get_db()
    task = db.execute("SELECT title FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)).fetchone()
    db.execute("DELETE FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id))
    touch_project(db, project_id)
    db.commit()
    audit_log("delete_task", "project", project_id, None, task["title"][:80] if task else f"task {task_id} (already gone)")
    return _task_reply(project_id)


@app.route("/projects/<int:project_id>/tasks/<int:task_id>/edit", methods=["POST"])
@login_required
def task_edit(project_id, task_id):
    """Correct a task in place. Fixing a typo previously meant deleting the
    task and retyping it, which also threw away its done state. Only the
    fields sent change (title, assignee_id, due_date, stage): a JSON edit of
    the title keeps the assignee and the due date (L14). Whoever may manage
    tasks changes any field; the person the task is on, only its due date."""
    load_project(project_id)   # visibility decided in one place
    db = get_db()
    task = db.execute("SELECT id, title, assignee_id, due_date, stage FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)).fetchone()
    if task is None:
        abort(404)
    form = _task_input()
    if not project_allows(project_id, "manage_tasks"):
        if task["assignee_id"] != session["user_id"]:
            abort(403)
        # the assignee's own task: the page sends the whole task, so only a changed field other than the date is refused
        same = {"title": (task["title"], lambda v: (v or "").strip()[:200]), "assignee_id": (task["assignee_id"], lambda v: int(v) if str(v or "").isdigit() else None),
                "stage": (task["stage"], lambda v: v or None)}
        if any(k in form and norm(form.get(k)) != old for k, (old, norm) in same.items()):
            abort(403)
    title = (form.get("title") or "").strip()[:200] if "title" in form else task["title"]
    if not title:
        return _task_reply(project_id, "Task needs a title")
    assignee_id = _assignee(db, project_id, form.get("assignee_id")) if "assignee_id" in form else task["assignee_id"]
    if problem := _due_problem(form):
        return _task_reply(project_id, problem)
    due = parse_date(form.get("due_date")) if "due_date" in form else task["due_date"]
    stage = _task_stage(project_id, form.get("stage")) if "stage" in form else task["stage"]
    db.execute(
        "UPDATE tasks SET title = ?, assignee_id = ?, due_date = ?, stage = ? WHERE id = ?",
        (title, assignee_id, due, stage, task_id),
    )
    touch_project(db, project_id)
    db.commit()
    # only ping on a genuine reassignment, not on every title tweak
    if assignee_id and str(assignee_id) != str(task["assignee_id"]):
        _notify_assignee(assignee_id, project_id, title)
    audit_log("edit_task", "project", project_id, None, title[:80] + (f" (was {task['title'][:60]})" if title != task["title"] else ""))
    return _task_reply(project_id)


@app.route("/projects/<int:project_id>/tasks/bulk", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def task_bulk(project_id):
    """Complete or delete several tasks at once.

    Ids are filtered against this project rather than trusted from the form, so
    a doctored checkbox can't reach a task belonging to somebody else's project.
    """
    load_project(project_id)   # visibility decided in one place
    action = request.form.get("action")
    if action not in ("complete", "reopen", "delete"):
        abort(400)
    raw_ids = request.form.getlist("task_ids")
    try:
        wanted = {int(value) for value in raw_ids}
    except ValueError:
        abort(400)
    if not wanted:
        flash("No tasks selected")
        return redirect(url_for("project_detail", project_id=project_id) + "#tasks")

    db = get_db()
    owned = {
        row["id"] for row in
        db.execute("SELECT id FROM tasks WHERE project_id = ?", (project_id,)).fetchall()
    }
    ids = sorted(wanted & owned)
    if not ids:
        abort(404)

    placeholders = ",".join("?" for _ in ids)
    if action == "delete":
        changed = db.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", ids).rowcount
        message = f"Deleted {changed} task(s)"
    else:
        done = 1 if action == "complete" else 0
        # only the tasks whose state changes: a task done last week keeps the day it was done (L13)
        changed = db.execute(
            f"UPDATE tasks SET done = ?, done_at = ? WHERE id IN ({placeholders}) AND done != ?",
            [done, datetime.utcnow().isoformat() if done else None, *ids, done],
        ).rowcount
        message = f"{'Completed' if done else 'Reopened'} {changed} task(s)"
    if changed:
        touch_project(db, project_id)
    db.commit()
    flash(message)
    audit_log("bulk_tasks", "project", project_id, None, f"{action}: {changed} task(s)")
    if action == "complete" and changed:
        project = load_project(project_id)
        _tell_pm(project, f"{changed} task{'s' if changed != 1 else ''} done on {escape(project['name'])}",
                 f"{escape(session['user_name'])} completed {changed} task{'s' if changed != 1 else ''} at once.")
    return redirect(url_for("project_detail", project_id=project_id) + "#tasks")


@app.route("/projects/<int:project_id>/tasks/clear-completed", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def task_clear_completed(project_id):
    """Drop every finished task at once, so the checklist stays about what's
    still outstanding."""
    load_project(project_id)   # visibility decided in one place
    db = get_db()
    cursor = db.execute("DELETE FROM tasks WHERE project_id = ? AND done = 1", (project_id,))
    db.commit()
    flash(f"Cleared {cursor.rowcount} completed task(s)")
    audit_log("clear_completed_tasks", "project", project_id)
    return redirect(url_for("project_detail", project_id=project_id) + "#tasks")
