import type { WorkloadCell } from "@/lib/api"
import { shortDay } from "@/lib/format"

// Pure wording for the workload views (page, dashboard widget, task picker);
// tested in workload.test.ts. Hours and counts only. Amber is a heavy week, red
// an over-capacity one: both are states, never decoration.
export const hrs = (h: number) => `${Number.isInteger(h) ? h : h.toFixed(1)} h`
export const weekLabel = (iso: string, i: number) => (i === 0 ? "This week" : `Week of ${shortDay(iso)}`)
export const levelWord = (l: WorkloadCell["level"]) => (l === "over" ? "Over capacity" : l === "warn" ? "Heavy" : "")
export const LEVEL_BAR: Record<WorkloadCell["level"], string> = { ok: "bg-nav-fg/60", warn: "bg-warn-line", over: "bg-bad-line" }
export const LEVEL_TEXT: Record<WorkloadCell["level"], string> = { ok: "", warn: "text-warn", over: "text-bad" }
// the hover and screen-reader text of one cell: where the hours come from
export const cellTitle = (c: WorkloadCell, capacity: number) =>
  `${hrs(c.hours)} of ${hrs(capacity)} (${c.pct} %): ${hrs(c.task_hours)} in ${c.tasks} task${c.tasks === 1 ? "" : "s"}${c.pm_hours ? `, ${hrs(c.pm_hours)} managing rollouts` : ""}`
// the assignee picker's line: "Priya · 34 h that week" (just the name before the week is known)
export const pickerHint = (name: string, week?: { hours: number }) => (week ? `${name} · ${hrs(week.hours)} that week` : name)
