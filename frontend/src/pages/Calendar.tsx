import { useEffect, useMemo, useState, type ReactNode } from "react"
import { DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core"
import { EmptyState } from "@/components/EmptyState"
import { pill } from "@/lib/ui"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { AlarmClock, ArrowRight, CalendarClock, Check, CheckSquare, ChevronLeft, ChevronRight, GanttChart, ShieldCheck, Target } from "lucide-react"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { Segmented } from "@/components/Segmented"
import { Calendar as MiniMonth } from "@/components/ui/calendar"
import { Button } from "@/components/ui/button"
import { DatePicker } from "@/components/DatePicker"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ApiError, calendar, moveTaskDue, type CalendarData } from "@/lib/api"
import { addDays } from "@/lib/plan"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { STATE } from "@/lib/state"
import { fmtDate, addMonths, localToday, laneSpans, monthGrid, monthTitle, shortDay, weekday } from "@/lib/format"

// The Calendar view (rebuilt 13 Oct 2026 after ReUI's "event-calendar-2"): a
// rail with the month at a glance, what is up next and the layers to show;
// then the month (bars for running rollouts, up to three items a day, the
// day's full list on demand), a week (every item, in lanes under the week's
// rollouts) or an agenda. Everything is all-day: Odin has dates, not hours.
// A task can be dragged to another day by whoever manages the rollout's tasks
// or the person it is on (the server checks again); the toast can undo it.
// The keyboard way is the chip's Move button and a date dialog (P2-43): Enter
// on the chip opens its rollout, as on any link.
type Item = { key: string; kind: "task" | "target" | "move" | "approval"; day: string; text: string; sub?: string; id: number; tone?: "bad" | "warn" | "ok" | "muted"; done?: boolean; task?: { id: number; project_id: number; title: string } }
type Show = Record<"tasks" | "targets" | "history" | "spans", boolean>
type Mode = "month" | "week" | "agenda"
const LANES = 3, WEEK_LANES = 6

function items(d: CalendarData, show: Show): Map<string, Item[]> {
  const out = new Map<string, Item[]>()
  const add = (it: Item) => out.set(it.day, [...(out.get(it.day) ?? []), it])
  if (show.targets) for (const t of d.targets) add({ key: `t${t.id}`, kind: "target", day: t.day, text: t.name, sub: `target · ${t.client}`, id: t.id, tone: t.state === "overdue" ? "bad" : t.state === "on_track" ? "muted" : "warn" })
  if (show.tasks) for (const t of d.tasks) add({ key: `k${t.id}`, kind: "task", day: t.day, text: t.title, sub: `${t.project}${t.who ? ` · ${t.who}` : ""}`, id: t.project_id, done: !!t.done, tone: !t.done && t.day < d.today ? "bad" : "muted", task: t.can_edit ? { id: t.id, project_id: t.project_id, title: t.title } : undefined })
  if (show.history) {
    for (const m of d.moves) add({ key: `m${m.project_id}${m.day}${m.stage}`, kind: "move", day: m.day, text: `${m.prev_stage} to ${m.stage}`, sub: `${m.project} · ${m.who}`, id: m.project_id, tone: "muted" })
    for (const a of d.approvals) add({ key: `a${a.project_id}${a.day}${a.kind}`, kind: "approval", day: a.day, text: a.kind === "asked" ? `Approval asked · ${a.stage}` : `${a.stage} ${a.status}`, sub: `${a.project}${a.who ? ` · ${a.who}` : ""}`, id: a.project_id, tone: a.kind === "asked" ? (a.status === "pending" ? "warn" : "muted") : a.status === "approved" ? "ok" : "bad" })
  }
  return out
}
// when the last drag ended: the click that follows a drop is not a click on the task
let lastDrop = 0
const mondayOf = (iso: string) => addDays(iso, -((new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7))

const ICON = { task: CheckSquare, target: Target, move: ArrowRight, approval: ShieldCheck }
// a chip opens its rollout under the calendar (the URL keeps the view)
function Chip({ it, full, href, still, onMove }: { it: Item; full?: boolean; href: (id: number) => string; still?: boolean; onMove?: (it: Item) => void }) {
  // late is a glyph and a word, not red alone (WCAG 1.4.1, test report UX-19)
  const late = it.tone === "bad" && !it.done && (it.kind === "task" || it.kind === "target")
  const Icon = late ? AlarmClock : ICON[it.kind]
  const tone = it.tone === "bad" ? "text-bad" : it.tone === "warn" ? "text-warn" : it.tone === "ok" ? "text-ok" : "text-muted-foreground"
  const movable = !!it.task && !still
  const { setNodeRef, listeners, transform, isDragging } = useDraggable({ id: still ? `still-${it.key}` : it.key, data: it, disabled: !movable })
  const navigate = useNavigate()
  const className = cn("flex min-w-0 items-start gap-2 rounded-md px-2 py-1 text-left text-[12px] leading-tight hover:bg-muted", full && "py-2 text-[13px]", movable && "flex-1 cursor-grab touch-none", isDragging && "opacity-40")
  const title = `${late ? "Late: " : ""}${it.text}${it.sub ? ` — ${it.sub}` : ""}${movable ? " · drag to another day, or use Move" : ""}`
  const body = (
    <>
      <Icon className={cn("mt-px h-3 w-3 shrink-0", tone)} aria-hidden />
      <span className="min-w-0">
        <span className={cn("block truncate", it.done && "line-through text-muted-foreground", it.tone === "bad" && !it.done && "font-medium text-bad")}>{late && <span className="sr-only">Late: </span>}{it.text}</span>
        {full && it.sub && <span className="block truncate text-muted-foreground">{it.sub}</span>}
      </span>
    </>
  )
  // a task that can move is a button that opens its rollout (Enter too: only the pointer drags),
  // so the click that ends a drag opens nothing; Move beside it picks the day from the keyboard
  if (movable) return (
    <div className="group/chip flex min-w-0 items-start">
      <button type="button" ref={setNodeRef} {...listeners} onClick={() => { if (Date.now() - lastDrop > 1000) navigate(href(it.id)) }} className={className} title={title}
        style={transform ? { transform: `translate(${transform.x}px, ${transform.y}px)`, position: "relative", zIndex: 30 } : undefined}>{body}</button>
      {onMove && <button type="button" onClick={() => onMove(it)} aria-label={`Move ${it.text} to another day`} title="Move to another day"
        className="shrink-0 rounded-md p-1 text-muted-foreground opacity-0 outline-none hover:bg-muted hover:text-foreground focus-visible:opacity-100 focus-visible:ring-[3px] focus-visible:ring-ring/50 group-hover/chip:opacity-100">
        <CalendarClock className="h-3 w-3" aria-hidden /></button>}
    </div>
  )
  return <Link to={href(it.id)} className={className} title={title}>{body}</Link>
}
// a day a task can be dropped on
function Day({ day, className, children }: { day: string; className?: string; children: ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: day })
  return <div ref={setNodeRef} className={cn(className, isOver && "bg-accent/50 ring-2 ring-inset ring-primary/40")}>{children}</div>
}

export function Calendar({ wide }: { wide: boolean }) {
  const [params, setParams] = useSearchParams()
  const today0 = localToday()
  const mode: Mode = params.get("cal") === "week" ? "week" : params.get("cal") === "agenda" ? "agenda" : "month"
  const week = /^\d{4}-\d{2}-\d{2}$/.test(params.get("week") ?? "") ? mondayOf(params.get("week")!) : mondayOf(today0)
  const month = mode === "week" ? week.slice(0, 7) : /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : today0.slice(0, 7)
  const set = (patch: Record<string, string | null>) => setParams((p) => { const n = new URLSearchParams(p); for (const [k, v] of Object.entries(patch)) { if (v == null) n.delete(k); else n.set(k, v) } return n }, { replace: true })
  const setMonth = (m: string) => set({ month: m, day: null })
  const openDay = params.get("day")
  const setOpenDay = (day: string | null) => set({ day })
  const href = (id: number) => { const n = new URLSearchParams(params); n.set("rollout", String(id)); return `/board?${n}` }
  const [d, setD] = useState<CalendarData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [show, setShow] = useState<Show>({ tasks: true, targets: true, history: true, spans: true })
  const [tick, setTick] = useState(0)   // a moved task reloads the month
  useEffect(() => {
    let live = true   // paging months quickly: only the month on screen lands
    calendar(month).then((x) => { if (live) { setD(x); setError(null) } }).catch((e) => { if (live) setError(e instanceof ApiError ? e.message : "Could not load the calendar") })
    return () => { live = false }
  }, [month, tick])
  const weeks = monthGrid(month)
  const byDay = useMemo(() => (d ? items(d, show) : new Map<string, Item[]>()), [d, show])
  // pointer only: dnd-kit's keyboard sensor took Enter for a silent drag (P2-43); Move is the keyboard way
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))
  const [moving, setMoving] = useState<{ it: Item; to: string; busy?: boolean; err?: string } | null>(null)
  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  const today = d.today
  const inMonth = (day: string) => day.startsWith(month)
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(week, i))

  // a drop and the Move dialog save the same way; the toast undoes it. Returns why it failed, or null.
  async function moveTo(it: Item, to: string): Promise<string | null> {
    if (!it.task || to === it.day) return null
    const { id, project_id, title } = it.task, from = it.day
    try {
      await moveTaskDue(project_id, id, to)
      setTick((n) => n + 1)
      toast(`${title}: due ${fmtDate(to)}`, { action: { label: "Undo", run: () => void moveTaskDue(project_id, id, from).then(() => setTick((n) => n + 1)) } })
      return null
    } catch (x) { return x instanceof ApiError ? x.message : "Could not move the task" }
  }
  async function onDrop(e: DragEndEvent) {
    const it = e.active.data.current as Item | undefined
    if (!it || !e.over) return
    const why = await moveTo(it, String(e.over.id))
    if (why) toast(why, { tone: "bad" })
  }
  async function saveMove() {
    if (!moving) return
    setMoving({ ...moving, busy: true, err: undefined })
    const why = await moveTo(moving.it, moving.to)
    setMoving(why ? { ...moving, busy: false, err: why } : null)
  }
  const ask = (it: Item) => setMoving({ it, to: it.day })
  const moveDialog = (
    <Dialog open={moving != null} onOpenChange={(o) => { if (!o) setMoving(null) }}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Move {moving?.it.text}</DialogTitle>
          <DialogDescription>Due {moving ? fmtDate(moving.it.day) : ""}{moving?.it.sub ? ` · ${moving.it.sub}` : ""}. Pick the new due date.</DialogDescription>
        </DialogHeader>
        {moving && <div className="grid grid-cols-1 gap-1 text-[13px] font-medium">New due date
          <DatePicker value={moving.to} onChange={(v) => setMoving({ ...moving, to: v, err: undefined })} label="New due date" clearable={false} className="w-full" /></div>}
        {moving?.err && <p className="text-[12px] text-destructive" role="alert">{moving.err}</p>}
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => setMoving(null)} disabled={moving?.busy}>Cancel</Button>
          <Button size="sm" onClick={() => void saveMove()} loading={moving?.busy} disabled={!moving || moving.to === moving.it.day}>Move task</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )

  const step = (n: number) => mode === "week" ? set({ week: addDays(week, 7 * n), day: null }) : setMonth(addMonths(month, n))
  const title = mode === "week" ? `${shortDay(week)} – ${shortDay(addDays(week, 6))} ${addDays(week, 6).slice(0, 4)}` : monthTitle(month)
  const layers: { key: keyof Show; label: string; icon: typeof Target }[] = [{ key: "spans", label: "Rollouts", icon: GanttChart }, { key: "targets", label: "Targets", icon: Target }, { key: "tasks", label: "Tasks", icon: CheckSquare }, { key: "history", label: "Moves & approvals", icon: ArrowRight }]
  const header = (
    <div className="flex flex-wrap items-center gap-2 px-4 pb-3 pt-3">
      <button type="button" onClick={() => mode === "week" ? set({ week: mondayOf(today), day: null }) : setMonth(today.slice(0, 7))} className={pill}>Today</button>
      {wide && <Segmented label="Calendar view" value={mode} onChange={(m) => set({ cal: m === "month" ? null : m, week: m === "week" ? (month === today.slice(0, 7) ? mondayOf(today) : `${month}-01`) : null, day: null })}
        options={[{ value: "month", label: "Month" }, { value: "week", label: "Week" }, { value: "agenda", label: "Agenda" }]} />}
      <div className="flex items-center gap-1">
        <button type="button" onClick={() => step(-1)} className={cn(pill, "w-7 px-0")} aria-label={mode === "week" ? "Previous week" : "Previous month"}><ChevronLeft className="h-3.5 w-3.5" /></button>
        <button type="button" onClick={() => step(1)} className={cn(pill, "w-7 px-0")} aria-label={mode === "week" ? "Next week" : "Next month"}><ChevronRight className="h-3.5 w-3.5" /></button>
      </div>
      <h2 className="text-[14px] font-semibold tracking-tight">{title}</h2>
      {!wide && (
        <div className="ml-auto flex flex-wrap gap-2" role="group" aria-label="Show">
          {layers.map((t) => <button key={t.key} type="button" aria-pressed={show[t.key]} onClick={() => setShow({ ...show, [t.key]: !show[t.key] })} className={cn(pill, show[t.key] && "border-foreground")}>{t.label}</button>)}
        </div>
      )}
    </div>
  )

  const agenda = (fromDays: string[]) => {
    const days = fromDays.filter((day) => byDay.get(day)?.length || (show.spans && d.spans.some((s) => s.start_date === day)))
    return (
      <ul className="divide-y divide-border px-4 pb-4">
        {days.map((day) => (
          <li key={day} className="py-2">
            <h3 className={cn("mb-1 text-[12px] font-semibold", day === today ? "text-primary-text" : "text-nav-fg")}>{fmtDate(day)}{day === today && " · today"}</h3>
            {show.spans && d.spans.filter((s) => s.start_date === day).map((s) => <Chip key={`s${s.id}`} full href={href} it={{ key: `s${s.id}`, kind: "target", day, text: `${s.name} starts`, sub: s.client, id: s.id, tone: "muted" }} />)}
            {(byDay.get(day) ?? []).map((it) => <Chip key={it.key} it={it} full href={href} onMove={ask} />)}
          </li>
        ))}
        {days.length === 0 && <EmptyState as="li">Nothing in {monthTitle(month)}.</EmptyState>}
      </ul>
    )
  }

  if (!wide) return <DndContext sensors={sensors}><div>{header}{agenda(weeks.flat().filter(inMonth))}</div>{moveDialog}</DndContext>

  // the rail: the month at a glance, what is next, the layers
  const upNext = [...byDay.entries()].filter(([day]) => day >= today && day <= addDays(today, 7)).sort(([a], [b]) => a.localeCompare(b))
    .flatMap(([, list]) => list.filter((it) => !it.done && it.kind !== "move")).slice(0, 6)
  const rail = (
    <aside className="hidden w-64 shrink-0 flex-col gap-4 overflow-y-auto border-r border-border px-3 py-3 lg:flex" aria-label="Calendar tools">
      <MiniMonth mode="single" hideNavigation month={new Date(`${month}-01T00:00:00`)} selected={openDay ? new Date(`${openDay}T00:00:00`) : undefined}
        onSelect={(x) => { if (!x) return; const iso = `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`; set(mode === "week" ? { week: mondayOf(iso), day: iso } : { month: iso.slice(0, 7), day: iso }) }}
        className="rounded-lg bg-transparent p-0" />
      <section aria-labelledby="cal-next">
        <p id="cal-next" className="mb-1 px-2 text-[12px] font-semibold text-nav-fg">Up next</p>
        {upNext.length ? upNext.map((it) => <Chip key={`n${it.key}`} it={it} full href={href} still />) : <p className="px-2 text-[12px] text-muted-foreground">Nothing due in the next 7 days.</p>}
      </section>
      <section aria-labelledby="cal-layers">
        <p id="cal-layers" className="mb-1 px-2 text-[12px] font-semibold text-nav-fg">Show</p>
        <div className="grid gap-0.5" role="group" aria-labelledby="cal-layers">
          {layers.map((t) => (
            <button key={t.key} type="button" aria-pressed={show[t.key]} onClick={() => setShow({ ...show, [t.key]: !show[t.key] })}
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50">
              <span className={cn("flex h-4 w-4 items-center justify-center rounded border", show[t.key] ? "border-foreground bg-foreground text-background" : "border-input")} aria-hidden>{show[t.key] && <Check className="h-3 w-3" />}</span>
              <t.icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />{t.label}
            </button>
          ))}
        </div>
      </section>
    </aside>
  )

  const bars = (days: string[], lanes: ReturnType<typeof laneSpans>, top: number) => lanes.segments.map((s) => (
    <Link key={`${s.id}-${s.startCol}`} to={href(s.id)} title={`${s.name} · ${s.client} · ${s.stage} · ${fmtDate(s.start_date)} – ${s.target_end_date ? fmtDate(s.target_end_date) : "no target"} · ${STATE[s.state].label}`}
      className={cn("absolute flex h-[14px] items-center truncate rounded-full px-2 text-[11px] font-medium leading-none hover:opacity-90",
        // the accent carries white; a stuck rollout is its state's soft fill and text, ringed in its line colour, so the name stays readable
        s.state === "on_track" ? "bg-muted text-foreground ring-1 ring-inset ring-input" : cn(STATE[s.state].chip, "ring-1 ring-inset", s.state === "overdue" ? "ring-bad-line" : "ring-warn-line"),
        s.startsHere ? "" : "rounded-l-none", s.endsHere ? "" : "rounded-r-none")}
      style={{ left: `calc(${(s.startCol / days.length) * 100}% + 2px)`, width: `calc(${(s.cols / days.length) * 100}% - 4px)`, top: top + s.lane * 18 }}>
      {s.name}
    </Link>
  ))

  let body: ReactNode
  if (mode === "agenda") body = <div className="min-h-0 flex-1 overflow-auto">{agenda(weeks.flat().filter(inMonth))}</div>
  else if (mode === "week") {
    const lanes = show.spans ? laneSpans(d.spans, weekDays, WEEK_LANES) : { segments: [], overflow: new Map<string, number>() }
    const laneCount = Math.min(WEEK_LANES, Math.max(0, ...lanes.segments.map((s) => s.lane + 1)))
    body = (
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="grid grid-cols-7 border-y border-border text-center text-[12px]">
          {weekDays.map((day) => (
            <div key={day} className={cn("py-2", day === today ? "font-semibold text-foreground" : "text-muted-foreground")}>{weekday(day)} <span className={cn("ml-1 inline-flex h-6 w-6 items-center justify-center rounded-full", day === today && "bg-primary text-primary-foreground")}>{Number(day.slice(8))}</span></div>
          ))}
        </div>
        <div className="relative border-b border-border" style={{ height: Math.max(1, laneCount) * 18 + 8 }} aria-label="Rollouts running this week">{bars(weekDays, lanes, 4)}</div>
        {Math.max(0, ...lanes.overflow.values()) > 0 && <p className="border-b border-border px-3 py-1 text-[11px] text-muted-foreground">+{Math.max(...lanes.overflow.values())} more rollouts running this week; open a day in Month for the full list.</p>}
        <div className="grid min-h-80 grid-cols-7">
          {weekDays.map((day) => (
            <Day key={day} day={day} className={cn("min-w-0 border-r border-border px-1 py-2 last:border-0", day === today && "bg-accent/20")}>
              {(byDay.get(day) ?? []).map((it) => <Chip key={it.key} it={it} full href={href} onMove={ask} />)}
              {!(byDay.get(day)?.length) && <span className="sr-only">Nothing on {fmtDate(day)}</span>}
            </Day>
          ))}
        </div>
      </div>
    )
  } else {
    const open = openDay ? byDay.get(openDay) ?? [] : null
    // every rollout running that day, so the ones folded into "+N rollouts" can be reached
    const running = openDay && show.spans ? d.spans.filter((s) => s.start_date <= openDay && (s.target_end_date ?? "9999") >= openDay) : []
    body = (
      <>
        <div className="grid grid-cols-7 border-y border-border text-center text-[12px] text-muted-foreground">
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((w) => <div key={w} className="py-2">{w}</div>)}
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {weeks.map((wk) => {
            const lanes = show.spans ? laneSpans(d.spans, wk, LANES) : { segments: [], overflow: new Map<string, number>() }
            const laneCount = Math.min(LANES, Math.max(0, ...lanes.segments.map((s) => s.lane + 1)))
            return (
              <div key={wk[0]} className="relative grid grid-cols-7 border-b border-border last:border-0" style={{ minHeight: 112 }}>
                {wk.map((day) => {
                  const list = byDay.get(day) ?? []
                  const extra = lanes.overflow.get(day) ?? 0
                  return (
                    <Day key={day} day={day} className={cn("min-w-0 border-r border-border px-1 pb-1 pt-1 last:border-0", !inMonth(day) && "bg-muted/40 text-muted-foreground")}>
                      <button type="button" onClick={() => setOpenDay(openDay === day ? null : day)} aria-label={`${fmtDate(day)}, ${list.length} item${list.length === 1 ? "" : "s"}`}
                        className={cn("mb-1 flex h-6 w-6 items-center justify-center rounded-full text-[12px] hover:bg-muted", day === today && "bg-primary font-semibold text-primary-foreground hover:bg-primary", openDay === day && day !== today && "ring-2 ring-primary/40")}>{Number(day.slice(8, 10))}</button>
                      <div style={{ height: laneCount * 18 }} aria-hidden />
                      {extra > 0 && <button type="button" onClick={() => setOpenDay(day)} className="block px-2 text-[11px] text-muted-foreground hover:text-foreground">+{extra} rollout{extra === 1 ? "" : "s"}</button>}
                      {list.slice(0, 3).map((it) => <Chip key={it.key} it={it} href={href} onMove={ask} />)}
                      {list.length > 3 && <button type="button" onClick={() => setOpenDay(day)} className="px-2 text-[11px] text-muted-foreground hover:text-foreground">+{list.length - 3} more</button>}
                    </Day>
                  )
                })}
                {bars(wk, lanes, 32)}
              </div>
            )
          })}
        </div>
        {open && openDay && (
          <div className="border-t border-border px-4 py-3">
            <div className="mb-1 flex items-center justify-between gap-3">
              <h3 className="text-[13px] font-semibold">{fmtDate(openDay)} <span className="font-normal text-muted-foreground">· {open.length} item{open.length === 1 ? "" : "s"}{running.length > 0 && `, ${running.length} rollout${running.length === 1 ? "" : "s"} running`}</span></h3>
              <button type="button" onClick={() => setOpenDay(null)} className="text-[12px] text-muted-foreground hover:text-foreground">Close</button>
            </div>
            <ul className="grid grid-cols-1 gap-x-6 md:grid-cols-2 xl:grid-cols-3">
              {running.map((s) => <li key={`r${s.id}`}><Chip href={href} it={{ key: `r${s.id}`, kind: "target", day: openDay, text: s.name, sub: `${s.client} · ${s.stage}`, id: s.id, tone: "muted" }} full /></li>)}
              {open.map((it) => <li key={it.key}><Chip it={it} full href={href} onMove={ask} /></li>)}
              {open.length + running.length === 0 && <li className="py-1 text-[13px] text-muted-foreground">Nothing on this day.</li>}
            </ul>
          </div>
        )}
      </>
    )
  }
  return (
    <DndContext sensors={sensors} autoScroll={false} onDragEnd={(e) => { lastDrop = Date.now(); void onDrop(e) }} onDragCancel={() => { lastDrop = Date.now() }}>
      <div className="flex h-full min-h-0">
        {rail}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">{header}{body}</div>
      </div>
      {moveDialog}
    </DndContext>
  )
}
