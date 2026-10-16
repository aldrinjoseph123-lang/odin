"""What's new in this release (review B15), for staff.

The change log is built from git when the system map is regenerated
(scripts/build_system_map.py) and ships inside docs/system-map.html, which
admins open under Settings › System map & changes. Staff get a short cut of
it: the subjects of the release's commits that changed the app (server or
screens), never the tests, tooling, docs or deployment, and never a file
path. Each person dismisses it once per release (users.whats_new_seen).
"""
import json
import os
import re
from functools import lru_cache

MAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "system-map.html")
SHOWN_AREAS = ("Server", "Screens")
SKIP = re.compile(r"^(Version \d|System map|Docs?:|Tests?:|CI:|Merge )", re.I)
PATHISH = re.compile(r"\s*\(?\b[\w.-]*/[\w./-]*\)?|\s*\b[\w-]+\.(py|tsx?|jsx?|md|sh|json|sql|html|ya?ml|css)\b")
MAX_ITEMS = 12


@lru_cache(maxsize=1)
def _changelog(path=MAP):
    """The change log in the map shipped with this release ({} when missing): read once, a release restarts the process."""
    try:
        with open(path, encoding="utf-8") as f:
            page = f.read()
    except OSError:
        return {}
    m = re.search(r'<script type="application/json" id="repo-data">(.*?)</script>', page, re.S)
    try:
        return json.loads(m.group(1)).get("changelog") or {} if m else {}
    except ValueError:
        return {}


def clean(subject):
    """A commit subject a member of staff may read: no file paths."""
    return re.sub(r"\s{2,}", " ", PATHISH.sub("", subject or "")).strip(" :;,-")


def summary(version, log=None):
    """{version, title, items} for this release, or None when there is nothing to say."""
    log = _changelog() if log is None else log
    rel = next((r for r in log.get("releases") or [] if r.get("version") == f"v{version}"), None)
    if not version or rel is None:
        return None
    items = []
    for c in rel.get("commits") or []:
        text = clean(c.get("subject"))
        if c.get("area") in SHOWN_AREAS and text and not SKIP.match(c.get("subject") or "") and text not in items:
            items.append(text)
    return {"version": version, "title": rel.get("title") or "", "items": items[:MAX_ITEMS]} if items else None
