"""Workload (services/workload.py): the People › Workload page, its data and the
week's hours the task picker shows. Staff who may view People; partners get a 403.
Reads only: the per-person capacity is set on the Users page (routes/users.py)."""
from datetime import date

from flask import abort, jsonify, request, session

from core import app, permission_required
from policies import local_today
from services import workload
from spa import spa_index


def _staff_only():
    if session.get("kind") == "external":
        abort(403)


@app.route("/people/workload")
@permission_required("view_board")
def workload_page():
    _staff_only()
    return spa_index()


@app.route("/api/workload")
@permission_required("view_board")
def api_workload():
    _staff_only()
    return jsonify(workload.build())


@app.route("/api/workload/week")
@permission_required("view_board")
def api_workload_week():
    """Each person's hours in the week holding ?date= (default: this week)."""
    _staff_only()
    try:
        day = date.fromisoformat(request.args["date"][:10]) if request.args.get("date") else local_today()
    except ValueError:
        return jsonify(error="Send the date as YYYY-MM-DD"), 400
    return jsonify(workload.week_of(day))
