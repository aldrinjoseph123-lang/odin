"""Production WSGI entrypoint.

Serve behind a real WSGI server — never the Flask dev server — e.g.:

    gunicorn --preload --workers 2 --threads 4 --bind 127.0.0.1:5050 wsgi:app

`gunicorn wsgi:app` imports this module (which imports app.py, registering every
route) but never executes app.py's `if __name__ == "__main__"` block, so the
database is initialised here instead. Run with `--preload` so this import — and
therefore init_db() — happens once in the master process before workers fork,
which both avoids a first-boot race on the admin-user seed and saves memory.

init_db() is idempotent (CREATE TABLE IF NOT EXISTS + ALTER-based migration),
so restarts and redeploys are safe.
"""
from app import app  # noqa: F401 — importing app registers all routes on it
from db import init_db

# Fail fast rather than serving traffic with a publicly-known signing key:
# anyone who knows it can forge a session cookie and log in as any user.
if app.config.get("USING_DEV_SECRET"):
    raise RuntimeError(
        "SECRET_KEY is unset, so the app fell back to its development signing key. "
        "Generate one with:  python3 -c 'import secrets; print(secrets.token_hex(32))'  "
        "and set it in the environment (see DEPLOY.md) before starting gunicorn."
    )

init_db()
