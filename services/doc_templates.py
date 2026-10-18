"""Document templates: how the rollout report, the portfolio report and the
sign-off look and read (Settings › Documents).

A template carries a brand (our logo, an optional customer co-brand logo, an
accent colour, a company line and a footer), which sections appear and in
what order, and text blocks with placeholders such as {client} and {project}.
Each kind has one default; the project manager can pick another per document.
Without any saved template the built-in default applies, which is exactly
the document as it was before templates existed.

A saved report version and a sent sign-off freeze the template they used (the
sign-off inside its fingerprinted content), so a later edit never changes a
document already issued. Logos live in DATA_DIR/brand (backed up with it).
"""
import json
import os
import re
import uuid
from datetime import datetime

import db as _db
from db import get_db

KINDS = {
    "rollout": {
        "label": "Rollout report", "title": "Rollout report",
        "sections": [("numbers", "Health and key numbers"), ("summary", "Summary, next steps, asks"), ("timeline", "Timeline and stage table"),
                     ("raid", "Risks, issues, decisions, blockers"), ("work", "Work, people and open tasks"), ("history", "Stage history and approvals"),
                     ("plan_changes", "What moved in the plan (internal)"), ("notes", "Notes"),
                     ("asks", "Asks of the customer and their rating (internal)"), ("team", "Team")],
        "texts": [("intro", "Opening text", "Printed under the title."), ("closing", "Closing text", "Printed at the end, e.g. contacts or a disclaimer.")],
    },
    "portfolio": {
        "label": "Portfolio report", "title": "Portfolio report",
        "sections": [("health", "Health mix and key numbers"), ("roadmap", "Roadmap"), ("slippage", "Slippage"), ("risks", "Blockers and high-impact risks"), ("table", "Every rollout")],
        "texts": [("intro", "Opening text", "Printed under the title."), ("closing", "Closing text", "Printed at the end.")],
    },
    "signoff": {
        "label": "Sign-off", "title": "Rollout sign-off",
        "sections": [("facts", "Rollout facts"), ("summary", "Summary"), ("scope", "Scope and what was delivered"), ("outstanding", "Outstanding items"),
                     ("terms", "Handover and support")],
        "texts": [("intro", "Opening text", "Printed under the title."), ("statement", "Acceptance statement", "What the customer signs under. Blank: the workspace's (Settings › Workflow)."),
                  ("terms", "Handover and support terms", "One point per line. Blank: the workspace's."), ("closing", "Closing text", "Printed before the signatures.")],
    },
}
PLACEHOLDERS = {"project": "the project's name", "client": "the customer", "company": "your company", "pm": "the project manager",
                "po": "the PO number", "stage": "the current stage", "target": "the target date", "forecast": "the forecast finish", "date": "today",
                "field:Name": "a custom field marked for customers, by its name (Settings › Rollouts & workflow)"}
ACCENTS = {"blue": (61, 90, 254), "indigo": (79, 70, 229), "teal": (13, 148, 136), "green": (22, 163, 74), "orange": (234, 88, 12),
           "red": (225, 29, 46), "slate": (51, 65, 85), "black": (16, 17, 20)}
LOGO_MAX = 1024 * 1024
BRAND_DIR = "brand"


def default_config(kind):
    k = KINDS[kind]
    return {"title": k["title"], "accent": "blue", "logo": None, "co_logo": None, "company_line": "", "footer": "",
            "sections": [{"key": key, "on": True} for key, _ in k["sections"]], "texts": {key: "" for key, _, _ in k["texts"]}}


def brand_dir():
    path = os.path.join(_db.DATA_DIR, BRAND_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def save_logo(file):
    """Store an uploaded logo (PNG or JPEG, ≤ 1 MB, readable by the PDF writer); returns its file name."""
    from services.pdf import Image
    data = file.read(LOGO_MAX + 1)
    if len(data) > LOGO_MAX:
        raise ValueError("A logo up to 1 MB, please")
    img = Image(data)   # raises ValueError with the reason when it cannot be used
    if img.w > 3000 or img.h > 3000:
        raise ValueError("A logo up to 3000 × 3000 pixels, please")
    ext = "jpg" if data[:2] == b"\xff\xd8" else "png"
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(brand_dir(), name), "wb") as fh:
        fh.write(data)
    return name


def logo_path(name):
    if not name or not re.fullmatch(r"[0-9a-f]{32}\.(png|jpg)", name):
        return None
    path = os.path.join(brand_dir(), name)
    return path if os.path.exists(path) else None


_image_cache = {}


def logo_image(name):
    """The decoded logo for the PDF writer (cached: decoding a PNG takes a moment)."""
    path = logo_path(name)
    if not path:
        return None
    from services.pdf import Image
    if name not in _image_cache:
        with open(path, "rb") as fh:
            _image_cache[name] = Image(fh.read())
    return _image_cache[name]


def clean(kind, body):
    """A validated config from a posted body, or raise ValueError."""
    if kind not in KINDS:
        raise ValueError("Unknown document kind")
    base = default_config(kind)
    title = str(body.get("title") or base["title"]).strip()[:80]
    accent = body.get("accent") or "blue"
    if accent not in ACCENTS:
        raise ValueError("Pick one of the accent colours")
    logos = {}
    for key in ("logo", "co_logo"):
        v = body.get(key) or None
        if v and not logo_path(v):
            raise ValueError("Upload the logo again")
        logos[key] = v
    known = [k for k, _ in KINDS[kind]["sections"]]
    sections, seen = [], set()
    for s in body.get("sections") or base["sections"]:
        if isinstance(s, dict) and s.get("key") in known and s["key"] not in seen:
            sections.append({"key": s["key"], "on": bool(s.get("on"))})
            seen.add(s["key"])
    sections += [{"key": k, "on": True} for k in known if k not in seen]   # a section added later appears, switched on
    texts = {}
    for key, _, _ in KINDS[kind]["texts"]:
        texts[key] = str((body.get("texts") or {}).get(key) or "").strip()[:3000]
    return {"title": title, "accent": accent, **logos, "company_line": str(body.get("company_line") or "").strip()[:160],
            "footer": str(body.get("footer") or "").strip()[:200], "sections": sections, "texts": texts}


def all_templates(kind=None):
    rows = get_db().execute("SELECT * FROM doc_templates" + (" WHERE kind = ?" if kind else "") + " ORDER BY kind, is_default DESC, name",
                            (kind,) if kind else ()).fetchall()
    return [{"id": r["id"], "kind": r["kind"], "name": r["name"], "is_default": bool(r["is_default"]), "config": json.loads(r["config"]),
             "updated_at": r["updated_at"], "updated_by": r["updated_by"]} for r in rows]


def resolve(kind, template_id=None):
    """The config to render with: the chosen template, else the kind's default, else the built-in."""
    db = get_db()
    row = None
    if template_id:
        row = db.execute("SELECT config FROM doc_templates WHERE id = ? AND kind = ?", (template_id, kind)).fetchone()
    if row is None:
        row = db.execute("SELECT config FROM doc_templates WHERE kind = ? AND is_default = 1", (kind,)).fetchone()
    return clean(kind, json.loads(row["config"])) if row else default_config(kind)


def save(kind, name, config, author, template_id=None):
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("Name the template")
    cfg = clean(kind, config)
    db = get_db()
    now = datetime.utcnow().isoformat()
    if template_id:
        n = db.execute("UPDATE doc_templates SET name = ?, config = ?, updated_at = ?, updated_by = ? WHERE id = ? AND kind = ?",
                       (name, json.dumps(cfg), now, author, template_id, kind)).rowcount
        if not n:
            raise LookupError
    else:
        first = not db.execute("SELECT 1 FROM doc_templates WHERE kind = ?", (kind,)).fetchone()
        template_id = db.execute("INSERT INTO doc_templates (kind, name, is_default, config, created_by, created_at, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                 (kind, name, int(first), json.dumps(cfg), author, now, now, author)).lastrowid
    db.commit()
    return template_id


def make_default(template_id):
    db = get_db()
    row = db.execute("SELECT kind FROM doc_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        raise LookupError
    db.execute("UPDATE doc_templates SET is_default = (id = ?) WHERE kind = ?", (template_id, row["kind"]))
    db.commit()


def delete(template_id):
    db = get_db()
    row = db.execute("SELECT kind, is_default FROM doc_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        raise LookupError
    db.execute("DELETE FROM doc_templates WHERE id = ?", (template_id,))
    if row["is_default"]:   # another of the kind takes over, if any
        nxt = db.execute("SELECT id FROM doc_templates WHERE kind = ? ORDER BY id LIMIT 1", (row["kind"],)).fetchone()
        if nxt:
            db.execute("UPDATE doc_templates SET is_default = 1 WHERE id = ?", (nxt["id"],))
    db.commit()


def fill(text, values):
    """Replace {placeholders} and {field:Name}; unknown ones are left as typed."""
    return re.sub(r"\{(\w+|field:[^{}\n]{1,60})\}", lambda m: str(values.get(m.group(1), m.group(0)) or ""), text or "")


def section_on(config, key):
    return any(s["key"] == key and s["on"] for s in config["sections"])


def order(config):
    return [s["key"] for s in config["sections"] if s["on"]]
