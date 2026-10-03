"""Dashboard + alerts views: the board (kanban + stats), the alerts log, and
per-project alert dismissal. Imported for route registration side effects.
"""
from flask import abort, redirect, render_template, request, session, url_for

from constants import ALERT_TYPES, ALERT_TYPE_TITLES
from core import app, login_required, permission_required, project_scope
from db import PROJECT_OPEN_SQL, get_db, get_stage_names, get_terminal_stage, stages_for_projects
from services.analytics import build_cycle_times
from spa import spa_index, spa_serves
from services.alerts import (
    alert_context_for,
    build_alerts,
    build_dashboard,
    get_dismissed_alerts,
    schedule_status,
    sync_alerts_to_db,
)

ALERTS_PER_PAGE = 50
# How many project names the board banner lists inline before collapsing to a
# count. At 400+ projects the uncapped banner was 2,443px — 3.4 screens — of
# names above the first number on the page.
BANNER_NAMES = 5
# Cards rendered per kanban column before collapsing to a link. Projects arrive
# ordered by updated_at DESC, so the visible slice is the most recently touched
# — the ones anyone scanning a column actually wants. At 431 active projects one
# column held 73 cards and stood 7,407px tall.
COLUMN_CARDS = 20


@app.route("/dashboard")
@permission_required("view_board")
def dashboard():
    """The portfolio this week — a React page only; without a build, the flow stands in."""
    if spa_serves("dashboard"):
        return spa_index()
    return redirect(url_for("board"))


@app.route("/people")
@permission_required("view_board")
def people():
    """The people directory — a React page only; without a build, the flow stands in."""
    if session.get("kind") == "external":
        abort(403)
    if spa_serves("people"):
        return spa_index()
    return redirect(url_for("board"))


@app.route("/people/<int:user_id>")
@permission_required("view_board")
def person(user_id):
    if session.get("kind") == "external":
        abort(403)
    if spa_serves("person"):
        return spa_index()
    return redirect(url_for("board"))


@app.route("/my-work")
@login_required
def my_work():
    if spa_serves("my_work"):
        return spa_index()
    db = get_db()
    uid = session["user_id"]
    from datetime import datetime as _dt
    from policies import local_today
    today = local_today().isoformat()

    owned = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE p.owner_id = ? AND p.deleted_at IS NULL AND {PROJECT_OPEN_SQL}{project_scope()[0]} ORDER BY p.updated_at DESC",
        (uid, *project_scope()[1]),
    ).fetchall()
    my_projects = [{"project": p, "schedule": schedule_status(p)} for p in owned]

    my_tasks = db.execute(
        "SELECT t.*, p.name AS project_name FROM tasks t JOIN projects p ON p.id = t.project_id "
        "WHERE t.assignee_id = ? AND t.done = 0 AND p.deleted_at IS NULL "
        "ORDER BY t.due_date IS NULL, t.due_date ASC, t.id ASC",
        (uid,),
    ).fetchall()

    overdue_count = sum(1 for row in my_projects if row["schedule"] == "overdue")
    return render_template(
        "my_work.html",
        my_projects=my_projects,
        my_tasks=my_tasks,
        overdue_count=overdue_count,
        today=today,
    )


def board_data():
    """Everything the board shows, for Jinja and React alike."""
    db = get_db()
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id) AS task_total, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.done = 1) AS task_done "
        "FROM projects p "
        "JOIN users u ON u.id = p.owner_id "
        f"WHERE {PROJECT_OPEN_SQL} AND p.deleted_at IS NULL{project_scope()[0]} ORDER BY p.updated_at DESC",
        project_scope()[1],
    ).fetchall()
    stages_for_projects([p["id"] for p in projects])   # bulk-inserted projects adopt a list here
    columns = {stage: [] for stage in get_stage_names()}
    for p in projects:
        columns.setdefault(p["stage"], []).append(p)
    # notifications (the alerts banner) respect this login's dismissals;
    # the real_alerts counts feeding the stat tiles never do — dismissing a
    # notification hides it from the banner, it doesn't change the real data
    real_alerts = build_alerts(projects)
    if not project_scope()[0]:   # only a view of every project may resolve alerts; a partner's narrow view would close the rest
        sync_alerts_to_db(real_alerts)
    alerts = build_alerts(projects, get_dismissed_alerts())
    dashboard = build_dashboard(projects)
    outside = session.get("kind") == "external"   # partners: their projects, customer-visible notes only
    recent_notes = db.execute(
        "SELECT sn.*, p.name AS project_name, p.id AS project_id FROM status_notes sn "
        "JOIN projects p ON p.id = sn.project_id WHERE p.deleted_at IS NULL"
        + (" AND sn.guest_visible = 1" if outside else "") + project_scope()[0] + " ORDER BY sn.created_at DESC LIMIT 8",
        project_scope()[1],
    ).fetchall()
    return {
        "columns": columns, "alerts": alerts, "real_alerts": real_alerts,
        "dashboard": dashboard, "recent_notes": recent_notes,
    }


@app.route("/board")
@permission_required("view_board")
def board():
    if spa_serves("board"):
        return spa_index()
    return render_template("board.html", **board_data(), banner_names=BANNER_NAMES, column_cards=COLUMN_CARDS)


def dismiss_alert(project_id, alert_type):
    """Session-only: real project data is never touched, and this clears
    itself out the next time the user logs in. Shared by the GET link on the
    Jinja board and the JSON route."""
    if alert_type not in ALERT_TYPES:
        abort(404)
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    if project is None:
        abort(404)
    dismissed = dict(session.get("dismissed_alerts", {}))
    dismissed[f"{project_id}:{alert_type}"] = alert_context_for(project, alert_type)
    session["dismissed_alerts"] = dismissed


@app.route("/analytics")
@permission_required("view_reports")
def analytics():
    """Where projects actually get stuck. Reuses view_reports rather than
    minting a new permission — this is a report, and every permission in the
    matrix has to be enforced somewhere (see the RBAC guard test)."""
    # Stage timings only compare across projects that share a stage list, so
    # the report is per template. Projects on a bespoke list are their own
    # history and are counted in the picker as "custom".
    if spa_serves("analytics"):
        return spa_index()
    db = get_db()
    templates = db.execute("SELECT id, name FROM stage_templates ORDER BY id").fetchall()
    template_id = request.args.get("template", type=int) or (templates[0]["id"] if templates else None)
    template = next((t for t in templates if t["id"] == template_id), None)
    projects = db.execute(
        "SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id "
        f"WHERE p.deleted_at IS NULL AND p.stage_template_id IS ?{project_scope()[0]}", (template_id, *project_scope()[1])
    ).fetchall()
    notes_by_project = {}
    for note in db.execute("SELECT project_id, stage, created_at FROM status_notes ORDER BY created_at"):
        notes_by_project.setdefault(note["project_id"], []).append(note)
    stage_rows_ = db.execute(
        "SELECT name, sla_days FROM stage_template_stages WHERE template_id = ? ORDER BY position", (template_id,)
    ).fetchall() if template_id else []
    names = [r["name"] for r in stage_rows_]
    slas = {r["name"]: r["sla_days"] for r in stage_rows_}
    stats = build_cycle_times(projects, notes_by_project, names, names[-1] if names else None) if names else None
    custom = db.execute("SELECT COUNT(*) FROM projects WHERE deleted_at IS NULL AND stage_template_id IS NULL").fetchone()[0]
    return render_template("analytics.html", stats=stats, slas=slas, templates=templates, template=template, custom_count=custom)


@app.route("/alerts")
@login_required
def alerts_log_view():
    """The full alert list. Paginated because it is unbounded: one row per
    (project, condition), so a few hundred projects can put a thousand rows on
    a single page. The board banner links here with ?type= to drill into one
    kind rather than listing every project inline.
    """
    if spa_serves("alerts_log_view"):
        return spa_index()
    return render_template("alerts_log.html", **alerts_page_data())


def alerts_page_data():
    """The alert list for Jinja and JSON alike."""
    db = get_db()
    show_resolved = request.args.get("resolved") == "1"
    alert_type = request.args.get("type", "")
    if alert_type not in ALERT_TYPES:
        alert_type = ""
    page = max(1, request.args.get("page", 1, type=int))

    where, params = [], []
    if not show_resolved:
        where.append("a.resolved = 0")
    if alert_type:
        where.append("a.alert_type = ?")
        params.append(alert_type)
    if session.get("kind") == "external":   # a partner sees alerts on their own projects only
        where.append("a.project_id IN (SELECT project_id FROM project_participants WHERE user_id = ?)")
        params.append(session["user_id"])
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    order = ("a.resolved ASC, " if show_resolved else "") + \
            "CASE a.severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, a.created_at DESC"

    total = db.execute(f"SELECT COUNT(*) AS c FROM alerts a{clause}", params).fetchone()["c"]
    total_pages = max(1, (total + ALERTS_PER_PAGE - 1) // ALERTS_PER_PAGE)
    page = min(page, total_pages)
    rows = db.execute(
        f"SELECT a.*, p.name AS project_name FROM alerts a "
        f"LEFT JOIN projects p ON p.id = a.project_id{clause} "
        f"ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, ALERTS_PER_PAGE, (page - 1) * ALERTS_PER_PAGE),
    ).fetchall()

    return dict(alerts=rows, show_resolved=show_resolved, alert_type=alert_type, alert_type_titles=ALERT_TYPE_TITLES,
                page=page, total_pages=total_pages, total=total)


@app.route("/alerts/<int:project_id>/dismiss/<alert_type>")
@login_required
def alert_dismiss(project_id, alert_type):
    from routes.projects import load_project
    load_project(project_id)   # 404 unless the caller may see it (test report SEC-8: a redirect told a partner which ids exist)
    dismiss_alert(project_id, alert_type)
    if request.args.get("next") == "board":
        return redirect(url_for("board") + "#alerts")
    return redirect(url_for("project_detail", project_id=project_id))
