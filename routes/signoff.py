"""The scope register and the sign-off document (services/signoff.py): the
page, its JSON, the signatures, the scanned-copy fallback, the admin's
waiver and the PDF. Every route goes through load_project; mutations are
audited; signing is decided by who the version names, not by role."""
from datetime import datetime

from flask import Response, abort, jsonify, request, session
from markupsafe import escape

import graph
from constants import SIGNOFF_DOC_CATEGORY
from core import admin_required, app, as_id, json_body, external_url, login_required, permission_required, project_allows, project_role_required, sees_po
from db import get_db, get_setting
from routes.projects import load_project, save_document
from policies import policy
from security import content_matches_extension, file_stem, issue_login_link, upload_problem
from services import signoff
from services.audit import audit_log
from services.notifications import notify_users
from spa import spa_index


def _staff():
    return session.get("kind") != "external"


def _partner_cut(project_id, row):
    """A partner or contractor reads a sign-off without the PO, the partner
    channel, the signatory's email and the signatures, unless they are the one
    asked to sign it (they sign the whole document). Staff and the Customer read it all."""
    return not sees_po(project_id) and row["signer_id"] != session.get("user_id")


def _link(project_id):
    return f"/projects/{project_id}/signoff"


def _body():
    return json_body()


def _bad(error, status=400):
    return jsonify(error=str(error)), status


# ---- the page --------------------------------------------------------------------

@app.route("/projects/<int:project_id>/signoff")
@permission_required("view_project_detail")
def project_signoff(project_id):
    load_project(project_id)
    return spa_index()


@app.route("/api/projects/<int:project_id>/signoff")
@permission_required("view_project_detail")
def api_signoff(project_id):
    project = load_project(project_id)
    rows = signoff.versions(project_id)
    wanted = request.args.get("v", type=as_id)
    row = next((r for r in rows if r["version"] == wanted), None) if wanted else (rows[0] if rows else None)
    if wanted and row is None:
        abort(404)
    manage = project_allows(project_id, "manage_project")
    st = signoff.state(project)
    me = session["user_id"]
    out = {
        "project": {"id": project["id"], "name": project["name"], "client": project["client"], "stage": project["stage"], "owner_id": project["owner_id"]},
        "state": st,
        # why it cannot be sent from this stage yet (None: it can), shown before anyone fills the form in (sim roles-8)
        "not_yet": signoff.sendable(project) if manage and not st["complete"] else None,
        "versions": [{"version": r["version"], "status": r["status"], "created_at": r["created_at"], "created_by": r["created_by"]} for r in rows],
        "current": signoff.view(row, _staff(), _partner_cut(project_id, row)) if row else None,
        "can": {
            "manage": manage and not st["complete"],
            "sign": bool(row) and row["status"] == "sent" and row["signer_id"] == me,
            "countersign": bool(row) and row["status"] == "signed" and _staff() and (row["counter_id"] == me or session.get("role") == "Admin"),
            "upload": manage and bool(row) and row["status"] in signoff.OPEN,
            "withdraw": manage and bool(row) and row["status"] in signoff.OPEN,
            "waive": session.get("role") == "Admin" and not st["complete"],
        },
        "me": {"name": session.get("user_name")},
    }
    if manage and not st["complete"]:
        signers, counters = signoff.candidates(project_id)
        out["draft"] = signoff.draft(project, request.args.get("template", type=as_id))
        out["candidates"] = {"signers": [{k: s[k] for k in ("id", "name", "role", "email")} for s in signers],
                             "countersigners": [{k: s[k] for k in ("id", "name", "role")} for s in counters],
                             "default_counter_id": project["owner_id"] if any(c["id"] == project["owner_id"] for c in counters) else (counters[0]["id"] if counters else None)}
    return jsonify(out)


# ---- scope -------------------------------------------------------------------------

def _scope_locked(project_id):
    """Why the scope cannot change now, or None: it is final once signed off,
    and frozen while a version is out for signature (L12) — withdraw it first."""
    if signoff.completed(project_id):
        return "The rollout is signed off; its scope is final"
    last = signoff.latest(project_id)
    if last and last["status"] in signoff.OPEN:
        return f"Version {last['version']} of the sign-off is out for signature; withdraw it before changing the scope"
    return None


@app.route("/api/projects/<int:project_id>/scope")
@permission_required("view_project_detail")
def api_scope(project_id):
    load_project(project_id)
    return jsonify(items=signoff.scope(project_id), statuses=list(signoff.SCOPE_STATUSES),
                   can_edit=project_allows(project_id, "manage_project") and not signoff.completed(project_id))


@app.route("/api/projects/<int:project_id>/scope", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def api_scope_add(project_id):
    project = load_project(project_id)
    if locked := _scope_locked(project_id):
        return _bad(locked, 409)
    try:
        fields = signoff.clean_scope(_body())
    except ValueError as e:
        return _bad(e)
    item_id = signoff.add_scope(project_id, fields, session["user_name"])
    audit_log("add_scope_item", "project", project_id, project["name"], fields["title"])
    return jsonify(ok=True, id=item_id)


@app.route("/api/projects/<int:project_id>/scope/<int:item_id>", methods=["PUT", "DELETE"])
@permission_required("edit_project")
@project_role_required("manage_project")
def api_scope_item(project_id, item_id):
    project = load_project(project_id)
    if locked := _scope_locked(project_id):
        return _bad(locked, 409)
    db = get_db()
    item = db.execute("SELECT * FROM scope_items WHERE id = ? AND project_id = ?", (item_id, project_id)).fetchone()
    if item is None:
        abort(404)
    if request.method == "DELETE":
        db.execute("DELETE FROM scope_items WHERE id = ?", (item_id,))
        db.commit()
        audit_log("delete_scope_item", "project", project_id, project["name"], item["title"])
        return jsonify(ok=True)
    body = _body()
    if body.get("move") in (-1, 1):
        signoff.move_scope(project_id, item_id, body["move"])
        audit_log("move_scope_item", "project", project_id, project["name"], item["title"])
        return jsonify(ok=True)
    try:
        fields = signoff.clean_scope(body, item)
    except ValueError as e:
        return _bad(e)
    signoff.update_scope(item_id, fields)
    audit_log("edit_scope_item", "project", project_id, project["name"], f"{fields['title']}: {fields['status']}")
    return jsonify(ok=True)


# ---- the document ----------------------------------------------------------------------

@app.route("/api/projects/<int:project_id>/signoff", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def api_signoff_send(project_id):
    project = load_project(project_id)
    suggestion = _body().get("ai_suggestion")
    if suggestion is not None and (not isinstance(suggestion, int) or isinstance(suggestion, bool)):
        return _bad("ai_suggestion is the id of an AI draft")   # checked before anything is written (F-M7)
    from routes.ai import use_suggestion
    try:
        row = signoff.send(project, _body(), session["user_name"], commit=False)
        ai = use_suggestion(project_id, suggestion, "signoff_summary")
    except ValueError as e:
        get_db().rollback()
        return _bad(e)
    get_db().commit()   # the version and the draft it used, together
    audit_log("signoff_send", "project", project_id, project["name"], f"v{row['version']} to {row['signer_email']} sha256={row['content_hash'][:16]}{ai}")
    notify_users([row["signer_id"]], "approval", project_id, f"Please review and sign off {project['name']}",
                 f"<p>{escape(session['user_name'])} has sent the sign-off for <b>{escape(project['name'])}</b> (version {row['version']}). "
                 "It lists what was delivered against the agreed scope. Please review it, then sign — or say what needs to change.</p>",
                 exclude_user_id=session["user_id"], link=_link(project_id))
    return jsonify(ok=True, version=row["version"])


def _version(project_id, version):
    row = signoff.get(project_id, version)
    if row is None:
        abort(404)
    return row


def _completed_mail(project, row):
    """The signed PDF to both signatories, when mail is on."""
    if get_setting("notify_email_enabled") != "1":
        return
    from services.signoff_pdf import render
    signed = signoff.get(project["id"], row["version"])
    # the signing record (addresses, browsers) is for staff: the customer's copy leaves it out
    pdfs = {True: render(signoff.view(signed, True)), False: render(signoff.view(signed, False))}
    db = get_db()
    staff = {r["email"] for r in db.execute("SELECT email FROM users WHERE id IN (?, ?) AND email IS NOT NULL", (row["counter_id"], project["owner_id"]))}
    to = {row["signer_email"]} | staff
    for address in sorted(x for x in to if x):
        pdf = pdfs[address in staff]
        try:
            graph.send_mail(address, f"Signed off: {project['name']}", f"<p>The sign-off for <b>{escape(project['name'])}</b> is signed by both sides. The signed copy is attached.</p>",
                            attachments=[(f"signoff-{project['id']}-v{row['version']}.pdf", pdf, "application/pdf")])
        except Exception as exc:   # mail never breaks the request
            app.logger.warning("sign-off mail to %s failed: %s", address, exc)


@app.route("/api/projects/<int:project_id>/signoff/<int:version>/sign", methods=["POST"])
@login_required
def api_signoff_sign(project_id, version):
    project = load_project(project_id)
    row = _version(project_id, version)
    if row["signer_id"] != session["user_id"]:
        abort(403)
    try:
        signoff.sign(row, _body(), request.remote_addr, request.headers.get("User-Agent"))
    except ValueError as e:
        return _bad(e)
    audit_log("signoff_sign", "project", project_id, project["name"], f"v{version} signed by {session['user_name']}")
    notify_users([row["counter_id"], project["owner_id"]], "approval", project_id, f"{project['name']}: the customer has signed the sign-off",
                 f"<p>{escape(session['user_name'])} signed version {version} of the sign-off for <b>{escape(project['name'])}</b>. It now needs our countersignature.</p>",
                 exclude_user_id=session["user_id"], link=_link(project_id))
    return jsonify(ok=True)


@app.route("/api/projects/<int:project_id>/signoff/<int:version>/countersign", methods=["POST"])
@login_required
def api_signoff_countersign(project_id, version):
    project = load_project(project_id)
    row = _version(project_id, version)
    if not _staff() or (row["counter_id"] != session["user_id"] and session.get("role") != "Admin"):
        abort(403)
    try:
        signoff.countersign(row, _body(), request.remote_addr, request.headers.get("User-Agent"))
    except ValueError as e:
        return _bad(e)
    audit_log("signoff_countersign", "project", project_id, project["name"], f"v{version} countersigned by {session['user_name']}")
    ids = [r[0] for r in get_db().execute("SELECT user_id FROM project_participants WHERE project_id = ?", (project_id,))]
    notify_users(ids, "approval", project_id, f"{project['name']} is signed off",
                 f"<p>The sign-off for <b>{escape(project['name'])}</b> is signed by the customer and countersigned. The rollout can now close.</p>",
                 exclude_user_id=session["user_id"], link=_link(project_id))
    _completed_mail(project, row)
    return jsonify(ok=True)


@app.route("/api/projects/<int:project_id>/signoff/<int:version>/reject", methods=["POST"])
@login_required
def api_signoff_reject(project_id, version):
    project = load_project(project_id)
    row = _version(project_id, version)
    if row["signer_id"] != session["user_id"]:
        abort(403)
    try:
        signoff.reject(project, row, _body().get("comment"), session["user_name"])
    except ValueError as e:
        return _bad(e)
    audit_log("signoff_reject", "project", project_id, project["name"], f"v{version} not accepted")
    notify_users([project["owner_id"], row["counter_id"]], "approval", project_id, f"{project['name']}: the sign-off was not accepted",
                 f"<p>{escape(session['user_name'])} did not sign version {version}: {escape(_body().get('comment') or '')}</p><p>It is now an open issue on the rollout; send a new version once it is resolved.</p>",
                 exclude_user_id=session["user_id"], link=_link(project_id))
    return jsonify(ok=True)


@app.route("/api/projects/<int:project_id>/signoff/<int:version>/link", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def api_signoff_link(project_id, version):
    """A one-time sign-in link for the signatory, landing on the sign-off: for
    when mail is not connected, or the email went astray. Carried by hand —
    but only for a signatory on this project alone: an account that is on
    other projects too gets the link by email, never in this reply, or the
    project manager could act as that person elsewhere."""
    project = load_project(project_id)
    row = _version(project_id, version)
    if row["status"] != "sent":
        return _bad("Only a version waiting for the customer's signature needs their link")
    db = get_db()
    signer = db.execute("SELECT * FROM users WHERE id = ?", (row["signer_id"],)).fetchone()
    raw = issue_login_link(row["signer_id"], session["user_id"])
    if signer is None or signer["kind"] != "external" or db.execute(
            "SELECT 1 FROM project_participants WHERE user_id = ? AND project_id != ?", (row["signer_id"], project_id)).fetchone():
        from routes.auth import send_login_link
        sent, _error = send_login_link(signer, raw, session["user_name"], project["name"], project_id) if signer else (False, None)
        audit_log("signoff_link", "project", project_id, project["name"], f"v{version} sign-in link for {row['signer_email']} {'emailed' if sent else 'not sent'}")
        return jsonify(ok=True, link=None, emailed=sent, minutes=policy("link_minutes"), email=row["signer_email"],
                       message=f"A sign-in link was emailed to {row['signer_email']}" if sent else
                       f"Email could not be sent; {row['signer_email']} can ask for a sign-in link on the sign-in page")
    link = external_url("auth_link_consume", token=raw, next=_link(project_id))
    # disclosed on the signing record: the signatory's sign-in came by hand from this person
    db.execute("UPDATE signoffs SET link_issued_by = ?, link_issued_at = ? WHERE id = ?", (session["user_name"], datetime.utcnow().isoformat(), row["id"]))
    db.commit()
    audit_log("signoff_link", "project", project_id, project["name"], f"v{version} sign-in link for {row['signer_email']}")
    return jsonify(ok=True, link=link, minutes=policy("link_minutes"), email=row["signer_email"])


@app.route("/api/projects/<int:project_id>/signoff/<int:version>/withdraw", methods=["POST"])
@permission_required("edit_project")
@project_role_required("manage_project")
def api_signoff_withdraw(project_id, version):
    project = load_project(project_id)
    try:
        signoff.withdraw(_version(project_id, version))
    except ValueError as e:
        return _bad(e)
    audit_log("signoff_withdraw", "project", project_id, project["name"], f"v{version}")
    row = signoff.get(project_id, version)
    if row and row["signer_id"]:
        notify_users([row["signer_id"]], "approval", project_id, f"{project['name']}: the sign-off was withdrawn",
                     f"Version {version} of the sign-off for <b>{escape(project['name'])}</b> was withdrawn and will be revised; nothing to sign for now.",
                     link=f"/projects/{project_id}/signoff")
    return jsonify(ok=True)


@app.route("/api/projects/<int:project_id>/signoff/<int:version>/upload", methods=["POST"])
@permission_required("upload_document")
@project_role_required("manage_project")
def api_signoff_upload(project_id, version):
    """The paper route: the customer printed the PDF, signed it, sent it back."""
    project = load_project(project_id)
    row = _version(project_id, version)
    file = request.files.get("file")
    name = request.form.get("signer_name", "").strip()[:120]
    signed_on = request.form.get("signed_on", "").strip()[:10]
    if not file or not file.filename:
        return _bad("Choose the signed copy")
    if not name or len(signed_on) != 10:
        return _bad("Who signed it, and on what date")
    try:
        datetime.strptime(signed_on, "%Y-%m-%d")
    except ValueError:
        return _bad("The signing date must be a date (YYYY-MM-DD)")
    from policies import local_date, local_today
    if signed_on > local_today().isoformat() or signed_on < local_date(row["created_at"]).isoformat():   # L19
        return _bad("The signing date is between the day the version was sent and today")
    if problem := upload_problem(file):
        return _bad(problem)
    if not content_matches_extension(file):
        return _bad("That file's contents don't match its extension")
    if row["status"] not in signoff.OPEN:
        return _bad("Upload the signed copy of a version that is waiting for signatures")
    original, doc_id = save_document(project_id, file, SIGNOFF_DOC_CATEGORY, session["user_name"])   # by id, never by name (P3-29)
    try:
        signoff.record_upload(row, doc_id, name, request.form.get("signer_title", "").strip()[:120], signed_on)
    except ValueError as e:   # completed or withdrawn by another request meanwhile; the file stays among the documents
        return _bad(e)
    audit_log("signoff_upload", "project", project_id, project["name"], f"v{version} signed copy {original}, signed by {name} on {signed_on}")
    ids = [r[0] for r in get_db().execute("SELECT user_id FROM project_participants WHERE project_id = ?", (project_id,))]
    notify_users(ids, "approval", project_id, f"{project['name']} is signed off",
                 f"<p>The signed copy of the sign-off for <b>{escape(project['name'])}</b> was uploaded. The rollout can now close.</p>",
                 exclude_user_id=session["user_id"], link=_link(project_id))
    return jsonify(ok=True)


@app.route("/api/projects/<int:project_id>/signoff/waive", methods=["POST"])
@admin_required
def api_signoff_waive(project_id):
    project = load_project(project_id)
    try:
        row = signoff.waive(project, _body().get("reason"), session["user_name"])
    except ValueError as e:
        return _bad(e)
    audit_log("signoff_waive", "project", project_id, project["name"], f"v{row['version']}: {row['waiver_reason']}")
    notify_users([project["owner_id"]], "approval", project_id, f"{project['name']}: sign-off waived",
                 f"<p>{escape(session['user_name'])} waived the sign-off: {escape(row['waiver_reason'])}</p>", exclude_user_id=session["user_id"], link=_link(project_id))
    return jsonify(ok=True, version=row["version"])


@app.route("/projects/<int:project_id>/signoff.pdf")
@permission_required("view_project_detail")
def signoff_pdf(project_id):
    from services.signoff_pdf import render
    project = load_project(project_id)
    v = request.args.get("v", type=as_id)
    row = signoff.get(project_id, v) if v else signoff.latest(project_id)
    if row is None:
        abort(404)
    safe = file_stem(project["name"])
    audit_log("download_signoff", "project", project_id, project["name"], f"v{row['version']}")   # an export like the others (P3-17)
    return Response(render(signoff.view(row, _staff(), _partner_cut(project_id, row))), mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{safe}-signoff-v{row["version"]}.pdf"'})
