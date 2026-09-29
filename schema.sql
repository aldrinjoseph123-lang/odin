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

CREATE TABLE IF NOT EXISTS doc_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
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
