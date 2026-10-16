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

-- A rollout's dated commitments (services/milestones.py): marked done when
-- reached, shown on the calendar and the timeline; customer_visible ones are
-- the only ones a customer, a partner or the customer's report ever carries.
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    date TEXT NOT NULL,
    stage TEXT,
    customer_visible INTEGER NOT NULL DEFAULT 0,
    done_at TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones (project_id, date);

-- Automations (services/rules.py): a trigger (event + event_config JSON), the
-- conditions and the actions (JSON lists). armed_at: made or last resumed; a
-- condition the alert pass sees fires only when it arose after that. Not
-- project-keyed: a reset keeps the rules, as it keeps the templates.
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    event TEXT NOT NULL,
    event_config TEXT NOT NULL DEFAULT '{}',
    conditions TEXT NOT NULL DEFAULT '[]',
    actions TEXT NOT NULL DEFAULT '[]',
    paused INTEGER NOT NULL DEFAULT 0,
    armed_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
-- Each firing of a rule on a rollout (its run log): what happened, each action's
-- outcome (detail, JSON). event_key: the scanned condition it fired for, once
-- per rule. Purged with the rollout; trimmed past rule_runs_keep_days.
CREATE TABLE IF NOT EXISTS rule_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES projects(id),
    event TEXT NOT NULL,
    event_key TEXT,
    at TEXT NOT NULL,
    ok INTEGER NOT NULL DEFAULT 0,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_rule_runs_rule ON rule_runs (rule_id, id);
CREATE INDEX IF NOT EXISTS idx_rule_runs_project ON rule_runs (project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_runs_key ON rule_runs (rule_id, event_key) WHERE event_key IS NOT NULL;

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

-- Custom fields (services/fields.py): an admin defines them (Settings › Rollouts
-- & workflow); each rollout holds one value per field, purged with the rollout.
-- kind: text | number | date | choice | yesno; choices: a JSON list.
CREATE TABLE IF NOT EXISTS custom_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    choices TEXT,
    required INTEGER NOT NULL DEFAULT 0,
    customer_visible INTEGER NOT NULL DEFAULT 0,
    show_in_list INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS project_field_values (
    project_id INTEGER NOT NULL REFERENCES projects(id),
    field_id INTEGER NOT NULL REFERENCES custom_fields(id),
    value TEXT NOT NULL,
    PRIMARY KEY (project_id, field_id)
);

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
    superseded_at TEXT,   -- the rollout was reopened after this completed: kept as signed, no longer closes it
    chase_count INTEGER NOT NULL DEFAULT 0, chased_at TEXT,   -- reminders to the signatory (services/chasers.py)
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
    vendor_id INTEGER REFERENCES vendors(id),
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

-- Finish-to-start: task_id waits on depends_on_task_id, both of one rollout
-- (services/task_links.py). Dies with either task and with the project.
CREATE TABLE IF NOT EXISTS task_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    UNIQUE (task_id, depends_on_task_id)
);
CREATE INDEX IF NOT EXISTS idx_task_links_project ON task_links (project_id);

-- The tasks a template's stages bring to a new rollout (services/template_tasks.py):
-- the project role each lands on, a due offset from the stage's start, and at most one
-- other template task it waits on. Not project-keyed: editing one never touches
-- rollouts already made; they go with their stage.
CREATE TABLE IF NOT EXISTS template_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage_id INTEGER NOT NULL REFERENCES stage_template_stages(id) ON DELETE CASCADE,
    title TEXT NOT NULL, role TEXT, offset_days INTEGER NOT NULL DEFAULT 0, estimate_hours REAL,
    waits_on_id INTEGER REFERENCES template_tasks(id) ON DELETE SET NULL,
    position INTEGER NOT NULL DEFAULT 0
);

-- The calls to the CRM intake endpoint (services/intake.py): who, when, what became of it.
-- A trimmed log, newest 200 kept, not history: project_id is set to NULL when the rollout is purged.
CREATE TABLE IF NOT EXISTS intake_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_name TEXT NOT NULL, at TEXT NOT NULL, status INTEGER NOT NULL, result TEXT NOT NULL,
    deal_id TEXT, project_id INTEGER, detail TEXT
);

-- Customer self-service (services/asks.py): a task's kind (tasks.kind: task |
-- upload | form, with tasks.ask_category or tasks.ask_form) and the answers
-- an ask's external assignee gave (an upload's: the document id under key
-- "file"). Dies with the task and with the project.
CREATE TABLE IF NOT EXISTS task_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    question_key TEXT NOT NULL,
    value TEXT NOT NULL,
    by_id INTEGER REFERENCES users(id),
    by_name TEXT NOT NULL,
    at TEXT NOT NULL,
    UNIQUE (task_id, question_key)
);

-- The customer's rating of a rollout, given when they sign a sign-off
-- version (services/asks.py): once per version; internal reading only.
CREATE TABLE IF NOT EXISTS csat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    signoff_version INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    by_id INTEGER REFERENCES users(id),
    by_name TEXT NOT NULL,
    at TEXT NOT NULL,
    UNIQUE (project_id, signoff_version)
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

-- Mute or follow one rollout (services/notifications.py): a participant who
-- muted it gets no mail or Teams from it; staff not on it who follow it hear
-- of its events. Purged with the project.
CREATE TABLE IF NOT EXISTS rollout_watch (
    user_id INTEGER NOT NULL REFERENCES users(id),
    project_id INTEGER NOT NULL REFERENCES projects(id),
    mode TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, project_id)
);
