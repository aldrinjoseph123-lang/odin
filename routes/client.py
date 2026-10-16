"""What the browser tells the server about itself: the release it should be
running (the version on /api/session) and the errors it hit (advice A6, A20).
Registration side effects only."""
import json
import os
import time
from collections import deque
from functools import cache

from flask import request, session

from core import app, request_id
from security import CLIENT_REPORT_WINDOW_SECONDS, CLIENT_REPORTS_PER_WINDOW
from services.audit import _CONTROL

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@cache
def app_version():
    """The release this server runs (the VERSION file, read once: a release
    restarts the process); "" when it is missing."""
    try:
        with open(os.path.join(_HERE, "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return ""


REPORT_MAX_BYTES = 8 * 1024
# ponytail: per worker process, in memory (the ceiling is the limit × workers);
# kept out of the database so this unauthenticated door writes nothing but a log line.
_recent = {}


def _over_limit(who):
    now = time.monotonic()
    if len(_recent) > 1000:   # many callers at once: forget the old ones rather than grow
        _recent.clear()
    hits = _recent.setdefault(who, deque())
    while hits and now - hits[0] > CLIENT_REPORT_WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= CLIENT_REPORTS_PER_WINDOW:
        return True
    hits.append(now)
    return False


@app.route("/api/client-errors", methods=["POST"])
def api_client_errors():
    """A crash in someone's browser (a render error, an unhandled rejection),
    sent as a beacon. Sign-in optional; rate-limited per person or address;
    size-capped; logged with the request id, never stored or audited. CSRF-exempt
    (security._validate_csrf) because it changes nothing: a forged report is one
    more log line, and the limit caps those."""
    who = f"user:{session['user_id']}" if "user_id" in session else f"ip:{request.remote_addr}"
    if (request.content_length or 0) > REPORT_MAX_BYTES or _over_limit(who):
        return "", 204   # the browser does not read the answer: no reason to say more
    try:
        report = json.loads(request.get_data(cache=False)[:REPORT_MAX_BYTES] or b"{}")
    except ValueError:
        report = {}
    if not isinstance(report, dict):
        report = {}
    # one line per report in the log, and no control character (a forged ANSI escape or line break) reaches it
    clip = lambda k, n: _CONTROL.sub(" ", str(report.get(k) or "")[:n].replace("\n", " | "))   # noqa: E731
    app.logger.warning(
        "client error [%s] %s kind=%s path=%s version=%s: %s :: %s",
        request_id(), who, clip("kind", 20), clip("path", 200),
        clip("version", 20), clip("message", 500), clip("stack", 3000),
    )
    return "", 204
