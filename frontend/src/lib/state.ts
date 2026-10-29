import type { FlowState, Rag } from "@/lib/api"

// ---- one health vocabulary: colour is a state and nothing else ---------------
// Every page says a rollout's health in the plan's words (On track / At risk /
// Off track) and gives the reason as detail (10 Oct 2026, the user's call).
// STATE: the schedule reading every list carries (target date and stage SLA).
export const STATE: Record<FlowState, { label: string; ring: string; chip: string; dot: string }> = {
  overdue:  { label: "Off track", ring: "border-bad-line ring-bad-soft",   chip: "bg-bad-soft text-bad",   dot: "bg-bad-line" },
  over_sla: { label: "At risk",   ring: "border-warn-line ring-warn-soft", chip: "bg-warn-soft text-warn", dot: "bg-warn-line" },
  due_soon: { label: "At risk",   ring: "border-warn-line ring-warn-soft", chip: "bg-warn-soft text-warn", dot: "bg-warn-line" },
  on_track: { label: "On track",  ring: "border-foreground ring-muted",    chip: "bg-muted text-muted-foreground", dot: "bg-ok-line" },
}

// HEALTH: the plan's verdict (services/plan.py, which also weighs the forecast
// and blockers), in the same words.
export const HEALTH: Record<Rag, { label: string; tone: string }> = {
  red:   { label: "Off track", tone: "bg-bad-soft text-bad" },
  amber: { label: "At risk",   tone: "bg-warn-soft text-warn" },
  green: { label: "On track",  tone: "bg-muted text-nav-fg" },
  done:  { label: "Complete",  tone: "bg-muted text-muted-foreground" },
  none:  { label: "No plan yet", tone: "bg-muted text-muted-foreground" },
}
