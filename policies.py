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
from constants import ACCENTS as ACCENT_CHOICES, THEMES as THEME_CHOICES   # noqa: E402

POLICIES = {
    # ---- General
    "company_name": dict(area="general", kind="text", default="Protect24x7", max=80,
                         label="Company name", help="Shown in email footers and on the PDFs attached to the weekly report."),
    "public_url": dict(area="general", kind="url", default="", max=200,
                       label="Public web address", help="e.g. https://odin.example.com. Sign-in and emailed links are built from it, never from the request. Blank: the address the browser used."),
    "timezone": dict(area="general", kind="choice", default="Asia/Dubai", choices="timezones",
                     label="Time zone", help="Decides \"today\" for due dates and when scheduled jobs run."),
    "date_format": dict(area="general", kind="choice", default="d MMM yyyy", choices=tuple(DATE_FORMATS),
                        label="Date format", help="How dates read across the app."),
    "working_days": dict(area="general", kind="multi", default="Mon,Tue,Wed,Thu,Fri", choices=WEEKDAYS, nonempty=True,
                         label="Working week", help="Stage lengths and SLAs count these days (Settings › Rollouts & workflow); reminders and digests go out on them only."),
    "holidays": dict(area="general", kind="dates", default="", max=4000, optional=True, label="Public holidays",
                     help="One per line: \"2026-12-02 National Day\", or a span \"2027-03-20 to 2027-03-22 Eid al-Fitr\" (dates as announced). Not counted as working days; no digest or reminders on them."),
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
    "mfa_required": dict(area="security", kind="choice", default="off", choices=("off", "admins", "everyone"),
                         label="Two-step sign-in", help="For password sign-in (Microsoft sign-in has its own). Anyone may turn it on for themselves on the Account page; when required and not yet set up, the next sign-in goes straight to setting it up."),
    "login_account_max": dict(area="security", kind="int", default=20, min=10, max=200,
                              label="Failed sign-ins per account before a pause", help="From all addresses together: stops a password being guessed from many machines. The account pauses for the same length."),
    "login_window_minutes": dict(area="security", kind="int", default=15, min=5, max=120,
                                 label="Pause length (minutes)", help="Failures older than this stop counting."),
    "upload_max_mb": dict(area="security", kind="int", default=25, min=1, max=100,
                          label="Largest upload (MB)", help="Per file. The server never accepts more than 100 MB."),
    "upload_types": dict(area="security", kind="multi", default=",".join(UPLOAD_TYPES), choices=UPLOAD_TYPES, nonempty=True,
                         label="Allowed file types", help="Untick a type to refuse it. Types the server cannot verify are never offered."),
    "link_minutes": dict(area="security", kind="int", default=30, min=5, max=1440,
                         label="Email link lifetime (minutes)", help="Partner sign-in links and password-reset links work once, for this long."),
    "external_domains": dict(area="security", kind="domains", default="", max=500,
                             label="Partner email domains", help="e.g. partner.com, vendor.ae. Only these can be invited or sent a sign-in link. Blank: any domain."),
    "undo_minutes": dict(area="security", kind="int", default=5, min=1, max=60,
                         label="Undo window (minutes)", help="How long deletes and stage moves can be undone."),
    # ---- Sign-up links and time on Odin (Settings › Sign-up & activity)
    "signup_enabled": dict(area="people", kind="bool", default=True,
                           label="Sign-up links work", help="Off: no new links can be made and every open link stops working until this is on again (links past their date stay expired)."),
    "signup_domains": dict(area="people", kind="domains", default="", max=500, optional=True,
                           label="Sign-up link email domains", help="Staff joining by a sign-up link must use one of these domains, e.g. protect24x7.com. Blank: any."),
    "signup_days": dict(area="people", kind="int", default=7, min=1, max=90,
                        label="Sign-up links last (days)", help="A new link's life; each can also be revoked on the Users page."),
    "activity_tracking": dict(area="people", kind="bool", default=True,
                              label="Record time on Odin", help="Counts active minutes while Odin is open, visible and in use. Off: nothing is counted, the Time on Odin panels disappear and Last seen shows the last sign-in."),
    "activity_roles": dict(area="people", kind="multi", default="Admin,Member", choices=("Admin", "Member", "Contributor"),
                           label="Who sees other people's time", help="Everyone always sees their own on the Account page. Untick every role to keep each person's time to themselves."),
    "activity_idle_minutes": dict(area="people", kind="int", default=5, min=1, max=30,
                                  label="Idle after (minutes)", help="No mouse, key or touch for this long stops the count until the person is back."),
    # ---- Notifications
    "digest_time": dict(area="notifications", kind="time", default="08:00",
                        label="Daily digest and reminders at", help="Workspace time zone, working days only. Needs the scheduler service running."),
    "mail_from": dict(area="notifications", kind="emails", one=True, default="", max=254,
                      label="Send email as", help="An alias of the connected Microsoft 365 mailbox (e.g. odin-pms@company.com), so people can tell the mail comes from Odin when the mailbox is shared with other systems. Blank: the mailbox's own address. Exchange must allow sending from aliases (SendFromAliasEnabled); if Microsoft refuses the alias, Odin sends from the mailbox and tells the admins."),
    # secret: the address is the channel's bearer key (sig=), so it is sealed at rest, never sent
    # back to the page and audited only as set or cleared, like the AI key (test round P2-9)
    "teams_webhook_url": dict(area="notifications", kind="url", default="", max=500, query=True, secret=True,
                              label="Teams Workflows webhook", help="From a Teams channel: Workflows › \"Post to a channel when a webhook request is received\". Stage changes, decisions and the weekly report are posted here too. Blank: channel posts only."),
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
                          label="And these addresses", help="e.g. ceo@company.com. The attached PDFs go only to addresses that belong to Odin staff accounts; any other address gets the summary alone."),
    "report_attach": dict(area="reports", kind="bool", default=False,
                          label="Attach the portfolio report and each rollout's latest saved report as PDFs", help="Rollout reports only for rollouts with a saved version."),
    "report_teams": dict(area="reports", kind="bool", default=False,
                         label="Also post a summary to Teams", help="The channel chosen under Integrations and/or the Workflows webhook under Notifications."),
    # ---- Audit & compliance
    "audit_keep": dict(area="audit", kind="choice", default="3", choices=("1", "2", "3", "5", "7", "forever"),
                       label="Keep audit log rows for (years)", help="Older rows are written to a CSV archive (kept with the backups) and then removed, nightly. At least a year: SOC 2 asks for 12 months."),
    "notifications_keep_days": dict(area="audit", kind="int", default=90, min=7, max=730,
                                    label="Keep read notifications for (days)", help="Bell items someone has read are removed after this; unread ones stay until they are read."),
    "activity_keep_days": dict(area="audit", kind="int", default=400, min=30, max=1825,
                               label="Keep time on Odin for (days)", help="Per-person active minutes older than this are removed nightly. The panels show the last 30 days."),
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
    # ---- AI (Settings › AI): the server, then how Odin watches it (services/ai)
    "ai_enabled": dict(area="ai", kind="bool", default=False,
                       label="Use AI features", help="Off: Odin never calls the AI server and every feature uses its usual behaviour."),
    "ai_base_url": dict(area="ai", kind="url", default="", max=200,
                        label="AI server address", help="The OpenAI-compatible base address, usually ending in /v1, e.g. http://ai.p24.lan:11434/v1. A name rather than an IP lets the server move without touching Odin."),
    "ai_model": dict(area="ai", kind="text", default="P24-AI", max=120,
                     label="Model name", help="The name the server answers to. Keep it an alias the server owns (P24-AI), so the model behind it can change without touching Odin."),
    "ai_identity": dict(area="ai", kind="text", default="You are P24x7-AI, the assistant for Odin.", max=200,
                        label="Identity line", help="Starts every system prompt Odin sends, as the AI server's integration guide asks; without it the model may name itself something else. Changing it validates every feature again."),
    "ai_allow_external": dict(area="ai", kind="bool", default=False,
                              label="Allow an external AI provider", help="Off: Odin refuses any address outside the private network, so customer notes never leave the building. On: a hosted provider may be used; every AI request then sends rollout text to it."),
    "ai_heartbeat_minutes": dict(area="ai_schedule", kind="int", default=5, min=1, max=60,
                                 label="Heartbeat every (minutes)", help="A light check that the server answers and which model it runs. No model work."),
    "ai_down_after": dict(area="ai_schedule", kind="int", default=2, min=1, max=10,
                          label="Down after missed heartbeats", help="Admins hear once when it goes down and once when it is back."),
    "ai_validate_time": dict(area="ai_schedule", kind="time", default="03:00",
                             label="Validate every feature daily at", help="Workspace time zone. Also runs after a settings change and whenever the model changes."),
    "ai_night_time": dict(area="ai_schedule", kind="time", default="03:30",
                          label="Night shift at", help="Nightly features (such as the weekly words) draft for every open rollout, after the daily validation. Only features that passed run."),
    "ai_brief_time": dict(area="ai_schedule", kind="time", default="07:30",
                          label="Morning brief at", help="Working days only. Each person with open rollouts gets one; they can switch the email off on their Account page."),
    "ai_budget_s": dict(area="ai_schedule", kind="int", default=90, min=10, max=900,
                        label="Seconds per answer before \"slow\"", help="A slow feature keeps running, with a warning in its row below."),
    "ai_max_input_chars": dict(area="ai_schedule", kind="int", default=4000, min=1000, max=30000,
                               label="Longest input per request (characters)", help="Reading is the slow part on a CPU server: Odin trims the longest text in a request (and reads documents in parts) to stay under this."),
    "ai_timeout_s": dict(area="ai_schedule", kind="int", default=300, min=30, max=1800,
                         label="Give up on an answer after (seconds)", help="The server answers one request at a time; allow for waiting behind another application's request."),
    # ---- Projects & workflow
    "default_template": dict(area="workflow", kind="choice", default="", choices="templates",
                             label="Stage template for new rollouts", help="Pre-selected on the new project form."),
    "default_stage_days": dict(area="workflow", kind="int", default=7, min=1, max=180, label="Default stage length (days)",
                               help="How long a stage is assumed to take when neither the plan nor its SLA says — for the forecast and the suggested plan."),
    "count_working_days": dict(area="workflow", kind="bool", default=True, label="Count stage lengths and SLAs in working days",
                               help="Weekends outside the working week and public holidays (Settings › General) do not count. Off: calendar days. Gaps between dates, such as days late, are always calendar days."),
    "sla_min_visits": dict(area="workflow", kind="int", default=3, min=2, max=50, label="Finished rollouts before an SLA is questioned",
                           help="The SLA check under Stage templates proposes a new SLA for a stage only when at least this many rollouts have passed through it."),
    "rag_amber_days": dict(area="workflow", kind="int", default=1, min=0, max=90, label="At risk after (days late)",
                           help="A rollout is at risk when it is forecast to finish more than this many days after its target date."),
    "rag_red_days": dict(area="workflow", kind="int", default=7, min=1, max=180, label="Off track after (days late)",
                         help="…and off track past this many days, or when it is already past its target, or has an open blocker."),
    "signoff_required": dict(area="workflow", kind="bool", default=True,
                             label="A signed sign-off closes a rollout",
                             help="The last stage cannot be reached until the customer has signed the sign-off document and we have countersigned (or a signed copy is uploaded). An admin can waive it with a written reason."),
    "signoff_statement": dict(area="workflow", kind="text", default=(
        "By signing, the customer confirms that the work listed above has been delivered in line with the agreed scope, "
        "that the items marked descoped or outstanding are recorded as stated, and that the rollout is accepted as complete."),
        max=1200, multiline=True, label="Acceptance statement", help="The sentence the customer signs under, on every sign-off document."),
    "signoff_terms": dict(area="workflow", kind="text", default=(
        "Support continues under the terms of the existing agreement.\n"
        "Outstanding items listed above will be closed as described, without affecting acceptance."),
        max=2000, optional=True, multiline=True, label="Handover and support terms",
        help="Printed on the sign-off under Handover; one point per line. The project manager can edit it per document."),
    "default_customer_approval": dict(area="workflow", kind="bool", default=False,
                                      label="Ask the customer to approve each stage by default",
                                      help="Pre-ticked on the new project form; each rollout can still change it."),
}


def _choices(entry):
    c = entry.get("choices")
    if c == "timezones":
        return sorted(available_timezones())
    if c == "templates":
        return [str(r["id"]) for r in get_db().execute("SELECT id FROM stage_templates ORDER BY id")]
    return list(c or ())


# A host name: dot-separated labels of letters, digits and inner hyphens (so "-" and "-.-" are not one).
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOST = rf"{_LABEL}(?:\.{_LABEL})*"


def _parse(entry, raw):
    """Typed value from a stored/posted string, or raise ValueError."""
    kind = entry["kind"]
    if kind == "int":
        s = str(raw).strip()
        if not re.fullmatch(r"-?[0-9]{1,9}", s):   # int() would take "١٢" and answer in Python's words
            raise ValueError(f"a whole number between {entry['min']} and {entry['max']}")
        v = int(s)
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
        if entry.get("nonempty") and not picked:
            raise ValueError("keep at least one")
        return [p for p in allowed if p in picked]   # canonical order
    v = str(raw).strip()
    if "\x00" in v or (kind in ("url", "emails", "domains", "time", "choice") or (kind == "text" and not entry.get("multiline"))) and ("\n" in v or "\r" in v):
        raise ValueError("one line of plain text")
    if kind == "url":
        v = v.rstrip("/")
        query = r"(\?[A-Za-z0-9_.~%&=+,;:@/-]*)?" if entry.get("query") else ""   # a webhook's ?api-version=…&sig=…
        if v and (len(v) > entry["max"] or not re.fullmatch(rf"https?://{_HOST}(:[0-9]{{1,5}})?(/[A-Za-z0-9_./%~-]*)?{query}", v)):
            raise ValueError("a web address like https://odin.example.com")
        return v
    if kind == "emails":
        parts = sorted({p.lower() for p in re.split(r"[\s,;]+", v) if p})
        if len(",".join(parts)) > entry["max"] or any(not re.fullmatch(rf"[^@\s<>\"']+@{_HOST}", p) or "." not in p.split("@")[1] for p in parts):
            raise ValueError("email addresses separated by commas")
        if entry.get("one") and len(parts) > 1:
            raise ValueError("one email address")
        return parts
    if kind == "domains":
        parts = sorted({p.lower().lstrip("@") for p in re.split(r"[\s,;]+", v) if p})
        if len(",".join(parts)) > entry["max"] or any(not re.fullmatch(_HOST, p) or "." not in p for p in parts):
            raise ValueError("domains like partner.com, separated by commas")
        return parts
    if kind == "time":
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("a time like 08:00")
        return v
    if kind == "dates":
        from services.workdays import parse_holidays
        parse_holidays(v)
        text = "\n".join(line.strip() for line in v.splitlines() if line.strip())
        if len(text) > entry["max"]:
            raise ValueError(f"up to {entry['max']} characters")
        return text
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
    if raw is not None and entry.get("secret"):
        from services.sealed import unseal
        raw = unseal(raw)   # a value saved before sealing reads as it is, and is sealed at its next save
    if raw is None:
        return _default(entry)
    try:
        return _parse(entry, raw)
    except ValueError:
        return _default(entry)


# The settings page draws each area as small titled cards, each with its own
# Save (9 Oct 2026, the user's call). `hint` is the one plain line (with an
# example) shown under a setting; the longer `help` sits behind "What is this?".
# A setting without a hint shows its help directly.
_GROUPS = {
    "Your workspace": ("company_name", "public_url"),
    "Dates and working days": ("timezone", "date_format", "working_days", "holidays"),
    "Look for new people": ("default_theme", "default_accent"),
    "Sessions": ("session_idle_minutes", "session_max_hours"),
    "Passwords and two-step": ("password_min_length", "mfa_required"),
    "Wrong passwords": ("login_max_attempts", "login_account_max", "login_window_minutes"),
    "Uploads": ("upload_max_mb", "upload_types"),
    "Partner access": ("external_domains", "link_minutes"),
    "Undo": ("undo_minutes",),
    "Sign-up links": ("signup_enabled", "signup_domains", "signup_days"),
    "Time on Odin": ("activity_tracking", "activity_roles", "activity_idle_minutes"),
    "Daily digest": ("digest_time",),
    "Sender": ("mail_from",),
    "Teams webhook": ("teams_webhook_url",),
    "When it goes out": ("report_enabled", "report_days", "report_time"),
    "Who gets it": ("report_roles", "report_emails"),
    "What it carries": ("report_attach", "report_teams"),
    "Retention": ("audit_keep", "notifications_keep_days", "activity_keep_days"),
    "When to back up": ("backup_time", "backup_days", "restore_test"),
    "Copies kept": ("keep_daily", "keep_weekly", "keep_monthly"),
    "Where copies go": ("dest_onedrive", "dest_sharepoint", "sharepoint_site", "sharepoint_folder", "dest_share", "share_path"),
    "AI server": ("ai_enabled", "ai_base_url", "ai_model", "ai_identity", "ai_allow_external"),
    "Watching the server": ("ai_heartbeat_minutes", "ai_down_after", "ai_validate_time", "ai_night_time", "ai_brief_time",
                            "ai_budget_s", "ai_max_input_chars", "ai_timeout_s"),
    "Defaults": ("default_template",),
    "Stage timing": ("default_stage_days", "count_working_days", "sla_min_visits"),
    "Plan health": ("rag_amber_days", "rag_red_days"),
    "Sign-off": ("signoff_required", "signoff_statement", "signoff_terms"),
    "Customer approval": ("default_customer_approval",),
}
_HINTS = {
    "public_url": "The address people use to reach Odin, e.g. https://odin.example.com.",
    "working_days": "The days your team works, e.g. Mon to Fri. Deadlines and reminders skip the rest.",
    "holidays": "Days off that do not count as working days, e.g. 2026-12-02 National Day.",
    "mfa_required": "Ask for a code from a phone app after the password, e.g. required for admins.",
    "login_max_attempts": "Pause sign-in after this many wrong passwords from one computer, e.g. 5.",
    "login_account_max": "Pause an account after this many wrong passwords from anywhere, e.g. 20.",
    "login_window_minutes": "How long the pause lasts, e.g. 15 minutes.",
    "upload_types": "The kinds of file people may attach, e.g. PDF and Word.",
    "external_domains": "Partners can be invited only from these email domains, e.g. partner.com. Blank: any.",
    "link_minutes": "How long a sign-in or password-reset email link works, e.g. 30 minutes.",
    "undo_minutes": "How long the Undo button stays after a delete or a stage move, e.g. 5 minutes.",
    "signup_enabled": "Lets new staff join with a link made on the Users page. Off: every open link stops working.",
    "signup_domains": "Only these email domains may join by link, e.g. protect24x7.com. Blank: any.",
    "signup_days": "How long a new sign-up link works, e.g. 7 days.",
    "activity_tracking": "Counts the minutes each person actively uses Odin.",
    "activity_roles": "Which roles may see other people's time. Everyone always sees their own.",
    "activity_idle_minutes": "Stop counting after this long without mouse or keyboard, e.g. 5 minutes.",
    "digest_time": "When the daily summary email and reminders go out, e.g. 08:00.",
    "mail_from": "The address people see Odin's email come from, e.g. odin-pms@company.com.",
    "teams_webhook_url": "Paste a Teams channel's webhook address to post updates there.",
    "report_enabled": "Email a weekly summary of every rollout.",
    "report_emails": "Extra people to email, e.g. ceo@company.com.",
    "audit_keep": "How many years of the audit log to keep, e.g. 3.",
    "restore_test": "Check each backup by actually restoring it.",
    "ai_base_url": "Where the AI server answers, e.g. http://ai.office.lan:11434/v1.",
    "ai_identity": "The first line of every instruction Odin sends the AI.",
    "ai_allow_external": "Off keeps customer notes inside the office network.",
    "ai_max_input_chars": "Longer text is trimmed to this before it is sent, e.g. 4,000 characters.",
    "default_template": "The stage list a new rollout starts with.",
    "default_stage_days": "How long a stage is expected to take when nothing else says, e.g. 7 days.",
    "count_working_days": "Skip weekends and holidays when counting stage days: Friday to Monday is one day.",
    "sla_min_visits": "How many rollouts must finish a stage before Odin suggests a new time limit, e.g. 3.",
    "rag_amber_days": "A rollout is at risk when forecast to finish more than this many days late, e.g. 1.",
    "rag_red_days": "It is off track when forecast more than this many days late, e.g. 7.",
    "signoff_required": "A rollout cannot close until the customer has signed it off.",
    "signoff_statement": "What the customer agrees to when they sign.",
    "signoff_terms": "Support terms printed on the sign-off, one per line.",
    "default_customer_approval": "New rollouts ask the customer to approve each stage move.",
}
for _title, _keys in _GROUPS.items():
    for _key in _keys:
        POLICIES[_key]["group"] = _title
for _key, _hint in _HINTS.items():
    POLICIES[_key]["hint"] = _hint

def policy_view(area=None):
    """Everything the settings page needs to draw and validate a form."""
    out = []
    for key, e in POLICIES.items():
        if area and e["area"] != area:
            continue
        item = {"key": key, "area": e["area"], "kind": e["kind"], "label": e["label"], "help": e.get("help", ""), "value": policy(key),
                "group": e.get("group", "")}
        for k in ("min", "max", "multiline", "hint"):
            if k in e:
                item[k] = e[k]
        if "choices" in e:
            item["choices"] = _choices(e)
        if e.get("secret"):
            # write-only: the page shows whether one is saved; blank keeps it, "clear" removes it
            item.update(value="", secret=True, saved=bool(item["value"]))
        out.append(item)
    return out


def save_policies(area, form):
    """Validate and store the policies of one area from a posted form. Only
    the keys the form carries change: the settings page saves one card at a
    time, so an absent key, a switch included, keeps its value (a card posts
    its switches as "on" or "0"). A multi-select posts one comma list.
    Returns (changed, errors) — nothing is stored if any value is invalid."""
    values, errors = {}, []
    for key, e in POLICIES.items():
        if e["area"] != area:
            continue
        raw = form.get(key)
        if e.get("secret") and not (raw or "").strip():
            raw = "" if form.get("clear") == key else None   # the field comes back blank: keep the saved one
        if raw is None:
            continue
        try:
            values[key] = _parse(e, raw)
        except ValueError as exc:
            errors.append(f"{e['label']}: {exc}")
    if "rag_amber_days" in values or "rag_red_days" in values:
        amber, red = values.get("rag_amber_days", policy("rag_amber_days")), values.get("rag_red_days", policy("rag_red_days"))
        if isinstance(amber, int) and isinstance(red, int) and amber >= red:
            errors.append(f"Amber after ({amber} days) must come before red after ({red} days)")
    if errors:
        return [], errors
    changed = []
    db = get_db()
    for key, v in values.items():
        if v == policy(key):
            continue
        stored = ",".join(v) if isinstance(v, list) else ("1" if v is True else "0" if v is False else str(v))
        said = stored
        if POLICIES[key].get("secret"):
            from services.sealed import seal
            stored, said = seal(stored), "set" if stored else "cleared"
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (f"policy.{key}", stored))
        changed.append(f"{key}={said}")
    db.commit()
    if has_request_context():
        g.pop("policy_rows", None)
    return changed, []


def local_date(value, db=None):
    """The workspace-local calendar date of a stored value: a stored UTC
    timestamp ('YYYY-MM-DDTHH:MM…') is converted — 01:30 in Dubai is still the
    previous day in UTC — while a plain 'YYYY-MM-DD' date is taken as it is.
    None for empty or malformed values."""
    from datetime import date, datetime, timezone
    from zoneinfo import ZoneInfo
    if not value:
        return None
    s = str(value)
    try:
        if len(s) > 10 and s[10] in "T ":
            return datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(policy("timezone", db))).date()
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def local_today(db=None):
    """Today's date in the workspace time zone (Settings › General). Due
    dates, "days left" and reminders use this, not the server's clock."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(policy("timezone", db))).date()


def is_working_day(day=None, db=None):
    """A day in the working week that is not a public holiday."""
    from services.workdays import _calendar
    day = day or local_today(db)
    return WEEKDAYS[day.weekday()] in policy("working_days", db) and day not in _calendar((), policy("holidays", db))[1]


def email_domain_allowed(email, db=None):
    """Partner addresses must be on an allowed domain (Settings › Sign-in &
    security); an empty list allows any."""
    allowed = policy("external_domains", db)
    return not allowed or email.rsplit("@", 1)[-1].lower() in allowed
