"""The rollout report: everything a delivery lead or a customer needs to
understand where a rollout stands and when it will land, in one structure
the page, the PDF and the weekly email all draw from.

Two audiences read it:

* internal — health with its reasons, plan against baseline with the slip
  and why it moved, the whole RAID register, work by person, every note;
* customer — progress, the timeline as planned and forecast, what is next,
  what we need from them, and only the RAID items and notes marked for them.

The project manager writes three things in their own words — the summary,
the next steps and (for the customer) what we need from them — and saves
the lot as a numbered version: a frozen snapshot of the data plus the
words. Live data is a draft; customers only ever see saved versions.
"""
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from db import get_db, participants_for
from policies import local_date, local_today, policy
from services import plan as plan_service
from services import raid as raid_service

AUDIENCES = ("internal", "customer")


def _day(stamp):
    """A stored UTC timestamp's workspace-local date, as 'YYYY-MM-DD' ('' when empty)."""
    d = local_date(stamp)
    return d.isoformat() if d else ""


def _fmt(iso):
    d = date.fromisoformat(iso[:10]) if iso else None
    return d.strftime("%-d %b %Y") if d else "—"


def draft_words(project, p, raid_items, audience="internal"):
    """Suggested summary, next steps and asks, from the numbers: a starting
    point the project manager edits, never the final word."""
    stages = p["stages"]
    cur = next((i for i, s in enumerate(stages) if s["status"] == "current"), 0)
    f = p["finish"]
    parts = [f"{project['name']} is in {project['stage']} (stage {cur + 1} of {len(stages)}), {p['pct_complete']}% complete."]
    if f["forecast"]:
        if f["vs_target_days"] is None:
            parts.append(f"Forecast to finish {_fmt(f['forecast'])}.")
        elif f["vs_target_days"] > 0:
            parts.append(f"Forecast to finish {_fmt(f['forecast'])}, {f['vs_target_days']} days after the {_fmt(f['target'])} target.")
        else:
            parts.append(f"Forecast to finish {_fmt(f['forecast'])}, {-f['vs_target_days']} days ahead of the {_fmt(f['target'])} target.")
    if f["vs_baseline_days"] and audience == "internal":   # the baseline is an internal yardstick
        # slip carries down the chain, so blame the stage where it grew most, not the last one
        grew, prev = [], 0
        for s in stages:
            if s["slip_days"] is not None:
                grew.append((s["slip_days"] - prev, s["name"]))
                prev = s["slip_days"]
        worst = max(grew, default=(0, None))
        why = f" — most of it in {worst[1]}" if worst[0] > 0 else ""
        parts.append(f"{abs(f['vs_baseline_days'])} days {'behind' if f['vs_baseline_days'] > 0 else 'ahead of'} the baseline{why}.")
    open_block = [r for r in raid_items if r["open"] and r["kind"] == "blocker" and (audience == "internal" or r["customer_visible"])]
    if open_block:
        parts.append(f"Blocked by: {'; '.join(r['title'] for r in open_block[:2])}.")
    ahead = [s for s in stages if s["status"] == "next"][:2]
    nxt = ([f"Finish {stages[cur]['name']} by {_fmt(stages[cur]['forecast_end'])}."] if stages else []) + \
          [f"{s['name']}: {_fmt(s['forecast_start'])} to {_fmt(s['forecast_end'])}." for s in ahead]
    return {"summary": " ".join(parts), "next_steps": "\n".join(nxt), "asks": ""}


def build(project, audience="internal"):
    """The live report data for one project and audience."""
    db = get_db()
    pid = project["id"]
    today = local_today()
    p = plan_service.build(project)
    items = raid_service.items(pid, customer=audience == "customer")
    team = [{"name": r["name"], "role": r["role"], "active": bool(r["active"])} for r in participants_for(pid)]
    tasks = [dict(r) for r in db.execute(
        "SELECT t.id, t.title, t.done, t.due_date, t.done_at, t.created_at, t.stage, u.name AS who, pp.role AS who_role FROM tasks t "
        "LEFT JOIN users u ON u.id = t.assignee_id LEFT JOIN project_participants pp ON pp.project_id = t.project_id AND pp.user_id = t.assignee_id "
        "WHERE t.project_id = ? ORDER BY t.done, t.due_date IS NULL, t.due_date, t.id", (pid,))]
    t_iso = today.isoformat()
    for t in tasks:
        t["done"] = bool(t["done"])
        t["late"] = bool(not t["done"] and t["due_date"] and t["due_date"] < t_iso)

    # work by stage and by person, and a weekly burn-up (tasks known vs tasks done)
    by_stage = []
    for s in p["stages"]:
        mine = [t for t in tasks if (t["stage"] or project["stage"]) == s["name"]]
        by_stage.append({"stage": s["name"], "total": len(mine), "done": sum(t["done"] for t in mine), "late": sum(t["late"] for t in mine)})
    people = defaultdict(lambda: {"open": 0, "done": 0, "late": 0, "role": None})
    for t in tasks:
        if t["who"]:
            x = people[t["who"]]
            x["role"] = x["role"] or t["who_role"]
            x["done" if t["done"] else "open"] += 1
            x["late"] += t["late"]
    start = plan_service._d(project["start_date"]) or plan_service._d(project["created_at"]) or today
    weeks, w = [], start - timedelta(days=start.weekday())
    while w <= today:
        end = (w + timedelta(days=7)).isoformat()
        weeks.append({"week": w.isoformat(), "total": sum(1 for t in tasks if _day(t["created_at"]) < end),
                      "done": sum(1 for t in tasks if t["done"] and _day(t["done_at"]) < end)})
        w += timedelta(days=7)

    # history: every visit (revisits included) with its dwell against the SLA; approvals; plan changes; notes
    sla_of = {s["name"]: s["sla_days"] for s in p["stages"]}
    dwell = [{"stage": v["stage"], "status": "done" if v["left"] else "current", "entered": v["entered"], "left": v["left"], "days": v["days"],
              "sla": sla_of.get(v["stage"]), "over": round(v["days"] - sla_of[v["stage"]], 1) if sla_of.get(v["stage"]) and v["days"] > sla_of[v["stage"]] else 0}
             for v in p["visits"]]
    approvals = [dict(r) for r in db.execute(
        "SELECT stage, status, requested_by, requested_at, decided_by, decided_at, comment FROM stage_approvals WHERE project_id = ? AND status != 'superseded' ORDER BY id DESC", (pid,))]
    note_sql = "SELECT author, note, stage, created_at FROM status_notes WHERE project_id = ? AND prev_stage IS NULL" + (" AND guest_visible = 1" if audience == "customer" else "") + " ORDER BY created_at DESC LIMIT 15"
    notes = [dict(r) for r in db.execute(note_sql, (pid,))]
    documents = [dict(r) for r in db.execute(
        "SELECT category, filename, uploaded_by, uploaded_at FROM documents WHERE project_id = ? AND deleted_at IS NULL ORDER BY uploaded_at DESC", (pid,))]
    pending_approval = next((a for a in approvals if a["status"] == "pending" and a["stage"] == project["stage"]), None)
    customer_tasks = [t for t in tasks if not t["done"] and t["who_role"] == "Customer"]

    cur_i = next((i for i, s in enumerate(p["stages"]) if s["status"] == "current"), 0)
    elapsed = (today - start).days
    data = {
        "audience": audience, "generated_at": datetime.utcnow().isoformat(), "today": t_iso, "company": policy("company_name"),
        "project": {"id": pid, "name": project["name"], "client": project["client"], "po_number": project["po_number"], "stage": project["stage"],
                    "owner_name": project["owner_name"], "start_date": start.isoformat(), "target_end_date": project["target_end_date"],
                    "vendor_name": project["vendor_name"], "product_name": project["product_name"], "delivery_mode": project["delivery_mode"],
                    "stage_number": cur_i + 1, "stage_count": len(p["stages"])},
        "health": p["health"], "pct_complete": p["pct_complete"], "finish": p["finish"], "baseline_at": p["baseline_at"],
        "elapsed_days": elapsed, "has_plan": p["has_plan"],
        "stages": p["stages"],
        "milestones": [{"stage": s["name"], "start": s["forecast_start"], "end": s["forecast_end"], "planned_end": s["plan_end"]}
                       for s in p["stages"] if s["status"] in ("current", "next")][:5],
        "raid": items,
        "work": {"total": len(tasks), "done": sum(t["done"] for t in tasks), "late": sum(t["late"] for t in tasks), "by_stage": by_stage,
                 "burn": weeks, "open": [t for t in tasks if not t["done"]][:40]},
        "team": team,
        "history": {"dwell": dwell, "approvals": approvals, "notes": notes},
        "needs": {"approval": pending_approval, "tasks": customer_tasks},
    }
    # The words are saved once and the customer reads them, so the suggestion
    # is always the customer's: no baseline, no blocker they cannot see.
    data["draft"] = draft_words(project, p, items, "customer")
    if audience == "internal":
        data["people"] = [{"name": k, **v} for k, v in sorted(people.items(), key=lambda kv: (-kv[1]["late"], -kv[1]["open"]))]
        data["plan_changes"] = plan_service.changes(pid, 30)
        data["documents"] = documents
    else:
        # the customer's health is the word, not the internal reasons
        data["health"] = customer_health(data)
        for s in data["stages"]:
            s.pop("base_start", None); s.pop("base_end", None); s.pop("slip_days", None)
        data["finish"] = {k: v for k, v in p["finish"].items() if k in ("forecast", "target", "vs_target_days", "days_to_target")}
        data["work"].pop("open")
        data["documents"] = [{"category": c, "count": n} for c, n in Counter(d["category"] for d in documents).most_common()]
    return data


def customer_health(d):
    """The colour a customer sees, worked out again from what they may see:
    only the RAID items marked for them count, and the baseline (an internal
    yardstick) does not, so a hidden blocker never turns their report red.
    No reasons: the customer's health is the word. Works on live data and on
    a saved snapshot alike."""
    h = d["health"]
    if h["rag"] == "done":
        return {"rag": "done", "reasons": [], "confidence": h.get("confidence")}
    stages = d.get("stages", [])
    cur = next((i for i, s in enumerate(stages) if s.get("status") == "current"), 0)
    finish = {**d.get("finish", {}), "vs_baseline_days": None}
    finish.setdefault("vs_target_days", None); finish.setdefault("target", None)
    risks = [r for r in d.get("raid", []) if r.get("customer_visible") and r.get("open")]
    today = date.fromisoformat(d["today"]) if d.get("today") else local_today()
    rag = plan_service._health(None, stages, cur, finish, risks, today, False, d.get("has_plan"))["rag"]
    return {"rag": rag, "reasons": [], "confidence": h.get("confidence")}


def customer_words(project_id, words, snapshot=None):
    """The project manager's words as the customer copy shows them: a
    sentence or line naming a RAID item that is not marked for the customer
    (now, or in the saved snapshot) is left out, and so is one about the
    baseline. Words written before the suggestion became customer-safe may
    still carry them."""
    import re
    hidden = {r["title"].strip().lower() for r in get_db().execute(
        "SELECT title FROM raid_items WHERE project_id = ? AND customer_visible = 0", (project_id,))}
    if snapshot:
        hidden |= {str(r.get("title") or "").strip().lower() for r in snapshot.get("raid", []) if not r.get("customer_visible")}
    hidden = {t for t in hidden if len(t) >= 3}

    def keep(sentence):
        low = sentence.lower()
        return "baseline" not in low and not any(t in low for t in hidden)

    out = {}
    for k, text in words.items():
        if k not in ("summary", "next_steps", "asks") or not isinstance(text, str):
            out[k] = text
            continue
        lines = []
        for line in text.split("\n"):
            parts = re.split(r"(?<=[.!?])\s+", line)
            kept = [s for s in parts if keep(s)]
            if kept or not line.strip():
                lines.append(" ".join(kept))
        out[k] = "\n".join(lines).strip()
    return out


def customer_view(snapshot):
    """A saved internal snapshot, cut down to what the customer may see."""
    d = json.loads(snapshot) if isinstance(snapshot, str) else dict(snapshot)
    d = json.loads(json.dumps(d))   # a deep copy
    d["audience"] = "customer"
    d["health"] = customer_health(d)
    for s in d.get("stages", []):
        s.pop("base_start", None); s.pop("base_end", None); s.pop("slip_days", None)
    d["finish"] = {k: v for k, v in d.get("finish", {}).items() if k in ("forecast", "target", "vs_target_days", "days_to_target")}
    d["raid"] = [r for r in d.get("raid", []) if r.get("customer_visible")]
    d["history"]["notes"] = d.get("customer_notes", [])
    d["work"].pop("open", None)
    for k in ("people", "plan_changes"):
        d.pop(k, None)
    d["documents"] = [{"category": c, "count": n} for c, n in Counter(x["category"] for x in d.get("documents", [])).most_common()]
    d.pop("customer_notes", None)
    return d


def snapshot(project):
    """The internal data frozen for a saved version, with the customer's notes
    kept aside so the customer version can be cut from it later."""
    d = build(project, "internal")
    d["customer_notes"] = [dict(r) for r in get_db().execute(
        "SELECT author, note, stage, created_at FROM status_notes WHERE project_id = ? AND prev_stage IS NULL AND guest_visible = 1 ORDER BY created_at DESC LIMIT 15",
        (project["id"],))]
    d.pop("draft", None)
    return d
