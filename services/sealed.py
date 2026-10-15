"""Secrets at rest (system map #6): the Microsoft 365 tokens and the client
secrets that admins paste into Settings are stored sealed (Fernet) with a key
derived from SECRET_KEY, which lives in the server's .env and never in the
database or a backup. A leaked database or backup therefore leaks no working
credential.

A value written before sealing existed reads back as it is and is sealed the
next time it is saved. Rotating SECRET_KEY (review A11): put the old key in
SECRET_KEY_FALLBACKS (comma-separated) beside the new one; values still open
with it, and the next boot seals them again with the new key (reseal), after
which the old key can go.
"""
import base64
import hashlib
import os

PREFIX = "sealed:"


def _secrets():
    """SECRET_KEY, then the old keys of a rotation (SECRET_KEY_FALLBACKS, as
    Flask uses them for sessions), then LEGACY_SECRET_KEY when core set one:
    values sealed on dev/UAT before the key moved to DATA_DIR/secret_key (15
    Oct 2026). The legacy fallback (here and in core.py) can be deleted once
    UAT has booted once with reseal."""
    try:
        from flask import current_app
        config = current_app.config
    except RuntimeError:   # a script or the scheduler outside an app context: the same app's key
        try:
            from core import app
            config = app.config
        except Exception:  # noqa: BLE001
            config = {"SECRET_KEY": os.environ.get("SECRET_KEY", ""),
                      "SECRET_KEY_FALLBACKS": [k.strip() for k in os.environ.get("SECRET_KEY_FALLBACKS", "").split(",") if k.strip()]}
    legacy = config.get("LEGACY_SECRET_KEY")
    return [config["SECRET_KEY"], *(config.get("SECRET_KEY_FALLBACKS") or [])] + ([legacy] if legacy else [])


def fernet(salt, secret=None):
    """The Fernet for one purpose (`salt`), keyed from SECRET_KEY unless `secret` is given."""
    from cryptography.fernet import Fernet
    secret = _secrets()[0] if secret is None else secret
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(salt + str(secret).encode()).digest()))


def _open(salt, token):
    """(plain, index of the key that opened it), or (None, None)."""
    from cryptography.fernet import InvalidToken
    for i, secret in enumerate(_secrets()):
        try:
            return fernet(salt, secret).decrypt(token).decode(), i
        except (InvalidToken, ValueError):
            pass
    return None, None


def decrypt(salt, token):
    """`token` opened with the current key, else an old one; None when none opens it."""
    return _open(salt, token)[0]


def seal(value):
    if not value or str(value).startswith(PREFIX):   # empty, or sealed already (a kept secret passed back)
        return value
    return PREFIX + fernet(b"odin-secrets:").encrypt(str(value).encode()).decode()


def unseal(value):
    """The plain value; None when it cannot be opened (SECRET_KEY changed)."""
    if not value or not str(value).startswith(PREFIX):
        return value
    return decrypt(b"odin-secrets:", str(value)[len(PREFIX):].encode())


def reseal(db):
    """At boot: every value an old key opens is sealed again with the current
    one (settings, the Microsoft 365 tokens, two-step secrets). `db` is the
    raw boot connection. Returns how many moved."""
    if len(_secrets()) < 2:
        return 0
    moved = 0
    jobs = [("settings", "key", "value", b"odin-secrets:", True),
            ("ms_connection", "id", "access_token", b"odin-secrets:", True), ("ms_connection", "id", "refresh_token", b"odin-secrets:", True),
            ("users", "id", "totp_secret", b"odin-totp:", False), ("users", "id", "totp_pending", b"odin-totp:", False)]
    for table, key, column, salt, prefixed in jobs:   # fixed names, never input
        for row_key, value in db.execute(f"SELECT {key}, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall():
            if prefixed and not str(value).startswith(PREFIX):
                continue
            plain, used = _open(salt, (value[len(PREFIX):] if prefixed else value).encode())
            if used:   # opened, and not by the current key
                fresh = fernet(salt).encrypt(plain.encode()).decode()
                db.execute(f"UPDATE {table} SET {column} = ? WHERE {key} = ?", ((PREFIX if prefixed else "") + fresh, row_key))
                moved += 1
    db.commit()
    return moved
