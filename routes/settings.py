"""Settings + administration routes: audit log viewer, the settings page,
RBAC matrix, lifecycle stages, document categories, contacts/partners
management, per-type alert config, and the contact/partner undo restores.
Registration side effects only.
"""
import csv
import io
import sqlite3
from datetime import datetime

from flask import Response, abort, flash, redirect, render_template, request, url_for
from markupsafe import Markup

import graph
from constants import ALERT_TYPE_TITLES, CONTACT_LISTS, PERMISSIONS, ROLES
from core import admin_required, app, permission_required, undo_button, write_required
from db import get_db, get_setting, restore_deleted, soft_delete
from services.alerts import get_alert_type_settings
from services.audit import audit_log


@app.route("/undo/contact/<list_key>/<int:item_id>", methods=["POST"])
@write_required
def undo_contact(list_key, item_id):
    if list_key not in CONTACT_LISTS:
        abort(404)
    meta = CONTACT_LISTS[list_key]
    restore_deleted(meta['table'], item_id)
    flash(f"{meta['label']} entry restored")
    audit_log("restore_contact", list_key, item_id)
    return redirect(url_for("settings_contacts"))


@app.route("/undo/partner/<int:partner_id>", methods=["POST"])
@write_required
def undo_partner(partner_id):
    db = get_db()
    restore_deleted("partners", partner_id)
    db.execute("UPDATE partner_account_managers SET deleted_at = NULL WHERE partner_id = ?", (partner_id,))
    db.commit()
    audit_log("restore_partner", "partner", partner_id)
    flash("Partner and its account managers restored")
    return redirect(url_for("settings_contacts"))


@app.route("/undo/partner-manager/<int:manager_id>", methods=["POST"])
@write_required
def undo_partner_manager(manager_id):
    restore_deleted("partner_account_managers", manager_id)
    flash("Account manager restored")
    audit_log("restore_partner_manager", "partner_manager", manager_id)
    return redirect(url_for("settings_contacts"))


def _audit_filter():
    """Shared by the viewer and the CSV export so both answer the same query."""
    username = request.args.get("user", "").strip()
    action = request.args.get("action", "").strip()
    project_id = request.args.get("project_id", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()

    where = " WHERE 1=1"
    params = []
    if username:
        where += " AND username = ?"
        params.append(username)
    if action:
        where += " AND action = ?"
        params.append(action)
    if project_id:
        where += " AND resource_type = 'project' AND resource_id = ?"
        params.append(project_id)
    if date_from:
        where += " AND timestamp >= ?"
        params.append(date_from)
    if date_to:
        where += " AND timestamp <= ?"
        params.append(date_to + "T23:59:59")
    filters = {"user": username, "action": action, "project_id": project_id, "from": date_from, "to": date_to}
    return where, params, filters


@app.route("/audit-logs/export.csv")
@permission_required("manage_settings")
def audit_logs_export():
    where, params, _ = _audit_filter()
    rows = get_db().execute(f"SELECT * FROM audit_logs{where} ORDER BY timestamp DESC", params).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["timestamp", "username", "action", "resource_type", "resource_id", "resource_name", "details", "ip_address"])
    for r in rows:
        writer.writerow([r["timestamp"], r["username"], r["action"], r["resource_type"], r["resource_id"], r["resource_name"], r["details"], r["ip_address"]])
    audit_log("export_audit_log", details=f"{len(rows)} rows")
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=odin-audit-log.csv"})


@app.route("/audit-logs")
@permission_required("manage_settings")
def audit_logs_view():
    db = get_db()
    page = request.args.get("page", 1, type=int)
    where, params, filters = _audit_filter()
    limit = 100
    offset = (page - 1) * limit
    logs = db.execute(
        f"SELECT * FROM audit_logs{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    total = db.execute(f"SELECT COUNT(*) as count FROM audit_logs{where}", params).fetchone()["count"]
    total_pages = max(1, (total + limit - 1) // limit)

    usernames = [row["username"] for row in db.execute("SELECT DISTINCT username FROM audit_logs ORDER BY username")]
    actions = [row["action"] for row in db.execute("SELECT DISTINCT action FROM audit_logs ORDER BY action")]
    projects = db.execute("SELECT id, name FROM projects ORDER BY name").fetchall()

    return render_template(
        "audit_logs.html",
        logs=logs,
        page=page,
        total_pages=total_pages,
        total=total,
        usernames=usernames,
        actions=actions,
        projects=projects,
        filters=filters,
    )


@app.route("/settings")
@permission_required("manage_settings")
def settings():
    db = get_db()
    stages = db.execute("SELECT * FROM stages ORDER BY position").fetchall()
    doc_categories = db.execute("SELECT * FROM doc_categories ORDER BY name").fetchall()

    connection = graph.get_connection()
    teams_list, channels_list, teams_error = [], [], None
    selected_team_id = request.args.get("team_id", "")
    if connection and connection["refresh_token"]:
        teams_list, teams_error = graph.list_joined_teams()
        if selected_team_id:
            channels_list, teams_error = graph.list_channels(selected_team_id)

    return render_template(
        "settings.html",
        stages=stages,
        doc_categories=doc_categories,
        alert_type_settings=get_alert_type_settings(),
        alert_type_titles=ALERT_TYPE_TITLES,
        oauth_client_configured=graph.oauth_client_configured(),
        azure_app=graph.azure_app_credentials(),
        connection=connection,
        teams_list=teams_list,
        channels_list=channels_list,
        teams_error=teams_error,
        selected_team_id=selected_team_id,
        notify_email_enabled=get_setting("notify_email_enabled") == "1",
        notify_teams_enabled=get_setting("notify_teams_enabled") == "1",
        onedrive_mirror_uploads_enabled=get_setting("onedrive_mirror_uploads_enabled") == "1",
        onedrive_backup_enabled=get_setting("onedrive_backup_enabled") == "1",
    )


@app.route("/settings/rbac")
@permission_required("manage_settings")
def settings_rbac():
    db = get_db()
    rows = db.execute("SELECT * FROM role_permissions").fetchall()
    matrix = {perm: {role: False for role in ROLES} for perm in PERMISSIONS}
    for row in rows:
        if row["permission"] in matrix:
            matrix[row["permission"]][row["role"]] = bool(row["allowed"])
    return render_template("settings_rbac.html", matrix=matrix, permissions=list(PERMISSIONS), roles=ROLES)


@app.route("/settings/rbac", methods=["POST"])
@permission_required("manage_settings")
def settings_rbac_update():
    db = get_db()
    for permission in PERMISSIONS:
        for role in ROLES:
            # Admin always keeps manage_settings + manage_users — otherwise an
            # admin could lock every account (including their own) out of this
            # page with no UI path back in — and every view_* right, since an
            # admin who cannot see projects is just a confused admin.
            if role == "Admin" and (permission in ("manage_settings", "manage_users") or permission.startswith("view_")):
                allowed = 1
            else:
                allowed = 1 if request.form.get(f"{permission}::{role}") == "on" else 0
            db.execute(
                "UPDATE role_permissions SET allowed = ? WHERE permission = ? AND role = ?",
                (allowed, permission, role),
            )
    db.commit()
    audit_log("update_role_permissions", details="RBAC matrix updated")
    flash("Permissions updated")
    return redirect(url_for("settings_rbac"))


@app.route("/settings/stages/add", methods=["POST"])
@admin_required
def settings_stage_add():
    name = request.form.get("name", "").strip()
    db = get_db()
    if not name:
        flash("Stage name required")
    elif db.execute("SELECT 1 FROM stages WHERE name = ?", (name,)).fetchone():
        flash("Stage already exists")
    else:
        # Insert *before* the terminal stage, not after it. The last stage is
        # treated as "closed" everywhere, so appending would silently hand that
        # role to the new stage and reopen every closed project — putting them
        # back on the board and back into overdue/stale/SLA alerting.
        max_pos = db.execute("SELECT MAX(position) AS m FROM stages").fetchone()["m"]
        if max_pos is None:
            db.execute("INSERT INTO stages (name, position) VALUES (?, 0)", (name,))
            db.commit()
            audit_log("add_stage", "stage", None, name)
            flash(f"Stage '{name}' added")
        else:
            terminal = db.execute(
                "SELECT name FROM stages ORDER BY position DESC LIMIT 1"
            ).fetchone()["name"]
            db.execute("UPDATE stages SET position = position + 1 WHERE position = ?", (max_pos,))
            db.execute("INSERT INTO stages (name, position) VALUES (?, ?)", (name, max_pos))
            db.commit()
            audit_log("add_stage", "stage", None, name)
            flash(f"Stage '{name}' added before '{terminal}', which stays the closed stage")
    return redirect(url_for("settings"))


@app.route("/settings/stages/<int:stage_id>/rename", methods=["POST"])
@admin_required
def settings_stage_rename(stage_id):
    new_name = request.form.get("name", "").strip()
    db = get_db()
    stage = db.execute("SELECT * FROM stages WHERE id = ?", (stage_id,)).fetchone()
    if not stage:
        abort(404)
    if not new_name:
        flash("Stage name required")
    elif db.execute("SELECT 1 FROM stages WHERE name = ? AND id != ?", (new_name, stage_id)).fetchone():
        flash("Stage name already in use")
    else:
        old_name = stage["name"]
        db.execute("UPDATE stages SET name = ? WHERE id = ?", (new_name, stage_id))
        db.execute("UPDATE projects SET stage = ? WHERE stage = ?", (new_name, old_name))
        db.execute("UPDATE status_notes SET stage = ? WHERE stage = ?", (new_name, old_name))
        db.commit()
        audit_log("rename_stage", "stage", stage_id, new_name, f"was {old_name}")
        flash(f"Stage renamed to '{new_name}'")
    return redirect(url_for("settings"))


@app.route("/settings/stages/<int:stage_id>/move", methods=["POST"])
@admin_required
def settings_stage_move(stage_id):
    direction = request.form.get("direction")
    db = get_db()
    stages = db.execute("SELECT * FROM stages ORDER BY position").fetchall()
    index = next((i for i, s in enumerate(stages) if s["id"] == stage_id), None)
    if index is None:
        abort(404)
    swap_index = index - 1 if direction == "up" else index + 1
    if 0 <= swap_index < len(stages):
        a, b = stages[index], stages[swap_index]
        db.execute("UPDATE stages SET position = ? WHERE id = ?", (b["position"], a["id"]))
        db.execute("UPDATE stages SET position = ? WHERE id = ?", (a["position"], b["id"]))
        db.commit()
        audit_log("move_stage", "stage", stage_id, None, direction)
    return redirect(url_for("settings"))


@app.route("/settings/stages/<int:stage_id>/delete", methods=["POST"])
@admin_required
def settings_stage_delete(stage_id):
    db = get_db()
    stage = db.execute("SELECT * FROM stages WHERE id = ?", (stage_id,)).fetchone()
    if not stage:
        abort(404)
    stage_count = db.execute("SELECT COUNT(*) AS c FROM stages").fetchone()["c"]
    in_use = db.execute("SELECT COUNT(*) AS c FROM projects WHERE stage = ?", (stage["name"],)).fetchone()["c"]
    if stage_count <= 1:
        flash("Cannot delete the last remaining stage")
    elif in_use:
        flash(f"Cannot delete '{stage['name']}' — {in_use} project(s) currently use it")
    else:
        db.execute("DELETE FROM stages WHERE id = ?", (stage_id,))
        db.commit()
        audit_log("delete_stage", "stage", stage_id, stage["name"])
        flash(f"Stage '{stage['name']}' deleted")
    return redirect(url_for("settings"))


@app.route("/settings/stages/sla", methods=["POST"])
@admin_required
def settings_stage_sla():
    """Set the expected days-in-stage per stage. Blank clears the SLA, which
    means that stage simply isn't measured — not that its target is zero."""
    db = get_db()
    for stage in db.execute("SELECT id, name FROM stages").fetchall():
        raw = request.form.get(f"sla::{stage['id']}", "").strip()
        if not raw:
            db.execute("UPDATE stages SET sla_days = NULL WHERE id = ?", (stage["id"],))
            continue
        try:
            days = int(raw)
        except ValueError:
            flash(f"SLA for {stage['name']} must be a whole number of days")
            return redirect(url_for("settings"))
        if days < 1:
            flash(f"SLA for {stage['name']} must be at least 1 day")
            return redirect(url_for("settings"))
        db.execute("UPDATE stages SET sla_days = ? WHERE id = ?", (days, stage["id"]))
    db.commit()
    audit_log("update_stage_slas")
    flash("Stage SLAs updated")
    return redirect(url_for("settings"))


@app.route("/settings/stages/sla/from-measured", methods=["POST"])
@admin_required
def settings_stage_sla_from_measured():
    """Adopt each stage's measured average as its SLA.

    Only stages with completed visits get a target — a stage nothing has passed
    through yet has no evidence to set one from, so it's left alone rather than
    given a made-up number. Rounds up, so the target is never stricter than the
    average it came from.
    """
    import math
    from services.analytics import build_cycle_times

    db = get_db()
    projects = db.execute("SELECT * FROM projects WHERE deleted_at IS NULL").fetchall()
    notes_by_project = {}
    for note in db.execute("SELECT project_id, stage, created_at FROM status_notes ORDER BY created_at"):
        notes_by_project.setdefault(note["project_id"], []).append(note)
    stage_names = [row["name"] for row in db.execute("SELECT name FROM stages ORDER BY position")]
    if not stage_names:
        flash("No stages defined")
        return redirect(url_for("settings"))

    stats = build_cycle_times(projects, notes_by_project, stage_names, stage_names[-1])
    applied = 0
    for row in stats["stages"]:
        if row["avg_days"] is None or row["stage"] == stage_names[-1]:
            continue
        db.execute(
            "UPDATE stages SET sla_days = ? WHERE name = ?",
            (max(1, math.ceil(row["avg_days"])), row["stage"]),
        )
        applied += 1
    db.commit()
    audit_log("set_stage_slas_from_measured", details=f"{applied} stage(s)")
    flash(
        f"Set {applied} SLA(s) from measured averages"
        if applied else "No stage has completed visits yet — nothing to measure"
    )
    return redirect(url_for("settings"))


@app.route("/settings/doc-categories/add", methods=["POST"])
@admin_required
def settings_category_add():
    name = request.form.get("name", "").strip()
    db = get_db()
    if not name:
        flash("Category name required")
    elif db.execute("SELECT 1 FROM doc_categories WHERE name = ?", (name,)).fetchone():
        flash("Category already exists")
    else:
        db.execute("INSERT INTO doc_categories (name) VALUES (?)", (name,))
        db.commit()
        audit_log("add_doc_category", "doc_category", None, name)
        flash(f"Category '{name}' added")
    return redirect(url_for("settings"))


@app.route("/settings/doc-categories/<int:cat_id>/delete", methods=["POST"])
@admin_required
def settings_category_delete(cat_id):
    db = get_db()
    category = db.execute("SELECT * FROM doc_categories WHERE id = ?", (cat_id,)).fetchone()
    if not category:
        abort(404)
    in_use = db.execute(
        "SELECT COUNT(*) AS c FROM documents WHERE category = ?", (category["name"],)
    ).fetchone()["c"]
    if in_use:
        flash(f"Cannot delete '{category['name']}' — {in_use} document(s) use it")
    else:
        db.execute("DELETE FROM doc_categories WHERE id = ?", (cat_id,))
        db.commit()
        audit_log("delete_doc_category", "doc_category", cat_id, category["name"])
        flash(f"Category '{category['name']}' deleted")
    return redirect(url_for("settings"))


@app.route("/settings/contacts")
@permission_required("manage_contacts")
def settings_contacts():
    db = get_db()
    partners = db.execute("SELECT * FROM partners WHERE deleted_at IS NULL ORDER BY name").fetchall()
    partner_managers = db.execute("SELECT * FROM partner_account_managers WHERE deleted_at IS NULL ORDER BY name").fetchall()
    managers_by_partner = {}
    for row in partner_managers:
        managers_by_partner.setdefault(row["partner_id"], []).append(row)
    return render_template(
        "settings_contacts.html",
        contact_lists=CONTACT_LISTS,
        lists={
            key: db.execute(f"SELECT * FROM {meta['table']} WHERE deleted_at IS NULL ORDER BY name").fetchall()
            for key, meta in CONTACT_LISTS.items()
        },
        partners=partners,
        managers_by_partner=managers_by_partner,
    )


@app.route("/settings/contacts/<list_key>/add", methods=["POST"])
@permission_required("manage_contacts")
def settings_contacts_add(list_key):
    if list_key not in CONTACT_LISTS:
        abort(404)
    meta = CONTACT_LISTS[list_key]
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name required")
        return redirect(url_for("settings_contacts"))
    email = request.form.get("email", "").strip() if meta["has_email"] else None
    db = get_db()
    try:
        if meta["has_email"]:
            db.execute(f"INSERT INTO {meta['table']} (name, email) VALUES (?, ?)", (name, email or None))
        else:
            db.execute(f"INSERT INTO {meta['table']} (name) VALUES (?)", (name,))
        db.commit()
        audit_log("add_contact", list_key, None, name)
        flash(f"{meta['label']}: '{name}' added")
    except sqlite3.IntegrityError:
        flash(f"'{name}' already exists in {meta['label']}")
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/<list_key>/<int:item_id>/delete", methods=["POST"])
@permission_required("manage_contacts")
def settings_contacts_delete(list_key, item_id):
    if list_key not in CONTACT_LISTS:
        abort(404)
    meta = CONTACT_LISTS[list_key]
    soft_delete(meta['table'], item_id)
    flash(Markup(f"{meta['label']} entry deleted. {undo_button('Undo', 'undo_contact', list_key=list_key, item_id=item_id)} (5 min window)"))
    audit_log("delete_contact", list_key, item_id)
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/partners/add", methods=["POST"])
@permission_required("manage_contacts")
def settings_partner_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Partner name required")
        return redirect(url_for("settings_contacts"))
    db = get_db()
    try:
        db.execute("INSERT INTO partners (name) VALUES (?)", (name,))
        db.commit()
        audit_log("add_partner", "partner", None, name)
        flash(f"Partner '{name}' added")
    except sqlite3.IntegrityError:
        flash(f"Partner '{name}' already exists")
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/partners/<int:partner_id>/delete", methods=["POST"])
@permission_required("manage_contacts")
def settings_partner_delete(partner_id):
    db = get_db()
    soft_delete("partners", partner_id)
    now = datetime.utcnow().isoformat()
    db.execute("UPDATE partner_account_managers SET deleted_at = ? WHERE partner_id = ?", (now, partner_id))
    db.commit()
    audit_log("delete_partner", "partner", partner_id)
    flash(Markup(f"Partner deleted (its account managers were removed too). {undo_button('Undo', 'undo_partner', partner_id=partner_id)} (5 min window)"))
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/partners/<int:partner_id>/managers/add", methods=["POST"])
@permission_required("manage_contacts")
def settings_partner_manager_add(partner_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM partners WHERE id = ? AND deleted_at IS NULL", (partner_id,)).fetchone():
        abort(404)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Account manager name required")
        return redirect(url_for("settings_contacts"))
    email = request.form.get("email", "").strip() or None
    db.execute(
        "INSERT INTO partner_account_managers (partner_id, name, email) VALUES (?, ?, ?)",
        (partner_id, name, email),
    )
    db.commit()
    audit_log("add_partner_manager", "partner", partner_id, name)
    flash(f"Account manager '{name}' added")
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/partner-managers/<int:manager_id>/delete", methods=["POST"])
@permission_required("manage_contacts")
def settings_partner_manager_delete(manager_id):
    soft_delete("partner_account_managers", manager_id)
    flash(Markup(f"Account manager deleted. {undo_button('Undo', 'undo_partner_manager', manager_id=manager_id)} (5 min window)"))
    audit_log("delete_partner_manager", "partner_manager", manager_id)
    return redirect(url_for("settings_contacts"))


@app.route("/settings/alerts", methods=["POST"])
@admin_required
def settings_alerts():
    # threshold_days-having types render a number input; the two overdue
    # types don't (they fire on the due date itself), so their field is
    # simply absent from the form and threshold_days stays NULL.
    db = get_db()
    for alert_type in ALERT_TYPE_TITLES:
        raw_threshold = request.form.get(f"threshold::{alert_type}", "").strip()
        threshold_days = None
        if raw_threshold:
            try:
                threshold_days = max(0, int(raw_threshold))
            except ValueError:
                flash(f"Threshold for {ALERT_TYPE_TITLES[alert_type]} must be a number")
                return redirect(url_for("settings"))

        severity = request.form.get(f"severity::{alert_type}", "warning")
        if severity not in ("critical", "warning", "info"):
            severity = "warning"
        notify_email = 1 if request.form.get(f"notify_email::{alert_type}") == "on" else 0
        notify_teams = 1 if request.form.get(f"notify_teams::{alert_type}") == "on" else 0
        notify_inapp = 1 if request.form.get(f"notify_inapp::{alert_type}") == "on" else 0

        if raw_threshold:
            db.execute(
                "UPDATE alert_type_settings SET severity = ?, threshold_days = ?, "
                "notify_email = ?, notify_teams = ?, notify_inapp = ? WHERE alert_type = ?",
                (severity, threshold_days, notify_email, notify_teams, notify_inapp, alert_type),
            )
        else:
            db.execute(
                "UPDATE alert_type_settings SET severity = ?, notify_email = ?, notify_teams = ?, notify_inapp = ? WHERE alert_type = ?",
                (severity, notify_email, notify_teams, notify_inapp, alert_type),
            )
    db.commit()

    audit_log("update_alert_settings")
    flash("Alert settings updated")
    return redirect(url_for("settings"))
