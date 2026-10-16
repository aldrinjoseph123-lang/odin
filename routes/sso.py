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
links an existing Odin user on their first Microsoft sign-in, and only when
that user proved the address by opening a link mailed to it (review P2-3).
The UPN Microsoft gave is kept beside the oid (users.ms_upn).

A colleague whose account already has a password links Microsoft from their
Account page (signed in with that password, then through Microsoft), so a
first Microsoft sign-in never takes over one that has a working password.

This uses its own app registration (Settings › Sign-in & security), separate
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
from flask import abort, flash, jsonify, redirect, request, session, url_for
from markupsafe import escape

from core import app, external_url, login_required, permission_required
from db import get_db, get_setting, set_setting
from routes.auth import safe_next_url, start_session
from security import clean_text
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
        flash("Microsoft sign-in is not set up yet", "error")
        return redirect(url_for("login"))
    return _authorize(safe_next_url())


@app.route("/api/account/microsoft")
@login_required
def api_account_microsoft():
    """Whether the Account page offers Link Microsoft."""
    me = get_db().execute("SELECT kind, ms_oid FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return jsonify(available=sso_configured() and me["kind"] == "internal", linked=me["ms_oid"] is not None)


@app.route("/account/microsoft", methods=["POST"])
@login_required
def account_link_microsoft():
    """Link Microsoft to the signed-in account: this session is the Odin half,
    the Microsoft sign-in the other; the callback binds that oid to this
    account only (see _link)."""
    me = get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    problem = ("Microsoft sign-in is not set up yet" if not sso_configured() else
               "Partner and customer accounts sign in with an email link" if me["kind"] != "internal" else
               "Your account is already linked to Microsoft" if me["ms_oid"] else None)
    if problem:
        flash(problem, "error")
        return redirect(url_for("account"))
    audit_log("link_microsoft_started", "user", me["id"], me["username"])
    return _authorize(url_for("account"), link=me["id"])


def _authorize(next_url, link=None):
    """Off to Microsoft; `link` is the signed-in user Link Microsoft binds to."""
    client_id, tenant, _ = sso_config()
    verifier = _b64url(secrets.token_bytes(32))
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    session["sso"] = {"state": state, "nonce": nonce, "verifier": verifier, "next": next_url, "link": link}
    params = {
        "client_id": client_id, "response_type": "code", "response_mode": "query",
        "redirect_uri": external_url("sso_callback"), "scope": "openid profile email",
        "state": state, "nonce": nonce, "prompt": "select_account",
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
    }
    return redirect(f"{LOGIN_BASE}/{tenant}/oauth2/v2.0/authorize?{urlencode(params)}")


def _refuse(reason, details):
    audit_log("login_failure", details=clean_text(f"microsoft: {details}"), actor="microsoft")
    flash(reason)
    return redirect(url_for("login"))


# Fixed words for Microsoft's error codes: the callback's query string is
# anyone's to write, so its error_description never reaches the page (review P3-4).
OAUTH_ERRORS = {
    "access_denied": "Microsoft sign-in was cancelled, or your organisation did not allow it",
    "consent_required": "Your organisation has not approved Odin's Microsoft sign-in yet: ask an admin",
    "interaction_required": "Microsoft needs you to sign in again: try once more",
    "login_required": "Microsoft needs you to sign in again: try once more",
    "temporarily_unavailable": "Microsoft is not answering at the moment: try again in a few minutes",
}


@app.route("/auth/microsoft/callback")
def sso_callback():
    pending = session.pop("sso", None)
    if request.args.get("error"):
        code = clean_text(request.args["error"], 60)
        return _refuse(OAUTH_ERRORS.get(code, "Microsoft did not sign you in — try again"), f"error {code}")
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
        return _refuse("Microsoft sign-in failed — try again", f"token exchange: {clean_text(exc, 120)}")
    # Trust nothing until it is ours: this tenant, this app, this attempt, still valid.
    if (claims.get("tid") != tenant or claims.get("iss") != f"{LOGIN_BASE}/{tenant}/v2.0" or claims.get("aud") != client_id
            or claims.get("nonce") != pending["nonce"] or int(claims.get("exp", 0)) < time.time() or not claims.get("oid")):
        return _refuse("That Microsoft account can't sign in here", f"claims rejected (tid={clean_text(claims.get('tid'), 40)})")

    db = get_db()
    oid = claims["oid"]
    upn = clean_text(claims.get("preferred_username"), 254).strip().lower() or None   # the home-tenant UPN, kept with the binding
    email = clean_text(claims.get("email") or claims.get("preferred_username"), 254).strip().lower()
    name = clean_text(claims.get("name") or email or "New colleague", 120).strip() or "New colleague"
    if pending.get("link"):
        return _link(pending["link"], oid, email, upn)
    user = db.execute("SELECT * FROM users WHERE ms_oid = ?", (oid,)).fetchone()
    if user is None and email:
        # First Microsoft sign-in of someone Odin already knows: bind by email, once,
        # and only to an address its owner proved (review P2-3).
        user = db.execute("SELECT * FROM users WHERE lower(email) = ? AND ms_oid IS NULL", (email,)).fetchone()
        if user and user["kind"] == "internal" and (_password_usable(user) or not user["email_verified_at"]):
            return _clash(user, email, name)
        if user and user["kind"] == "internal":
            # the password, if any, could not sign in anyway: retire it with the binding, end old sessions
            db.execute("UPDATE users SET ms_oid = ?, ms_upn = ?, password_hash = 'microsoft:no-password', session_epoch = session_epoch + 1 WHERE id = ?",
                       (oid, upn, user["id"]))
            db.commit()
            audit_log("link_microsoft_account", "user", user["id"], user["username"], f"{email} (UPN {upn})", actor=user["username"])
            user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    if user is not None and user["kind"] == "external":
        return _refuse("Partner and customer accounts sign in with an email link", f"external account {email}")
    if user is None:
        return _request_access(oid, email, name, upn)
    if user["pending"]:
        flash("Your access request is waiting for an admin — you'll be able to sign in once it's approved")
        return redirect(url_for("login"))
    if not user["active"]:
        return _refuse("This account has been deactivated", f"deactivated {user['username']}")
    start_session(user)
    audit_log("login_success", "user", user["id"], user["username"], "microsoft", actor=user["username"])
    return redirect(pending.get("next") or url_for("board"))


def _password_usable(user):
    """A password that can sign in: a real hash, and password sign-in allowed for it."""
    return "$" in (user["password_hash"] or "") and not (sso_enforced() and not user["password_login"])


def _link(user_id, oid, email, upn):
    """The end of Link Microsoft: still the same live session, and an oid no account holds."""
    from core import _session_still_valid
    db = get_db()
    if session.get("user_id") != user_id or not _session_still_valid():
        return _refuse("Your session ended: sign in again, then link Microsoft on your Account page", "link: the session ended")
    username = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()[0]
    if db.execute("SELECT 1 FROM users WHERE ms_oid = ?", (oid,)).fetchone():
        audit_log("link_microsoft_refused", "user", user_id, username, f"microsoft {email}: already linked to another account")
        flash("That Microsoft account is already linked to another Odin account", "error")
        return redirect(url_for("account"))
    db.execute("UPDATE users SET ms_oid = ?, ms_upn = ? WHERE id = ? AND ms_oid IS NULL", (oid, upn, user_id))
    db.commit()
    audit_log("link_microsoft_account", "user", user_id, username, f"microsoft {email} (UPN {upn}), from the Account page")
    flash("Microsoft linked: you can sign in with it from now on")
    return redirect(url_for("account"))


def _clash(user, email, name):
    """A first Microsoft sign-in whose address is on an account with a working
    password (test round P2-3), or on one whose owner never proved the address
    (review P2-3): whoever set it may not be this person, so nothing is linked
    and no account is created. With a password, the person signs in with it
    and links Microsoft on their Account page; an unproven address is
    confirmed from the link mailed to it first. The admins are told in case it
    is someone else."""
    from services.notifications import notify_users
    proven = bool(user["email_verified_at"])
    audit_log("link_microsoft_refused", "user", user["id"], user["username"],
              f"microsoft {email}: " + ("the account has a password; link it from the Account page" if proven else "the address on the account is not confirmed"),
              actor="microsoft")
    admins = [r["id"] for r in get_db().execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
    why = "which signs in with a password" if proven else "whose owner has not confirmed that address"
    notify_users(admins, "access", None, f"{escape(name)} tried to sign in with Microsoft",
                 f"{escape(name)} ({escape(email)}) signed in with Microsoft for the first time, but {escape(email)} is the address of"
                 f" {escape(user['name'])}'s account, {why}, so Odin linked nothing. If it is the same person,"
                 + (" they sign in with the password and use Link Microsoft on their Account page." if proven else
                    " they confirm the address from the link Odin mails to it (saving the address on the Users page sends one).")
                 + " If not, check who set that address.",
                 link="/users")
    flash("An Odin account with your address signs in with a password, so Microsoft was not linked to it."
          " Sign in with that password, then use Link Microsoft on your Account page" if proven else
          "An Odin account has your address but it is not confirmed yet, so Microsoft was not linked to it."
          " Open the confirmation link Odin mailed to that address, or ask an admin")
    return redirect(url_for("login"))


def _request_access(oid, email, name, upn):
    """An unknown colleague: an inactive, pending Viewer the admins approve.
    An address another account already has stays off the request (one
    account per address)."""
    from policies import policy
    from services.notifications import notify_users
    db = get_db()
    username = (email.split("@")[0] if email else f"ms-{oid[:8]}")[:40]
    if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        username = f"{username}-{oid[:6]}"
    from security import identity_taken
    taken = bool(email) and identity_taken(db, email)
    now = datetime.utcnow().isoformat()
    # the address counts as proven when it is the UPN: a name in a domain this tenant verified
    cur = db.execute(
        "INSERT INTO users (username, password_hash, name, role, active, email, created_at, kind, ms_oid, ms_upn, pending, theme, accent, email_verified_at)"
        " VALUES (?, 'microsoft:no-password', ?, 'Viewer', 0, ?, ?, 'internal', ?, ?, 1, ?, ?, ?)",
        (username, name, None if taken else email or None, now, oid, upn, policy("default_theme"), policy("default_accent"),
         now if email and not taken and email == upn else None))
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
            flash("Client and tenant IDs are GUIDs, as shown on the app registration's overview (not \"common\")", "error")
            return redirect(url_for("settings_section", section="security"))
        set_setting("sso_client_id", client_id)
        set_setting("sso_tenant_id", tenant)
        if f.get("client_secret", "").strip():
            set_setting("sso_client_secret", seal(f["client_secret"].strip()))   # sealed at rest
    want = f.get("enforced") == "on"
    if want and not sso_configured():
        flash("Save the app registration before requiring Microsoft sign-in", "error")
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
        flash("Pick a role", "error")
        return redirect(url_for("users"))
    from routes.users import admin_only
    if admin_only(role):
        flash("Only an admin can approve someone as an admin", "error")
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
    from routes.users import admin_only
    if admin_only(user["role"]):
        flash("Only an admin can change how an admin signs in", "error")
        return redirect(url_for("users"))
    on = request.form.get("allowed") == "on"
    if not on and sso_enforced() and user["role"] == "Admin" and not db.execute(
            "SELECT 1 FROM users WHERE role = 'Admin' AND active = 1 AND password_login = 1 AND id != ?", (user_id,)).fetchone():
        flash("Keep at least one admin who can sign in with a password while Microsoft sign-in is required", "error")
        return redirect(url_for("users"))
    db.execute("UPDATE users SET password_login = ? WHERE id = ?", (1 if on else 0, user_id))
    db.commit()
    audit_log("set_password_login", "user", user_id, user["username"], "allowed" if on else "removed")
    flash(f"{user['name']} {'can' if on else 'can no longer'} sign in with a password")
    return redirect(url_for("users"))
