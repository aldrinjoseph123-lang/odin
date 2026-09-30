"""Sign in with Microsoft for staff (Entra ID, one tenant, OpenID Connect).

Microsoft only proves who someone is; Odin decides what they may do. A first
sign-in by an unknown colleague creates an inactive, pending account and asks
the admins to approve it with a role. Partners never use this: they sign in
with an emailed link (routes/auth.py).

Flow: authorization code + PKCE, state and nonce, against the tenant-specific
authority (never "common"). The code is exchanged server to server over TLS
with the client secret, so per OpenID Connect Core 3.1.3.7 the ID token's
issuer is established by that TLS connection; we still check issuer, tenant,
audience, nonce and expiry before trusting a single claim. Accounts are bound
by the immutable object id (oid), never by a changeable email; the email only
links an existing Odin user on their first Microsoft sign-in.

This uses its own app registration (Settings → Sign-in & security), separate
from the Microsoft 365 mail/Teams connection, so signing in can never touch
the connected mailbox's token.
"""
import base64
import hashlib
import json
import os
import secrets
import time
from datetime import datetime
from urllib.parse import urlencode

import requests
from flask import abort, flash, redirect, request, session, url_for
from markupsafe import escape

from core import app, external_url, permission_required
from db import get_db, get_setting, set_setting
from routes.auth import safe_next_url, start_session
from services.audit import audit_log
from services.sealed import seal, unseal

LOGIN_BASE = "https://login.microsoftonline.com"


def sso_config():
    """(client_id, tenant_id, secret) — Settings first, then environment."""
    return (get_setting("sso_client_id") or os.environ.get("SSO_CLIENT_ID", ""),
            get_setting("sso_tenant_id") or os.environ.get("SSO_TENANT_ID", ""),
            unseal(get_setting("sso_client_secret")) or os.environ.get("SSO_CLIENT_SECRET", ""))


def sso_configured():
    client_id, tenant, secret = sso_config()
    return bool(client_id and tenant and secret)


def sso_enforced():
    """Staff must use Microsoft; passwords only for flagged accounts."""
    return sso_configured() and get_setting("sso_enforced") == "1"


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _claims(id_token):
    payload = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


@app.route("/auth/microsoft")
def sso_start():
    if not sso_configured():
        flash("Microsoft sign-in is not set up yet")
        return redirect(url_for("login"))
    client_id, tenant, _ = sso_config()
    verifier = _b64url(secrets.token_bytes(32))
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    session["sso"] = {"state": state, "nonce": nonce, "verifier": verifier, "next": safe_next_url()}
    params = {
        "client_id": client_id, "response_type": "code", "response_mode": "query",
        "redirect_uri": external_url("sso_callback"), "scope": "openid profile email",
        "state": state, "nonce": nonce, "prompt": "select_account",
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
    }
    return redirect(f"{LOGIN_BASE}/{tenant}/oauth2/v2.0/authorize?{urlencode(params)}")


def _refuse(reason, details):
    audit_log("login_failure", details=f"microsoft: {details}", actor="microsoft")
    flash(reason)
    return redirect(url_for("login"))


@app.route("/auth/microsoft/callback")
def sso_callback():
    pending = session.pop("sso", None)
    if request.args.get("error"):
        return _refuse("Microsoft did not sign you in: " + request.args.get("error_description", request.args["error"])[:200], request.args["error"])
    if not pending or not secrets.compare_digest(request.args.get("state", ""), pending["state"]):
        return _refuse("That sign-in attempt expired — try again", "state mismatch")
    client_id, tenant, secret = sso_config()
    try:
        resp = requests.post(f"{LOGIN_BASE}/{tenant}/oauth2/v2.0/token", timeout=15, data={
            "client_id": client_id, "client_secret": secret, "grant_type": "authorization_code",
            "code": request.args.get("code", ""), "redirect_uri": external_url("sso_callback"),
            "code_verifier": pending["verifier"], "scope": "openid profile email",
        })
        token = resp.json()
        claims = _claims(token["id_token"])
    except Exception as exc:  # noqa: BLE001 — network, bad JSON, no id_token
        return _refuse("Microsoft sign-in failed — try again", f"token exchange: {str(exc)[:120]}")
    # Trust nothing until it is ours: this tenant, this app, this attempt, still valid.
    if (claims.get("tid") != tenant or claims.get("iss") != f"{LOGIN_BASE}/{tenant}/v2.0" or claims.get("aud") != client_id
            or claims.get("nonce") != pending["nonce"] or int(claims.get("exp", 0)) < time.time() or not claims.get("oid")):
        return _refuse("That Microsoft account can't sign in here", f"claims rejected (tid={claims.get('tid')})")

    db = get_db()
    oid = claims["oid"]
    email = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    name = (claims.get("name") or email or "New colleague").strip()[:120]
    user = db.execute("SELECT * FROM users WHERE ms_oid = ?", (oid,)).fetchone()
    if user is None and email:
        # First Microsoft sign-in of someone Odin already knows: bind by email, once.
        user = db.execute("SELECT * FROM users WHERE lower(email) = ? AND ms_oid IS NULL", (email,)).fetchone()
        if user and user["kind"] == "internal":
            db.execute("UPDATE users SET ms_oid = ? WHERE id = ?", (oid, user["id"]))
            db.commit()
            audit_log("link_microsoft_account", "user", user["id"], user["username"], email, actor=user["username"])
            user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    if user is not None and user["kind"] == "external":
        return _refuse("Partner and customer accounts sign in with an email link", f"external account {email}")
    if user is None:
        return _request_access(oid, email, name)
    if user["pending"]:
        flash("Your access request is waiting for an admin — you'll be able to sign in once it's approved")
        return redirect(url_for("login"))
    if not user["active"]:
        return _refuse("This account has been deactivated", f"deactivated {user['username']}")
    start_session(user)
    audit_log("login_success", "user", user["id"], user["username"], "microsoft", actor=user["username"])
    return redirect(pending.get("next") or url_for("board"))


def _request_access(oid, email, name):
    """An unknown colleague: an inactive, pending Viewer the admins approve."""
    from policies import policy
    from services.notifications import notify_users
    db = get_db()
    username = (email.split("@")[0] if email else f"ms-{oid[:8]}")[:40]
    if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        username = f"{username}-{oid[:6]}"
    cur = db.execute(
        "INSERT INTO users (username, password_hash, name, role, active, email, created_at, kind, ms_oid, pending, theme, accent)"
        " VALUES (?, 'microsoft:no-password', ?, 'Viewer', 0, ?, ?, 'internal', ?, 1, ?, ?)",
        (username, name, email or None, datetime.utcnow().isoformat(), oid, policy("default_theme"), policy("default_accent")))
    db.commit()
    audit_log("access_requested", "user", cur.lastrowid, username, f"microsoft {email}", actor=username)
    admins = [r["id"] for r in db.execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
    notify_users(admins, "access", None, f"{escape(name)} asked to use Odin",
                 f"{escape(name)} ({escape(email)}) signed in with Microsoft for the first time. Approve them with a role on the Users page.",
                 link="/users")
    flash("Thanks — an admin has been asked to approve your access. You'll be able to sign in once they do")
    return redirect(url_for("login"))


@app.route("/settings/sso", methods=["POST"])
@permission_required("manage_settings")
def settings_sso():
    """Save the sign-in app registration and the "Microsoft only" switch. The
    secret is write-only: blank keeps the saved one."""
    f = request.form
    if f.get("clear") == "1":
        db = get_db()
        db.execute("DELETE FROM settings WHERE key IN ('sso_client_id', 'sso_tenant_id', 'sso_client_secret', 'sso_enforced')")
        db.commit()
        audit_log("update_sso_settings", "settings", None, "microsoft sign-in", "removed")
        flash("Microsoft sign-in removed: staff sign in with a password again")
        return redirect(url_for("settings_section", section="security"))
    client_id, tenant = f.get("client_id", "").strip(), f.get("tenant_id", "").strip()
    if client_id or tenant:
        import re
        guid = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        if not (re.fullmatch(guid, client_id) and re.fullmatch(guid, tenant)):
            flash("Client and tenant IDs are GUIDs, as shown on the app registration's overview (not \"common\")")
            return redirect(url_for("settings_section", section="security"))
        set_setting("sso_client_id", client_id)
        set_setting("sso_tenant_id", tenant)
        if f.get("client_secret", "").strip():
            set_setting("sso_client_secret", seal(f["client_secret"].strip()))   # sealed at rest
    want = f.get("enforced") == "on"
    if want and not sso_configured():
        flash("Save the app registration before requiring Microsoft sign-in")
        return redirect(url_for("settings_section", section="security"))
    if want and not get_db().execute(
            "SELECT 1 FROM users WHERE role = 'Admin' AND active = 1 AND kind = 'internal' AND password_login = 1").fetchone():
        flash("Give at least one active admin \"Can sign in with a password\" on the Users page first — it is the way back in if Microsoft is unavailable")
        return redirect(url_for("settings_section", section="security"))
    set_setting("sso_enforced", "1" if want else "0")
    audit_log("update_sso_settings", "settings", None, "microsoft sign-in",
              f"client={client_id or '(unchanged)'} tenant={tenant or '(unchanged)'} enforced={want}")
    flash("Saved")
    return redirect(url_for("settings_section", section="security"))


@app.route("/users/<int:user_id>/approve", methods=["POST"])
@permission_required("manage_users")
def user_approve(user_id):
    from constants import ROLES
    role = request.form.get("role", "")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ? AND pending = 1", (user_id,)).fetchone()
    if user is None:
        abort(404)
    if role not in ROLES or role == "External":
        flash("Pick a role")
        return redirect(url_for("users"))
    db.execute("UPDATE users SET pending = 0, active = 1, role = ? WHERE id = ?", (role, user_id))
    db.commit()
    from services.signup import on_approve
    joined = on_approve(user)   # a sign-up link that named a project
    audit_log("approve_access", "user", user_id, user["username"], f"role={role}" + (f"; joined {joined}" if joined else ""))
    from services.notifications import notify_users
    notify_users([user_id], "access", None, "Welcome to Odin",
                 f"Your access was approved: you are a {escape(role)}" + (f" and on {escape(joined)}" if joined else "") + ".", link="/")
    flash(f"{user['name']} can now sign in as {role}" + (f" and is on {joined}" if joined else ""))
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/decline", methods=["POST"])
@permission_required("manage_users")
def user_decline(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ? AND pending = 1", (user_id,)).fetchone()
    if user is None:
        abort(404)
    # Kept as an inactive account, so a second attempt is visibly the same person.
    db.execute("UPDATE users SET pending = 0, active = 0 WHERE id = ?", (user_id,))
    db.commit()
    audit_log("decline_access", "user", user_id, user["username"])
    flash(f"Declined {user['name']}")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/password-login", methods=["POST"])
@permission_required("manage_users")
def user_password_login(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ? AND kind = 'internal'", (user_id,)).fetchone()
    if user is None:
        abort(404)
    on = request.form.get("allowed") == "on"
    if not on and sso_enforced() and user["role"] == "Admin" and not db.execute(
            "SELECT 1 FROM users WHERE role = 'Admin' AND active = 1 AND password_login = 1 AND id != ?", (user_id,)).fetchone():
        flash("Keep at least one admin who can sign in with a password while Microsoft sign-in is required")
        return redirect(url_for("users"))
    db.execute("UPDATE users SET password_login = ? WHERE id = ?", (1 if on else 0, user_id))
    db.commit()
    audit_log("set_password_login", "user", user_id, user["username"], "allowed" if on else "removed")
    flash(f"{user['name']} {'can' if on else 'can no longer'} sign in with a password")
    return redirect(url_for("users"))
