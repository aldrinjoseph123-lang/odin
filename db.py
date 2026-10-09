"""Database layer: connection, schema/migration, settings + lookup reads.

Depends only on constants (and Flask's request-scoped `g` for the connection
cache). Never imports app or services, so it sits safely below them in the
import graph — routes and services import from here, not the reverse.
"""
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta

from flask import g
from werkzeug.security import check_password_hash, generate_password_hash

from constants import (
    CLIENT_PO_DOC_CATEGORY,
    ALERT_TYPES,
    SOFT_DELETE_TABLES,
    DEFAULT_ALERT_TYPE_SETTINGS,
    DEFAULT_DOC_CATEGORIES,
    SIGNOFF_DOC_CATEGORY,
    SIGNOFF_STAGE,
    DEFAULT_SETTINGS,
    DEFAULT_STAGES,
    DROPPED_PROJECT_COLUMNS,
    NEW_PROJECT_COLUMNS,
    NEW_USER_COLUMNS,
    PERMISSIONS,
    ROLES,
)

# Where mutable state lives. Defaults to the source directory so local dev is
# unchanged, but containers set ODIN_DATA_DIR to a mounted volume — otherwise
# the database and every upload would vanish with the container.
DATA_DIR = os.environ.get("ODIN_DATA_DIR") or os.path.dirname(__file__)
DB_PATH = os.path.join(DATA_DIR, "odin.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")  # ships with the code
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
AVATAR_DIR = os.path.join(DATA_DIR, "avatars")
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
    """Mark row as deleted; recoverable for the undo window (policy undo_minutes)."""
    assert_safe_table(table)  # identifiers can't be parameterised — allowlist instead
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(f"UPDATE {table} SET deleted_at = ? WHERE id = ?", (now, item_id))
    db.commit()


def restore_deleted(table, item_id):
    """Restore a soft-deleted row (undo) — only within the undo window, the
    promise the Undo button makes. Returns True when a row came back."""
    assert_safe_table(table)
    db = get_db()
    from policies import policy
    cutoff = (datetime.utcnow() - timedelta(minutes=policy("undo_minutes", db))).isoformat()
    done = db.execute(f"UPDATE {table} SET deleted_at = NULL WHERE id = ? AND deleted_at IS NOT NULL AND deleted_at >= ?", (item_id, cutoff)).rowcount
    db.commit()
    return bool(done)


def touch_project(db, project_id):
    """Work happened on the project (a note, a task, a document, the plan,
    RAID, the sign-off): it is not idle. The caller commits."""
    db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (datetime.utcnow().isoformat(), project_id))


def cleanup_soft_deletes(db=None):
    """Permanently remove rows older than the undo window, and everything that
    hangs off them.

    Purging a project used to delete only the projects row, leaving its status
    notes and tasks pointing at an id that no longer existed (PRAGMA
    foreign_key_check reported them) and leaving every uploaded file on disk
    forever — where it still got swept into each backup.
    """
    if db is None:
        db = get_db()
    from policies import policy
    cutoff = (datetime.utcnow() - timedelta(minutes=policy("undo_minutes", db))).isoformat()

    doomed = [row[0] for row in db.execute(
        "SELECT id FROM projects WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,)
    )]

    # The files backing any document that is about to disappear — whether it
    # was deleted on its own or belongs to a project being purged. They go
    # only once the rows are gone for good (a failed purge keeps both).
    marks = ",".join("?" for _ in doomed)
    doomed_docs = db.execute(
        "SELECT project_id, stored_name FROM documents "
        f"WHERE (deleted_at IS NOT NULL AND deleted_at < ?){f' OR project_id IN ({marks})' if doomed else ''}",
        (cutoff, *doomed),
    ).fetchall()

    # One transaction: children before parents, and all of it or none of it
    # (test report B3: a partner with account managers failed the foreign key
    # half way and left a half-committed purge).
    try:
        if doomed:
            # a sign-up link that named the project keeps working, without the project
            db.execute(f"UPDATE signup_links SET project_id = NULL, project_role = NULL WHERE project_id IN ({marks})", doomed)
            db.execute(f"UPDATE lessons SET project_id = NULL WHERE project_id IN ({marks})", doomed)   # the lesson stays in the library
            for table in ("doc_text", "ai_calls", "signoffs", "scope_items", "status_notes", "tasks", "alerts", "documents", "project_stages", "project_participants", "project_reports", "stage_approvals", "notifications", "plan_changes", "raid_items", "ai_jobs", "ai_suggestions"):
                db.execute(f"DELETE FROM {table} WHERE project_id IN ({marks})", doomed)

        gone_docs = "SELECT id FROM documents WHERE deleted_at IS NOT NULL AND deleted_at < ?"
        db.execute(f"DELETE FROM doc_text WHERE document_id IN ({gone_docs})", (cutoff,))   # the text read from a document goes with it
        db.execute(f"UPDATE signoffs SET document_id = NULL WHERE document_id IN ({gone_docs})", (cutoff,))   # a deleted signed copy
        # a partner's account managers go with it, whether or not each was deleted on its own
        db.execute("DELETE FROM partner_account_managers WHERE partner_id IN (SELECT id FROM partners WHERE deleted_at IS NOT NULL AND deleted_at < ?)", (cutoff,))
        for table in ["partner_account_managers", "projects", "documents", "account_managers", "partners", "vendors", "products", "outsourcers"]:
            db.execute(f"DELETE FROM {table} WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,))

        _purge_orphans(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    for project_id, stored_name in doomed_docs:
        _remove_upload(project_id, stored_name)


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
    for table in ("doc_text", "signoffs", "scope_items", "status_notes", "tasks", "alerts", "project_stages", "project_participants", "project_reports", "stage_approvals", "notifications", "plan_changes", "raid_items", "ai_jobs", "ai_suggestions"):
        column = "project_id"
        db.execute(
            f"DELETE FROM {table} WHERE {column} IS NOT NULL "
            f"AND {column} NOT IN (SELECT id FROM projects)"
        )
    # an account that signed up through a project's link keeps no pointer to a project that is gone
    db.execute("UPDATE users SET signup_project_id = NULL WHERE signup_project_id IS NOT NULL AND signup_project_id NOT IN (SELECT id FROM projects)")
    # Files are never swept here. A folder "not in the database" is also what
    # every upload looks like to an empty, missing or older database (a restore,
    # a volume mix-up), and deleting them then would destroy the documents.
    # Purged projects' files are removed with their rows in cleanup_soft_deletes.



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

    for project_id, stage, created_at in rows:
        # Each project's own first stage; a project with no list yet falls
        # back to the first template's opening stage.
        first_stage_row = db.execute(
            "SELECT name FROM project_stages WHERE project_id = ? ORDER BY position LIMIT 1", (project_id,)
        ).fetchone() or db.execute(
            "SELECT name FROM stage_template_stages ORDER BY template_id, position LIMIT 1"
        ).fetchone()
        if first_stage_row is None:
            continue
        first_stage = first_stage_row[0]
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
    if "password_login" not in user_columns:
        # Admins who exist before Microsoft sign-in keep their password, so
        # turning "Microsoft only" on can never lock everyone out.
        db.execute("UPDATE users SET password_login = 1 WHERE role = 'Admin' AND kind = 'internal'")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_ms_oid ON users(ms_oid) WHERE ms_oid IS NOT NULL")
    # Rose and amber accents were retired: they read as the overdue/warning states.
    db.execute("UPDATE users SET accent = CASE accent WHEN 'rose' THEN 'plum' ELSE 'sky' END WHERE accent IN ('rose', 'amber')")
    # 9 Oct 2026: pastel accents with red as the default (the user's call). Once:
    # everyone still on the old default blue, and the workspace default, move to red;
    # anyone who picks blue afterwards keeps it.
    if not db.execute("SELECT 1 FROM settings WHERE key = 'migrated.accent_red'").fetchone():
        db.execute("UPDATE users SET accent = 'red' WHERE accent = 'blue' OR accent IS NULL")
        db.execute("UPDATE settings SET value = 'red' WHERE key = 'policy.default_accent' AND value = 'blue'")
        db.execute("INSERT INTO settings (key, value) VALUES ('migrated.accent_red', '1')")
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
    # Who wrote a note, by id (names are editable, so a name cannot prove
    # authorship), and when it was last corrected. Older notes have no id and
    # stay read-only.
    if "author_id" not in note_columns:
        db.execute("ALTER TABLE status_notes ADD COLUMN author_id INTEGER")
    if "edited_at" not in note_columns:
        db.execute("ALTER TABLE status_notes ADD COLUMN edited_at TEXT")
    # A stage-change note remembers where the project came from, so its author
    # can undo the move for a few minutes (routes/projects.undo_stage_change).
    if "prev_stage" not in note_columns:
        db.execute("ALTER TABLE status_notes ADD COLUMN prev_stage TEXT")
    if "prev_entered_at" not in note_columns:
        db.execute("ALTER TABLE status_notes ADD COLUMN prev_entered_at TEXT")

    _migrate_stage_lists(db)
    _migrate_signoff_stage(db)
    # A saved report version is either the old plain text (kind 'text') or a
    # frozen snapshot of the report data plus the PM's words (services/report_data.py).
    report_columns = {row[1] for row in db.execute("PRAGMA table_info(project_reports)")}
    for column, coltype in (("kind", "TEXT NOT NULL DEFAULT 'text'"), ("data", "TEXT"), ("summary", "TEXT"), ("next_steps", "TEXT"), ("asks", "TEXT")):
        if report_columns and column not in report_columns:   # a fresh database creates the table, with them, further on
            db.execute(f"ALTER TABLE project_reports ADD COLUMN {column} {coltype}")
    # A sign-off version remembers who handed its signatory a sign-in link by hand (the signing record shows it).
    signoff_columns = {row[1] for row in db.execute("PRAGMA table_info(signoffs)")}
    for column in ("link_issued_by", "link_issued_at"):
        if signoff_columns and column not in signoff_columns:
            db.execute(f"ALTER TABLE signoffs ADD COLUMN {column} TEXT")
    # A rollout's plan: dates per stage and the baseline they are measured against (services/plan.py).
    plan_columns = {row[1] for row in db.execute("PRAGMA table_info(project_stages)")}
    for column in ("plan_start", "plan_end", "base_start", "base_end"):
        if column not in plan_columns:
            db.execute(f"ALTER TABLE project_stages ADD COLUMN {column} TEXT")
    _migrate_participants(db)
    # tasks.stage: which stage a task belongs to (name, like status_notes).
    # NULL = "whatever stage the project is in" — old tasks and quick adds.
    if "stage" not in {row[1] for row in db.execute("PRAGMA table_info(tasks)")}:
        db.execute("ALTER TABLE tasks ADD COLUMN stage TEXT")
    # Read-only API tokens (routes/tokens.py): only a hash is stored; the
    # token itself is shown once. Revoked/expired ones are trimmed after 90 days.
    db.execute("""CREATE TABLE IF NOT EXISTS api_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
        created_by TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
        last_used_at TEXT, revoked_at TEXT)""")
    # One row per backup run (backup.py): what was made, where it went, and
    # whether its restore test passed. Trimmed to the newest 200 by each run.
    db.execute("""CREATE TABLE IF NOT EXISTS backup_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL, finished_at TEXT, trigger TEXT, actor TEXT,
        file TEXT, size_bytes INTEGER, ok INTEGER NOT NULL DEFAULT 0,
        restore_ok INTEGER, restore_detail TEXT, destinations TEXT)""")
    # The AI framework (services/ai): jobs the web app queues for the
    # scheduler's AI worker, and every validation result per feature and
    # model. A job may name a project (purged with it); checks are trimmed
    # after 180 days, finished jobs after 30.
    db.execute("""CREATE TABLE IF NOT EXISTS ai_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL, feature TEXT, project_id INTEGER REFERENCES projects(id),
        payload TEXT, status TEXT NOT NULL DEFAULT 'queued', requested_by TEXT,
        created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, result TEXT, error TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS ai_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER, kind TEXT NOT NULL, feature TEXT, model TEXT, fingerprint TEXT, prompt_hash TEXT,
        state TEXT NOT NULL, seconds REAL, detail TEXT, output TEXT, created_at TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ai_checks_feature ON ai_checks (feature, fingerprint, prompt_hash)")
    # What a feature produced for a project: a draft a person uses or
    # dismisses, never a change by itself. Kept with the model, fingerprint
    # and prompt that made it; purged with its project.
    db.execute("""CREATE TABLE IF NOT EXISTS ai_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id), feature TEXT NOT NULL, payload TEXT NOT NULL,
        inputs_hash TEXT, model TEXT, fingerprint TEXT, prompt_hash TEXT, seconds REAL, job_id INTEGER,
        status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL, decided_by TEXT, decided_at TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ai_suggestions_project ON ai_suggestions (project_id, feature, status)")
    # Every request Odin sends to the AI server (services/ai/client.py chat):
    # what, for whom, how big, how long, whether it worked. The AI server's
    # integration guide asks each application to keep this; trimmed after 90
    # days, removed with the project.
    db.execute("""CREATE TABLE IF NOT EXISTS ai_calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, feature TEXT, job_id INTEGER, project_id INTEGER, username TEXT,
        model TEXT, input_chars INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER, seconds REAL, ok INTEGER NOT NULL, error TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ai_calls_at ON ai_calls (at)")
    # The lessons library: what went wrong and what to repeat, saved by a
    # project manager from a rollout (services/lessons.py). It outlives the
    # rollout: when a project is purged its lessons keep their words and the
    # rollout's name, and lose the link (project_id NULL).
    db.execute("""CREATE TABLE IF NOT EXISTS lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER REFERENCES projects(id), project_name TEXT NOT NULL,
        template_id INTEGER, product TEXT, vendor TEXT, client TEXT, kind TEXT NOT NULL, text TEXT NOT NULL, evidence TEXT,
        created_by TEXT NOT NULL, created_at TEXT NOT NULL)""")
    # The text of an uploaded document, read once for the AI features that
    # need it (services/doctext.py); purged with its project.
    db.execute("""CREATE TABLE IF NOT EXISTS doc_text (
        document_id INTEGER PRIMARY KEY REFERENCES documents(id), project_id INTEGER NOT NULL REFERENCES projects(id),
        chars INTEGER NOT NULL DEFAULT 0, text TEXT, error TEXT, extracted_at TEXT NOT NULL)""")
    # The old "Allow scheduled full backups to OneDrive" switch is now the
    # OneDrive destination in Settings → Backups.
    db.execute("INSERT OR IGNORE INTO settings (key, value) SELECT 'policy.dest_onedrive', '1' FROM settings WHERE key = 'onedrive_backup_enabled' AND value = '1'")
    # In-app notifications: one row per recipient per event. Read ones older
    # than 90 days are trimmed as new ones are written.
    db.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        project_id INTEGER REFERENCES projects(id),
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT,
        link TEXT,
        actor TEXT,
        created_at TEXT NOT NULL,
        read_at TEXT
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (user_id, read_at, id)")
    # the board and the flow count each project's tasks and notes: without these
    # every project scanned the whole table (test report OPS-11: 4.3 s at 2,000 projects, 96 ms with them)
    db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks (project_id, done)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_status_notes_project ON status_notes (project_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_documents_project ON documents (project_id, category)")
    # Customer approval of a stage change, when the project asks for it.
    # One row per change; a newer change supersedes an undecided older one.
    db.execute("""CREATE TABLE IF NOT EXISTS stage_approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        stage TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        requested_by TEXT NOT NULL,
        requested_at TEXT NOT NULL,
        decided_by TEXT,
        decided_at TEXT,
        comment TEXT
    )""")
    # Project reports: the PM's text, one row per saved version, never edited in place.
    db.execute("""CREATE TABLE IF NOT EXISTS project_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        version INTEGER NOT NULL,
        body TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'text',
        data TEXT,
        summary TEXT,
        next_steps TEXT,
        asks TEXT,
        UNIQUE (project_id, version)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS login_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        created_by INTEGER,
        ip_address TEXT
    )""")
    # A link is either a partner sign-in or a staff password reset; each is
    # only ever accepted by its own route.
    if "purpose" not in {row[1] for row in db.execute("PRAGMA table_info(login_links)")}:
        db.execute("ALTER TABLE login_links ADD COLUMN purpose TEXT NOT NULL DEFAULT 'signin'")
    # The account's session_epoch when the link was issued: a password change,
    # deactivation, role change or two-step reset bumps it and so kills every
    # link issued before (system map test SEC-3). Older links (NULL) are dead.
    if "epoch" not in {row[1] for row in db.execute("PRAGMA table_info(login_links)")}:
        db.execute("ALTER TABLE login_links ADD COLUMN epoch INTEGER")

    # Which document kinds partners and customers may see (Settings → Projects &
    # workflow). The client's PO is internal from the start.
    if "partners" not in {row[1] for row in db.execute("PRAGMA table_info(doc_categories)")}:
        db.execute("ALTER TABLE doc_categories ADD COLUMN partners INTEGER NOT NULL DEFAULT 1")
        db.execute("UPDATE doc_categories SET partners = 0 WHERE name = ?", (CLIENT_PO_DOC_CATEGORY,))
    # Every project has a vendor guest-link token. The old Jinja project page
    # minted a missing one on view; since the page is React (9 Oct 2026) this
    # fills them once instead.
    for (pid,) in db.execute("SELECT id FROM projects WHERE access_token IS NULL").fetchall():
        db.execute("UPDATE projects SET access_token = ? WHERE id = ?", (secrets.token_urlsafe(16), pid))
    # A product belongs to one vendor (9 Oct 2026, the user's call); older
    # products stay "any vendor" until an admin picks one.
    if "vendor_id" not in {row[1] for row in db.execute("PRAGMA table_info(products)")}:
        db.execute("ALTER TABLE products ADD COLUMN vendor_id INTEGER REFERENCES vendors(id)")
    if not db.execute("SELECT 1 FROM doc_categories LIMIT 1").fetchone():
        for name in DEFAULT_DOC_CATEGORIES:
            db.execute("INSERT INTO doc_categories (name) VALUES (?)", (name,))
        db.execute("UPDATE doc_categories SET partners = 0 WHERE name = ?", (CLIENT_PO_DOC_CATEGORY,))

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

    # The lookups every page makes (audit viewer and retention, My work, the
    # nav badges, approvals, purges): without these each scans its table.
    for name, table, columns in (
        ("idx_audit_logs_time", "audit_logs", "timestamp"),
        ("idx_audit_logs_resource", "audit_logs", "resource_type, resource_id"),
        ("idx_participants_user", "project_participants", "user_id"),
        ("idx_tasks_assignee", "tasks", "assignee_id, done"),
        ("idx_approvals_project", "stage_approvals", "project_id, id"),
        ("idx_alerts_project", "alerts", "project_id"),
        ("idx_notifications_project", "notifications", "project_id"),
        ("idx_signoffs_document", "signoffs", "document_id"),
        ("idx_ai_jobs_status", "ai_jobs", "status"),
        ("idx_projects_owner", "projects", "owner_id"),
        ("idx_projects_deleted", "projects", "deleted_at"),
    ):
        db.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")

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
            "INSERT INTO users (username, password_hash, name, role, active, must_change_password, password_login) VALUES (?, ?, ?, ?, ?, ?, 1)",
            ("admin", generate_password_hash("changeme", method="pbkdf2:sha256"), "Admin", "Admin", 1, 1),
        )
        db.commit()
        print("Created default user: admin / changeme  (change this password!)")
    db.close()


# ---- stages: every project owns its own list ------------------------------
#
# projects.stage and status_notes.stage hold stage *names*. A project's list
# lives in project_stages; templates in Settings are only where a new project
# copies its list from. "Closed" is therefore per project: its stage equals the
# last name in its own list. COALESCE keeps a project with no list yet (a row
# inserted outside the app) counted as open rather than vanishing.
PROJECT_CLOSED_SQL = (
    "COALESCE(p.stage = (SELECT ps.name FROM project_stages ps WHERE ps.project_id = p.id "
    "ORDER BY ps.position DESC LIMIT 1), 0)"
)
PROJECT_OPEN_SQL = f"({PROJECT_CLOSED_SQL} = 0)"


def _migrate_stage_lists(db):
    """Templates + per-project stage lists. The old global `stages` table
    becomes the "Generic" template; every project without a list gets a copy."""
    db.execute("""CREATE TABLE IF NOT EXISTS stage_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS stage_template_stages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id INTEGER NOT NULL REFERENCES stage_templates(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        position INTEGER NOT NULL,
        sla_days INTEGER,
        UNIQUE (template_id, name)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS project_stages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        position INTEGER NOT NULL,
        sla_days INTEGER,
        UNIQUE (project_id, name)
    )""")
    if not db.execute("SELECT 1 FROM stage_templates LIMIT 1").fetchone():
        legacy = db.execute("SELECT name, sla_days FROM stages ORDER BY position").fetchall()
        source = [(row[0], row[1]) for row in legacy] or [(name, None) for name in DEFAULT_STAGES]
        db.execute("INSERT INTO stage_templates (name) VALUES ('Generic')")
        template_id = db.execute("SELECT id FROM stage_templates WHERE name = 'Generic'").fetchone()[0]
        for position, (name, sla) in enumerate(source):
            db.execute(
                "INSERT INTO stage_template_stages (template_id, name, position, sla_days) VALUES (?, ?, ?, ?)",
                (template_id, name, position, sla),
            )
    template_id = db.execute("SELECT id FROM stage_templates ORDER BY id LIMIT 1").fetchone()[0]
    orphans = db.execute(
        "SELECT id, stage FROM projects WHERE id NOT IN (SELECT DISTINCT project_id FROM project_stages)"
    ).fetchall()
    for project_id, current in orphans:
        copy_template_stages(db, template_id, project_id)
        # A project sitting in a stage its new list lacks keeps that stage,
        # slotted before the terminal one, so nothing is silently re-staged.
        if current and not db.execute(
            "SELECT 1 FROM project_stages WHERE project_id = ? AND name = ?", (project_id, current)
        ).fetchone():
            last = db.execute(
                "SELECT MAX(position) FROM project_stages WHERE project_id = ?", (project_id,)
            ).fetchone()[0] or 0
            db.execute("UPDATE project_stages SET position = position + 1 WHERE project_id = ? AND position = ?", (project_id, last))
            db.execute("INSERT INTO project_stages (project_id, name, position) VALUES (?, ?, ?)", (project_id, current, last))


def _migrate_signoff_stage(db):
    """Once (30 Sep 2026): every template and every open project's list gets a
    Sign-off stage before its terminal one. An admin may remove it later; this
    never runs again, so it is not put back."""
    if db.execute("SELECT 1 FROM settings WHERE key = 'migration.signoff_stage'").fetchone():
        return
    def slot(table, key, owner_id):
        rows = db.execute(f"SELECT name, position FROM {table} WHERE {key} = ? ORDER BY position", (owner_id,)).fetchall()
        if len(rows) < 2 or any(r[0].lower() == SIGNOFF_STAGE.lower() for r in rows):
            return
        last = rows[-1][1]
        db.execute(f"UPDATE {table} SET position = position + 1 WHERE {key} = ? AND position >= ?", (owner_id, last))
        db.execute(f"INSERT INTO {table} ({key}, name, position) VALUES (?, ?, ?)", (owner_id, SIGNOFF_STAGE, last))
    for (template_id,) in db.execute("SELECT id FROM stage_templates").fetchall():
        slot("stage_template_stages", "template_id", template_id)
    for (project_id, stage) in db.execute("SELECT id, stage FROM projects").fetchall():
        last = db.execute("SELECT name FROM project_stages WHERE project_id = ? ORDER BY position DESC LIMIT 1", (project_id,)).fetchone()
        if last and last[0] != stage:          # a closed project keeps the history it had
            slot("project_stages", "project_id", project_id)
    if db.execute("SELECT 1 FROM doc_categories LIMIT 1").fetchone():   # a fresh database seeds it with the defaults
        db.execute("INSERT OR IGNORE INTO doc_categories (name) VALUES (?)", (SIGNOFF_DOC_CATEGORY,))
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('migration.signoff_stage', '1')")


def _migrate_participants(db):
    """Who is on a project, in what capacity. The owner is always its project
    manager; existing projects get that row on first boot."""
    db.execute("""CREATE TABLE IF NOT EXISTS project_participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id),
        role TEXT NOT NULL,
        added_by INTEGER,
        added_at TEXT NOT NULL,
        UNIQUE (project_id, user_id)
    )""")
    db.execute(
        "INSERT OR IGNORE INTO project_participants (project_id, user_id, role, added_by, added_at) "
        "SELECT id, owner_id, 'Project manager', NULL, created_at FROM projects"
    )


def set_project_manager(db, project_id, user_id, added_by=None):
    """The PM row follows the owner: the new owner becomes PM (upsert), and a
    previous owner who was PM is kept on the team as a coordinator."""
    db.execute(
        "UPDATE project_participants SET role = 'Coordinator' WHERE project_id = ? AND role = 'Project manager' AND user_id != ?",
        (project_id, user_id),
    )
    db.execute(
        "INSERT INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, 'Project manager', ?, ?) "
        "ON CONFLICT(project_id, user_id) DO UPDATE SET role = 'Project manager'",
        (project_id, user_id, added_by, datetime.utcnow().isoformat()),
    )


def partner_hidden_categories(db=None):
    """Document categories partners and customers never see."""
    return {r[0] for r in (db or get_db()).execute("SELECT name FROM doc_categories WHERE partners = 0")}


def participants_for(project_id):
    return get_db().execute(
        "SELECT pp.*, u.name, u.email, u.active, u.avatar FROM project_participants pp JOIN users u ON u.id = pp.user_id "
        "WHERE pp.project_id = ? ORDER BY CASE pp.role WHEN 'Project manager' THEN 0 ELSE 1 END, u.name",
        (project_id,),
    ).fetchall()


def current_approval(project_id):
    """The approval row for the latest stage change, or None."""
    return get_db().execute(
        "SELECT * FROM stage_approvals WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)
    ).fetchone()


def avatar_url(row):
    """The URL a page uses for a user's picture, or None. The filename is part
    of the path, so a replaced picture gets a new URL and no stale cache."""
    return f"/users/{row['id']}/avatar/{row['avatar']}" if row["avatar"] else None


def project_role_of(project_id, user_id):
    row = get_db().execute(
        "SELECT role FROM project_participants WHERE project_id = ? AND user_id = ?", (project_id, user_id)
    ).fetchone()
    return row["role"] if row else None


def is_customer_on(project_id, user_id):
    return get_db().execute(
        "SELECT 1 FROM project_participants WHERE project_id = ? AND user_id = ? AND role = 'Customer'", (project_id, user_id)
    ).fetchone() is not None


def my_project_ids(user_id):
    """Projects this user owns or participates in — the board's 'Mine' filter
    today, and the whole visible set for external accounts later."""
    return {row[0] for row in get_db().execute(
        "SELECT project_id FROM project_participants WHERE user_id = ? UNION SELECT id FROM projects WHERE owner_id = ?",
        (user_id, user_id),
    )}


def copy_template_stages(db, template_id, project_id):
    """Give a project its own copy of a template's stages (names, order, SLAs)."""
    for name, position, sla in db.execute(
        "SELECT name, position, sla_days FROM stage_template_stages WHERE template_id = ? ORDER BY position",
        (template_id,),
    ).fetchall():
        db.execute(
            "INSERT OR IGNORE INTO project_stages (project_id, name, position, sla_days) VALUES (?, ?, ?, ?)",
            (project_id, name, position, sla),
        )
    db.execute(
        "UPDATE projects SET stage_template_id = ? WHERE id = ? AND stage_template_id IS NULL",
        (template_id, project_id),
    )


def stage_rows(project_id):
    """This project's stages, in order. A project with no list (inserted outside
    the app, e.g. a bulk import) adopts the first template's on first read."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM project_stages WHERE project_id = ? ORDER BY position", (project_id,)
    ).fetchall()
    if rows:
        return rows
    if not db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
        return []
    template = db.execute("SELECT id FROM stage_templates ORDER BY id LIMIT 1").fetchone()
    if template is None:
        return []
    copy_template_stages(db, template["id"], project_id)
    db.commit()
    return db.execute(
        "SELECT * FROM project_stages WHERE project_id = ? ORDER BY position", (project_id,)
    ).fetchall()


def stages_for_projects(project_ids):
    """{project_id: [stage rows]} in one query — for the board and alerts."""
    ids = list(project_ids)
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    grouped = {}
    for row in get_db().execute(
        f"SELECT * FROM project_stages WHERE project_id IN ({marks}) ORDER BY project_id, position", ids
    ):
        grouped.setdefault(row["project_id"], []).append(row)
    for project_id in ids:
        if project_id not in grouped:
            grouped[project_id] = stage_rows(project_id)
    return grouped


def get_stage_names(project_id=None):
    """A project's stage names in order. Without a project: every name in use
    across projects, ordered by where it typically sits — for the list filters
    and the kanban columns, which span projects with different lists."""
    if project_id is None:
        return [row[0] for row in get_db().execute(
            "SELECT name FROM project_stages GROUP BY name ORDER BY MIN(position), name"
        )]
    return [row["name"] for row in stage_rows(project_id)]


def get_terminal_stage(project_id):
    names = get_stage_names(project_id)
    return names[-1] if names else None


def sla_for_project(project_id):
    """{stage name: sla_days} for this project's stages that have one."""
    return {row["name"]: row["sla_days"] for row in stage_rows(project_id) if row["sla_days"]}


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


def set_setting(key, value):
    db = get_db()
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    db.commit()
