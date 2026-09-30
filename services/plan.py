"""A rollout's plan: dates per stage, a baseline, and a forecast.

Each of a project's stages may carry a planned start and end
(`project_stages.plan_start/plan_end`). The first time a plan is saved it is
also frozen as the baseline (`base_start/base_end`, `projects.baseline_at`);
re-baselining later needs a reason. Every date change is logged in
`plan_changes`, so the report can say what moved, by how much and why.

The forecast answers "when will this really finish?":

* a stage already left finishes when it was left (its actual dates);
* the current stage ends at the later of today and its start plus its
  planned length;
* each stage after it starts when the one before ends and lasts its planned
  length — the plan's, else the stage's SLA, else the workspace default.

Lengths count working days when the workspace does (services/workdays.py);
gaps between dates (slip, days after target) are calendar days. The last
stage of a list is the finish line (Closed and the like): it takes no time. Health is judged against the target date and the baseline with the
thresholds in Settings → Workflow.
"""
import json
from datetime import date, datetime

from db import get_db
from policies import local_today, policy, local_date
from services import workdays
from services.analytics import _parse, stage_timeline

ISO = "%Y-%m-%d"


def _d(value):
    """A workspace-local date from a stored date or UTC timestamp, or None."""
    return local_date(value)


def _iso(d):
    return d.isoformat() if d else None


def _days(a, b):
    return (b - a).days if a and b else None


def _visits(project, notes, stage_names):
    """{stage: (first entered, last left or None)} from the stage history."""
    timeline = stage_timeline(project, notes, stage_names[0] if stage_names else project["stage"])
    out = {}
    for i, (stage, entered) in enumerate(timeline):
        left = timeline[i + 1][1] if i + 1 < len(timeline) else None
        first = out.get(stage, (entered.date(), None))[0]
        out[stage] = (first, left.date() if left else None)
    return out


def suggested_plan(rows, start, default_days, cal=None):
    """A plan from nothing: stages back to back from `start`, each lasting
    its SLA or the default (working days, when the workspace counts them);
    the last stage is a zero-length finish line."""
    cal = cal or workdays.calendar()
    out, at = [], start
    for i, r in enumerate(rows):
        length = 0 if i == len(rows) - 1 else (r["sla_days"] or default_days)
        end = workdays.add(at, length, cal)
        out.append({"id": r["id"], "plan_start": _iso(at), "plan_end": _iso(end)})
        at = end
    return out


def build(project, rows=None, notes=None, risks=None):
    """The plan, the actuals, the forecast and the health of one project.
    `rows` are its project_stages rows, `notes` its status notes, `risks` its
    open RAID items (for health); each is read when not passed."""
    db = get_db()
    pid = project["id"]
    if rows is None:
        rows = db.execute("SELECT * FROM project_stages WHERE project_id = ? ORDER BY position", (pid,)).fetchall()
    if notes is None:
        notes = db.execute("SELECT stage, created_at FROM status_notes WHERE project_id = ? ORDER BY created_at", (pid,)).fetchall()
    if risks is None:
        risks = db.execute("SELECT kind, impact, status FROM raid_items WHERE project_id = ? AND status NOT IN ('closed', 'decided')", (pid,)).fetchall()
    today = local_today()
    default_days = policy("default_stage_days")
    names = [r["name"] for r in rows]
    cur = names.index(project["stage"]) if project["stage"] in names else 0
    visits = _visits(project, notes, names)
    start = _d(project["start_date"]) or _d(project["created_at"]) or today
    cal = workdays.calendar()
    wd = lambda a, b: workdays.between(a, b, cal)   # noqa: E731   durations: working days; gaps between dates stay _days
    suggested = {s["id"]: s for s in suggested_plan(rows, start, default_days, cal)}
    has_plan = any(r["plan_start"] for r in rows)
    last = len(rows) - 1

    stages, prev_end = [], None
    for i, r in enumerate(rows):
        p_start, p_end = _d(r["plan_start"]), _d(r["plan_end"])
        length = wd(p_start, p_end) if p_start and p_end else (0 if i == last else (r["sla_days"] or default_days))
        a_start, a_end = visits.get(r["name"], (None, None))
        if i < cur:
            status = "done" if a_start else "skipped"
            f_start, f_end = a_start or prev_end, a_end or a_start or prev_end
        elif i == cur:
            status = "current"
            f_start = a_start or _d(project["stage_entered_at"]) or today
            f_end = f_start if i == last else max(workdays.add(f_start, length, cal), today)
            a_end = None
        else:
            status = "next"
            f_start = prev_end or today
            f_end = workdays.add(f_start, length, cal)
            a_start = a_end = None
        prev_end = f_end
        compare = _d(r["base_end"]) or p_end
        stages.append({
            "id": r["id"], "name": r["name"], "position": r["position"], "sla_days": r["sla_days"], "status": status,
            "plan_start": _iso(p_start), "plan_end": _iso(p_end), "base_start": r["base_start"], "base_end": r["base_end"],
            "actual_start": _iso(a_start), "actual_end": _iso(a_end), "forecast_start": _iso(f_start), "forecast_end": _iso(f_end),
            "planned_days": length, "actual_days": wd(a_start, a_end or (today if status == "current" else None)),
            "slip_days": _days(compare, f_end) if compare else None,
            "suggested_start": suggested[r["id"]]["plan_start"], "suggested_end": suggested[r["id"]]["plan_end"],
        })

    finish = {
        "forecast": stages[-1]["forecast_end"] if stages else None,
        "planned": stages[-1]["plan_end"] if stages and has_plan else None,
        "baseline": stages[-1]["base_end"] if stages else None,
        "target": project["target_end_date"],
    }
    f, t, b = _d(finish["forecast"]), _d(finish["target"]), _d(finish["baseline"])
    finish["vs_target_days"] = _days(t, f)
    finish["vs_baseline_days"] = _days(b, f)
    finish["days_to_target"] = _days(today, t)

    # % complete by planned length: stages done count whole, the current one by time elapsed
    total = sum(max(s["planned_days"], 0) for s in stages) or 1
    done = sum(max(s["planned_days"], 0) for s in stages if s["status"] in ("done", "skipped"))
    c = stages[cur] if stages else None
    if c and c["planned_days"]:
        done += min(c["planned_days"], max(0, wd(_d(c["forecast_start"]), today) or 0))
    closed = bool(stages) and cur == last
    pct = 100 if closed else round(100 * done / total)

    health = _health(project, stages, cur, finish, risks, today, closed, has_plan)
    return {"stages": stages, "finish": finish, "health": health, "pct_complete": pct, "has_plan": has_plan,
            "baseline_at": project["baseline_at"], "today": today.isoformat(), "closed": closed, "default_days": default_days,
            # for the editor's live day counts: Python weekday numbers (Mon = 0) and the holidays
            "calendar": {"working": policy("count_working_days"), "week": sorted(cal[0]), "off": sorted(d.isoformat() for d in cal[1])}}


def _health(project, stages, cur, finish, risks, today, closed, has_plan):
    """Red / amber / green with the reasons, and how far to trust the forecast."""
    if closed:
        return {"rag": "done", "reasons": ["The rollout has reached its last stage."], "confidence": "high"}
    amber, red = policy("rag_amber_days"), policy("rag_red_days")
    reasons_red, reasons_amber = [], []
    vs_t = finish["vs_target_days"]
    t = _d(finish["target"])
    if t and t < today:
        reasons_red.append(f"Past its target date by {(today - t).days} d.")
    elif vs_t is not None and vs_t > red:
        reasons_red.append(f"Forecast to finish {vs_t} d after the target date.")
    elif vs_t is not None and vs_t > amber:
        reasons_amber.append(f"Forecast to finish {vs_t} d after the target date.")
    vs_b = finish["vs_baseline_days"]
    if vs_b is not None and vs_b > red and not reasons_red:
        reasons_amber.append(f"{vs_b} d behind the baseline.")
    c = stages[cur] if stages else None
    if c and c["sla_days"] and c["actual_days"] is not None and c["actual_days"] > c["sla_days"]:
        reasons_amber.append(f"{c['name']} is {c['actual_days'] - c['sla_days']} d over its {c['sla_days']} d SLA.")
    blockers = [r for r in risks if r["kind"] == "blocker"]
    high = [r for r in risks if r["kind"] in ("risk", "issue") and r["impact"] == "high"]
    if blockers:
        reasons_red.append(f"{len(blockers)} open blocker{'s' if len(blockers) != 1 else ''}.")
    if high:
        reasons_amber.append(f"{len(high)} open high-impact risk{'s' if len(high) != 1 else ''} or issue{'s' if len(high) != 1 else ''}.")
    rag = "red" if reasons_red else "amber" if reasons_amber else "green"
    reasons = reasons_red + reasons_amber or ["On plan, inside its SLAs, nothing blocking."]
    # confidence: how much of what is left rests on real dates rather than defaults
    ahead = stages[cur:] if stages else []
    planned = sum(1 for s in ahead if s["plan_start"])
    late_now = c and c["plan_end"] and _d(c["plan_end"]) < today
    confidence = "low" if not has_plan or late_now else "high" if planned == len(ahead) else "medium"
    return {"rag": rag, "reasons": reasons, "confidence": confidence}


def validate(rows, items):
    """Clean {stage id: (start, end)} from posted items, or raise ValueError."""
    known = {r["id"]: r for r in rows}
    out = {}
    for it in items if isinstance(items, list) else []:
        sid = it.get("id") if isinstance(it, dict) else None
        if sid not in known:
            continue
        s, e = it.get("plan_start") or None, it.get("plan_end") or None
        ds, de = _d(s), _d(e)
        if (s and not ds) or (e and not de):
            raise ValueError(f"{known[sid]['name']}: dates like 2026-10-31")
        if bool(ds) != bool(de):
            raise ValueError(f"{known[sid]['name']}: give both a start and an end, or neither")
        if ds and de < ds:
            raise ValueError(f"{known[sid]['name']}: the end is before the start")
        out[sid] = (_iso(ds), _iso(de))
    return out


def save(project, items, reason, author):
    """Store a plan; log each moved date; freeze the first one as the
    baseline. Returns (changed, baselined)."""
    db = get_db()
    rows = db.execute("SELECT * FROM project_stages WHERE project_id = ? ORDER BY position", (project["id"],)).fetchall()
    clean = validate(rows, items)
    now = datetime.utcnow().isoformat()
    changed = 0
    for r in rows:
        if r["id"] not in clean:
            continue
        s, e = clean[r["id"]]
        for field, old, new in (("start", r["plan_start"], s), ("end", r["plan_end"], e)):
            if (old or None) != new:
                changed += 1
                db.execute("INSERT INTO plan_changes (project_id, stage, field, old, new, reason, author, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (project["id"], r["name"], field, old, new, reason or None, author, now))
        db.execute("UPDATE project_stages SET plan_start = ?, plan_end = ? WHERE id = ?", (s, e, r["id"]))
    baselined = False
    if not project["baseline_at"] and any(v[0] for v in clean.values()):
        db.execute("UPDATE project_stages SET base_start = plan_start, base_end = plan_end WHERE project_id = ?", (project["id"],))
        db.execute("UPDATE projects SET baseline_at = ? WHERE id = ?", (now, project["id"]))
        baselined = True
    db.commit()
    return changed, baselined


def rebaseline(project, reason, author):
    """Make the current plan the new baseline (a reason is required)."""
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute("UPDATE project_stages SET base_start = plan_start, base_end = plan_end WHERE project_id = ?", (project["id"],))
    db.execute("UPDATE projects SET baseline_at = ? WHERE id = ?", (now, project["id"]))
    db.execute("INSERT INTO plan_changes (project_id, stage, field, old, new, reason, author, created_at) VALUES (?, NULL, 'baseline', ?, ?, ?, ?, ?)",
               (project["id"], project["baseline_at"], now, reason, author, now))
    db.commit()


def changes(project_id, limit=50):
    return [dict(r) for r in get_db().execute(
        "SELECT stage, field, old, new, reason, author, created_at FROM plan_changes WHERE project_id = ? ORDER BY id DESC LIMIT ?", (project_id, limit))]


def snapshot_json(obj):
    return json.dumps(obj, separators=(",", ":"), default=str)
