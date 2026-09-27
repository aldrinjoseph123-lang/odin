"""JSON API for the React front end. Same session cookie, same CSRF token
(sent as X-CSRF-Token), same decorators and audit trail as the HTML routes —
the API is a second door into the same rooms, not a second house.
"""
from flask import abort, jsonify, request, session, url_for

from datetime import date, datetime

from constants import ALERT_TYPE_TITLES, CONTACT_LISTS, DELIVERY_MODES, EXTERNAL_PROJECT_ROLES, PERMISSIONS, PROJECT_MANAGER, PROJECT_ROLES, ROLES, VIA_OPTIONS
from core import app, login_required, nav_counts, permission_required, project_allows, project_role_required, project_scope, role_has_permission
from db import get_doc_category_names, stage_rows
from db import PROJECT_OPEN_SQL, current_approval, get_db, get_stage_names, get_terminal_stage, is_customer_on, my_project_ids, participants_for, sla_for_project, stages_for_projects
from routes.auth import attempt_login
from routes.board import BANNER_NAMES, COLUMN_CARDS, alerts_page_data, board_data, dismiss_alert
from routes.projects import DEFAULT_SORT, PROJECTS_PER_PAGE, SORT_COLUMNS, change_stage, decide_approval, filtered_projects_query, load_project, report_context
from security import csrf_token
from services.alerts import schedule_status
from services.analytics import _parse, sla_by_stage, stage_sla_state, stage_timeline
from services.audit import audit_log
from spa import spa_asset


def _permissions_for(role):
    return [
        row["permission"]
        for row in get_db().execute(
            "SELECT permission FROM role_permissions WHERE role = ? AND allowed = 1 ORDER BY permission", (role,)
        )
    ]


def _current_user():
    if "user_id" not in session:
        return None
    return {
        "id": session["user_id"],
        "name": session.get("user_name"),
        "role": session.get("role"),
        "kind": session.get("kind", "internal"),
        "must_change_password": bool(session.get("must_change_password")),
        "permissions": _permissions_for(session.get("role")),
        "nav": nav_counts(),
    }


@app.route("/api/session")
def api_session():
    """Who am I, what may I do, and the CSRF token every mutation must carry.
    Anonymous callers get the token too — the login form needs it."""
    return jsonify({"csrf": csrf_token(), "user": _current_user()})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    ok, message = attempt_login((data.get("username") or "").strip(), data.get("password") or "")
    if not ok:
        # attempt_login audits every outcome; 429 when it is the lockout talking.
        return jsonify({"error": message}), (429 if message.startswith("Too many") else 401)
    # attempt_login cleared the session (fixation defence), so the token rotated.
    return jsonify({"user": _current_user(), "csrf": csrf_token()})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    if "user_id" in session:
        audit_log("logout", "user", session["user_id"], session.get("user_name"))
    session.clear()
    return jsonify({"ok": True, "csrf": csrf_token()})


def _card(p):
    return {
        "id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"],
        "owner_name": p["owner_name"], "delivery_mode": p["delivery_mode"],
        "task_total": p["task_total"], "task_done": p["task_done"], "updated_at": p["updated_at"],
    }


@app.route("/api/board")
@permission_required("view_board")
def api_board():
    data = board_data()
    return jsonify({
        "stages": get_stage_names(),
        "delivery_modes": list(DELIVERY_MODES),
        "alert_titles": ALERT_TYPE_TITLES,
        "columns": {stage: [_card(p) for p in cards] for stage, cards in data["columns"].items()},
        "alerts": {key: [{"id": p["id"], "name": p["name"]} for p in items] for key, items in data["alerts"].items()},
        "real_alerts": {key: len(items) for key, items in data["real_alerts"].items()},
        "dashboard": data["dashboard"],
        "recent_notes": [
            {"id": n["id"], "author": n["author"], "project_id": n["project_id"], "project_name": n["project_name"],
             "stage": n["stage"], "created_at": n["created_at"], "note": n["note"]}
            for n in data["recent_notes"]
        ],
        "banner_names": BANNER_NAMES,
        "column_cards": COLUMN_CARDS,
        "can_move": role_has_permission(session.get("role"), "edit_project_stage"),
    })


@app.route("/api/projects/<int:project_id>/approvals/<int:approval_id>", methods=["POST"])
@login_required
def api_approval_decide(project_id, approval_id):
    body = request.get_json(silent=True) or {}
    error = decide_approval(project_id, approval_id, body.get("decision"), body.get("comment"))
    if error:
        return jsonify(error=error), 400
    return jsonify(ok=True)


@app.route("/api/settings")
@permission_required("manage_settings")
def api_settings():
    """The settings page: stage templates, document categories, alert types,
    the Microsoft 365 connection and the integration toggles. Teams and
    channels are listed only when connected (and channels only for the
    ?team_id asked for): each is a Graph round trip."""
    import graph
    from constants import ALERT_TYPE_TITLES as TITLES, DEFAULT_ALERT_TYPE_SETTINGS
    from db import get_setting
    from services import stages as stage_ops
    from services.alerts import get_alert_type_settings
    db = get_db()
    templates = [
        {"id": t["id"], "name": t["name"],
         "stages": [{"id": s["id"], "name": s["name"], "sla_days": s["sla_days"]} for s in stage_ops.list_stages("template", t["id"])],
         "projects": db.execute("SELECT COUNT(*) FROM projects WHERE stage_template_id = ? AND deleted_at IS NULL", (t["id"],)).fetchone()[0]}
        for t in db.execute("SELECT * FROM stage_templates ORDER BY id").fetchall()
    ]
    cfg = get_alert_type_settings()
    alerts = [{"key": k, "title": title, **(cfg.get(k) or {kk: bool(v) if kk.startswith("notify") else v for kk, v in DEFAULT_ALERT_TYPE_SETTINGS[k].items()})}
              for k, title in TITLES.items()]
    connection = graph.get_connection()
    connected = bool(connection and connection["refresh_token"])
    teams, channels, teams_error = [], [], None
    team_id = request.args.get("team_id", "")
    if connected:
        teams, teams_error = graph.list_joined_teams()
        if team_id:
            channels, teams_error = graph.list_channels(team_id)
    return jsonify({
        "templates": templates,
        "doc_categories": [{"id": r["id"], "name": r["name"]} for r in db.execute("SELECT * FROM doc_categories ORDER BY name")],
        "alerts": alerts,
        "m365": {
            "oauth_client_configured": graph.oauth_client_configured(),
            "azure_app": graph.azure_app_credentials(),
            "connected": connected,
            "connected_email": connection["connected_email"] if connected else None,
            "team_name": connection["team_name"] if connected else None,
            "channel_name": connection["channel_name"] if connected else None,
            "channel_id": connection["channel_id"] if connected else None,
            "teams": teams, "channels": channels, "team_id": team_id, "teams_error": teams_error,
        },
        "toggles": {**{k: get_setting(k) == "1" for k in ("notify_email_enabled", "notify_teams_enabled", "onedrive_mirror_uploads_enabled", "onedrive_backup_enabled")},
                    "guest_links_enabled": get_setting("guest_links_enabled", "1") == "1"},
    })


@app.route("/api/settings/rbac")
@permission_required("manage_settings")
def api_settings_rbac():
    """The role/permission matrix. Locked cells are what the save route
    forces on regardless: an admin can never lock every account out."""
    rows = get_db().execute("SELECT * FROM role_permissions").fetchall()
    allowed = {(r["permission"], r["role"]) for r in rows if r["allowed"]}
    return jsonify(
        roles=list(ROLES), permissions=list(PERMISSIONS),
        matrix={p: {r: (p, r) in allowed for r in ROLES} for p in PERMISSIONS},
        locked={p: ["Admin"] if (p in ("manage_settings", "manage_users") or p.startswith("view_")) else [] for p in PERMISSIONS},
    )


@app.route("/api/settings/contacts")
@permission_required("manage_contacts")
def api_settings_contacts():
    db = get_db()
    managers = {}
    for m in db.execute("SELECT * FROM partner_account_managers WHERE deleted_at IS NULL ORDER BY name"):
        managers.setdefault(m["partner_id"], []).append({"id": m["id"], "name": m["name"], "email": m["email"]})
    return jsonify(
        lists=[{"key": key, "label": meta["label"], "has_email": meta["has_email"],
                "items": [{"id": r["id"], "name": r["name"], "email": r["email"] if meta["has_email"] else None}
                          for r in db.execute(f"SELECT * FROM {meta['table']} WHERE deleted_at IS NULL ORDER BY name")]}
               for key, meta in CONTACT_LISTS.items()],
        partners=[{"id": p["id"], "name": p["name"], "managers": managers.get(p["id"], [])}
                  for p in db.execute("SELECT * FROM partners WHERE deleted_at IS NULL ORDER BY name")],
    )


@app.route("/api/users")
@permission_required("manage_users")
def api_users():
    rows = get_db().execute(
        "SELECT id, username, name, email, role, active, kind, last_login_at, created_at FROM users ORDER BY name"
    ).fetchall()
    return jsonify(users=[dict(r) | {"active": bool(r["active"])} for r in rows], roles=list(ROLES), me=session["user_id"])


@app.route("/api/audit")
@permission_required("manage_settings")
def api_audit():
    """The audit viewer's data: same filter helper as the Jinja page and the
    CSV export, so all three answer the same query."""
    from routes.settings import _audit_filter
    db = get_db()
    where, params, filters = _audit_filter()
    limit = 100
    page = max(1, request.args.get("page", 1, type=int))
    total = db.execute(f"SELECT COUNT(*) AS c FROM audit_logs{where}", params).fetchone()["c"]
    total_pages = max(1, (total + limit - 1) // limit)
    page = min(page, total_pages)
    rows = db.execute(f"SELECT * FROM audit_logs{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?", (*params, limit, (page - 1) * limit)).fetchall()
    return jsonify(
        rows=[dict(r) for r in rows], page=page, total=total, total_pages=total_pages, filters=filters,
        usernames=[r[0] for r in db.execute("SELECT DISTINCT username FROM audit_logs ORDER BY username")],
        actions=[r[0] for r in db.execute("SELECT DISTINCT action FROM audit_logs ORDER BY action")],
        projects=[{"id": r["id"], "name": r["name"]} for r in db.execute("SELECT id, name FROM projects ORDER BY name")],
    )


@app.route("/api/reports/all")
@permission_required("view_reports")
def api_report_all():
    rows = get_db().execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE {PROJECT_OPEN_SQL} AND p.deleted_at IS NULL{project_scope()[0]} ORDER BY p.client, p.name", project_scope()[1],
    ).fetchall()
    return jsonify(generated_at=datetime.utcnow().isoformat(), rows=[
        {k: p[k] for k in ("id", "name", "client", "stage", "owner_name", "delivery_mode", "vendor_name", "product_name", "target_end_date")} for p in rows])


@app.route("/api/projects/<int:project_id>/report")
@permission_required("view_reports")
def api_report(project_id):
    c = report_context(project_id)
    return jsonify(
        project={"id": c["project"]["id"], "name": c["project"]["name"], "client": c["project"]["client"], "owner_name": c["project"]["owner_name"], "stage": c["project"]["stage"]},
        versions=[{"version": v["version"], "created_by": v["created_by"], "created_at": v["created_at"]} for v in c["versions"]],
        current=None if c["current"] is None else {"version": c["current"]["version"], "created_by": c["current"]["created_by"], "created_at": c["current"]["created_at"]},
        blocks=c["blocks"], editor_text=c["editor_text"], can_edit=c["can_edit"], is_draft=c["is_draft"],
    )


@app.route("/api/account")
@login_required
def api_account():
    u = get_db().execute("SELECT username, name, email, kind, must_change_password FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return jsonify(username=u["username"], name=u["name"], email=u["email"], kind=u["kind"], must_change_password=bool(u["must_change_password"]))


@app.route("/api/my-work")
@login_required
def api_my_work():
    db = get_db()
    uid = session["user_id"]
    today = date.today().isoformat()
    owned = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE p.owner_id = ? AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{project_scope()[0]} ORDER BY p.updated_at DESC",
        (uid, *project_scope()[1]),
    ).fetchall()
    tasks = db.execute(
        "SELECT t.*, p.name AS project_name FROM tasks t JOIN projects p ON p.id = t.project_id "
        f"WHERE t.assignee_id = ? AND t.done = 0 AND p.deleted_at IS NULL{project_scope()[0]} "
        "ORDER BY t.due_date IS NULL, t.due_date ASC, t.id ASC", (uid, *project_scope()[1]),
    ).fetchall()
    return jsonify(
        tasks=[{"id": t["id"], "title": t["title"], "project_id": t["project_id"], "project_name": t["project_name"], "due_date": t["due_date"],
                "overdue": bool(t["due_date"] and t["due_date"] < today), "stage": t["stage"]} for t in tasks],
        projects=[{"id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"], "schedule": schedule_status(p),
                   "target_end_date": p["target_end_date"]} for p in owned],
    )


@app.route("/api/alerts")
@login_required
def api_alerts():
    d = alerts_page_data()
    return jsonify(
        rows=[{"id": a["id"], "project_id": a["project_id"], "project_name": a["project_name"], "alert_type": a["alert_type"], "severity": a["severity"],
               "title": a["title"], "description": a["description"], "created_at": a["created_at"], "resolved": bool(a["resolved"]), "resolved_at": a["resolved_at"]}
              for a in d["alerts"]],
        show_resolved=d["show_resolved"], alert_type=d["alert_type"], types=d["alert_type_titles"],
        page=d["page"], total_pages=d["total_pages"], total=d["total"],
    )


@app.route("/api/analytics")
@permission_required("view_reports")
def api_analytics():
    from services.analytics import build_cycle_times
    db = get_db()
    templates = db.execute("SELECT id, name FROM stage_templates ORDER BY id").fetchall()
    template_id = request.args.get("template", type=int) or (templates[0]["id"] if templates else None)
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE p.deleted_at IS NULL AND p.stage_template_id IS ?{project_scope()[0]}", (template_id, *project_scope()[1])
    ).fetchall()
    notes = {}
    for n in db.execute("SELECT project_id, stage, created_at FROM status_notes ORDER BY created_at"):
        notes.setdefault(n["project_id"], []).append(n)
    rows = db.execute("SELECT name, sla_days FROM stage_template_stages WHERE template_id = ? ORDER BY position", (template_id,)).fetchall() if template_id else []
    names = [r["name"] for r in rows]
    stats = build_cycle_times(projects, notes, names, names[-1]) if names else None
    return jsonify(
        templates=[{"id": t["id"], "name": t["name"]} for t in templates], template_id=template_id,
        slas={r["name"]: r["sla_days"] for r in rows},
        custom_count=db.execute("SELECT COUNT(*) FROM projects WHERE deleted_at IS NULL AND stage_template_id IS NULL").fetchone()[0],
        stats=None if stats is None else {
            "stages": stats["stages"],
            "aging": [{"project_id": a["project"]["id"], "project_name": a["project"]["name"], "stage": a["stage"], "days": a["days"]} for a in stats["aging"][:12]],
            "slowest": stats["slowest"], "lead_avg": stats["lead_avg"], "lead_median": stats["lead_median"],
            "completed_count": stats["completed_count"], "throughput": stats["throughput"], "measured_projects": stats["measured_projects"],
        },
    )


@app.route("/api/project-form")
@permission_required("view_projects")
def api_project_form():
    """What the new / duplicate / edit project form needs: the pick-lists,
    templates, users, and the record being edited or copied. ?edit=<id>
    needs manage_project on that project; otherwise create_project."""
    from db import get_contact_lists
    db = get_db()
    edit_id, from_id = request.args.get("edit", type=int), request.args.get("from", type=int)
    role = session.get("role")
    if edit_id:
        if not project_allows(edit_id, "manage_project"):
            abort(403)
        source, mode = load_project(edit_id), "edit"
    else:
        if not role_has_permission(role, "create_project"):
            abort(403)
        # only a project you may see can be copied; a stale link just gives a blank form
        source = None
        if from_id and get_db().execute("SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL", (from_id,)).fetchone():
            source = load_project(from_id)
        mode = "duplicate" if source else "new"
    lists = get_contact_lists()
    fields = ["name", "client", "via", "account_manager_name", "account_manager_email", "partner_name", "partner_account_manager_name",
              "partner_account_manager_email", "po_number", "po_date", "start_date", "target_end_date", "delivery_mode",
              "vendor_name", "product_name", "outsourcer_name", "outsourcer_email"]
    project = {f: source[f] for f in fields} if source else {}
    if source:
        project.update({"customer_approval": bool(source["customer_approval"]), "stage_template_id": source["stage_template_id"], "owner_id": source["owner_id"]})
        if mode == "duplicate":
            project["name"] = f"{source['name']} (copy)"
    return jsonify({
        "mode": mode, "id": edit_id, "project": project, "me": session["user_id"],
        "via_options": list(VIA_OPTIONS), "delivery_modes": list(DELIVERY_MODES),
        "account_managers": [{"name": r["name"], "email": r["email"]} for r in lists["account_managers"]],
        "partners": [{"id": p["id"], "name": p["name"], "managers": lists["partner_managers_by_partner"].get(str(p["id"]), [])} for p in lists["partners"]],
        "vendors": [r["name"] for r in lists["vendors"]], "products": [r["name"] for r in lists["products"]],
        "outsourcers": [{"name": r["name"], "email": r["email"]} for r in lists["outsourcers"]],
        "templates": [{"id": t["id"], "name": t["name"]} for t in db.execute("SELECT id, name FROM stage_templates ORDER BY name")],
        "users": [{"id": u["id"], "name": u["name"]} for u in db.execute("SELECT id, name FROM users WHERE active = 1 AND kind = 'internal' ORDER BY name")],
    })


@app.route("/api/projects")
@permission_required("view_projects")
def api_projects():
    """The projects list: same filters, sort, search, paging and scope as the
    Jinja page (one query builder), rows carrying their own stage list."""
    args = request.args
    sort = args.get("sort", DEFAULT_SORT)
    sort = sort if sort in SORT_COLUMNS else DEFAULT_SORT
    direction = "asc" if args.get("dir") == "asc" else "desc"
    view, stage, mode = args.get("view", ""), args.get("stage", ""), args.get("delivery_mode", "")
    closed, q = args.get("closed") == "1", args.get("q", "").strip()
    page = max(1, args.get("page", 1, type=int))
    # the nav's Projects link returns to this filter (page deliberately not kept)
    session["projects_query"] = {k: v for k, v in args.items() if k in ("view", "stage", "delivery_mode", "closed", "q", "sort", "dir") and v}
    db = get_db()
    query, params = filtered_projects_query(view, stage, closed, mode, q, sort, direction)
    total = db.execute(f"SELECT COUNT(*) AS c FROM ({query})", params).fetchone()["c"]
    total_pages = max(1, (total + PROJECTS_PER_PAGE - 1) // PROJECTS_PER_PAGE)
    page = min(page, total_pages)
    rows = db.execute(query + " LIMIT ? OFFSET ?", (*params, PROJECTS_PER_PAGE, (page - 1) * PROJECTS_PER_PAGE)).fetchall()
    lists = stages_for_projects([r["id"] for r in rows])
    scope_sql, scope_params = project_scope()
    stage_names = [r[0] for r in db.execute(
        f"SELECT DISTINCT p.stage FROM projects p WHERE p.deleted_at IS NULL{scope_sql} ORDER BY p.stage", scope_params)]
    out = []
    for r in rows:
        names = [s["name"] for s in (lists.get(r["id"]) or [])]
        out.append({
            "id": r["id"], "name": r["name"], "client": r["client"], "po_number": r["po_number"], "stage": r["stage"],
            "stages": names, "stage_index": names.index(r["stage"]) if r["stage"] in names else 0,
            "closed": bool(names) and r["stage"] == names[-1],
            "owner_name": r["owner_name"], "delivery_mode": r["delivery_mode"], "vendor_name": r["vendor_name"],
            "product_name": r["product_name"], "target_end_date": r["target_end_date"], "updated_at": r["updated_at"],
        })
    return jsonify(rows=out, total=total, page=page, total_pages=total_pages, sort=sort, dir=direction,
                   stages=stage_names, delivery_modes=list(DELIVERY_MODES),
                   can_create=role_has_permission(session.get("role"), "create_project"))


@app.route("/api/projects/<int:project_id>")
@permission_required("view_project_detail")
def api_project(project_id):
    """Everything the project page shows beyond the flow detail: the record,
    guest links, the editable stage list, team, notes, documents, and what
    this session may do. Mutations go to the existing form routes."""
    db = get_db()
    project = load_project(project_id)
    role = session.get("role")
    fields = ["client", "via", "partner_name", "partner_account_manager_name", "partner_account_manager_email",
              "account_manager_name", "account_manager_email", "po_number", "po_date", "start_date", "target_end_date",
              "delivery_mode", "outsourcer_name", "outsourcer_email", "vendor_name", "product_name"]
    can_manage = project_allows(project_id, "manage_project")
    from db import get_setting
    guest_on = get_setting("guest_links_enabled", "1") == "1"
    return jsonify({
        "id": project["id"], "name": project["name"], "owner_id": project["owner_id"],
        "guest_links_enabled": guest_on,
        "details": {f: project[f] for f in fields},
        "customer_approval": bool(project["customer_approval"]),
        "guest_links": {
            "customer": url_for("guest_view", token=project["customer_token"], _external=True) if project["customer_token"] else None,
            "vendor": url_for("guest_view", token=project["access_token"], _external=True)
            if project["delivery_mode"] == "Outsourced" and project["access_token"] else None,
        } if guest_on and (can_manage or role != "External") else {"customer": None, "vendor": None},
        "stage_rows": [{"id": r["id"], "name": r["name"], "sla_days": r["sla_days"]} for r in stage_rows(project_id)],
        "participants": [{"id": r["id"], "user_id": r["user_id"], "name": r["name"], "role": r["role"], "email": r["email"], "active": bool(r["active"])}
                         for r in participants_for(project_id)],
        "notes": [{"id": n["id"], "author": n["author"], "note": n["note"], "stage": n["stage"], "created_at": n["created_at"]}
                  for n in db.execute("SELECT * FROM status_notes WHERE project_id = ? ORDER BY created_at DESC", (project_id,))],
        "documents": [{"id": d["id"], "category": d["category"], "filename": d["filename"], "uploaded_by": d["uploaded_by"], "uploaded_at": d["uploaded_at"]}
                      for d in db.execute("SELECT * FROM documents WHERE project_id = ? AND deleted_at IS NULL ORDER BY uploaded_at DESC", (project_id,))],
        "doc_categories": get_doc_category_names(),
        "users": [{"id": u["id"], "name": u["name"]} for u in db.execute("SELECT id, name FROM users WHERE active = 1 AND kind = 'internal' ORDER BY name")] if can_manage else [],
        "roles": [r for r in PROJECT_ROLES if r != PROJECT_MANAGER], "external_roles": list(EXTERNAL_PROJECT_ROLES),
        "can": {
            "manage": can_manage, "tasks": project_allows(project_id, "manage_tasks"),
            "docs": project_allows(project_id, "manage_documents"), "move": project_allows(project_id, "move_stage"),
            "note": role_has_permission(role, "add_project_note"), "download": role_has_permission(role, "download_document"),
            "create": role_has_permission(role, "create_project"),
        },
    })


# How the activity feed words each audit action. Anything not listed shows
# as the action name with underscores dropped, so a new action needs no edit
# here to appear.
ACTIVITY_LABELS = {
    "create_project": "created the project", "update_project": "edited the project", "update_project_stage": "moved the stage",
    "add_project_note": "added a note", "add_task": "added a task", "edit_task": "edited a task", "toggle_task": "ticked or reopened a task",
    "delete_task": "removed a task", "upload_document": "uploaded a document", "delete_document": "removed a document",
    "add_participant": "added someone to the team", "invite_participant": "invited a partner", "remove_participant": "removed someone from the team",
    "approval_decision": "recorded the customer's decision", "save_report": "saved a report version",
    "add_project_stage": "added a stage", "rename_project_stage": "renamed a stage", "move_project_stage": "reordered the stages",
    "delete_project_stage": "removed a stage", "update_project_slas": "changed the stage SLAs", "rotate_guest_token": "rotated the guest links",
    "delete_project": "deleted the project", "restore_project": "restored the project",
}


@app.route("/api/projects/<int:project_id>/activity")
@permission_required("view_project_detail")
def api_project_activity(project_id):
    """What happened on this project, newest first, for staff who do not
    read their email. It is the audit trail's own rows for the project, so
    nothing is recorded twice. External accounts get the customer-visible
    notes instead (their view of history), never the trail."""
    load_project(project_id)
    if session.get("kind") == "external":
        return jsonify(rows=[])
    rows = get_db().execute(
        "SELECT timestamp, username, action, details FROM audit_logs WHERE resource_type = 'project' AND resource_id = ? "
        "ORDER BY id DESC LIMIT 60", (project_id,),
    ).fetchall()
    return jsonify(rows=[{
        "when": r["timestamp"], "who": r["username"], "action": r["action"],
        "label": ACTIVITY_LABELS.get(r["action"], r["action"].replace("_", " ")),
        "details": (r["details"] or "").replace("stage=", "to ") if r["action"] == "update_project_stage" else (r["details"] or ""),
    } for r in rows])


@app.route("/projects/<int:project_id>/activity.csv")
@permission_required("view_project_detail")
def project_activity_export(project_id):
    """The same rows as the feed, as a file for an evidence pack. Staff only;
    the export is itself an audited action, like the other exports."""
    import csv
    import io
    from flask import Response
    project = load_project(project_id)
    if session.get("kind") == "external":
        abort(403)
    rows = get_db().execute(
        "SELECT timestamp, username, action, details FROM audit_logs WHERE resource_type = 'project' AND resource_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["timestamp_utc", "who", "action", "what", "details"])
    for r in rows:
        writer.writerow([r["timestamp"], r["username"], r["action"], ACTIVITY_LABELS.get(r["action"], r["action"].replace("_", " ")), r["details"] or ""])
    audit_log("export_project_activity", "project", project_id, project["name"], f"{len(rows)} rows")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in project["name"])[:60] or "project"
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=odin-activity-{safe}.csv"})


@app.route("/api/projects/<int:project_id>/stage", methods=["POST"])
@permission_required("edit_project_stage")
@project_role_required("move_stage")
def api_project_stage(project_id):
    load_project(project_id)
    data = request.get_json(silent=True) or {}
    # change_stage audits and notifies; this is the same door the form uses.
    error = change_stage(project_id, data.get("stage", ""), (data.get("note") or "").strip()[:5000])
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/alerts/<int:project_id>/dismiss/<alert_type>", methods=["POST"])
@login_required
def api_alert_dismiss(project_id, alert_type):
    load_project(project_id)
    dismiss_alert(project_id, alert_type)
    audit_log("dismiss_alert", "project", project_id, None, alert_type)
    return jsonify({"ok": True})


# ---- Flow: the first screen. Every active rollout, stuck first; then one
# rollout's stage flow with tasks, next action, ETA and timeline. -------------

STATE_RANK = {"overdue": 0, "over_sla": 1, "due_soon": 2, "on_track": 3}


def _flow_state(project, sla, schedule):
    if schedule == "overdue":
        return "overdue"
    if sla and sla["breached"]:
        return "over_sla"
    if schedule == "at_risk":
        return "due_soon"
    return "on_track"


def _days_since(iso, now):
    parsed = _parse(iso) if iso else None
    return round((now - parsed).total_seconds() / 86400, 1) if parsed else None


@app.route("/api/flow")
@permission_required("view_board")
def api_flow():
    db = get_db()
    now = datetime.utcnow()
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.done = 0) AS open_tasks, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id) AS total_tasks "
        "FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{project_scope()[0]} ORDER BY p.updated_at DESC",
        project_scope()[1],
    ).fetchall()
    stage_lists = stages_for_projects([p["id"] for p in projects])
    mine = my_project_ids(session["user_id"])
    # latest approval per project, only meaningful for the current stage
    approvals = {}
    for r in db.execute(
        "SELECT a.project_id, a.stage, a.status FROM stage_approvals a "
        "WHERE a.id = (SELECT MAX(id) FROM stage_approvals WHERE project_id = a.project_id)"
    ):
        approvals[r["project_id"]] = r
    team = {}   # project_id -> participant names, PM first (avatars on the row)
    for r in db.execute(
        "SELECT pp.project_id, u.name FROM project_participants pp JOIN users u ON u.id = pp.user_id "
        "WHERE u.active = 1 ORDER BY CASE pp.role WHEN 'Project manager' THEN 0 ELSE 1 END, u.name"
    ):
        team.setdefault(r["project_id"], []).append(r["name"])
    # Earliest-due open task per project = the next actionable item.
    next_task = {}
    for t in db.execute(
        "SELECT t.project_id, t.title, t.due_date, u.name AS assignee_name FROM tasks t "
        "LEFT JOIN users u ON u.id = t.assignee_id WHERE t.done = 0 "
        "ORDER BY t.due_date IS NULL, t.due_date, t.id"
    ):
        next_task.setdefault(t["project_id"], {"title": t["title"], "due_date": t["due_date"], "assignee": t["assignee_name"]})
    rows = []
    for p in projects:
        own = stage_lists.get(p["id"]) or []
        stages = [r["name"] for r in own]
        terminal = stages[-1] if stages else None
        slas = sla_by_stage(own)
        sla = stage_sla_state(p, slas, terminal, now)
        schedule = schedule_status(p, terminal_stage=terminal)
        state = _flow_state(p, sla, schedule)
        rows.append({
            "id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"],
            "stages": stages, "mine": p["id"] in mine, "team": team.get(p["id"], [p["owner_name"]]),
            "approval": (approvals[p["id"]]["status"] if p["id"] in approvals and approvals[p["id"]]["stage"] == p["stage"] else None),
            "stage_index": stages.index(p["stage"]) if p["stage"] in stages else 0,
            "owner_name": p["owner_name"], "delivery_mode": p["delivery_mode"],
            "target_end_date": p["target_end_date"], "days_in_stage": _days_since(p["stage_entered_at"], now),
            "sla_days": slas.get(p["stage"]), "over_by": round(sla["over_by"], 1) if sla else None,
            "state": state, "open_tasks": p["open_tasks"], "total_tasks": p["total_tasks"],
            "next_task": next_task.get(p["id"]), "updated_at": p["updated_at"],
        })
    rows.sort(key=lambda r: (STATE_RANK[r["state"]], r["updated_at"] or ""), reverse=False)
    # inside each state, most recently touched first
    rows.sort(key=lambda r: (STATE_RANK[r["state"]], -(_parse(r["updated_at"]) or now).timestamp()))
    counts = {k: sum(1 for r in rows if r["state"] == k) for k in STATE_RANK}
    return jsonify({"stages": get_stage_names(), "rows": rows, "counts": counts,
                    "can_move": role_has_permission(session.get("role"), "edit_project_stage")})


@app.route("/api/projects/<int:project_id>/flow")
@permission_required("view_project_detail")
def api_project_flow(project_id):
    db = get_db()
    project = load_project(project_id)
    stages, terminal = get_stage_names(project_id), get_terminal_stage(project_id)
    slas = sla_for_project(project_id)
    now = datetime.utcnow()
    notes = db.execute("SELECT * FROM status_notes WHERE project_id = ? ORDER BY created_at", (project_id,)).fetchall()
    timeline = stage_timeline(project, notes, stages[0])
    # Dwell per stage: the last visit's span (a stage can be revisited; the
    # latest visit is what the current SLA measures).
    visits = {}
    for i, (stage, entered) in enumerate(timeline):
        left = timeline[i + 1][1] if i + 1 < len(timeline) else now
        visits[stage] = {"entered_at": entered.isoformat(), "days": round((left - entered).total_seconds() / 86400, 1)}
    current = stages.index(project["stage"]) if project["stage"] in stages else 0
    # The current stage's clock is stage_entered_at (what change_stage sets and
    # the SLA measures); the note history can lag it, e.g. after a backdate.
    entered_now = _parse(project["stage_entered_at"]) if project["stage_entered_at"] else None
    if entered_now and project["stage"] in stages:
        visits[project["stage"]] = {"entered_at": entered_now.isoformat(), "days": round((now - entered_now).total_seconds() / 86400, 1)}
    stage_rows = []
    for i, name in enumerate(stages):
        status = "done" if i < current else "current" if i == current else "next"
        stage_rows.append({"name": name, "status": status, "sla_days": slas.get(name),
                           **(visits.get(name) or {"entered_at": None, "days": None})})
    tasks = db.execute(
        "SELECT t.*, u.name AS assignee_name FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id "
        "WHERE t.project_id = ? ORDER BY t.done, t.due_date IS NULL, t.due_date, t.id", (project_id,),
    ).fetchall()
    sla = stage_sla_state(project, slas, terminal, now)
    schedule = schedule_status(project, terminal_stage=terminal)
    target = date.fromisoformat(project["target_end_date"]) if project["target_end_date"] else None
    start = project["start_date"] or project["created_at"][:10]
    return jsonify({
        "id": project["id"], "name": project["name"], "client": project["client"],
        "vendor_name": project["vendor_name"], "product_name": project["product_name"],
        "delivery_mode": project["delivery_mode"], "outsourcer_name": project["outsourcer_name"],
        "owner_name": project["owner_name"], "stage": project["stage"], "stage_index": current,
        "next_stage": stages[current + 1] if current + 1 < len(stages) else None,
        "state": _flow_state(project, sla, schedule), "over_by": round(sla["over_by"], 1) if sla else None,
        "start_date": start, "target_end_date": project["target_end_date"],
        "days_left": (target - date.today()).days if target else None,
        "today": date.today().isoformat(),
        "stages": stage_rows,
        # a task without a stage belongs to whatever stage the project is in
        "tasks": [{"id": t["id"], "title": t["title"], "done": bool(t["done"]), "due_date": t["due_date"],
                   "assignee": t["assignee_name"], "assignee_id": t["assignee_id"],
                   "stage": t["stage"] if t["stage"] in stages else project["stage"]} for t in tasks],
        "assignable": [{"id": r["user_id"], "name": r["name"]} for r in participants_for(project_id) if r["active"]],
        "can_edit": project_allows(project_id, "manage_tasks"),
        "me": session["user_id"],
        "documents": db.execute("SELECT COUNT(*) AS c FROM documents WHERE project_id = ? AND deleted_at IS NULL", (project_id,)).fetchone()["c"],
        "recent_notes": [{"author": n["author"], "note": n["note"], "stage": n["stage"], "created_at": n["created_at"]} for n in notes[-4:][::-1]],
        "participants": [{"id": r["id"], "user_id": r["user_id"], "name": r["name"], "role": r["role"]} for r in participants_for(project_id)],
        "can_move": project_allows(project_id, "move_stage"),
        "customer_approval": bool(project["customer_approval"]),
        "approval": ({"id": a["id"], "stage": a["stage"], "status": a["status"], "decided_by": a["decided_by"], "comment": a["comment"]}
                     if (a := current_approval(project_id)) else None),
        "can_approve": is_customer_on(project_id, session["user_id"]),
    })


@app.route("/assets/<path:filename>")
def spa_assets(filename):
    return spa_asset(filename)
