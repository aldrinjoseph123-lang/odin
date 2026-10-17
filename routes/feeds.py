"""The personal calendar feed (review B13; services/ics.py).

GET /feeds/calendar/<token>.ics needs no session and changes nothing, so it
needs no CSRF token: the token in the address is the whole credential, read
only, and stored hashed. Reads are limited per feed (policy
ics_feed_per_hour). The Account page makes, rotates and turns off the feed;
each is audited, and the address is shown once.
"""
from flask import Response, abort, jsonify, session

from core import app, login_required, public_base, staff_required
from db import get_db
from policies import policy
from security import rate_limited
from services import ics
from services.audit import audit_log


@app.route("/feeds/calendar/<token>.ics")
def calendar_feed(token):
    # the token first: an unknown one is throttled per address (ics_feed_per_hour wrong guesses an hour),
    # so a stream of made-up tokens writes at most that many rows, never one per request
    user = ics.owner_of(token)
    if user is None:
        if rate_limited("ics-miss", policy("ics_feed_per_hour"), 60):
            return Response("Too many reads of this feed this hour.\n", status=429, mimetype="text/plain", headers={"Retry-After": "3600"})
        abort(404)
    if rate_limited(f"ics:{user['id']}", policy("ics_feed_per_hour"), 60, any_ip=True):
        return Response("Too many reads of this feed this hour.\n", status=429, mimetype="text/plain", headers={"Retry-After": "3600"})
    body = ics.build(user["id"], public_base())
    ics.touch(user["id"])   # a feed nobody reads switches itself off (policy ics_idle_days, the nightly housekeeping)
    return Response(body, mimetype="text/calendar",
                    headers={"Content-Disposition": 'inline; filename="odin.ics"', "Cache-Control": "private, no-store"})


@app.route("/account/calendar", methods=["POST"])
@login_required
@staff_required
def account_calendar():
    """Make the feed, or rotate it (the old address stops working at once). Staff only."""
    db = get_db()
    had = db.execute("SELECT ics_token_hash FROM users WHERE id = ?", (session["user_id"],)).fetchone()[0]
    raw = ics.mint(session["user_id"])
    db.commit()
    audit_log("rotate_calendar_feed" if had else "create_calendar_feed", "user", session["user_id"], session.get("user_name"))
    return jsonify(ok=True, url=f"{public_base()}/feeds/calendar/{raw}.ics")


@app.route("/account/calendar/off", methods=["POST"])
@login_required
@staff_required   # as the feed itself: nothing to turn off, nothing to audit
def account_calendar_off():
    ics.revoke(session["user_id"])
    get_db().commit()
    audit_log("revoke_calendar_feed", "user", session["user_id"], session.get("user_name"))
    return jsonify(ok=True)
