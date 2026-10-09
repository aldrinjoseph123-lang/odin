"""Document templates (services/doc_templates.py): Settings → Documents for
admins, and the choice of template for everyone who writes a document."""
import json

from flask import Response, abort, jsonify, request, send_file, session

from core import app, as_id, json_body, text_field, login_required, permission_required
from services import doc_templates as dt
from services.audit import audit_log


def _kinds():
    return {k: {"label": v["label"], "sections": [{"key": a, "label": b} for a, b in v["sections"]],
                "texts": [{"key": a, "label": b, "help": c} for a, b, c in v["texts"]], "default": dt.default_config(k)} for k, v in dt.KINDS.items()}


@app.route("/api/doc-templates")
@permission_required("manage_settings")
def api_doc_templates():
    return jsonify(templates=dt.all_templates(), kinds=_kinds(), placeholders=dt.PLACEHOLDERS, accents=list(dt.ACCENTS))


@app.route("/api/doc-templates/choices")
@login_required
def api_doc_template_choices():
    """What a writer may pick for a document of this kind (names only)."""
    kind = request.args.get("kind", "")
    if kind not in dt.KINDS:
        abort(404)
    return jsonify(choices=[{"id": t["id"], "name": t["name"], "is_default": t["is_default"]} for t in dt.all_templates(kind)])


def _template_input(b, named=True):
    """(kind, name, config) — or (kind, config) — from a posted body, the
    shapes checked so the services see a string kind, a one-line name and a
    config object whose parts are of the right types (else ValueError)."""
    kind, config = b.get("kind"), b.get("config") or {}
    if not isinstance(kind, str) or not isinstance(config, dict):
        raise ValueError("Unknown document kind")
    for key, want in (("title", str), ("accent", str), ("logo", str), ("co_logo", str), ("company_line", str), ("footer", str), ("sections", list), ("texts", dict)):
        if config.get(key) is not None and not isinstance(config.get(key), want):
            raise ValueError(f"The template's {key.replace('_', ' ')} is not in the expected form")
    if not isinstance(config.get("texts") or {}, dict) or any(not isinstance(v, str) for v in (config.get("texts") or {}).values() if v is not None):
        raise ValueError("The template's texts are not in the expected form")
    return (kind, text_field(b.get("name"), 80, "Name"), config) if named else (kind, config)


@app.route("/api/doc-templates", methods=["POST"])
@permission_required("manage_settings")
def api_doc_template_create():
    b = json_body()
    try:
        tid = dt.save(*_template_input(b), session["user_name"])
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except KeyError:
        return jsonify(error="Unknown document kind"), 400
    audit_log("doc_template_create", "doc_template", tid, str(b.get("name") or "")[:80], b.get("kind"))
    return jsonify(ok=True, id=tid)


@app.route("/api/doc-templates/<int:template_id>", methods=["PUT", "DELETE"])
@permission_required("manage_settings")
def api_doc_template(template_id):
    if request.method == "DELETE":
        try:
            dt.delete(template_id)
        except LookupError:
            abort(404)
        audit_log("doc_template_delete", "doc_template", template_id)
        return jsonify(ok=True)
    b = json_body()
    try:
        dt.save(*_template_input(b), session["user_name"], template_id)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except (LookupError, KeyError):
        abort(404)
    audit_log("doc_template_update", "doc_template", template_id, str(b.get("name") or "")[:80])
    return jsonify(ok=True)


@app.route("/api/doc-templates/<int:template_id>/default", methods=["POST"])
@permission_required("manage_settings")
def api_doc_template_default(template_id):
    try:
        dt.make_default(template_id)
    except LookupError:
        abort(404)
    audit_log("doc_template_default", "doc_template", template_id)
    return jsonify(ok=True)


@app.route("/api/doc-templates/logo", methods=["POST"])
@permission_required("manage_settings")
def api_doc_template_logo():
    f = request.files.get("file")
    if not f:
        return jsonify(error="Choose an image"), 400
    try:
        name = dt.save_logo(f)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    audit_log("doc_template_logo", "doc_template", None, name)
    return jsonify(ok=True, name=name)


@app.route("/api/doc-templates/logo/<name>")
@login_required
def api_doc_template_logo_file(name):
    path = dt.logo_path(name)
    if not path:
        abort(404)
    return send_file(path, mimetype="image/png" if name.endswith(".png") else "image/jpeg", max_age=86400)


@app.route("/api/doc-templates/preview.pdf", methods=["POST"])
@permission_required("manage_settings")
def api_doc_template_preview():
    """The unsaved template on sample data: the newest open project (or the portfolio)."""
    b = json_body()
    kind = b.get("kind")
    try:
        cfg = dt.clean(*_template_input(b, named=False))
    except (ValueError, KeyError) as e:
        return jsonify(error=str(e)), 400
    return Response(_preview(kind, cfg), mimetype="application/pdf", headers={"Content-Disposition": 'inline; filename="preview.pdf"'})


def _preview(kind, cfg):
    from db import PROJECT_OPEN_SQL, get_db
    from services.report_pdf import render, render_portfolio
    db = get_db()
    if kind == "portfolio":
        from services import portfolio
        rows = db.execute(f"SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE {PROJECT_OPEN_SQL} AND p.deleted_at IS NULL").fetchall()
        return render_portfolio(portfolio.build(rows), cfg)
    project = db.execute("SELECT p.*, u.name AS owner_name FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.deleted_at IS NULL ORDER BY p.id DESC LIMIT 1").fetchone()
    if project is None:
        abort(409, "Create a project first: the preview uses one")
    if kind == "rollout":
        from services import report_data
        data = report_data.build(project, "internal")
        return render(data, data["draft"], cfg)
    # a sign-off: this project's draft, frozen with the template, unsigned
    from datetime import datetime
    from services import signoff
    from services.doc_templates import fill
    from services.signoff_pdf import render as render_signoff
    d = signoff.draft(project)
    values = signoff._values(project)
    content = {"template": cfg, "intro": fill(cfg["texts"].get("intro"), values).strip(), "closing": fill(cfg["texts"].get("closing"), values).strip(),
               "project": signoff._meta(project), "summary": d["summary"], "scope": [{k: x[k] for k in ("title", "detail", "status", "note")} for x in d["scope"]],
               "delivered": d["delivered"], "outstanding": d["outstanding"],
               "terms": [x for x in (cfg["texts"].get("terms") or "\n".join(d["terms"])).splitlines() if x.strip()],
               "statement": fill(cfg["texts"].get("statement"), values).strip() or d["statement"],
               "signer": {"name": "(the customer's signatory)", "email": "", "role": "Customer"}, "countersigner": {"name": project["owner_name"], "role": "Project manager"},
               "prepared_by": session["user_name"], "prepared_at": datetime.utcnow().isoformat()}
    v = {"version": 0, "status": "sent", "content_hash": signoff.fingerprint(content), "created_by": session["user_name"], "created_at": content["prepared_at"],
         "content": content, "intact": True, "signature": None, "counter_signature": None, "signer_name": None, "signer_title": None, "signer_email": "",
         "signed_at": None, "counter_name": None, "counter_title": None, "counter_signed_at": None, "reject_comment": None, "rejected_at": None,
         "document_id": None, "waiver_reason": None, "waived_by": None, "completed_at": None}
    return render_signoff(v)
