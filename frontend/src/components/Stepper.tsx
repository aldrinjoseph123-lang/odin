import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { FlowState } from "@/lib/api"
import { STATE } from "@/lib/state"
import { cn } from "@/lib/utils"

// ---- the 7-dot stepper: one row's whole flow at a glance ----------------------
export function Stepper({ stages, index, state, selected }: { stages: string[]; index: number; state: FlowState; selected: boolean }) {
  return (
    <div className="flex items-center" role="img" aria-label={`Stage ${index + 1} of ${stages.length}: ${stages[index]}`}>
      {stages.map((s, i) => (
        <div key={s} className="flex flex-1 items-center last:flex-none">
          <Tooltip>
            <TooltipTrigger
              render={<span />}
              className={cn(
                "block h-3 w-3 shrink-0 rounded-full border-[1.5px] bg-transparent",
                i < index && "border-ok-line bg-ok-line",
                i === index && cn("ring-[3px]", STATE[state].ring, selected && "scale-110"),
                i > index && "border-input",
              )}
            />
            <TooltipContent>{s}{i === index ? " · current" : i < index ? " · done" : ""}</TooltipContent>
          </Tooltip>
          {i < stages.length - 1 && <span className={cn("h-[1.5px] flex-1", i < index ? "bg-ok-line" : "bg-input")} />}
        </div>
      ))}
    </div>
  )
}
