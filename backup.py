"""Zip the SQLite DB + uploads folder into the data directory, and push it to
OneDrive when Microsoft 365 is connected.

A local copy is always written (KEEP_LOCAL most recent are kept) — a backup
that only exists when a cloud integration happens to be configured is not a
backup. Restore procedure: DEPLOY.md, "Restore".

Run manually: python backup.py
Or cron it daily, e.g.:
    0 2 * * * cd /path/to/PMS && ./venv/bin/python backup.py >> backup.log 2>&1

Also called from the "Backup Now" button in Settings (app.py imports this
module lazily to avoid a circular import).
"""
import os
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime

import db as _db
import graph

KEEP_LOCAL = 14


def _backup_dir():
    path = os.path.join(_db.DATA_DIR, "backups")
    os.makedirs(path, exist_ok=True)
    return path


def _backup_enabled():
    if not os.path.exists(_db.DB_PATH):
        return False
    db = sqlite3.connect(_db.DB_PATH)
    row = db.execute("SELECT value FROM settings WHERE key = 'onedrive_backup_enabled'").fetchone()
    db.close()
    return bool(row and row[0] == "1")


def run_backup(force=False):
    """force=True bypasses the admin on/off toggle — used by the manual
    'Backup Now' button, which is itself an explicit admin action."""
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    zip_name = f"odin-backup-{timestamp}.zip"
    DB_PATH, UPLOAD_DIR = _db.DB_PATH, _db.UPLOAD_DIR

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(_backup_dir(), zip_name)

        # Snapshot the database through SQLite's online backup API rather than
        # zipping the live file. zipfile reads page by page with no lock, so a
        # write landing mid-read produces an archive holding a half-applied
        # transaction — a backup that only fails when you try to restore it.
        snapshot = os.path.join(tmp, "odin.db")
        if os.path.exists(DB_PATH):
            source = sqlite3.connect(DB_PATH)
            target = sqlite3.connect(snapshot)
            try:
                with target:
                    source.backup(target)
            finally:
                target.close()
                source.close()

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(snapshot):
                zf.write(snapshot, arcname="odin.db")
            for folder, label in ((UPLOAD_DIR, "uploads"), (_db.AVATAR_DIR, "avatars")):
                for root, _dirs, files in os.walk(folder):
                    for fname in files:
                        full = os.path.join(root, fname)
                        zf.write(full, arcname=os.path.join(label, os.path.relpath(full, folder)))

    # Prune: newest KEEP_LOCAL stay. Names sort chronologically.
    older = sorted(f for f in os.listdir(_backup_dir()) if f.startswith("odin-backup-") and f.endswith(".zip"))
    for stale in older[:-KEEP_LOCAL]:
        os.remove(os.path.join(_backup_dir(), stale))

    if not graph.onedrive_configured():
        return True, f"Local backup written to {zip_path} (OneDrive not configured)"
    if not force and not _backup_enabled():
        return True, f"Local backup written to {zip_path} (OneDrive upload disabled in Settings)"
    ok, error = graph.upload_file(zip_path, f"Odin-Backups/{zip_name}")
    if not ok:
        return False, f"Local backup written to {zip_path}; OneDrive upload failed: {error}"
    return True, f"Backed up locally and to OneDrive ({zip_name})"


if __name__ == "__main__":
    success, err = run_backup()
    if success:
        print(err)
        sys.exit(0)
    else:
        print(f"Backup failed: {err}", file=sys.stderr)
        sys.exit(1)
