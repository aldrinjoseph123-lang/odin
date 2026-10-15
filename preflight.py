"""Production readiness check. Run inside the deployment environment:

    python preflight.py

Exits non-zero if anything would make this deployment unsafe. Each check
reports what to do about it rather than just failing.
"""
import os
import sqlite3
import sys

from werkzeug.security import check_password_hash

CHECKS = []
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"   # what a check returns first; WARN is reported, never a failure


def check(name):
    def register(fn):
        CHECKS.append((name, fn))
        return fn
    return register


@check("SECRET_KEY is set and not the dev default")
def _secret():
    key = os.environ.get("SECRET_KEY", "")
    if not key:
        return FAIL, "unset — generate: python3 -c 'import secrets; print(secrets.token_hex(32))'"
    if key == "dev-secret-change-me":
        return FAIL, "still the development key; anyone can forge a session cookie"
    if len(key) < 32:
        return FAIL, f"only {len(key)} chars; use at least 32"
    return PASS, "ok"


@check("Session cookie marked Secure (PMS_HTTPS=1)")
def _https():
    if os.environ.get("PMS_HTTPS") != "1":
        return FAIL, "unset — the session cookie will be sent over plain HTTP too"
    return PASS, "ok"


@check("Proxy headers trusted (PMS_TRUST_PROXY=1)")
def _proxy():
    if os.environ.get("PMS_TRUST_PROXY") != "1":
        return FAIL, ("unset — behind nginx every request looks like 127.0.0.1, which "
                       "collapses the login rate limiter into one shared bucket")
    return PASS, "ok"


@check("Default admin password changed")
def _admin_password():
    from db import DB_PATH
    if not os.path.exists(DB_PATH):
        return PASS, "no database yet — will be seeded on first boot (change it immediately)"
    db = sqlite3.connect(DB_PATH)
    rows = db.execute("SELECT username, password_hash FROM users WHERE active = 1").fetchall()
    db.close()
    weak = [u for u, h in rows if check_password_hash(h, "changeme")]
    if weak:
        return FAIL, f"still 'changeme': {', '.join(weak)}"
    return PASS, f"{len(rows)} active user(s), none using the seed password"


@check("Data directory is writable and outside the image")
def _data_dir():
    from db import DATA_DIR
    if not os.access(DATA_DIR, os.W_OK):
        return FAIL, f"{DATA_DIR} is not writable"
    if os.environ.get("ODIN_DATA_DIR"):
        return PASS, f"{DATA_DIR} (mounted)"
    return PASS, f"{DATA_DIR} (source dir — fine for a VM, set ODIN_DATA_DIR in containers)"


@check("Database opens and passes SQLite's quick check")
def _database():
    from db import DB_PATH
    if not os.path.exists(DB_PATH):
        return PASS, "no database yet — created on first boot"
    try:
        db = sqlite3.connect(DB_PATH)
        result = db.execute("PRAGMA quick_check").fetchone()[0]
        db.close()
    except sqlite3.Error as exc:
        return FAIL, f"cannot read {DB_PATH}: {exc} — restore the last good backup"
    return (PASS, "ok") if result == "ok" else (FAIL, f"damaged: {result} — restore the last good backup")


@check("Database schema matches this code")
def _schema():
    # A newer database than the code is a rollback (deploy/odin-update.sh going
    # back after a failed update). It warns rather than fails: the rollback must
    # pass preflight to boot, and the older code skips destructive boot steps.
    from db import DB_PATH, SCHEMA_VERSION, schema_version
    if not os.path.exists(DB_PATH):
        return PASS, "no database yet"
    db = sqlite3.connect(DB_PATH)
    found = schema_version(db)
    db.close()
    if found > SCHEMA_VERSION:
        return WARN, (f"database v{found} is newer than this code (v{SCHEMA_VERSION}): a rollback; "
                      "it runs, but restore the pre-update backup if the newer release's data must go")
    if found < SCHEMA_VERSION:
        return PASS, f"database v{found}, migrated to v{SCHEMA_VERSION} on the next boot"
    return PASS, f"v{found}"


@check("Debug mode off")
def _debug():
    if os.environ.get("FLASK_DEBUG") or os.environ.get("FLASK_ENV") == "development":
        return FAIL, "FLASK_DEBUG/FLASK_ENV indicates development mode"
    return PASS, "ok"


@check("Microsoft 365 redirect URI note")
def _oauth():
    from db import DB_PATH
    if not os.path.exists(DB_PATH):
        return PASS, "no database yet"
    db = sqlite3.connect(DB_PATH)
    row = db.execute("SELECT value FROM settings WHERE key = 'ms_client_id'").fetchone()
    db.close()
    if not (row and row[0]) and not os.environ.get("MS_CLIENT_ID"):
        return PASS, "M365 not configured — skipping"
    return PASS, ("configured — confirm the Azure app's redirect URI matches this host "
                  "exactly (scheme/host/port/path) or sign-in fails with AADSTS50011")


@check("Public web address is set (Settings › General)")
def _public_url():
    from db import DB_PATH
    if not os.path.exists(DB_PATH):
        return PASS, "no database yet — set it after the first sign-in"
    db = sqlite3.connect(DB_PATH)
    row = db.execute("SELECT value FROM settings WHERE key = 'policy.public_url'").fetchone()
    db.close()
    if not (row and row[0]):
        return FAIL, "unset — sign-in, reset and invitation links would be built from the request's host; set https://your-host in Settings › General"
    return PASS, row[0]


def main():
    print("Odin pre-flight\n" + "-" * 60)
    failures = warnings = 0
    for name, fn in CHECKS:
        try:
            status, detail = fn()
        except Exception as exc:  # a broken check shouldn't mask the others
            status, detail = FAIL, f"check errored: {exc}"
        print(f"[{status}] {name}\n       {detail}")
        failures += status == FAIL
        warnings += status == WARN
    print("-" * 60)
    if failures:
        print(f"{failures} issue(s) must be fixed before serving.")
    else:
        print("Ready to serve." + (f" {warnings} warning(s) above." if warnings else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
