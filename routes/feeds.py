"""The personal calendar feed (review B13; services/ics.py).

GET /feeds/calendar/<token>.ics needs no session and changes nothing, so it
needs no CSRF token: the token in the address is the whole credential, read
only, and stored hashed. Reads are limited per feed (policy
ics_feed_per_hour). The Account page makes, rotates and turns off the feed;
each is audited, and the address is shown once.
"""
from flask import Response, abort, jsonify, session

from core import app, login_required, public_base
from db import get_db
from policies import policy
from security import rate_limited, token_hash
from services import ics
from services.audit import audit_log


@app.route("/feeds/calendar/<token>.ics")
def calendar_feed(token):
    if rate_limited(f"ics:{token_hash(token)[:24]}", policy("ics_feed_per_hour"), 60, any_ip=True):
        return Response("Too many reads of this feed this hour.\n", status=429, mimetype="text/plain", headers={"Retry-After": "3600"})
    user = ics.owner_of(token)
    if user is None:
        abort(404)
    return Response(ics.build(user["id"], public_base()), mimetype="text/calendar",
                    headers={"Content-Disposition": 'inline; filename="odin.ics"', "Cache-Control": "private, no-store"})


@app.route("/account/calendar", methods=["POST"])
@login_required
def account_calendar():
    """Make the feed, or rotate it (the old address stops working at once). Staff only."""
    if session.get("kind") == "external":
        abort(403)
    db = get_db()
    had = db.execute("SELECT ics_token_hash FROM users WHERE id = ?", (session["user_id"],)).fetchone()[0]
    raw = ics.mint(session["user_id"])
    db.commit()
    audit_log("rotate_calendar_feed" if had else "create_calendar_feed", "user", session["user_id"], session.get("user_name"))
    return jsonify(ok=True, url=f"{public_base()}/feeds/calendar/{raw}.ics")


@app.route("/account/calendar/off", methods=["POST"])
@login_required
def account_calendar_off():
    ics.revoke(session["user_id"])
    get_db().commit()
    audit_log("revoke_calendar_feed", "user", session["user_id"], session.get("user_name"))
    return jsonify(ok=True)
