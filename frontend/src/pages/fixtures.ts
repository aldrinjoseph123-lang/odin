// Small, typed slices of what the API sends, for the page tests.
import type { CalendarData, DashboardData, FlowData, FlowRow, ProjectsData, User } from "@/lib/api"

export const admin: User = {
  id: 1, name: "Admin User", role: "Admin", kind: "internal", must_change_password: false, home: "dashboard",
  permissions: ["view_board", "manage_settings", "edit_project", "create_project", "edit_project_stage", "view_reports"],
  nav: { active_alert_count: 0, my_open_task_count: 0, unread_notifications: 0, projects_nav_url: "/projects" } as User["nav"],
  theme: "light", accent: "blue", avatar_url: null,
}

const stages = ["PO Received", "Scoping", "Sensor pilot", "Deployment", "Closed"]
export const flowRow = (over: Partial<FlowRow>): FlowRow => ({
  id: 1, name: "EDR Rollout - Globex", client: "Globex", stage: "Scoping", stages, stage_index: 1, owner_name: "Admin User", mine: true,
  team: [{ id: 1, name: "Admin User", avatar_url: null }], approval: null, delivery_mode: "Direct", target_end_date: "2026-12-01",
  days_in_stage: 3, sla_days: 5, over_by: null, state: "on_track", open_tasks: 1, total_tasks: 2, late_tasks: 0, late_since: null,
  next_task: { title: "Collect asset inventory", due_date: "2026-10-02", assignee: "Priya" }, updated_at: "2026-09-28T10:00:00", idle_days: 1, stale: false,
  start_date: "2026-09-01", next_stage: "Sensor pilot", can_move: true, signoff_needed: false, gate_blocked: false, gate_reasons: [], ...over,
})
export const flow: FlowData = {
  stages, today: "2026-09-29", can_move: true,
  rows: [
    flowRow({ id: 1, name: "Late one", state: "overdue", target_end_date: "2026-09-01" }),
    flowRow({ id: 2, name: "Stuck one", state: "over_sla", over_by: 3 }),
    flowRow({ id: 3, name: "Fine one" }),
    flowRow({ id: 4, name: "Other fine", client: "Initech", stage: "Deployment", stage_index: 3, mine: false, approval: "pending" }),
  ],
  counts: { overdue: 1, over_sla: 1, due_soon: 0, on_track: 2, late_tasks: 0 },
}

export const dashboard: DashboardData = {
  today: "2026-09-29", version: 7, is_custom: false, scope_full: true,
  layout: [{ id: "kpis", w: 3, settings: { tiles: ["active", "overdue"] } }, { id: "timeline", w: 2, settings: { show: "all", limit: 12 } }, { id: "progress", w: 1, settings: {} }, { id: "alerts", w: 1, settings: { limit: 8 } }],
  catalogue: [
    { id: "kpis", title: "Headline numbers", blurb: "", w: 3, multiple: false, settings: [{ key: "tiles", label: "Tiles", kind: "multi", default: ["active"], choices: ["active", "overdue"] }] },
    { id: "timeline", title: "Timeline", blurb: "", w: 2, multiple: false, settings: [{ key: "show", label: "Show", kind: "choice", default: "all", choices: ["all", "attention"] }, { key: "limit", label: "Rows", kind: "int", default: 12, min: 5, max: 50 }] },
    { id: "progress", title: "Portfolio progress", blurb: "", w: 1, multiple: false, settings: [] },
    { id: "alerts", title: "Open alerts", blurb: "", w: 1, multiple: false, settings: [{ key: "limit", label: "Items", kind: "int", default: 8, min: 5, max: 30 }] },
    { id: "team", title: "Team", blurb: "who is on what", w: 1, multiple: false, settings: [] },
    { id: "custom", title: "Custom metric", blurb: "your own", w: 1, multiple: true, settings: [
      { key: "title", label: "Title", kind: "text", default: "Custom metric", max: 40 },
      { key: "measure", label: "Measure", kind: "choice", default: "rollouts_by_stage", choices: ["rollouts_by_stage", "rollouts_by_owner"] },
      { key: "chart", label: "Chart", kind: "choice", default: "bar", choices: ["number", "bar", "pie", "list"] },
      { key: "top", label: "Top", kind: "int", default: 6, min: 3, max: 12 }] },
  ],
  data: {
    kpis: { counts: { active: 4, overdue: 1, over_sla: 1, due_soon: 0, awaiting: 1, idle: 0 }, before: { active: 3, overdue: 2, over_sla: 1, due_soon: 0, awaiting: 0, idle: 0 }, since: "2026-09-22", moved_this_week: 5,
            series: { active: [{ day: "2026-09-28", v: 3 }, { day: "2026-09-29", v: 4 }], overdue: [], over_sla: [], due_soon: [], awaiting: [], idle: [] },
            detail: { active: [{ id: 1, name: "EDR Rollout - Globex", client: "Globex", stage: "Scoping", text: "On track" }], overdue: [{ id: 1, name: "EDR Rollout - Globex", client: "Globex", stage: "Scoping", text: "12 d late" }], over_sla: [], due_soon: [], awaiting: [], idle: [] } },
    aggregates: { rollouts_by_stage: [{ key: "Scoping", count: 4 }], rollouts_by_owner: [{ key: "Admin User", count: 4 }] },
    attention: [{ id: 1, name: "EDR Rollout - Globex", client: "Globex", stage: "Scoping", worst: "overdue", reasons: [{ kind: "overdue", text: "5 d late" }] }],
    timeline: [{ id: 1, name: "EDR Rollout - Globex", client: "Globex", stage: "Scoping", start_date: "2026-09-01", target_end_date: "2026-12-01", state: "on_track", progress: 0.25, team: [],
                milestones: [{ name: "Pilot go-live", date: "2026-10-15", done: false, missed: false }, { name: "Kick-off held", date: "2026-09-10", done: true, missed: false }] }],
    progress: { done: 3, current: 4, pending: 10, pct: 18 }, stages: [{ stage: "Scoping", count: 4, late: 0, warn: 0 }], completion: Array.from({ length: 56 }, (_, i) => ({ day: `2026-08-${String(i + 1).padStart(2, "0")}`, count: i % 3 })),
    schedule: { due: [], approvals: [] }, team: { people: [], unassigned: 0 }, activity: [], alerts: [{ id: 1, project_id: 1, project: "EDR Rollout - Globex", type: "project_overdue", title: "Rollout overdue", severity: "critical", created_at: "2026-09-29T08:00:00" }],
    mywork: { tasks: [], owned: 2 }, cycle: null,
    workload: { today: "2026-09-29", weeks: ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"], capacity_default: 30, warn_pct: 90, over: 0, heavy: 0, people: [] },
  },
}

export const projects: ProjectsData = {
  rows: [{ id: 1, name: "EDR Rollout - Globex", client: "Globex", po_number: "PO-1", stage: "Scoping", stages, stage_index: 1, closed: false, state: "on_track", owner_name: "Admin User", delivery_mode: "Direct", vendor_name: null, product_name: null, target_end_date: "2026-12-01", updated_at: "2026-09-28T10:00:00", total_tasks: 2, open_tasks: 1, team: [], fields: ["UAE"] }],
  total: 1, page: 1, total_pages: 1, sort: "updated", dir: "desc", stages: ["Scoping"], delivery_modes: ["Direct"], can_create: true, pending: 0,
  fields: [{ id: 1, name: "Region", kind: "choice" }], field_filters: [{ id: 1, name: "Region", choices: ["UAE", "KSA"] }],
}

export const calendarData: CalendarData = {
  month: "2026-09", today: "2026-09-29", from: "2026-08-24", to: "2026-10-19",
  spans: [{ id: 1, name: "EDR Rollout - Globex", client: "Globex", stage: "Scoping", start_date: "2026-09-01", target_end_date: "2026-10-15", state: "on_track" }],
  targets: [{ id: 1, name: "EDR Rollout - Globex", client: "Globex", day: "2026-10-15", state: "on_track" }],
  tasks: [1, 2, 3, 4].map((i) => ({ id: i, project_id: 1, title: `Task ${i}`, day: "2026-09-10", done: 0, project: "EDR Rollout - Globex", who: "Priya", can_edit: true })),
  moves: [{ project_id: 1, project: "EDR Rollout - Globex", day: "2026-09-08", prev_stage: "PO Received", stage: "Scoping", who: "Admin" }],
  approvals: [],
  milestones: [{ id: 1, project_id: 1, project: "EDR Rollout - Globex", name: "Pilot go-live", day: "2026-09-17", stage: "Scoping", done: 0, customer_visible: true }],
}
