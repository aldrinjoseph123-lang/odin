import type { FlowState } from "@/lib/api"
import { STATE } from "@/lib/state"
import { daysLate, fmtDate } from "@/lib/format"
import { cn } from "@/lib/utils"

// A rollout's health as one chip, the same on every page: the plan word and
// the reason ("At risk · due 30 Nov"). On track draws nothing unless `quiet`
// text is given: colour is for trouble. Pass `text` when the page knows the
// reason better (the Flow's "6 d over SLA").
export function StateChip({ state, target, text, quiet, className }: { state: FlowState; target?: string | null; text?: string; quiet?: string; className?: string }) {
  if (state === "on_track") return quiet ? <span className={cn("text-[12px] text-muted-foreground", className)}>{quiet}</span> : null
  const why = text ?? (state === "overdue" ? `overdue ${daysLate(target ?? null)} d` : state === "due_soon" ? `due ${fmtDate(target)}` : "over SLA")
  return (
    <span className={cn("whitespace-nowrap rounded-md px-2 py-1 text-[12px] font-medium", STATE[state].chip, className)}>
      {STATE[state].label}<span className="font-normal"> · {why}</span>
    </span>
  )
}
