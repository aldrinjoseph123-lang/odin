"""Alert engine + dashboard aggregation.

build_alerts() is pure computation over a list of project rows — it takes an
optional session-scoped `dismissed` map but never reads the session itself, so
the daily cron (send_daily_alerts.py) can call it with no request context.
sync_alerts_to_db() persists the computed conditions and fires notifications.

Depends on db, constants, and services.notifications. Nothing lower imports it.
"""
from datetime import date, datetime, timedelta

from flask import session
from markupsafe import escape

from constants import (
    ALERT_TYPE_TITLES,
    DEFAULT_ALERT_TYPE_SETTINGS,
    DELIVERY_MODES,
)
from policies import local_today
from db import get_db, get_stage_names, get_terminal_stage, stages_for_projects
from services.analytics import sla_by_stage, stage_sla_state
from services.notifications import notify_event, notify_users


def create_alert(alert_type, project_id, title, description=None, severity="info"):
    """Create an alert. Returns True only if this call actually inserted one.

    OR IGNORE against the partial unique index makes concurrent board loads
    safe: whichever request loses the race inserts nothing and gets False, so
    the notification fires once rather than once per racing request.
    """
    db = get_db()
    created_at = datetime.utcnow().isoformat()
    cursor = db.execute(
        "INSERT OR IGNORE INTO alerts (alert_type, project_id, title, description, severity, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (alert_type, project_id, title, description, severity, created_at),
    )
    db.commit()
    return cursor.rowcount > 0


def resolve_alert(alert_type, project_id):
    """Mark alerts of a type for a project as resolved."""
    db = get_db()
    resolved_at = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE alerts SET resolved = 1, resolved_at = ? WHERE alert_type = ? AND project_id = ? AND resolved = 0",
        (resolved_at, alert_type, project_id),
    )
    db.commit()


def get_active_alerts():
    """Get all unresolved alerts ordered by severity."""
    db = get_db()
    return db.execute(
        "SELECT * FROM alerts WHERE resolved = 0 ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, created_at DESC"
    ).fetchall()


def get_alert_type_settings():
    """Per-type threshold/severity/delivery config, keyed by alert_type."""
    db = get_db()
    rows = db.execute("SELECT * FROM alert_type_settings").fetchall()
    return {
        row["alert_type"]: {
            "severity": row["severity"],
            "threshold_days": row["threshold_days"],
            "notify_email": bool(row["notify_email"]),
            "notify_teams": bool(row["notify_teams"]),
            "notify_inapp": bool(row["notify_inapp"]),
        }
        for row in rows
    }


def sync_alerts_to_db(alerts):
    """Persist alert conditions to database. Create alerts for new issues, resolve ones that
    cleared, and fire email/Teams notifications for newly-created alerts per the type's config."""
    db = get_db()
    alert_settings = get_alert_type_settings()

    for alert_type, projects in alerts.items():
        if alert_type not in ALERT_TYPE_TITLES:
            continue
        config = alert_settings.get(alert_type, DEFAULT_ALERT_TYPE_SETTINGS[alert_type])
        id_to_project = {p["id"]: p for p in projects}
        # in-app is the master switch: off means no persisted alert at all,
        # so email/teams (which fire off the persisted-alert transition) go quiet too
        project_ids_with_alert = set(id_to_project) if config["notify_inapp"] else set()

        # Get existing unresolved alerts of this type
        existing = db.execute(
            "SELECT * FROM alerts WHERE alert_type = ? AND resolved = 0", (alert_type,)
        ).fetchall()
        existing_ids = {row["project_id"] for row in existing}

        # Create alerts for new issues (skipped entirely when the type is disabled)
        for project_id in project_ids_with_alert - existing_ids:
            inserted = create_alert(
                alert_type, project_id, ALERT_TYPE_TITLES[alert_type], severity=config["severity"]
            )
            if inserted:
                project = id_to_project[project_id]
                title, body = ALERT_TYPE_TITLES[alert_type], f"Project: {escape(project['name'])} ({escape(project['client'])})"
                # the AI's plain-words reason and first move, when one was written in the last day and a half (services/ai)
                from services.ai import latest_project
                why = latest_project("health_explained", project_id, db)
                if why:
                    body += f"<p>{escape(why['why'])}</p><p><b>First move:</b> {escape(why['first_move'])}</p><p style='color:#6B7280'>Written by AI from Odin's figures.</p>"
                # the owner and the staff on the project: always in the bell, by
                # email when the type says so (each person's email choices apply)
                team = [r[0] for r in db.execute(
                    "SELECT pp.user_id FROM project_participants pp JOIN users u ON u.id = pp.user_id WHERE pp.project_id = ? AND u.kind = 'internal'", (project_id,))]
                notify_users([project["owner_id"], *team], "alert", project_id, f"{title}: {escape(project['name'])}", body, email=config["notify_email"])
                if config["notify_teams"]:
                    notify_event(project, title, body, channels={"email": False, "teams": True})

        # Resolve alerts for issues that cleared (or all of them, if the type got disabled)
        for alert_row in existing:
            if alert_row["project_id"] not in project_ids_with_alert:
                resolve_alert(alert_type, alert_row["project_id"])


def alert_context_for(project, alert_type):
    """The field whose value must stay unchanged for a dismissal to still apply —
    if it changes (project touched again), the alert is treated as new and
    reappears even though a dismissal row still exists."""
    if alert_type == "stale":
        return project["updated_at"]
    if alert_type in ("project_overdue", "project_due_soon"):
        return project["target_end_date"]
    if alert_type == "stage_sla_breach":
        # dismissal survives until the project moves on to another stage
        return project["stage_entered_at"]
    if alert_type == "approval_waiting":
        return project["stage"]   # until the next stage's approval
    return None


def _bottlenecks(project_ids, thresholds, today):
    """Per project, which bottleneck rules hold: an approval waiting, a
    blocker left open, an overdue task nobody owns, a customer task overdue.
    One query each over all the projects."""
    from datetime import timedelta as _td
    if not project_ids:
        return {}
    db = get_db()
    days = {k: thresholds.get(k, DEFAULT_ALERT_TYPE_SETTINGS[k])["threshold_days"] or 0
            for k in ("approval_waiting", "blocker_open", "task_unowned", "customer_quiet")}
    before = lambda k: (today - _td(days=days[k])).isoformat()   # noqa: E731
    marks = ",".join("?" * len(project_ids))
    hits = {}
    for (rule, sql, cutoff) in (
        ("approval_waiting", f"SELECT DISTINCT a.project_id FROM stage_approvals a JOIN projects p ON p.id = a.project_id "
                             f"WHERE a.status = 'pending' AND a.stage = p.stage AND substr(a.requested_at, 1, 10) <= ? AND a.project_id IN ({marks})", before("approval_waiting")),
        ("blocker_open", f"SELECT DISTINCT project_id FROM raid_items WHERE kind = 'blocker' AND status NOT IN ('closed', 'decided') "
                         f"AND substr(created_at, 1, 10) <= ? AND project_id IN ({marks})", before("blocker_open")),
        ("task_unowned", f"SELECT DISTINCT project_id FROM tasks WHERE done = 0 AND assignee_id IS NULL AND due_date IS NOT NULL "
                         f"AND due_date < ? AND project_id IN ({marks})", before("task_unowned")),
        ("customer_quiet", f"SELECT DISTINCT t.project_id FROM tasks t JOIN project_participants pp ON pp.project_id = t.project_id AND pp.user_id = t.assignee_id "
                           f"WHERE t.done = 0 AND pp.role = 'Customer' AND t.due_date IS NOT NULL AND t.due_date < ? AND t.project_id IN ({marks})", before("customer_quiet")),
    ):
        for (pid,) in db.execute(sql, (cutoff, *project_ids)):
            hits.setdefault(pid, set()).add(rule)
    return hits


def schedule_status(project, today=None, soon_days=None, terminal_stage=None):
    """Health of a project against its target end date: 'overdue', 'at_risk'
    (within soon_days), 'on_track', or None (no target date, or already in the
    terminal stage where a deadline no longer applies)."""
    if not project["target_end_date"]:
        return None
    if (terminal_stage or get_terminal_stage(project["id"])) == project["stage"]:
        return None
    today = today or local_today()
    if soon_days is None:
        soon_days = get_alert_type_settings().get(
            "project_due_soon", DEFAULT_ALERT_TYPE_SETTINGS["project_due_soon"]
        )["threshold_days"]
    target = date.fromisoformat(project["target_end_date"])
    if target < today:
        return "overdue"
    if target <= today + timedelta(days=soon_days):
        return "at_risk"
    return "on_track"


def get_dismissed_alerts():
    """Session-scoped only — never touches the database or real project data.
    Resets to empty on every fresh login, so a dismissed alert reappears the
    next time the user logs in even if the underlying condition hasn't changed."""
    return session.get("dismissed_alerts", {})


def is_alert_dismissed(dismissed, project, alert_type):
    key = f"{project['id']}:{alert_type}"
    if key not in dismissed:
        return False
    return dismissed[key] == alert_context_for(project, alert_type)


def build_alerts(projects, dismissed=None):
    dismissed = dismissed or {}
    thresholds = get_alert_type_settings()
    stale_cutoff = datetime.utcnow() - timedelta(days=thresholds.get("stale", DEFAULT_ALERT_TYPE_SETTINGS["stale"])["threshold_days"])
    soon_days = thresholds.get("project_due_soon", DEFAULT_ALERT_TYPE_SETTINGS["project_due_soon"])["threshold_days"]
    today = local_today()
    stage_lists = stages_for_projects([p["id"] for p in projects])
    alerts = {"project_overdue": [], "project_due_soon": [], "stage_sla_breach": [], "stale": [],
              "approval_waiting": [], "blocker_open": [], "task_unowned": [], "customer_quiet": []}
    bottlenecks = _bottlenecks([p["id"] for p in projects], thresholds, today)
    for p in projects:
        rows = stage_lists.get(p["id"]) or []
        terminal = rows[-1]["name"] if rows else None
        slas = sla_by_stage(rows)
        status = schedule_status(p, today=today, soon_days=soon_days, terminal_stage=terminal)
        if status == "overdue" and not is_alert_dismissed(dismissed, p, "project_overdue"):
            alerts["project_overdue"].append(p)
        elif status == "at_risk" and not is_alert_dismissed(dismissed, p, "project_due_soon"):
            alerts["project_due_soon"].append(p)
        sla = stage_sla_state(p, slas, terminal, now=datetime.utcnow())
        if sla and sla["breached"] and not is_alert_dismissed(dismissed, p, "stage_sla_breach"):
            alerts["stage_sla_breach"].append(p)
        if datetime.fromisoformat(p["updated_at"]) < stale_cutoff and not is_alert_dismissed(dismissed, p, "stale"):
            alerts["stale"].append(p)
        for rule in bottlenecks.get(p["id"], ()):
            if not is_alert_dismissed(dismissed, p, rule):
                alerts[rule].append(p)
    return alerts


def project_states(projects, alerts=None):
    """project id -> overdue | over_sla | due_soon | on_track: one state each,
    in the Flow's order (routes/api._flow_state), so every count agrees."""
    alerts = build_alerts(projects) if alerts is None else alerts
    stuck = {"overdue": {p["id"] for p in alerts["project_overdue"]}, "over_sla": {p["id"] for p in alerts["stage_sla_breach"]},
             "due_soon": {p["id"] for p in alerts["project_due_soon"]}}
    return {p["id"]: next((k for k in ("overdue", "over_sla", "due_soon") if p["id"] in stuck[k]), "on_track") for p in projects}


def build_dashboard(projects):
    stage_counts = {stage: 0 for stage in get_stage_names()}
    delivery_counts = {mode: 0 for mode in DELIVERY_MODES}
    for p in projects:
        stage_counts[p["stage"]] = stage_counts.get(p["stage"], 0) + 1
        delivery_counts[p["delivery_mode"]] = delivery_counts.get(p["delivery_mode"], 0) + 1
    max_stage_count = max(stage_counts.values()) if stage_counts else 0
    return {
        "stage_counts": stage_counts,
        "max_stage_count": max_stage_count,
        "delivery_counts": delivery_counts,
        "total_active": len(projects),
    }
