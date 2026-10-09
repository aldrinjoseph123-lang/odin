"""The lessons library and similar rollouts.

A lesson is a sentence a project manager saved from a rollout: something
that went wrong (avoid) or worked (repeat), with the evidence it came from.
Lessons outlive their rollout (db.py keeps them when a project is purged).

Similar rollouts are found by plain matching, not by the AI: the same
product counts 3, the same template 2, the same vendor 2, the same client 1;
a score of 3 or more is similar. For each, the page shows its saved lessons
and the risks that actually hit it (blockers, and high-impact issues and
risks), so the next rollout can log them on day one."""
from datetime import datetime

from db import get_db


def save(project, items, author):
    """Store the ticked lessons. items: [{kind, text, evidence}]. Returns how
    many. The caller commits, together with whatever else the save records."""
    db = get_db()
    n = 0
    for it in items:
        text = it.get("text").strip()[:400] if isinstance(it.get("text"), str) else ""
        kind = it.get("kind") if it.get("kind") in ("avoid", "repeat") else "avoid"
        if not text:
            continue
        db.execute("INSERT INTO lessons (project_id, project_name, template_id, product, vendor, client, kind, text, evidence, created_by, created_at) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (project["id"], project["name"], project["stage_template_id"], project["product_name"], project["vendor_name"], project["client"],
                    kind, text, (it.get("evidence").strip()[:400] if isinstance(it.get("evidence"), str) else "") or None, author, datetime.utcnow().isoformat()))
        n += 1
    return n


def of_project(project_id):
    return [dict(r) for r in get_db().execute("SELECT id, kind, text, evidence, created_by, created_at FROM lessons WHERE project_id = ? ORDER BY id", (project_id,))]


def similar(project, limit=3):
    """The most similar other rollouts, with their lessons and the risks that hit them."""
    db = get_db()
    weights = (("product_name", 3), ("stage_template_id", 2), ("vendor_name", 2), ("client", 1))
    scored = []
    for p in db.execute("SELECT * FROM projects WHERE deleted_at IS NULL AND id != ?", (project["id"],)).fetchall():
        score = sum(w for col, w in weights if project[col] and p[col] and str(project[col]).strip().lower() == str(p[col]).strip().lower())
        if score >= 3:
            scored.append((score, p["updated_at"] or "", p))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    out = []
    for score, _, p in scored:
        lessons = [dict(r) for r in db.execute("SELECT kind, text, evidence FROM lessons WHERE project_id = ? ORDER BY id", (p["id"],))]
        hit = [dict(r) for r in db.execute(
            "SELECT kind, title, impact, status, resolution FROM raid_items WHERE project_id = ? AND (kind = 'blocker' OR (kind IN ('issue', 'risk') AND impact = 'high')) "
            "ORDER BY id DESC LIMIT 5", (p["id"],))]
        if not lessons and not hit:
            continue
        why = [label for col, _w, label in (("product_name", 3, "same product"), ("stage_template_id", 2, "same template"), ("vendor_name", 2, "same vendor"),
                                           ("client", 1, "same client")) if project[col] and p[col] and str(project[col]).strip().lower() == str(p[col]).strip().lower()]
        out.append({"id": p["id"], "name": p["name"], "client": p["client"], "stage": p["stage"], "why": why, "lessons": lessons, "risks": hit})
        if len(out) >= limit:
            break
    return out
