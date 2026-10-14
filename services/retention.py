"""Audit log retention (Settings › Audit & compliance › Keep for N years).

The audit log is append-only: triggers refuse UPDATE and DELETE, so no
account can thin its own evidence. Retention is the one exception and it is
not an account: the nightly scheduler, and only after the rows are safe.

  1. rows older than the cutoff are written to a CSV in
     <data>/audit-archive/ (backups include that folder), with a SHA-256;
  2. in one transaction the delete trigger is lifted, those rows removed and
     the trigger put back;
  3. an audit row records what was archived where, and its checksum.

With "forever" nothing happens.
"""
from security import safe_csv_writer
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta

import db as _db

ARCHIVE_DIR_NAME = "audit-archive"
NO_DELETE = "CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete BEFORE DELETE ON audit_logs BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END"


def archive_dir():
    path = os.path.join(_db.DATA_DIR, ARCHIVE_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def run_audit_retention(now=None):
    """Archive and remove audit rows past the retention period. Returns
    (rows_removed, archive_path or None). Needs no app context."""
    from policies import policy
    con = sqlite3.connect(_db.DB_PATH)
    try:
        keep = policy("audit_keep", con)
        if keep == "forever":
            return 0, None
        cutoff = ((now or datetime.utcnow()) - timedelta(days=365 * int(keep))).isoformat()
        cur = con.execute("SELECT * FROM audit_logs WHERE timestamp < ? ORDER BY id", (cutoff,))
        rows = cur.fetchall()
        if not rows:
            return 0, None
        path = os.path.join(archive_dir(), f"audit-before-{cutoff[:10]}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv")
        with open(path, "w", newline="") as fh:
            writer = safe_csv_writer(fh)   # a cell starting with = + - @ is defused, as in every export
            writer.writerow([d[0] for d in cur.description])
            writer.writerows(rows)
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        last_id = rows[-1][0]
        with con:   # one transaction: the trigger is never missing outside it
            con.execute("BEGIN IMMEDIATE")   # DDL does not open one by itself: without this the DROP commits alone
            con.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete")
            con.execute("DELETE FROM audit_logs WHERE timestamp < ? AND id <= ?", (cutoff, last_id))
            con.execute(NO_DELETE)
            con.execute(
                "INSERT INTO audit_logs (user_id, username, action, resource_type, resource_name, details, timestamp) VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                ("scheduler", "audit_retention", "audit_logs", os.path.basename(path),
                 f"{len(rows)} rows older than {cutoff[:10]} archived (sha256 {digest}) and removed; keep {keep} years", datetime.utcnow().isoformat()))
        return len(rows), path
    finally:
        con.close()
