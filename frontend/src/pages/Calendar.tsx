import { Fragment, useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { AlarmClock, ArrowRight, CheckSquare, ChevronLeft, ChevronRight, ShieldCheck, Target } from "lucide-react"
import { buttonVariants } from "@/components/ui/button"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { ApiError, calendar, type CalendarData } from "@/lib/api"
import { cn } from "@/lib/utils"
import { STATE } from "@/lib/state"
import { fmtDate, addMonths, laneSpans, monthGrid, monthTitle } from "@/lib/format"

// The Calendar view: a six-week grid of the month. Active rollouts run as
// bars across their days at the top of each week; under them each day lists
// what is due, what moved and what a customer was asked or decided. Below
// md the same month is an agenda: one heading per day that has anything.
type Item = { key: string; kind: "task" | "target" | "move" | "approval"; day: string; text: string; sub?: string; href: string; tone?: "bad" | "warn" | "ok" | "muted"; done?: boolean }
type Show = Record<"tasks" | "targets" | "history" | "spans", boolean>
const pill = cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7 rounded-full px-3 text-[12px]")
const LANES = 3

function items(d: CalendarData, show: Show): Map<string, Item[]> {
  const out = new Map<string, Item[]>()
  const add = (it: Item) => out.set(it.day, [...(out.get(it.day) ?? []), it])
  if (show.targets) for (const t of d.targets) add({ key: `t${t.id}`, kind: "target", day: t.day, text: t.name, sub: `target · ${t.client}`, href: `/board?rollout=${t.id}`, tone: t.state === "overdue" ? "bad" : t.state === "on_track" ? "muted" : "warn" })
  if (show.tasks) for (const t of d.tasks) add({ key: `k${t.id}`, kind: "task", day: t.day, text: t.title, sub: `${t.project}${t.who ? ` · ${t.who}` : ""}`, href: `/board?rollout=${t.project_id}`, done: !!t.done, tone: !t.done && t.day < d.today ? "bad" : "muted" })
  if (show.history) {
    for (const m of d.moves) add({ key: `m${m.project_id}${m.day}${m.stage}`, kind: "move", day: m.day, text: `${m.prev_stage} → ${m.stage}`, sub: `${m.project} · ${m.who}`, href: `/board?rollout=${m.project_id}`, tone: "muted" })
    for (const a of d.approvals) add({ key: `a${a.project_id}${a.day}${a.kind}`, kind: "approval", day: a.day, text: a.kind === "asked" ? `Approval asked · ${a.stage}` : `${a.stage} ${a.status}`, sub: `${a.project}${a.who ? ` · ${a.who}` : ""}`, href: `/board?rollout=${a.project_id}`, tone: a.kind === "asked" ? (a.status === "pending" ? "warn" : "muted") : a.status === "approved" ? "ok" : "bad" })
  }
  return out
}

const ICON = { task: CheckSquare, target: Target, move: ArrowRight, approval: ShieldCheck }
function Chip({ it, full }: { it: Item; full?: boolean }) {
  // late is a glyph and a word, not red alone (WCAG 1.4.1, test report UX-19)
  const late = it.tone === "bad" && !it.done && (it.kind === "task" || it.kind === "target")
  const Icon = late ? AlarmClock : ICON[it.kind]
  const tone = it.tone === "bad" ? "text-bad" : it.tone === "warn" ? "text-warn" : it.tone === "ok" ? "text-ok" : "text-muted-foreground"
  return (
    <Link to={it.href} className={cn("flex min-w-0 items-start gap-1.5 rounded-md px-1.5 py-0.5 text-[12px] leading-tight hover:bg-muted", full && "py-1.5 text-[13px]")} title={`${late ? "Late: " : ""}${it.text}${it.sub ? ` — ${it.sub}` : ""}`}>
      <Icon className={cn("mt-px h-3 w-3 shrink-0", tone)} aria-hidden />
      <span className="min-w-0">
        <span className={cn("block truncate", it.done && "line-through text-muted-foreground", it.tone === "bad" && !it.done && "font-medium text-bad")}>{late && <span className="sr-only">Late: </span>}{it.text}</span>
        {full && it.sub && <span className="block truncate text-muted-foreground">{it.sub}</span>}
      </span>
    </Link>
  )
}

export function Calendar({ wide }: { wide: boolean }) {
  const [params, setParams] = useSearchParams()
  const month = /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : new Date().toISOString().slice(0, 7)
  const setMonth = (m: string) => setParams((p) => { const n = new URLSearchParams(p); n.set("month", m); n.delete("day"); return n }, { replace: true })
  const openDay = params.get("day")
  const setOpenDay = (day: string | null) => setParams((p) => { const n = new URLSearchParams(p); if (day) n.set("day", day); else n.delete("day"); return n }, { replace: true })
  const [d, setD] = useState<CalendarData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [show, setShow] = useState<Show>({ tasks: true, targets: true, history: true, spans: true })
  useEffect(() => { calendar(month).then((x) => { setD(x); setError(null) }).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load the calendar")) }, [month])
  const weeks = useMemo(() => monthGrid(month), [month])
  const byDay = useMemo(() => (d ? items(d, show) : new Map<string, Item[]>()), [d, show])
  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  const today = d.today
  const inMonth = (day: string) => day.startsWith(month)
  const toggles: { key: keyof Show; label: string }[] = [{ key: "spans", label: "Rollouts" }, { key: "targets", label: "Targets" }, { key: "tasks", label: "Tasks" }, { key: "history", label: "Moves & approvals" }]
  const header = (
    <div className="flex flex-wrap items-center gap-2 px-4 pb-3 pt-3">
      <div className="flex items-center gap-1">
        <button type="button" onClick={() => setMonth(addMonths(month, -1))} className={cn(pill, "w-7 px-0")} aria-label="Previous month"><ChevronLeft className="h-3.5 w-3.5" /></button>
        <button type="button" onClick={() => setMonth(addMonths(month, 1))} className={cn(pill, "w-7 px-0")} aria-label="Next month"><ChevronRight className="h-3.5 w-3.5" /></button>
        <button type="button" onClick={() => setMonth(today.slice(0, 7))} className={pill}>Today</button>
      </div>
      <h2 className="text-[14px] font-semibold tracking-tight">{monthTitle(month)}</h2>
      <div className="ml-auto flex flex-wrap gap-1.5" role="group" aria-label="Show">
        {toggles.map((t) => (
          <button key={t.key} type="button" aria-pressed={show[t.key]} onClick={() => setShow({ ...show, [t.key]: !show[t.key] })}
            className={cn("h-7 rounded-full border px-3 text-[12px] font-medium", show[t.key] ? "border-foreground bg-foreground text-background" : "border-border text-nav-fg hover:bg-muted")}>{t.label}</button>
        ))}
      </div>
    </div>
  )

  if (!wide) {
    const days = weeks.flat().filter((day) => inMonth(day) && (byDay.get(day)?.length || d.spans.some((s) => s.start_date === day)))
    return (
      <div>
        {header}
        <ul className="divide-y divide-border px-4 pb-4">
          {days.map((day) => (
            <li key={day} className="py-2">
              <h3 className={cn("mb-1 text-[12px] font-semibold", day === today ? "text-primary-text" : "text-nav-fg")}>{fmtDate(day)}{day === today && " · today"}</h3>
              {show.spans && d.spans.filter((s) => s.start_date === day).map((s) => <Chip key={`s${s.id}`} full it={{ key: `s${s.id}`, kind: "target", day, text: `${s.name} starts`, sub: s.client, href: `/board?rollout=${s.id}`, tone: "muted" }} />)}
              {(byDay.get(day) ?? []).map((it) => <Chip key={it.key} it={it} full />)}
            </li>
          ))}
          {days.length === 0 && <li className="py-6 text-center text-[13px] text-muted-foreground">Nothing in {monthTitle(month)}.</li>}
        </ul>
      </div>
    )
  }

  const open = openDay ? byDay.get(openDay) ?? [] : null
  return (
    <div className="flex h-full min-h-0 flex-col">
      {header}
      <div className="grid grid-cols-7 border-y border-border text-center text-[12px] text-muted-foreground">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((w) => <div key={w} className="py-1.5">{w}</div>)}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {weeks.map((week) => {
          const lanes = show.spans ? laneSpans(d.spans, week, LANES) : { segments: [], overflow: new Map<string, number>() }
          const laneCount = Math.min(LANES, Math.max(0, ...lanes.segments.map((s) => s.lane + 1)))
          return (
            <div key={week[0]} className="relative grid grid-cols-7 border-b border-border last:border-0" style={{ minHeight: 112 }}>
              {week.map((day) => {
                const list = byDay.get(day) ?? []
                const extra = lanes.overflow.get(day) ?? 0
                const shown = list.slice(0, 3)
                return (
                  <div key={day} className={cn("min-w-0 border-r border-border px-1 pb-1 pt-1 last:border-0", !inMonth(day) && "bg-muted/40 text-muted-foreground")}>
                    <button type="button" onClick={() => setOpenDay(openDay === day ? null : day)} aria-label={`${fmtDate(day)}, ${list.length} item${list.length === 1 ? "" : "s"}`}
                      className={cn("mb-0.5 flex h-6 w-6 items-center justify-center rounded-full text-[12px] hover:bg-muted", day === today && "bg-primary font-semibold text-primary-foreground hover:bg-primary", openDay === day && day !== today && "ring-2 ring-primary/40")}>{Number(day.slice(8, 10))}</button>
                    <div style={{ height: laneCount * 18 }} aria-hidden />
                    {extra > 0 && <span className="block px-1.5 text-[11px] text-muted-foreground">+{extra} rollout{extra === 1 ? "" : "s"}</span>}
                    {shown.map((it) => <Chip key={it.key} it={it} />)}
                    {list.length > 3 && <button type="button" onClick={() => setOpenDay(day)} className="px-1.5 text-[11px] text-muted-foreground hover:text-foreground">+{list.length - 3} more</button>}
                  </div>
                )
              })}
              {/* the week's rollout bars, laid over the cells */}
              {lanes.segments.map((s) => (
                <Link key={`${s.id}-${s.startCol}`} to={`/board?rollout=${s.id}`} title={`${s.name} · ${s.client} · ${s.stage} · ${fmtDate(s.start_date)} → ${s.target_end_date ? fmtDate(s.target_end_date) : "no target"}`}
                  className={cn("absolute flex h-[14px] items-center truncate rounded-full px-1.5 text-[11px] font-medium leading-none hover:opacity-90",
                    // the accent carries white; a stuck rollout is its state's soft fill and text, ringed in its line colour, so the name stays readable
                    s.state === "on_track" ? "bg-primary text-primary-foreground" : cn(STATE[s.state].chip, "ring-1 ring-inset", s.state === "overdue" ? "ring-bad-line" : "ring-warn-line"),
                    s.startsHere ? "" : "rounded-l-none", s.endsHere ? "" : "rounded-r-none")}
                  style={{ left: `calc(${(s.startCol / 7) * 100}% + 2px)`, width: `calc(${(s.cols / 7) * 100}% - 4px)`, top: 32 + s.lane * 18 }}>
                  {s.name}
                </Link>
              ))}
            </div>
          )
        })}
      </div>
      {open && openDay && (
        <div className="border-t border-border px-4 py-3">
          <div className="mb-1 flex items-center justify-between gap-3">
            <h3 className="text-[13px] font-semibold">{fmtDate(openDay)} <span className="font-normal text-muted-foreground">· {open.length} item{open.length === 1 ? "" : "s"}</span></h3>
            <button type="button" onClick={() => setOpenDay(null)} className="text-[12px] text-muted-foreground hover:text-foreground">Close</button>
          </div>
          <ul className="grid grid-cols-1 gap-x-6 md:grid-cols-2 xl:grid-cols-3">
            {open.map((it) => <li key={it.key}><Chip it={it} full /></li>)}
            {open.length === 0 && <li className="py-1 text-[13px] text-muted-foreground">Nothing on this day.</li>}
          </ul>
        </div>
      )}
      <Fragment />
    </div>
  )
}
