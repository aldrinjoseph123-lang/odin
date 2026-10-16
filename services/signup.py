"""Sign-up links: an admin makes a link (a default role, optionally a project
and a project role, an expiry and a number of uses); a new colleague opens it,
fills in their name, username, email, password and preferred channel, and
waits as a pending account until an admin approves it (the Users page, as for
Microsoft sign-in requests). Approval activates the account and, when the link
named one, adds them to the project. Only a SHA-256 of the token is stored.
"""
import secrets
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from constants import PROJECT_MANAGER, PROJECT_ROLES, EXTERNAL_PROJECT_ROLES
from db import get_db
from policies import policy
from security import password_problem, token_hash, valid_email, valid_username

LINK_ROLES = ("Member", "Contributor", "Viewer")                                  # never Admin by link
PROJECT_LINK_ROLES = tuple(r for r in PROJECT_ROLES if r != PROJECT_MANAGER and r not in EXTERNAL_PROJECT_ROLES)
CHANNELS = ("email", "teams")



def create(label, role, project_id, project_role, days, max_uses, author):
    """Returns the raw token (shown once in the link)."""
    if not policy("signup_enabled"):
        raise ValueError("Sign-up links are switched off (Settings › Sign-up & activity)")
    label = (label or "").strip()[:80]
    if not label:
        raise ValueError("Name the link (e.g. who it is for)")
    if role not in LINK_ROLES:
        raise ValueError(f"The role is one of: {', '.join(LINK_ROLES)}")
    db = get_db()
    if project_id:
        if not db.execute("SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone():
            raise ValueError("That rollout does not exist")
        if project_role not in PROJECT_LINK_ROLES:
            raise ValueError(f"The rollout role is one of: {', '.join(PROJECT_LINK_ROLES)}")
    else:
        project_id, project_role = None, None
    try:   # test report FN-16: int()'s own error text reached the page
        days = max(1, min(90, int(days or policy("signup_days"))))
        max_uses = max(1, min(100, int(max_uses or 1)))
    except (TypeError, ValueError):
        raise ValueError("Days and uses are whole numbers") from None
    raw = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.execute("INSERT INTO signup_links (token_hash, label, role, project_id, project_role, max_uses, expires_at, created_by, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (token_hash(raw), label, role, project_id, project_role, max_uses, (now + timedelta(days=days)).isoformat(), author, now.isoformat()))
    db.commit()
    return raw


def links():
    rows = get_db().execute("SELECT l.*, p.name AS project FROM signup_links l LEFT JOIN projects p ON p.id = l.project_id ORDER BY l.id DESC LIMIT 100").fetchall()
    now = datetime.utcnow().isoformat()
    out = []
    for r in rows:
        state = "revoked" if r["revoked_at"] else "expired" if r["expires_at"] < now else "used up" if r["uses"] >= r["max_uses"] else "open"
        out.append({k: r[k] for k in ("id", "label", "role", "project_id", "project", "project_role", "max_uses", "uses", "expires_at", "created_by", "created_at")} | {"state": state})
    return out


def revoke(link_id):
    db = get_db()
    done = db.execute("UPDATE signup_links SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL", (datetime.utcnow().isoformat(), link_id)).rowcount
    db.commit()
    return bool(done)


def revoke_all():
    """Revoke every link still open; returns how many."""
    db = get_db()
    now = datetime.utcnow().isoformat()
    n = db.execute("UPDATE signup_links SET revoked_at = ? WHERE revoked_at IS NULL AND expires_at >= ? AND uses < max_uses", (now, now)).rowcount
    db.commit()
    return n


def trim(db=None):
    """Links that stopped working (revoked, expired or used up) more than 90 days ago."""
    from datetime import datetime, timedelta
    db = db or get_db()
    cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
    db.execute("DELETE FROM signup_links WHERE (revoked_at IS NOT NULL AND revoked_at < ?) OR expires_at < ? "
               "OR (uses >= max_uses AND created_at < ?)", (cutoff, cutoff, cutoff))
    db.commit()


def lookup(raw):
    """The open link for this token, or None (unknown, revoked, expired, used up, or sign-up switched off)."""
    if not policy("signup_enabled"):
        return None
    row = get_db().execute("SELECT l.*, p.name AS project FROM signup_links l LEFT JOIN projects p ON p.id = l.project_id WHERE token_hash = ?",
                           (token_hash(raw or ""),)).fetchone()
    if not row or row["revoked_at"] or row["expires_at"] < datetime.utcnow().isoformat() or row["uses"] >= row["max_uses"]:
        return None
    return row


def register(link, form):
    """Create the pending account; returns its id or raises ValueError with the reason."""
    if any(form.get(k) is not None and not isinstance(form.get(k), str) for k in ("name", "username", "email", "password", "notify_via")):
        raise ValueError("Send the form's fields as text")
    name = str(form.get("name") or "").strip()[:120]
    username = str(form.get("username") or "").strip()
    email = str(form.get("email") or "").strip().lower()[:200]
    password = str(form.get("password") or "")
    channel = "email"   # the Email/Teams choice went on 13 Oct (Teams follows the topic switches); the column stays for a rollback
    if not name:
        raise ValueError("Your full name")
    if not valid_username(username):   # ASCII, as on the Users page: no look-alike of an existing name (review P3-13)
        raise ValueError("A username of up to 64 letters (a-z), digits, dots, dashes, underscores or @")
    if not valid_email(email):
        raise ValueError("A valid email address")
    allowed = policy("signup_domains")
    if allowed and email.rsplit("@", 1)[-1] not in allowed:
        raise ValueError("That email domain is not accepted here; use your work address")
    if problem := password_problem(password):
        raise ValueError(problem)
    if channel not in CHANNELS:
        raise ValueError("Pick email or Teams")
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE lower(username) = ?", (username.lower(),)).fetchone():
        raise ValueError("That username is taken; pick another")
    if db.execute("SELECT 1 FROM users WHERE lower(email) = ?", (email,)).fetchone():
        raise ValueError("That address already has an account; ask an admin")
    # take the use first, guarded: two people on a single-use link at the same moment cannot both get in
    if not db.execute("UPDATE signup_links SET uses = uses + 1 WHERE id = ? AND uses < max_uses AND revoked_at IS NULL",
                      (link["id"],)).rowcount:
        raise ValueError("This sign-up link has just been used up. Ask the admin who sent it for a new one.")
    cur = db.execute(
        "INSERT INTO users (username, password_hash, name, role, active, email, created_at, kind, pending, theme, accent, notify_via, "
        "signup_link_id, signup_project_id, signup_project_role) VALUES (?, ?, ?, ?, 0, ?, ?, 'internal', 1, ?, ?, ?, ?, ?, ?)",
        (username, generate_password_hash(password, method="pbkdf2:sha256"), name, link["role"], email, datetime.utcnow().isoformat(),
         policy("default_theme"), policy("default_accent"), channel, link["id"], link["project_id"], link["project_role"]))
    db.commit()
    from routes.auth import send_verification
    send_verification(cur.lastrowid)   # the address is unproven until its link is opened (review P2-3)
    return cur.lastrowid


def on_approve(user):
    """Approval: join the project the link named (when it still exists)."""
    if not user["signup_project_id"]:
        return None
    db = get_db()
    p = db.execute("SELECT id, name FROM projects WHERE id = ? AND deleted_at IS NULL", (user["signup_project_id"],)).fetchone()
    if not p:
        return None
    db.execute("INSERT INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, ?, NULL, ?) "
               "ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
               (p["id"], user["id"], user["signup_project_role"] or "Coordinator", datetime.utcnow().isoformat()))
    db.commit()
    return p["name"]
