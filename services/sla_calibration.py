"""SLA calibration: where a template's stage SLAs disagree with how long that
stage really took on the rollouts that used the template.

For each stage, every finished visit (one the rollout has left) is measured
in the SLA's own unit (working days when Settings counts them, through
services/workdays). With at least `sla_min_visits` visits, Odin proposes the
80th percentile (a target most rollouts meet) when it differs from today's
SLA by at least a day and a fifth. Pure statistics; the AI only adds a reason
per proposal (services/ai/features/sla_calibration.py). An admin applies a
proposal through the normal template SLA save, which is audited."""
import math

from db import get_db
from policies import local_date, policy
from services import stages as stage_ops
from services import workdays
from services.analytics import stage_timeline


def _nearest_rank(values, pct):
    s = sorted(values)
    return s[max(0, math.ceil(pct / 100 * len(s)) - 1)]


def proposals(db=None):
    """[{key, template_id, template, stage_id, stage, current, proposed, visits, median, p80}]"""
    db = db or get_db()
    cal = workdays.calendar(db)
    minimum = policy("sla_min_visits", db)
    notes = {}
    for n in db.execute("SELECT project_id, stage, created_at FROM status_notes ORDER BY created_at"):
        notes.setdefault(n["project_id"], []).append(n)
    out = []
    for t in db.execute("SELECT id, name FROM stage_templates ORDER BY id").fetchall():
        stages = stage_ops.list_stages("template", t["id"])
        if not stages:
            continue
        durations = {s["name"]: [] for s in stages}
        for p in db.execute("SELECT * FROM projects WHERE deleted_at IS NULL AND stage_template_id = ?", (t["id"],)).fetchall():
            timeline = stage_timeline(p, notes.get(p["id"], []), stages[0]["name"])
            for (name, entered), (_, left) in zip(timeline, timeline[1:]):
                if name in durations:
                    durations[name].append(max(1, workdays.between(local_date(entered.isoformat(), db), local_date(left.isoformat(), db), cal)))
        for s in stages[:-1]:   # the last stage is the closed one: no SLA
            visits = durations.get(s["name"]) or []
            if len(visits) < minimum:
                continue
            p80 = _nearest_rank(visits, 80)
            current = s["sla_days"]
            if current and abs(p80 - current) < max(1, math.ceil(0.2 * current)):
                continue
            out.append({"key": f"{t['id']}:{s['id']}:{p80}", "template_id": t["id"], "template": t["name"], "stage_id": s["id"], "stage": s["name"],
                        "current": current, "proposed": p80, "visits": len(visits), "median": _nearest_rank(visits, 50), "p80": p80,
                        "unit": "working days" if policy("count_working_days", db) else "days"})
    return out
