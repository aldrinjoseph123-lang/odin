import { useCallback, useState } from "react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { PlanStage } from "@/lib/api"
import { cn } from "@/lib/utils"
import { dayOf, fmtDate, monthTicks } from "@/lib/format"

// Plan against reality, one row per stage: the baseline as a thin grey line
// under the row, the current plan as an outlined bar, what actually happened
// as a solid bar, and the forecast for what is left as a pale bar. A stage
// that is running late shows its overrun past the plan in the warn colour.
// Used on the project page, in the report and (drawn again) in its PDF.
export function PlanGantt({ stages, today, target, compact = false }: { stages: PlanStage[]; today: string; target?: string | null; compact?: boolean }) {
  const all = stages.flatMap((s) => [s.plan_start, s.plan_end, s.base_start, s.base_end, s.actual_start, s.actual_end, s.forecast_start, s.forecast_end])
    .concat([today, target ?? null]).filter((x): x is string => !!x).map(dayOf)
  const t0 = Math.min(...all) - 3 * 864e5, t1 = Math.max(...all) + 3 * 864e5
  const pct = (iso: string) => `${((dayOf(iso) - t0) / (t1 - t0)) * 100}%`
  const span = (a: string, b: string) => ({ left: pct(a), width: `max(3px, calc(${pct(b)} - ${pct(a)}))` })
  const [width, setWidth] = useState(0)
  const measure = useCallback((el: HTMLDivElement | null) => {
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const months = monthTicks(t0, t1, width ? Math.max(2, Math.floor(width / 70)) : 8)
  const row = compact ? "h-7" : "h-9"
  return (
    <div className="text-[12px]">
      <div className="grid grid-cols-[minmax(100px,160px)_minmax(0,1fr)] gap-x-3">
        <span />
        <div ref={measure} className="relative h-5 text-[11px] text-muted-foreground">
          {months.map((m) => <span key={m.t} className="absolute top-0 -translate-x-1/2" style={{ left: `${((m.t - t0) / (t1 - t0)) * 100}%` }}>{m.label}</span>)}
        </div>
        {stages.map((s) => {
          const late = s.status === "current" && s.plan_end && s.forecast_end && s.forecast_end > s.plan_end
          const label = `${s.name}: plan ${s.plan_start ? `${fmtDate(s.plan_start)} → ${fmtDate(s.plan_end)}` : "not set"}; ${s.actual_start ? `actual from ${fmtDate(s.actual_start)}${s.actual_end ? ` to ${fmtDate(s.actual_end)}` : ""}` : "not started"}; forecast to end ${fmtDate(s.forecast_end)}${s.slip_days ? `, ${s.slip_days > 0 ? `${s.slip_days} d late` : `${-s.slip_days} d early`}` : ""}`
          return (
            <div key={s.id} className="contents">
              <span className={cn("flex items-center truncate", row, s.status === "current" ? "font-semibold" : s.status === "next" ? "text-nav-fg" : "")}>{s.name}</span>
              <Tooltip>
                <TooltipTrigger render={<div />} tabIndex={0} role="img" aria-label={label} className={cn("relative outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50", row)}>
                  <span className="absolute inset-y-0 w-[1.5px] bg-primary/60" style={{ left: pct(today) }} aria-hidden />
                  {target && <span className="absolute inset-y-0 w-0 border-l border-dashed border-bad-line" style={{ left: pct(target) }} aria-hidden />}
                  {s.base_start && s.base_end && <span className="absolute bottom-0.5 h-[3px] rounded-full bg-input" style={span(s.base_start, s.base_end)} aria-hidden />}
                  {s.plan_start && s.plan_end && <span className="absolute top-1/2 h-3.5 -translate-y-1/2 rounded-full border-[1.5px] border-primary/70" style={span(s.plan_start, s.plan_end)} aria-hidden />}
                  {s.actual_start && (s.actual_end || s.status === "current") && (
                    <span className={cn("absolute top-1/2 h-2 -translate-y-1/2 rounded-full", late ? "bg-warn-line" : s.status === "current" ? "bg-primary" : "bg-foreground/70")} style={span(s.actual_start, s.actual_end ?? today)} aria-hidden />
                  )}
                  {s.forecast_start && s.forecast_end && (s.status === "next" || (s.status === "current" && s.forecast_end > today)) && (
                    <span className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-primary/30" style={span(s.status === "current" ? today : s.forecast_start, s.forecast_end)} aria-hidden />
                  )}
                </TooltipTrigger>
                <TooltipContent>{label}</TooltipContent>
              </Tooltip>
            </div>
          )
        })}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground" aria-label="Legend">
        <li className="flex items-center gap-2"><span className="h-3 w-5 rounded-full border-[1.5px] border-primary/70" />Plan</li>
        <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-foreground/70" />Actual</li>
        <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-primary/30" />Forecast</li>
        {stages.some((s) => s.base_start) && <li className="flex items-center gap-2"><span className="h-[3px] w-5 rounded-full bg-input" />Baseline</li>}
        <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-warn-line" />Running late</li>
        <li className="flex items-center gap-2"><span className="h-3 w-[1.5px] bg-primary/60" />Today</li>
        {target && <li className="flex items-center gap-2"><span className="h-3 w-0 border-l border-dashed border-bad-line" />Target</li>}
      </ul>
    </div>
  )
}

// The health pill: RAG in its state colour, with the word, never colour alone.
export function RagPill({ rag, className }: { rag: "green" | "amber" | "red" | "done"; className?: string }) {
  const map = { green: ["bg-ok-soft text-ok", "On track"], amber: ["bg-warn-soft text-warn", "At risk"], red: ["bg-bad-soft text-bad", "Off track"], done: ["bg-muted text-muted-foreground", "Complete"] } as const
  const [cls, word] = map[rag]
  return <span className={cn("inline-flex items-center gap-2 rounded-full px-3 py-1 text-[12px] font-semibold", cls, className)}><span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />{word}</span>
}
