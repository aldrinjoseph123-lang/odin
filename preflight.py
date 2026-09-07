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


def check(name):
    def register(fn):
        CHECKS.append((name, fn))
        return fn
    return register


@check("SECRET_KEY is set and not the dev default")
def _secret():
    key = os.environ.get("SECRET_KEY", "")
    if not key:
        return False, "unset — generate: python3 -c 'import secrets; print(secrets.token_hex(32))'"
    if key == "dev-secret-change-me":
        return False, "still the development key; anyone can forge a session cookie"
    if len(key) < 32:
        return False, f"only {len(key)} chars; use at least 32"
    return True, "ok"


@check("Session cookie marked Secure (PMS_HTTPS=1)")
def _https():
    if os.environ.get("PMS_HTTPS") != "1":
        return False, "unset — the session cookie will be sent over plain HTTP too"
    return True, "ok"


@check("Proxy headers trusted (PMS_TRUST_PROXY=1)")
def _proxy():
    if os.environ.get("PMS_TRUST_PROXY") != "1":
        return False, ("unset — behind nginx every request looks like 127.0.0.1, which "
                       "collapses the login rate limiter into one shared bucket")
    return True, "ok"


@check("Default admin password changed")
def _admin_password():
    from db import DB_PATH
    if not os.path.exists(DB_PATH):
        return True, "no database yet — will be seeded on first boot (change it immediately)"
    db = sqlite3.connect(DB_PATH)
    rows = db.execute("SELECT username, password_hash FROM users WHERE active = 1").fetchall()
    db.close()
    weak = [u for u, h in rows if check_password_hash(h, "changeme")]
    if weak:
        return False, f"still 'changeme': {', '.join(weak)}"
    return True, f"{len(rows)} active user(s), none using the seed password"


@check("Data directory is writable and outside the image")
def _data_dir():
    from db import DATA_DIR
    if not os.access(DATA_DIR, os.W_OK):
        return False, f"{DATA_DIR} is not writable"
    if os.environ.get("ODIN_DATA_DIR"):
        return True, f"{DATA_DIR} (mounted)"
    return True, f"{DATA_DIR} (source dir — fine for a VM, set ODIN_DATA_DIR in containers)"


@check("Debug mode off")
def _debug():
    if os.environ.get("FLASK_DEBUG") or os.environ.get("FLASK_ENV") == "development":
        return False, "FLASK_DEBUG/FLASK_ENV indicates development mode"
    return True, "ok"


@check("Microsoft 365 redirect URI note")
def _oauth():
    from db import DB_PATH
    if not os.path.exists(DB_PATH):
        return True, "no database yet"
    db = sqlite3.connect(DB_PATH)
    row = db.execute("SELECT value FROM settings WHERE key = 'ms_client_id'").fetchone()
    db.close()
    if not (row and row[0]) and not os.environ.get("MS_CLIENT_ID"):
        return True, "M365 not configured — skipping"
    return True, ("configured — confirm the Azure app's redirect URI matches this host "
                  "exactly (scheme/host/port/path) or sign-in fails with AADSTS50011")


def main():
    print("Odin pre-flight\n" + "-" * 60)
    failures = 0
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:  # a broken check shouldn't mask the others
            ok, detail = False, f"check errored: {exc}"
        print(f"[{'PASS' if ok else 'FAIL'}] {name}\n       {detail}")
        failures += 0 if ok else 1
    print("-" * 60)
    print("Ready to serve." if not failures else f"{failures} issue(s) must be fixed before serving.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
