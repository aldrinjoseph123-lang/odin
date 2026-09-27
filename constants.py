"""Static configuration for the Odin app.

Pure data only — no imports from app, db, or services. Everything else in the
codebase may import from here; this module imports from nothing internal, so it
can never be part of an import cycle.
"""

UNDO_WINDOW_SECS = 300  # 5 minutes

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
    "Closed",
]
DEFAULT_DOC_CATEGORIES = ["Client PO", "Deliverable"]

DEFAULT_SETTINGS = {
    "notify_email_enabled": "0",
    "notify_teams_enabled": "0",
    "onedrive_mirror_uploads_enabled": "0",
    "onedrive_backup_enabled": "0",
}

# The one document category the project can't be created without — its upload
# is the create-project trigger. See has_required_document() / project_new.
CLIENT_PO_DOC_CATEGORY = "Client PO"

DELIVERY_MODES = ["Distribution/MSSP", "Outsourced"]
VIA_OPTIONS = ["Direct", "Partner"]

# Flat managed lookup lists administered from /settings/contacts, keyed by the
# URL segment used in their add/delete routes. Partners are handled separately
# since they cascade to partner_account_managers — see the dedicated routes.
CONTACT_LISTS = {
    "account-managers": {"table": "account_managers", "has_email": True, "label": "Internal Account Managers"},
    "vendors": {"table": "vendors", "has_email": False, "label": "Vendors"},
    "products": {"table": "products", "has_email": False, "label": "Products"},
    "outsourcers": {"table": "outsourcers", "has_email": True, "label": "Outsourcers"},
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
    "stage": "Stage changes on projects I am on",
    "approval": "Customer approval decisions",
    "activity": "Notes, finished tasks and documents on projects I manage",
    "assigned": "Tasks assigned to me",
    "mention": "When someone mentions me in a note",
    "due": "A daily reminder of my tasks due today or overdue",
}

THEMES = ("system", "light", "dark")
ACCENTS = ("blue", "indigo", "violet", "teal", "green", "amber", "rose", "ink")
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
}

# Lifecycle alerts: schedule health (vs a project's target end date) + inactivity.
# The commercial payment alerts were removed with the rest of the financials.
ALERT_TYPES = {"project_overdue", "project_due_soon", "stage_sla_breach", "stale"}

ALERT_TYPE_TITLES = {
    "project_overdue": "Project overdue",
    "project_due_soon": "Project due soon",
    "stage_sla_breach": "Stage SLA breached",
    "stale": "Project inactive",
}

# project_overdue has no threshold — it fires the moment the target end date passes.
DEFAULT_ALERT_TYPE_SETTINGS = {
    "project_overdue": {"severity": "critical", "threshold_days": None, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    "project_due_soon": {"severity": "warning", "threshold_days": 7, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    # no threshold_days: the target is per stage, set on the stage itself
    "stage_sla_breach": {"severity": "warning", "threshold_days": None, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
    "stale": {"severity": "warning", "threshold_days": 7, "notify_email": 0, "notify_teams": 0, "notify_inapp": 1},
}

# Columns added to projects / users after their original CREATE TABLE — applied
# idempotently by db.migrate_db() via ALTER TABLE on existing installs.
NEW_PROJECT_COLUMNS = {
    # Second guest link. access_token is the vendor/outsourcer link (may
    # advance the stage); customer_token is view-and-comment only.
    "customer_token": "TEXT",
    # Which template this project's own stage list was copied from. Analytics
    # compares projects only within a template, since their stages match.
    "stage_template_id": "INTEGER",
    # 1 = every stage change asks the customer contact to approve it
    "customer_approval": "INTEGER NOT NULL DEFAULT 0",
    "via": "TEXT",
    "account_manager_name": "TEXT",
    "account_manager_email": "TEXT",
    "partner_name": "TEXT",
    "partner_account_manager_name": "TEXT",
    "partner_account_manager_email": "TEXT",
    "vendor_name": "TEXT",
    "product_name": "TEXT",
    "access_token": "TEXT",
    "deleted_at": "TEXT",
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
    # Appearance is the user's, not the deployment's: light / dark / follow the
    # OS, and which hue the one accent takes. The avatar is a filename under
    # ODIN_DATA_DIR/avatars, unique per upload so its URL changes on replace.
    "theme": "TEXT NOT NULL DEFAULT 'system'",
    "accent": "TEXT NOT NULL DEFAULT 'blue'",
    "avatar": "TEXT",
    # Notification kinds this user does NOT want by email (comma list); the
    # in-app notification always arrives.
    "email_off": "TEXT NOT NULL DEFAULT ''",
    # Bumped on deactivate / admin reset: any session minted under an older
    # epoch is dead on its next request. Cheap "log out everywhere".
    "session_epoch": "INTEGER NOT NULL DEFAULT 0",
    # Access-review evidence: who exists since when, and who has gone quiet.
    "created_at": "TEXT",
    "last_login_at": "TEXT",
    # internal (password, Cloudflare Access) or external (email sign-in link)
    "kind": "TEXT NOT NULL DEFAULT 'internal'",
}
