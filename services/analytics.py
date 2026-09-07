"""Cycle-time analytics: how long projects actually spend in each stage.

Everything here is derived from data the app already stores — every stage
change writes a status_notes row carrying the stage and a timestamp, so the
note history *is* the stage history. Nothing new is recorded to support this
module.

build_cycle_times() is pure computation over rows, so it can be tested without
a request context and reused by any caller.
"""
from datetime import datetime
from statistics import median


def _parse(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def stage_timeline(project, notes, first_stage):
    """Reconstruct [(stage, entered_at), ...] for one project, oldest first.

    Two things make this less obvious than reading the notes in order:

    * Creating a project writes no note, so the opening entry has to be
      synthesised from the project's own created_at in the first stage.
    * A plain status note carries whatever stage the project is currently in,
      so consecutive notes sharing a stage are one visit, not several.
    """
    created = _parse(project["created_at"])
    if created is None:
        return []

    timeline = [(first_stage, created)]
    for note in notes:
        entered = _parse(note["created_at"])
        if entered is None or entered < created:
            continue  # a note predating its project is corrupt; ignore it
        if note["stage"] != timeline[-1][0]:
            timeline.append((note["stage"], entered))

    # Defensive: if the project's current stage somehow isn't where the note
    # history ends, trust the project row and close the gap with updated_at.
    if project["stage"] != timeline[-1][0]:
        updated = _parse(project["updated_at"]) or timeline[-1][1]
        timeline.append((project["stage"], max(updated, timeline[-1][1])))
    return timeline


def build_cycle_times(projects, notes_by_project, stage_names, terminal_stage, now=None):
    """Per-stage dwell statistics, current aging, lead time and throughput.

    A *completed* visit is one the project has already left — those are the
    only ones with a known duration, so they alone feed the averages. Time in
    the stage a project sits in right now is reported separately as aging;
    folding it into the average would quietly drag every number down, because
    an unfinished visit is always shorter than the finished one it becomes.
    """
    now = now or datetime.utcnow()
    completed = {stage: [] for stage in stage_names}
    current = {stage: [] for stage in stage_names}
    aging, lead_times, closed_events = [], [], []

    for project in projects:
        timeline = stage_timeline(project, notes_by_project.get(project["id"], []), stage_names[0])
        if not timeline:
            continue

        for index, (stage, entered) in enumerate(timeline):
            if index + 1 < len(timeline):
                days = (timeline[index + 1][1] - entered).total_seconds() / 86400
                completed.setdefault(stage, []).append(days)
            else:
                days = (now - entered).total_seconds() / 86400
                if stage != terminal_stage:
                    current.setdefault(stage, []).append(days)
                    aging.append({"project": project, "stage": stage, "days": days, "since": entered})

        final_stage, reached_at = timeline[-1]
        if final_stage == terminal_stage:
            lead_times.append((reached_at - timeline[0][1]).total_seconds() / 86400)
            closed_events.append(reached_at)

    stages = []
    for stage in stage_names:
        durations = completed.get(stage, [])
        open_now = current.get(stage, [])
        stages.append({
            "stage": stage,
            "visits": len(durations),
            "avg_days": (sum(durations) / len(durations)) if durations else None,
            "median_days": median(durations) if durations else None,
            "max_days": max(durations) if durations else None,
            "in_stage_now": len(open_now),
            "oldest_now": max(open_now) if open_now else None,
        })

    aging.sort(key=lambda row: row["days"], reverse=True)

    # closures per calendar month, most recent last
    throughput = {}
    for moment in closed_events:
        throughput[moment.strftime("%Y-%m")] = throughput.get(moment.strftime("%Y-%m"), 0) + 1

    slowest = max(
        (s for s in stages if s["avg_days"] is not None and s["stage"] != terminal_stage),
        key=lambda s: s["avg_days"], default=None,
    )

    return {
        "stages": stages,
        "aging": aging,
        "slowest": slowest,
        "lead_avg": (sum(lead_times) / len(lead_times)) if lead_times else None,
        "lead_median": median(lead_times) if lead_times else None,
        "completed_count": len(lead_times),
        "throughput": sorted(throughput.items()),
        "measured_projects": len(projects),
    }


def stage_sla_state(project, sla_by_stage, terminal_stage, now=None):
    """How this project is tracking against its current stage's SLA.

    Returns None when the stage has no SLA set, when the project has already
    reached the terminal stage (a finished project isn't stuck), or when the
    entry time is unknown. Otherwise: days in stage, the target, and whether
    it has breached.
    """
    sla_days = sla_by_stage.get(project["stage"])
    if not sla_days or project["stage"] == terminal_stage:
        return None
    entered = _parse(project["stage_entered_at"]) if project["stage_entered_at"] else None
    if entered is None:
        return None
    days = ((now or datetime.utcnow()) - entered).total_seconds() / 86400
    return {
        "days": days,
        "sla_days": sla_days,
        "over_by": days - sla_days,
        "breached": days > sla_days,
    }


def sla_by_stage(stage_rows):
    """{stage name: sla_days} for stages that actually have one set."""
    return {row["name"]: row["sla_days"] for row in stage_rows if row["sla_days"]}
