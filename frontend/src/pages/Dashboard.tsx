import { Fragment, useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { UserAvatar } from "@/components/UserAvatar"
import { StatTile } from "@/components/StatTile"
import { PageSkeleton } from "@/components/PageSkeleton"
import { ApiError, dashboard, type DashboardData, type DashKey, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { STATE } from "@/lib/state"
import { dayOf, deltaText, fmtDate, lateBy, monthTicks, timelineDomain } from "@/lib/format"

// The portfolio this week. Every number is one the flow, the alerts or the
// weekly report already compute; this page only puts them side by side.
const TILES: { key: DashKey; label: string; tone?: "warn" | "bad" }[] = [
  { key: "active", label: "Active rollouts" },
  { key: "overdue", label: "Overdue", tone: "bad" },
  { key: "over_sla", label: "Over stage SLA", tone: "warn" },
  { key: "due_soon", label: "Due soon", tone: "warn" },
  { key: "awaiting", label: "Waiting on customer" },
  { key: "idle", label: "Idle" },
]
const panel = "rounded-lg border border-border p-4"
const heading = "mb-2 text-[12px] font-semibold text-nav-fg"
const sub = "font-normal text-muted-foreground"
const more = "mt-2 text-[12px] text-muted-foreground hover:text-foreground"
const WEEKDAY = ["S", "M", "T", "W", "T", "F", "S"]

// "+2 since 22 Sep" — the change against the nearest snapshot a week or more old.
function Delta({ now, before, since }: { now: number; before: number | null; since: string | null }) {
  const t = deltaText(now, before)
  return <>{t ? `${t} since ${fmtDate(since)}` : "no history yet"}</>
}

// Every active rollout on one axis, start to target, today marked; stuck ones carry their state colour.
function Timeline({ d }: { d: DashboardData }) {
  const [all, setAll] = useState(false)
  const rows = all ? d.timeline : d.timeline.slice(0, 15)
  const { t0, t1 } = timelineDomain(d.timeline, d.today)
  const pct = (t: number) => `${((t - t0) / (t1 - t0)) * 100}%`
  const today = dayOf(d.today)
  // as many month ticks as the track has room for (one per 64 px), measured live
  const [width, setWidth] = useState(0)
  const measure = useCallback((el: HTMLDivElement | null) => {
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const months = monthTicks(t0, t1, width ? Math.max(2, Math.floor(width / 64)) : 8)
  // month ticks and "today" on one row, unless they would touch: then today drops a row
  const crowded = months.some((tk) => Math.abs(tk.t - today) / (t1 - t0) < 0.05)
  return (
    <section className={panel} aria-label="Timeline">
      <h3 className={heading}>Timeline <span className={sub}>every active rollout, start to target</span></h3>
      {d.timeline.length === 0 ? <p className="text-[13px] text-muted-foreground">No active rollouts.</p> : (
        <div className="grid grid-cols-[minmax(96px,180px)_minmax(0,1fr)] gap-x-3 text-[12.5px]">
          <span />
          <div ref={measure} className={cn("relative text-[11px] text-muted-foreground", crowded ? "h-9" : "h-5")}>
            {months.map((tk) => <span key={tk.t} className="absolute top-0 -translate-x-1/2" style={{ left: pct(tk.t) }}>{tk.label}</span>)}
            <span className={cn("absolute -translate-x-1/2 font-semibold text-primary-text", crowded ? "top-4" : "top-0")} style={{ left: pct(today) }}>today</span>
          </div>
          {rows.map((r) => {
            const s = dayOf(r.start_date), e = r.target_end_date ? dayOf(r.target_end_date) : today
            const from = Math.min(s, e), to = Math.max(s, e)
            return (
              <Fragment key={r.id}>
                <Link to={`/board?rollout=${r.id}`} className="truncate py-1 font-medium hover:underline">{r.name}</Link>
                <div className="relative">
                  <span className="absolute inset-y-0 w-[1.5px] bg-primary" style={{ left: pct(today) }} aria-hidden />
                  <Tooltip>
                    <TooltipTrigger render={<span />} tabIndex={0}
                      aria-label={`${r.name}: ${fmtDate(r.start_date)} to ${r.target_end_date ? fmtDate(r.target_end_date) : "no target"}, ${STATE[r.state].label}`}
                      className={cn("absolute top-1/2 h-1.5 min-w-1 -translate-y-1/2 rounded-full", r.state === "on_track" ? "bg-input" : STATE[r.state].dot)}
                      style={{ left: pct(from), width: `calc(${pct(to)} - ${pct(from)})` }} />
                    <TooltipContent>{r.name} · {r.client} · {r.stage} · {fmtDate(r.start_date)} → {r.target_end_date ? fmtDate(r.target_end_date) : "no target"}{r.state !== "on_track" && ` · ${STATE[r.state].label}`}</TooltipContent>
                  </Tooltip>
                </div>
              </Fragment>
            )
          })}
        </div>
      )}
      {d.timeline.length > 15 && <button type="button" onClick={() => setAll(!all)} className={more}>{all ? "Show fewer" : `Show all ${d.timeline.length}`}</button>}
    </section>
  )
}

export default function Dashboard(_props: { user: User }) {
  const [d, setD] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [allDue, setAllDue] = useState(false)
  useEffect(() => { document.title = "Dashboard · Odin"; dashboard().then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")) }, [])
  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!d) return <PageSkeleton />
  const peakStage = Math.max(0, ...d.stages.map((s) => s.count))
  const peakDay = Math.max(0, ...d.done_per_day.map((x) => x.count))
  const ticked = d.done_per_day.reduce((n, x) => n + x.count, 0)
  const due = allDue ? d.due : d.due.slice(0, 8)
  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Dashboard</h1>
        <p className="text-[13px] text-muted-foreground">the portfolio this week</p>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        {TILES.map((t) => {
          const n = d.counts[t.key]
          return <StatTile key={t.key} label={t.label} value={String(n)} tone={n > 0 ? t.tone : undefined}
            sub={t.key === "active"
              ? <>{d.moved_this_week} stage move{d.moved_this_week === 1 ? "" : "s"} this week · <Delta now={n} before={d.before?.[t.key] ?? null} since={d.since} /></>
              : <Delta now={n} before={d.before?.[t.key] ?? null} since={d.since} />} />
        })}
      </div>

      <div className="mt-4"><Timeline d={d} /></div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <section className={panel}>
          <h3 className={heading}>Rollouts per stage</h3>
          <ul className="grid gap-1.5 text-[13px]">
            {d.stages.map((s) => (
              <li key={s.stage} className="flex items-center gap-3">
                <Link to={`/board?stage=${encodeURIComponent(s.stage)}`} className="w-32 truncate text-[12.5px] hover:underline">{s.stage}</Link>
                <span className="h-2 flex-1 rounded-full bg-muted"><span className="block h-2 rounded-full bg-foreground" style={{ width: `${peakStage ? (s.count / peakStage) * 100 : 0}%` }} /></span>
                <span className="w-6 text-right tabular-nums">{s.count}</span>
              </li>
            ))}
            {d.stages.length === 0 && <li className="text-muted-foreground">No active rollouts.</li>}
          </ul>
        </section>

        <section className={panel}>
          <h3 className={heading}>Tasks completed <span className={sub}>{ticked} in the last 7 days</span></h3>
          <ul className="flex h-28 items-end gap-2" aria-label="Tasks completed per day">
            {d.done_per_day.map((x) => (
              <li key={x.day} className="flex h-full flex-1 flex-col items-center justify-end gap-1 text-[11px] text-muted-foreground">
                {peakDay > 0 && x.count === peakDay && <span className="tabular-nums text-foreground">{x.count}</span>}
                <Tooltip>
                  <TooltipTrigger render={<span />} tabIndex={0} aria-label={`${fmtDate(x.day)}: ${x.count} task${x.count === 1 ? "" : "s"}`}
                    className="block w-full rounded-t-[4px] bg-foreground" style={{ height: `${peakDay ? (x.count / peakDay) * 100 : 0}%`, minHeight: x.count ? 4 : 0 }} />
                  <TooltipContent>{fmtDate(x.day)} · {x.count} task{x.count === 1 ? "" : "s"}</TooltipContent>
                </Tooltip>
                <span aria-hidden>{WEEKDAY[new Date(`${x.day}T00:00:00`).getDay()]}</span>
              </li>
            ))}
          </ul>
          {ticked === 0 && <p className="mt-2 text-[12.5px] text-muted-foreground">Nothing ticked off this week.</p>}
        </section>

        <section className={panel}>
          <h3 className={heading}>Due in the next 7 days <span className={sub}>{d.due.length}</span></h3>
          <ul className="divide-y divide-border text-[13px]">
            {due.map((t) => {
              const late = lateBy(t.due_date, d.today)
              return (
                <li key={t.id} className="flex items-center gap-2 py-1.5">
                  <span className={cn("w-14 shrink-0 text-[12px]", late > 0 ? "font-medium text-bad" : "text-muted-foreground")}>{late > 0 ? `${late} d late` : fmtDate(t.due_date)}</span>
                  <span className="min-w-0 flex-1">
                    <Link to={`/board?rollout=${t.project_id}`} className="block truncate font-medium hover:underline">{t.title}</Link>
                    <span className="block truncate text-[12px] text-muted-foreground">{t.project}</span>
                  </span>
                  {t.who && <UserAvatar name={t.who} url={t.avatar_url} className="h-5 w-5" textClass="text-[10px]" />}
                </li>
              )
            })}
            {d.due.length === 0 && <li className="py-1.5 text-muted-foreground">Nothing falls due.</li>}
          </ul>
          {d.due.length > 8 && <button type="button" onClick={() => setAllDue(!allDue)} className={more}>{allDue ? "Show fewer" : `Show all ${d.due.length}`}</button>}
        </section>

        <section className={panel}>
          <h3 className={heading}>Team load <span className={sub}>open tasks per person</span></h3>
          <ul className="grid gap-1.5 text-[13px]">
            {d.load.map((m) => (
              <li key={m.id} className="flex items-center gap-2">
                <UserAvatar name={m.name} url={m.avatar_url} />
                <span className="min-w-0 flex-1 truncate font-medium">{m.name}</span>
                <span className="text-[12.5px] text-muted-foreground tabular-nums">{m.open} open{m.late > 0 && <> · <span className="font-medium text-bad">{m.late} late</span></>}</span>
              </li>
            ))}
            {d.load.length === 0 && <li className="text-muted-foreground">No open tasks are assigned.</li>}
          </ul>
          {d.unassigned > 0 && <p className="mt-2 text-[12.5px] text-muted-foreground">{d.unassigned} open task{d.unassigned === 1 ? "" : "s"} unassigned</p>}
        </section>
      </div>
    </div>
  )
}
