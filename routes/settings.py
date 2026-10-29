"""Settings + administration routes: audit log viewer, the settings page,
RBAC matrix, lifecycle stages, document categories, contacts/partners
management, per-type alert config, and the contact/partner undo restores.
Registration side effects only.
"""
import io
import sqlite3

from flask import Response, abort, flash, redirect, request, session, url_for

from constants import ALERT_TYPE_TITLES, CONTACT_LISTS, PERMISSIONS, ROLES
from core import app, as_id, offer_undo, permission_required, undo_note
from db import get_db, restore_deleted, soft_delete
from services import stages as stage_ops
from security import safe_csv_writer, valid_email
from services.audit import audit_log
from spa import spa_index


def _restore_or_refuse(table, item_id):
    """Undo a delete, or refuse: 404 when there is no such deleted entry, 409
    when its undo window has passed. Never "restored" and an audit row for
    nothing (P3-19)."""
    if not get_db().execute(f"SELECT 1 FROM {table} WHERE id = ? AND deleted_at IS NOT NULL", (item_id,)).fetchone():
        abort(404)
    if not restore_deleted(table, item_id):
        abort(409, description="Too late to undo — the undo window has passed")


@app.route("/undo/contact/<list_key>/<int:item_id>", methods=["POST"])
@permission_required("manage_contacts")
def undo_contact(list_key, item_id):
    if list_key not in CONTACT_LISTS:
        abort(404)
    meta = CONTACT_LISTS[list_key]
    _restore_or_refuse(meta["table"], item_id)
    flash(f"{meta['label']} entry restored")
    audit_log("restore_contact", list_key, item_id)
    return redirect(url_for("settings_contacts"))


@app.route("/undo/partner/<int:partner_id>", methods=["POST"])
@permission_required("manage_contacts")
def undo_partner(partner_id):
    db = get_db()
    stamp = db.execute("SELECT deleted_at FROM partners WHERE id = ?", (partner_id,)).fetchone()
    if not stamp or not restore_deleted("partners", partner_id):
        flash("Too late to undo — the undo window has passed", "error")
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
    _restore_or_refuse("partner_account_managers", manager_id)
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
    if username:   # one person, whether a row names their sign-in handle or their name (sim roles-10)
        where += (" AND (username = ? OR user_id IN (SELECT id FROM users WHERE name = ? OR username = ?)"
                  " OR username IN (SELECT username FROM users WHERE name = ?))")
        params.extend([username] * 4)
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
    return spa_index()


@app.route("/settings")
@permission_required("manage_settings")
def settings():
    return spa_index()


# Settings is one page with a side menu; each area has its own address.
SETTINGS_SECTIONS = ("general", "security", "people", "workflow", "notifications", "integrations", "ai", "reports", "documents", "backups", "api", "audit", "map")
# A policy area drawn inside another area's page.
AREA_SECTION = {"ai_schedule": "ai"}


@app.route("/settings/map/page")
@permission_required("manage_settings")
def settings_map_page():
    """The Odin System Map (docs/system-map.html, regenerated with every change
    and shipped in the image), framed by Settings › System map & changes. The
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
    return spa_index()


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
            flash("Not saved. " + problem, "error")
            return redirect(url_for("settings_section", section="ai"))
    changed, errors = save_policies(area, request.form)
    if errors:
        flash("Not saved. " + "; ".join(errors), "error")
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
            from services.ai.health import queue
            db = get_db()
            db.execute("DELETE FROM settings WHERE key = ?", (STATUS_SETTING,))   # a new server starts unknown
            db.commit()
            if status(db)["state"] != "off":
                queue(db, "validate", payload={"reason": "the AI settings changed"}, actor=session.get("user_name"))
                flash("Saved. Each AI feature is checked again once the server answers; this page shows how it goes.")
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
    return spa_index()


@app.route("/settings/rbac", methods=["POST"])
@permission_required("manage_settings")
def settings_rbac_update():
    if session.get("role") != "Admin":
        # manage_settings can be delegated; the matrix would let its holder grant
        # their own role manage_users and then make themselves Admin (test round P2-1)
        flash("Only an admin can change role permissions", "error")
        return redirect(url_for("settings_rbac"))
    if request.form.get("matrix") != "full":
        # an absent box means "off", so only a post of the whole matrix may save: a partial
        # one (an API caller, an old page) used to switch off every grant it left out
        flash("Not saved: send the whole matrix (the field matrix=full with every box that is on)", "error")
        return redirect(url_for("settings_rbac"))
    db = get_db()
    refused = [p for p in PERMISSIONS if p not in EXTERNAL_ALLOWED and request.form.get(f"{p}::External") == "on"]
    if refused:
        flash(f"Not saved: partner and customer accounts (External) can only view, comment and download, not {', '.join(refused)}", "error")
        return redirect(url_for("settings_rbac"))
    before = {(r["permission"], r["role"]): bool(r["allowed"]) for r in db.execute("SELECT * FROM role_permissions")}
    # Admin always keeps manage_settings + manage_users — otherwise an admin could
    # lock every account (including their own) out of this page with no UI path
    # back in — and every view_* right, since an admin who cannot see projects is
    # just a confused admin.
    floor = {(p, "Admin") for p in PERMISSIONS if p in ("manage_settings", "manage_users") or p.startswith("view_")}
    wanted = {(p, r): (p, r) in floor or request.form.get(f"{p}::{r}") == "on" for p in PERMISSIONS for r in ROLES}
    on = [k for k, v in before.items() if v and k not in floor]
    going = sum(1 for k in on if not wanted.get(k, True))
    if going * 2 > len(on) and request.form.get("confirm") != "1":
        flash(f"Not saved: this would switch off {going} of the {len(on)} permissions that are on. Confirm to save it.", "error")
        return redirect(url_for("settings_rbac"))
    changes = []
    for permission in PERMISSIONS:
        for role in ROLES:
            allowed = 1 if wanted[(permission, role)] else 0
            db.execute(
                "UPDATE role_permissions SET allowed = ? WHERE permission = ? AND role = ?",
                (allowed, permission, role),
            )
            if before.get((permission, role), False) != bool(allowed):
                changes.append(f"{permission}: {role} {'on' if allowed else 'off'}")
    db.commit()
    audit_log("update_role_permissions", details="; ".join(changes) or "no change")
    flash("Permissions updated" if changes else "Nothing changed")
    return redirect(url_for("settings_rbac"))


# What an External (partner or customer) account may ever be granted: its
# seeded rights, which only view, comment and download. Anything else would
# hand an outsider staff or admin powers from one tick in the matrix.
EXTERNAL_ALLOWED = frozenset(p for p, roles in PERMISSIONS.items() if "External" in roles)


# ---- stage templates: what a new project copies its stage list from ---------

def _template(template_id):
    row = get_db().execute("SELECT * FROM stage_templates WHERE id = ?", (template_id,)).fetchone()
    if row is None:
        abort(404)
    return row


def _template_change(action, error, detail=None):
    if error:
        flash(error, "error")
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
            "SELECT name, position, sla_days, gate_tasks, required_docs FROM stage_template_stages WHERE template_id = ? ORDER BY position", (source["id"],)
        ).fetchall():
            db.execute(
                "INSERT INTO stage_template_stages (template_id, name, position, sla_days, gate_tasks, required_docs) VALUES (?, ?, ?, ?, ?, ?)",
                (cursor.lastrowid, row["name"], row["position"], row["sla_days"], row["gate_tasks"], row["required_docs"]),
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
        flash(f"Removed '{gone}': new rollouts from this template send their sign-off from the stage before {names[-1]} instead")
    return _template_change("delete_template_stage", error, str(stage_id))


@app.route("/settings/templates/<int:template_id>/sla", methods=["POST"])
@permission_required("manage_settings")
def settings_stage_sla(template_id):
    """Expected days per stage for projects created from this template."""
    _template(template_id)
    return _template_change("update_template_slas", stage_ops.set_slas("template", template_id, request.form), str(template_id))


@app.route("/settings/templates/<int:template_id>/gates", methods=["POST"])
@permission_required("manage_settings")
def settings_stage_gates(template_id):
    """What each stage asks before a rollout leaves it, for rollouts created from this template."""
    _template(template_id)
    return _template_change("update_template_gates", stage_ops.set_gates("template", template_id, request.form), str(template_id))


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


def _name_problem(name, label, limit, email=None):
    """A pick-list entry's name (and address, when it has one): required,
    one line, at most `limit` characters."""
    if not name:
        return f"{label} required"
    if len(name) > limit or any(ord(ch) < 32 for ch in name):
        return f"{label}: one line, at most {limit} characters"
    if email and not valid_email(email):
        return "Enter a valid email address"
    return None


@app.route("/settings/doc-categories/add", methods=["POST"])
@permission_required("manage_settings")
def settings_category_add():
    name = request.form.get("name", "").strip()
    db = get_db()
    if problem := _name_problem(name, "Category name", 80):
        flash(problem, "error")
    elif db.execute("SELECT 1 FROM doc_categories WHERE name = ?", (name,)).fetchone():
        flash("Category already exists", "error")
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
        flash(f"Cannot delete '{category['name']}' — {in_use} document(s) use it", "error")
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
    return spa_index()


@app.route("/settings/contacts/<list_key>/add", methods=["POST"])
@permission_required("manage_contacts")
def settings_contacts_add(list_key):
    if list_key not in CONTACT_LISTS:
        abort(404)
    meta = CONTACT_LISTS[list_key]
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip() if meta["has_email"] else None
    if problem := _name_problem(name, "Name", 120, email):
        flash(problem, "error")
        return redirect(url_for("settings_contacts"))
    db = get_db()
    vendor_id = _vendor_field(db) if list_key == "products" else None
    if vendor_id is False:
        flash("Pick a vendor from the list", "error")
        return redirect(url_for("settings_contacts"))
    if _name_taken(db, meta["table"], name):
        flash(f"'{name}' already exists in {meta['label']}", "error")
        return redirect(url_for("settings_contacts"))
    try:
        if meta["has_email"]:
            db.execute(f"INSERT INTO {meta['table']} (name, email) VALUES (?, ?)", (name, email or None))
        elif list_key == "products":
            db.execute("INSERT INTO products (name, vendor_id) VALUES (?, ?)", (name, vendor_id))
        else:
            db.execute(f"INSERT INTO {meta['table']} (name) VALUES (?)", (name,))
        db.commit()
        audit_log("add_contact", list_key, None, name)
        flash(f"{meta['label']}: '{name}' added")
    except sqlite3.IntegrityError:
        flash(f"'{name}' already exists in {meta['label']}", "error")
    return redirect(url_for("settings_contacts"))


def _name_taken(db, table, name, exclude_id=None):
    """Another live entry with the same name, ignoring case ("SimVendor" and
    "simvendor" are one vendor, sim roles-11). A deleted entry waiting out its
    undo window gives the name up (the column is UNIQUE): it is renamed out of
    the way, so it can still be undone, and the new one takes the name (P2-18).
    The caller commits."""
    db.execute(f"UPDATE {table} SET name = name || ' (deleted ' || id || ')' WHERE lower(name) = lower(?) AND deleted_at IS NOT NULL", (name,))
    return db.execute(f"SELECT 1 FROM {table} WHERE lower(name) = lower(?) AND deleted_at IS NULL AND id IS NOT ?",
                      (name, exclude_id)).fetchone() is not None


def _vendor_field(db):
    """The product form's vendor: None for "any vendor", a live vendor's id,
    or False when the field names something else."""
    raw = request.form.get("vendor_id", "").strip()
    if not raw:
        return None
    vendor_id = as_id(raw)
    if vendor_id and db.execute("SELECT 1 FROM vendors WHERE id = ? AND deleted_at IS NULL", (vendor_id,)).fetchone():
        return vendor_id
    return False


def _carry_rename(db, column, old, new, where="", args=()):
    """Projects keep a picked name as text: a rename follows it there, so
    "used in N projects" and the project pages stay true."""
    if old != new:
        db.execute(f"UPDATE projects SET {column} = ? WHERE {column} = ?{where}", (new, old, *args))


@app.route("/settings/contacts/<list_key>/<int:item_id>/edit", methods=["POST"])
@permission_required("manage_contacts")
def settings_contacts_edit(list_key, item_id):
    if list_key not in CONTACT_LISTS:
        abort(404)
    meta = CONTACT_LISTS[list_key]
    db = get_db()
    row = db.execute(f"SELECT * FROM {meta['table']} WHERE id = ? AND deleted_at IS NULL", (item_id,)).fetchone()
    if not row:
        abort(404)
    name = request.form.get("name", "").strip()
    email = (request.form.get("email", "").strip() or None) if meta["has_email"] else None
    if problem := _name_problem(name, "Name", 120, email):
        flash(problem, "error")
        return redirect(url_for("settings_contacts"))
    vendor_id = _vendor_field(db) if list_key == "products" else None
    if vendor_id is False:
        flash("Pick a vendor from the list", "error")
        return redirect(url_for("settings_contacts"))
    if _name_taken(db, meta["table"], name, item_id):
        flash(f"'{name}' already exists in {meta['label']}", "error")
        return redirect(url_for("settings_contacts"))
    try:
        if meta["has_email"]:
            db.execute(f"UPDATE {meta['table']} SET name = ?, email = ? WHERE id = ?", (name, email, item_id))
            email_col = meta["column"].replace("_name", "_email")
            if (row["email"] or None) != email:
                db.execute(f"UPDATE projects SET {email_col} = ? WHERE {meta['column']} = ? AND COALESCE({email_col}, '') = ?",
                           (email, row["name"], row["email"] or ""))
        elif list_key == "products":
            db.execute("UPDATE products SET name = ?, vendor_id = ? WHERE id = ?", (name, vendor_id, item_id))
        else:
            db.execute(f"UPDATE {meta['table']} SET name = ? WHERE id = ?", (name, item_id))
        _carry_rename(db, meta["column"], row["name"], name)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        flash(f"'{name}' already exists in {meta['label']}", "error")
        return redirect(url_for("settings_contacts"))
    audit_log("edit_contact", list_key, item_id, name, details=None if row["name"] == name else f"renamed from {row['name']}")
    flash(f"{meta['label']}: '{name}' saved")
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/partners/<int:partner_id>/edit", methods=["POST"])
@permission_required("manage_contacts")
def settings_partner_edit(partner_id):
    db = get_db()
    row = db.execute("SELECT * FROM partners WHERE id = ? AND deleted_at IS NULL", (partner_id,)).fetchone()
    if not row:
        abort(404)
    name = request.form.get("name", "").strip()
    if problem := _name_problem(name, "Partner name", 120):
        flash(problem, "error")
        return redirect(url_for("settings_contacts"))
    if _name_taken(db, "partners", name, partner_id):
        flash(f"Partner '{name}' already exists", "error")
        return redirect(url_for("settings_contacts"))
    try:
        db.execute("UPDATE partners SET name = ? WHERE id = ?", (name, partner_id))
        _carry_rename(db, "partner_name", row["name"], name)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        flash(f"Partner '{name}' already exists", "error")
        return redirect(url_for("settings_contacts"))
    audit_log("edit_partner", "partner", partner_id, name, details=None if row["name"] == name else f"renamed from {row['name']}")
    flash(f"Partner '{name}' saved")
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/partner-managers/<int:manager_id>/edit", methods=["POST"])
@permission_required("manage_contacts")
def settings_partner_manager_edit(manager_id):
    db = get_db()
    row = db.execute("SELECT m.*, p.name AS partner FROM partner_account_managers m JOIN partners p ON p.id = m.partner_id "
                     "WHERE m.id = ? AND m.deleted_at IS NULL", (manager_id,)).fetchone()
    if not row:
        abort(404)
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip() or None
    if problem := _name_problem(name, "Account manager name", 120, email):
        flash(problem, "error")
        return redirect(url_for("settings_contacts"))
    db.execute("UPDATE partner_account_managers SET name = ?, email = ? WHERE id = ?", (name, email, manager_id))
    if (row["email"] or None) != email:
        db.execute("UPDATE projects SET partner_account_manager_email = ? WHERE partner_name = ? AND partner_account_manager_name = ? "
                   "AND COALESCE(partner_account_manager_email, '') = ?", (email, row["partner"], row["name"], row["email"] or ""))
    _carry_rename(db, "partner_account_manager_name", row["name"], name, " AND partner_name = ?", (row["partner"],))
    db.commit()
    audit_log("edit_partner_manager", "partner_manager", manager_id, name, details=None if row["name"] == name else f"renamed from {row['name']}")
    flash(f"Account manager '{name}' saved")
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/<list_key>/<int:item_id>/delete", methods=["POST"])
@permission_required("manage_contacts")
def settings_contacts_delete(list_key, item_id):
    if list_key not in CONTACT_LISTS:
        abort(404)
    meta = CONTACT_LISTS[list_key]
    if not soft_delete(meta['table'], item_id):
        abort(404)
    offer_undo("undo_contact", list_key=list_key, item_id=item_id)
    flash(f"{meta['label']} entry deleted. Undo {undo_note()}")
    audit_log("delete_contact", list_key, item_id)
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/partners/add", methods=["POST"])
@permission_required("manage_contacts")
def settings_partner_add():
    name = request.form.get("name", "").strip()
    if problem := _name_problem(name, "Partner name", 120):
        flash(problem, "error")
        return redirect(url_for("settings_contacts"))
    db = get_db()
    if _name_taken(db, "partners", name):
        flash(f"Partner '{name}' already exists", "error")
        return redirect(url_for("settings_contacts"))
    try:
        db.execute("INSERT INTO partners (name) VALUES (?)", (name,))
        db.commit()
        audit_log("add_partner", "partner", None, name)
        flash(f"Partner '{name}' added")
    except sqlite3.IntegrityError:
        flash(f"Partner '{name}' already exists", "error")
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/partners/<int:partner_id>/delete", methods=["POST"])
@permission_required("manage_contacts")
def settings_partner_delete(partner_id):
    db = get_db()
    if not soft_delete("partners", partner_id):
        abort(404)
    db.execute("UPDATE partner_account_managers SET deleted_at = (SELECT deleted_at FROM partners WHERE id = ?) WHERE partner_id = ? AND deleted_at IS NULL",
               (partner_id, partner_id))
    db.commit()
    audit_log("delete_partner", "partner", partner_id)
    offer_undo("undo_partner", partner_id=partner_id)
    flash(f"Partner deleted (its account managers were removed too). Undo {undo_note()}")
    return redirect(url_for("settings_contacts"))


@app.route("/settings/contacts/partners/<int:partner_id>/managers/add", methods=["POST"])
@permission_required("manage_contacts")
def settings_partner_manager_add(partner_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM partners WHERE id = ? AND deleted_at IS NULL", (partner_id,)).fetchone():
        abort(404)
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip() or None
    if problem := _name_problem(name, "Account manager name", 120, email):
        flash(problem, "error")
        return redirect(url_for("settings_contacts"))
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
    if not soft_delete("partner_account_managers", manager_id):
        abort(404)
    offer_undo("undo_partner_manager", manager_id=manager_id)
    flash(f"Account manager deleted. Undo {undo_note()}")
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
            # bounded: a day count past a year is a typo, and a huge one overflowed every page that adds it to a date
            threshold_days = int(raw_threshold) if raw_threshold.isascii() and raw_threshold.isdigit() and len(raw_threshold) <= 3 else None
            if threshold_days is None or threshold_days > 365:
                flash(f"Threshold for {ALERT_TYPE_TITLES[alert_type]}: a whole number of days, 0 to 365", "error")
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
