import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { FlowState } from "@/lib/api"
import { cn } from "@/lib/utils"

// ---- the progress bar: one row's whole flow at a glance ----------------------
// A straight line of rounded segments, one per stage (9 Oct 2026: replaced the
// dots-on-a-line stepper). Done stages are green, the current one wears its
// state (ink when on track, amber when due soon or over SLA, red when overdue),
// upcoming ones are a quiet grey. With `columns` (the shared stage order of
// every row on screen) each segment sits in its stage's column, so the lead can
// read down a column; a stage this project doesn't have leaves a gap.
const CURRENT: Record<FlowState, string> = {
  on_track: "bg-foreground",
  due_soon: "bg-warn-line",
  over_sla: "bg-warn-line",
  overdue: "bg-bad-line",
}

// `compact` (a 96 px slot: My work, a person, the projects table) draws one
// continuous bar instead, so ten or more stages never shrink to slivers.
export function Stepper({ stages, index, state, selected, columns, compact }: { stages: string[]; index: number; state: FlowState; selected: boolean; columns?: string[]; compact?: boolean }) {
  if (compact) {
    const n = Math.max(stages.length, 1), label = `Stage ${index + 1} of ${stages.length}: ${stages[index]}`
    return (
      <Tooltip>
        <TooltipTrigger render={<span />} role="img" aria-label={label} className="relative flex h-4 items-center before:absolute before:inset-x-0 before:-inset-y-1 before:content-['']">
          <span className="flex h-1.5 w-full overflow-hidden rounded-full bg-input/70">
            <span className="h-full bg-ok-line" style={{ width: `${(index / n) * 100}%` }} />
            <span className={cn("h-full rounded-r-full", CURRENT[state])} style={{ width: `${100 / n}%` }} />
          </span>
        </TooltipTrigger>
        <TooltipContent>{label}</TooltipContent>
      </Tooltip>
    )
  }
  const shared = columns && columns.length > 1 ? columns : null
  const col = (i: number) => (shared ? Math.max(0, shared.indexOf(stages[i])) : i) + 1
  return (
    <div className="grid h-4 items-center gap-1" style={{ gridTemplateColumns: `repeat(${shared ? shared.length : stages.length}, minmax(0, 1fr))` }}
      role="img" aria-label={`Stage ${index + 1} of ${stages.length}: ${stages[index]}`}>
      {stages.map((s, i) => (
        <Tooltip key={s}>
          <TooltipTrigger
            render={<span />}
            style={{ gridColumnStart: col(i) }}
            className={cn(
              // a taller invisible hit area around a 6 px bar
              "relative block h-1.5 rounded-full transition-colors before:absolute before:inset-x-0 before:-inset-y-1.5 before:content-['']",
              i < index && "bg-ok-line",
              i === index && cn(CURRENT[state], selected && "h-2"),
              i > index && "bg-input/70",
            )}
          />
          <TooltipContent>{s}{i === index ? " · current" : i < index ? " · done" : ""}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  )
}
