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


def _box():
    from cryptography.fernet import Fernet
    try:
        from flask import current_app
        secret = current_app.config["SECRET_KEY"]
    except RuntimeError:   # a script or the scheduler outside an app context: the same app's key
        try:
            from core import app
            secret = app.config["SECRET_KEY"]
        except Exception:  # noqa: BLE001
            secret = os.environ.get("SECRET_KEY", "")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"odin-secrets:" + str(secret).encode()).digest()))


def seal(value):
    if not value or str(value).startswith(PREFIX):   # empty, or sealed already (a kept secret passed back)
        return value
    return PREFIX + _box().encrypt(str(value).encode()).decode()


def unseal(value):
    """The plain value; None when it cannot be opened (SECRET_KEY changed)."""
    if not value or not str(value).startswith(PREFIX):
        return value
    from cryptography.fernet import InvalidToken
    try:
        return _box().decrypt(str(value)[len(PREFIX):].encode()).decode()
    except (InvalidToken, ValueError):
        return None
