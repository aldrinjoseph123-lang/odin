import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { PlanStage } from "@/lib/api"
import { cn } from "@/lib/utils"
import { dayOf, fmtDate, monthTicks } from "@/lib/format"
import { useWidth } from "@/lib/useMeasure"

// Plan against reality, one row per stage: the baseline as a thin grey line
// under the row, the current plan as an outlined bar, what actually happened
// as a solid bar, and the forecast for what is left as a pale bar. A stage
// that is running late shows its overrun past the plan in the warn colour.
// Used on the project page, in the report and (drawn again) in its PDF.
export function PlanGantt({ stages, today, target, compact = false }: { stages: PlanStage[]; today: string; target?: string | null; compact?: boolean }) {
  // red only when the target has passed with work still open; otherwise the target is a quiet ink line
  const overdue = !!target && target < today && stages.some((s) => s.status === "current" || s.status === "next")
  const all = stages.flatMap((s) => [s.plan_start, s.plan_end, s.base_start, s.base_end, s.actual_start, s.actual_end, s.forecast_start, s.forecast_end])
    .concat([today, target ?? null]).filter((x): x is string => !!x).map(dayOf)
  const t0 = Math.min(...all) - 3 * 864e5, t1 = Math.max(...all) + 3 * 864e5
  const at = (t: number) => `${((t - t0) / (t1 - t0)) * 100}%`
  const pct = (iso: string) => at(dayOf(iso))
  const span = (a: string, b: string) => ({ left: pct(a), width: `max(3px, calc(${pct(b)} - ${pct(a)}))` })
  const [width, measure] = useWidth<HTMLDivElement>()
  const months = monthTicks(t0, t1, width ? Math.max(2, Math.floor(width / 70)) : 8)
  // a light line at each Monday (Odin's weeks start on Monday), numbered when there is room
  const weeks = mondays(t0, t1)
  const weekLabels = width > 0 && width / Math.max(weeks.length, 1) >= 28
  const row = compact ? "h-9" : "h-11"
  const grid = (
    <>
      {weeks.map((w) => <span key={w} className="absolute inset-y-0 w-px bg-border" style={{ left: at(w) }} aria-hidden />)}
      <span className="absolute inset-y-0 w-[1.5px] bg-foreground" style={{ left: pct(today) }} aria-hidden />
      {target && <span className={cn("absolute inset-y-0 w-0 border-l border-dashed", overdue ? "border-bad-line" : "border-foreground/60")} style={{ left: pct(target) }} aria-hidden />}
    </>
  )
  return (
    <div className="text-[12px]">
      <div className="grid grid-cols-[minmax(120px,200px)_minmax(0,1fr)] gap-x-4">
        <span />
        {/* the time axis: months, then each week's Monday; today and the target named */}
        <div ref={measure} className={cn("relative text-[11px] text-muted-foreground", weekLabels ? "h-10" : "h-6")}>
          {months.map((m) => <span key={m.t} className="absolute top-0 -translate-x-1/2 font-medium text-foreground" style={{ left: at(m.t) }}>{m.label}</span>)}
          {weekLabels && weeks.map((w) => <span key={w} className="absolute top-5 -translate-x-1/2 tabular-nums" style={{ left: at(w) }}>{new Date(w).getUTCDate()}</span>)}
          <span className="absolute bottom-0 h-1.5 w-[1.5px] bg-foreground" style={{ left: pct(today) }} aria-hidden />
        </div>
        {stages.map((s) => {
          const late = s.status === "current" && s.plan_end && s.forecast_end && s.forecast_end > s.plan_end
          const label = `${s.name}: plan ${s.plan_start ? `${fmtDate(s.plan_start)} → ${fmtDate(s.plan_end)}` : "not set"}; ${s.actual_start ? `actual from ${fmtDate(s.actual_start)}${s.actual_end ? ` to ${fmtDate(s.actual_end)}` : ""}` : "not started"}; forecast to end ${fmtDate(s.forecast_end)}${s.slip_days ? `, ${s.slip_days > 0 ? `${s.slip_days} d late` : `${-s.slip_days} d early`}` : ""}`
          return (
            <div key={s.id} className="contents">
              <div className={cn("flex min-w-0 flex-col justify-center border-t border-border", row)}>
                <span className={cn("truncate", s.status === "current" ? "font-semibold" : s.status === "next" ? "text-nav-fg" : "")} title={s.name}>{s.name}</span>
                <span className={cn("truncate text-[12px] tabular-nums", late ? "text-warn" : "text-muted-foreground")}>{stageDates(s)}</span>
              </div>
              <Tooltip>
                <TooltipTrigger render={<div />} role="img" aria-label={label} className={cn("relative border-t border-border outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50", row)}>
                  {grid}
                  {s.base_start && s.base_end && <span className="absolute bottom-1 h-[3px] rounded-full bg-input" style={span(s.base_start, s.base_end)} aria-hidden />}
                  {s.plan_start && s.plan_end && <span className="absolute top-1/2 h-4 -translate-y-1/2 rounded-full border-[1.5px] border-foreground/45" style={span(s.plan_start, s.plan_end)} aria-hidden />}
                  {s.actual_start && (s.actual_end || s.status === "current") && (
                    <span className={cn("absolute top-1/2 h-2 -translate-y-1/2 rounded-full", late ? "bg-warn-line" : s.status === "current" ? "bg-foreground/75" : "bg-ok-line")} style={span(s.actual_start, s.actual_end ?? today)} aria-hidden />
                  )}
                  {s.forecast_start && s.forecast_end && (s.status === "next" || (s.status === "current" && s.forecast_end > today)) && (
                    <span className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-foreground/15" style={span(s.status === "current" ? today : s.forecast_start, s.forecast_end)} aria-hidden />
                  )}
                </TooltipTrigger>
                <TooltipContent>{label}</TooltipContent>
              </Tooltip>
            </div>
          )
        })}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground" aria-label="Legend">
        <li className="flex items-center gap-2"><span className="h-3 w-5 rounded-full border-[1.5px] border-foreground/45" />Plan</li>
        <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-ok-line" />Done</li>
        <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-foreground/75" />In progress</li>
        <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-foreground/15" />Forecast</li>
        {stages.some((s) => s.base_start) && <li className="flex items-center gap-2"><span className="h-[3px] w-5 rounded-full bg-input" />Baseline</li>}
        <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-warn-line" />Running late</li>
        <li className="flex items-center gap-2"><span className="h-3 w-[1.5px] bg-foreground" />Today, {fmtDate(today)}</li>
        {target && <li className="flex items-center gap-2"><span className={cn("h-3 w-0 border-l border-dashed", overdue ? "border-bad-line" : "border-foreground/60")} />{overdue ? "Target (passed)" : "Target"}, {fmtDate(target)}</li>}
        <li>Light lines mark each Monday.</li>
      </ul>
    </div>
  )
}

// The dates a reader wants beside the stage: done = when it ran; current =
// since when and the forecast end; upcoming = the plan (or the forecast).
function stageDates(s: PlanStage): string {
  if (s.status === "done" && s.actual_start) return `${fmtDate(s.actual_start)} → ${fmtDate(s.actual_end ?? s.actual_start)}`
  if (s.status === "current" && s.actual_start) return `since ${fmtDate(s.actual_start)} · ends ${fmtDate(s.forecast_end ?? s.plan_end)}`
  if (s.plan_start && s.plan_end) return `${fmtDate(s.plan_start)} → ${fmtDate(s.plan_end)} planned`
  if (s.forecast_start && s.forecast_end) return `${fmtDate(s.forecast_start)} → ${fmtDate(s.forecast_end)} forecast`
  return "no dates yet"
}

// Midnight-UTC timestamps of each Monday between two day stamps.
function mondays(t0: number, t1: number): number[] {
  const out: number[] = []
  const d = new Date(t0)
  d.setUTCDate(d.getUTCDate() + ((8 - d.getUTCDay()) % 7))   // the first Monday on or after t0
  for (let t = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()); t <= t1; t += 7 * 864e5) out.push(t)
  return out
}

// A status pill: a dot and the word, in the state's soft fill (one shape for the
// plan's health and the sign-off's status alike), never colour alone.
export function StatusPill({ tone, children, className }: { tone: string; children: React.ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center gap-2 rounded-full px-3 py-1 text-[12px] font-semibold", tone, className)}><span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />{children}</span>
}

// The health pill: RAG in its state colour, with the word.
export function RagPill({ rag, className }: { rag: "green" | "amber" | "red" | "done"; className?: string }) {
  const map = { green: ["bg-muted text-nav-fg", "On track"], amber: ["bg-warn-soft text-warn", "At risk"], red: ["bg-bad-soft text-bad", "Off track"], done: ["bg-muted text-muted-foreground", "Complete"] } as const
  const [cls, word] = map[rag]
  return <StatusPill tone={cls} className={className}>{word}</StatusPill>
}
