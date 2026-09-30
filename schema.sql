CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Member',
    active INTEGER NOT NULL DEFAULT 1,
    email TEXT
);

CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    position INTEGER NOT NULL
);

-- Sessions ended by signing out: the cookie is signed, not stored, so a copy
-- would otherwise work until it expired. Rows older than a session's longest
-- life are trimmed as new ones arrive.
CREATE TABLE IF NOT EXISTS revoked_sessions (
    user_id INTEGER NOT NULL,
    login_at TEXT NOT NULL,
    revoked_at TEXT NOT NULL,
    PRIMARY KEY (user_id, login_at)
);

CREATE TABLE IF NOT EXISTS doc_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    partners INTEGER NOT NULL DEFAULT 1   -- 0: partners and customers never see documents of this kind
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Every moved plan date on a rollout, and every re-baseline (services/plan.py).
CREATE TABLE IF NOT EXISTS plan_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    stage TEXT,
    field TEXT NOT NULL,
    old TEXT,
    new TEXT,
    reason TEXT,
    author TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plan_changes_project ON plan_changes (project_id, id);

-- A rollout's risks, issues, decisions and blockers (services/raid.py).
CREATE TABLE IF NOT EXISTS raid_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    impact TEXT NOT NULL DEFAULT 'medium',
    likelihood TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    owner_id INTEGER REFERENCES users(id),
    due_date TEXT,
    stage TEXT,
    resolution TEXT,
    customer_visible INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_raid_project ON raid_items (project_id, status);

-- Document templates for the rollout report, the portfolio report and the
-- sign-off (services/doc_templates.py): brand, sections and text, as JSON.
CREATE TABLE IF NOT EXISTS doc_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    config TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);

-- Sign-up links an admin hands to a new colleague (services/signup.py): only
-- a hash is stored; each creates pending accounts the admins approve.
CREATE TABLE IF NOT EXISTS signup_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    role TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    project_role TEXT,
    max_uses INTEGER NOT NULL DEFAULT 1,
    uses INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

-- Active minutes per person per workspace-local day (services/activity.py):
-- counted only while Odin is open, visible and in use.
CREATE TABLE IF NOT EXISTS user_activity (
    user_id INTEGER NOT NULL REFERENCES users(id),
    day TEXT NOT NULL,
    minutes INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

-- The agreed scope of a rollout (services/signoff.py): recorded while scoping,
-- marked delivered / partial / descoped at the end, listed on the sign-off.
CREATE TABLE IF NOT EXISTS scope_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    position INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    detail TEXT,
    status TEXT NOT NULL DEFAULT 'agreed',
    note TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scope_project ON scope_items (project_id, position);

-- Sign-off documents (services/signoff.py): each version freezes its content
-- and fingerprint when sent; the customer signs, then we countersign. A
-- scanned copy (document_id) or an admin's written waiver also completes it.
CREATE TABLE IF NOT EXISTS signoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    signer_id INTEGER REFERENCES users(id),
    signer_name TEXT, signer_title TEXT, signer_email TEXT,
    signed_at TEXT, signed_ip TEXT, signed_agent TEXT, signature TEXT,
    counter_id INTEGER REFERENCES users(id),
    counter_name TEXT, counter_title TEXT,
    counter_signed_at TEXT, counter_ip TEXT, counter_agent TEXT, counter_signature TEXT,
    reject_comment TEXT, rejected_at TEXT,
    document_id INTEGER REFERENCES documents(id),
    waiver_reason TEXT, waived_by TEXT,
    link_issued_by TEXT, link_issued_at TEXT,
    completed_at TEXT,
    UNIQUE (project_id, version)
);

-- One row a day of the portfolio's headline counts (services/dashboard.py):
-- the history behind the Dashboard's week-over-week deltas.
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    day TEXT PRIMARY KEY,
    active INTEGER NOT NULL,
    overdue INTEGER NOT NULL,
    over_sla INTEGER NOT NULL,
    due_soon INTEGER NOT NULL,
    awaiting INTEGER NOT NULL,
    idle INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS account_managers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    email TEXT,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS partners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS partner_account_managers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    deleted_at TEXT,
    FOREIGN KEY (partner_id) REFERENCES partners(id)
);

CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS outsourcers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    email TEXT,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS ms_connection (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT,
    refresh_token TEXT,
    expires_at INTEGER,
    connected_email TEXT,
    team_id TEXT,
    team_name TEXT,
    channel_id TEXT,
    channel_name TEXT,
    connected_at TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    client TEXT NOT NULL,
    po_number TEXT,
    po_date TEXT,
    stage TEXT NOT NULL DEFAULT 'PO Received',
    owner_id INTEGER NOT NULL,
    start_date TEXT,
    target_end_date TEXT,
    via TEXT,
    account_manager_name TEXT,
    account_manager_email TEXT,
    partner_name TEXT,
    partner_account_manager_name TEXT,
    partner_account_manager_email TEXT,
    delivery_mode TEXT NOT NULL DEFAULT 'Distribution/MSSP',
    outsourcer_name TEXT,
    outsourcer_email TEXT,
    vendor_name TEXT,
    product_name TEXT,
    access_token TEXT UNIQUE,
    stage_entered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    uploaded_by TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    assignee_id INTEGER,
    due_date TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT,
    done_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (assignee_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS status_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    author TEXT NOT NULL,
    note TEXT NOT NULL,
    stage TEXT NOT NULL,
    created_at TEXT NOT NULL,
    guest_visible INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id INTEGER,
    resource_name TEXT,
    details TEXT,
    timestamp TEXT NOT NULL,
    ip_address TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,
    project_id INTEGER,
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT DEFAULT 'info',
    created_at TEXT NOT NULL,
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS alert_type_settings (
    alert_type TEXT PRIMARY KEY,
    severity TEXT NOT NULL DEFAULT 'warning',
    threshold_days INTEGER,
    notify_email INTEGER NOT NULL DEFAULT 0,
    notify_teams INTEGER NOT NULL DEFAULT 0,
    notify_inapp INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS role_permissions (
    permission TEXT NOT NULL,
    role TEXT NOT NULL,
    allowed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (permission, role)
);
