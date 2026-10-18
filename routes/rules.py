"""Settings › Automations (services/rules.py): the rules, their run logs, pause
and resume, and the dry run. Every route needs manage_rules (Admin by
default). The request hooks below hold a request's firings until the request
is done, so a rule acts on the user's change whole and committed."""

from flask import abort, g, jsonify, session

from core import app, json_body, permission_required
from policies import policy
from services import rules
from services.audit import audit_log
from spa import spa_index


@app.before_request
def _rules_queue():
    g.rules_later = []


@app.after_request
def _rules_run(response):
    if response.status_code >= 500:   # the request failed part-way: its firings go, and so do its uncommitted writes
        g.pop("rules_later", None)
        rules.discard_uncommitted()
        return response
    rules.flush()   # never raises: a rule's failure is in its run log, not in the user's answer
    return response


@app.route("/settings/automations")
@permission_required("manage_rules")
def settings_automations():
    return spa_index()


def _said(d):
    return f"when {d['event']}; {len(d['conditions'])} conditions; " + ", ".join(a["kind"] for a in d["actions"])


@app.route("/api/rules")
@permission_required("manage_rules")
def api_rules():
    return jsonify(rules=rules.listing(), max=policy("rules_max"), keep_days=policy("rule_runs_keep_days"), **rules.catalogue())


@app.route("/api/rules", methods=["POST"])
@permission_required("manage_rules")
def api_rule_create():
    try:
        d = rules.clean(json_body())
        rid = rules.create(d, session["user_name"])
    except ValueError as e:
        return jsonify(error=str(e)), 400
    audit_log("create_rule", "rule", rid, d["name"], _said(d))
    return jsonify(ok=True, id=rid)


def _rule(rule_id):
    r = rules.get(rule_id)
    if r is None:
        abort(404)
    return r


@app.route("/api/rules/<int:rule_id>", methods=["PUT"])
@permission_required("manage_rules")
def api_rule_update(rule_id):
    _rule(rule_id)
    try:
        d = rules.clean(json_body())
    except ValueError as e:
        return jsonify(error=str(e)), 400
    rules.update(rule_id, d)
    audit_log("update_rule", "rule", rule_id, d["name"], _said(d))
    return jsonify(ok=True)


@app.route("/api/rules/<int:rule_id>/pause", methods=["POST"])
@permission_required("manage_rules")
def api_rule_pause(rule_id):
    r = _rule(rule_id)
    paused = json_body().get("paused")
    if not isinstance(paused, bool):
        return jsonify(error="Send paused as true or false"), 400
    rules.set_paused(rule_id, paused)
    audit_log("pause_rule" if paused else "resume_rule", "rule", rule_id, r["name"])
    return jsonify(ok=True)


@app.route("/api/rules/<int:rule_id>", methods=["DELETE"])
@permission_required("manage_rules")
def api_rule_delete(rule_id):
    r = _rule(rule_id)
    rules.delete(rule_id)
    audit_log("delete_rule", "rule", rule_id, r["name"], f"when {r['event']}")
    return jsonify(ok=True)


@app.route("/api/rules/<int:rule_id>/runs")
@permission_required("manage_rules")
def api_rule_runs(rule_id):
    _rule(rule_id)
    return jsonify(runs=rules.runs(rule_id), keep_days=policy("rule_runs_keep_days"))


@app.route("/api/rules/dry-run", methods=["POST"])
@permission_required("manage_rules")
def api_rule_dry_run():
    """A rule as the editor holds it (saved or not) against the last 30 days. Sends nothing, changes nothing."""
    try:
        d = rules.clean(json_body())
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(rules.dry_run(d))   # a read: unaudited (test_app's meta-test lists it as read-only)
