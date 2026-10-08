"""Wipe demo/seed project data, keeping configuration and users.

Run before handing Odin to real users:

    python reset_data.py --dry-run     # show what would go
    python reset_data.py               # asks for confirmation
    python reset_data.py --yes         # no prompt (for scripted setup)

Kept:    users, roles/permissions, stages (and their SLAs), doc categories,
         contacts/partners/vendors/products/outsourcers, settings, the M365
         connection, and the audit log.
Removed: projects and everything hanging off them — status notes, tasks,
         document rows, alerts, each project's own stage list, its team,
         approval requests and saved reports — plus the uploaded files on
         disk, and every outstanding sign-in link (they belong to demo
         invitations). External accounts created by demo invites are kept
         like any other user; deactivate them from Users if unwanted.

The audit log is deliberately kept: it is the record of who did what, and
deleting it to tidy up demo data is exactly the kind of thing an audit trail
exists to prevent.
"""
import argparse
import os
import shutil
import sqlite3
import sys

from db import DB_PATH, UPLOAD_DIR

# Children before parents. Any new table keyed by project_id belongs here —
# the id counter is reset below, so a survivor would attach itself to the
# next project created (see the "new table" checklist in CLAUDE.md).
WIPE_TABLES = ["doc_text", "ai_calls", "ai_suggestions", "ai_jobs", "signoffs", "scope_items", "plan_changes", "raid_items", "notifications", "status_notes", "tasks", "documents", "alerts", "stage_approvals", "project_reports",
               "project_participants", "project_stages", "login_links", "signup_links", "projects"]


def counts(db):
    return {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in WIPE_TABLES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"No database at {DB_PATH} — nothing to reset.")
        return 1

    db = sqlite3.connect(DB_PATH)
    before = counts(db)
    uploads = sum(len(files) for _, _, files in os.walk(UPLOAD_DIR))

    print(f"Database: {DB_PATH}")
    for table, n in before.items():
        print(f"  {table:15} {n}")
    print(f"  {'uploaded files':15} {uploads}")

    if args.dry_run:
        print("\nDry run — nothing changed.")
        db.close()
        return 0

    if sum(before.values()) == 0 and uploads == 0:
        print("\nAlready empty.")
        db.close()
        return 0

    if not args.yes:
        print("\nThis permanently deletes the rows above and every uploaded file.")
        print("Users, stages, SLAs, contacts, settings and the audit log are kept.")
        if input("Type 'reset' to continue: ").strip() != "reset":
            print("Aborted.")
            db.close()
            return 1

    backup = f"{DB_PATH}.pre-reset.bak"
    shutil.copy2(DB_PATH, backup)

    # Children first: foreign keys point at projects, and PRAGMA foreign_keys
    # is on for app connections even though it is off by default here.
    for table in WIPE_TABLES:
        db.execute(f"DELETE FROM {table}")
    # The id counters are kept: the audit log survives the reset, and a new
    # project 1 would otherwise show the wiped project 1's history (test report OPS-6).
    from datetime import datetime
    db.execute("INSERT INTO audit_logs (user_id, username, action, resource_type, resource_id, resource_name, details, timestamp, ip_address) "
               "VALUES (NULL, ?, 'reset_data', 'workspace', NULL, NULL, ?, ?, NULL)",
               (os.environ.get("USER") or "command line", f"{sum(before.values())} rows wiped; copy at {backup}", datetime.utcnow().isoformat()))
    db.commit()
    db.execute("VACUUM")
    db.close()

    removed = 0
    if os.path.isdir(UPLOAD_DIR):
        for entry in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, entry)
            if os.path.isdir(path):
                removed += sum(len(f) for _, _, f in os.walk(path))
                shutil.rmtree(path)

    print(f"\nDone. Removed {sum(before.values())} rows and {removed} file(s).")
    print(f"Pre-reset backup: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
