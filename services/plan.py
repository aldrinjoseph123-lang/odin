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
  length — the plan's, else the stage's SLA, else the workspace default;
* a running or coming stage ends no sooner than its latest open task that
  waits on other open work, chained through the task links
  (services/task_links.py): a late predecessor moves the forecast, and the
  stage says which task did it (forecast_reason, and a health reason).

Lengths count working days when the workspace does (services/workdays.py);
gaps between dates (slip, days after target) are calendar days. The last
stage of a list is the finish line (Closed and the like): it takes no time. Health is judged against the target date and the baseline with the
thresholds in Settings › Workflow.
"""
import json
from datetime import date, datetime

from db import get_db, touch_project
from policies import local_today, policy, local_date
from services import task_links, workdays
from services.analytics import _parse, clock, stage_timeline, working_days

ISO = "%Y-%m-%d"
FIRST_DAY, LAST_DAY = date(2000, 1, 1), date(2100, 12, 31)   # a plan date outside this is a typo, not a plan


def _d(value):
    """A workspace-local date from a stored date or UTC timestamp, or None."""
    return local_date(value)


def _iso(d):
    return d.isoformat() if d else None


def _days(a, b):
    return (b - a).days if a and b else None


def _visits(project, notes, stage_names, clk, now):
    """Every visit from the stage history, oldest first: {stage, entered,
    left (None while there), days}. Days are working days, part days
    included — the measure the Flow and the SLA use. The visit in progress
    starts at stage_entered_at, the clock change_stage sets."""
    timeline = stage_timeline(project, notes, stage_names[0] if stage_names else project["stage"])
    entered_now = _parse(project["stage_entered_at"]) if project["stage_entered_at"] else None
    if timeline and entered_now and timeline[-1][0] == project["stage"]:
        timeline[-1] = (project["stage"], entered_now)
    out = []
    for i, (stage, entered) in enumerate(timeline):
        left = timeline[i + 1][1] if i + 1 < len(timeline) else None
        out.append({"stage": stage, "entered": entered, "left": left, "days": working_days(entered, left or now, clk)})
    return out


def _local(moment):
    return local_date(moment.isoformat()) if moment else None


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


def _chained(project, names, tasks, links, today):
    """{stage name: (finish, task, late root or None)}: per stage, the open
    task waiting on open work that finishes last, chained through the links."""
    held = task_links.blocked_by(tasks, links, today)
    chain = task_links.chained_finish(tasks, links, today) if held else {}
    out = {}
    for t in tasks:
        end, root = chain.get(t["id"], (None, None))
        if t["id"] not in held or end is None:
            continue
        stage = t["stage"] if t["stage"] in names else project["stage"]   # no stage: the current one
        if stage not in out or end > out[stage][0]:
            out[stage] = (end, t, root)
    return out


def _push_reason(stage, task, root, today):
    if root is None:
        return None   # dates beyond the plan, nothing late: the forecast follows, health is not touched
    late = (today - _d(root["due_date"])).days
    via = f", which waits on {root['title']} ({late} d late)" if root["id"] != task["id"] else f" ({late} d late)"
    return f"{stage} is forecast later: {task['title']} waits on open work{via}."


def build(project, rows=None, notes=None, risks=None, tasks=None, declined=...):
    """The plan, the actuals, the forecast and the health of one project.
    `rows` are its project_stages rows, `notes` its status notes, `risks` its
    open RAID items (for health), `tasks` its tasks (for the chains),
    `declined` the customer's decline that pauses its stage or None
    (services/approvals.declined); each is read when not passed."""
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
    links = task_links.links_for(pid, db)
    if links and tasks is None:
        tasks = db.execute("SELECT id, title, done, due_date, stage FROM tasks WHERE project_id = ?", (pid,)).fetchall()
    pushed = _chained(project, names, tasks, links, today) if links else {}
    cur = names.index(project["stage"]) if project["stage"] in names else 0
    clk = clock()
    cal = clk[0]
    visits = _visits(project, notes, names, clk, datetime.utcnow())
    start = _d(project["start_date"]) or _d(project["created_at"]) or today
    wd = lambda a, b: workdays.between(a, b, cal)   # noqa: E731   durations: working days; gaps between dates stay _days
    suggested = {s["id"]: s for s in suggested_plan(rows, start, default_days, cal)}
    has_plan = any(r["plan_start"] for r in rows)
    last = len(rows) - 1

    stages, prev_end = [], None
    for i, r in enumerate(rows):
        p_start, p_end = _d(r["plan_start"]), _d(r["plan_end"])
        length = wd(p_start, p_end) if p_start and p_end else (0 if i == last else (r["sla_days"] or default_days))
        left = [v for v in visits if v["stage"] == r["name"] and v["left"]]
        a_start, a_end = (_local(left[0]["entered"]), _local(left[-1]["left"])) if left else (None, None)
        a_days = round(sum(v["days"] for v in left), 1) if left else None   # every visit counts, revisits included
        if i < cur:
            status = "done" if a_start else "skipped"
            f_start, f_end = a_start or prev_end, a_end or a_start or prev_end
        elif i == cur:
            status = "current"
            now_visit = visits[-1] if visits and visits[-1]["stage"] == r["name"] and not visits[-1]["left"] else None
            a_start = _local(now_visit["entered"]) if now_visit else (_d(project["stage_entered_at"]) or today)
            a_days = round(now_visit["days"], 1) if now_visit else None   # this visit, as the Flow and the SLA count it
            f_start = a_start
            f_end = f_start if i == last else max(workdays.add(f_start, length, cal), today)
            a_end = None
        else:
            status = "next"
            f_start = prev_end or today
            f_end = workdays.add(f_start, length, cal)
            a_start = a_end = a_days = None
        reason = None
        if status in ("current", "next") and i != last and r["name"] in pushed and pushed[r["name"]][0] > f_end:
            f_end, task, root = pushed[r["name"]]
            reason = _push_reason(r["name"], task, root, today)
        prev_end = f_end
        compare = _d(r["base_end"]) or p_end
        stages.append({
            "id": r["id"], "name": r["name"], "position": r["position"], "sla_days": r["sla_days"], "status": status,
            "plan_start": _iso(p_start), "plan_end": _iso(p_end), "base_start": r["base_start"], "base_end": r["base_end"],
            "actual_start": _iso(a_start), "actual_end": _iso(a_end), "forecast_start": _iso(f_start), "forecast_end": _iso(f_end),
            "planned_days": length, "actual_days": a_days,
            "slip_days": _days(compare, f_end) if compare else None,
            "suggested_start": suggested[r["id"]]["plan_start"], "suggested_end": suggested[r["id"]]["plan_end"],
            "forecast_reason": reason,
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

    # a stage gate that holds the move once the stage is due to end (services/gates.py)
    gate = None
    if not closed and c and cur + 1 < len(rows) and _d(c["forecast_end"]) and _d(c["forecast_end"]) <= today:
        from services import gates
        # a decline is its own (red) reason below, not the gate's
        gate = gates.summary([r for r in gates.blocked(project, names[cur + 1], rows) if r["kind"] != "declined"]) or None
    if declined is ...:
        from services import approvals
        declined = None if closed else approvals.declined(project, db)
    health = _health(project, stages, cur, finish, risks, today, closed, has_plan, gate, declined)
    return {"stages": stages, "finish": finish, "health": health, "pct_complete": pct, "has_plan": has_plan,
            "warning": past_target(max((s["plan_end"] for s in stages if s["plan_end"]), default=None), project["target_end_date"]),
            # every visit, revisits included, for the report's history
            "visits": [{"stage": v["stage"], "entered": _iso(_local(v["entered"])), "left": _iso(_local(v["left"])), "days": round(v["days"], 1)} for v in visits],
            "baseline_at": project["baseline_at"], "today": today.isoformat(), "closed": closed, "default_days": default_days,
            # for the editor's live day counts: Python weekday numbers (Mon = 0) and the holidays
            "calendar": {"working": policy("count_working_days"), "week": sorted(cal[0]), "off": sorted(d.isoformat() for d in cal[1])}}


def _health(project, stages, cur, finish, risks, today, closed, has_plan, gate=None, declined=None):
    """Red / amber / green with the reasons, and how far to trust the forecast.
    `gate`: what holds a move that is due now (internal; the customer's health passes none).
    `declined`: the customer's decline that pauses the stage (red; the customer's health passes none)."""
    if closed:
        return {"rag": "done", "reasons": ["The rollout has reached its last stage."], "confidence": "high"}
    amber, red = policy("rag_amber_days"), policy("rag_red_days")
    reasons_red, reasons_amber = [], []
    vs_t = finish["vs_target_days"]
    t = _d(finish["target"])
    if t and t < today:
        reasons_red.append(f"Past its target date by {(today - t).days} d.")
    elif not has_plan:
        pass   # no plan saved: the forecast is only the template's default lengths, so it says nothing about the target (sim 28 Oct)
    elif vs_t is not None and vs_t > red:
        reasons_red.append(f"Forecast to finish {vs_t} d after the target date.")
    elif vs_t is not None and vs_t > amber:
        reasons_amber.append(f"Forecast to finish {vs_t} d after the target date.")
    vs_b = finish["vs_baseline_days"]
    if vs_b is not None and vs_b > amber and not reasons_red:   # amber past the amber line, as the target (P3-22)
        reasons_amber.append(f"{vs_b} d behind the baseline.")
    c = stages[cur] if stages else None
    if c and c["sla_days"] and c["actual_days"] is not None and c["actual_days"] > c["sla_days"]:
        # whole days, as the stage chips count them ("6 over SLA"), so one fact reads one way everywhere
        reasons_amber.append(f"{c['name']} is {round(c['actual_days'] - c['sla_days'])} d over its {c['sla_days']} d SLA.")
    if gate and c:
        reasons_amber.append(f"Due to leave {c['name']}, held by its gate: {gate}.")
    if declined:
        reasons_red.append(f"The customer declined {declined['stage']}.")
    blockers = [r for r in risks if r["kind"] == "blocker"]
    high = [r for r in risks if r["kind"] in ("risk", "issue") and r["impact"] == "high"]
    if blockers:
        reasons_red.append(f"{len(blockers)} open blocker{'s' if len(blockers) != 1 else ''}.")
    reasons_amber += [s["forecast_reason"] for s in stages if s.get("forecast_reason")]   # a late predecessor, by name
    if high:
        reasons_amber.append(f"{len(high)} open high-impact risk{'s' if len(high) != 1 else ''} or issue{'s' if len(high) != 1 else ''}.")
    rag = "red" if reasons_red else "amber" if reasons_amber else "green" if has_plan else "none"   # "none": no plan yet, nothing else wrong
    reasons = reasons_red + reasons_amber or (["On plan, inside its SLAs, nothing blocking."] if has_plan else ["No plan has been saved yet; health starts when one is."])
    # confidence: how much of what is left rests on real dates rather than defaults
    ahead = stages[cur:] if stages else []
    planned = sum(1 for s in ahead if s["plan_start"])
    late_now = c and c["plan_end"] and _d(c["plan_end"]) < today
    confidence = "low" if not has_plan or late_now else "high" if planned == len(ahead) else "medium"
    return {"rag": rag, "reasons": reasons, "confidence": confidence}


def validate(rows, items):
    """Clean {stage id: (start, end)} from posted items, or raise ValueError:
    a body that is not a list of this rollout's stages is refused, never
    answered "saved" with nothing saved (P2-27)."""
    known = {r["id"]: r for r in rows}
    out = {}
    if not isinstance(items, list):
        raise ValueError("Send the stages as a list")
    for it in items:
        sid = it.get("id") if isinstance(it, dict) else None
        if isinstance(sid, bool) or not isinstance(sid, int) or sid not in known:
            raise ValueError("A stage in the plan is not one of this rollout's stages; reload and try again")
        s, e = it.get("plan_start") or None, it.get("plan_end") or None
        if any(v is not None and not isinstance(v, str) for v in (s, e)):
            raise ValueError(f"{known[sid]['name']}: dates like 2026-10-31")
        ds, de = _d(s), _d(e)
        if (s and not ds) or (e and not de):
            raise ValueError(f"{known[sid]['name']}: dates like 2026-10-31")
        if any(d and not FIRST_DAY <= d <= LAST_DAY for d in (ds, de)):
            raise ValueError(f"{known[sid]['name']}: dates between {FIRST_DAY.year} and {LAST_DAY.year}")
        if bool(ds) != bool(de):
            raise ValueError(f"{known[sid]['name']}: give both a start and an end, or neither")
        if ds and de < ds:
            raise ValueError(f"{known[sid]['name']}: the end is before the start")
        out[sid] = (_iso(ds), _iso(de))
    return out


def past_target(planned_end, target):
    """The warning when a plan ends after the target date (shown, never blocking)."""
    p, t = _d(planned_end), _d(target)
    if p and t and p > t:
        return f"The plan ends on {p.isoformat()}, {(p - t).days} d after the target date {t.isoformat()}."
    return None


def save(project, items, reason, author):
    """Store a plan; log each moved date; freeze the first one as the
    baseline. Once there is a baseline every move needs its reason
    (PRODUCT.md: the report says what moved and why). Returns (changed,
    baselined, warning)."""
    db = get_db()
    rows = db.execute("SELECT * FROM project_stages WHERE project_id = ? ORDER BY position", (project["id"],)).fetchall()
    clean = validate(rows, items)
    now = datetime.utcnow().isoformat()
    moves = [(r["name"], field, old, new) for r in rows if r["id"] in clean
             for field, old, new in (("start", r["plan_start"], clean[r["id"]][0]), ("end", r["plan_end"], clean[r["id"]][1]))
             if (old or None) != new]
    has_baseline = any(r["base_start"] for r in rows)
    if moves and has_baseline and not reason:
        raise ValueError("Say why the dates move")
    for stage, field, old, new in moves:
        db.execute("INSERT INTO plan_changes (project_id, stage, field, old, new, reason, author, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (project["id"], stage, field, old, new, reason or None, author, now))
    for sid, (s, e) in clean.items():
        db.execute("UPDATE project_stages SET plan_start = ?, plan_end = ? WHERE id = ?", (s, e, sid))
    baselined = False
    if not has_baseline and any(v[0] for v in clean.values()):   # the first real plan, even after an early re-baseline of nothing
        db.execute("UPDATE project_stages SET base_start = plan_start, base_end = plan_end WHERE project_id = ?", (project["id"],))
        db.execute("UPDATE projects SET baseline_at = ? WHERE id = ?", (now, project["id"]))
        baselined = True
    if moves or baselined:
        touch_project(db, project["id"])
    db.commit()
    end = db.execute("SELECT MAX(plan_end) FROM project_stages WHERE project_id = ?", (project["id"],)).fetchone()[0]
    return len(moves), baselined, past_target(end, project["target_end_date"])


def rebaseline(project, reason, author):
    """Make the current plan the new baseline (a reason is required). Refused
    while there is no plan: the first plan saved becomes the baseline."""
    db = get_db()
    if not db.execute("SELECT 1 FROM project_stages WHERE project_id = ? AND plan_start IS NOT NULL", (project["id"],)).fetchone():
        raise ValueError("There is no plan to baseline yet; the first plan saved becomes the baseline")
    now = datetime.utcnow().isoformat()
    db.execute("UPDATE project_stages SET base_start = plan_start, base_end = plan_end WHERE project_id = ?", (project["id"],))
    db.execute("UPDATE projects SET baseline_at = ? WHERE id = ?", (now, project["id"]))
    db.execute("INSERT INTO plan_changes (project_id, stage, field, old, new, reason, author, created_at) VALUES (?, NULL, 'baseline', ?, ?, ?, ?, ?)",
               (project["id"], project["baseline_at"], now, reason, author, now))
    touch_project(db, project["id"])
    db.commit()


def changes(project_id, limit=50):
    return [dict(r) for r in get_db().execute(
        "SELECT stage, field, old, new, reason, author, created_at FROM plan_changes WHERE project_id = ? ORDER BY id DESC LIMIT ?", (project_id, limit))]


def snapshot_json(obj):
    return json.dumps(obj, separators=(",", ":"), default=str)
