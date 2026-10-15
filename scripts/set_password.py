"""Set a user's password from the server shell — for the first boot, before
the hostname is public, so the first admin's printed password is never usable from outside.

    docker compose exec app python scripts/set_password.py            # admin
    docker compose exec app python scripts/set_password.py priya      # anyone

Prompts twice (nothing echoed, nothing in shell history), applies the same
password policy as the Account page, signs the user out everywhere, clears
"must change password", and writes an audit row naming the server shell.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash  # noqa: E402

from app import app  # noqa: E402
from db import get_db  # noqa: E402
from security import password_problem  # noqa: E402
from services.audit import audit_log  # noqa: E402


def main(username):
    with app.test_request_context(environ_base={"REMOTE_ADDR": "server-shell"}):
        db = get_db()
        user = db.execute("SELECT id, name, kind FROM users WHERE username = ?", (username,)).fetchone()
        if user is None:
            sys.exit(f"No user '{username}'.")
        if user["kind"] == "external":
            sys.exit(f"'{username}' is a partner/customer account; they sign in by email link, not password.")
        first = getpass.getpass(f"New password for {username}: ")
        if problem := password_problem(first):
            sys.exit(problem)
        if getpass.getpass("Again: ") != first:
            sys.exit("The two entries differ; nothing changed.")
        db.execute("UPDATE users SET password_hash = ?, must_change_password = 0, session_epoch = session_epoch + 1, active = 1 WHERE id = ?",
                   (generate_password_hash(first, method="pbkdf2:sha256"), user["id"]))
        db.commit()
        audit_log("set_password_shell", "user", user["id"], user["name"], "password set from the server shell; signed out everywhere", actor="server-shell")
    print(f"Password set for {username}. Existing sessions are signed out.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "admin")
