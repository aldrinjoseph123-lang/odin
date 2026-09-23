import type { FlowState } from "@/lib/api"

// ---- state vocabulary: colour is a state and nothing else -------------------
export const STATE: Record<FlowState, { label: string; ring: string; chip: string; dot: string }> = {
  overdue:  { label: "Overdue",   ring: "border-bad-line ring-bad-soft",   chip: "bg-bad-soft text-bad",   dot: "bg-bad-line" },
  over_sla: { label: "Over SLA",  ring: "border-warn-line ring-warn-soft", chip: "bg-warn-soft text-warn", dot: "bg-warn-line" },
  due_soon: { label: "Due soon",  ring: "border-warn-line ring-warn-soft", chip: "bg-warn-soft text-warn", dot: "bg-warn-line" },
  on_track: { label: "On track",  ring: "border-foreground ring-muted",    chip: "bg-muted text-muted-foreground", dot: "bg-ok-line" },
}
