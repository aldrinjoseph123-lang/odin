"""The portfolio report: every open rollout's health, forecast and slip in
one structure for the page (/reports/all), its PDF and the weekly email.

Built from the same plan engine as the rollout report (services/plan.py),
so a rollout's health and forecast read the same in both places."""
from collections import Counter
from datetime import datetime, timedelta

from db import get_db
from policies import local_today, policy
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
    for p in projects:
        pl = plan_service.build(p)
        items = raid_service.items(p["id"], customer=customer)
        f = pl["finish"]
        cur = next((i for i, s in enumerate(pl["stages"]) if s["status"] == "current"), 0)
        first = pl["stages"][0] if pl["stages"] else {}
        latest = db.execute("SELECT version, kind, created_at FROM project_reports WHERE project_id = ? ORDER BY version DESC LIMIT 1", (p["id"],)).fetchone()
        open_items = [r for r in items if r["open"]]
        rows.append({
            **{k: p[k] for k in ("id", "name", "client", "stage", "owner_name", "delivery_mode", "vendor_name", "product_name", "target_end_date")},
            "rag": pl["health"]["rag"], "reasons": pl["health"]["reasons"], "confidence": pl["health"]["confidence"],
            "pct_complete": pl["pct_complete"], "stage_number": cur + 1, "stage_count": len(pl["stages"]),
            "start": first.get("actual_start") or first.get("plan_start") or (p["start_date"] or p["created_at"] or today.isoformat())[:10],
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
