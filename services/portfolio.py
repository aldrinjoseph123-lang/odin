"""The portfolio report: every open rollout's health, forecast and slip in
one structure for the page (/reports/all), its PDF and the weekly email.

Built from the same plan engine as the rollout report (services/plan.py),
so a rollout's health and forecast read the same in both places."""
from collections import Counter
from datetime import datetime, timedelta

from db import get_db, stages_for_projects
from policies import local_date, local_today, policy
from services import plan as plan_service
from services import raid as raid_service

RAG_ORDER = {"red": 0, "amber": 1, "green": 2, "done": 3}


INTERNAL = ("reasons", "confidence", "baseline", "vs_baseline_days")


def build(projects, customer=False):
    """projects: rows of projects joined with owner_name. The customer cut
    (partners and customers) drops the reasons, the baseline and every RAID
    item not marked for them."""
    db = get_db()
    today = local_today()
    rows, risks = [], []
    # everything per project in one query each, not one per project (the report of all rollouts)
    ids = [p["id"] for p in projects]
    marks = ",".join("?" * len(ids)) or "NULL"
    stage_rows = stages_for_projects(ids)
    notes, raid, latest_of = {}, {}, {}
    for n in db.execute(f"SELECT project_id, stage, created_at FROM status_notes WHERE project_id IN ({marks}) ORDER BY created_at", ids):
        notes.setdefault(n["project_id"], []).append(n)
    for r in db.execute(
            f"SELECT r.*, u.name AS owner_name FROM raid_items r LEFT JOIN users u ON u.id = r.owner_id WHERE r.project_id IN ({marks}) "
            "ORDER BY r.status IN ('closed', 'decided'), CASE r.kind WHEN 'blocker' THEN 0 WHEN 'issue' THEN 1 WHEN 'risk' THEN 2 ELSE 3 END, "
            "CASE r.impact WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, r.due_date IS NULL, r.due_date, r.id", ids):
        raid.setdefault(r["project_id"], []).append(dict(r) | {"customer_visible": bool(r["customer_visible"]), "open": r["status"] not in raid_service.DONE})
    for r in db.execute(f"SELECT project_id, version, kind, created_at FROM project_reports WHERE project_id IN ({marks}) ORDER BY version", ids):
        latest_of[r["project_id"]] = r
    for p in projects:
        every = raid.get(p["id"], [])
        pl = plan_service.build(p, stage_rows.get(p["id"]) or [], notes.get(p["id"], []), [r for r in every if r["open"]])
        items = [r for r in every if r["customer_visible"]] if customer else every
        if customer:   # the colour from what they may see: a hidden blocker never turns it red
            from services.report_data import customer_health
            pl["health"] = customer_health({"health": pl["health"], "stages": pl["stages"], "finish": pl["finish"], "raid": items,
                                            "today": today.isoformat(), "has_plan": pl["has_plan"]})
        f = pl["finish"]
        cur = next((i for i, s in enumerate(pl["stages"]) if s["status"] == "current"), 0)
        first = pl["stages"][0] if pl["stages"] else {}
        latest = latest_of.get(p["id"])
        open_items = [r for r in items if r["open"]]
        rows.append({
            **{k: p[k] for k in ("id", "name", "client", "stage", "owner_name", "delivery_mode", "vendor_name", "product_name", "target_end_date")},
            "rag": pl["health"]["rag"], "reasons": pl["health"]["reasons"], "confidence": pl["health"]["confidence"],
            "pct_complete": pl["pct_complete"], "stage_number": cur + 1, "stage_count": len(pl["stages"]),
            "start": first.get("actual_start") or first.get("plan_start") or (p["start_date"] or (local_date(p["created_at"]) or today).isoformat())[:10],
            "forecast": f["forecast"], "planned": f["planned"], "baseline": f["baseline"],
            "vs_target_days": f["vs_target_days"], "vs_baseline_days": f["vs_baseline_days"], "has_plan": pl["has_plan"],
            "open": {k: sum(1 for r in open_items if r["kind"] == k) for k in ("blocker", "issue", "risk")},
            "report": None if latest is None else {"version": latest["version"], "kind": latest["kind"], "created_at": latest["created_at"]},
        })
        risks += [{"project_id": p["id"], "project": p["name"], "kind": r["kind"], "title": r["title"], "impact": r["impact"],
                   "status": r["status"], "owner_name": r["owner_name"], "due_date": r["due_date"]}
                  for r in open_items if r["kind"] == "blocker" or (r["impact"] == "high" and r["kind"] in ("risk", "issue"))]
    rows.sort(key=lambda r: (RAG_ORDER.get(r["rag"], 9), r["forecast"] or "9999"))
    risks.sort(key=lambda r: (r["kind"] != "blocker", r["due_date"] or "9999"))
    slips = [r["vs_baseline_days"] for r in rows if r["vs_baseline_days"] is not None]
    soon = (today + timedelta(days=30)).isoformat()
    summary = {
        "count": len(rows), "health": dict(Counter(r["rag"] for r in rows)),
        "late_vs_target": sum(1 for r in rows if r["vs_target_days"] and r["vs_target_days"] > 0),
        "behind_baseline": sum(1 for s in slips if s > 0), "avg_slip": round(sum(slips) / len(slips), 1) if slips else None,
        "blockers": sum(r["open"]["blocker"] for r in rows), "finishing_30d": sum(1 for r in rows if r["forecast"] and r["forecast"] <= soon),
        "no_plan": sum(1 for r in rows if not r["has_plan"]),
    }
    if customer:
        for r in rows:
            for k in INTERNAL:
                r.pop(k)
        summary["behind_baseline"] = summary["avg_slip"] = None
    return {"audience": "customer" if customer else "internal", "generated_at": datetime.utcnow().isoformat(), "today": today.isoformat(), "company": policy("company_name"),
            "summary": summary, "rows": rows, "risks": risks[:25]}
