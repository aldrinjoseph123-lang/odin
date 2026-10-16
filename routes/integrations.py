"""Microsoft 365 integration routes: Azure app credentials, OAuth connect/
callback, disconnect, Teams channel selection, notification toggles, and the
test-email / test-teams / backup-now actions. Registration side effects only.
"""
import os
import secrets

from flask import flash, redirect, request, session, url_for

import graph
from core import app, external_url, permission_required
from db import get_db, set_setting
from services.audit import audit_log


@app.route("/settings/azure-app", methods=["POST"])
@permission_required("manage_integrations")
def settings_azure_app():
    client_id = request.form.get("client_id", "").strip()
    tenant_id = request.form.get("tenant_id", "").strip()
    client_secret = request.form.get("client_secret", "").strip()
    if not client_id or not tenant_id:
        flash("Client ID and Tenant ID are required", "error")
        return redirect(url_for("settings"))
    if not client_secret:
        # blank means "leave the existing secret alone" — re-typing a live
        # secret every time you tweak the client ID would be needless friction
        existing = graph.azure_app_credentials()
        if not existing["has_secret"]:
            flash("Client Secret is required the first time you connect", "error")
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
@permission_required("manage_integrations")
def integrations_connect():
    if not graph.oauth_client_configured():
        flash("Enter your Azure app credentials first", "error")
        return redirect(url_for("settings"))
    state = secrets.token_urlsafe(24)
    session["ms_oauth_state"] = state
    redirect_uri = external_url("integrations_callback")   # never the Host header (P3-1)
    return redirect(graph.build_authorize_url(redirect_uri, state))


@app.route("/integrations/callback")
@permission_required("manage_integrations")
def integrations_callback():
    error = request.args.get("error_description") or request.args.get("error")
    if error:
        flash(f"Microsoft sign-in failed: {error}", "error")
        return redirect(url_for("settings"))
    expected_state = session.pop("ms_oauth_state", None)
    if not expected_state or request.args.get("state") != expected_state:
        flash("Sign-in session expired or mismatched — click Connect again", "error")
        return redirect(url_for("settings"))
    code = request.args.get("code")
    if not code:
        flash("Microsoft did not return an authorization code", "error")
        return redirect(url_for("settings"))
    redirect_uri = external_url("integrations_callback")
    ok, result = graph.complete_connection(code, redirect_uri)
    if ok:
        audit_log("connect_microsoft365", details=f"as {result}")
    flash(f"Connected to Microsoft 365 as {result}" if ok else f"Connection failed: {result}", "message" if ok else "error")
    return redirect(url_for("settings"))


@app.route("/integrations/disconnect", methods=["POST"])
@permission_required("manage_integrations")
def integrations_disconnect():
    audit_log("disconnect_microsoft365")
    graph.disconnect()
    audit_log("disconnect_microsoft365")
    flash("Disconnected from Microsoft 365")
    return redirect(url_for("settings"))


@app.route("/integrations/channel", methods=["POST"])
@permission_required("manage_integrations")
def integrations_set_channel():
    team_id = request.form.get("team_id", "")
    channel_id = request.form.get("channel_id", "")
    if not team_id or not channel_id:
        flash("Pick both a team and a channel", "error")
        return redirect(url_for("settings"))
    teams_list, _err = graph.list_joined_teams()
    channels_list, _err = graph.list_channels(team_id)
    team_name = next((t["name"] for t in teams_list if t["id"] == team_id), team_id)
    channel_name = next((c["name"] for c in channels_list if c["id"] == channel_id), channel_id)
    graph.set_channel(team_id, team_name, channel_id, channel_name)
    audit_log("set_teams_channel", details=f"{team_name} / {channel_name}")
    flash(f"Teams channel set to {team_name} / {channel_name}")
    return redirect(url_for("settings"))


@app.route("/settings/integrations/test-email", methods=["POST"])
@permission_required("manage_integrations")
def settings_test_email():
    audit_log("test_email")
    db = get_db()
    user = db.execute("SELECT email FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user or not user["email"]:
        flash("Set your email on the Account page first", "error")
        return redirect(url_for("settings"))
    from policies import policy
    sender = next(iter(policy("mail_from")), None) or "the connected mailbox"   # Settings › Notifications › Send email as
    ok, error = graph.send_mail(
        user["email"], "Odin test notification", f"<p>This is a test email from Odin, sent as {sender}.</p>"
    )
    flash(f"Test email sent to {user['email']} as {sender}" if ok else f"Test email failed: {error}", "message" if ok else "error")
    return redirect(url_for("settings"))


@app.route("/settings/integrations/test-teams", methods=["POST"])
@permission_required("manage_integrations")
def settings_test_teams():
    """A card from the Odin PMS Teams app to the admin who asked, and a post in the chosen channel when one is set."""
    audit_log("test_teams")
    me = get_db().execute("SELECT email FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    results = []
    if me and me["email"]:
        from services import teams_bot
        ok, error = teams_bot.send(me["email"], "Odin test notification", "This is how Odin's notifications reach you in Teams.")
        results.append(f"Odin PMS to {me['email']}: " + ("sent" if ok else f"failed ({error})"))
    else:
        results.append("Chat: add your email address on My account first")
    if graph.teams_configured():
        ok, error = graph.send_teams_message("<b>Odin test notification</b><br>This is a test message from Odin.")
        results.append("Channel: " + ("posted" if ok else f"failed ({error})"))
    flash(" · ".join(results), "message" if all("failed" not in r and "first" not in r for r in results) else "error")
    return redirect(url_for("settings"))


@app.route("/api/teams/messages", methods=["POST"])
def teams_bot_inbound():
    """The Odin PMS app's messaging endpoint (set on the Azure Bot). Odin only
    sends; installs and anything else Teams posts here are answered and ignored,
    so nothing from this unauthenticated door is read or stored."""
    return "", 200


@app.route("/settings/teams-app.zip")
@permission_required("manage_integrations")
def settings_teams_app():
    """The Odin PMS Teams app package for a Teams admin to upload: the manifest
    (bot id = the Azure app's id) and the two icons from static/teams."""
    import io
    import zipfile
    from flask import send_file
    from policies import policy
    from services import teams_bot
    if not teams_bot.configured() or not policy("public_url").startswith("https://"):
        flash("Save the Azure app (id, secret, tenant) and an https public address under Settings › General first", "error")
        return redirect(url_for("settings_section", section="integrations"))
    from routes.client import app_version
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", teams_bot.manifest(app_version(), policy("public_url")))
        for name in ("color.png", "outline.png"):
            z.write(os.path.join(here, "static", "teams", name), name)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="odin-pms-teams-app.zip")


@app.route("/settings/integrations/backup-now", methods=["POST"])
@permission_required("manage_integrations")
def settings_backup_now():
    """Ask for a full backup (make, restore-test, copy, prune) now. The
    scheduler runs it on its next pass, within a minute, never a web worker
    (a large archive ties up a thread and dies with a worker restart, review
    P3-29); the run appears in the history on the Backups page when it ends."""
    from scheduler import BACKUP_REQUEST, healthy
    audit_log("backup_now")
    set_setting(BACKUP_REQUEST, session.get("user_name") or "an admin")
    flash("Backup queued: it starts within a minute and appears in the history below when it finishes" if healthy() else
          "Backup queued, but the scheduler is not running: it starts when the scheduler does (see Status above)")
    return redirect(url_for("settings_section", section="backups"))


@app.route("/settings/reports/send-test", methods=["POST"])
@permission_required("manage_settings")
def settings_report_send_test():
    """This week's report, now, to the admin who asked (no Teams post)."""
    from services import weekly_report
    me = get_db().execute("SELECT email FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not me or not me["email"]:
        flash("Add your email address on the Account page first", "error")
    else:
        sent, failed, message = weekly_report.send(to=[me["email"]], teams=False)
        audit_log("report_send_test", details=message)
        flash(f"Test report sent to {me['email']}" if sent else f"Not sent: {message}", "message" if sent else "error")
    return redirect(url_for("settings_section", section="reports"))


@app.route("/settings/notifications/test-resend", methods=["POST"])
@permission_required("manage_settings")
def settings_test_resend():
    """A sign-in style email through Resend alone (no Microsoft fallback), to the admin who asked."""
    audit_log("test_resend")
    from policies import policy
    from services import resend
    user = get_db().execute("SELECT email FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not policy("resend_api_key"):
        flash("Save a Resend API key above first", "error")
    elif not user or not user["email"]:
        flash("Set your email on the Account page first", "error")
    else:
        ok, error = resend.send(user["email"], "Odin test sign-in email", "<p>This is a test of Odin's sign-in mail through Resend. Sign-in links, password resets and invitations will look like this.</p>")
        flash(f"Sent to {user['email']} as {policy('resend_from')}" if ok else f"Resend refused it: {error}", "message" if ok else "error")
    return redirect(url_for("settings"))


@app.route("/settings/notifications/test-webhook", methods=["POST"])
@permission_required("manage_settings")
def settings_test_webhook():
    from policies import policy
    url = policy("teams_webhook_url")
    audit_log("test_teams_webhook", details="set" if url else "(none)")
    if not url:
        flash("Save a Teams Workflows webhook address first", "error")
    else:
        ok, error = graph.post_teams_webhook(url, "Odin test message", ["If you can read this, Odin can post to this channel."], external_url("board"))
        flash("Posted to the Teams webhook" if ok else f"The webhook refused it: {error}", "message" if ok else "error")
    return redirect(url_for("settings_section", section="notifications"))


@app.route("/settings/backups/test-share", methods=["POST"])
@permission_required("manage_integrations")
def settings_backup_test_share():
    """Is the network-share folder there and writable from the server?"""
    from policies import policy
    path = policy("share_path")
    audit_log("backup_test_share", details=path or "(none)")
    if not path or not os.path.isabs(path):
        flash("Set the share folder path (an absolute path) and save first", "error")
    elif not os.path.isdir(path):
        flash(f"{path} doesn't exist on the server — is the share mounted into the container?", "error")
    else:
        probe = os.path.join(path, f".odin-write-test-{secrets.token_hex(4)}")
        try:
            with open(probe, "w") as fh:
                fh.write("ok")
            os.remove(probe)
            flash(f"{path} is reachable and writable")
        except OSError as exc:
            flash(f"{path} exists but can't be written: {exc.strerror}", "error")
    return redirect(url_for("settings_section", section="backups"))
