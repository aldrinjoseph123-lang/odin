"""Microsoft 365 integration routes: Azure app credentials, OAuth connect/
callback, disconnect, Teams channel selection, notification toggles, and the
test-email / test-teams / backup-now actions. Registration side effects only.
"""
import os
import secrets

from flask import flash, redirect, request, session, url_for

import graph
from core import admin_required, app, permission_required
from db import get_db, set_setting
from services.audit import audit_log


@app.route("/settings/azure-app", methods=["POST"])
@permission_required("manage_integrations")
def settings_azure_app():
    client_id = request.form.get("client_id", "").strip()
    tenant_id = request.form.get("tenant_id", "").strip()
    client_secret = request.form.get("client_secret", "").strip()
    if not client_id or not tenant_id:
        flash("Client ID and Tenant ID are required")
        return redirect(url_for("settings"))
    if not client_secret:
        # blank means "leave the existing secret alone" — re-typing a live
        # secret every time you tweak the client ID would be needless friction
        existing = graph.azure_app_credentials()
        if not existing["has_secret"]:
            flash("Client Secret is required the first time you connect")
            return redirect(url_for("settings"))
        client_secret = graph._db_setting("ms_client_secret") or os.environ.get("MS_CLIENT_SECRET", "")
    graph.set_azure_app_credentials(client_id, client_secret, tenant_id)
    audit_log("set_azure_credentials", details=f"client_id={client_id}")
    flash("Azure app credentials saved — click Connect Microsoft 365 below")
    return redirect(url_for("settings"))


@app.route("/settings/azure-app/clear", methods=["POST"])
@permission_required("manage_integrations")
def settings_azure_app_clear():
    graph.disconnect()
    graph.clear_azure_app_credentials()
    audit_log("clear_azure_credentials")
    flash("Azure app credentials cleared and disconnected")
    return redirect(url_for("settings"))


@app.route("/integrations/connect")
@admin_required
def integrations_connect():
    if not graph.oauth_client_configured():
        flash("Enter your Azure app credentials first")
        return redirect(url_for("settings"))
    state = secrets.token_urlsafe(24)
    session["ms_oauth_state"] = state
    redirect_uri = url_for("integrations_callback", _external=True)
    return redirect(graph.build_authorize_url(redirect_uri, state))


@app.route("/integrations/callback")
@admin_required
def integrations_callback():
    error = request.args.get("error_description") or request.args.get("error")
    if error:
        flash(f"Microsoft sign-in failed: {error}")
        return redirect(url_for("settings"))
    expected_state = session.pop("ms_oauth_state", None)
    if not expected_state or request.args.get("state") != expected_state:
        flash("Sign-in session expired or mismatched — click Connect again")
        return redirect(url_for("settings"))
    code = request.args.get("code")
    if not code:
        flash("Microsoft did not return an authorization code")
        return redirect(url_for("settings"))
    redirect_uri = url_for("integrations_callback", _external=True)
    ok, result = graph.complete_connection(code, redirect_uri)
    if ok:
        audit_log("connect_microsoft365", details=f"as {result}")
    flash(f"Connected to Microsoft 365 as {result}" if ok else f"Connection failed: {result}")
    return redirect(url_for("settings"))


@app.route("/integrations/disconnect", methods=["POST"])
@admin_required
def integrations_disconnect():
    audit_log("disconnect_microsoft365")
    graph.disconnect()
    audit_log("disconnect_microsoft365")
    flash("Disconnected from Microsoft 365")
    return redirect(url_for("settings"))


@app.route("/integrations/channel", methods=["POST"])
@admin_required
def integrations_set_channel():
    team_id = request.form.get("team_id", "")
    channel_id = request.form.get("channel_id", "")
    if not team_id or not channel_id:
        flash("Pick both a team and a channel")
        return redirect(url_for("settings"))
    teams_list, _err = graph.list_joined_teams()
    channels_list, _err = graph.list_channels(team_id)
    team_name = next((t["name"] for t in teams_list if t["id"] == team_id), team_id)
    channel_name = next((c["name"] for c in channels_list if c["id"] == channel_id), channel_id)
    graph.set_channel(team_id, team_name, channel_id, channel_name)
    audit_log("set_teams_channel", details=f"{team_name} / {channel_name}")
    flash(f"Teams channel set to {team_name} / {channel_name}")
    return redirect(url_for("settings"))


@app.route("/settings/integrations", methods=["POST"])
@permission_required("manage_integrations")
def settings_integrations():
    set_setting("notify_email_enabled", "1" if request.form.get("notify_email_enabled") == "on" else "0")
    set_setting("notify_teams_enabled", "1" if request.form.get("notify_teams_enabled") == "on" else "0")
    set_setting(
        "onedrive_mirror_uploads_enabled",
        "1" if request.form.get("onedrive_mirror_uploads_enabled") == "on" else "0",
    )
    set_setting("onedrive_backup_enabled", "1" if request.form.get("onedrive_backup_enabled") == "on" else "0")
    audit_log("update_integration_settings")
    flash("Integration settings saved")
    return redirect(url_for("settings"))


@app.route("/settings/integrations/test-email", methods=["POST"])
@permission_required("manage_integrations")
def settings_test_email():
    audit_log("test_email")
    db = get_db()
    user = db.execute("SELECT email FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user or not user["email"]:
        flash("Set your email on the Account page first")
        return redirect(url_for("settings"))
    ok, error = graph.send_mail(
        user["email"], "Odin test notification", "This is a test email from Odin."
    )
    flash("Test email sent" if ok else f"Test email failed: {error}")
    return redirect(url_for("settings"))


@app.route("/settings/integrations/test-teams", methods=["POST"])
@permission_required("manage_integrations")
def settings_test_teams():
    audit_log("test_teams")
    ok, error = graph.send_teams_message("<b>Odin test notification</b><br>This is a test message from Odin.")
    flash("Test Teams message sent" if ok else f"Test Teams message failed: {error}")
    return redirect(url_for("settings"))


@app.route("/settings/integrations/backup-now", methods=["POST"])
@permission_required("manage_integrations")
def settings_backup_now():
    audit_log("backup_now")
    import backup as backup_module

    ok, error = backup_module.run_backup(force=True)
    flash("Backup uploaded to OneDrive" if ok else f"Backup failed: {error}")
    return redirect(url_for("settings"))
