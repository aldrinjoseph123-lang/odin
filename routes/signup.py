"""Sign-up links (services/signup.py): the admin's list on the Users page and
the public /join/<token> page a new colleague fills in. Approval happens on
the Users page with the existing access-request flow (routes/sso.py)."""
from flask import abort, jsonify, request, session
from markupsafe import escape

from core import admin_required, app, as_id, json_body, text_field, external_url
from db import get_db
from policies import policy
from security import rate_limited
from services import signup
from services.audit import audit_log
from services.notifications import notify_users
from spa import spa_index


@app.route("/api/signup-links")
@admin_required
def api_signup_links():
    projects = [{"id": r["id"], "name": r["name"]} for r in get_db().execute(
        "SELECT id, name FROM projects WHERE deleted_at IS NULL ORDER BY name")]
    return jsonify(links=signup.links(), enabled=policy("signup_enabled"), default_days=policy("signup_days"), roles=list(signup.LINK_ROLES), project_roles=list(signup.PROJECT_LINK_ROLES), projects=projects)


@app.route("/api/signup-links", methods=["POST"])
@admin_required
def api_signup_link_create():
    b = json_body()
    try:
        label = text_field(b.get("label"), 80, "Label")
        project_id = as_id(b.get("project_id"))
        if b.get("project_id") not in (None, "", 0) and project_id is None:
            raise ValueError("That rollout does not exist")
        raw = signup.create(label, b.get("role"), project_id, b.get("project_role"), b.get("days"), b.get("max_uses"), session["user_name"])
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400
    audit_log("signup_link_create", "signup_link", None, label, f"role={b.get('role')} project={project_id} uses={b.get('max_uses')}")
    return jsonify(ok=True, link=external_url("join_page", token=raw))


@app.route("/api/signup-links/<int:link_id>/revoke", methods=["POST"])
@admin_required
def api_signup_link_revoke(link_id):
    if not signup.revoke(link_id):
        abort(404)
    audit_log("signup_link_revoke", "signup_link", link_id)
    return jsonify(ok=True)


@app.route("/api/signup-links/revoke-all", methods=["POST"])
@admin_required
def api_signup_links_revoke_all():
    n = signup.revoke_all()
    audit_log("signup_link_revoke", "signup_link", None, "all open links", f"{n} revoked")
    return jsonify(ok=True, revoked=n)


@app.route("/join/<token>")
def join_page(token):
    """The public sign-up page; the React app draws it."""
    return spa_index()


def _gone():
    if not policy("signup_enabled"):
        return jsonify(error="Sign-up is closed at the moment. Ask the admin who sent you the link."), 404
    return jsonify(error="This sign-up link is no longer valid. Ask the admin who sent it for a new one."), 404


@app.route("/api/join/<token>")
def api_join(token):
    link = signup.lookup(token)
    if link is None:
        return _gone()
    return jsonify(role=link["role"], project=link["project"], project_role=link["project_role"], expires_at=link["expires_at"],
                   company=policy("company_name"), domains=policy("signup_domains"))


@app.route("/api/join/<token>", methods=["POST"])
def api_join_submit(token):
    if rate_limited(f"join:{request.remote_addr}", policy("join_attempts"), 15):
        return jsonify(error="Too many attempts from here; wait a few minutes"), 429
    link = signup.lookup(token)
    if link is None:
        return _gone()
    try:
        uid = signup.register(link, json_body())
    except ValueError as e:
        return jsonify(error=str(e)), 400
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    audit_log("signup_request", "user", uid, user["username"], f"via link '{link['label']}' as {link['role']}", actor=user["username"])
    admins = [r["id"] for r in get_db().execute("SELECT id FROM users WHERE role = 'Admin' AND active = 1")]
    where = f" and to join <b>{escape(link['project'])}</b> as {escape(link['project_role'])}" if link["project"] else ""
    notify_users(admins, "access", None, f"{user['name']} signed up for Odin",
                 f"{escape(user['name'])} ({escape(user['email'])}) used the sign-up link <b>{escape(link['label'])}</b> to ask for access as "
                 f"{escape(link['role'])}{where}. Approve or decline on the Users page.", link="/users")
    return jsonify(ok=True)
