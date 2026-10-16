"""Customer self-service (services/asks.py): what a rollout asks of its
outside parties, and their answers to a form. An external reads and answers
only their own asks; staff read every ask on the rollout with what came back.
A tick goes to the task toggle route, an upload to the documents route with
`ask_id`; both are opened only for the person the ask is on."""
from flask import abort, jsonify, session
from markupsafe import escape

from core import app, json_body, login_required, permission_required
from db import get_db, touch_project
from routes.projects import _tell_pm, load_project
from services import asks
from services.audit import audit_log


@app.route("/api/projects/<int:project_id>/asks")
@permission_required("view_project_detail")
def api_asks(project_id):
    load_project(project_id)
    external = session.get("kind") == "external"
    return jsonify({
        # an external: theirs alone (never another party's, never a team task); staff: every ask on the rollout
        "asks": asks.listing(project_id, session["user_id"] if external else None),
        "ratings": [] if external else asks.ratings(project_id),
    })


@app.route("/api/projects/<int:project_id>/asks/<int:task_id>/answers", methods=["POST"])
@login_required
def api_ask_answers(project_id, task_id):
    project = load_project(project_id)
    task = asks.own_ask(project_id, task_id, session["user_id"])
    if task is None or task["kind"] != "form":
        abort(404)
    if session.get("kind") == "external" and asks.limited(session["user_id"]):
        return jsonify(error="Too many changes in a minute; wait a moment"), 429
    body = json_body() or {}
    try:
        answers = asks.clean_answers(asks.questions(task), body.get("answers"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    db = get_db()
    asks.save_answers(db, task, answers, session["user_id"], session["user_name"])
    touch_project(db, project_id)
    db.commit()
    audit_log("complete_ask", "project", project_id, None, f"form: {task['title'][:80]} ({len(answers)} answers)")
    _tell_pm(project, f"Ask done on {escape(project['name'])}",
             f"{escape(session['user_name'])} answered <b>{escape(task['title'])}</b>.")
    return jsonify(ok=True)
