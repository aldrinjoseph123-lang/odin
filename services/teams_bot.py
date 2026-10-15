"""The "Odin PMS" Teams app: each notification as a card in the person's own
chat with Odin, under Odin's name and icon, apart from the other systems that
share the notifications@ mailbox (13 Oct 2026, the user's call).

A notification-only bot on the same Azure app registration as the Microsoft 365
connection (its app id and secret, single tenant). Odin only sends: it opens a
one-to-one conversation with the person through the Bot Framework and posts an
Adaptive Card. The app must be installed for the person (a Teams admin setup
policy does that for everyone); until it is, sending fails and the admins hear
of it once a day. Best effort: never raises; returns (ok, error)."""
import json
import time

import requests

import graph

SERVICE_URL = "https://smba.trafficmanager.net/teams"   # Teams' global Bot Framework endpoint
_token = {"value": None, "until": 0.0}


def configured():
    """The Azure app's id and secret, and a real tenant (a bot is single-tenant)."""
    return graph.oauth_client_configured() and graph._tenant() not in ("", "common")


def _bot_token():
    if _token["value"] and time.time() < _token["until"] - 60:
        return _token["value"], None
    resp = requests.post(f"{graph.AUTH_BASE}/{graph._tenant()}/oauth2/v2.0/token", timeout=15, data={
        "grant_type": "client_credentials", "client_id": graph._client_id(), "client_secret": graph._client_secret(),
        "scope": "https://api.botframework.com/.default"})
    if resp.status_code >= 400:
        return None, f"Teams app sign-in failed: {resp.status_code} {resp.text[:200]}"
    body = resp.json()
    _token.update(value=body["access_token"], until=time.time() + int(body.get("expires_in", 3600)))
    return _token["value"], None


def card(title, text, link=None):
    """The Adaptive Card every message wears: the title, the words, a way back
    into Odin. The words may quote an outsider (a guest note): Markdown escaped."""
    return {"type": "AdaptiveCard", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "version": "1.4",
            "body": [{"type": "TextBlock", "text": graph.md_escape(title), "weight": "Bolder", "wrap": True},
                     *([{"type": "TextBlock", "text": graph.md_escape(text), "wrap": True, "spacing": "Small"}] if text else [])],
            **({"actions": [{"type": "Action.OpenUrl", "title": "Open in Odin", "url": link}]} if link else {})}


def send(email, title, text, link=None):
    """A card in the person's chat with Odin PMS. The conversation is opened on
    the first message and kept per address; a gone one is opened again once."""
    if not configured():
        return False, "The Odin PMS Teams app needs the Azure app's id, secret and tenant (Settings › Integrations)"
    try:
        token, error = _bot_token()
        if error:
            return False, error
        headers = {"Authorization": f"Bearer {token}"}
        key = f"teams_conv:{email.lower()}"
        for attempt in (1, 2):
            conv = graph._db_setting(key)
            if not conv:
                conv, error = _open(headers, email)
                if error:
                    return False, error
                graph._set_db_setting(key, conv)
            resp = requests.post(f"{SERVICE_URL}/v3/conversations/{conv}/activities", headers=headers, timeout=15, json={
                "type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card(title, text, link)}]})
            if resp.status_code < 400:
                return True, None
            if resp.status_code in (403, 404) and attempt == 1:
                graph._set_db_setting(key, None)   # uninstalled and installed again: a new conversation
                continue
            return False, f"Teams message failed: {resp.status_code} {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Teams message failed: {exc}"


def _open(headers, email):
    uid, error = graph.user_id(email)
    if error:
        return None, error
    tenant = graph._tenant()
    resp = requests.post(f"{SERVICE_URL}/v3/conversations", headers=headers, timeout=15, json={
        "isGroup": False, "bot": {"id": f"28:{graph._client_id()}"}, "members": [{"id": uid}],
        "tenantId": tenant, "channelData": {"tenant": {"id": tenant}}})
    if resp.status_code == 403:
        return None, f"The Odin PMS app is not installed in Teams for {email}"
    if resp.status_code >= 400:
        return None, f"Teams message failed: {resp.status_code} {resp.text[:200]}"
    return resp.json()["id"], None


def manifest(version, public_url):
    """The Teams app manifest (v1.16): a personal, notification-only bot named
    Odin PMS. Privacy and terms: the public page about the app (static/teams/about.html)."""
    from urllib.parse import urlsplit
    app_id = graph._client_id()
    about = f"{public_url}/static/teams/about.html"
    return json.dumps({
        "$schema": "https://developer.microsoft.com/en-us/json-schemas/teams/v1.16/MicrosoftTeams.schema.json",
        "manifestVersion": "1.16", "version": version, "id": app_id,
        "developer": {"name": "Protect24x7", "websiteUrl": public_url, "privacyUrl": f"{about}#privacy", "termsOfUseUrl": f"{about}#terms"},
        "name": {"short": "Odin PMS", "full": "Odin by Protect24x7"},
        "description": {"short": "Rollout notifications from Odin", "full": "Odin's notifications and alerts for the rollouts you work on: stage moves, approvals, tasks, mentions and alerts, each with a link back into Odin."},
        "icons": {"color": "color.png", "outline": "outline.png"}, "accentColor": "#0A0A0A",
        "bots": [{"botId": app_id, "scopes": ["personal"], "isNotificationOnly": True, "supportsFiles": False}],
        "permissions": ["identity"], "validDomains": [urlsplit(public_url).hostname],
    }, indent=2)
