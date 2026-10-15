"""Secrets at rest (system map #6): the Microsoft 365 tokens and the client
secrets that admins paste into Settings are stored sealed (Fernet) with a key
derived from SECRET_KEY, which lives in the server's .env and never in the
database or a backup. A leaked database or backup therefore leaks no working
credential.

A value written before sealing existed reads back as it is and is sealed the
next time it is saved. Rotating SECRET_KEY makes sealed values unreadable:
reconnect Microsoft 365 and paste the client secrets again.
"""
import base64
import hashlib
import os

PREFIX = "sealed:"


def _secrets():
    """SECRET_KEY, then LEGACY_SECRET_KEY when core set one: values sealed on
    dev/UAT before the key moved to DATA_DIR/secret_key (15 Oct 2026). The
    legacy fallback (here and in core.py) can be deleted once UAT's secrets
    and two-step sign-ins are saved again."""
    try:
        from flask import current_app
        config = current_app.config
    except RuntimeError:   # a script or the scheduler outside an app context: the same app's key
        try:
            from core import app
            config = app.config
        except Exception:  # noqa: BLE001
            config = {"SECRET_KEY": os.environ.get("SECRET_KEY", "")}
    legacy = config.get("LEGACY_SECRET_KEY")
    return [config["SECRET_KEY"]] + ([legacy] if legacy else [])


def fernet(salt, secret=None):
    """The Fernet for one purpose (`salt`), keyed from SECRET_KEY unless `secret` is given."""
    from cryptography.fernet import Fernet
    secret = _secrets()[0] if secret is None else secret
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(salt + str(secret).encode()).digest()))


def decrypt(salt, token):
    """`token` opened with the current key, else the legacy one; None when neither opens it."""
    from cryptography.fernet import InvalidToken
    for secret in _secrets():
        try:
            return fernet(salt, secret).decrypt(token).decode()
        except (InvalidToken, ValueError):
            pass
    return None


def seal(value):
    if not value or str(value).startswith(PREFIX):   # empty, or sealed already (a kept secret passed back)
        return value
    return PREFIX + fernet(b"odin-secrets:").encrypt(str(value).encode()).decode()


def unseal(value):
    """The plain value; None when it cannot be opened (SECRET_KEY changed)."""
    if not value or not str(value).startswith(PREFIX):
        return value
    return decrypt(b"odin-secrets:", str(value)[len(PREFIX):].encode())
