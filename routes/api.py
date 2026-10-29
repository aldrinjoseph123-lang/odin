"""JSON API for the React front end. Same session cookie, same CSRF token
(sent as X-CSRF-Token), same decorators and audit trail as the HTML routes —
the API is a second door into the same rooms, not a second house.
"""
from flask import abort, g, jsonify, request, session

from policies import local_today, policy, policy_view

from datetime import date, datetime

from constants import CONTACT_LISTS, DEFAULT_ALERT_TYPE_SETTINGS, DELIVERY_MODES, EXTERNAL_PROJECT_ROLES, PERMISSIONS, PROJECT_MANAGER, PROJECT_ROLES, ROLES, VIA_OPTIONS
from core import app, as_id, json_body, like_any, sees_po, text_field, login_required, nav_counts, permission_required, project_allows, project_role_required, project_scope, role_has_permission
from db import avatar_url, get_doc_category_names, get_setting, partner_hidden_categories, project_role_of, stage_rows
from db import PROJECT_CLOSED_SQL, PROJECT_OPEN_SQL, current_approval, customer_ids, get_db, touch_project, get_stage_names, get_terminal_stage, is_customer_on, my_project_ids, participants_for, sla_for_project, stages_for_projects
from routes.auth import MFA_NEEDED, attempt_login
from routes.board import alerts_page_data
from routes.projects import DEFAULT_SORT, PROJECTS_PER_PAGE, SORT_COLUMNS, StageConflict, change_stage, decide_approval, filtered_projects_query, leads, load_project, stage_entry_note_ids
from security import csrf_token, file_stem, nudge_limited, safe_csv_writer
from services.alerts import get_alert_type_settings, schedule_status
from services.analytics import _parse, clock, days_in_stage, sla_by_stage, stage_sla_state, stage_timeline, working_days
from services.audit import audit_log
from services.fmt import plural
from services import signoff as signoff_service
from services import fields as custom_fields
from services import gates
from services.activity import enabled as activity_enabled, summary as activity_summary
from services.notifications import watch_state
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
    # Same test every protected route applies: a session ended elsewhere
    # (deactivation, password reset, "sign out of other devices", age) is
    # not signed in here either, or the shell would render and then bounce.
    from core import _session_still_valid
    from flask import flash
    if not _session_still_valid():
        session.clear()
        flash("Your session has ended — please sign in again")
        return None
    me = get_db().execute("SELECT id, theme, accent, avatar, home FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return {
        "id": session["user_id"],
        "name": session.get("user_name"),
        "theme": me["theme"] if me else "system", "accent": me["accent"] if me else "blue",
        "avatar_url": avatar_url(me) if me else None,
        "role": session.get("role"),
        "kind": session.get("kind", "internal"),
        # an external's project role, for the header badge: "Customer" when they
        # are the customer on any open project, else their first role
        "external_role": _external_role(session["user_id"]) if session.get("kind") == "external" else None,
        # where sign-in and the logo land; partners always get the flow
        "home": "board" if session.get("kind") == "external" or not me or me["home"] == "board" else "dashboard",
        "must_change_password": bool(session.get("must_change_password")),
        "must_enroll_mfa": bool(session.get("must_enroll_mfa")),
        "permissions": _permissions_for(session.get("role")),
        "nav": nav_counts(),
        # workspace-wide display choices from Settings › General
        "prefs": {"date_format": policy("date_format"), "undo_minutes": policy("undo_minutes"),
                  "password_min_length": policy("password_min_length"),
                  "activity_idle_minutes": policy("activity_idle_minutes") if policy("activity_tracking") else 0},
    }


def _external_role(user_id):
    roles = [r["role"] for r in get_db().execute(
        "SELECT pp.role FROM project_participants pp JOIN projects p ON p.id = pp.project_id "
        "WHERE pp.user_id = ? AND p.deleted_at IS NULL ORDER BY pp.id", (user_id,))]
    return "Customer" if "Customer" in roles else (roles[0] if roles else None)


@app.route("/api/session")
def api_session():
    """Who am I, what may I do, and the CSRF token every mutation must carry.
    Anonymous callers get the token too — the login form needs it.

    `messages` drains Flask's pending flashes. A route that flashes and then
    redirects to a React page ("Your session has ended", "Set a new password
    before continuing") would otherwise lose the message, or have it surface
    later inside an unrelated reply."""
    from flask import get_flashed_messages
    user = _current_user()
    messages = [str(m) for m in get_flashed_messages()]
    from routes.sso import sso_configured, sso_enforced
    # what the sign-in page offers: Microsoft for staff, and whether the
    # password form is hidden (then only at /login/password, for flagged accounts)
    signin = {"microsoft": sso_configured(), "microsoft_only": sso_enforced(), "link_minutes": policy("link_minutes"),
              "password_min_length": policy("password_min_length")}
    from routes.client import app_version   # the page compares it with the one it loaded with (advice A20)
    # the workspace time zone: the page counts "today" (overdue, late by n days) on the workspace's
    # calendar, as the server does, not on the browser's
    return jsonify({"csrf": csrf_token(), "user": user, "messages": messages, "signin": signin, "version": app_version(),
                    "timezone": policy("timezone")})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = json_body()
    username, password = data.get("username") or "", data.get("password") or ""
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error="Send a username and a password as text"), 400
    ok, message = attempt_login(username.strip(), password)
    if message == MFA_NEEDED:
        return jsonify({"code_needed": True, "csrf": csrf_token()})
    if not ok:
        # attempt_login audits every outcome; 429 when it is the lockout talking.
        if message.startswith("Too many"):
            return jsonify({"error": message}), 429, {"Retry-After": str(60 * policy("login_window_minutes"))}
        return jsonify({"error": message}), 401
    # attempt_login cleared the session (fixation defence), so the token rotated.
    return jsonify({"user": _current_user(), "csrf": csrf_token()})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    from core import end_session
    end_session()
    return jsonify({"ok": True, "csrf": csrf_token()})


@app.route("/api/projects/<int:project_id>/approvals/<int:approval_id>", methods=["POST"])
@login_required
def api_approval_decide(project_id, approval_id):
    body = json_body()
    if body.get("comment") is not None and not isinstance(body.get("comment"), str):
        return jsonify(error="Send the comment as text"), 400
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
    from services import stages as stage_ops
    from services.alerts import get_alert_type_settings
    db = get_db()
    templates = [
        {"id": t["id"], "name": t["name"],
         "stages": [{"id": s["id"], "name": s["name"], "sla_days": s["sla_days"], "gate_tasks": bool(s["gate_tasks"]), "required_docs": gates.required_docs(s)}
                    for s in stage_ops.list_stages("template", t["id"])],
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
    # Teams are fetched from Microsoft only for the Integrations area; every
    # other settings area loads without a network round trip.
    if connected and request.args.get("section") in (None, "integrations"):
        teams, teams_error = graph.list_joined_teams()
        if team_id:
            channels, teams_error = graph.list_channels(team_id)
    return jsonify({
        "templates": templates,
        "doc_categories": [{"id": r["id"], "name": r["name"], "partners": bool(r["partners"])} for r in db.execute("SELECT * FROM doc_categories ORDER BY name")],
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
        "policies": policy_view(),
        "sso": _sso_view(),
        "backups": _backups_view() if request.args.get("section") in (None, "backups") else None,
        "api_tokens": [dict(r) for r in db.execute(
            "SELECT id, name, created_by, created_at, expires_at, last_used_at, revoked_at, scope FROM api_tokens WHERE scope = 'read' ORDER BY id DESC LIMIT 100")],
        "audit_archives": _audit_archives(),
        "public_url_set": bool(policy("public_url")),
    })


def _audit_archives():
    import os
    from services.retention import archive_dir
    folder = archive_dir()
    return [{"name": n, "size": os.path.getsize(os.path.join(folder, n))} for n in sorted(os.listdir(folder), reverse=True) if n.endswith(".csv")][:50]


def _backups_view():
    """History, the next scheduled run and whether the scheduler is alive."""
    from datetime import timedelta
    from policies import local_now
    from scheduler import HEARTBEAT, next_run
    db = get_db()
    beat = get_setting(HEARTBEAT)
    alive = bool(beat) and datetime.fromisoformat(beat) > datetime.utcnow() - timedelta(minutes=5)
    upcoming = next_run(local_now(), policy("backup_time"), policy("backup_days"))
    return {
        "runs": [dict(r) | {"ok": bool(r["ok"]), "restore_ok": None if r["restore_ok"] is None else bool(r["restore_ok"])}
                 for r in db.execute("SELECT * FROM backup_runs ORDER BY id DESC LIMIT 20")],
        "scheduler_seen": beat or None, "scheduler_alive": alive,
        "next_run": upcoming.strftime("%a %d %b, %H:%M") if upcoming else None,
    }


def _sso_view():
    from core import external_url
    from routes.sso import sso_config, sso_configured, sso_enforced
    client_id, tenant, secret = sso_config()
    return {"client_id": client_id or None, "tenant_id": tenant or None, "has_secret": bool(secret), "configured": sso_configured(),
            "enforced": sso_enforced(), "redirect_uri": external_url("sso_callback"),
            "password_admins": get_db().execute("SELECT COUNT(*) FROM users WHERE role = 'Admin' AND active = 1 AND password_login = 1").fetchone()[0]}


@app.route("/api/settings/templates/<int:template_id>/tasks", methods=["GET", "PUT"])
@permission_required("manage_settings")
def api_template_tasks(template_id):
    """The tasks a template's stages bring to a new rollout
    (services/template_tasks.py). PUT replaces the whole list; links name
    other items by their key."""
    from services import template_tasks
    db = get_db()
    template = db.execute("SELECT id, name FROM stage_templates WHERE id = ?", (template_id,)).fetchone()
    if template is None:
        abort(404)
    if request.method == "PUT":
        try:
            n = template_tasks.save(template_id, (json_body() or {}).get("tasks"))
        except ValueError as e:
            return jsonify(error=str(e)), 400
        audit_log("update_template_tasks", "stage_template", template_id, template["name"], f"{n} {plural(n, 'task')}")
    return jsonify(tasks=template_tasks.for_template(template_id, db), roles=list(template_tasks.ROLES))


@app.route("/api/settings/rbac")
@permission_required("manage_settings")
def api_settings_rbac():
    """The role/permission matrix. Locked cells are what the save route
    forces on regardless: an admin can never lock every account out."""
    from routes.settings import EXTERNAL_ALLOWED
    rows = get_db().execute("SELECT * FROM role_permissions").fetchall()
    allowed = {(r["permission"], r["role"]) for r in rows if r["allowed"]}
    return jsonify(
        roles=list(ROLES), permissions=list(PERMISSIONS),
        matrix={p: {r: (p, r) in allowed for r in ROLES} for p in PERMISSIONS},
        locked={p: ["Admin"] if (p in ("manage_settings", "manage_users") or p.startswith("view_")) else [] for p in PERMISSIONS},
        # cells the save route refuses to turn on (External is capped to view, comment, download)
        forbidden={p: [] if p in EXTERNAL_ALLOWED else ["External"] for p in PERMISSIONS},
    )


@app.route("/api/settings/contacts")
@permission_required("manage_contacts")
def api_settings_contacts():
    db = get_db()

    def used(*columns):
        # where each entry is used: the live projects that name it (projects keep the name as text)
        found = {}
        for r in db.execute(f"SELECT id, name, {', '.join(columns)} FROM projects WHERE deleted_at IS NULL ORDER BY name"):
            found.setdefault(tuple(r[2:]), []).append({"id": r["id"], "name": r["name"]})
        return found
    by_partner_manager = used("partner_name", "partner_account_manager_name")
    by_partner = used("partner_name")
    partner_rows = db.execute("SELECT * FROM partners WHERE deleted_at IS NULL ORDER BY name").fetchall()
    partner_names = {p["id"]: p["name"] for p in partner_rows}
    managers = {}
    for m in db.execute("SELECT * FROM partner_account_managers WHERE deleted_at IS NULL ORDER BY name"):
        managers.setdefault(m["partner_id"], []).append({"id": m["id"], "name": m["name"], "email": m["email"],
                                                         "used": by_partner_manager.get((partner_names.get(m["partner_id"]), m["name"]), [])})
    lists = []
    for key, meta in CONTACT_LISTS.items():
        counts = used(meta["column"])
        lists.append({"key": key, "label": meta["label"], "has_email": meta["has_email"],
                      "items": [{"id": r["id"], "name": r["name"], "email": r["email"] if meta["has_email"] else None,
                                 "used": counts.get((r["name"],), []), **({"vendor_id": r["vendor_id"]} if key == "products" else {})}
                                for r in db.execute(f"SELECT * FROM {meta['table']} WHERE deleted_at IS NULL ORDER BY name")]})
    return jsonify(
        lists=lists,
        partners=[{"id": p["id"], "name": p["name"], "used": by_partner.get((p["name"],), []), "managers": managers.get(p["id"], [])}
                  for p in partner_rows],
    )


@app.route("/api/users")
@permission_required("manage_users")
def api_users():
    rows = get_db().execute(
        "SELECT u.id, u.username, u.name, u.email, u.role, u.active, u.kind, u.last_login_at, u.created_at, u.avatar, u.pending, u.password_login, u.ms_oid, "
        "u.totp_enabled_at IS NOT NULL AS two_step, u.capacity_hours, l.label AS signup_label, p.name AS signup_project, u.signup_project_role, u.declined_reason FROM users u "
        "LEFT JOIN signup_links l ON l.id = u.signup_link_id LEFT JOIN projects p ON p.id = u.signup_project_id ORDER BY u.name"
    ).fetchall()
    from routes.sso import sso_enforced
    from services.workload import holds
    held = holds(get_db(), [r["id"] for r in rows])   # what a hand-over on leave would move
    from services.access_review import review
    flagged = review(get_db(), policy("access_review_days"))
    return jsonify(users=[{k: r[k] for k in r.keys() if k not in ("avatar", "ms_oid")}
                          | {"active": bool(r["active"]), "pending": bool(r["pending"]), "password_login": bool(r["password_login"]), "two_step": bool(r["two_step"]),
                             "microsoft": r["ms_oid"] is not None, "avatar_url": avatar_url(r), "holds": held[r["id"]], "review": flagged.get(r["id"], [])} for r in rows],
                   roles=list(ROLES), me=session["user_id"], microsoft_only=sso_enforced(), capacity_default=policy("capacity_hours_per_week"),
                   review_days=policy("access_review_days"))


@app.route("/api/audit")
@permission_required("manage_settings")
def api_audit():
    """The audit viewer's data: same filter helper as the Jinja page and the
    CSV export, so all three answer the same query."""
    from routes.settings import _audit_filter
    db = get_db()
    where, params, filters = _audit_filter()
    limit = 100
    page = max(1, request.args.get("page", type=as_id) or 1)
    total = db.execute(f"SELECT COUNT(*) AS c FROM audit_logs{where}", params).fetchone()["c"]
    total_pages = max(1, (total + limit - 1) // limit)
    page = min(page, total_pages)
    rows = db.execute(f"SELECT audit_logs.*, (SELECT u.name FROM users u WHERE u.id = audit_logs.user_id) AS user_name "
                      f"FROM audit_logs{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?", (*params, limit, (page - 1) * limit)).fetchall()
    return jsonify(
        rows=[dict(r) for r in rows], page=page, total=total, total_pages=total_pages, filters=filters,
        # one entry per person: their name, whether the row was written with their name or their sign-in handle
        usernames=[r[0] for r in db.execute(
            "SELECT DISTINCT COALESCE(u.name, a.username) FROM audit_logs a "
            "LEFT JOIN users u ON u.id = a.user_id OR (a.user_id IS NULL AND u.username = a.username) ORDER BY 1")],
        actions=[r[0] for r in db.execute("SELECT DISTINCT action FROM audit_logs ORDER BY action")],
        projects=[{"id": r["id"], "name": r["name"]} for r in db.execute("SELECT id, name FROM projects ORDER BY name")],
    )


def _portfolio():
    from services import portfolio
    rows = get_db().execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE {PROJECT_OPEN_SQL} AND p.deleted_at IS NULL{project_scope()[0]} ORDER BY p.client, p.name", project_scope()[1],
    ).fetchall()
    return portfolio.build(rows, customer=session.get("kind") == "external")


@app.route("/api/reports/all")
@permission_required("view_reports")
def api_report_all():
    from services.doc_templates import resolve
    return jsonify({**_portfolio(), "template": resolve("portfolio", request.args.get("template", type=as_id))})


@app.route("/reports/all.pdf")
@permission_required("view_reports")
def portfolio_pdf():
    """The portfolio report as a PDF: health mix, roadmap, slippage, blockers, every rollout."""
    from flask import Response
    from services.report_pdf import render_portfolio
    if session.get("kind") == "external":
        abort(404)            # the PDF is the internal cut
    from services.doc_templates import resolve
    data = _portfolio()
    audit_log("download_portfolio_report", "report", None, "portfolio", f"{len(data.get('rows') or [])} rollouts")   # an export like the others (P3-17)
    return Response(render_portfolio(data, resolve("portfolio", request.args.get("template", type=as_id))), mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="portfolio-report-{data["today"]}.pdf"'})


def _rollout_report(project_id, audience, version):
    """(words, data, versions, current row or None) for the report page and its PDF.
    Internal readers get live data by default; partners and customers only
    ever see a saved version, cut down to the customer's view."""
    import json
    from services import report_data
    from services.reports import render_blocks
    db = get_db()
    project = load_project(project_id)
    external = session.get("kind") == "external"
    if external:
        audience = "customer"
    versions = [dict(r) for r in db.execute(
        "SELECT version, kind, created_by, created_at FROM project_reports WHERE project_id = ? ORDER BY version DESC", (project_id,))]
    row = None
    if version or external:
        wanted = version or next((v["version"] for v in versions if v["kind"] == "snapshot"), None)
        row = db.execute("SELECT * FROM project_reports WHERE project_id = ? AND version = ?", (project_id, wanted)).fetchone() if wanted else None
        if row is None or (external and row["kind"] != "snapshot"):
            abort(404)
    if row is not None and row["kind"] == "snapshot":
        data = json.loads(row["data"]) if audience == "internal" else report_data.customer_view(row["data"])
        if external and not sees_po(project_id):   # a contractor's copy carries no PO (the snapshot froze it)
            data["project"]["po_number"] = None
        words = {"summary": row["summary"] or "", "next_steps": row["next_steps"] or "", "asks": row["asks"] or ""}
        if audience == "customer":
            words = report_data.customer_words(project_id, words, json.loads(row["data"]))
    elif row is not None:                       # an old plain-text version
        data, words = None, {"blocks": render_blocks(row["body"])}
    else:
        from services.doc_templates import resolve
        data = report_data.build(project, audience)
        data["template"] = resolve("rollout", request.args.get("template", type=as_id))   # a saved version keeps the one it was saved with
        last = db.execute("SELECT summary, next_steps, asks FROM project_reports WHERE project_id = ? AND kind = 'snapshot' ORDER BY version DESC LIMIT 1", (project_id,)).fetchone()
        words = {k: (last[k] if last and last[k] else data["draft"][k]) for k in ("summary", "next_steps", "asks")}
        words["suggested"] = data.pop("draft")
        if audience == "customer":
            words = report_data.customer_words(project_id, words)
    return project, audience, words, data, versions, row


@app.route("/api/projects/<int:project_id>/rollout-report")
@permission_required("view_reports")
def api_rollout_report(project_id):
    audience = request.args.get("audience", "internal")
    audience = audience if audience in ("internal", "customer") else "internal"
    project, audience, words, data, versions, row = _rollout_report(project_id, audience, request.args.get("v", type=as_id))
    external = session.get("kind") == "external"
    return jsonify(audience=audience, words=words, data=data, is_live=row is None,
                   version=None if row is None else {"version": row["version"], "kind": row["kind"], "created_by": row["created_by"], "created_at": row["created_at"]},
                   versions=[v for v in versions if not external or v["kind"] == "snapshot"],
                   can_edit=not external and project_allows(project_id, "manage_project"),
                   project={"id": project["id"], "name": project["name"], "client": project["client"]})


@app.route("/projects/<int:project_id>/report.pdf")
@permission_required("view_reports")
def rollout_report_pdf(project_id):
    """The report as a PDF: the live draft or a saved version, internal or the customer copy."""
    from flask import Response
    from services.report_pdf import render
    audience = request.args.get("audience", "internal")
    project, audience, words, data, _versions, row = _rollout_report(project_id, audience if audience in ("internal", "customer") else "internal", request.args.get("v", type=as_id))
    if data is None:
        abort(404)            # an old plain-text version has no PDF of this kind
    safe = file_stem(project["name"])
    tag = f"-v{row['version']}" if row else ""
    name = f"{safe}-report{tag}{'-customer' if audience == 'customer' else ''}.pdf"
    audit_log("download_report", "project", project_id, project["name"], f"{'v' + str(row['version']) if row else 'live'} {audience}")   # P3-17
    return Response(render(data, words), mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


@app.route("/api/projects/<int:project_id>/rollout-report", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def api_rollout_report_save(project_id):
    """Freeze today's report with the project manager's words as a new version."""
    from services import report_data
    from services.plan import snapshot_json
    project = load_project(project_id)
    body = json_body()
    try:
        words = {k: text_field(body.get(k), 6000, label, multiline=True)
                 for k, label in (("summary", "Summary"), ("next_steps", "Next steps"), ("asks", "What we need"))}
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if not words["summary"]:
        return jsonify(error="Write the summary first — two or three lines on where it stands"), 400
    db = get_db()
    from services.doc_templates import resolve
    snap = report_data.snapshot(project)
    snap["template"] = resolve("rollout", as_id(body.get("template_id")))   # frozen: a later template edit never changes an issued version
    # the number is taken inside the INSERT: two saves at once cannot pick the same one
    cur = db.execute("INSERT INTO project_reports (project_id, version, body, created_by, created_at, kind, data, summary, next_steps, asks) "
                     "SELECT ?, COALESCE(MAX(version), 0) + 1, ?, ?, ?, 'snapshot', ?, ?, ?, ? FROM project_reports WHERE project_id = ?",
                     (project_id, words["summary"], session["user_name"], datetime.utcnow().isoformat(), snapshot_json(snap),
                      words["summary"], words["next_steps"], words["asks"], project_id))
    version = db.execute("SELECT version FROM project_reports WHERE id = ?", (cur.lastrowid,)).fetchone()[0]
    from routes.ai import use_suggestion
    ai = use_suggestion(project_id, body.get("ai_suggestion"), ("weekly_words", "customer_words"))
    db.commit()
    # Save and share (B8): the rollout's Customer contacts hear of it, each mail with a fresh
    # sign-in link to the customer copy of this version (the outbox mints it as it sends)
    customers = customer_ids(project_id, db, active=True) if body.get("share") is True else []
    audit_log("save_report", "project", project_id, project["name"], f"version {version}{ai}" + (f"; shared with {len(customers)} customer {plural(len(customers), 'contact')}" if body.get("share") is True else ""))
    if customers:
        from markupsafe import escape as _esc
        from services.notifications import notify_users
        notify_users(customers, "report", project_id, f"{project['name']}: a new rollout report",
                     f"<p>{_esc(session['user_name'])} has shared version {version} of the report on <b>{_esc(project['name'])}</b>: "
                     "where the rollout stands, what comes next and what we need from you.</p>",
                     exclude_user_id=session["user_id"], link=f"/projects/{project_id}/report?v={version}")
    return jsonify(ok=True, version=version, shared=len(customers))


@app.route("/api/account")
@login_required
def api_account():
    from constants import ADMIN_KINDS, NOTIFICATION_KINDS, STAFF_KINDS
    from services.notifications import delivery
    u = get_db().execute("SELECT id, username, name, email, kind, must_change_password, theme, accent, avatar, email_off, email_summary, home, password_hash, ics_created_at, ics_last_read_at FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    off = set((u["email_off"] or "").split(","))
    return jsonify(username=u["username"], name=u["name"], email=u["email"], kind=u["kind"], must_change_password=bool(u["must_change_password"]),
                   has_password=bool(u["password_hash"] and "$" in u["password_hash"]),
                   theme=u["theme"], accent=u["accent"], avatar_url=avatar_url(u), home=u["home"],
                   email_kinds=[{"key": k, "label": v, "on": k not in off, "mode": delivery(u, k)} for k, v in NOTIFICATION_KINDS.items()
                                if (k not in ADMIN_KINDS or session.get("role") == "Admin")   # access requests and AI health reach admins only
                                and (k not in STAFF_KINDS or u["kind"] != "external")],
                   mail_enabled=policy("notify_email_enabled"),
                   calendar=None if u["kind"] == "external" else {"created_at": u["ics_created_at"], "last_read_at": u["ics_last_read_at"],
                                                                   "idle_days": policy("ics_idle_days")},   # the personal feed (routes/feeds.py)
                   activity=activity_summary(session["user_id"]) if activity_enabled() else None,
                   activity_viewers=policy("activity_roles"))


@app.route("/api/whats-new")
@login_required
def api_whats_new():
    """The release's change log for staff, once (B15): `show` until they press Got it."""
    from routes.client import app_version
    from services.whats_new import summary
    version = app_version()
    seen = get_db().execute("SELECT whats_new_seen FROM users WHERE id = ?", (session["user_id"],)).fetchone()[0]
    news = summary(version) if session.get("kind") != "external" else None
    return jsonify(show=bool(news) and seen != version, **(news or {"version": version, "title": "", "items": []}))


@app.route("/api/whats-new/seen", methods=["POST"])
@login_required
def api_whats_new_seen():
    from routes.client import app_version
    version = app_version()
    get_db().execute("UPDATE users SET whats_new_seen = ? WHERE id = ?", (version, session["user_id"]))
    get_db().commit()
    audit_log("dismiss_whats_new", "user", session["user_id"], session.get("user_name"), f"v{version}")
    return jsonify(ok=True)


@app.route("/api/my-work")
@permission_required("view_board")
def api_my_work():
    from services.people import my_work
    d = my_work(session["user_id"], project_scope())
    for p in d["projects"]:   # the quick-add picks only rollouts the task route would accept
        p["can_add_task"] = project_allows(p["id"], "manage_tasks")
    return jsonify(d)


@app.route("/api/people")
@permission_required("view_board")
def api_people():
    """Everyone internal who is on active work; staff only."""
    from services.people import people
    if session.get("kind") == "external":
        abort(403)
    return jsonify(people=people(project_scope()), can_notify=session.get("role") in ("Admin", "Member", "Contributor"), me=session["user_id"])


@app.route("/api/people/<int:user_id>")
@permission_required("view_board")
def api_person(user_id):
    from services.people import person
    if session.get("kind") == "external":
        abort(403)
    d = person(user_id, project_scope())
    if d is None:
        abort(404)
    d["can_notify"] = session.get("role") in ("Admin", "Member", "Contributor") and user_id != session["user_id"]
    from services import activity
    if activity.can_see_others(session.get("role")) or (activity.enabled() and user_id == session["user_id"]):
        d["activity"] = activity.summary(user_id)
    return jsonify(d)


@app.route("/api/activity", methods=["POST"])
@login_required
def api_activity():
    """One active minute (see services/activity.py). Not audited: it is the measurement itself."""
    from services import activity
    return jsonify(ok=True, counted=activity.ping(session["user_id"]))


@app.route("/api/people/<int:user_id>/notify", methods=["POST"])
@permission_required("view_board")
def api_person_notify(user_id):
    """A note to a colleague: in-app, and by mail unless they switched the kind off. Audited."""
    from markupsafe import escape as _esc
    from services.notifications import notify_users
    if session.get("kind") == "external" or session.get("role") not in ("Admin", "Member", "Contributor") or user_id == session["user_id"]:
        abort(403)
    body = json_body()
    try:
        message = text_field(body.get("message"), 1000, "Message", multiline=True)   # too long is said, never cut (P2-27)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if not message:
        return jsonify(error="Write a message first"), 400
    target = get_db().execute("SELECT id, name FROM users WHERE id = ? AND active = 1 AND kind = 'internal'", (user_id,)).fetchone()
    if not target:
        abort(404)
    project_id = as_id(body.get("project_id"))
    if project_id and not get_db().execute("SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone():
        return jsonify(error="That rollout does not exist"), 400   # test report FN-12: it was a 500
    if busy := nudge_limited(session["user_id"], user_id):   # review P3-3
        return jsonify(error=busy), 429, {"Retry-After": "3600"}   # counted over the last hour
    notify_users([user_id], "nudge", project_id, f"{session.get('user_name')} sent you a note", f"<p>{_esc(message)}</p>", link=f"/board?rollout={project_id}" if project_id else "/my-work")
    audit_log("notify_person", "user", user_id, target["name"], message[:80])
    return jsonify(ok=True)


@app.route("/api/dashboard")
@permission_required("view_board")
def api_dashboard():
    if session.get("kind") == "external":   # staff workloads and internal activity: partners get the flow instead
        abort(403)
    from services import dashboard
    return jsonify(dashboard.build(project_scope(), session["user_id"]))


@app.route("/api/calendar")
@permission_required("view_board")
def api_calendar():
    import re
    from services import calendar
    month = request.args.get("month", "")
    if not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", month):   # the window parse_date keeps; year 1 overflowed the grid's arithmetic
        month = ""   # the current month
    d = calendar.build(month, project_scope())
    from services import milestones   # diamonds on their day; an outsider sees only those marked for the customer
    d["milestones"] = milestones.between(d["from"], d["to"], project_scope(), customer=session.get("kind") == "external")
    # who may drag a task to another day: whoever manages the rollout's tasks, done or not, exactly
    # as task_edit decides (P2-10: the person a task is on ticks it, never re-dates it; P3-18)
    if session.get("kind") == "external":   # a partner sees their own tasks, never the team's (as on the rollout page)
        d["tasks"] = [t for t in d["tasks"] if t["assignee_id"] == session["user_id"]]
    manages = {pid: project_allows(pid, "manage_tasks") for pid in {t["project_id"] for t in d["tasks"]}}
    for t in d["tasks"]:
        t.pop("assignee_id")
        t["can_edit"] = manages[t["project_id"]]
    return jsonify(d)


@app.route("/api/dashboard/version")
@permission_required("view_board")
def api_dashboard_version():
    """Cheap: the page asks every few seconds whether anything changed."""
    if session.get("kind") == "external":   # the dashboard is staff only, and so is its heartbeat (P3-14)
        abort(403)
    from services import dashboard
    return jsonify(version=dashboard.version())


@app.route("/api/dashboard/layout", methods=["PUT", "DELETE"])
@permission_required("view_board")
def api_dashboard_layout():
    """This user's own arrangement: PUT saves it, DELETE goes back to the workspace default."""
    import json
    from services import dashboard
    db = get_db()
    if request.method == "DELETE":
        db.execute("UPDATE users SET dashboard_layout = NULL WHERE id = ?", (session["user_id"],))
        db.commit()
        audit_log("dashboard_layout_reset", "user", session["user_id"], session.get("user_name"))
        return jsonify(ok=True, layout=dashboard.default_layout(), is_custom=False)
    layout = dashboard.normalize_layout(json_body().get("layout"))
    if layout is None:
        abort(400)
    db.execute("UPDATE users SET dashboard_layout = ? WHERE id = ?", (json.dumps(layout), session["user_id"]))
    db.commit()
    audit_log("dashboard_layout_saved", "user", session["user_id"], session.get("user_name"), f"{len(layout)} widgets")
    return jsonify(ok=True, layout=layout, is_custom=True)


@app.route("/api/dashboard/layout/default", methods=["PUT"])
@permission_required("manage_settings")
def api_dashboard_default_layout():
    """The workspace default, set by an admin from the page; users without their own arrangement follow it."""
    import json
    from db import set_setting
    from services import dashboard
    layout = dashboard.normalize_layout(json_body().get("layout"))
    if layout is None:
        abort(400)
    set_setting(dashboard.LAYOUT_KEY, json.dumps(layout))
    audit_log("dashboard_default_layout", "settings", None, "dashboard", f"{len(layout)} widgets: {', '.join(w['id'] for w in layout)}")
    return jsonify(ok=True, layout=layout)


@app.route("/api/alerts")
@permission_required("view_board")
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
    from services.analytics import build_cycle_times, busiest_template, clock
    if session.get("kind") == "external":   # internal cycle times: staff only
        abort(403)
    db = get_db()
    templates = db.execute("SELECT id, name FROM stage_templates ORDER BY id").fetchall()
    template_id = request.args.get("template", type=as_id) or (templates and busiest_template(db, project_scope())["id"]) or None
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE p.deleted_at IS NULL AND p.intake_pending = 0 AND p.stage_template_id IS ?{project_scope()[0]}", (template_id, *project_scope()[1])
    ).fetchall()
    notes = {}
    for n in db.execute("SELECT project_id, stage, created_at FROM status_notes ORDER BY created_at"):
        notes.setdefault(n["project_id"], []).append(n)
    rows = db.execute("SELECT name, sla_days FROM stage_template_stages WHERE template_id = ? ORDER BY position", (template_id,)).fetchall() if template_id else []
    names = [r["name"] for r in rows]
    stats = build_cycle_times(projects, notes, names, names[-1], clock=clock()) if names else None
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
    edit_id, from_id = request.args.get("edit", type=as_id), request.args.get("from", type=as_id)
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
    # a product keeps its vendor's name after the vendor is deleted, so it is not offered with every vendor (sim L-17)
    vendor_names = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM vendors")}
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
        "vendors": [r["name"] for r in lists["vendors"]],
        # each product names its vendor ("" = any vendor); the form offers the chosen vendor's
        "products": [{"name": r["name"], "vendor": vendor_names.get(r["vendor_id"], "")} for r in lists["products"]],
        "outsourcers": [{"name": r["name"], "email": r["email"]} for r in lists["outsourcers"]],
        "templates": [{"id": t["id"], "name": t["name"]} for t in db.execute("SELECT id, name FROM stage_templates ORDER BY name")],
        # Settings › Projects & workflow: what a new project starts with
        "defaults": {"stage_template_id": int(policy("default_template")) if policy("default_template")
                      else (db.execute("SELECT id FROM stage_templates ORDER BY id LIMIT 1").fetchone() or [None])[0],
                     "customer_approval": policy("default_customer_approval")},
        # the team joins as coordinators: a Viewer only reads, so is not offered
        "users": [{"id": u["id"], "name": u["name"]} for u in db.execute("SELECT id, name FROM users WHERE active = 1 AND kind = 'internal' AND role != 'Viewer' ORDER BY name")],
        # a project manager must be able to move stages; someone who cannot picks one
        "leads": leads(db, project.get("owner_id") if mode == "edit" else None),   # editing keeps the current owner listed
        "can_lead": role_has_permission(session.get("role"), "edit_project_stage"),
        # custom fields (Settings › Rollouts & workflow), with the record's values on an edit or a copy
        "custom_fields": custom_fields.for_project(source["id"]) if source else [f | {"value": None} for f in custom_fields.definitions()],
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
    page = max(1, args.get("page", type=as_id) or 1)
    # the nav's Projects link returns to this filter (page deliberately not kept)
    session["projects_query"] = {k: v[:100] for k, v in args.items() if k in ("view", "stage", "delivery_mode", "closed", "q", "sort", "dir") and v}   # capped: a crafted link must not outgrow the cookie (review P3-12)
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
    # the cards view: how much of the work is done, and who is on it (PM first)
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids)) or "NULL"
    tally = {t["project_id"]: t for t in db.execute(
        f"SELECT project_id, COUNT(*) AS total, SUM(done = 0) AS open FROM tasks WHERE project_id IN ({marks}) GROUP BY project_id", ids)}
    team = {}
    for t in db.execute(
        "SELECT pp.project_id, u.id, u.name, u.avatar FROM project_participants pp JOIN users u ON u.id = pp.user_id "
        f"WHERE u.active = 1 AND pp.project_id IN ({marks}) ORDER BY CASE pp.role WHEN 'Project manager' THEN 0 ELSE 1 END, u.name", ids):
        team.setdefault(t["project_id"], []).append({"id": t["id"], "name": t["name"], "avatar_url": avatar_url(t)})
    out = []
    # each row's state, counted as the Flow counts it, so a late rollout looks late here too (critique 10 Oct)
    from services.alerts import project_states
    states = project_states(rows)
    external = session.get("kind") == "external"   # custom fields: the extra columns, a filter per choice field, each row's values in column order
    defs = custom_fields.definitions(customer=external)
    columns = [{"id": f["id"], "name": f["name"], "kind": f["kind"]} for f in defs if f["show_in_list"]]
    field_filters = [{"id": f["id"], "name": f["name"], "choices": f["choices"]} for f in defs if f["kind"] == "choice"]
    have = custom_fields.values_for(ids, external, list_only=True)
    field_values = {pid: [have[pid].get(c["id"]) for c in columns] for pid in ids}
    for r in rows:
        names = [s["name"] for s in (lists.get(r["id"]) or [])]
        t = tally.get(r["id"])
        out.append({
            "total_tasks": t["total"] if t else 0, "open_tasks": t["open"] if t else 0,
            "team": team.get(r["id"], [{"id": r["owner_id"], "name": r["owner_name"], "avatar_url": None}]),
            "id": r["id"], "name": r["name"], "client": r["client"], "po_number": r["po_number"] if sees_po(r["id"]) else None, "stage": r["stage"],
            "stages": names, "stage_index": names.index(r["stage"]) if r["stage"] in names else 0,
            "closed": bool(names) and r["stage"] == names[-1], "state": states.get(r["id"], "on_track"),
            "owner_name": r["owner_name"], "delivery_mode": r["delivery_mode"], "vendor_name": r["vendor_name"],
            "product_name": r["product_name"], "target_end_date": r["target_end_date"], "updated_at": r["updated_at"],
            "fields": field_values[r["id"]],   # in the order of `fields` below
        })
    # CRM intakes waiting for a project manager: the "Pending intake" filter's count (staff only; an outsider has none)
    pending = db.execute(f"SELECT COUNT(*) FROM projects p WHERE p.deleted_at IS NULL AND p.intake_pending = 1{scope_sql}", scope_params).fetchone()[0]
    return jsonify(rows=out, total=total, page=page, total_pages=total_pages, sort=sort, dir=direction, pending=pending,
                   stages=stage_names, delivery_modes=list(DELIVERY_MODES), fields=columns, field_filters=field_filters,
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
    entries = stage_entry_note_ids(project_id)
    external = session.get("kind") == "external"
    if external:
        # partners and customers: no internal contacts or partner channel; the PO only to the customer
        fields = ["client", "account_manager_name", "start_date", "target_end_date", "delivery_mode", "vendor_name", "product_name"]
        if project_role_of(project_id, session["user_id"]) == "Customer":
            fields += ["po_number", "po_date"]
    hidden_docs = partner_hidden_categories(db) if external else set()
    from routes.guest import links_expire
    from core import external_url   # the public address, never the Host a PM happened to use (P3-1)
    guest_on = policy("guest_links_enabled")
    return jsonify({
        "id": project["id"], "name": project["name"], "owner_id": project["owner_id"],
        "guest_links_enabled": guest_on,
        # a CRM intake waiting for a project manager (services/intake.py): the page says so and offers Confirm (staff only)
        "intake_pending": bool(project["intake_pending"]) and not external,
        "details": {f: project[f] for f in fields},
        "customer_approval": bool(project["customer_approval"]),
        "guest_links": {
            "customer": external_url("guest_view", token=project["customer_token"]) if project["customer_token"] else None,
            "vendor": external_url("guest_view", token=project["access_token"])
            if project["delivery_mode"] == "Outsourced" and project["access_token"] else None,
        } if guest_on and can_manage else {"customer": None, "vendor": None},
        # when those links stop working (None: never); rotating renews them (P2-6)
        "guest_links_expire": links_expire(project) if guest_on and can_manage else None,
        # the gates and the SLAs are staff-only (services/gates.py; PRODUCT.md, "Customer copy")
        "stage_rows": [{"id": r["id"], "name": r["name"], **({} if external else {"sla_days": r["sla_days"]}),
                        "gate_tasks": bool(r["gate_tasks"]) and not external, "required_docs": [] if external else gates.required_docs(r)}
                       for r in stage_rows(project_id)],
        "participants": [{"id": r["id"], "user_id": r["user_id"], "name": r["name"], "role": r["role"],
                          "email": r["email"] if not external or r["user_id"] == session["user_id"] else None, "active": bool(r["active"]),
                          "avatar_url": f"/users/{r['user_id']}/avatar/{r['avatar']}" if r["avatar"] else None}
                         for r in participants_for(project_id)],
        "notes": [{"id": n["id"], "author": n["author"], "note": n["note"], "stage": n["stage"], "created_at": n["created_at"],
                   "mine": n["author_id"] is not None and n["author_id"] == session["user_id"], "edited": n["edited_at"] is not None,
                   "stage_entry": n["id"] in entries}
                  for n in db.execute("SELECT * FROM status_notes WHERE project_id = ?" + (" AND guest_visible = 1" if session.get("kind") == "external" else "")
                                      + " ORDER BY created_at DESC", (project_id,))],
        # review: "pending" while an outside upload waits for staff (services/doc_review.py); partners never see one pending
        "documents": [{"id": d["id"], "category": d["category"], "filename": d["filename"], "uploaded_by": d["uploaded_by"], "uploaded_at": d["uploaded_at"],
                       "review": d["review_status"]}
                      for d in db.execute("SELECT * FROM documents WHERE project_id = ? AND deleted_at IS NULL ORDER BY uploaded_at DESC", (project_id,))
                      if d["category"] not in hidden_docs and not (external and d["review_status"] != "accepted")],
        "doc_categories": get_doc_category_names(),
        "users": [{"id": u["id"], "name": u["name"]} for u in db.execute("SELECT id, name FROM users WHERE active = 1 AND kind = 'internal' ORDER BY name")] if can_manage else [],
        "roles": [r for r in PROJECT_ROLES if r not in (PROJECT_MANAGER, "Customer")], "external_roles": list(EXTERNAL_PROJECT_ROLES),
        "can": {
            "manage": can_manage, "tasks": project_allows(project_id, "manage_tasks"),
            "docs": project_allows(project_id, "manage_documents"),
            "move": project_allows(project_id, "move_stage") and not project["intake_pending"],   # a pending intake has no stage to leave
            "note": role_has_permission(role, "add_project_note"), "download": role_has_permission(role, "download_document"),
            "create": role_has_permission(role, "create_project"),
            # the delete routes check the global permission too (Admin by default): offer only what will succeed
            "delete_doc": project_allows(project_id, "manage_documents") and role_has_permission(role, "delete_document"),
            "delete_project": can_manage and role_has_permission(role, "delete_project"),
        },
    })


# How the activity feed words each audit action. Anything not listed shows
# as the action name with underscores dropped, so a new action needs no edit
# here to appear.
ACTIVITY_LABELS = {
    "create_project": "created the project", "update_project": "edited the project", "update_project_stage": "moved the stage", "undo_project_stage": "undid a stage move",
    "add_project_note": "added a note", "add_task": "added a task", "edit_task": "edited a task", "toggle_task": "ticked or reopened a task",
    "delete_task": "removed a task", "override_task_wait": "ticked a task still waiting on another (Admin override)", "upload_document": "uploaded a document", "delete_document": "removed a document",
    "add_participant": "added someone to the team", "invite_participant": "invited a partner", "remove_participant": "removed someone from the team",
    "approval_decision": "recorded the customer's decision", "save_report": "saved a report version",
    "add_project_stage": "added a stage", "rename_project_stage": "renamed a stage", "move_project_stage": "reordered the stages",
    "delete_project_stage": "removed a stage", "update_project_slas": "changed the stage SLAs", "rotate_guest_token": "rotated the guest links",
    "update_project_stage_gates": "changed what each stage asks before it is left", "override_stage_gate": "moved past a stage gate",
    "delete_project": "deleted the project", "restore_project": "restored the project",
    "add_scope_item": "added to the scope", "edit_scope_item": "updated the scope", "move_scope_item": "reordered the scope", "delete_scope_item": "removed a scope item",
    "signoff_send": "sent the sign-off", "signoff_sign": "signed the sign-off", "signoff_countersign": "countersigned the sign-off",
    "signoff_reject": "did not accept the sign-off", "signoff_withdraw": "withdrew the sign-off", "signoff_upload": "uploaded the signed sign-off",
    "signoff_waive": "waived the sign-off", "signoff_link": "made a sign-in link for the signatory",
    "download_report": "downloaded the report PDF", "download_signoff": "downloaded the sign-off PDF",
    "update_field_values": "changed custom fields",
    "complete_ask": "finished what was asked of them", "rate_rollout": "rated the rollout",
    "accept_document": "accepted an uploaded file", "reject_document": "rejected an uploaded file",
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
    return jsonify(rows=[{"when": r["timestamp"], "who": r["username"], "action": r["action"], **_activity_words(r["action"], r["details"] or "")}
                         for r in rows])


def _activity_words(action, details):
    """An audit row as the feed says it: words, never field names (sim PM-19)."""
    label = ACTIVITY_LABELS.get(action, action.replace("_", " "))
    if action in ("update_project_stage", "undo_project_stage"):
        details = details.replace("stage=", "to ")
    elif action == "update_project":
        details = ""   # "client=…; owner_id=…" is for the audit log
    elif action == "toggle_task" and ":" in details:
        state, _, details = details.partition(": ")
        label = "completed a task" if state == "done" else "reopened a task"
    return {"label": label, "details": details}


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
    writer = safe_csv_writer(out)
    writer.writerow(["timestamp_utc", "who", "action", "what", "details"])
    for r in rows:
        writer.writerow([r["timestamp"], r["username"], r["action"], ACTIVITY_LABELS.get(r["action"], r["action"].replace("_", " ")), r["details"] or ""])
    audit_log("export_project_activity", "project", project_id, project["name"], f"{len(rows)} rows")
    safe = file_stem(project["name"])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=odin-activity-{safe}.csv"})


@app.route("/api/projects/<int:project_id>/stage", methods=["POST"])
@permission_required("edit_project_stage")
@project_role_required("move_stage")
def api_project_stage(project_id):
    load_project(project_id)
    data = json_body()
    try:
        stage, note = text_field(data.get("stage"), 200, "Stage"), text_field(data.get("note"), 5000, "Note", multiline=True)
        # the stage the page showed: a move from a stale view is a 409, never a step backwards (P2-26)
        seen = text_field(data.get("from_stage"), 200, "From stage") if data.get("from_stage") is not None else None
        override = text_field(data.get("override"), 300, "Reason")   # moving past a stage gate (services/gates.py)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    # change_stage audits and notifies; this is the same door the form uses.
    error = change_stage(project_id, stage, note, from_stage=seen, override=override or None)
    if error:
        return jsonify({"error": error}), 409 if isinstance(error, StageConflict) else 400
    return jsonify({"ok": True, "undo": g.stage_undo_url})


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
    """Calendar days since a stored timestamp, unrounded (round only to show)."""
    parsed = _parse(iso) if iso else None
    return (now - parsed).total_seconds() / 86400 if parsed else None


def _flow_urgency(r, now):
    """Order inside a state: the worst case first. Overdue and due soon by
    target date (the most late first), over SLA by days over, on track by the
    most recently touched."""
    if r["state"] in ("overdue", "due_soon"):
        return (r["target_end_date"] or "9999", r["name"])
    if r["state"] == "over_sla":
        return (-(r["over_by"] or 0), r["name"])
    return (-(_parse(r["updated_at"]) or now).timestamp(), r["name"])


@app.route("/api/flow")
@permission_required("view_board")
def api_flow():
    db = get_db()
    now = datetime.utcnow()
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.done = 0) AS open_tasks, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id) AS total_tasks, "
        # open tasks past their date: a rollout inside its SLA can still need attention (critique 10 Oct)
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.done = 0 AND t.due_date < ?) AS late_tasks, "
        "(SELECT MIN(t.due_date) FROM tasks t WHERE t.project_id = p.id AND t.done = 0 AND t.due_date < ?) AS late_since "
        "FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{project_scope()[0]} ORDER BY p.updated_at DESC",
        (local_today().isoformat(), local_today().isoformat(), *project_scope()[1]),
    ).fetchall()
    stage_lists = stages_for_projects([p["id"] for p in projects])
    mine = my_project_ids(session["user_id"])
    # the rows below for the rollouts on this page only, never every rollout ever made (review P3-25)
    shown = f"SELECT p.id FROM projects p WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{project_scope()[0]}"
    # latest approval per project, only meaningful for the current stage
    approvals = {}
    for r in db.execute(
        "SELECT a.project_id, a.stage, a.status FROM stage_approvals a "
        f"WHERE a.project_id IN ({shown}) AND a.id = (SELECT MAX(id) FROM stage_approvals WHERE project_id = a.project_id)", project_scope()[1]
    ):
        approvals[r["project_id"]] = r
    team = {}   # project_id -> participant names, PM first (avatars on the row)
    for r in db.execute(
        "SELECT pp.project_id, u.id, u.name, u.avatar FROM project_participants pp JOIN users u ON u.id = pp.user_id "
        f"WHERE u.active = 1 AND pp.project_id IN ({shown}) ORDER BY CASE pp.role WHEN 'Project manager' THEN 0 ELSE 1 END, u.name", project_scope()[1]
    ):
        team.setdefault(r["project_id"], []).append({"id": r["id"], "name": r["name"], "avatar_url": avatar_url(r)})
    # The next actionable item, as the detail pane's "Next up" picks it: the
    # current stage's work first, then the earliest due date, undated last.
    # (a task whose stage is gone, or never had one, belongs to the current stage)
    stage_of = {p["id"]: p["stage"] for p in projects}
    names_of = {pid: {r["name"] for r in rows} for pid, rows in stage_lists.items()}
    next_task = {}
    # a task still waiting on open work is not the next step; a partner hears only of their own tasks
    own, own_params = (" AND t.assignee_id = ?", [session["user_id"]]) if session.get("kind") == "external" else ("", [])
    for t in db.execute(
        "SELECT t.project_id, t.stage, t.title, t.due_date, u.name AS assignee_name FROM tasks t "
        f"LEFT JOIN users u ON u.id = t.assignee_id WHERE t.done = 0 AND t.project_id IN ({shown}){own} "
        "AND NOT EXISTS (SELECT 1 FROM task_links l JOIN tasks w ON w.id = l.depends_on_task_id WHERE l.task_id = t.id AND w.done = 0) "
        "ORDER BY t.due_date IS NULL, t.due_date, t.id", [*project_scope()[1], *own_params]
    ):
        here = t["stage"] == stage_of.get(t["project_id"]) or t["stage"] not in names_of.get(t["project_id"], ())
        if t["project_id"] not in next_task or (here and not next_task[t["project_id"]]["here"]):
            next_task[t["project_id"]] = {"title": t["title"], "due_date": t["due_date"], "assignee": t["assignee_name"], "here": here}
    for v in next_task.values():
        del v["here"]
    # may this person move each rollout (the Kanban's drag): project_allows, for every row in one query
    from constants import PROJECT_ACTIONS
    move_perm, move_roles = PROJECT_ACTIONS["move_stage"]
    role = session.get("role", "Viewer")
    my_roles = {r["project_id"]: r["role"] for r in db.execute("SELECT project_id, role FROM project_participants WHERE user_id = ?", (session["user_id"],))}
    may_move = lambda pid: role_has_permission(role, move_perm) and (role == "Admin" or my_roles.get(pid) in move_roles)   # noqa: E731
    signoff_on = bool(policy("signoff_required"))
    staff = session.get("kind") != "external"
    alert_settings = get_alert_type_settings()
    stale_days = (alert_settings.get("stale") or DEFAULT_ALERT_TYPE_SETTINGS["stale"])["threshold_days"]
    soon_days = (alert_settings.get("project_due_soon") or DEFAULT_ALERT_TYPE_SETTINGS["project_due_soon"])["threshold_days"]
    rows = []
    for p in projects:
        own = stage_lists.get(p["id"]) or []
        stages = [r["name"] for r in own]
        terminal = stages[-1] if stages else None
        slas = sla_by_stage(own)
        sla = stage_sla_state(p, slas, terminal, now)
        schedule = schedule_status(p, soon_days=soon_days, terminal_stage=terminal)
        state = _flow_state(p, sla if staff else None, schedule)   # SLAs are staff-only: an outsider never reads "over SLA"
        idle = _days_since(p["updated_at"], now)
        in_stage = sla["days"] if sla else days_in_stage(p["stage_entered_at"], now)
        at = stages.index(p["stage"]) if p["stage"] in stages else 0
        nxt = stages[at + 1] if at + 1 < len(stages) else None
        # two queries per rollout; batch them if the board ever holds thousands
        held = gates.blocked(p, nxt, own) if nxt and staff else []
        rows.append({
            "id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"],
            "stages": stages, "mine": p["id"] in mine, "team": team.get(p["id"], [{"id": p["owner_id"], "name": p["owner_name"], "avatar_url": None}]),
            "approval": (approvals[p["id"]]["status"] if p["id"] in approvals and approvals[p["id"]]["stage"] == p["stage"] else None),
            "stage_index": stages.index(p["stage"]) if p["stage"] in stages else 0,
            "owner_name": p["owner_name"], "delivery_mode": p["delivery_mode"],
            "target_end_date": p["target_end_date"], "days_in_stage": None if in_stage is None else round(in_stage, 1),
            "sla_days": slas.get(p["stage"]) if staff else None, "over_by": round(sla["over_by"], 1) if sla and staff else None,
            "state": state, "open_tasks": p["open_tasks"], "total_tasks": p["total_tasks"],
            "late_tasks": p["late_tasks"], "late_since": p["late_since"],
            "next_task": next_task.get(p["id"]), "updated_at": p["updated_at"],
            "idle_days": None if idle is None else round(idle, 1), "stale": idle is not None and idle >= stale_days,
            "start_date": p["start_date"], "next_stage": nxt, "can_move": bool(nxt) and may_move(p["id"]),
            # the last stage waits for a signed sign-off (services/signoff.gate): the board refuses that drop up front
            "signoff_needed": signoff_on and nxt is not None and nxt == terminal and not signoff_service.completed(p["id"]),
            # so does a stage gate (services/gates.blocked): staff see why, the customer never sees gate internals
            "gate_blocked": bool(held), "gate_reasons": [r["text"] for r in held],
        })
    rows.sort(key=lambda r: (STATE_RANK[r["state"]], 0 if r["late_tasks"] else 1, _flow_urgency(r, now)))
    counts = {k: sum(1 for r in rows if r["state"] == k) for k in STATE_RANK}
    counts["late_tasks"] = sum(1 for r in rows if r["state"] == "on_track" and r["late_tasks"])   # on track, but a task is late
    first_at = {}   # in-scope stage names only, ordered by where they typically sit (as get_stage_names() does)
    for lst in stage_lists.values():
        for r in lst:
            first_at[r["name"]] = min(r["position"], first_at.get(r["name"], r["position"]))
    from services import intake   # CRM intakes wait in the List's holding lane, in no count (staff only)
    closed = []   # an outsider keeps their finished rollouts, with the way to the sign-off and the report (sim 28 Oct): staff find theirs in Rollouts
    if not staff:
        from policies import local_date
        for p in db.execute(
                "SELECT p.id, p.name, p.client, p.stage_entered_at, "
                "EXISTS (SELECT 1 FROM project_reports r WHERE r.project_id = p.id) AS has_report FROM projects p "
                f"WHERE p.deleted_at IS NULL AND {PROJECT_CLOSED_SQL} = 1 AND COALESCE(p.intake_pending, 0) = 0{project_scope()[0]} ORDER BY p.stage_entered_at DESC",
                project_scope()[1]).fetchall():
            on = local_date(p["stage_entered_at"]) if p["stage_entered_at"] else None
            closed.append({"id": p["id"], "name": p["name"], "client": p["client"], "closed_on": on.isoformat() if on else None,
                           "signed_off": bool(signoff_service.completed(p["id"])), "report": bool(p["has_report"])})
    return jsonify({"stages": sorted(first_at, key=lambda n: (first_at[n], n)), "rows": rows, "counts": counts, "today": local_today().isoformat(),
                    "can_move": role_has_permission(session.get("role"), "edit_project_stage"),
                    "pending": intake.pending_rows(db) if staff else [], **({} if staff else {"closed": closed})})


@app.route("/api/flow/plan")
@permission_required("view_board")
def api_flow_plan():
    """The Flow's Gantt: every open rollout in scope with its stages' plan,
    actuals, forecast and baseline (services/plan.py, read in one batch), and
    whether this person may drag its planned dates (the plan's PUT checks again).
    Staff only: the customer cut of a plan is the rollout report's."""
    from constants import PROJECT_ACTIONS
    from services.portfolio import plans
    if session.get("kind") == "external":
        abort(403)
    db = get_db()
    scope_sql, scope_params = project_scope()
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{scope_sql} ORDER BY COALESCE(p.start_date, p.created_at), p.name", scope_params).fetchall()
    perm, roles = PROJECT_ACTIONS["manage_project"]
    role = session.get("role", "Viewer")
    mine = {r["project_id"]: r["role"] for r in db.execute("SELECT project_id, role FROM project_participants WHERE user_id = ?", (session["user_id"],))}
    may_edit = lambda pid: role_has_permission(role, perm) and (role == "Admin" or mine.get(pid) in roles)   # noqa: E731
    keep = ("id", "name", "status", "sla_days", "plan_start", "plan_end", "base_start", "base_end", "actual_start", "actual_end",
            "forecast_start", "forecast_end", "suggested_start", "suggested_end", "slip_days")
    rows, cal = [], None
    built = plans(projects)
    for p in projects:
        pl, _ = built[p["id"]]
        cal = cal or pl["calendar"]
        rows.append({
            "id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"], "owner_name": p["owner_name"],
            "start_date": p["start_date"], "target_end_date": p["target_end_date"], "forecast": pl["finish"]["forecast"],
            "pct_complete": pl["pct_complete"], "rag": pl["health"]["rag"], "has_plan": pl["has_plan"], "baselined": bool(pl["baseline_at"]),
            "can_edit": may_edit(p["id"]), "stages": [{k: s.get(k) for k in keep} for s in pl["stages"]],
        })
    return jsonify(today=local_today().isoformat(), calendar=cal, rows=rows)


@app.route("/api/projects/<int:project_id>/plan")
@permission_required("view_project_detail")
def api_plan(project_id):
    """The rollout's plan, actuals, forecast and health, with the change log."""
    from services import plan
    project = load_project(project_id)
    d = plan.build(project)
    d["changes"] = plan.changes(project_id)
    d["can_edit"] = project_allows(project_id, "manage_project")
    if session.get("kind") == "external":   # the customer's cut, as in their report: no baseline, slip, reasons or change log
        from services import raid as raid_service
        from services.report_data import customer_health
        visible = [r for r in raid_service.items(project_id) if r["customer_visible"]]
        d["health"] = customer_health({"health": d["health"], "stages": d["stages"], "finish": d["finish"], "raid": visible,
                                       "today": local_today().isoformat(), "has_plan": d.get("has_plan")})
        for s in d["stages"]:
            for k in ("base_start", "base_end", "slip_days", "sla_days", "planned_days"):
                s.pop(k, None)
            s["forecast_reason"] = None   # it names the internal task that holds the stage
        d["health"] = {"rag": d["health"]["rag"], "reasons": [], "confidence": d["health"]["confidence"]}
        d["finish"] = {k: v for k, v in d["finish"].items() if k in ("forecast", "planned", "target", "vs_target_days", "days_to_target")}
        d["changes"], d["baseline_at"] = [], None
    d["project"] = {"id": project["id"], "name": project["name"], "start_date": project["start_date"], "target_end_date": project["target_end_date"]}
    return jsonify(d)


@app.route("/api/projects/<int:project_id>/plan", methods=["PUT"])
@permission_required("edit_project")
@project_role_required("manage_project")
def api_plan_save(project_id):
    """Save the plan's dates; the first plan saved becomes the baseline."""
    from services import plan
    project = load_project(project_id)
    body = json_body()
    try:
        reason = text_field(body.get("reason"), 300, "Reason")   # a list is refused, too long is said (P2-27)
        changed, baselined, warning = plan.save(project, body.get("stages"), reason, session["user_name"])
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if changed or baselined:
        audit_log("save_plan", "project", project_id, project["name"], f"{changed} date(s) changed{'; baseline set' if baselined else ''}{f'; {reason}' if reason else ''}")
    # warning: the plan ends after the target date (said, never blocking)
    return jsonify(ok=True, changed=changed, baselined=baselined, warning=warning)


@app.route("/api/projects/<int:project_id>/plan/baseline", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def api_plan_rebaseline(project_id):
    """Freeze the current plan as the new baseline; a reason is required."""
    from services import plan
    project = load_project(project_id)
    try:
        reason = text_field(json_body().get("reason"), 300, "Reason")
        if not reason:
            return jsonify(error="Say why the baseline moves"), 400
        plan.rebaseline(project, reason, session["user_name"])
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    audit_log("rebaseline_plan", "project", project_id, project["name"], reason)
    return jsonify(ok=True)


@app.route("/api/projects/<int:project_id>/raid")
@permission_required("view_project_detail")
def api_raid(project_id):
    """The rollout's risks, issues, decisions and blockers. Partners and
    customers see only what was marked for the customer."""
    from services import raid
    load_project(project_id)
    external = session.get("kind") == "external"
    owners = [] if external else [{"id": r["id"], "name": r["name"]} for r in get_db().execute(
        "SELECT id, name FROM users WHERE active = 1 AND kind = 'internal' ORDER BY name")]
    return jsonify(items=raid.items(project_id, customer=external), owners=owners, statuses=raid.STATUSES,
                   can_edit=not external and project_allows(project_id, "manage_tasks"), stages=get_stage_names(project_id))


def _raid_notify_owner(project, item_title, owner_id, before=None):
    from markupsafe import escape as _esc
    from services.notifications import notify_users
    if owner_id and owner_id != before:
        notify_users([owner_id], "assigned", project["id"], f"You own a RAID item on {project['name']}",
                     f"<p>{_esc(item_title)}</p>", exclude_user_id=session.get("user_id"))


@app.route("/api/projects/<int:project_id>/raid", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def api_raid_create(project_id):
    from services import raid
    project = load_project(project_id)
    try:
        fields = raid.clean(json_body(), project_id)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    touch_project(get_db(), project_id)
    rid = raid.create(project_id, fields, session["user_name"])
    audit_log("add_raid_item", "project", project_id, project["name"], f"{fields['kind']}: {fields['title'][:80]}")
    _raid_notify_owner(project, fields["title"], fields["owner_id"])
    return jsonify(ok=True, id=rid)


@app.route("/api/projects/<int:project_id>/raid/<int:item_id>", methods=["PUT", "DELETE"])
@permission_required("edit_project")
@project_role_required("manage_tasks")
def api_raid_item(project_id, item_id):
    from services import raid
    project = load_project(project_id)
    db = get_db()
    item = db.execute("SELECT * FROM raid_items WHERE id = ? AND project_id = ?", (item_id, project_id)).fetchone()
    if item is None:
        abort(404)
    if request.method == "DELETE":
        if not project_allows(project_id, "manage_project"):
            abort(403)
        db.execute("DELETE FROM raid_items WHERE id = ?", (item_id,))
        touch_project(db, project_id)
        db.commit()
        audit_log("delete_raid_item", "project", project_id, project["name"], f"{item['kind']}: {item['title'][:80]}")
        return jsonify(ok=True)
    try:
        fields = raid.clean(json_body(), project_id, existing=item)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    touch_project(db, project_id)
    raid.update(item, fields)
    audit_log("update_raid_item", "project", project_id, project["name"], f"{fields['kind']}: {fields['title'][:60]} to {fields['status']}")
    _raid_notify_owner(project, fields["title"], fields["owner_id"], before=item["owner_id"])
    return jsonify(ok=True)


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
    # latest visit is what the current SLA measures), in the SLA's own days.
    clk = clock()
    visits = {}
    for i, (stage, entered) in enumerate(timeline):
        left = timeline[i + 1][1] if i + 1 < len(timeline) else now
        visits[stage] = {"entered_at": entered.isoformat(), "days": round(working_days(entered, left, clk), 1)}
    current = stages.index(project["stage"]) if project["stage"] in stages else 0
    # The current stage's clock is stage_entered_at (what change_stage sets and
    # the SLA measures); the note history can lag it, e.g. after a backdate.
    entered_now = _parse(project["stage_entered_at"]) if project["stage_entered_at"] else None
    if entered_now and project["stage"] in stages:
        visits[project["stage"]] = {"entered_at": entered_now.isoformat(), "days": round(working_days(entered_now, now, clk), 1)}
    stage_rows = []
    external = session.get("kind") == "external"
    for i, name in enumerate(stages):
        status = "done" if i < current else "current" if i == current else "next"
        stage_rows.append({"name": name, "status": status, "sla_days": None if external else slas.get(name),   # SLAs are staff-only
                           **(visits.get(name) or {"entered_at": None, "days": None})})
    tasks = db.execute(
        "SELECT t.*, u.name AS assignee_name, u.avatar AS assignee_avatar FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id "
        "WHERE t.project_id = ? ORDER BY t.done, t.due_date IS NULL, t.due_date, t.id", (project_id,),
    ).fetchall()
    from services import task_links
    links = task_links.links_for(project_id, db)
    blocked = task_links.blocked_by(tasks, links)
    if session.get("kind") == "external":   # the customer cut: their own asks only (services/asks.py), never the team's tasks
        tasks = [t for t in tasks if t["assignee_id"] == session["user_id"]]
        own = {t["id"] for t in tasks}   # and what holds them: their own only, never the team's (task_links.outsider_cut)
        links = {k: [i for i in v if i in own] for k, v in links.items()}
        blocked = {k: task_links.outsider_cut(v, own) for k, v in blocked.items()}
    from services.asks import questions as ask_questions
    sla = stage_sla_state(project, slas, terminal, now)
    schedule = schedule_status(project, terminal_stage=terminal)
    target = date.fromisoformat(project["target_end_date"]) if project["target_end_date"] else None
    from policies import local_date
    start = project["start_date"] or local_date(project["created_at"]).isoformat()
    hidden_docs = partner_hidden_categories(db) if external else set()
    return jsonify({
        "id": project["id"], "name": project["name"], "client": project["client"],
        "vendor_name": project["vendor_name"], "product_name": project["product_name"],
        # partners and customers: no outsourcer, as on the project page
        "delivery_mode": project["delivery_mode"], "outsourcer_name": None if external else project["outsourcer_name"],
        "owner_name": project["owner_name"], "stage": project["stage"], "stage_index": current,
        "next_stage": stages[current + 1] if current + 1 < len(stages) else None,
        "state": _flow_state(project, None if external else sla, schedule), "over_by": round(sla["over_by"], 1) if sla and not external else None,
        "start_date": start, "target_end_date": project["target_end_date"],
        "days_left": (target - local_today()).days if target else None,
        "today": local_today().isoformat(),
        "stages": stage_rows,
        # a task without a stage belongs to whatever stage the project is in
        "tasks": [{"id": t["id"], "title": t["title"], "done": bool(t["done"]), "done_at": t["done_at"], "due_date": t["due_date"],
                   "assignee": t["assignee_name"], "assignee_id": t["assignee_id"],
                   "assignee_avatar_url": f"/users/{t['assignee_id']}/avatar/{t['assignee_avatar']}" if t["assignee_avatar"] else None,
                   "stage": t["stage"] if t["stage"] in stages else project["stage"],
                   "recurrence": t["recurrence"], "recur_until": t["recur_until"],   # Repeats (services/recurrence.py)
                   # finish-to-start (services/task_links.py): what it waits on, and the open ones that hold it
                   "estimate_hours": t["estimate_hours"], "waits_on": links.get(t["id"], []), "blocked_by": blocked.get(t["id"], []),
                   # what it asks for (services/asks.py): a tick, a document of one category, or a short form
                   "kind": t["kind"] or "task", "ask_category": t["ask_category"], "questions": ask_questions(t) if t["kind"] == "form" else []} for t in tasks],
        "assignable": [{"id": r["user_id"], "name": r["name"]} for r in participants_for(project_id) if r["active"]],
        "can_edit": project_allows(project_id, "manage_tasks"),
        "doc_categories": get_doc_category_names() if project_allows(project_id, "manage_tasks") else [],   # what an upload ask may ask for
        "can_override": session.get("role") == "Admin",   # an Admin may tick a waiting task; it is audited as an override
        "me": session["user_id"],
        "documents": sum(1 for d in db.execute("SELECT category, review_status FROM documents WHERE project_id = ? AND deleted_at IS NULL", (project_id,))
                         if d["category"] not in hidden_docs and not (external and d["review_status"] != "accepted")),   # only what they can open
        "recent_notes": [{"author": n["author"], "note": n["note"], "stage": n["stage"], "created_at": n["created_at"]}
                         for n in [n for n in notes if session.get("kind") != "external" or n["guest_visible"]][-4:][::-1]],
        "participants": [{"id": r["id"], "user_id": r["user_id"], "name": r["name"], "role": r["role"],
                          "avatar_url": f"/users/{r['user_id']}/avatar/{r['avatar']}" if r["avatar"] else None} for r in participants_for(project_id)],
        "can_move": project_allows(project_id, "move_stage") and not project["intake_pending"],   # a pending intake is confirmed first
        "customer_approval": bool(project["customer_approval"]),
        "approval": ({"id": a["id"], "stage": a["stage"], "status": a["status"], "decided_by": a["decided_by"], "comment": a["comment"],
                      "chases": a["chase_count"] if not external else 0}   # reminders Odin sent the customer (services/chasers.py)
                     if (a := current_approval(project_id)) else None),
        "can_approve": is_customer_on(project_id, session["user_id"]),
        "signoff": signoff_service.state(project, session["user_id"], session.get("kind") != "external"),
        "signoff_chases": 0 if external else (db.execute("SELECT chase_count FROM signoffs WHERE project_id = ? AND status = 'sent' ORDER BY version DESC LIMIT 1", (project_id,)).fetchone() or [0])[0],
        "watch": watch_state(project_id, session["user_id"], session.get("kind")),   # mute or follow (B3)
        # what stops the next move (services/gates.py), for staff only
        "gate": None if external else {"blocked": gates.blocked(project, stages[current + 1]) if current + 1 < len(stages) else [],
                                       "can_override": gates.may_override(project)},
    })


@app.route("/api/notifications")
@login_required
def api_notifications():
    """The bell: the newest 40 (?limit= up to 100), and older ones a page at a
    time with ?before_id=<the last id shown>; `more` says whether there are."""
    from services.notifications import visible_clause
    where, params = visible_clause(session["user_id"], session.get("kind"))
    before, limit = as_id(request.args.get("before_id")), min(as_id(request.args.get("limit")) or 40, 100)
    rows = get_db().execute(
        "SELECT n.*, p.name AS project_name FROM notifications n LEFT JOIN projects p ON p.id = n.project_id "
        f"WHERE n.user_id = ?{where}{' AND n.id < ?' if before else ''} ORDER BY n.id DESC LIMIT ?",
        (session["user_id"], *params, *([before] if before else []), limit + 1),
    ).fetchall()
    more, rows = len(rows) > limit, rows[:limit]
    unread = get_db().execute(f"SELECT COUNT(*) FROM notifications n WHERE n.user_id = ? AND n.read_at IS NULL{where}", (session["user_id"], *params)).fetchone()[0]
    return jsonify(unread=unread, more=more, rows=[{
        "id": r["id"], "kind": r["kind"], "title": r["title"], "body": r["body"], "link": r["link"], "actor": r["actor"],
        "project_name": r["project_name"], "created_at": r["created_at"], "read": r["read_at"] is not None, "muted": bool(r["muted"]),
    } for r in rows])


@app.route("/api/notifications/read", methods=["POST"])
@login_required
def api_notifications_read():
    """Mark one (id) or all of this user's notifications read. Only ever the
    caller's own rows."""
    from services.notifications import visible_clause
    body = json_body()
    db = get_db()
    now = datetime.utcnow().isoformat()
    # what the bell shows, no more (test report FN-14): hidden rows are neither marked nor counted
    where, vis = visible_clause(session["user_id"], session.get("kind"))
    if body.get("all"):
        db.execute(f"UPDATE notifications AS n SET read_at = ? WHERE n.user_id = ? AND n.read_at IS NULL{where}", (now, session["user_id"], *vis))
    elif as_id(body.get("id")):
        db.execute("UPDATE notifications SET read_at = ? WHERE id = ? AND user_id = ? AND read_at IS NULL", (now, as_id(body["id"]), session["user_id"]))
    else:
        return jsonify(error="Say which: {id} or {all: true}"), 400
    db.commit()
    return jsonify(ok=True, unread=db.execute(f"SELECT COUNT(*) FROM notifications n WHERE n.user_id = ? AND n.read_at IS NULL{where}", (session["user_id"], *vis)).fetchone()[0])


@app.route("/api/search")
@permission_required("view_projects")
def api_search():
    """The command palette: projects by name, client or PO, tasks by title,
    and the words inside notes, RAID items, scope items and uploaded
    documents (services/doctext), within what this session may see:
    externals only their projects, and of those only what is shown to them."""
    q = request.args.get("q", "").strip()[:100]
    if len(q) < 2:
        return jsonify(projects=[], tasks=[], mentions=[])
    db = get_db()
    like = like_any(q)
    scope_sql, scope_params = project_scope()
    external = session.get("kind") == "external"
    projects = db.execute(   # partners never see the PO, so it is not searched for them
        f"SELECT p.id, p.name, p.client, p.stage FROM projects p WHERE p.deleted_at IS NULL{scope_sql} "
        "AND (p.name LIKE ? ESCAPE '\\' OR p.client LIKE ? ESCAPE '\\'" + ("" if external else " OR p.po_number LIKE ? ESCAPE '\\'") + ") ORDER BY p.updated_at DESC LIMIT 8",
        (*scope_params, like, like, *([] if external else [like])),
    ).fetchall()
    own, own_params = (" AND t.assignee_id = ?", [session["user_id"]]) if external else ("", [])   # a partner finds only their own asks
    tasks = db.execute(
        f"SELECT t.id, t.title, t.done, t.project_id, p.name AS project_name FROM tasks t JOIN projects p ON p.id = t.project_id "
        f"WHERE p.deleted_at IS NULL{scope_sql}{own} AND t.title LIKE ? ESCAPE '\\' ORDER BY t.done, t.id DESC LIMIT 8",
        (*scope_params, *own_params, like),
    ).fetchall()
    sources = (
        ("note", "/projects/{pid}", f"SELECT n.project_id, p.name AS project_name, n.note AS text, n.created_at AS at FROM status_notes n JOIN projects p ON p.id = n.project_id "
                                    f"WHERE p.deleted_at IS NULL{scope_sql} AND n.prev_stage IS NULL AND n.note LIKE ? ESCAPE '\\'{' AND n.guest_visible = 1' if external else ''}"),
        ("risk", "/projects/{pid}#raid", f"SELECT r.project_id, p.name AS project_name, r.title || ': ' || COALESCE(r.detail, '') || ' ' || COALESCE(r.resolution, '') AS text, r.updated_at AS at "
                                         f"FROM raid_items r JOIN projects p ON p.id = r.project_id WHERE p.deleted_at IS NULL{scope_sql} "
                                         f"AND (r.title LIKE ? ESCAPE '\\' OR r.detail LIKE ? ESCAPE '\\' OR r.resolution LIKE ? ESCAPE '\\'){' AND r.customer_visible = 1' if external else ''}"),
        ("scope", "/projects/{pid}#scope", f"SELECT s.project_id, p.name AS project_name, s.title || ': ' || COALESCE(s.detail, '') || ' ' || COALESCE(s.note, '') AS text, p.updated_at AS at "
                                           f"FROM scope_items s JOIN projects p ON p.id = s.project_id WHERE p.deleted_at IS NULL{scope_sql} AND (s.title LIKE ? ESCAPE '\\' OR s.detail LIKE ? ESCAPE '\\' OR s.note LIKE ? ESCAPE '\\')"),
        ("document", "/projects/{pid}", f"SELECT d.project_id, p.name AS project_name, d.filename || ': ' || t.text AS text, d.uploaded_at AS at FROM doc_text t "
                                        f"JOIN documents d ON d.id = t.document_id AND d.deleted_at IS NULL JOIN projects p ON p.id = d.project_id "
                                        f"LEFT JOIN doc_categories c ON c.name = d.category WHERE p.deleted_at IS NULL{scope_sql} AND t.text LIKE ? ESCAPE '\\'"
                                        f"{' AND COALESCE(c.partners, 0) = 1' if external else ''}"),
    )
    mentions = []
    for kind, link, sql in sources:
        for r in db.execute(sql + " ORDER BY at DESC LIMIT 6", (*scope_params, *([like] * sql.count("LIKE ?")))):
            text = r["text"] or ""
            at = text.lower().find(q.lower())
            start = max(0, at - 70)
            snippet = ("…" if start else "") + " ".join(text[start:at + len(q) + 90].split()) + ("…" if at + len(q) + 90 < len(text) else "")
            mentions.append({"kind": kind, "project_id": r["project_id"], "project_name": r["project_name"], "snippet": snippet,
                             "href": link.format(pid=r["project_id"])})
    return jsonify(projects=[dict(r) for r in projects], tasks=[dict(r) | {"done": bool(r["done"])} for r in tasks], mentions=mentions[:16])


# The brand files at the site root: favicon, home-screen icon, link preview.
@app.route("/<any('favicon.svg', 'apple-touch-icon.png', 'og.png'):name>")
def favicon(name):
    from flask import send_from_directory
    from spa import DIST_DIR
    import os
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "public")
    folder = DIST_DIR if os.path.exists(os.path.join(DIST_DIR, name)) else here
    return send_from_directory(folder, name, max_age=86400)


@app.route("/assets/<path:filename>")
def spa_assets(filename):
    return spa_asset(filename)
