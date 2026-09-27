import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { FlowState } from "@/lib/api"
import { STATE } from "@/lib/state"
import { cn } from "@/lib/utils"

// ---- the stepper: one row's whole flow at a glance ----------------------------
// With `columns` (the shared stage order of every row on screen), each dot sits
// in its stage's column, so the lead can read down a column and see who is in
// Deployment. A stage this project doesn't have leaves a gap on its line.
export function Stepper({ stages, index, state, selected, columns }: { stages: string[]; index: number; state: FlowState; selected: boolean; columns?: string[] }) {
  const n = columns && columns.length > 1 ? columns.length - 1 : Math.max(stages.length - 1, 1)
  const pos = (i: number) => `${((columns && columns.length > 1 ? Math.max(0, columns.indexOf(stages[i])) : i) / n) * 100}%`
  const last = stages.length - 1
  return (
    <div className="relative mx-1.5 h-3" role="img" aria-label={`Stage ${index + 1} of ${stages.length}: ${stages[index]}`}>
      <span className="absolute top-1/2 h-[1.5px] -translate-y-1/2 bg-input" style={{ left: pos(0), width: `calc(${pos(last)} - ${pos(0)})` }} aria-hidden />
      {index > 0 && <span className="absolute top-1/2 h-[1.5px] -translate-y-1/2 bg-ok-line" style={{ left: pos(0), width: `calc(${pos(index)} - ${pos(0)})` }} aria-hidden />}
      {stages.map((s, i) => (
        <Tooltip key={s}>
          <TooltipTrigger
            render={<span />}
            style={{ left: pos(i) }}
            className={cn(
              "absolute top-0 block h-3 w-3 -translate-x-1/2 rounded-full border-[1.5px]",
              selected ? "bg-accent" : "bg-background",   // opaque, so the line stops at the ring
              i < index && "border-ok-line bg-ok-line",
              i === index && cn("ring-[3px]", STATE[state].ring, selected && "scale-110"),
              i > index && "border-input",
            )}
          />
          <TooltipContent>{s}{i === index ? " · current" : i < index ? " · done" : ""}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  )
}
