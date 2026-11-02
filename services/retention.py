"""Audit log retention (Settings › Audit & compliance › Keep for N years).

The audit log is append-only: triggers refuse UPDATE and DELETE, so no
account can thin its own evidence. Retention is the one exception and it is
not an account: the nightly scheduler, and only after the rows are safe.

  1. rows older than the cutoff are written to a CSV in
     <data>/audit-archive/ (backups include that folder), with a SHA-256;
  2. in one transaction the delete trigger is lifted, those rows removed and
     the trigger put back;
  3. an audit row records what was archived where, and its checksum.

The same period keeps the signed record of a rollout that was deleted
(<data>/signoff-archive/, written by `keep_evidence`, trimmed here).
With "forever" nothing happens.
"""
from security import safe_csv_writer
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta

import db as _db

ARCHIVE_DIR_NAME = "audit-archive"
EVIDENCE_DIR_NAME = "signoff-archive"   # the signed record of a deleted rollout, kept for the same period (audit_keep)
NO_DELETE = "CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete BEFORE DELETE ON audit_logs BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END"


def archive_dir():
    path = os.path.join(_db.DATA_DIR, ARCHIVE_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def evidence_dir():
    path = os.path.join(_db.DATA_DIR, EVIDENCE_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def keep_evidence(project, rows, user, reason):
    """Write the signed record of a rollout about to be deleted to
    <data>/signoff-archive/: per signed version the PDF as the customer
    saw it, a JSON with the frozen content, its SHA-256, every signature
    column and the customer's rating, and the paper copy when there is one.
    Returns the file names. The nightly purge deletes the rows after the undo
    window; these files stay until `audit_keep` years pass (trim_evidence)."""
    import json
    import shutil
    from db import UPLOAD_DIR, get_db
    from security import file_stem
    from services import signoff
    from services.signoff_pdf import render
    folder, db = evidence_dir(), get_db()
    now = datetime.utcnow().isoformat()
    names = []
    for row in rows:
        stem = f"{project['id']}-{file_stem(project['name'])}-v{row['version']}"
        data = {k: row[k] for k in row.keys() if k != "content"} | {"content": json.loads(row["content"])}
        csat = db.execute("SELECT rating, comment, by_name, at FROM csat WHERE project_id = ? AND signoff_version = ?", (project["id"], row["version"])).fetchone()
        data |= {"csat": dict(csat) if csat else None, "project_name": project["name"], "deleted_by": {"id": user.get("user_id"), "name": user.get("user_name")},
                 "reason": reason, "deleted_at": now}
        with open(os.path.join(folder, stem + ".pdf"), "wb") as fh:
            fh.write(render(signoff.view(row, True, False)))
        with open(os.path.join(folder, stem + ".json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
        names += [stem + ".pdf", stem + ".json"]
        doc = row["document_id"] and db.execute("SELECT filename, stored_name FROM documents WHERE id = ?", (row["document_id"],)).fetchone()
        paper = doc and os.path.join(UPLOAD_DIR, str(project["id"]), doc["stored_name"])
        if paper and os.path.isfile(paper):
            names.append(f"{stem}-paper{os.path.splitext(doc['filename'])[1][:10].lower()}")
            shutil.copyfile(paper, os.path.join(folder, names[-1]))
    return names


def trim_evidence(cutoff):
    """Remove evidence files last written before `cutoff` (an ISO timestamp).
    ponytail: by file time; a restore from backup renews it, which only keeps files longer."""
    folder, limit = evidence_dir(), datetime.fromisoformat(cutoff).timestamp()
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and os.path.getmtime(path) < limit:
            os.remove(path)


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
        trim_evidence(cutoff)
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
