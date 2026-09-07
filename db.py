"""Database layer: connection, schema/migration, settings + lookup reads.

Depends only on constants (and Flask's request-scoped `g` for the connection
cache). Never imports app or services, so it sits safely below them in the
import graph — routes and services import from here, not the reverse.
"""
import os
import re
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta

from flask import g
from werkzeug.security import check_password_hash, generate_password_hash

from constants import (
    ALERT_TYPES,
    SOFT_DELETE_TABLES,
    DEFAULT_ALERT_TYPE_SETTINGS,
    DEFAULT_DOC_CATEGORIES,
    DEFAULT_SETTINGS,
    DEFAULT_STAGES,
    DROPPED_PROJECT_COLUMNS,
    NEW_PROJECT_COLUMNS,
    NEW_USER_COLUMNS,
    PERMISSIONS,
    ROLES,
    UNDO_WINDOW_SECS,
)

# Where mutable state lives. Defaults to the source directory so local dev is
# unchanged, but containers set ODIN_DATA_DIR to a mounted volume — otherwise
# the database and every upload would vanish with the container.
DATA_DIR = os.environ.get("ODIN_DATA_DIR") or os.path.dirname(__file__)
DB_PATH = os.path.join(DATA_DIR, "odin.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")  # ships with the code
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def assert_safe_table(table, allowed=SOFT_DELETE_TABLES):
    """Guard the few queries that must interpolate a table name.

    Every caller passes a server-side constant today, so this is defence in
    depth — it turns a future refactoring mistake into a loud failure instead
    of a SQL injection.
    """
    if table not in allowed or not _SAFE_IDENTIFIER.match(table):
        raise ValueError(f"unsafe table identifier: {table!r}")
    return table


def get_db():
    if "db" not in g:
        # timeout: wait up to 10s on a write lock instead of failing immediately
        # with "database is locked" under concurrent gunicorn threads.
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        # WAL: readers never block the writer and vice versa — matters under
        # gunicorn's 2 workers × 4 threads. Persistent per database file.
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def soft_delete(table, item_id):
    """Mark row as deleted; recoverable for UNDO_WINDOW_SECS."""
    assert_safe_table(table)  # identifiers can't be parameterised — allowlist instead
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(f"UPDATE {table} SET deleted_at = ? WHERE id = ?", (now, item_id))
    db.commit()


def restore_deleted(table, item_id):
    """Restore a soft-deleted row (undo)."""
    assert_safe_table(table)
    db = get_db()
    db.execute(f"UPDATE {table} SET deleted_at = NULL WHERE id = ?", (item_id,))
    db.commit()


def cleanup_soft_deletes(db=None):
    """Permanently remove rows older than UNDO_WINDOW_SECS, and everything that
    hangs off them.

    Purging a project used to delete only the projects row, leaving its status
    notes and tasks pointing at an id that no longer existed (PRAGMA
    foreign_key_check reported them) and leaving every uploaded file on disk
    forever — where it still got swept into each backup.
    """
    if db is None:
        db = get_db()
    cutoff = (datetime.utcnow() - timedelta(seconds=UNDO_WINDOW_SECS)).isoformat()

    doomed = [row[0] for row in db.execute(
        "SELECT id FROM projects WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,)
    )]

    # Delete the files backing any document that is about to disappear —
    # whether it was deleted on its own or belongs to a project being purged.
    marks = ",".join("?" for _ in doomed)
    doomed_docs = db.execute(
        "SELECT project_id, stored_name FROM documents "
        f"WHERE (deleted_at IS NOT NULL AND deleted_at < ?){f' OR project_id IN ({marks})' if doomed else ''}",
        (cutoff, *doomed),
    ).fetchall()
    for project_id, stored_name in doomed_docs:
        _remove_upload(project_id, stored_name)

    if doomed:
        for table in ("status_notes", "tasks", "alerts", "documents"):
            db.execute(f"DELETE FROM {table} WHERE project_id IN ({marks})", doomed)

    for table in ["projects", "documents", "account_managers", "partners", "partner_account_managers", "vendors", "products", "outsourcers"]:
        db.execute(f"DELETE FROM {table} WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,))

    _purge_orphans(db)
    db.commit()


def _remove_upload(project_id, stored_name):
    """Best-effort file removal — a missing file must not abort the purge."""
    try:
        os.remove(os.path.join(UPLOAD_DIR, str(project_id), stored_name))
    except OSError:
        pass


def _purge_orphans(db):
    """Sweep rows and files whose project is already gone.

    Covers data orphaned by the older cleanup, which deleted projects without
    their children. Everything removed here is unreachable by definition: no
    project row means no page can ever display it.
    """
    for table in ("status_notes", "tasks", "alerts"):
        column = "project_id"
        db.execute(
            f"DELETE FROM {table} WHERE {column} IS NOT NULL "
            f"AND {column} NOT IN (SELECT id FROM projects)"
        )

    if not os.path.isdir(UPLOAD_DIR):
        return
    live = {str(row[0]) for row in db.execute("SELECT id FROM projects")}
    for entry in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, entry)
        if os.path.isdir(path) and entry not in live:
            shutil.rmtree(path, ignore_errors=True)



def _backfill_stage_entered_at(db):
    """One-time: derive each project's current-stage entry from its note history.

    Mirrors services.analytics.stage_timeline — db.py sits below services in the
    import graph and can't import it. The duplication is inert after the first
    run, since every stage change maintains the column from then on.
    """
    rows = db.execute(
        "SELECT id, stage, created_at FROM projects WHERE stage_entered_at IS NULL"
    ).fetchall()
    if not rows:
        return
    first_stage_row = db.execute("SELECT name FROM stages ORDER BY position LIMIT 1").fetchone()
    if first_stage_row is None:
        return
    first_stage = first_stage_row[0]

    for project_id, stage, created_at in rows:
        notes = db.execute(
            "SELECT stage, created_at FROM status_notes WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        current_stage, entered = first_stage, created_at
        for note_stage, note_at in notes:
            if note_at < created_at:
                continue                      # a note predating its project is corrupt
            if note_stage != current_stage:   # consecutive same-stage notes are one visit
                current_stage, entered = note_stage, note_at
        db.execute("UPDATE projects SET stage_entered_at = ? WHERE id = ?", (entered, project_id))


# ponytail: ad-hoc ALTER-based migration, no framework. Move to a real
# migration tool (alembic or similar) if the schema starts changing often.
def migrate_db(db):
    existing = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
    for column, coltype in NEW_PROJECT_COLUMNS.items():
        if column not in existing:
            db.execute(f"ALTER TABLE projects ADD COLUMN {column} {coltype}")

    # Commercial phase-out: permanently drop the invoice/payment/PO-money columns
    # (identifiers are allowlisted in constants, never user input). Irreversible.
    for column in DROPPED_PROJECT_COLUMNS:
        if column in existing:
            db.execute(f"ALTER TABLE projects DROP COLUMN {column}")

    user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
    role_column_is_new = "role" not in user_columns
    for column, coltype in NEW_USER_COLUMNS.items():
        if column not in user_columns:
            db.execute(f"ALTER TABLE users ADD COLUMN {column} {coltype}")
    if role_column_is_new:
        # pre-RBAC installs: promote the original (lowest-id) user to Admin once
        db.execute("UPDATE users SET role = 'Admin' WHERE id = (SELECT MIN(id) FROM users)")
    # Any install still on the seed password gets funnelled to change it at
    # next login — the audit found admin/changeme live in production. Checked
    # every boot (one hash), not just when the column is new: a migration that
    # crashes after its ALTER has already committed the column in SQLite.
    # Plain tuples: migrate_db runs on a connection with no row_factory.
    for user_id, password_hash in db.execute("SELECT id, password_hash FROM users WHERE username = 'admin'").fetchall():
        if check_password_hash(password_hash, "changeme"):
            db.execute("UPDATE users SET must_change_password = 1 WHERE id = ?", (user_id,))


    # Every project gets a customer link; older rows only had the vendor one.
    for (project_id,) in db.execute("SELECT id FROM projects WHERE customer_token IS NULL").fetchall():
        db.execute("UPDATE projects SET customer_token = ? WHERE id = ?", (secrets.token_urlsafe(16), project_id))

    # Add deleted_at soft-delete columns to all relevant tables (undo/recovery)
    for table in ["projects", "documents", "account_managers", "partners", "partner_account_managers", "vendors", "products", "outsourcers"]:
        table_columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if "deleted_at" not in table_columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT")

    # Stage SLAs need to know when the project entered its current stage.
    # updated_at can't stand in for that — project_edit bumps it too, so an
    # unrelated metadata change would silently restart the SLA clock.
    if "stage_entered_at" not in existing:
        db.execute("ALTER TABLE projects ADD COLUMN stage_entered_at TEXT")

    stage_columns = {row[1] for row in db.execute("PRAGMA table_info(stages)")}
    if "sla_days" not in stage_columns:
        db.execute("ALTER TABLE stages ADD COLUMN sla_days INTEGER")

    # status_notes.guest_visible: gates which notes the token-holding guest can
    # see. Defaults to 0 (hidden) so pre-existing internal/financial notes never
    # leak — only rows explicitly inserted as guest-safe show on the guest page.
    note_columns = {row[1] for row in db.execute("PRAGMA table_info(status_notes)")}
    if "guest_visible" not in note_columns:
        db.execute("ALTER TABLE status_notes ADD COLUMN guest_visible INTEGER NOT NULL DEFAULT 0")

    if not db.execute("SELECT 1 FROM stages LIMIT 1").fetchone():
        for position, name in enumerate(DEFAULT_STAGES):
            db.execute("INSERT INTO stages (name, position) VALUES (?, ?)", (name, position))

    if not db.execute("SELECT 1 FROM doc_categories LIMIT 1").fetchone():
        for name in DEFAULT_DOC_CATEGORIES:
            db.execute("INSERT INTO doc_categories (name) VALUES (?)", (name,))

    _backfill_stage_entered_at(db)

    for key, value in DEFAULT_SETTINGS.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    # alert dismissals moved to the session (per-login, never persisted) —
    # drop the old persistent table from installs that had it
    db.execute("DROP TABLE IF EXISTS alert_dismissals")

    # "In-house" renamed to "Distribution/MSSP" — idempotent, no-op after first run
    db.execute("UPDATE projects SET delivery_mode = 'Distribution/MSSP' WHERE delivery_mode = 'In-house'")

    # Create audit_logs table if missing (audit trail)
    db.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
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
    )""")
    # Append-only: the audit trail is evidence, and evidence that can be
    # edited or thinned by the same account it describes is not evidence.
    # Retention is deliberately unbounded (SOC 2 asks for 12+ months).
    for verb in ("UPDATE", "DELETE"):
        db.execute(
            f"CREATE TRIGGER IF NOT EXISTS audit_logs_no_{verb.lower()} BEFORE {verb} ON audit_logs "
            f"BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END"
        )

    # Create alerts table if missing (notifications)
    db.execute("""CREATE TABLE IF NOT EXISTS alerts (
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
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS alert_type_settings (
        alert_type TEXT PRIMARY KEY,
        severity TEXT NOT NULL DEFAULT 'warning',
        threshold_days INTEGER,
        notify_email INTEGER NOT NULL DEFAULT 0,
        notify_teams INTEGER NOT NULL DEFAULT 0,
        notify_inapp INTEGER NOT NULL DEFAULT 1
    )""")
    ats_columns = {row[1] for row in db.execute("PRAGMA table_info(alert_type_settings)")}
    had_legacy_enabled = "enabled" in ats_columns
    for column, coltype in {
        "threshold_days": "INTEGER",
        "notify_email": "INTEGER NOT NULL DEFAULT 0",
        "notify_teams": "INTEGER NOT NULL DEFAULT 0",
        "notify_inapp": "INTEGER NOT NULL DEFAULT 1",
    }.items():
        if column not in ats_columns:
            db.execute(f"ALTER TABLE alert_type_settings ADD COLUMN {column} {coltype}")
    if had_legacy_enabled:
        # pre-existing installs: carry the old single enabled flag over as
        # the new in-app master switch, one time only
        db.execute("UPDATE alert_type_settings SET notify_inapp = enabled")

    for alert_type, config in DEFAULT_ALERT_TYPE_SETTINGS.items():
        db.execute(
            "INSERT OR IGNORE INTO alert_type_settings (alert_type, severity, threshold_days, notify_email, notify_teams, notify_inapp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (alert_type, config["severity"], config["threshold_days"], config["notify_email"], config["notify_teams"], config["notify_inapp"]),
        )

    # carry over the old shared due_soon_days / stale_days settings (if this
    # install had customized them) into the new per-type threshold columns —
    # one time only, only where a per-type threshold hasn't been set yet
    legacy_due_soon = db.execute("SELECT value FROM settings WHERE key = 'due_soon_days'").fetchone()
    legacy_stale = db.execute("SELECT value FROM settings WHERE key = 'stale_days'").fetchone()
    legacy_thresholds = {
        "due_soon_client": int(legacy_due_soon[0]) if legacy_due_soon else None,
        "due_soon_vendor": int(legacy_due_soon[0]) if legacy_due_soon else None,
        "stale": int(legacy_stale[0]) if legacy_stale else None,
    }
    for alert_type, days in legacy_thresholds.items():
        if days is not None:
            db.execute(
                "UPDATE alert_type_settings SET threshold_days = ? WHERE alert_type = ? AND threshold_days IS NULL",
                (days, alert_type),
            )

    # brute-force lockout ledger for the login route (see security.py)
    db.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        ip_address TEXT,
        attempted_at TEXT NOT NULL,
        success INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_attempts_lookup "
        "ON login_attempts (username, ip_address, attempted_at)"
    )

    db.execute("""CREATE TABLE IF NOT EXISTS tasks (
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
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS role_permissions (
        permission TEXT NOT NULL,
        role TEXT NOT NULL,
        allowed INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (permission, role)
    )""")
    for permission, allowed_roles in PERMISSIONS.items():
        for role in ROLES:
            db.execute(
                "INSERT OR IGNORE INTO role_permissions (permission, role, allowed) VALUES (?, ?, ?)",
                (permission, role, 1 if role in allowed_roles else 0),
            )

    # Drop role_permissions rows for permissions that no longer exist (the
    # retired invoice ones). Left behind they'd be invisible dead weight, and a
    # future permission reusing the name would inherit stale allow/deny values.
    perm_placeholders = ",".join("?" for _ in PERMISSIONS)
    db.execute(f"DELETE FROM role_permissions WHERE permission NOT IN ({perm_placeholders})", tuple(PERMISSIONS))

    # One unresolved alert per (type, project). Without this, two board loads
    # racing on the same newly-overdue project both saw "no existing alert" and
    # both inserted — duplicate rows and duplicate notification emails.
    # Collapse any pre-existing duplicates first or the index cannot be built.
    db.execute("""DELETE FROM alerts WHERE resolved = 0 AND id NOT IN (
        SELECT MIN(id) FROM alerts WHERE resolved = 0 GROUP BY alert_type, project_id
    )""")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_one_open_per_project "
        "ON alerts (alert_type, project_id) WHERE resolved = 0"
    )

    # Clear alert rows whose type is no longer defined (e.g. the retired
    # payment alerts). Keyed off the live ALERT_TYPES set so lifecycle types
    # added later (schedule health, etc.) are never wiped on boot.
    placeholders = ",".join("?" for _ in ALERT_TYPES)
    db.execute(f"DELETE FROM alert_type_settings WHERE alert_type NOT IN ({placeholders})", tuple(ALERT_TYPES))
    db.execute(f"DELETE FROM alerts WHERE alert_type NOT IN ({placeholders})", tuple(ALERT_TYPES))

    db.commit()


def init_db():
    first_run = not os.path.exists(DB_PATH)
    db = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH) as f:
        db.executescript(f.read())
    migrate_db(db)
    cleanup_soft_deletes(db)
    if first_run:
        db.execute(
            "INSERT INTO users (username, password_hash, name, role, active, must_change_password) VALUES (?, ?, ?, ?, ?, ?)",
            ("admin", generate_password_hash("changeme", method="pbkdf2:sha256"), "Admin", "Admin", 1, 1),
        )
        db.commit()
        print("Created default user: admin / changeme  (change this password!)")
    db.close()


def get_stage_names():
    db = get_db()
    return [row["name"] for row in db.execute("SELECT name FROM stages ORDER BY position")]


def get_terminal_stage():
    return get_stage_names()[-1]


def get_doc_category_names():
    db = get_db()
    return [row["name"] for row in db.execute("SELECT name FROM doc_categories ORDER BY name")]


def get_contact_lists():
    """All six managed lookup lists for the project form's dropdowns, plus a
    partner_id -> [{name, email}] map (for the Partner -> Account Manager
    cascading select, rendered client-side from an embedded JSON blob)."""
    db = get_db()
    lists = {
        "account_managers": db.execute("SELECT * FROM account_managers WHERE deleted_at IS NULL ORDER BY name").fetchall(),
        "partners": db.execute("SELECT * FROM partners WHERE deleted_at IS NULL ORDER BY name").fetchall(),
        "vendors": db.execute("SELECT * FROM vendors WHERE deleted_at IS NULL ORDER BY name").fetchall(),
        "products": db.execute("SELECT * FROM products WHERE deleted_at IS NULL ORDER BY name").fetchall(),
        "outsourcers": db.execute("SELECT * FROM outsourcers WHERE deleted_at IS NULL ORDER BY name").fetchall(),
    }
    partner_managers = db.execute("SELECT * FROM partner_account_managers WHERE deleted_at IS NULL ORDER BY name").fetchall()
    partner_managers_by_partner = {}
    for row in partner_managers:
        partner_managers_by_partner.setdefault(str(row["partner_id"]), []).append(
            {"name": row["name"], "email": row["email"] or ""}
        )
    lists["partner_managers_by_partner"] = partner_managers_by_partner
    return lists


def get_setting(key, default=""):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def get_setting_int(key, default):
    try:
        return int(get_setting(key, str(default)))
    except ValueError:
        return default


def set_setting(key, value):
    db = get_db()
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    db.commit()
