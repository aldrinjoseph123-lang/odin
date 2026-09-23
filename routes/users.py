"""User administration: create users, set role/active/email, reset passwords.
All gated on manage_users. Imported for route registration side effects.
"""
from datetime import datetime

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from constants import ROLES
from core import app, permission_required
from spa import spa_index, spa_serves
from db import get_db
from security import password_problem, valid_email
from services.audit import audit_log


@app.route("/users", methods=["GET", "POST"])
@permission_required("manage_users")
def users():
    if request.method == "GET" and spa_serves("users"):
        return spa_index()
    db = get_db()
    if request.method == "POST":
        username = request.form["username"].strip()
        name = request.form["name"].strip()
        email = request.form.get("email", "").strip()
        password = request.form["password"]
        role = request.form.get("role", "Member")
        if role not in ROLES:
            role = "Member"
        existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        problem = password_problem(password)
        if existing:
            flash("Username already exists")
        elif email and not valid_email(email):
            flash("Enter a valid email address")
        elif problem:
            flash(problem)
        else:
            cursor = db.execute(
                "INSERT INTO users (username, password_hash, name, role, active, email, created_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
                (username, generate_password_hash(password, method="pbkdf2:sha256"), name, role, email or None,
                 datetime.utcnow().isoformat()),
            )
            db.commit()
            audit_log("create_user", "user", cursor.lastrowid, username, f"role={role}")
            flash(f"User {name} created")
        return redirect(url_for("users"))
    all_users = db.execute("SELECT * FROM users ORDER BY name").fetchall()
    return render_template("users.html", users=all_users, ROLES=ROLES)


@app.route("/users/export.csv")
@permission_required("manage_users")
def users_export():
    """The access-review pack: every account, its role, when it was created,
    when it last signed in. Quarterly, an auditor asks for exactly this."""
    import csv
    import io
    from flask import Response
    rows = get_db().execute(
        "SELECT username, name, email, role, active, created_at, last_login_at FROM users ORDER BY username"
    ).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["username", "name", "email", "role", "active", "created_at", "last_login_at"])
    for r in rows:
        writer.writerow([r["username"], r["name"], r["email"], r["role"], r["active"], r["created_at"], r["last_login_at"]])
    audit_log("export_users", details=f"{len(rows)} accounts")
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=odin-users.csv"})


@app.route("/users/<int:user_id>/role", methods=["POST"])
@permission_required("manage_users")
def user_set_role(user_id):
    role = request.form.get("role", "")
    if role not in ROLES:
        flash("Invalid role")
        return redirect(url_for("users"))
    if user_id == session["user_id"] and role != "Admin":
        flash("You cannot remove your own Admin role")
        return redirect(url_for("users"))
    db = get_db()
    user = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    db.commit()
    audit_log("update_user_role", "user", user_id, user["username"], f"new_role={role}")
    flash("Role updated")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/active", methods=["POST"])
@permission_required("manage_users")
def user_set_active(user_id):
    if user_id == session["user_id"]:
        flash("You cannot deactivate your own account")
        return redirect(url_for("users"))
    active = 1 if request.form.get("active") == "1" else 0
    db = get_db()
    user = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    # Bumping the epoch ends any session this user currently has open.
    db.execute("UPDATE users SET active = ?, session_epoch = session_epoch + 1 WHERE id = ?", (active, user_id))
    db.commit()
    audit_log("set_user_active", "user", user_id, user["username"] if user else None, f"active={active}")
    flash("User updated")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/reset-password", methods=["POST"])
@permission_required("manage_users")
def user_reset_password(user_id):
    if get_db().execute("SELECT kind FROM users WHERE id = ?", (user_id,)).fetchone()["kind"] == "external":
        flash("External accounts sign in by email link — nothing to reset")
        return redirect(url_for("users"))
    new_password = request.form.get("new_password", "")
    problem = password_problem(new_password)
    if problem:
        flash(problem)
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
        flash("Enter a valid email address")
        return redirect(url_for("users"))
    db = get_db()
    user = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    db.execute("UPDATE users SET email = ? WHERE id = ?", (email or None, user_id))
    db.commit()
    audit_log("set_user_email", "user", user_id, user["username"] if user else None)
    flash("Email updated")
    return redirect(url_for("users"))
