"""User administration: create users, set role/active/email, reset passwords.
All gated on manage_users. Imported for route registration side effects.
"""
from datetime import datetime

from flask import abort, flash, redirect, request, session, url_for
from werkzeug.security import generate_password_hash

from constants import ROLES
from policies import POLICIES, policy
from core import app, as_id, permission_required, role_has_permission
from spa import spa_index
from db import PROJECT_OPEN_SQL, get_db, set_project_manager
from security import identity_taken, password_problem, valid_email, valid_username, safe_csv_writer
from services import workload
from services.fmt import plural
from services.audit import audit_log


def _email_taken(db, email, user_id=None):
    """Email lookups (invites, sign-in links, password resets) need one account per address (test report FN-6)."""
    return identity_taken(db, email, user_id)   # nor anyone's username: sign-in takes either


def admin_only(*roles):
    """True when someone who is not an Admin acts on the Admin role (test round
    P2-1): manage_users can be delegated, and its holder must not be able to
    make an Admin (themselves included) or take over one's account."""
    return "Admin" in roles and session.get("role") != "Admin"


def _user_or_404(db, user_id):
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    return user


@app.route("/users", methods=["GET", "POST"])
@permission_required("manage_users")
def users():
    if request.method == "GET":
        return spa_index()
    db = get_db()
    username = request.form.get("username", "").strip()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role") or "Member"
    existing = identity_taken(db, username)   # "Pm1" is "pm1", and no one's address either
    problem = password_problem(password)
    if not username or not name:
        flash("Username and name are required", "error")
    elif not valid_username(username):
        flash("Username: up to 64 letters, digits, dots, dashes, underscores or @", "error")
    elif len(name) > 120 or any(ord(ch) < 32 for ch in name):
        flash("Name: one line, at most 120 characters", "error")
    elif role not in ROLES or role == "External":   # staff accounts; partners are invited to a project instead
        flash(f"Pick a role: {', '.join(r for r in ROLES if r != 'External')}", "error")
    elif admin_only(role):
        flash("Only an admin can create an admin", "error")
    elif existing:
        flash("That username is taken, or is another account's email", "error")
    elif email and not valid_email(email):
        flash("Enter a valid email address", "error")
    elif email and _email_taken(db, email):
        flash("That address belongs to another account", "error")
    elif problem:
        flash(problem, "error")
    else:
        cursor = db.execute(
            # an admin-set password is temporary: the person sets their own at first sign-in
            "INSERT INTO users (username, password_hash, name, role, active, email, created_at, theme, accent, must_change_password) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 1)",
            (username, generate_password_hash(password, method="pbkdf2:sha256"), name, role, email or None,
             datetime.utcnow().isoformat(), policy("default_theme"), policy("default_accent")),
        )
        db.commit()
        audit_log("create_user", "user", cursor.lastrowid, username, f"role={role}")
        flash(f"User {name} created" + _verification_note(cursor.lastrowid, email))
    return redirect(url_for("users"))


@app.route("/users/export.csv")
@permission_required("manage_users")
def users_export():
    """The access-review pack: every account, its role, when it was created,
    when it last signed in. Quarterly, an auditor asks for exactly this."""
    import csv
    import io
    from flask import Response
    from services.access_review import review
    db = get_db()
    rows = db.execute(
        "SELECT id, username, name, email, role, active, created_at, last_login_at FROM users ORDER BY username"
    ).fetchall()
    flagged = review(db, policy("access_review_days"))
    out = io.StringIO()
    writer = safe_csv_writer(out)
    writer.writerow(["username", "name", "email", "role", "active", "created_at", "last_login_at", "review"])
    for r in rows:
        writer.writerow([r["username"], r["name"], r["email"], r["role"], r["active"], r["created_at"], r["last_login_at"], "; ".join(flagged.get(r["id"], []))])
    audit_log("export_users", details=f"{len(rows)} accounts")
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=odin-users.csv"})


@app.route("/users/<int:user_id>/role", methods=["POST"])
@permission_required("manage_users")
def user_set_role(user_id):
    role = request.form.get("role", "")
    if role not in ROLES:
        flash("Invalid role", "error")
        return redirect(url_for("users"))
    if user_id == session["user_id"] and role != "Admin":
        flash("You cannot remove your own Admin role" if session.get("role") == "Admin" else "You cannot change your own role", "error")
        return redirect(url_for("users"))
    db = get_db()
    user = _user_or_404(db, user_id)
    if admin_only(role, user["role"]):
        flash("Only an admin can give or take away the Admin role", "error")
        return redirect(url_for("users"))
    if (role == "External") != (user["kind"] == "external"):
        # the role follows the kind of account: partners stay External, staff never become it
        flash("External is the role of partner accounts only; staff take Admin, Member, Contributor or Viewer", "error")
        return redirect(url_for("users"))
    # the role rides in the session cookie: end their sessions so it takes effect now, not at their next sign-in
    db.execute("UPDATE users SET role = ?, session_epoch = session_epoch + 1 WHERE id = ?", (role, user_id))
    db.commit()
    audit_log("update_user_role", "user", user_id, user["username"], f"new_role={role}")
    flash("Role updated")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/active", methods=["POST"])
@permission_required("manage_users")
def user_set_active(user_id):
    if user_id == session["user_id"]:
        flash("You cannot deactivate your own account", "error")
        return redirect(url_for("users"))
    active = 1 if request.form.get("active") == "1" else 0
    db = get_db()
    user = _user_or_404(db, user_id)
    if admin_only(user["role"]):
        flash("Only an admin can deactivate or reactivate an admin", "error")
        return redirect(url_for("users"))
    if user["pending"]:
        # the switch would skip the approval: no role chosen, no rollout joined, still "waiting" (review P3-15)
        flash("This person is waiting for approval: use Approve or Decline on the Users page", "error")
        return redirect(url_for("users"))
    handover = None
    if request.form.get("handover_to"):
        handover, problem = _handover_target(db, user, active, as_id(request.form.get("handover_to")))
        if problem:
            flash(problem, "error")
            return redirect(url_for("users"))
    # Bumping the epoch ends any session this user currently has open.
    db.execute("UPDATE users SET active = ?, session_epoch = session_epoch + 1 WHERE id = ?", (active, user_id))
    moved = _hand_over(db, user_id, handover["id"]) if handover else None   # same transaction: all of it or none
    db.commit()
    said = ""
    if moved:
        said = (f"; handed over to {handover['name']}: {moved['tasks']} open {plural(moved['tasks'], 'task')}, "
                f"{len(moved['rollouts'])} {plural(len(moved['rollouts']), 'rollout')}, {moved['raid']} RAID {plural(moved['raid'], 'item')}")
    audit_log("set_user_active", "user", user_id, user["username"], f"active={active}{said}")
    if moved and (moved["tasks"] or moved["rollouts"] or moved["raid"]):
        _tell_new_owner(handover["id"], user["name"], moved)
    flash("User updated" + said)
    return redirect(url_for("users"))


def _handover_target(db, user, active, target_id):
    """(the colleague to hand the work to, None) or (None, why not). Leave only: an
    active staff account other than the person, who can manage a rollout when they hold some."""
    if active:
        return None, "A hand-over goes with deactivating, not reactivating"
    target = db.execute("SELECT id, name, role FROM users WHERE id = ? AND active = 1 AND kind = 'internal' AND pending = 0",
                        (target_id or 0,)).fetchone()
    if target is None or target["id"] == user["id"]:
        return None, "Pick an active colleague (not an external account) to hand the work to"
    if workload.holds(db, [user["id"]])[user["id"]]["rollouts"] and not role_has_permission(target["role"], "edit_project_stage"):
        return None, f"{target['name']} cannot manage rollouts: pick an Admin or Member"   # as the owner of a rollout must be
    return target, None


def _hand_over(db, from_id, to_id):
    """Move the person's open tasks, rollouts (as owner, pending CRM intakes too) and RAID items to `to_id`; the caller commits."""
    now = datetime.utcnow().isoformat()
    live = f"IN (SELECT p.id FROM projects p WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL})"
    rollouts = [dict(r) for r in db.execute(   # an intake waiting for confirmation would otherwise wait on someone who left
        f"SELECT p.id, p.name FROM projects p WHERE p.owner_id = ? AND p.deleted_at IS NULL AND ({PROJECT_OPEN_SQL} OR p.intake_pending = 1) ORDER BY p.name",
        (from_id,))]
    for r in rollouts:
        db.execute("UPDATE projects SET owner_id = ?, updated_at = ? WHERE id = ?", (to_id, now, r["id"]))
        set_project_manager(db, r["id"], to_id, session["user_id"])   # the PM row follows the owner; they stay on the team as a coordinator
    tasks = db.execute(f"UPDATE tasks SET assignee_id = ? WHERE assignee_id = ? AND done = 0 AND project_id {live}", (to_id, from_id)).rowcount
    raid = db.execute(f"UPDATE raid_items SET owner_id = ?, updated_at = ? WHERE owner_id = ? AND status NOT IN ('closed', 'decided') AND project_id {live}",
                      (to_id, now, from_id)).rowcount
    return {"tasks": tasks, "rollouts": rollouts, "raid": raid}


def _tell_new_owner(to_id, from_name, moved):
    from markupsafe import escape
    from services.notifications import notify_users
    parts = [f"{moved['tasks']} open {plural(moved['tasks'], 'task')}" if moved["tasks"] else "",
             f"{len(moved['rollouts'])} {plural(len(moved['rollouts']), 'rollout')} to manage" if moved["rollouts"] else "",
             f"{moved['raid']} RAID {plural(moved['raid'], 'item')}" if moved["raid"] else ""]
    what = ", ".join(x for x in parts if x)
    names = ", ".join(escape(r["name"]) for r in moved["rollouts"][:5]) + (" and more" if len(moved["rollouts"]) > 5 else "")
    notify_users([to_id], "assigned", None, f"{escape(from_name)}'s work is yours now",
                 f"{escape(session['user_name'])} handed over {escape(from_name)}'s work to you: {what}." + (f" Rollouts: <b>{names}</b>." if names else ""),
                 exclude_user_id=session["user_id"], link="/my-work")


@app.route("/users/<int:user_id>/capacity", methods=["POST"])
@permission_required("manage_users")
def user_set_capacity(user_id):
    """Hours a week this person can plan (People › Workload); blank takes the workspace default."""
    db = get_db()
    user = _user_or_404(db, user_id)
    raw = request.form.get("capacity_hours", "").strip()
    low, high = POLICIES["capacity_hours_per_week"]["min"], POLICIES["capacity_hours_per_week"]["max"]   # one's own limits are the default's
    try:
        hours = round(float(raw), 1) if raw else None
    except ValueError:
        hours = -1
    if hours is not None and not low <= hours <= high:
        flash(f"Capacity is between {low} and {high} hours a week; leave it blank for the default", "error")
        return redirect(url_for("users"))
    db.execute("UPDATE users SET capacity_hours = ? WHERE id = ?", (hours, user_id))
    db.commit()
    audit_log("set_user_capacity", "user", user_id, user["username"], f"capacity_hours={hours}")
    flash("Capacity saved" if hours else "Capacity back to the default")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/reset-password", methods=["POST"])
@permission_required("manage_users")
def user_reset_password(user_id):
    target = _user_or_404(get_db(), user_id)
    if target["kind"] == "external":
        flash("External accounts sign in by email link — nothing to reset", "error")
        return redirect(url_for("users"))
    if admin_only(target["role"]):
        flash("Only an admin can reset an admin's password", "error")
        return redirect(url_for("users"))
    new_password = request.form.get("new_password", "")
    problem = password_problem(new_password)
    if problem:
        flash(problem, "error")
        return redirect(url_for("users"))
    db = get_db()
    user = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    # A password the admin knows is a shared secret; the user replaces it on
    # their next login.
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 1, session_epoch = session_epoch + 1 WHERE id = ?",
        (generate_password_hash(new_password, method="pbkdf2:sha256"), user_id),
    )
    db.commit()
    audit_log("reset_user_password", "user", user_id, user["username"] if user else None)
    flash("Password reset")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/email", methods=["POST"])
@permission_required("manage_users")
def user_set_email(user_id):
    email = request.form.get("email", "").strip()
    if email and not valid_email(email):
        flash("Enter a valid email address", "error")
        return redirect(url_for("users"))
    db = get_db()
    user = _user_or_404(db, user_id)
    if admin_only(user["role"]):   # reset links go to this address
        flash("Only an admin can change an admin's email", "error")
        return redirect(url_for("users"))
    if email and _email_taken(db, email, user_id):
        flash("That address belongs to another account", "error")
        return redirect(url_for("users"))
    if (email or None) == user["email"] and user["email_verified_at"]:
        flash("Email unchanged")   # already confirmed: nothing to do
        return redirect(url_for("users"))
    # reset links go to the address: the old one's links and sessions end (test round P2-2).
    # The address is unproven until the person opens the link mailed to it (review P2-3);
    # saving the same unconfirmed address again sends a fresh link.
    db.execute("UPDATE users SET email = ?, email_verified_at = NULL, session_epoch = session_epoch + 1 WHERE id = ?", (email or None, user_id))
    db.commit()
    if user_id == session["user_id"]:   # an admin editing their own row carries on
        session["epoch"] = db.execute("SELECT session_epoch FROM users WHERE id = ?", (user_id,)).fetchone()[0]
    audit_log("set_user_email", "user", user_id, user["username"])
    flash("Email updated" + _verification_note(user_id, email))
    return redirect(url_for("users"))


def _verification_note(user_id, email):
    """Mail a staff account's new address its confirmation link (review P2-3);
    the words that follow "updated"/"created"."""
    from routes.auth import send_verification
    if not email or get_db().execute("SELECT kind FROM users WHERE id = ?", (user_id,)).fetchone()[0] != "internal":
        return ""
    if not send_verification(user_id):
        return ""   # mail is off: the person sees "not confirmed" on their Account page
    return ": they confirm the address from the link sent to it"
