"""Two-step sign-in for password accounts: a 6-digit code from an
authenticator app (TOTP, RFC 6238: SHA-1, 30 s, 6 digits), or one of ten
single-use recovery codes.

Password sign-in is the only door that needs it: Microsoft sign-in brings
Microsoft's own two-step check, and partners' email links are single-use
and go to the address on record. An admin can require it for admins or for
everyone (policy mfa_required); someone who must but has not set it up is
signed in straight to the Account page until they do.

The secret is stored encrypted with a key derived from SECRET_KEY, so a
leaked database or backup does not leak it; rotating SECRET_KEY therefore
means everyone sets two-step sign-in up again (an admin resets it on the
Users page). A code is accepted once: the last used time step is kept.
Recovery codes are random, 80 bits, stored as salted SHA-256 (review P3-5);
codes made before that (40 bits, unsalted) keep working until new ones are made.
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import datetime
from urllib.parse import quote

from db import get_db
from policies import policy
from services.sealed import decrypt, fernet

STEP = 30
DIGITS = 6
RECOVERY_CODES = 10
PENDING_MINUTES = 5       # between the right password and the code
PENDING_TRIES = 5


def seal(secret):
    return fernet(b"odin-totp:").encrypt(secret.encode()).decode()


def unseal(sealed):
    return decrypt(b"odin-totp:", (sealed or "").encode())


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode()


def code_at(secret, step):
    digest = hmac.new(base64.b32decode(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    return str((struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS).zfill(DIGITS)


def matching_step(secret, code, after=0, now=None):
    """The time step (±1 for clock drift) this code belongs to, if later than `after`."""
    code = "".join(ch for ch in str(code or "") if ch in "0123456789")   # ASCII only: compare_digest raises on any other
    if len(code) != DIGITS or not secret:
        return None
    step = int((now or time.time()) // STEP)
    for s in (step - 1, step, step + 1):
        if s > after and hmac.compare_digest(code_at(secret, s), code):
            return s
    return None


def uri(secret, username):
    issuer = policy("company_name") or "Odin"
    label = quote(f"Odin ({issuer}):{username}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote('Odin ' + issuer)}&digits={DIGITS}&period={STEP}"


def qr_svg(text):
    """Inline SVG. Black on white whatever the theme: scanners need it."""
    import segno
    return segno.make(text, error="m").svg_inline(scale=4, border=2, dark="#000", light="#fff")


def _hash(code, salt=""):
    return hashlib.sha256((salt + "".join(code.split()).replace("-", "").lower()).encode()).hexdigest()


def _salted(code):
    salt = secrets.token_hex(8)
    return f"v2:{salt}:{_hash(code, salt)}"


def _matches(stored, code):
    """A stored recovery code against a typed one: v2:<salt>:<hash>, or an older bare hash."""
    if stored.startswith("v2:"):
        _, salt, digest = stored.split(":")
        return hmac.compare_digest(digest, _hash(code, salt))
    return hmac.compare_digest(stored, _hash(code))


def new_recovery_codes():
    """Ten codes of 80 bits as xxxx-xxxx-xxxx-xxxx (base32: no 0/1/8/9 to misread)."""
    raw = [base64.b32encode(secrets.token_bytes(10)).decode().lower() for _ in range(RECOVERY_CODES)]
    codes = ["-".join(r[i:i + 4] for i in range(0, 16, 4)) for r in raw]
    return codes, json.dumps([_salted(c) for c in codes])


def enabled(user):
    return bool(user["totp_enabled_at"])


def required(user):
    rule = policy("mfa_required")
    return user["kind"] == "internal" and (rule == "everyone" or (rule == "admins" and user["role"] == "Admin"))


def recovery_left(user):
    return len(json.loads(user["recovery_codes"] or "[]"))


def check(user, code):
    """'code' or 'recovery' when the code is good (and burns it), else None."""
    db = get_db()
    step = matching_step(unseal(user["totp_secret"]), code, user["totp_last_step"] or 0)
    if step is not None:
        # guarded update: two requests racing with the same code cannot both win
        n = db.execute("UPDATE users SET totp_last_step = ? WHERE id = ? AND COALESCE(totp_last_step, 0) < ?", (step, user["id"], step)).rowcount
        db.commit()
        return "code" if n else None
    hashes = json.loads(user["recovery_codes"] or "[]")
    hit = next((h for h in hashes if _matches(h, str(code or ""))), None)
    if hit:
        hashes.remove(hit)
        n = db.execute("UPDATE users SET recovery_codes = ? WHERE id = ? AND recovery_codes = ?", (json.dumps(hashes), user["id"], user["recovery_codes"])).rowcount
        db.commit()
        return "recovery" if n else None
    return None


def start_setup(user_id):
    """A fresh secret waiting for its first code; returns what the app shows."""
    db = get_db()
    secret = new_secret()
    db.execute("UPDATE users SET totp_pending = ? WHERE id = ?", (seal(secret), user_id))
    db.commit()
    username = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()["username"]
    link = uri(secret, username)
    return {"secret": secret, "uri": link, "qr_svg": qr_svg(link)}


def confirm_setup(user_id, code):
    """Turn it on once a code from the new secret checks out; returns the recovery codes, or None."""
    db = get_db()
    row = db.execute("SELECT totp_pending FROM users WHERE id = ?", (user_id,)).fetchone()
    secret = unseal(row["totp_pending"]) if row else None
    step = matching_step(secret, code)
    if step is None:
        return None
    codes, hashes = new_recovery_codes()
    db.execute("UPDATE users SET totp_secret = ?, totp_pending = NULL, totp_enabled_at = ?, totp_last_step = ?, recovery_codes = ? WHERE id = ?",
               (seal(secret), datetime.utcnow().isoformat(), step, hashes, user_id))
    db.commit()
    return codes


def regenerate_codes(user_id):
    codes, hashes = new_recovery_codes()
    get_db().execute("UPDATE users SET recovery_codes = ? WHERE id = ?", (hashes, user_id))
    get_db().commit()
    return codes


def turn_off(user_id):
    get_db().execute("UPDATE users SET totp_secret = NULL, totp_pending = NULL, totp_enabled_at = NULL, totp_last_step = 0, recovery_codes = NULL WHERE id = ?", (user_id,))
    get_db().commit()


if __name__ == "__main__":
    # RFC 6238 appendix B, SHA-1 seed "12345678901234567890" at T = 59 s: 94287082 (8 digits) → 287082
    rfc = base64.b32encode(b"12345678901234567890").decode()
    assert code_at(rfc, 59 // STEP) == "287082"
    assert matching_step(rfc, "287082", now=59) == 1
    assert matching_step(rfc, "287082", after=1, now=59) is None      # already used
    assert matching_step(rfc, "287 082", now=59 + STEP) == 1           # a step of drift, spaces ignored
    assert matching_step(rfc, "287082", now=59 + 3 * STEP) is None
    codes, stored = new_recovery_codes()
    assert len(codes[0]) == 19 and _matches(json.loads(stored)[0], codes[0].upper().replace("-", " "))
    assert _matches(_hash("abcd-ef0123"), "ABCD-EF0123") and not _matches(json.loads(stored)[1], codes[0])   # old codes still work
    print("ok")
