"""Custom fields per rollout (Odin 2.0): an admin defines a few extra fields
in Settings › Rollouts & workflow (at most `custom_fields_max`), and every
rollout holds one value per field.

A field has a kind (text, number, date, choice, yes-no), may be required when
a rollout is created, may be shown to partners and customers (the customer
cut: their project page, the customer report, the sign-off placeholders
{field:Name}) and may be shown as a column on the rollouts list. Values are
stored as text in one canonical form per kind and read back typed.
"""
import json
import math

from core import as_bool, parse_date, text_field
from db import get_db
from policies import policy
from services.fmt import fmt_date

KINDS = {"text": "Text", "number": "Number", "date": "Date", "choice": "Choice", "yesno": "Yes / no"}
NAME_MAX = 60
TEXT_MAX = 200        # a text value is one line
CHOICE_MAX = 60
CHOICES_MAX = 30
ARCHIVE_VALUES = 15   # values kept in the audit row when a field is deleted (audit's own cap is 2,000 characters)


def _row(r):
    return {"id": r["id"], "name": r["name"], "kind": r["kind"], "choices": json.loads(r["choices"] or "[]"),
            "required": bool(r["required"]), "customer_visible": bool(r["customer_visible"]),
            "show_in_list": bool(r["show_in_list"]), "position": r["position"]}


def definitions(customer=False, db=None):
    """Every field in order; the customer cut keeps only those marked for partners and customers."""
    rows = (db or get_db()).execute("SELECT * FROM custom_fields ORDER BY position, id").fetchall()
    return [_row(r) for r in rows if not customer or r["customer_visible"]]


def get(field_id):
    r = get_db().execute("SELECT * FROM custom_fields WHERE id = ?", (field_id,)).fetchone()
    return _row(r) if r else None


# ---- values -------------------------------------------------------------------

def parse_value(field, raw):
    """The stored form of a value for this field, None for empty; ValueError
    (with the field's name) for anything the kind does not allow."""
    name, kind = field["name"], field["kind"]
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if kind == "text":
        return text_field(raw, TEXT_MAX, name) or None
    if kind == "number":
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise ValueError(f"{name}: a number like 12 or 4.5")
        try:
            n = float(raw.strip().replace(",", "") if isinstance(raw, str) else raw)
        except ValueError:
            raise ValueError(f"{name}: a number like 12 or 4.5") from None
        if not math.isfinite(n):
            raise ValueError(f"{name}: a number like 12 or 4.5")
        return str(int(n)) if n.is_integer() and abs(n) < 1e15 else repr(n)
    if kind == "date":
        try:
            return parse_date(raw)
        except ValueError as e:
            raise ValueError(f"{name}: {e}") from None
    if kind == "choice":
        if not isinstance(raw, str) or raw.strip() not in field["choices"]:
            raise ValueError(f"{name}: pick one of {', '.join(field['choices'])}")
        return raw.strip()
    if kind == "yesno":
        yes = {"yes": True, "no": False}.get(raw.strip().lower(), as_bool(raw.strip().lower())) if isinstance(raw, str) else as_bool(raw)
        if yes is None:
            raise ValueError(f"{name}: yes or no")
        return "1" if yes else "0"
    raise ValueError(f"{name}: unknown kind")


def typed(kind, stored):
    """A stored value as JSON reads it: numbers as numbers, yes-no as true/false."""
    if stored is None:
        return None
    if kind == "number":
        n = float(stored)
        return int(n) if n.is_integer() and abs(n) < 1e15 else n
    if kind == "yesno":
        return stored == "1"
    return stored


def shown(kind, value):
    """A value, stored or typed, as a document prints it."""
    if value is None:
        return ""
    if kind == "yesno":
        return "Yes" if value in ("1", True) else "No"
    if kind == "date":
        return fmt_date(value)
    return str(value)


def _stored(project_id, db=None):
    return {r["field_id"]: r["value"] for r in (db or get_db()).execute(
        "SELECT field_id, value FROM project_field_values WHERE project_id = ?", (project_id,))}


def for_project(project_id, customer=False):
    """Every field (the customer cut: theirs only) with this rollout's value."""
    have = _stored(project_id)
    return [f | {"value": typed(f["kind"], have.get(f["id"]))} for f in definitions(customer)]


def values_for(project_ids, customer=False, list_only=False):
    """{project id: {field: typed value}} for many rollouts in one query: the
    list, the export, the read-only API and the portfolio."""
    defs = [f for f in definitions(customer) if f["show_in_list"] or not list_only]
    by_id = {f["id"]: f for f in defs}
    out = {pid: {} for pid in project_ids}
    if not project_ids or not defs:
        return out
    marks = ",".join("?" * len(project_ids))
    for r in get_db().execute(f"SELECT project_id, field_id, value FROM project_field_values WHERE project_id IN ({marks})", list(project_ids)):
        f = by_id.get(r["field_id"])
        if f:
            out[r["project_id"]][f["id"]] = typed(f["kind"], r["value"])
    return out


def named_values(project_ids):
    """{project id: {field name: value or None}}: every field, as staff see them (the read-only API)."""
    defs, have = definitions(), values_for(project_ids)
    return {pid: {f["name"]: have[pid].get(f["id"]) for f in defs} for pid in project_ids}


def clean_values(items, creating=False):
    """{field id: stored value or None} from {id: raw value}. An id that is no
    field is refused; on create, every required field needs a value."""
    defs = {f["id"]: f for f in definitions()}
    out, errors = {}, []
    for key, raw in items.items():
        fid = int(key) if isinstance(key, int) or (isinstance(key, str) and key.isascii() and key.isdigit()) else None
        if fid not in defs:
            raise ValueError("That field no longer exists: reload the page")
        try:
            out[fid] = parse_value(defs[fid], raw)
        except ValueError as e:
            errors.append(str(e))
    if creating:
        errors += [f"{f['name']} is required" for f in defs.values() if f["required"] and out.get(f["id"]) is None]
    if errors:
        raise ValueError("; ".join(errors))
    return out


def form_items(form):
    """The custom fields a project form posted, as field_<id> keys."""
    return {k[6:]: v for k, v in form.items() if k.startswith("field_")}


def save(db, project_id, values):
    """Write the values; returns the changes as "Name: old → new" for the audit
    row (nothing when nothing changed). The caller commits."""
    defs = {f["id"]: f for f in definitions(db=db)}
    old = _stored(project_id, db)
    changes = []
    for fid, value in values.items():
        if old.get(fid) == value:
            continue
        if value is None:
            db.execute("DELETE FROM project_field_values WHERE project_id = ? AND field_id = ?", (project_id, fid))
        else:
            db.execute("INSERT INTO project_field_values (project_id, field_id, value) VALUES (?, ?, ?) "
                       "ON CONFLICT(project_id, field_id) DO UPDATE SET value = excluded.value", (project_id, fid, value))
        changes.append(f"{defs[fid]['name']}: {old.get(fid) or '—'} → {value or '—'}")
        if value is not None:   # automations (services/rules.py): in a request they wait for its end, after the caller commits
            from services import rules
            rules.fire("field_set", project_id, {"field_id": fid, "value": value})
    return changes


def placeholders(project_id):
    """{field:Name} for the documents a customer reads: their fields only."""
    have = _stored(project_id)
    return {f"field:{f['name']}": shown(f["kind"], have.get(f["id"])) for f in definitions(customer=True)}


def filter_sql(args, customer=False):
    """(sql, params) narrowing a `projects p` query by ?field.<id>=<choice> for
    choice fields (the customer cut: only fields they may see)."""
    sql, params = "", []
    defs = {str(f["id"]): f for f in definitions(customer) if f["kind"] == "choice"}
    for key, value in args.items():
        f = defs.get(key[6:]) if key.startswith("field.") else None
        if f and value in f["choices"]:
            sql += " AND p.id IN (SELECT project_id FROM project_field_values WHERE field_id = ? AND value = ?)"
            params += [f["id"], value]
    return sql, params


# ---- definitions --------------------------------------------------------------

def clean_definition(body, existing=None):
    """The definition from a posted body, checked; ValueError otherwise."""
    name = text_field(body.get("name"), NAME_MAX, "Name")
    if not name:
        raise ValueError("Name the field")
    if any(c in name for c in "{}"):
        raise ValueError("A field name cannot hold { or }: they mark placeholders")
    clash = get_db().execute("SELECT 1 FROM custom_fields WHERE lower(name) = lower(?) AND id != ?", (name, existing["id"] if existing else 0)).fetchone()
    if clash:
        raise ValueError(f"There is already a field called {name}")
    kind = body.get("kind", existing["kind"] if existing else None)
    if kind not in KINDS:
        raise ValueError("Pick a kind: text, number, date, choice or yes / no")
    in_use = existing and get_db().execute("SELECT value FROM project_field_values WHERE field_id = ?", (existing["id"],)).fetchall()
    if existing and kind != existing["kind"] and in_use:
        raise ValueError("Rollouts already hold values for this field: its kind cannot change")
    choices = []
    if kind == "choice":
        raw = body.get("choices")
        raw = raw.split("\n") if isinstance(raw, str) else raw
        if not isinstance(raw, list):
            raise ValueError("Choices: one per line")
        for c in raw:
            c = text_field(c, CHOICE_MAX, "Choice")
            if c and c.lower() not in {x.lower() for x in choices}:
                choices.append(c)
        if not choices or len(choices) > CHOICES_MAX:
            raise ValueError(f"A choice field needs 1 to {CHOICES_MAX} choices")
        gone = sorted({r["value"] for r in in_use or []} - set(choices)) if existing else []
        if gone:
            raise ValueError(f"Rollouts still use {', '.join(gone)}: change them first")
    flags = {}
    for k in ("required", "customer_visible", "show_in_list"):
        v = body.get(k, existing[k] if existing else False)
        flags[k] = as_bool(v) if not isinstance(v, bool) else v
        if flags[k] is None:
            raise ValueError(f"{k.replace('_', ' ')}: true or false")
    return {"name": name, "kind": kind, "choices": choices, **flags}


def create(body):
    db = get_db()
    cap = policy("custom_fields_max")
    if db.execute("SELECT COUNT(*) FROM custom_fields").fetchone()[0] >= cap:
        raise ValueError(f"At most {cap} fields (Settings › Rollouts & workflow › Custom fields)")
    d = clean_definition(body)
    pos = db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM custom_fields").fetchone()[0]
    cur = db.execute("INSERT INTO custom_fields (name, kind, choices, required, customer_visible, show_in_list, position) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (d["name"], d["kind"], json.dumps(d["choices"]), d["required"], d["customer_visible"], d["show_in_list"], pos))
    db.commit()
    return cur.lastrowid, d


def update(field, body):
    """Change a definition; the values stay with the field, whatever its name."""
    d = clean_definition(body, existing=field)
    db = get_db()
    db.execute("UPDATE custom_fields SET name = ?, kind = ?, choices = ?, required = ?, customer_visible = ?, show_in_list = ? WHERE id = ?",
               (d["name"], d["kind"], json.dumps(d["choices"]), d["required"], d["customer_visible"], d["show_in_list"], field["id"]))
    db.commit()
    return d


def move(field, step):
    ids = [f["id"] for f in definitions()]
    i = ids.index(field["id"])
    j = max(0, min(len(ids) - 1, i + (1 if step > 0 else -1)))
    ids[i], ids[j] = ids[j], ids[i]
    db = get_db()
    for pos, fid in enumerate(ids):
        db.execute("UPDATE custom_fields SET position = ? WHERE id = ?", (pos, fid))
    db.commit()


def delete(field):
    """Remove the field and its values; returns the archive for the audit row:
    the name, the kind, how many rollouts held a value, and the first few."""
    db = get_db()
    rows = db.execute("SELECT project_id, value FROM project_field_values WHERE field_id = ? ORDER BY project_id", (field["id"],)).fetchall()
    db.execute("DELETE FROM project_field_values WHERE field_id = ?", (field["id"],))
    db.execute("DELETE FROM custom_fields WHERE id = ?", (field["id"],))
    db.commit()
    return json.dumps({"field": field["name"], "kind": field["kind"], "count": len(rows),
                       "values": [[r["project_id"], r["value"][:60]] for r in rows[:ARCHIVE_VALUES]]}, ensure_ascii=False)
