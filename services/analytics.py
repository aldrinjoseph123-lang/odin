"""Cycle-time analytics: how long projects actually spend in each stage.

Everything here is derived from data the app already stores — every stage
change writes a status_notes row carrying the stage and a timestamp, so the
note history *is* the stage history. Nothing new is recorded to support this
module.

build_cycle_times() is pure computation over rows, so it can be tested without
a request context and reused by any caller.
"""
from datetime import datetime, timezone
from statistics import median
from zoneinfo import ZoneInfo

# (working days, time zone) for pure callers: every day counts, in UTC
CALENDAR = ((frozenset(range(7)), frozenset()), ZoneInfo("UTC"))


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


def build_cycle_times(projects, notes_by_project, stage_names, terminal_stage, now=None, clock=None):
    """Per-stage dwell statistics, current aging, lead time and throughput.

    Durations are measured with `clock` (see clock()): pass the workspace's
    to count working days like the SLAs do; without one every day counts.

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
                days = working_days(entered, timeline[index + 1][1], clock)
                completed.setdefault(stage, []).append(days)
            else:
                days = working_days(entered, now, clock)
                if stage != terminal_stage:
                    current.setdefault(stage, []).append(days)
                    aging.append({"project": project, "stage": stage, "days": days, "since": entered})

        final_stage, reached_at = timeline[-1]
        if final_stage == terminal_stage:
            lead_times.append(working_days(timeline[0][1], reached_at, clock))
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
    days = days_in_stage(project["stage_entered_at"], now)
    if days is None:
        return None
    return {
        "days": days,
        "sla_days": sla_days,
        "over_by": days - sla_days,
        "breached": days > sla_days,
    }


def clock(db=None):
    """(working-day calendar, time zone) of the workspace, for working_days()."""
    from policies import policy
    from services import workdays
    return workdays.calendar(db), ZoneInfo(policy("timezone", db))


def busiest_template(db, scope):
    """The stage template most of the visible rollouts use (ties: the
    workspace default, then the oldest), so Cycle time opens on real data."""
    from policies import policy
    scope_sql, scope_params = scope
    return db.execute(
        "SELECT t.id, t.name FROM stage_templates t LEFT JOIN projects p ON p.stage_template_id = t.id AND p.deleted_at IS NULL"
        f"{scope_sql} GROUP BY t.id ORDER BY COUNT(p.id) DESC, t.id = ? DESC, t.id LIMIT 1",
        (*scope_params, policy("default_template") or 0)).fetchone()


def working_days(start, end, clock=None):
    """Fractional days from `start` to `end` (naive UTC datetimes) that fall on
    working days in the workspace's time zone, part days included: the one
    measure of time in a stage, so the SLA clock never runs backwards over a
    weekend. Without a clock every day counts."""
    from services import workdays
    cal, tz = clock or CALENDAR
    local = lambda d: d.replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)   # noqa: E731
    return workdays.elapsed(local(start), local(end), cal)


def days_in_stage(entered_at, now=None, clock_=None):
    """Working days since `entered_at` (fractional), or calendar days when the
    workspace counts those (services/workdays.py)."""
    entered = _parse(entered_at) if entered_at else None
    if entered is None:
        return None
    return working_days(entered, now or datetime.utcnow(), clock_ or clock())


def sla_by_stage(stage_rows):
    """{stage name: sla_days} for stages that actually have one set."""
    return {row["name"]: row["sla_days"] for row in stage_rows if row["sla_days"]}
