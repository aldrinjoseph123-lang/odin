"""Resend (https://api.resend.com) for Odin's sign-in mail (16 Oct 2026, the user's
call): sign-in links, password resets, address confirmations and invitations go
out through Resend; notifications, the digest and reports stay on Microsoft 365.

The free plan allows 100 emails a day (reset at midnight UTC) and 10 requests a
second; sign-in mail is a few a day. A refusal over the limit is a 429 with
`daily_quota_exceeded`. When Resend is off or refuses, Odin falls back to
Microsoft 365 if that is connected. The key is a sealed policy, never in git."""
import json
import urllib.error
import urllib.request
import uuid

API = "https://api.resend.com/emails"


def configured(db=None):
    from policies import policy
    return bool(policy("resend_enabled", db)) and bool(policy("resend_api_key", db))


def _post(payload, key):
    """One request; Odin never retries a send, so the idempotency key only guards
    a network-level resend of this one request."""
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4()),
        "User-Agent": "Odin",
    })
    with urllib.request.urlopen(req, timeout=10) as r:   # noqa: S310 — a fixed https address
        return json.loads(r.read() or b"{}")


def send(to, subject, html_body):
    """Send one email through Resend: (ok, error). Never raises."""
    import graph
    from policies import policy
    try:
        payload = {"from": policy("resend_from"), "to": [to], "subject": subject, "html": graph.email_html(html_body)}
        reply = next(iter(policy("resend_reply_to")), None)
        if reply:
            payload["reply_to"] = [reply]
        _post(payload, policy("resend_api_key"))
        return True, None
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read() or b"{}")
        except ValueError:
            body = {}
        if exc.code == 429 and "quota" in str(body.get("name", "")):
            return False, "Resend's daily limit is used up (100 a day on the free plan); it resets at midnight UTC"
        return False, f"Resend refused the email ({exc.code}): {str(body.get('message') or exc.reason)[:200]}"
    except Exception as exc:  # noqa: BLE001 — network, DNS, a bad key: the caller decides
        return False, f"Resend could not be reached: {str(exc)[:200]}"


def send_account_mail(to, subject, html_body):
    """Sign-in mail: Resend first when it is on, else (or if it refuses)
    Microsoft 365 when connected. A Resend failure is told to the admins once a day."""
    import graph
    if configured():
        ok, error = send(to, subject, html_body)
        if ok:
            return True, None
        _tell_admins(error)
        if not graph.is_connected():
            return False, error
    return graph.send_mail(to, subject, html_body)


def _tell_admins(error):
    from datetime import datetime, timedelta
    from markupsafe import escape
    from db import get_db, get_setting, set_setting
    from services.notifications import notify_users
    last, now = get_setting("resend_failure_reported_at"), datetime.utcnow()
    if last and datetime.fromisoformat(last) > now - timedelta(hours=24):
        return
    set_setting("resend_failure_reported_at", now.isoformat())
    admins = [r[0] for r in get_db().execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
    notify_users(admins, "ops", None, "Odin could not send a sign-in email through Resend",
                 f"{escape(error)}. Check the key and the sending domain in Resend, and Settings › Notifications › Sign-in mail.",
                 link="/settings/notifications", email=False, teams=False)
