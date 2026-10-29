"""Static configuration for the Odin app.

Pure data only — no imports from app, db, or services. Everything else in the
codebase may import from here; this module imports from nothing internal, so it
can never be part of an import cycle.
"""


# Tables the soft-delete/restore helpers may touch. SQLite cannot parameterise
# an identifier, so those helpers interpolate the table name — this allowlist
# is what keeps that safe. See db.assert_safe_table.
SOFT_DELETE_TABLES = {
    "projects", "documents", "account_managers", "partners",
    "partner_account_managers", "vendors", "products", "outsourcers",
}

# Seed values only — the live lists are admin-editable via /settings and
# stored in the stages / doc_categories tables. See get_stage_names() etc.
# Delivery lifecycle, not a billing one — the commercial stages went with the
# rest of the financials, and a vendor holding a guest link sees these names.
# Seeded only into an empty stages table; existing installs rename in Settings.
DEFAULT_STAGES = [
    "PO Received",
    "Scoping",
    "Kickoff",
    "Deployment",
    "Tuning/UAT",
    "Hypercare",
    "Sign-off",
    "Closed",
]
# The stage where the customer signs the sign-off document; the terminal stage
# after it cannot be reached until they (and we) have signed (services/signoff.py).
SIGNOFF_STAGE = "Sign-off"
SIGNOFF_DOC_CATEGORY = "Sign-off"
DEFAULT_DOC_CATEGORIES = ["Client PO", "Deliverable", "Sign-off"]

# Seeded on first boot. The switches that used to live here (notify_*_enabled,
# onedrive_mirror_uploads_enabled) are policies now (policies.POLICIES).
DEFAULT_SETTINGS = {}

# The one document category the project can't be created without — its upload
# is the create-project trigger (routes/projects.project_new).
CLIENT_PO_DOC_CATEGORY = "Client PO"

DELIVERY_MODES = ["Distribution/MSSP", "Outsourced"]
VIA_OPTIONS = ["Direct", "Partner"]

# Flat managed lookup lists administered from /settings/contacts, keyed by the
# URL segment used in their add/delete routes. Partners are handled separately
# since they cascade to partner_account_managers — see the dedicated routes.
CONTACT_LISTS = {
    # column: where a project keeps the picked name (text, so a rename carries it over)
    "account-managers": {"table": "account_managers", "has_email": True, "label": "Internal Account Managers", "column": "account_manager_name"},
    "vendors": {"table": "vendors", "has_email": False, "label": "Vendors", "column": "vendor_name"},
    "products": {"table": "products", "has_email": False, "label": "Products", "column": "product_name"},
    "outsourcers": {"table": "outsourcers", "has_email": True, "label": "Outsourcers", "column": "outsourcer_name"},
}

# Contributor: creates and comments (sales / account managers) but never moves
# a delivery stage or deletes. Member is the delivery team.
# What a project role may do on that project, on top of the global
# permission: (global permission, project roles allowed). Admins bypass the
# role check; everyone else — including staff not on the project — reads,
# comments, and ticks tasks tagged to them.
PROJECT_ACTIONS = {
    "move_stage":       ("edit_project_stage", {"Project manager"}),
    "manage_project":   ("edit_project", {"Project manager"}),                 # edit, delete, stages, team, report, guest links
    "manage_tasks":     ("edit_project", {"Project manager", "Coordinator"}),
    "manage_documents": ("upload_document", {"Project manager", "Coordinator"}),
}

# What a notification is about. Each kind can be switched off by email.
NOTIFICATION_KINDS = {
    "stage": "Stage changes on rollouts I am on",
    "approval": "Customer approval decisions",
    "activity": "Notes, finished tasks and documents on rollouts I manage",
    "assigned": "Tasks assigned to me",
    "access": "Sign-in requests and emergency password sign-ins (admins)",
    "ai": "AI server down or back, and AI features that failed validation (admins)",
    "ops": "Scheduled jobs that failed, backups that are overdue, and mail or Teams messages Odin could not send (admins)",
    "mention": "When someone mentions me in a note",
    "due": "A daily reminder of my tasks due today or overdue",
    "nudge": "A note a colleague sends me from the People page",
    "alert": "Alerts on rollouts I am on (overdue, due soon, over SLA, idle), and my daily digest",
    "milestone": "A milestone passing undone on rollouts I am on",
    "brief": "My morning brief: my rollouts, what is due, what came in (written by AI)",
    "report": "A rollout report shared with me",
    "automation": "Automations an admin set up (Settings › Automations) that name me or my role on a rollout",
}

# What a follower of a rollout hears about (services/notifications, B3): its
# events, never what is addressed to one person (an assignment, a reminder).
FOLLOW_KINDS = ("stage", "activity", "alert", "milestone")
# How a person takes each kind by email and Teams (Account page, B2): at once,
# in one mail at the digest time, or not at all. The bell is always at once.
DELIVERY = ("instant", "summary", "off")

# Kinds only admins receive, so only admins see them on the Account page.
ADMIN_KINDS = ("access", "ai", "ops")
# Kinds only staff receive (People page notes, the AI morning brief): partner and customer accounts never see them.
STAFF_KINDS = ("nudge", "brief", "milestone", "automation")   # automation: a rule never reaches the customer (services/rules.py)

THEMES = ("system", "light", "dark")
# Pastel accents (9 Oct 2026); blue the default again since 10 Oct (policy default_accent), as red read
# as overdue. Overdue stays the solid --bad state.
ACCENTS = ("red", "blue", "indigo", "violet", "teal", "green", "sky", "plum", "ink")
AVATAR_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
AVATAR_MAX_BYTES = 2 * 1024 * 1024

# External: contractors, resellers and customer contacts invited by email. No
# password, no product surface beyond the projects they participate in.
ROLES = ["Admin", "Member", "Contributor", "Viewer", "External"]
EXTERNAL_PROJECT_ROLES = ["Contractor", "Reseller", "Customer"]

# What someone is *on one project*, independent of their global role. The
# project manager is the owner (set at creation, follows owner reassignment).
PROJECT_ROLES = ["Project manager", "Sales", "Coordinator", "Contractor", "Reseller", "Customer"]
PROJECT_MANAGER = PROJECT_ROLES[0]

# Canonical permission list + seed values for role_permissions (DB is the
# source of truth at runtime — this dict only seeds first migration and
# defines the fixed display order for the RBAC settings matrix).
PERMISSIONS = {
    "view_board": ["Admin", "Member", "Contributor", "Viewer", "External"],
    "view_projects": ["Admin", "Member", "Contributor", "Viewer", "External"],
    "view_project_detail": ["Admin", "Member", "Contributor", "Viewer", "External"],
    "create_project": ["Admin", "Member", "Contributor"],
    "edit_project": ["Admin", "Member", "Contributor"],
    "delete_project": ["Admin"],
    "view_reports": ["Admin", "Member", "Contributor", "Viewer", "External"],
    "edit_project_stage": ["Admin", "Member"],
    "add_project_note": ["Admin", "Member", "Contributor", "External"],
    "upload_document": ["Admin", "Member", "Contributor"],
    "download_document": ["Admin", "Member", "Contributor", "Viewer", "External"],
    "delete_document": ["Admin"],
    "manage_contacts": ["Admin"],
    "manage_settings": ["Admin"],
    "manage_users": ["Admin"],
    "manage_integrations": ["Admin"],
    "manage_rules": ["Admin"],   # Settings › Automations (services/rules.py)
}

# Lifecycle alerts: schedule health (vs a project's target end date) + inactivity.
# The commercial payment alerts were removed with the rest of the financials.

ALERT_TYPE_TITLES = {
    "project_overdue": "Rollout overdue",
    "project_due_soon": "Rollout due soon",
    "stage_sla_breach": "Stage SLA breached",
    "stale": "Rollout idle",
    "approval_waiting": "Customer approval waiting",
    "blocker_open": "Blocker still open",
    "task_unowned": "Overdue task with no owner",
    "customer_quiet": "Customer task overdue",
    "milestone_missed": "Milestone missed",
}

ALERT_TYPES = set(ALERT_TYPE_TITLES)   # every type with a title; boot deletes only db.RETIRED_ALERT_TYPES, so a newer release's types survive a rollback

# project_overdue has no threshold — it fires the moment the target end date passes.
DEFAULT_ALERT_TYPE_SETTINGS = {
    "project_overdue": {"severity": "critical", "threshold_days": None, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    "project_due_soon": {"severity": "warning", "threshold_days": 7, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    # no threshold_days: the target is per stage, set on the stage itself
    "stage_sla_breach": {"severity": "warning", "threshold_days": None, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    "stale": {"severity": "warning", "threshold_days": 7, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    # bottlenecks (8 Oct 2026): what usually stalls a rollout, each with its own wait in days
    "approval_waiting": {"severity": "warning", "threshold_days": 5, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    "blocker_open": {"severity": "critical", "threshold_days": 3, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    "task_unowned": {"severity": "warning", "threshold_days": 1, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    "customer_quiet": {"severity": "warning", "threshold_days": 3, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    # milestones (W5): a dated commitment passed undone; the days are the grace after its date (0: raised the day after)
    "milestone_missed": {"severity": "warning", "threshold_days": 0, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
}

# Columns added to projects / users after their original CREATE TABLE — applied
# idempotently by db.migrate_db() via ALTER TABLE on existing installs.
NEW_PROJECT_COLUMNS = {
    # When the plan was first frozen as the baseline (services/plan.py).
    "baseline_at": "TEXT",
    # Second guest link. access_token is the vendor/outsourcer link (may
    # advance the stage); customer_token is view-and-comment only.
    "customer_token": "TEXT",
    # Which template this project's own stage list was copied from. Analytics
    # compares projects only within a template, since their stages match.
    "stage_template_id": "INTEGER",
    # 1 = every stage change asks the customer contact to approve it
    "customer_approval": "INTEGER NOT NULL DEFAULT 0",
    # who that is: one Customer participant (services/approvals.py); NULL = the first Customer on the team
    "approver_id": "INTEGER",
    "via": "TEXT",
    "account_manager_name": "TEXT",
    "account_manager_email": "TEXT",
    "partner_name": "TEXT",
    "partner_account_manager_name": "TEXT",
    "partner_account_manager_email": "TEXT",
    "vendor_name": "TEXT",
    "product_name": "TEXT",
    "access_token": "TEXT",
    # when the guest links were last minted (rotation); NULL = since created_at. They expire per guest_link_days
    "guest_tokens_at": "TEXT",
    "deleted_at": "TEXT",
    # CRM intake (services/intake.py): 1 = created by POST /api/v1/intake and
    # not yet confirmed by a project manager. A pending rollout is neither open
    # nor closed (db.PROJECT_OPEN_SQL), so no lane, count, alert or report has it.
    "intake_pending": "INTEGER NOT NULL DEFAULT 0",
    "intake_deal_id": "TEXT",       # the CRM's deal id: a repeat call answers with this rollout
    "intake_source": "TEXT",        # the intake token's name
    "intake_contacts": "TEXT",      # JSON list of the customer contact emails the CRM sent
}

# Commercial columns dropped in the project-tracker phase-out (invoice/payment/
# PO-money tracking moved to the analysis platform). migrate_db drops any that
# still exist; kept here as the authoritative list so a re-added column can't
# silently creep back. Irreversible — the column data goes with the column.
DROPPED_PROJECT_COLUMNS = [
    "po_amount", "po_payment_terms", "po_due_date",
    "invoice_number", "invoice_date", "invoice_due_date", "invoice_amount",
    "payment_terms", "client_payment_status",
    "vendor_invoice_number", "vendor_invoice_date", "vendor_invoice_due_date",
    "vendor_invoice_amount", "vendor_payment_terms", "vendor_payment_status",
]

NEW_USER_COLUMNS = {
    "role": "TEXT NOT NULL DEFAULT 'Member'",
    "active": "INTEGER NOT NULL DEFAULT 1",
    "email": "TEXT",
    # Set on the seed admin and whenever an admin resets someone's password:
    # the next login is funnelled to the account page until it is changed.
    "must_change_password": "INTEGER NOT NULL DEFAULT 0",
    # The last time the person was active in Odin (an activity ping or a sign-in).
    "last_seen_at": "TEXT",
    # The last counted active minute (services/activity.py guards on this, not on last_seen_at).
    "last_ping_at": "TEXT",
    # How the person wants to hear from Odin beyond the bell: 'email' or 'teams'
    # (Teams is delivered once Microsoft 365 is connected; email until then).
    "notify_via": "TEXT NOT NULL DEFAULT 'email'",
    # A sign-up link's request: which link, and the project it asks to join (applied on approval).
    "signup_link_id": "INTEGER",
    "signup_project_id": "INTEGER",
    "signup_project_role": "TEXT",
    # Two-step sign-in (services/mfa.py): the authenticator secret, sealed with a
    # key derived from SECRET_KEY; one waiting for its first code; when it was
    # turned on; the last time step used (a code works once); recovery code hashes.
    "totp_secret": "TEXT",
    "totp_pending": "TEXT",
    "totp_enabled_at": "TEXT",
    "totp_last_step": "INTEGER NOT NULL DEFAULT 0",
    "recovery_codes": "TEXT",
    # Appearance is the user's, not the deployment's: light / dark / follow the
    # OS, and which hue the one accent takes. The avatar is a filename under
    # ODIN_DATA_DIR/avatars, unique per upload so its URL changes on replace.
    # Odin 2.0 (workload): hours per week this person can plan; NULL takes the policy
    "capacity_hours": "REAL",
    "theme": "TEXT NOT NULL DEFAULT 'system'",
    "accent": "TEXT NOT NULL DEFAULT 'blue'",
    "avatar": "TEXT",
    # Notification kinds this user does NOT want by email (comma list); the
    # in-app notification always arrives.
    "email_off": "TEXT NOT NULL DEFAULT ''",
    # Kinds this user takes in the daily summary instead (comma list, B2): the
    # outbox holds them until the digest time. Neither list = at once.
    "email_summary": "TEXT NOT NULL DEFAULT ''",
    # The personal calendar feed (services/ics.py, B13): the token's hash and
    # when it was made; NULL = no feed. The token itself is shown once.
    "ics_token_hash": "TEXT",
    "ics_created_at": "TEXT",
    # The feed's last successful read (written at most once an hour): a feed unread
    # for policy ics_idle_days switches itself off in the nightly housekeeping.
    "ics_last_read_at": "TEXT",
    # The release whose "What's new" this user dismissed (B15).
    "whats_new_seen": "TEXT",
    # "Since you last looked" (services/dashboard.py, B10): where this visit's
    # window starts, and the last dashboard load (a gap starts a new visit).
    "since_from": "TEXT",
    "since_seen_at": "TEXT",
    # The dashboard as this user arranged it (JSON layout; NULL = the
    # workspace default), and which page sign-in lands on.
    "dashboard_layout": "TEXT",
    "home": "TEXT NOT NULL DEFAULT 'dashboard'",
    # Bumped on deactivate / admin reset: any session minted under an older
    # epoch is dead on its next request. Cheap "log out everywhere".
    "session_epoch": "INTEGER NOT NULL DEFAULT 0",
    # Access-review evidence: who exists since when, and who has gone quiet.
    "created_at": "TEXT",
    "last_login_at": "TEXT",
    # internal (password, Cloudflare Access) or external (email sign-in link)
    "kind": "TEXT NOT NULL DEFAULT 'internal'",
    # Microsoft sign-in (routes/sso.py): the Entra object id this account is
    # bound to; a first sign-in waits (pending=1, inactive) for an admin; and
    # which accounts keep a password once staff must use Microsoft.
    "ms_oid": "TEXT",
    "pending": "INTEGER NOT NULL DEFAULT 0",
    "password_login": "INTEGER NOT NULL DEFAULT 0",
    # why an admin declined a sign-up request (one line, optional): kept with the inactive account
    "declined_reason": "TEXT",
}
