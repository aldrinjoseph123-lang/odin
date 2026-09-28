"""Admin-editable policy: every value an admin can change, defined once.

Each entry says which Settings area it belongs to, what kind of value it is,
its default and its limits. The value lives in the `settings` table under
"policy.<key>"; a missing or unparseable row reads as the default, so a fresh
install and an old one behave the same until an admin changes something.

Code reads values with policy("key") — typed, and cached for the request.
The settings page is generated from POLICIES, and save_policies() is the one
validator, so the form, the API and the code can never disagree on a limit.
"""

import re
from zoneinfo import available_timezones

from flask import g, has_request_context

from db import get_db

# Uploads an admin may allow. Only types the magic-byte check in security.py
# understands; an admin can narrow this, never widen it.
UPLOAD_TYPES = ("pdf", "png", "jpg", "jpeg", "gif", "webp", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "txt", "msg", "eml", "zip")
DATE_FORMATS = {"d MMM yyyy": "27 Sep 2026", "yyyy-MM-dd": "2026-09-27", "dd/MM/yyyy": "27/09/2026", "MM/dd/yyyy": "09/27/2026"}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
THEME_CHOICES = ("system", "light", "dark")
ACCENT_CHOICES = ("blue", "indigo", "violet", "teal", "green", "sky", "plum", "ink")

POLICIES = {
    # ---- General
    "company_name": dict(area="general", kind="text", default="Protect24x7", max=80,
                         label="Company name", help="Shown in email footers and on printed reports."),
    "public_url": dict(area="general", kind="url", default="", max=200,
                       label="Public web address", help="e.g. https://odin.example.com. Sign-in and emailed links are built from it, never from the request. Blank: the address the browser used."),
    "timezone": dict(area="general", kind="choice", default="Asia/Dubai", choices="timezones",
                     label="Time zone", help="Decides \"today\" for due dates and when scheduled jobs run."),
    "date_format": dict(area="general", kind="choice", default="d MMM yyyy", choices=tuple(DATE_FORMATS),
                        label="Date format", help="How dates read across the app."),
    "working_days": dict(area="general", kind="multi", default="Mon,Tue,Wed,Thu,Fri", choices=WEEKDAYS,
                         label="Working week", help="Reminders and digests go out on these days only."),
    "default_theme": dict(area="general", kind="choice", default="system", choices=THEME_CHOICES,
                          label="Theme for new people", help="Each person can change their own on the Account page."),
    "default_accent": dict(area="general", kind="choice", default="blue", choices=ACCENT_CHOICES,
                           label="Accent for new people", help="Each person can change their own on the Account page."),
    # ---- Sign-in & security
    "session_idle_minutes": dict(area="security", kind="int", default=60, min=5, max=1440,
                                 label="Sign out after inactivity (minutes)", help="No request for this long ends the session."),
    "session_max_hours": dict(area="security", kind="int", default=12, min=1, max=168,
                              label="Longest session (hours)", help="Sign in again after this, however active."),
    "password_min_length": dict(area="security", kind="int", default=12, min=12, max=64,
                                label="Minimum password length", help="For accounts allowed to sign in with a password."),
    "login_max_attempts": dict(area="security", kind="int", default=5, min=3, max=20,
                               label="Failed sign-ins before a pause", help="Per username and network address."),
    "login_window_minutes": dict(area="security", kind="int", default=15, min=5, max=120,
                                 label="Pause length (minutes)", help="Failures older than this stop counting."),
    "upload_max_mb": dict(area="security", kind="int", default=25, min=1, max=100,
                          label="Largest upload (MB)", help="Per file. The server never accepts more than 100 MB."),
    "upload_types": dict(area="security", kind="multi", default=",".join(UPLOAD_TYPES), choices=UPLOAD_TYPES,
                         label="Allowed file types", help="Untick a type to refuse it. Types the server cannot verify are never offered."),
    "link_minutes": dict(area="security", kind="int", default=30, min=5, max=1440,
                         label="Email link lifetime (minutes)", help="Partner sign-in links and password-reset links work once, for this long."),
    "external_domains": dict(area="security", kind="domains", default="", max=500,
                             label="Partner email domains", help="e.g. partner.com, vendor.ae. Only these can be invited or sent a sign-in link. Blank: any domain."),
    "undo_minutes": dict(area="security", kind="int", default=5, min=1, max=60,
                         label="Undo window (minutes)", help="How long deletes and stage moves can be undone."),
    # ---- Notifications
    "digest_time": dict(area="notifications", kind="time", default="08:00",
                        label="Daily digest and reminders at", help="Workspace time zone, working days only. Needs the scheduler service running."),
    "teams_webhook_url": dict(area="notifications", kind="url", default="", max=500,
                              label="Teams Workflows webhook", help="From a Teams channel: Workflows → \"Post to a channel when a webhook request is received\". Stage changes, decisions and the weekly report are posted here too. Blank: channel posts only."),
    # ---- Reports
    "report_enabled": dict(area="reports", kind="bool", default=False,
                           label="Send the weekly report", help="Stuck and overdue rollouts first, stages moved this week, due next week, counts per stage."),
    "report_days": dict(area="reports", kind="multi", default="Mon", choices=WEEKDAYS,
                        label="On these days", help="Usually one day a week."),
    "report_time": dict(area="reports", kind="time", default="09:00",
                        label="At", help="Workspace time zone."),
    "report_roles": dict(area="reports", kind="multi", default="Admin", choices=("Admin", "Member", "Contributor", "Viewer"),
                         label="To everyone with these roles", help="Active staff with an email address. Partners never receive it."),
    "report_emails": dict(area="reports", kind="emails", default="", max=1000,
                          label="And these addresses", help="e.g. ceo@company.com, delivery@company.com"),
    "report_attach": dict(area="reports", kind="bool", default=False,
                          label="Attach each active project's latest saved report as a PDF", help="Only projects with a saved report version."),
    "report_teams": dict(area="reports", kind="bool", default=False,
                         label="Also post a summary to Teams", help="The channel chosen under Integrations and/or the Workflows webhook under Notifications."),
    # ---- Audit & compliance
    "audit_keep": dict(area="audit", kind="choice", default="3", choices=("1", "2", "3", "5", "7", "forever"),
                       label="Keep audit log rows for (years)", help="Older rows are written to a CSV archive (kept with the backups) and then removed, nightly. At least a year: SOC 2 asks for 12 months."),
    # ---- Backups
    "backup_time": dict(area="backups", kind="time", default="02:00",
                        label="Back up at", help="Workspace time zone."),
    "backup_days": dict(area="backups", kind="multi", default=",".join(WEEKDAYS), choices=WEEKDAYS,
                        label="On these days", help="Untick days to skip."),
    "keep_daily": dict(area="backups", kind="int", default=7, min=1, max=60,
                       label="Keep daily copies", help="The newest backup of each of the last N days."),
    "keep_weekly": dict(area="backups", kind="int", default=4, min=0, max=52,
                        label="Keep weekly copies", help="The newest of each of the last N weeks."),
    "keep_monthly": dict(area="backups", kind="int", default=12, min=0, max=60,
                         label="Keep monthly copies", help="The newest of each of the last N months. Applied here and at every destination."),
    "restore_test": dict(area="backups", kind="bool", default=True,
                         label="Test each backup by restoring it", help="Opens the copy, checks the database is intact and every document is inside; the result is kept below."),
    "dest_onedrive": dict(area="backups", kind="bool", default=False,
                          label="Copy to OneDrive", help="The connected Microsoft 365 account's OneDrive, folder Odin-Backups."),
    "dest_sharepoint": dict(area="backups", kind="bool", default=False,
                            label="Copy to a SharePoint site", help="Needs the Microsoft 365 connection with SharePoint access (reconnect once after turning this on)."),
    "sharepoint_site": dict(area="backups", kind="url", default="", max=200,
                            label="SharePoint site", help="e.g. https://contoso.sharepoint.com/sites/IT"),
    "sharepoint_folder": dict(area="backups", kind="text", default="Odin-Backups", max=120, optional=True,
                              label="Folder in its Documents library", help="Created if missing."),
    "dest_share": dict(area="backups", kind="bool", default=False,
                       label="Copy to a network share", help="A NAS or file-server folder mounted into the server (SMB/NFS)."),
    "share_path": dict(area="backups", kind="text", default="", max=200, optional=True,
                       label="Share folder path", help="The absolute path where the share is mounted, e.g. /mnt/nas/odin."),
    # ---- Projects & workflow
    "default_template": dict(area="workflow", kind="choice", default="", choices="templates",
                             label="Stage template for new projects", help="Pre-selected on the new project form."),
    "default_customer_approval": dict(area="workflow", kind="bool", default=False,
                                      label="Ask the customer to approve each stage by default",
                                      help="Pre-ticked on the new project form; each project can still change it."),
}


def _choices(entry):
    c = entry.get("choices")
    if c == "timezones":
        return sorted(available_timezones())
    if c == "templates":
        return [str(r["id"]) for r in get_db().execute("SELECT id FROM stage_templates ORDER BY id")]
    return list(c or ())


def _parse(entry, raw):
    """Typed value from a stored/posted string, or raise ValueError."""
    kind = entry["kind"]
    if kind == "int":
        v = int(str(raw).strip())
        if not entry["min"] <= v <= entry["max"]:
            raise ValueError(f"between {entry['min']} and {entry['max']}")
        return v
    if kind == "bool":
        return str(raw) in ("1", "on", "true", "True")
    if kind == "multi":
        picked = [p for p in str(raw).split(",") if p]
        allowed = _choices(entry)
        if any(p not in allowed for p in picked):
            raise ValueError("pick from the list")
        return [p for p in allowed if p in picked]   # canonical order
    v = str(raw).strip()
    if kind == "url":
        v = v.rstrip("/")
        if v and (len(v) > entry["max"] or not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d+)?(/[\w./-]*)?", v)):
            raise ValueError("a web address like https://odin.example.com")
        return v
    if kind == "emails":
        parts = sorted({p.lower() for p in re.split(r"[\s,;]+", v) if p})
        if len(",".join(parts)) > entry["max"] or any(not re.fullmatch(r"[^@\s]+@[a-z0-9-]+(\.[a-z0-9-]+)+", p) for p in parts):
            raise ValueError("email addresses separated by commas")
        return parts
    if kind == "domains":
        parts = sorted({p.lower().lstrip("@") for p in re.split(r"[\s,;]+", v) if p})
        if len(",".join(parts)) > entry["max"] or any(not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", p) for p in parts):
            raise ValueError("domains like partner.com, separated by commas")
        return parts
    if kind == "time":
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("a time like 08:00")
        return v
    if kind == "text":
        if (not v and not entry.get("optional")) or len(v) > entry["max"]:
            raise ValueError(f"up to {entry['max']} characters" if entry.get("optional") else f"1 to {entry['max']} characters")
        return v
    if kind == "choice":
        if v not in _choices(entry) and not (entry["choices"] == "templates" and v == ""):   # "" = the first template
            raise ValueError("pick from the list")
        return v
    raise ValueError("unknown kind")


def _default(entry):
    d = entry["default"]
    return _parse(entry, d) if entry["kind"] in ("multi", "domains", "emails") else d


def _stored(db=None):
    if db is None and has_request_context() and "policy_rows" in g:
        return g.policy_rows
    rows = {r[0][7:]: r[1] for r in (db or get_db()).execute("SELECT key, value FROM settings WHERE key LIKE 'policy.%'")}
    if db is None and has_request_context():
        g.policy_rows = rows
    return rows


def policy(key, db=None):
    """Typed value of one policy. Pass `db` when there is no app context
    (start-up migrations, scripts)."""
    entry = POLICIES[key]
    raw = _stored(db).get(key)
    if raw is None:
        return _default(entry)
    try:
        return _parse(entry, raw)
    except ValueError:
        return _default(entry)


def policy_view(area=None):
    """Everything the settings page needs to draw and validate a form."""
    out = []
    for key, e in POLICIES.items():
        if area and e["area"] != area:
            continue
        item = {"key": key, "area": e["area"], "kind": e["kind"], "label": e["label"], "help": e.get("help", ""), "value": policy(key)}
        for k in ("min", "max"):
            if k in e:
                item[k] = e[k]
        if "choices" in e:
            item["choices"] = _choices(e)
        out.append(item)
    return out


def save_policies(area, form):
    """Validate and store every policy in one area from a posted form (absent
    booleans are false; a multi-select posts one comma list). Returns
    (changed, errors) — nothing is stored if any value is invalid."""
    values, errors = {}, []
    for key, e in POLICIES.items():
        if e["area"] != area:
            continue
        raw = form.get(key, "" if e["kind"] in ("bool", "multi", "domains", "emails", "url") else None)
        if raw is None:
            continue
        try:
            values[key] = _parse(e, raw)
        except ValueError as exc:
            errors.append(f"{e['label']}: {exc}")
    if values.get("upload_types") == []:
        errors.append("Allowed file types: keep at least one")
    if errors:
        return [], errors
    changed = []
    db = get_db()
    for key, v in values.items():
        if v == policy(key):
            continue
        stored = ",".join(v) if isinstance(v, list) else ("1" if v is True else "0" if v is False else str(v))
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (f"policy.{key}", stored))
        changed.append(f"{key}={stored}")
    db.commit()
    if has_request_context():
        g.pop("policy_rows", None)
    return changed, []


def local_today(db=None):
    """Today's date in the workspace time zone (Settings → General). Due
    dates, "days left" and reminders use this, not the server's clock."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(policy("timezone", db))).date()


def is_working_day(day=None, db=None):
    day = day or local_today(db)
    return WEEKDAYS[day.weekday()] in policy("working_days", db)


def email_domain_allowed(email, db=None):
    """Partner addresses must be on an allowed domain (Settings → Sign-in &
    security); an empty list allows any."""
    allowed = policy("external_domains", db)
    return not allowed or email.rsplit("@", 1)[-1].lower() in allowed
