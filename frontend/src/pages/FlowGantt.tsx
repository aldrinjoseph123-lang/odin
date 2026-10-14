import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react"
import { ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown, Crosshair } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { DatePicker } from "@/components/DatePicker"
import { Segmented } from "@/components/Segmented"
import { UserAvatar } from "@/components/UserAvatar"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { ApiError, flowPlan, savePlan, type GanttData, type GanttRow, type GanttStage } from "@/lib/api"
import { addDays, changedStages, daysBetween, dragPlan, setDate, workDays } from "@/lib/plan"
import { fmtDate, monthName, shortDay, weekday } from "@/lib/format"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"

// The Flow as a Gantt (13 Oct 2026, the user's call, after ReUI's "gantt-1"):
// a row per rollout (start to forecast, filled to its share done, in its health
// colour) that opens into its stages — the plan as an outlined bar, what ran
// as a solid one, the forecast pale, the baseline a thin line, as PlanGantt
// draws them — with finish-to-start arrows, today, the target, and the days
// off shaded. Whoever may edit a rollout's plan drags or resizes a stage's
// planned bar (or opens it with Enter); the change saves through the plan's
// own route, which asks why once a baseline exists.

type Zoom = "week" | "month" | "quarter"
const PX: Record<Zoom, number> = { week: 44, month: 18, quarter: 6 }
const ROW = 36, LEFT = 440
const ZOOM_KEY = "odin.gantt.zoom", OPEN_KEY = "odin.gantt.open"
const read = <T,>(k: string, d: T): T => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) as T : d } catch { return d } }
const keep = (k: string, v: unknown) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* private mode */ } }
const RAG_BAR = { red: "bg-bad-line", amber: "bg-warn-line", green: "bg-nav-fg/60", done: "bg-ok-line" } as const
const RAG_WORD = { red: "Off track", amber: "At risk", green: "On track", done: "Complete" } as const

type Edit = { row: GanttRow; index: number; mode: "move" | "start" | "end" | "pick"; days: number; start?: string; end?: string; cascade: boolean }

export default function FlowGantt({ ids, selectedId, onSelect }: { ids: number[]; selectedId: number | null; onSelect: (id: number) => void }) {
  const [data, setData] = useState<GanttData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => flowPlan().then((d) => { setData(d); setError(null) }).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load the plans")), [])
  useEffect(() => { void load() }, [load])
  const [zoom, setZoom] = useState<Zoom>(() => read<Zoom>(ZOOM_KEY, "month"))
  const [open, setOpen] = useState<number[]>(() => read<number[]>(OPEN_KEY, []))
  useEffect(() => keep(ZOOM_KEY, zoom), [zoom])
  useEffect(() => keep(OPEN_KEY, open), [open])
  const [drag, setDrag] = useState<{ row: number; index: number; mode: Edit["mode"]; x: number; days: number } | null>(null)
  const [edit, setEdit] = useState<Edit | null>(null)
  const scroller = useRef<HTMLDivElement>(null)

  const rows = useMemo(() => {
    const order = new Set(ids)
    return (data?.rows ?? []).filter((r) => order.has(r.id))
  }, [data, ids])
  // the range: a week before the earliest date (or today) to three after the latest
  const [t0, t1] = useMemo(() => {
    const today = data?.today ?? new Date().toISOString().slice(0, 10)
    const all = rows.flatMap((r) => [r.start_date, r.target_end_date, r.forecast, ...r.stages.flatMap((s) => [s.plan_start, s.plan_end, s.actual_start, s.forecast_end, s.base_end])])
      .concat(today).filter((x): x is string => !!x).sort()
    return [addDays(all[0], -7), addDays(all[all.length - 1], 21)]
  }, [rows, data])
  const px = PX[zoom]
  const span = daysBetween(t0, t1) + 1
  const x = (iso: string) => daysBetween(t0, iso) * px
  const w = (a: string, b: string) => Math.max(px, (daysBetween(a, b) + 1) * px)
  // open on today, a little in from the left, and again on a new zoom
  useLayoutEffect(() => {
    if (scroller.current && data) scroller.current.scrollLeft = Math.max(0, x(data.today) - 6 * px * (zoom === "quarter" ? 5 : 1))
  }, [zoom, data?.today, t0])   // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />
  const cal = data.calendar
  const days = Array.from({ length: span }, (_, i) => addDays(t0, i))
  const off = (iso: string) => cal?.working && cal.week.length ? !cal.week.includes((new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7) || cal.off.includes(iso)
    : ["Sat", "Sun"].includes(weekday(iso))

  // the rows the body draws: each rollout, then its stages when open
  const lines: ({ kind: "rollout"; r: GanttRow } | { kind: "stage"; r: GanttRow; s: GanttStage; i: number })[] = []
  for (const r of rows) {
    lines.push({ kind: "rollout", r })
    if (open.includes(r.id)) r.stages.forEach((s, i) => lines.push({ kind: "stage", r, s, i }))
  }
  // a drag shows where the plan would go before anything is saved
  const preview = (r: GanttRow): GanttStage[] => {
    if (!drag || drag.row !== r.id || drag.days === 0) return r.stages
    return dragPlan(r.stages, drag.index, drag.mode as "move" | "start" | "end", drag.days, true)
  }

  function startDrag(e: ReactPointerEvent<HTMLButtonElement>, r: GanttRow, i: number) {
    if (e.button !== 0) return
    const box = e.currentTarget.getBoundingClientRect()
    const at = e.clientX - box.left
    const mode = at <= 8 ? "start" : at >= box.width - 8 ? "end" : "move"
    e.currentTarget.setPointerCapture(e.pointerId)
    setDrag({ row: r.id, index: i, mode, x: e.clientX, days: 0 })
  }
  function moveDrag(e: ReactPointerEvent<HTMLButtonElement>) {
    if (!drag) return
    const d = Math.round((e.clientX - drag.x) / px)
    if (d !== drag.days) setDrag({ ...drag, days: d })
  }
  function endDrag(r: GanttRow) {
    if (!drag) return
    const { index, mode, days } = drag
    setDrag(null)
    if (days !== 0) setEdit({ row: r, index, mode, days, cascade: mode !== "start" })
  }

  const months = days.filter((d, i) => i === 0 || d.endsWith("-01"))
  const mondays = days.filter((d) => weekday(d) === "Mon")
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 px-5 pb-3">
        <Button size="sm" variant="outline" onClick={() => { if (scroller.current) scroller.current.scrollLeft = Math.max(0, x(data.today) - 6 * px) }}><Crosshair className="h-3.5 w-3.5" /> Today</Button>
        <Segmented label="Zoom" value={zoom} onChange={setZoom} options={[{ value: "week", label: "Week" }, { value: "month", label: "Month" }, { value: "quarter", label: "Quarter" }]} />
        <Button size="sm" variant="ghost" onClick={() => setOpen(open.length ? [] : rows.map((r) => r.id))}>
          {open.length ? <><ChevronsDownUp className="h-3.5 w-3.5" /> Close all</> : <><ChevronsUpDown className="h-3.5 w-3.5" /> Open every rollout</>}</Button>
        <ul className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted-foreground" aria-label="Legend">
          <li className="flex items-center gap-2"><span className="h-3 w-5 rounded-md border-[1.5px] border-foreground/45" />Plan</li>
          <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-ok-line" />Done</li>
          <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-foreground/75" />In progress</li>
          <li className="flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-foreground/15" />Forecast</li>
          <li className="flex items-center gap-2"><span className="h-[3px] w-5 rounded-full bg-input" />Baseline</li>
          <li className="flex items-center gap-2"><span className="h-3 w-0 border-l border-dashed border-foreground/60" />Target</li>
        </ul>
      </div>
      <div ref={scroller} className="relative min-h-0 flex-1 overflow-auto border-t border-border" role="grid" aria-label="Rollouts on a timeline" aria-rowcount={lines.length + 1}>
        <div style={{ width: LEFT + span * px }} className="relative">
          {/* the time axis: months (or quarters' months) over days or Mondays */}
          <div className="sticky top-0 z-20 flex h-12 border-b border-border bg-card" role="row">
            <div className="sticky left-0 z-10 grid shrink-0 grid-cols-[1fr_104px_24px_56px] items-end gap-2 border-r border-border bg-card px-3 pb-2 text-[12px] text-muted-foreground" style={{ width: LEFT }} role="columnheader">
              <span>Rollout</span><span>Stage</span><span className="sr-only">Owner</span><span className="whitespace-nowrap text-right">Target</span>
            </div>
            <div className="relative h-full" style={{ width: span * px }} aria-hidden>
              {months.map((m) => <span key={m} className="absolute top-1 whitespace-nowrap pl-1 text-[12px] font-medium" style={{ left: x(m) }}>{monthName(m)} {m.slice(0, 4)}</span>)}
              {(zoom === "quarter" ? mondays : days).map((d) => (
                <span key={d} className={cn("absolute bottom-1 text-center text-[11px] tabular-nums text-muted-foreground", d === data.today && "font-semibold text-foreground")}
                  style={{ left: x(d), width: zoom === "quarter" ? 7 * px : px }}>
                  {zoom === "week" ? `${weekday(d)[0]} ${Number(d.slice(8))}` : Number(d.slice(8))}
                </span>
              ))}
            </div>
          </div>
          {/* days off shaded, Mondays ruled, today drawn through every row */}
          <div className="pointer-events-none absolute bottom-0 top-12" style={{ left: LEFT, width: span * px }} aria-hidden>
            {zoom !== "quarter" && days.filter(off).map((d) => <span key={d} className="absolute inset-y-0 bg-muted/60" style={{ left: x(d), width: px }} />)}
            {mondays.map((d) => <span key={d} className="absolute inset-y-0 w-px bg-border" style={{ left: x(d) }} />)}
            <span className="absolute inset-y-0 w-[1.5px] bg-foreground" style={{ left: x(data.today) + px / 2 }} />
          </div>
          {lines.map((line, n) => {
            const r = line.r
            if (line.kind === "rollout") {
              const stages = preview(r)
              const from = r.start_date ?? stages.find((s) => s.actual_start)?.actual_start ?? stages[0]?.plan_start ?? stages[0]?.suggested_start
              const to = r.forecast ?? r.target_end_date ?? stages[stages.length - 1]?.forecast_end
              const isOpen = open.includes(r.id)
              return (
                <div key={`r${r.id}`} role="row" aria-rowindex={n + 2} className={cn("relative flex border-b border-border", r.id === selectedId && "bg-accent/40")} style={{ height: ROW }}>
                  <div role="gridcell" className={cn("sticky left-0 z-10 grid shrink-0 grid-cols-[1fr_104px_24px_56px] items-center gap-2 border-r border-border bg-card px-3 text-[13px]", r.id === selectedId && "bg-accent")} style={{ width: LEFT }}>
                    <span className="flex min-w-0 items-center gap-1">
                      <button type="button" onClick={() => setOpen(isOpen ? open.filter((i) => i !== r.id) : [...open, r.id])} aria-expanded={isOpen} aria-label={`${isOpen ? "Close" : "Open"} the stages of ${r.name}`}
                        className="rounded-md p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground">{isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</button>
                      <button type="button" onClick={() => onSelect(r.id)} className="min-w-0 truncate text-left font-medium hover:underline" title={`${r.name} · ${r.client}`}>{r.name}</button>
                    </span>
                    <span className="truncate text-[12px] text-muted-foreground" title={r.stage}>{r.stage}</span>
                    <UserAvatar name={r.owner_name} className="h-5 w-5" textClass="text-[9px]" />
                    <span className="text-right text-[12px] tabular-nums text-muted-foreground">{r.target_end_date ? shortDay(r.target_end_date) : "—"}</span>
                  </div>
                  <div role="gridcell" className="relative" style={{ width: span * px }}>
                    {from && to && (
                      <button type="button" onClick={() => onSelect(r.id)} aria-label={`${r.name}: ${fmtDate(from)} to ${fmtDate(to)}, ${r.pct_complete}% done, ${RAG_WORD[r.rag]}`}
                        className="absolute top-1/2 h-2.5 -translate-y-1/2 overflow-hidden rounded-full bg-muted outline-none ring-1 ring-inset ring-input focus-visible:ring-[3px] focus-visible:ring-ring/50" style={{ left: x(from), width: w(from, to) }}>
                        <span className={cn("block h-full rounded-full", RAG_BAR[r.rag])} style={{ width: `${r.pct_complete}%` }} />
                      </button>
                    )}
                    {from && to && <span className="absolute top-1/2 -translate-y-1/2 whitespace-nowrap pl-2 text-[12px] text-muted-foreground" style={{ left: x(from) + w(from, to) }}>{r.pct_complete}% · {RAG_WORD[r.rag]}{r.forecast && ` · ends ${shortDay(r.forecast)}`}</span>}
                    {r.target_end_date && <span className={cn("absolute inset-y-1 w-0 border-l border-dashed", r.forecast && r.forecast > r.target_end_date ? "border-bad-line" : "border-foreground/60")} style={{ left: x(r.target_end_date) + px }} title={`Target ${fmtDate(r.target_end_date)}`} />}
                  </div>
                </div>
              )
            }
            const s = preview(r)[line.i]
            const editable = r.can_edit && s.status !== "done" && s.status !== "skipped"
            const pStart = s.plan_start ?? (editable ? s.suggested_start : null), pEnd = s.plan_end ?? (editable ? s.suggested_end : null)
            const late = s.status === "current" && s.plan_end && s.forecast_end && s.forecast_end > s.plan_end
            const moving = drag?.row === r.id && drag.index === line.i
            const next = preview(r)[line.i + 1]
            return (
              <div key={`s${s.id}`} role="row" aria-rowindex={n + 2} className="relative flex border-b border-border/60" style={{ height: ROW }}>
                <div role="gridcell" className="sticky left-0 z-10 grid shrink-0 grid-cols-[1fr_104px_24px_56px] items-center gap-2 border-r border-border bg-card px-3 text-[12px]" style={{ width: LEFT }}>
                  <span className={cn("truncate pl-8", s.status === "current" && "font-semibold")} title={s.name}>{s.name}</span>
                  <span className={cn("truncate", late ? "text-warn" : "text-muted-foreground")}>{s.status === "current" ? (late ? `${s.slip_days} d late` : "current") : s.status}</span>
                  <span />
                  <span className="text-right tabular-nums text-muted-foreground">{s.plan_end ? shortDay(s.plan_end) : s.forecast_end ? shortDay(s.forecast_end) : "—"}</span>
                </div>
                <div role="gridcell" className="relative" style={{ width: span * px }}>
                  {s.base_start && s.base_end && <span className="absolute bottom-1 h-[3px] rounded-full bg-input" style={{ left: x(s.base_start), width: w(s.base_start, s.base_end) }} aria-hidden />}
                  {s.actual_start && (s.actual_end || s.status === "current") && (
                    <span className={cn("absolute top-1/2 h-2 -translate-y-1/2 rounded-full", late ? "bg-warn-line" : s.status === "current" ? "bg-foreground/75" : "bg-ok-line")}
                      style={{ left: x(s.actual_start), width: w(s.actual_start, s.actual_end ?? data.today) }} aria-hidden />
                  )}
                  {s.forecast_start && s.forecast_end && (s.status === "next" || (s.status === "current" && s.forecast_end > data.today)) && (
                    <span className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-foreground/15" style={{ left: x(s.status === "current" ? data.today : s.forecast_start), width: w(s.status === "current" ? data.today : s.forecast_start, s.forecast_end) }} aria-hidden />
                  )}
                  {pStart && pEnd && (editable ? (
                    <button type="button" onPointerDown={(e) => startDrag(e, r, line.i)} onPointerMove={moveDrag} onPointerUp={() => endDrag(r)} onPointerCancel={() => setDrag(null)}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); setEdit({ row: r, index: line.i, mode: "pick", days: 0, start: pStart, end: pEnd, cascade: true }) } }}
                      aria-label={`${s.name} plan ${fmtDate(pStart)} to ${fmtDate(pEnd)}. Drag to move, drag an edge to resize, or press Enter to pick dates`}
                      title={`${s.name}: ${fmtDate(pStart)} – ${fmtDate(pEnd)} · ${workDays(pStart, pEnd, cal ?? undefined) + 1} days`}
                      className={cn("absolute top-1/2 h-5 -translate-y-1/2 cursor-grab touch-none rounded-md border-[1.5px] bg-card/40 outline-none hover:border-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50",
                        s.plan_start ? "border-foreground/45" : "border-dashed border-foreground/30", moving && "cursor-grabbing border-primary-text ring-2 ring-primary/30")}
                      style={{ left: x(pStart), width: w(pStart, pEnd) }}>
                      <span className="absolute inset-y-0 left-0 w-2 cursor-ew-resize" aria-hidden /><span className="absolute inset-y-0 right-0 w-2 cursor-ew-resize" aria-hidden />
                    </button>
                  ) : <span className="absolute top-1/2 h-5 -translate-y-1/2 rounded-md border-[1.5px] border-foreground/30" style={{ left: x(pStart), width: w(pStart, pEnd) }} aria-hidden />)}
                  {moving && drag && drag.days !== 0 && pStart && pEnd && (
                    <span className="absolute -top-0.5 z-10 whitespace-nowrap rounded-md bg-foreground px-2 py-0.5 text-[11px] text-background" style={{ left: x(pStart) }}>{shortDay(pStart)} – {shortDay(pEnd)}</span>
                  )}
                  {/* finish to start: this stage's end to the next one's start */}
                  {next && pEnd && (next.plan_start ?? next.forecast_start) && (
                    <svg className="pointer-events-none absolute overflow-visible text-foreground/35" style={{ left: x(pEnd) + px, top: ROW / 2 }} width="1" height="1" aria-hidden>
                      <path d={`M0 0 H6 V${ROW} H${Math.max(6, x((next.plan_start ?? next.forecast_start)!) - x(pEnd) - px)}`} fill="none" stroke="currentColor" strokeWidth="1.2" />
                    </svg>
                  )}
                  {pEnd && <span className="absolute top-1/2 -translate-y-1/2 whitespace-nowrap pl-3 text-[12px] text-muted-foreground" style={{ left: x(pEnd) + px }}>{s.name}</span>}
                </div>
              </div>
            )
          })}
          {lines.length === 0 && <p className="sticky left-0 px-5 py-10 text-[13px] text-muted-foreground">No rollout matches this filter.</p>}
        </div>
      </div>
      {edit && <SavePlan edit={edit} cal={cal} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); void load() }} />}
    </div>
  )
}

// Where a drag (or Enter) lands: the new dates, whether later stages follow,
// and why — once a baseline exists the plan's log needs a reason.
function SavePlan({ edit, cal, onClose, onSaved }: { edit: Edit; cal: GanttData["calendar"]; onClose: () => void; onSaved: () => void }) {
  const [e, setE] = useState(edit)
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const base = e.row.stages
  const s = base[e.index]
  const after = e.mode === "pick"
    ? setDate(setDate(base, e.index, "plan_start", e.start!, false), e.index, "plan_end", e.end!, e.cascade)
    : dragPlan(base, e.index, e.mode, e.days, e.cascade)
  const changes = changedStages(base, after)
  const now = after[e.index]
  async function save() {
    if (e.row.baselined && !reason.trim()) { setErr("Say why the dates move: it goes in the plan's log."); return }
    setBusy(true); setErr(null)
    try {
      const r = await savePlan(e.row.id, changes, reason.trim())
      toast(`Plan saved for ${e.row.name}${r.baselined ? "; this is now its baseline" : ""}${r.warning ? `. ${r.warning}` : ""}`)
      onSaved()
    } catch (x) { setErr(x instanceof ApiError ? x.message : "Could not save the plan") } finally { setBusy(false) }
  }
  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{s.name} · {e.row.name}</DialogTitle>
          <DialogDescription>{e.mode === "pick" ? "Pick the planned dates." : `Planned ${fmtDate(now.plan_start)} – ${fmtDate(now.plan_end)}${now.plan_start && now.plan_end ? `, ${workDays(now.plan_start, now.plan_end, cal ?? undefined) + 1} days` : ""}.`}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 text-[13px]">
          {e.mode === "pick" && (
            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1 text-[12px] text-muted-foreground">Start<DatePicker value={e.start!} onChange={(v) => setE({ ...e, start: v || e.start })} label="Planned start" className="w-full" /></label>
              <label className="grid gap-1 text-[12px] text-muted-foreground">End<DatePicker value={e.end!} onChange={(v) => setE({ ...e, end: v || e.end })} label="Planned end" min={e.start} className="w-full" /></label>
            </div>
          )}
          {e.mode !== "start" && (
            <label className="flex items-center gap-2"><input type="checkbox" checked={e.cascade} onChange={(x) => setE({ ...e, cascade: x.target.checked })} className="h-3.5 w-3.5 accent-primary" />Move later stages with it</label>
          )}
          {changes.length > 1 && <p className="text-[12px] text-muted-foreground">{changes.length} stages change.</p>}
          <label className="grid gap-1 text-[12px] text-muted-foreground">{e.row.baselined ? "Why the dates move (required; goes in the plan's log)" : "Note for the plan's log (optional; the first plan saved becomes the baseline)"}
            <Input value={reason} onChange={(x) => setReason(x.target.value)} maxLength={300} className="h-8 text-[13px]" autoFocus />
          </label>
          {err && <p className="text-[12px] text-destructive" role="alert">{err}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button size="sm" onClick={() => void save()} loading={busy} disabled={changes.length === 0}>Save plan</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
