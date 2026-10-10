import type { FlowState } from "@/lib/api"
import { STATE } from "@/lib/state"
import { daysLate, fmtDate } from "@/lib/format"
import { cn } from "@/lib/utils"

// A rollout's state as one chip, the same on every page (critique 10 Oct: the
// Projects page showed an overdue rollout as on track). On track draws nothing
// unless `quiet` text is given: colour is for trouble. Pass `text` when the
// page knows more (the Flow's "11 d · 6 over SLA").
export function StateChip({ state, target, text, quiet, className }: { state: FlowState; target?: string | null; text?: string; quiet?: string; className?: string }) {
  if (state === "on_track") return quiet ? <span className={cn("text-[12px] text-muted-foreground", className)}>{quiet}</span> : null
  const words = text ?? (state === "overdue" ? `Overdue ${daysLate(target ?? null)} d` : state === "due_soon" ? `Due ${fmtDate(target)}` : "Over SLA")
  return (
    <span className={cn("whitespace-nowrap rounded-md px-2 py-1 text-[12px] font-medium", STATE[state].chip, className)}>
      <span className="sr-only">{STATE[state].label}: </span>{words}
    </span>
  )
}
