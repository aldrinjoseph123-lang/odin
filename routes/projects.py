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
    CLIENT_PO_DOC_CATEGORY,
    DEFAULT_ALERT_TYPE_SETTINGS,
    DELIVERY_MODES,
)
from core import app, permission_required, undo_button, write_required
from security import ALLOWED_UPLOAD_EXTENSIONS, allowed_upload, content_matches_extension
from db import (
    UPLOAD_DIR,
    get_contact_lists,
    get_db,
    get_doc_category_names,
    get_setting,
    get_stage_names,
    get_terminal_stage,
    restore_deleted,
    soft_delete,
)
from services.alerts import get_alert_type_settings, schedule_status
from services.analytics import sla_by_stage, stage_sla_state
from services.audit import audit_log
from services.notifications import notify_event

PROJECTS_PER_PAGE = 25

# Sortable columns, mapped to their SQL expression. SQLite cannot parameterise
# an ORDER BY, so this allowlist is what keeps the column name from ever being
# user-controlled text spliced into the query.
SORT_COLUMNS = {
    "name": "p.name",
    "client": "p.client",
    "po_number": "p.po_number",
    "stage": "p.stage",
    "owner": "u.name",
    "mode": "p.delivery_mode",
    "vendor": "p.vendor_name",
    "product": "p.product_name",
    "updated": "p.updated_at",
}
DEFAULT_SORT = "updated"


@app.route("/projects")
@permission_required("view_projects")
def projects_list():
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
    params = []
    if view == "stale":
        stale_threshold = get_alert_type_settings().get("stale", DEFAULT_ALERT_TYPE_SETTINGS["stale"])["threshold_days"]
        stale_cutoff = (datetime.utcnow() - timedelta(days=stale_threshold)).isoformat()
        query += " AND p.updated_at < ?"
        params.append(stale_cutoff)
        if not show_closed:
            query += " AND p.stage != ?"
            params.append(get_terminal_stage())
    elif view == "overdue":
        # past target end date, not yet in the terminal stage
        today = datetime.utcnow().date().isoformat()
        query += " AND p.target_end_date IS NOT NULL AND p.target_end_date < ? AND p.stage != ?"
        params.extend([today, get_terminal_stage()])
    elif view == "at_risk":
        # target end date within the due-soon window (and not already overdue/terminal)
        soon_days = get_alert_type_settings().get("project_due_soon", DEFAULT_ALERT_TYPE_SETTINGS["project_due_soon"])["threshold_days"]
        today = datetime.utcnow().date()
        soon = (today + timedelta(days=soon_days)).isoformat()
        query += " AND p.target_end_date IS NOT NULL AND p.target_end_date >= ? AND p.target_end_date <= ? AND p.stage != ?"
        params.extend([today.isoformat(), soon, get_terminal_stage()])
    elif stage_filter:
        query += " AND p.stage = ?"
        params.append(stage_filter)
    elif delivery_mode_filter:
        query += " AND p.delivery_mode = ?"
        params.append(delivery_mode_filter)
        if not show_closed:
            query += " AND p.stage != ?"
            params.append(get_terminal_stage())
    elif not show_closed:
        query += " AND p.stage != ?"
        params.append(get_terminal_stage())
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
    writer = csv.writer(output)
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
    db = get_db()
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        "WHERE p.stage != ? AND p.deleted_at IS NULL ORDER BY p.client, p.name",
        (get_terminal_stage(),),
    ).fetchall()
    return render_template(
        "report_all.html",
        projects=projects,
        generated_at=datetime.utcnow(),
    )


@app.route("/projects/<int:project_id>/report")
@permission_required("view_reports")
def report_single(project_id):
    db = get_db()
    project = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.id = ? AND p.deleted_at IS NULL",
        (project_id,),
    ).fetchone()
    if project is None:
        flash("Project not found")
        return redirect(url_for("board"))
    notes = db.execute(
        "SELECT * FROM status_notes WHERE project_id = ? ORDER BY created_at DESC", (project_id,)
    ).fetchall()
    documents = db.execute(
        "SELECT * FROM documents WHERE project_id = ? AND deleted_at IS NULL ORDER BY category", (project_id,)
    ).fetchall()
    return render_template(
        "report_single.html", project=project, notes=notes, documents=documents,
        generated_at=datetime.utcnow(),
    )


@app.route("/projects/new", methods=["GET", "POST"])
@permission_required("create_project")
def project_new():
    db = get_db()
    if request.method == "POST":
        po_document = request.files.get("po_document")
        if not po_document or not po_document.filename:
            flash(f"Upload a '{CLIENT_PO_DOC_CATEGORY}' document to create the project")
            return redirect(url_for("project_new"))
        if not allowed_upload(po_document.filename):
            flash(f"That file type isn't allowed. Accepted: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}")
            return redirect(url_for("project_new"))
        if not content_matches_extension(po_document):
            flash("That file's contents don't match its extension")
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
             access_token, customer_token, created_at, updated_at, stage_entered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                request.form["client"].strip()[:200],
                request.form.get("po_number") or None,
                request.form.get("po_date") or None,
                get_stage_names()[0],
                session["user_id"],
                request.form.get("via") or None,
                request.form.get("account_manager_name") or None,
                request.form.get("account_manager_email") or None,
                request.form.get("partner_name") or None,
                request.form.get("partner_account_manager_name") or None,
                request.form.get("partner_account_manager_email") or None,
                request.form.get("start_date") or None,
                request.form.get("target_end_date") or None,
                request.form.get("delivery_mode", DELIVERY_MODES[0]),
                request.form.get("outsourcer_name") or None,
                request.form.get("outsourcer_email") or None,
                request.form.get("vendor_name") or None,
                request.form.get("product_name") or None,
                secrets.token_urlsafe(16),   # vendor link
                secrets.token_urlsafe(16),   # customer link
                now,
                now,
                now,
            ),
        )
        project_id = cursor.lastrowid
        save_document(project_id, po_document, CLIENT_PO_DOC_CATEGORY, session["user_name"])
        db.commit()
        audit_log("create_project", "project", project_id, name, f"client={request.form['client']}")
        notify_event(
            {"owner_id": session["user_id"]},
            f"New project: {escape(name)}",
            f"Project '{escape(name)}' for {escape(request.form['client'])} was created and assigned to you.",
        )
        flash("Project created")
        return redirect(url_for("board"))
    users = db.execute("SELECT * FROM users ORDER BY name").fetchall()
    source = None
    duplicate_of = request.args.get("from", type=int)
    if duplicate_of:
        source = db.execute(
            "SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (duplicate_of,)
        ).fetchone()
    return render_template(
        "project_form.html", users=users, project=source, duplicating=bool(source),
        **get_contact_lists()
    )


@app.route("/projects/<int:project_id>")
@permission_required("view_project_detail")
def project_detail(project_id):
    db = get_db()
    project = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.id = ? AND p.deleted_at IS NULL",
        (project_id,),
    ).fetchone()
    if project is None:
        flash("Project not found")
        return redirect(url_for("board"))
    notes = db.execute(
        "SELECT * FROM status_notes WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    ).fetchall()
    documents = db.execute(
        "SELECT * FROM documents WHERE project_id = ? AND deleted_at IS NULL ORDER BY uploaded_at DESC",
        (project_id,),
    ).fetchall()
    if not project["access_token"]:
        token = secrets.token_urlsafe(16)
        db.execute("UPDATE projects SET access_token = ? WHERE id = ?", (token, project_id))
        db.commit()
        project = db.execute(
            "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.id = ? AND p.deleted_at IS NULL",
            (project_id,),
        ).fetchone()
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
        schedule=schedule_status(project),
        sla=stage_sla_state(
            project,
            sla_by_stage(db.execute("SELECT name, sla_days FROM stages").fetchall()),
            get_terminal_stage(),
        ),
        today=datetime.utcnow().date().isoformat(),
        has_client_po_doc=has_required_document(project_id, CLIENT_PO_DOC_CATEGORY),
        **get_contact_lists(),
    )


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@permission_required("edit_project")
def project_edit(project_id):
    db = get_db()
    project = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.id = ? AND p.deleted_at IS NULL",
        (project_id,),
    ).fetchone()
    if project is None:
        flash("Project not found")
        return redirect(url_for("board"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()[:200]
        client = request.form.get("client", "").strip()[:200]
        if not name or not client:
            flash("Project name and client are required")
            return redirect(url_for("project_edit", project_id=project_id))

        # Owner reassignment — fall back to the current owner if the submitted
        # id is missing or not a real user (never leave a project ownerless).
        try:
            owner_id = int(request.form.get("owner_id", project["owner_id"]))
        except (TypeError, ValueError):
            owner_id = project["owner_id"]
        if not db.execute("SELECT 1 FROM users WHERE id = ?", (owner_id,)).fetchone():
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
                outsourcer_name=?, outsourcer_email=?, vendor_name=?, product_name=?, updated_at=?
               WHERE id=?""",
            (
                name, client, owner_id,
                request.form.get("po_number") or None,
                request.form.get("po_date") or None,
                request.form.get("via") or None,
                request.form.get("account_manager_name") or None,
                request.form.get("account_manager_email") or None,
                request.form.get("partner_name") or None,
                request.form.get("partner_account_manager_name") or None,
                request.form.get("partner_account_manager_email") or None,
                request.form.get("start_date") or None,
                request.form.get("target_end_date") or None,
                delivery_mode,
                request.form.get("outsourcer_name") or None,
                request.form.get("outsourcer_email") or None,
                request.form.get("vendor_name") or None,
                request.form.get("product_name") or None,
                now, project_id,
            ),
        )
        db.commit()
        audit_log("update_project", "project", project_id, name, f"client={client}; owner_id={owner_id}")
        flash("Project updated")
        return redirect(url_for("project_detail", project_id=project_id))

    users = db.execute("SELECT * FROM users ORDER BY name").fetchall()
    return render_template("project_form.html", project=project, users=users, **get_contact_lists())


@app.route("/projects/<int:project_id>/stage", methods=["POST"])
@permission_required("edit_project_stage")
def project_stage(project_id):
    error = change_stage(project_id, request.form["stage"], request.form.get("note", "").strip()[:5000])
    if error:
        flash(error)
        return redirect(url_for("project_detail", project_id=project_id))
    if request.form.get("redirect") == "board":
        return redirect(url_for("board"))
    return redirect(url_for("project_detail", project_id=project_id))


def change_stage(project_id, new_stage, note_text):
    """The one stage-change path (form + JSON). Returns an error message or
    None; 404s when the project is gone. Caller must hold edit_project_stage."""
    if new_stage not in get_stage_names():
        return "Invalid stage"
    db = get_db()
    # Check before writing. Without this a stale tab could move the stage of a
    # project someone else just deleted: the UPDATE has no deleted_at filter, so
    # it mutated the deleted row and wrote an orphan note before crashing on the
    # follow-up lookup, which does filter deleted_at.
    project = db.execute(
        "SELECT owner_id, name FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)
    ).fetchone()
    if project is None:
        abort(404)
    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE projects SET stage = ?, updated_at = ?, stage_entered_at = ? WHERE id = ?",
        (new_stage, now, now, project_id),
    )
    db.execute(
        "INSERT INTO status_notes (project_id, author, note, stage, created_at, guest_visible) VALUES (?, ?, ?, ?, ?, 1)",
        (
            project_id,
            session["user_name"],
            note_text or f"Stage changed to {new_stage}",
            new_stage,
            now,
        ),
    )
    db.commit()
    audit_log("update_project_stage", "project", project_id, project["name"], f"stage={new_stage}")
    notify_event(
        project,
        f"Stage changed: {escape(project['name'])}",
        f"Stage moved to <b>{escape(new_stage)}</b> by {escape(session['user_name'])}."
        + (f"<br>{escape(note_text)}" if note_text else ""),
    )
    return None


def has_required_document(project_id, category):
    db = get_db()
    return (
        db.execute(
            "SELECT 1 FROM documents WHERE project_id = ? AND category = ? AND deleted_at IS NULL LIMIT 1", (project_id, category)
        ).fetchone()
        is not None
    )


def save_document(project_id, file, category, uploaded_by):
    """Save an uploaded file to disk + documents table (+ OneDrive mirror if
    enabled). Assumes the caller already validated file/category — shared by
    the Documents panel upload and project creation's bundled PO upload."""
    original_name = secure_filename(file.filename)
    stored_name = f"{uuid.uuid4().hex}_{original_name}"
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
    db.commit()

    if get_setting("onedrive_mirror_uploads_enabled") == "1":
        project = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
        remote_path = f"Odin-Documents/{project_id}-{secure_filename(project['name'])}/{category}/{original_name}"
        ok, error = graph.upload_file(os.path.join(project_dir, stored_name), remote_path)
        if not ok:
            print(f"[save_document] OneDrive mirror failed: {error}")
    return original_name


@app.route("/projects/<int:project_id>/documents", methods=["POST"])
@permission_required("upload_document")
def document_upload(project_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone():
        abort(404)
    file = request.files.get("file")
    category = request.form.get("category", "")
    if not file or not file.filename:
        flash("No file selected")
        return redirect(url_for("project_detail", project_id=project_id))
    if not allowed_upload(file.filename):
        flash(f"That file type isn't allowed. Accepted: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}")
        return redirect(url_for("project_detail", project_id=project_id))
    if not content_matches_extension(file):
        flash("That file's contents don't match its extension")
        return redirect(url_for("project_detail", project_id=project_id))
    if category not in get_doc_category_names():
        flash("Invalid category")
        return redirect(url_for("project_detail", project_id=project_id))
    original_name = save_document(project_id, file, category, session["user_name"])
    audit_log("upload_document", "project", project_id, None, f"{category}: {original_name}")

    flash(f"Uploaded {original_name}")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/documents/<int:doc_id>/download")
@permission_required("download_document")
def document_download(project_id, doc_id):
    db = get_db()
    doc = db.execute(
        "SELECT * FROM documents WHERE id = ? AND project_id = ? AND deleted_at IS NULL", (doc_id, project_id)
    ).fetchone()
    if doc is None:
        abort(404)
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
def document_delete(project_id, doc_id):
    db = get_db()
    doc = db.execute(
        "SELECT * FROM documents WHERE id = ? AND project_id = ? AND deleted_at IS NULL", (doc_id, project_id)
    ).fetchone()
    if doc is not None:
        soft_delete("documents", doc_id)
        audit_log("delete_document", "document", doc_id, doc["filename"], f"project_id={project_id}")
        flash(Markup(f"Deleted {escape(doc['filename'])}. {undo_button('Undo', 'undo_document', doc_id=doc_id)} (5 min window)"))
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
@permission_required("delete_project")
def project_delete(project_id):
    db = get_db()
    # deleted_at filter matters: re-deleting would re-stamp deleted_at, restarting
    # the undo window and writing a second audit entry for one user action.
    project = db.execute(
        "SELECT name FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)
    ).fetchone()
    if not project:
        abort(404)
    soft_delete("projects", project_id)
    soft_delete_query = "UPDATE documents SET deleted_at = ? WHERE project_id = ? AND deleted_at IS NULL"
    db.execute(soft_delete_query, (datetime.utcnow().isoformat(), project_id))
    db.commit()
    audit_log("delete_project", "project", project_id, project["name"])
    flash(Markup(f"Project deleted. {undo_button('Undo', 'undo_project', project_id=project_id)} (5 min window)"))
    return redirect(url_for("board"))


@app.route("/projects/<int:project_id>/rotate-token", methods=["POST"])
@write_required
def project_rotate_token(project_id):
    """Mint a fresh guest access token — instantly revokes any leaked old link."""
    db = get_db()
    project = db.execute("SELECT name FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
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


@app.route("/undo/project/<int:project_id>", methods=["POST"])
@write_required
def undo_project(project_id):
    restore_deleted("projects", project_id)
    db = get_db()
    db.execute("UPDATE documents SET deleted_at = NULL WHERE project_id = ?", (project_id,))
    db.commit()
    project = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    audit_log("restore_project", "project", project_id, project["name"])
    flash(f"Project '{project['name']}' restored")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/undo/document/<int:doc_id>", methods=["POST"])
@write_required
def undo_document(doc_id):
    restore_deleted("documents", doc_id)
    db = get_db()
    doc = db.execute("SELECT project_id, filename FROM documents WHERE id = ? AND deleted_at IS NULL", (doc_id,)).fetchone()
    audit_log("restore_document", "document", doc_id, doc["filename"], f"project_id={doc['project_id']}")
    flash(f"Document '{doc['filename']}' restored")
    return redirect(url_for("project_detail", project_id=doc["project_id"]))


@app.route("/projects/<int:project_id>/note", methods=["POST"])
@permission_required("add_project_note")
def project_note(project_id):
    note_text = request.form["note"].strip()[:5000]
    if not note_text:
        return redirect(url_for("project_detail", project_id=project_id))
    db = get_db()
    project = db.execute("SELECT name, stage FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    if project is None:
        abort(404)
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO status_notes (project_id, author, note, stage, created_at) VALUES (?, ?, ?, ?, ?)",
        (project_id, session["user_name"], note_text, project["stage"], now),
    )
    db.commit()
    audit_log("add_project_note", "project", project_id, project["name"], note_text)
    return redirect(url_for("project_detail", project_id=project_id))


def _notify_assignee(assignee_id, project_id, title):
    """Tell someone a task landed on them. Skipped when you assign to yourself —
    you already know. notify_event keys off owner_id, so the assignee is passed
    in that slot deliberately."""
    if not assignee_id or int(assignee_id) == session.get("user_id"):
        return
    project = get_db().execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    notify_event(
        {"owner_id": int(assignee_id)},
        f"Task assigned to you: {escape(title)}",
        f"{escape(session.get('user_name', 'Someone'))} assigned you "
        f"\"{escape(title)}\" on project {escape(project['name'] if project else '')}.",
    )


@app.route("/projects/<int:project_id>/tasks", methods=["POST"])
@permission_required("edit_project")
def task_add(project_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone():
        abort(404)
    title = request.form.get("title", "").strip()[:200]
    if not title:
        flash("Task needs a title")
        return redirect(url_for("project_detail", project_id=project_id) + "#tasks")
    assignee_id = request.form.get("assignee_id") or None
    # must be a real, still-active user: the dropdown only offers active ones,
    # but a hand-crafted POST could name a deactivated account.
    if assignee_id and not db.execute("SELECT 1 FROM users WHERE id = ? AND active = 1", (assignee_id,)).fetchone():
        assignee_id = None
    db.execute(
        "INSERT INTO tasks (project_id, title, assignee_id, due_date, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, title, assignee_id, request.form.get("due_date") or None,
         datetime.utcnow().isoformat(), session["user_name"]),
    )
    db.commit()
    _notify_assignee(assignee_id, project_id, title)
    audit_log("add_task", "project", project_id, None, request.form.get("title", "")[:80])
    return redirect(url_for("project_detail", project_id=project_id) + "#tasks")


@app.route("/projects/<int:project_id>/tasks/<int:task_id>/toggle", methods=["POST"])
@permission_required("edit_project")
def task_toggle(project_id, task_id):
    db = get_db()
    task = db.execute("SELECT done FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)).fetchone()
    if task is None:
        abort(404)
    new_done = 0 if task["done"] else 1
    db.execute(
        "UPDATE tasks SET done = ?, done_at = ? WHERE id = ?",
        (new_done, datetime.utcnow().isoformat() if new_done else None, task_id),
    )
    db.commit()
    audit_log("toggle_task", "project", project_id, None, f"task_id={task_id}")
    return redirect(url_for("project_detail", project_id=project_id) + "#tasks")


@app.route("/projects/<int:project_id>/tasks/<int:task_id>/delete", methods=["POST"])
@permission_required("edit_project")
def task_delete(project_id, task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id))
    db.commit()
    audit_log("delete_task", "project", project_id, None, f"task_id={task_id}")
    return redirect(url_for("project_detail", project_id=project_id) + "#tasks")


@app.route("/projects/<int:project_id>/tasks/<int:task_id>/edit", methods=["POST"])
@permission_required("edit_project")
def task_edit(project_id, task_id):
    """Correct a task in place. Fixing a typo previously meant deleting the
    task and retyping it, which also threw away its done state."""
    db = get_db()
    task = db.execute("SELECT id, assignee_id FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)).fetchone()
    if task is None:
        abort(404)
    title = request.form.get("title", "").strip()[:200]
    if not title:
        flash("Task needs a title")
        return redirect(url_for("project_detail", project_id=project_id) + "#tasks")
    assignee_id = request.form.get("assignee_id") or None
    # must be a real, still-active user: the dropdown only offers active ones,
    # but a hand-crafted POST could name a deactivated account.
    if assignee_id and not db.execute("SELECT 1 FROM users WHERE id = ? AND active = 1", (assignee_id,)).fetchone():
        assignee_id = None
    db.execute(
        "UPDATE tasks SET title = ?, assignee_id = ?, due_date = ? WHERE id = ?",
        (title, assignee_id, request.form.get("due_date") or None, task_id),
    )
    db.commit()
    # only ping on a genuine reassignment, not on every title tweak
    if assignee_id and str(assignee_id) != str(task["assignee_id"]):
        _notify_assignee(assignee_id, project_id, title)
    audit_log("edit_task", "project", project_id, None, f"task_id={task_id}")
    return redirect(url_for("project_detail", project_id=project_id) + "#tasks")


@app.route("/projects/<int:project_id>/tasks/bulk", methods=["POST"])
@permission_required("edit_project")
def task_bulk(project_id):
    """Complete or delete several tasks at once.

    Ids are filtered against this project rather than trusted from the form, so
    a doctored checkbox can't reach a task belonging to somebody else's project.
    """
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
        db.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", ids)
        message = f"Deleted {len(ids)} task(s)"
    else:
        done = 1 if action == "complete" else 0
        db.execute(
            f"UPDATE tasks SET done = ?, done_at = ? WHERE id IN ({placeholders})",
            [done, datetime.utcnow().isoformat() if done else None, *ids],
        )
        message = f"{'Completed' if done else 'Reopened'} {len(ids)} task(s)"
    db.commit()
    flash(message)
    audit_log("bulk_tasks", "project", project_id, None, request.form.get("action", ""))
    return redirect(url_for("project_detail", project_id=project_id) + "#tasks")


@app.route("/projects/<int:project_id>/tasks/clear-completed", methods=["POST"])
@permission_required("edit_project")
def task_clear_completed(project_id):
    """Drop every finished task at once, so the checklist stays about what's
    still outstanding."""
    db = get_db()
    cursor = db.execute("DELETE FROM tasks WHERE project_id = ? AND done = 1", (project_id,))
    db.commit()
    flash(f"Cleared {cursor.rowcount} completed task(s)")
    audit_log("clear_completed_tasks", "project", project_id)
    return redirect(url_for("project_detail", project_id=project_id) + "#tasks")
