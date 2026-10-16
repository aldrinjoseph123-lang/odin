"""Microsoft Graph integration: Outlook mail, Teams channel messages, OneDrive storage.

One admin clicks "Connect Microsoft 365" in Settings, signs in on Microsoft's
own login page, and consents. We store the resulting refresh token and act as
that person via delegated Graph calls (/me/...) from then on — including from
the cron'd backup.py / send_daily_alerts.py scripts, since a valid refresh
token works outside an interactive browser session too.

The Azure AD app registration itself (client ID/secret/tenant) still has to
exist first — that part can't be click-through, Azure requires a pre-registered
app before any OAuth flow can start. See AZURE_SETUP.md.

Every public function is best-effort: none of them raise. Send/upload
functions return (ok: bool, error: str | None) so callers can flash a warning
and continue — a Graph outage must never break a project update.
"""
import base64
import os
import sqlite3
import time
from urllib.parse import quote, urlencode

import requests
from markupsafe import escape

# Same data location as db.DATA_DIR — graph.py is imported by the cron scripts
# outside a Flask context, so it resolves the path itself rather than importing db.
DB_PATH = os.path.join(os.environ.get("ODIN_DATA_DIR") or os.path.dirname(__file__), "odin.db")
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTH_BASE = "https://login.microsoftonline.com"
# Sites.ReadWrite.All: backups into a SharePoint site the connected admin can reach (Settings → Backups).
# User.ReadBasic.All: finds a colleague by email for the Odin PMS Teams app (services/teams_bot.py).
SCOPES = ("offline_access User.Read Mail.Send Files.ReadWrite Sites.ReadWrite.All ChannelMessage.Send Team.ReadBasic.All Channel.ReadBasic.All "
          "User.ReadBasic.All")


def _env(key):
    return os.environ.get(key, "").strip()


def _db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def _db_setting(key):
    if not os.path.exists(DB_PATH):
        return ""
    db = _db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    db.close()
    return row["value"] if row else ""


# Azure app credentials can come from env vars (ops-managed deployment) or be
# pasted into Settings by an admin (DB-stored) — DB wins if both are set, since
# it's the one an admin can change without touching the server's environment.
def _client_id():
    return _db_setting("ms_client_id") or _env("MS_CLIENT_ID")


def _client_secret():
    from services.sealed import unseal
    return unseal(_db_setting("ms_client_secret")) or _env("MS_CLIENT_SECRET")


def _tenant():
    return _db_setting("ms_tenant_id") or _env("MS_TENANT_ID") or "common"


def oauth_client_configured():
    """Whether the Azure AD app registration's own credentials are set —
    required before the Connect button will work at all."""
    return bool(_client_id() and _client_secret())


def azure_app_credentials():
    """Current values for display in Settings — never returns the secret
    itself, just whether one is set and where these came from."""
    db_client_id = _db_setting("ms_client_id")
    db_secret = _db_setting("ms_client_secret")
    db_tenant = _db_setting("ms_tenant_id")
    return {
        "client_id": db_client_id or _env("MS_CLIENT_ID"),
        "tenant_id": db_tenant or _env("MS_TENANT_ID"),
        "has_secret": bool(db_secret or _env("MS_CLIENT_SECRET")),
        "source": "database" if (db_client_id or db_secret or db_tenant) else ("env" if oauth_client_configured() else None),
    }


def set_azure_app_credentials(client_id, client_secret, tenant_id):
    from services.sealed import seal
    db = _db()
    for key, value in [
        ("ms_client_id", client_id.strip()),
        ("ms_client_secret", seal(client_secret.strip())),   # sealed at rest (services/sealed.py)
        ("ms_tenant_id", tenant_id.strip()),
    ]:
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    db.commit()
    db.close()


def clear_azure_app_credentials():
    db = _db()
    db.execute("DELETE FROM settings WHERE key IN ('ms_client_id', 'ms_client_secret', 'ms_tenant_id')")
    db.commit()
    db.close()


def get_connection():
    if not os.path.exists(DB_PATH):
        return None
    db = _db()
    row = db.execute("SELECT * FROM ms_connection WHERE id = 1").fetchone()
    db.close()
    if row is None:
        return None
    from services.sealed import unseal   # the tokens are stored sealed
    return {**dict(row), "access_token": unseal(row["access_token"]), "refresh_token": unseal(row["refresh_token"])}


def is_connected():
    conn = get_connection()
    return bool(conn and conn["refresh_token"])


def teams_configured():
    conn = get_connection()
    return bool(conn and conn["refresh_token"] and conn["team_id"] and conn["channel_id"])


def build_authorize_url(redirect_uri, state):
    params = {
        "client_id": _client_id(),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": SCOPES,
        "state": state,
        "prompt": "consent",
    }
    return f"{AUTH_BASE}/{_tenant()}/oauth2/v2.0/authorize?{urlencode(params)}"


def _save_tokens(token_response):
    from services.sealed import seal
    now = int(time.time())
    db = _db()
    db.execute(
        """INSERT INTO ms_connection (id, access_token, refresh_token, expires_at, connected_at)
           VALUES (1, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%S', 'now'))   -- ISO 8601 with a T, like every other stored time
           ON CONFLICT(id) DO UPDATE SET
             access_token = excluded.access_token,
             -- COALESCE, not a plain assignment: a refresh response is allowed
             -- to omit a rotated refresh_token, and overwriting the stored one
             -- with NULL silently disconnects Microsoft 365 for good.
             refresh_token = COALESCE(excluded.refresh_token, ms_connection.refresh_token),
             expires_at = excluded.expires_at""",
        (
            seal(token_response["access_token"]),
            seal(token_response.get("refresh_token")),
            now + int(token_response.get("expires_in", 3600)),
        ),
    )
    db.commit()
    db.close()


def complete_connection(code, redirect_uri):
    """Exchange the authorization code for tokens, record who connected."""
    try:
        resp = requests.post(
            f"{AUTH_BASE}/{_tenant()}/oauth2/v2.0/token",
            data={
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": SCOPES,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_response = resp.json()
        _save_tokens(token_response)

        me = requests.get(
            f"{GRAPH_BASE}/me?$select=mail,userPrincipalName",
            headers={"Authorization": f"Bearer {token_response['access_token']}"},
            timeout=15,
        )
        me.raise_for_status()
        email = me.json().get("mail") or me.json().get("userPrincipalName")
        db = _db()
        db.execute("UPDATE ms_connection SET connected_email = ? WHERE id = 1", (email,))
        db.commit()
        db.close()
        return True, email
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _set_db_setting(key, value):
    db = _db()
    if value:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    else:
        db.execute("DELETE FROM settings WHERE key = ?", (key,))
    db.commit()
    db.close()


def disconnect():
    db = _db()
    db.execute("DELETE FROM ms_connection WHERE id = 1")
    db.commit()
    db.close()


def set_channel(team_id, team_name, channel_id, channel_name):
    db = _db()
    db.execute(
        "UPDATE ms_connection SET team_id=?, team_name=?, channel_id=?, channel_name=? WHERE id = 1",
        (team_id, team_name, channel_id, channel_name),
    )
    db.commit()
    db.close()


def _get_access_token():
    conn = get_connection()
    if not conn or not conn["refresh_token"]:
        return None, "Not connected to Microsoft 365"

    now = time.time()
    if conn["access_token"] and now < (conn["expires_at"] or 0) - 60:
        return conn["access_token"], None

    try:
        resp = requests.post(
            f"{AUTH_BASE}/{_tenant()}/oauth2/v2.0/token",
            data={
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "refresh_token": conn["refresh_token"],
                "grant_type": "refresh_token",
                "scope": SCOPES,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_response = resp.json()
        _save_tokens(token_response)
        return token_response["access_token"], None
    except Exception as exc:  # noqa: BLE001
        return None, f"Token refresh failed — reconnect Microsoft 365 in Settings ({exc})"


def _headers():
    token, error = _get_access_token()
    if error:
        return None, error
    return {"Authorization": f"Bearer {token}"}, None


def list_joined_teams():
    headers, error = _headers()
    if error:
        return [], error
    try:
        resp = requests.get(f"{GRAPH_BASE}/me/joinedTeams", headers=headers, timeout=15)
        resp.raise_for_status()
        return [{"id": t["id"], "name": t["displayName"]} for t in resp.json().get("value", [])], None
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)


def list_channels(team_id):
    headers, error = _headers()
    if error:
        return [], error
    try:
        resp = requests.get(f"{GRAPH_BASE}/teams/{team_id}/channels", headers=headers, timeout=15)
        resp.raise_for_status()
        return [{"id": c["id"], "name": c["displayName"]} for c in resp.json().get("value", [])], None
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)


# Every Odin email wears the brand: the parent's black band, the struck-through
# O in red, the tagline underneath. Text, not an image, so it survives mail
# clients that block pictures. Inline styles only; mail clients drop <style>.
EMAIL_SHELL = (
    '<div style="background:#F3F4F6;padding:24px 12px;font-family:Inter,\'Segoe UI\',Arial,sans-serif;color:#101114">'
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;border-collapse:collapse">'
    '<tr><td style="background:#0A0A0A;padding:16px 24px">'
    '<span style="font:700 18px/1 \'Chakra Petch\',Arial,sans-serif;letter-spacing:.12em;color:#FFFFFF"><span style="color:#E11D2E">&Oslash;</span>DIN</span>'
    '<span style="font:600 10px/1 Arial,sans-serif;letter-spacing:.16em;color:#B8B8B4;margin-left:12px">BY PROTECT<span style="color:#F23D4D">24X7</span></span>'
    '</td></tr>'
    '<tr><td style="background:#FFFFFF;padding:24px;font-size:14px;line-height:1.55">{body}</td></tr>'
    '<tr><td style="padding:12px 24px;font:600 10px/1.4 Arial,sans-serif;letter-spacing:.16em;color:#4B5563">EVERY PROJECT. ON WATCH. · {company}</td></tr>'
    '</table></div>'
)


def send_mail(to_email, subject, html_body, attachments=None, report=True):
    """attachments: [(filename, bytes, content_type)] — small files only
    (Graph's sendMail takes the whole message in one ~4 MB request). A failure
    while email is switched on is reported to the admins' bell, at most daily
    (`report=False`: the outbox reports only when it gives up)."""
    ok, error = _send_mail(to_email, subject, html_body, attachments)
    if not ok and report:
        try:
            from services.notifications import report_mail_failure
            report_mail_failure(error)
        except Exception:  # noqa: BLE001 — reporting never breaks the sender
            pass
    return ok, error


def email_html(html_body):
    """The branded shell every Odin email wears (Microsoft 365 and Resend alike)."""
    try:   # the footer names the company from Settings → General; a script without the app still sends
        from policies import policy
        company = policy("company_name").upper()
    except Exception:  # noqa: BLE001
        company = "PROTECT24X7"
    return EMAIL_SHELL.format(body=html_body, company=escape(company))


def _send_mail(to_email, subject, html_body, attachments=None):
    try:
        from policies import policy
        alias = next(iter(policy("mail_from")), None)   # Settings › Notifications › Send email as
    except Exception:  # noqa: BLE001
        alias = None
    html_body = email_html(html_body)
    if not is_connected():
        return False, "Outlook mail is not connected"
    headers, error = _headers()
    if error:
        return False, error
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
            **({"attachments": [{"@odata.type": "#microsoft.graph.fileAttachment", "name": name, "contentType": ctype,
                                 "contentBytes": base64.b64encode(data).decode()} for name, data, ctype in attachments]}
               if attachments else {}),
        },
        "saveToSentItems": "true",
    }
    if alias:   # an alias of the connected mailbox, so a shared mailbox's mail says it is Odin's
        payload["message"]["from"] = {"emailAddress": {"address": alias, "name": "Odin by Protect24x7"}}
    try:
        resp = requests.post(f"{GRAPH_BASE}/me/sendMail", headers=headers, json=payload, timeout=15)
        if alias and resp.status_code >= 400 and "SendAsDenied" in resp.text:
            # the tenant refused the alias (ErrorSendAsDenied; a 429 or 503 is not that, and the
            # outbox tries it again later): deliver from the mailbox itself, and tell the admins once a day
            refused = f"{alias}: {resp.status_code} {resp.text[:200]}"
            del payload["message"]["from"]
            resp = requests.post(f"{GRAPH_BASE}/me/sendMail", headers=headers, json=payload, timeout=15)
            if resp.status_code < 400:
                try:
                    from services.notifications import report_mail_failure
                    report_mail_failure(refused, alias=True)
                except Exception:  # noqa: BLE001
                    pass
        if resp.status_code >= 400:
            return False, f"sendMail failed: {resp.status_code} {resp.text[:300]}"
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"sendMail failed: {exc}"


def md_escape(text):
    """Text for an Adaptive Card TextBlock, which reads Markdown: Odin's own
    words never use it, and outsider text (a guest note) must not plant a
    link or styling in an Odin-branded card (P3-6)."""
    import re
    text = re.sub(r"([\\`*_\[\]~])", r"\\\1", text or "")             # emphasis, code and [links](…)
    text = re.sub(r"(?m)^(\s*)([-+>])", r"\1\\\2", text)               # a list or quote at a line's start…
    return re.sub(r"(?m)^(\s*\d+)\.", r"\1\\.", text)                    # …or a numbered one


def post_teams_webhook(url, title, lines, link=None):
    """Post an Adaptive Card to a Teams Workflows webhook ("Post to a channel
    when a webhook request is received"). The old Office 365 connector
    webhooks were retired in 2026; Workflows accepts this message shape.
    Returns (ok, error); never raises."""
    body = [{"type": "TextBlock", "text": md_escape(title), "weight": "Bolder", "size": "Medium", "wrap": True}]
    body += [{"type": "TextBlock", "text": md_escape(line), "wrap": True, "spacing": "Small"} for line in lines]
    card = {"type": "AdaptiveCard", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "version": "1.4", "body": body,
            **({"actions": [{"type": "Action.OpenUrl", "title": "Open in Odin", "url": link}]} if link else {})}
    try:
        resp = requests.post(url, json={"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}, timeout=15)
        return (resp.status_code < 400), (None if resp.status_code < 400 else f"webhook answered {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        return False, f"webhook failed: {exc}"


# Microsoft refuses the lookup when the connection predates the User.ReadBasic.All scope (added 13 Oct 2026)
CONSENT_MISSING = ("Microsoft 365 refused to look people up: the connection lacks the User.ReadBasic.All permission. "
                   "Disconnect and Connect again under Settings › Integrations to grant it")


def user_id(email):
    """(Microsoft 365 object id, None) for a colleague's address — as their
    sign-in name first, then as a mail address (an alias that is not the UPN) —
    or (None, error). Through the connected account (User.ReadBasic.All)."""
    if not is_connected():
        return None, "Microsoft 365 is not connected"
    headers, error = _headers()
    if error:
        return None, error
    try:
        # quoted whole: a "/" in a staff-set address must not walk the path (/users/x/../me, P3-8)
        who = requests.get(f"{GRAPH_BASE}/users/{quote(email, safe='')}?$select=id", headers=headers, timeout=15)
        if who.status_code == 403:
            return None, CONSENT_MISSING
        uid = who.json().get("id") if who.status_code < 400 else None
        if not uid:
            found = requests.get(f"{GRAPH_BASE}/users", headers=headers, timeout=15,
                                 params={"$filter": f"mail eq '{email.replace(chr(39), chr(39) * 2)}'", "$select": "id"})
            if found.status_code == 403:
                return None, CONSENT_MISSING
            hits = found.json().get("value", []) if found.status_code < 400 else []
            uid = hits[0]["id"] if hits else None
        return (uid, None) if uid else (None, f"No one in Microsoft 365 has the address {email}")
    except Exception as exc:  # noqa: BLE001
        return None, f"Microsoft 365 lookup failed: {exc}"


def send_teams_message(text):
    if not teams_configured():
        return False, "Teams channel is not selected"
    headers, error = _headers()
    if error:
        return False, error
    conn = get_connection()
    payload = {"body": {"contentType": "html", "content": text}}
    try:
        resp = requests.post(
            f"{GRAPH_BASE}/teams/{conn['team_id']}/channels/{conn['channel_id']}/messages",
            headers=headers, json=payload, timeout=15,
        )
        if resp.status_code >= 400:
            return False, f"Teams message failed: {resp.status_code} {resp.text[:300]}"
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"Teams message failed: {exc}"


def sharepoint_drive(site_url):
    """'/sites/<id>/drive' for a site URL like https://contoso.sharepoint.com/sites/IT,
    or (None, error)."""
    from urllib.parse import urlparse
    parts = urlparse(site_url)
    headers, error = _headers()
    if error:
        return None, error
    try:
        resp = requests.get(f"{GRAPH_BASE}/sites/{parts.hostname}:{parts.path or '/'}", headers=headers, timeout=15)
        if resp.status_code >= 400:
            return None, f"SharePoint site not found or not allowed ({resp.status_code}) — reconnect Microsoft 365 if SharePoint access was added recently"
        return f"/sites/{resp.json()['id']}/drive", None
    except Exception as exc:  # noqa: BLE001
        return None, f"SharePoint lookup failed: {exc}"


def list_folder(folder, drive="/me/drive"):
    """[(name, item_id)] in a drive folder; [] if it doesn't exist yet."""
    headers, error = _headers()
    if error:
        return [], error
    try:
        resp = requests.get(f"{GRAPH_BASE}{drive}/root:/{folder}:/children?$select=name,id&$top=999", headers=headers, timeout=15)
        if resp.status_code == 404:
            return [], None
        resp.raise_for_status()
        return [(i["name"], i["id"]) for i in resp.json().get("value", [])], None
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)


def delete_item(item_id, drive="/me/drive"):
    headers, error = _headers()
    if error:
        return False, error
    try:
        resp = requests.delete(f"{GRAPH_BASE}{drive}/items/{item_id}", headers=headers, timeout=15)
        return resp.status_code < 400, None if resp.status_code < 400 else f"delete failed: {resp.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def upload_file(local_path, remote_path, drive="/me/drive"):
    """Upload local_path to a drive (the connected user's OneDrive by default,
    or a SharePoint site's from sharepoint_drive) at remote_path.

    Simple PUT for files <=4MB, chunked upload session above that — Graph
    rejects direct PUT uploads over 4MB.
    """
    if not is_connected():
        return False, "OneDrive is not connected"
    headers, error = _headers()
    if error:
        return False, error
    size = os.path.getsize(local_path)
    try:
        if size <= 4 * 1024 * 1024:
            with open(local_path, "rb") as f:
                resp = requests.put(
                    f"{GRAPH_BASE}{drive}/root:/{remote_path}:/content",
                    headers={**headers, "Content-Type": "application/octet-stream"},
                    data=f.read(),
                    timeout=60,
                )
            if resp.status_code >= 400:
                return False, f"OneDrive upload failed: {resp.status_code} {resp.text[:300]}"
            return True, None

        session_resp = requests.post(
            f"{GRAPH_BASE}{drive}/root:/{remote_path}:/createUploadSession",
            headers=headers, json={}, timeout=15,
        )
        if session_resp.status_code >= 400:
            return False, f"OneDrive upload session failed: {session_resp.status_code}"
        upload_url = session_resp.json()["uploadUrl"]

        chunk_size = 5 * 1024 * 1024
        with open(local_path, "rb") as f:
            offset = 0
            while offset < size:
                chunk = f.read(chunk_size)
                chunk_end = offset + len(chunk) - 1
                resp = requests.put(
                    upload_url,
                    headers={"Content-Length": str(len(chunk)), "Content-Range": f"bytes {offset}-{chunk_end}/{size}"},
                    data=chunk,
                    timeout=60,
                )
                if resp.status_code >= 400:
                    return False, f"OneDrive chunk upload failed: {resp.status_code} {resp.text[:300]}"
                offset += len(chunk)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"OneDrive upload failed: {exc}"
