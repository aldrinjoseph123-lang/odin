"""Settings + administration routes: audit log viewer, the settings page,
RBAC matrix, lifecycle stages, document categories, contacts/partners
management, per-type alert config, and the contact/partner undo restores.
Registration side effects only.
"""
import csv
import io
import sqlite3

from flask import Response, abort, flash, redirect, render_template, request, session, url_for
from markupsafe import Markup

import graph
from constants import ALERT_TYPE_TITLES, CONTACT_LISTS, PERMISSIONS, ROLES
from core import app, permission_required, undo_button, undo_note, write_required
from db import get_db, get_setting, restore_deleted, soft_delete
from services.alerts import get_alert_type_settings
from services import stages as stage_ops
from security import safe_csv_writer
from services.audit import audit_log
from spa import spa_index, spa_serves


@app.route("/undo/contact/<list_key>/<int:item_id>", methods=["POST"])
@permission_required("manage_contacts")
def undo_contact(list_key, item_id):
    if list_key not in CONTACT_LISTS:
        abort(404)
    meta = CONTACT_LISTS[list_key]
    restore_deleted(meta['table'], item_id)
    flash(f"{meta['label']} entry restored")
    audit_log("restore_contact", list_key, item_id)
    return redirect(url_for("settings_contacts"))


@app.route("/undo/partner/<int:partner_id>", methods=["POST"])
@permission_required("manage_contacts")
def undo_partner(partner_id):
    db = get_db()
    stamp = db.execute("SELECT deleted_at FROM partners WHERE id = ?", (partner_id,)).fetchone()
    if not stamp or not restore_deleted("partners", partner_id):
        flash("Too late to undo — the undo window has passed")
        return redirect(url_for("settings_contacts"))
    # only the managers that went with the partner (B4): one removed on its own stays removed
    db.execute("UPDATE partner_account_managers SET deleted_at = NULL WHERE partner_id = ? AND deleted_at = ?", (partner_id, stamp[0]))
    db.commit()
    audit_log("restore_partner", "partner", partner_id)
    flash("Partner and its account managers restored")
    return redirect(url_for("settings_contacts"))


@app.route("/undo/partner-manager/<int:manager_id>", methods=["POST"])
@permission_required("manage_contacts")
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
    writer = safe_csv_writer(out)
    writer.writerow(["timestamp", "username", "action", "resource_type", "resource_id", "resource_name", "details", "ip_address"])
    for r in rows:
        writer.writerow([r["timestamp"], r["username"], r["action"], r["resource_type"], r["resource_id"], r["resource_name"], r["details"], r["ip_address"]])
    audit_log("export_audit_log", details=f"{len(rows)} rows")
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=odin-audit-log.csv"})


@app.route("/audit-logs")
@permission_required("manage_settings")
def audit_logs_view():
    if spa_serves("audit_logs_view"):
        return spa_index()
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
    if spa_serves("settings"):
        return spa_index()
    db = get_db()
    templates = [
        {"id": t["id"], "name": t["name"], "stages": stage_ops.list_stages("template", t["id"]),
         "projects": db.execute("SELECT COUNT(*) FROM projects WHERE stage_template_id = ? AND deleted_at IS NULL", (t["id"],)).fetchone()[0]}
        for t in db.execute("SELECT * FROM stage_templates ORDER BY id").fetchall()
    ]
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
        templates=templates,
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


# Settings is one page with a side menu; each area has its own address.
SETTINGS_SECTIONS = ("general", "security", "people", "workflow", "notifications", "integrations", "ai", "reports", "documents", "backups", "api", "audit", "map")
# A policy area drawn inside another area's page.
AREA_SECTION = {"ai_schedule": "ai"}


@app.route("/settings/map/page")
@permission_required("manage_settings")
def settings_map_page():
    """The Odin System Map (docs/system-map.html, regenerated with every change
    and shipped in the image), framed by Settings → System map & changes. The
    one page Odin lets itself frame: same origin only, admins only."""
    import os
    from flask import send_file
    from security import CSP
    resp = send_file(os.path.join(app.root_path, "docs", "system-map.html"), mimetype="text/html", max_age=0)
    resp.headers["Content-Security-Policy"] = CSP.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/settings/<section>")
@permission_required("manage_settings")
def settings_section(section):
    if section not in SETTINGS_SECTIONS:
        abort(404)
    if spa_serves("settings_section"):
        return spa_index()
    return redirect(url_for("settings"))


@app.route("/settings/policies/<area>", methods=["POST"])
@permission_required("manage_settings")
def settings_policies(area):
    """The one save path for every admin policy (policies.POLICIES)."""
    from policies import POLICIES, save_policies
    if area not in {e["area"] for e in POLICIES.values()}:
        abort(404)
    if area == "ai":
        # the address guard, before anything is stored (services/ai/client.py)
        from policies import POLICIES as P, _parse
        from services.ai.client import address_problem
        try:
            url = _parse(P["ai_base_url"], request.form.get("ai_base_url", ""))
        except ValueError:
            url = ""   # save_policies reports the format
        problem = url and address_problem(url, request.form.get("ai_allow_external") == "on")
        if problem:
            flash("Not saved. " + problem)
            return redirect(url_for("settings_section", section="ai"))
    changed, errors = save_policies(area, request.form)
    if errors:
        flash("Not saved. " + "; ".join(errors))
    elif changed:
        audit_log("update_policies", "settings", None, area, ", ".join(changed))
        if any(c.startswith("mfa_required=") for c in changed):
            # test report SEC-6: sessions begun before the rule kept working; end
            # those of everyone the rule now covers who has not set it up, so their
            # next sign-in goes through the setup gate
            from policies import policy
            db = get_db()
            rule = policy("mfa_required")
            if rule != "off":
                n = db.execute("UPDATE users SET session_epoch = session_epoch + 1 WHERE kind = 'internal' AND totp_enabled_at IS NULL AND id != ?"
                               + ("" if rule == "everyone" else " AND role = 'Admin'"), (session["user_id"],)).rowcount
                db.commit()
                if n:
                    audit_log("end_sessions_for_two_step", "settings", None, area, f"{n} account(s) must set up two-step sign-in")
        if area == "ai" and any(c.split("=")[0] in ("ai_enabled", "ai_base_url", "ai_model") for c in changed):
            from services.ai import STATUS_SETTING, status
            from services.ai.health import heartbeat, queue
            db = get_db()
            db.execute("DELETE FROM settings WHERE key = ?", (STATUS_SETTING,))   # a new server starts unknown
            db.commit()
            if status(db)["state"] != "off":
                queue(db, "validate", payload={"reason": "the AI settings changed"}, actor=session.get("user_name"))
                flash("Saved. Every AI feature is now being validated on this server; this page updates as it goes.")
            else:
                flash("Saved")
        else:
            flash("Saved")
    else:
        flash("Nothing changed")
    return redirect(url_for("settings_section", section=AREA_SECTION.get(area, area)))


@app.route("/settings/rbac")
@permission_required("manage_settings")
def settings_rbac():
    if spa_serves("settings_rbac"):
        return spa_index()
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


# ---- stage templates: what a new project copies its stage list from ---------

def _template(template_id):
    row = get_db().execute("SELECT * FROM stage_templates WHERE id = ?", (template_id,)).fetchone()
    if row is None:
        abort(404)
    return row


def _template_change(action, error, detail=None):
    if error:
        flash(error)
    else:
        audit_log(action, "stage_template", None, None, detail)
    return redirect(url_for("settings") + "#templates")


@app.route("/settings/templates/add", methods=["POST"])
@permission_required("manage_settings")
def settings_template_add():
    name = request.form.get("name", "").strip()[:80]
    db = get_db()
    if not name:
        return _template_change("add_stage_template", "Template name required")
    if db.execute("SELECT 1 FROM stage_templates WHERE name = ?", (name,)).fetchone():
        return _template_change("add_stage_template", "Template already exists")
    cursor = db.execute("INSERT INTO stage_templates (name) VALUES (?)", (name,))
    # Start from the Generic list rather than empty — an empty template cannot
    # create projects, and copying is one delete away from any shape wanted.
    source = db.execute("SELECT id FROM stage_templates ORDER BY id LIMIT 1").fetchone()
    if source and source["id"] != cursor.lastrowid:
        for row in db.execute(
            "SELECT name, position, sla_days FROM stage_template_stages WHERE template_id = ? ORDER BY position", (source["id"],)
        ).fetchall():
            db.execute(
                "INSERT INTO stage_template_stages (template_id, name, position, sla_days) VALUES (?, ?, ?, ?)",
                (cursor.lastrowid, row["name"], row["position"], row["sla_days"]),
            )
    db.commit()
    return _template_change("add_stage_template", None, name)


@app.route("/settings/templates/<int:template_id>/rename", methods=["POST"])
@permission_required("manage_settings")
def settings_template_rename(template_id):
    _template(template_id)
    name = request.form.get("name", "").strip()[:80]
    db = get_db()
    if not name:
        return _template_change("rename_stage_template", "Template name required")
    if db.execute("SELECT 1 FROM stage_templates WHERE name = ? AND id != ?", (name, template_id)).fetchone():
        return _template_change("rename_stage_template", "Template name already in use")
    db.execute("UPDATE stage_templates SET name = ? WHERE id = ?", (name, template_id))
    db.commit()
    return _template_change("rename_stage_template", None, f"{template_id} -> {name}")


@app.route("/settings/templates/<int:template_id>/delete", methods=["POST"])
@permission_required("manage_settings")
def settings_template_delete(template_id):
    template = _template(template_id)
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM stage_templates").fetchone()[0] <= 1:
        return _template_change("delete_stage_template", "Cannot delete the last template")
    # Projects keep their own copies; only the source list goes.
    db.execute("UPDATE projects SET stage_template_id = NULL WHERE stage_template_id = ?", (template_id,))
    db.execute("DELETE FROM stage_template_stages WHERE template_id = ?", (template_id,))
    db.execute("DELETE FROM stage_templates WHERE id = ?", (template_id,))
    db.commit()
    return _template_change("delete_stage_template", None, template["name"])


@app.route("/settings/templates/<int:template_id>/stages/add", methods=["POST"])
@permission_required("manage_settings")
def settings_stage_add(template_id):
    _template(template_id)
    name = request.form.get("name", "")
    return _template_change("add_template_stage", stage_ops.add_stage("template", template_id, name), f"{template_id}: {name}")


@app.route("/settings/templates/<int:template_id>/stages/<int:stage_id>/rename", methods=["POST"])
@permission_required("manage_settings")
def settings_stage_rename(template_id, stage_id):
    _template(template_id)
    name = request.form.get("name", "")
    return _template_change("rename_template_stage", stage_ops.rename_stage("template", template_id, stage_id, name), f"{stage_id} -> {name}")


@app.route("/settings/templates/<int:template_id>/stages/<int:stage_id>/move", methods=["POST"])
@permission_required("manage_settings")
def settings_stage_move(template_id, stage_id):
    _template(template_id)
    direction = request.form.get("direction", "")
    return _template_change("move_template_stage", stage_ops.move_stage("template", template_id, stage_id, direction), f"{stage_id} {direction}")


@app.route("/settings/templates/<int:template_id>/stages/<int:stage_id>/delete", methods=["POST"])
@permission_required("manage_settings")
def settings_stage_delete(template_id, stage_id):
    _template(template_id)
    from constants import SIGNOFF_STAGE
    rows = stage_ops.list_stages("template", template_id)
    names = [s["name"] for s in rows]
    gone = next((s["name"] for s in rows if s["id"] == stage_id), None)
    error = stage_ops.delete_stage("template", template_id, stage_id)
    if not error and gone == SIGNOFF_STAGE and len(names) >= 2 and names[-2] == gone:   # R14: allowed, but said
        flash(f"Removed '{gone}': new projects from this template send their sign-off from the stage before {names[-1]} instead")
    return _template_change("delete_template_stage", error, str(stage_id))


@app.route("/settings/templates/<int:template_id>/sla", methods=["POST"])
@permission_required("manage_settings")
def settings_stage_sla(template_id):
    """Expected days per stage for projects created from this template."""
    _template(template_id)
    return _template_change("update_template_slas", stage_ops.set_slas("template", template_id, request.form), str(template_id))


@app.route("/settings/templates/<int:template_id>/sla/from-measured", methods=["POST"])
@permission_required("manage_settings")
def settings_stage_sla_from_measured(template_id):
    """Adopt each stage's measured average across projects created from this
    template, measured in working days like the SLAs themselves (when the
    workspace counts them). Stages nothing has passed through are left alone — no evidence,
    no made-up number. Rounds up, so the target is never stricter than the
    average it came from."""
    import math
    from services.analytics import build_cycle_times, clock

    _template(template_id)
    db = get_db()
    projects = db.execute(
        "SELECT * FROM projects WHERE deleted_at IS NULL AND stage_template_id = ?", (template_id,)
    ).fetchall()
    notes_by_project = {}
    for note in db.execute("SELECT project_id, stage, created_at FROM status_notes ORDER BY created_at"):
        notes_by_project.setdefault(note["project_id"], []).append(note)
    stage_names = [row["name"] for row in stage_ops.list_stages("template", template_id)]
    if not stage_names:
        return _template_change("set_template_slas_from_measured", "Template has no stages")
    stats = build_cycle_times(projects, notes_by_project, stage_names, stage_names[-1], clock=clock())
    applied = 0
    for row in stats["stages"]:
        if row["avg_days"] is None or row["stage"] == stage_names[-1]:
            continue
        db.execute(
            "UPDATE stage_template_stages SET sla_days = ? WHERE template_id = ? AND name = ?",
            (min(365, max(1, math.ceil(row["avg_days"]))), template_id, row["stage"]),
        )
        applied += 1
    db.commit()
    flash(f"Set {applied} SLA(s) from measured averages" if applied else "No stage has completed visits yet — nothing to measure")
    return _template_change("set_template_slas_from_measured", None, f"{applied} stage(s)")


@app.route("/settings/doc-categories/add", methods=["POST"])
@permission_required("manage_settings")
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
@permission_required("manage_settings")
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


@app.route("/settings/doc-categories/<int:cat_id>/partners", methods=["POST"])
@permission_required("manage_settings")
def settings_category_partners(cat_id):
    """Whether partners and customers see documents of this kind."""
    db = get_db()
    category = db.execute("SELECT * FROM doc_categories WHERE id = ?", (cat_id,)).fetchone()
    if not category:
        abort(404)
    on = request.form.get("partners") == "on"
    db.execute("UPDATE doc_categories SET partners = ? WHERE id = ?", (1 if on else 0, cat_id))
    db.commit()
    audit_log("doc_category_partners", "doc_category", cat_id, category["name"], "shown to partners" if on else "hidden from partners")
    flash(f"'{category['name']}' is {'shown to' if on else 'hidden from'} partners and customers")
    return redirect(url_for("settings"))


@app.route("/settings/contacts")
@permission_required("manage_contacts")
def settings_contacts():
    if spa_serves("settings_contacts"):
        return spa_index()
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
    flash(Markup(f"{meta['label']} entry deleted. {undo_button('Undo', 'undo_contact', list_key=list_key, item_id=item_id)} {undo_note()}"))
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
    db.execute("UPDATE partner_account_managers SET deleted_at = (SELECT deleted_at FROM partners WHERE id = ?) WHERE partner_id = ? AND deleted_at IS NULL",
               (partner_id, partner_id))
    db.commit()
    audit_log("delete_partner", "partner", partner_id)
    flash(Markup(f"Partner deleted (its account managers were removed too). {undo_button('Undo', 'undo_partner', partner_id=partner_id)} {undo_note()}"))
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
    flash(Markup(f"Account manager deleted. {undo_button('Undo', 'undo_partner_manager', manager_id=manager_id)} {undo_note()}"))
    audit_log("delete_partner_manager", "partner_manager", manager_id)
    return redirect(url_for("settings_contacts"))


@app.route("/settings/alerts", methods=["POST"])
@permission_required("manage_settings")
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
