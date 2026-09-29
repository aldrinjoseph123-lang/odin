import { Fragment, useCallback, useEffect, useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { Activity, AlertTriangle, ArrowRight, CalendarClock, CheckSquare, FileText, Layers, MessageSquare, PauseCircle, ShieldCheck, Timer, UserCheck } from "lucide-react"
import { Area, AreaChart, Bar, BarChart, Cell, LabelList, Pie, PieChart, PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer, Tooltip as ChartTip, XAxis } from "recharts"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { buttonVariants } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { UserAvatar } from "@/components/UserAvatar"
import { TeamStack } from "@/components/TeamStack"
import { Ago } from "@/components/Ago"
import { PageSkeleton } from "@/components/PageSkeleton"
import { ApiError, dashboard, type DashboardData, type DashKey, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { STATE } from "@/lib/state"
import { dayOf, deltaText, fmtDate, lateBy, monthTicks, timelineDomain } from "@/lib/format"
import { pctChange, splitWindow, WIDTH_CLASS, type LayoutItem } from "@/lib/dashboard"

// The dashboard: widgets on a three-column grid, in the order and widths of
// the layout the server hands over (the workspace default, or this user's
// own). Each widget draws one slice of `data`; the settings it honours are
// its own, validated server-side.
type D = DashboardData["data"]
type S = Record<string, unknown>

const tip = {
  contentStyle: { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "var(--elevation-pop)", fontSize: 12, padding: "6px 10px" },
  labelStyle: { color: "var(--muted-foreground)" }, itemStyle: { color: "var(--foreground)" }, cursor: { fill: "var(--muted)" },
}
const pill = cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7 rounded-full px-3 text-[12px]")
const chip = "rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
const dayLabel = (iso: string) => WEEKDAY[new Date(`${iso}T00:00:00`).getDay()]

function Widget({ title, sub, action, children }: { title: string; sub?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel flex h-full min-w-0 flex-col p-4" aria-label={title}>
      <header className="mb-3 flex items-start justify-between gap-3">
        <h3 className="text-[13.5px] font-semibold">{title}{sub && <span className="ml-1.5 font-normal text-muted-foreground">{sub}</span>}</h3>
        {action}
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  )
}
const Empty = ({ children }: { children: ReactNode }) => <p className="py-2 text-[13px] text-muted-foreground">{children}</p>

// ---- headline numbers -------------------------------------------------------
const TILES: { key: DashKey; label: string; icon: typeof Activity; tone?: "warn" | "bad"; worseUp: boolean }[] = [
  { key: "active", label: "Active rollouts", icon: Layers, worseUp: false },
  { key: "overdue", label: "Overdue", icon: AlertTriangle, tone: "bad", worseUp: true },
  { key: "over_sla", label: "Over stage SLA", icon: Timer, tone: "warn", worseUp: true },
  { key: "due_soon", label: "Due soon", icon: CalendarClock, tone: "warn", worseUp: true },
  { key: "awaiting", label: "Waiting on customer", icon: UserCheck, worseUp: true },
  { key: "idle", label: "Idle", icon: PauseCircle, worseUp: true },
]
function Kpis({ k, s }: { k: D["kpis"]; s: S }) {
  const tiles = TILES.filter((t) => (s.tiles as string[] | undefined)?.includes(t.key) ?? true)
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
      {tiles.map((t) => {
        const n = k.counts[t.key], before = k.before?.[t.key] ?? null
        const d = before == null ? 0 : n - before
        const tone = d === 0 || !t.worseUp ? "bg-muted text-muted-foreground" : d > 0 ? "bg-bad-soft text-bad" : "bg-ok-soft text-ok"
        const series = k.series[t.key]
        return (
          <div key={t.key} className="panel flex min-w-0 flex-col p-4">
            <div className="flex items-center gap-2 text-[12px] text-muted-foreground"><t.icon className="h-3.5 w-3.5" aria-hidden />{t.label}</div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className={cn("text-[26px] font-semibold leading-none tracking-tight", n > 0 && t.tone === "bad" && "text-bad", n > 0 && t.tone === "warn" && "text-warn")}>{n}</span>
              {before != null && <span className={cn("rounded-full px-1.5 py-0.5 text-[11px] font-medium", tone)}>{deltaText(n, before)}</span>}
            </div>
            <div className="mt-1 text-[11.5px] text-muted-foreground">
              {t.key === "active" ? `${k.moved_this_week} stage move${k.moved_this_week === 1 ? "" : "s"} this week` : before != null ? `since ${fmtDate(k.since)}` : "no history yet"}
            </div>
            {series.length > 1 && (
              <div className="mt-2 h-9" aria-hidden>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={series} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
                    <Area type="monotone" dataKey="v" stroke="var(--primary)" strokeWidth={1.5} fill="var(--primary)" fillOpacity={0.12} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---- timeline ---------------------------------------------------------------
function Timeline({ rows, today, s }: { rows: D["timeline"]; today: string; s: S }) {
  const [all, setAll] = useState(false)
  const shown = (s.show === "attention" ? rows.filter((r) => r.state !== "on_track") : rows)
  const limit = Number(s.limit ?? 12)
  const list = all ? shown : shown.slice(0, limit)
  const { t0, t1 } = timelineDomain(shown, today)
  const pct = (t: number) => `${((t - t0) / (t1 - t0)) * 100}%`
  const now = dayOf(today)
  const [width, setWidth] = useState(0)
  const measure = useCallback((el: HTMLDivElement | null) => {
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const months = monthTicks(t0, t1, width ? Math.max(2, Math.floor(width / 64)) : 8)
  const crowded = months.some((tk) => Math.abs(tk.t - now) / (t1 - t0) * (width || 800) < 44)
  return (
    <Widget title="Timeline" sub="every active rollout, start to target" action={<Link to="/board" className={pill}>Open the flow</Link>}>
      {shown.length === 0 ? <Empty>No active rollouts{s.show === "attention" ? " need attention" : ""}.</Empty> : (
        <div className="grid grid-cols-[minmax(96px,176px)_minmax(0,1fr)] gap-x-3 text-[12.5px]">
          <span />
          <div ref={measure} className={cn("relative text-[11px] text-muted-foreground", crowded ? "h-9" : "h-5")}>
            {months.map((tk) => <span key={tk.t} className="absolute top-0 -translate-x-1/2" style={{ left: pct(tk.t) }}>{tk.label}</span>)}
            <span className={cn("absolute -translate-x-1/2 font-semibold text-primary-text", crowded ? "top-4" : "top-0")} style={{ left: pct(now) }}>today</span>
          </div>
          {list.map((r) => {
            const a = dayOf(r.start_date), b = r.target_end_date ? dayOf(r.target_end_date) : now
            const from = Math.min(a, b), to = Math.max(a, b)
            const fill = r.state === "on_track" ? "bg-primary" : STATE[r.state].dot
            return (
              <Fragment key={r.id}>
                <Link to={`/board?rollout=${r.id}`} className="truncate py-1.5 font-medium hover:underline">{r.name}<span className="ml-1.5 font-normal text-muted-foreground">{r.client}</span></Link>
                <div className="relative py-1.5">
                  <span className="absolute inset-y-0 w-[1.5px] bg-primary/60" style={{ left: pct(now) }} aria-hidden />
                  <Tooltip>
                    <TooltipTrigger render={<span />} tabIndex={0}
                      aria-label={`${r.name}: ${fmtDate(r.start_date)} to ${r.target_end_date ? fmtDate(r.target_end_date) : "no target"}, ${Math.round(r.progress * 100)} percent of stages done, ${STATE[r.state].label}`}
                      className="absolute top-1/2 block h-2.5 min-w-2 -translate-y-1/2 overflow-hidden rounded-full bg-muted"
                      style={{ left: pct(from), width: `calc(${pct(to)} - ${pct(from)})` }}>
                      <span className={cn("block h-full rounded-full", fill)} style={{ width: `${Math.max(4, r.progress * 100)}%` }} />
                    </TooltipTrigger>
                    <TooltipContent>{r.name} · {r.stage} · {fmtDate(r.start_date)} → {r.target_end_date ? fmtDate(r.target_end_date) : "no target"} · {Math.round(r.progress * 100)}% of stages{r.state !== "on_track" && ` · ${STATE[r.state].label}`}</TooltipContent>
                  </Tooltip>
                  {r.team.length > 0 && <TeamStack people={r.team} className="absolute top-1/2 flex -translate-y-1/2 pl-1.5 [&_span]:h-5 [&_span]:w-5 [&_span]:text-[9px]" style={{ left: pct(to) }} />}
                </div>
              </Fragment>
            )
          })}
        </div>
      )}
      {shown.length > limit && <button type="button" onClick={() => setAll(!all)} className="mt-2 text-[12px] text-muted-foreground hover:text-foreground">{all ? "Show fewer" : `Show all ${shown.length}`}</button>}
    </Widget>
  )
}

// ---- portfolio progress -----------------------------------------------------
function Progress({ p }: { p: D["progress"] }) {
  const total = p.done + p.current + p.pending
  return (
    <Widget title="Portfolio progress" sub="stage steps across active rollouts">
      {total === 0 ? <Empty>No active rollouts.</Empty> : (
        <>
          <div className="relative mx-auto h-40 max-w-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart innerRadius="72%" outerRadius="100%" startAngle={210} endAngle={-30} data={[{ v: p.pct }]} barSize={14}>
                <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
                <RadialBar dataKey="v" fill="var(--primary)" cornerRadius={8} background={{ fill: "var(--muted)" }} isAnimationActive={false} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pt-4">
              <span className="text-[34px] font-semibold leading-none tracking-tight">{p.pct}%</span>
              <span className="mt-1 text-[11.5px] text-muted-foreground">of stages done</span>
            </div>
          </div>
          <ul className="mt-2 grid grid-cols-3 gap-2 text-center text-[12px]">
            {[["Completed", p.done, "bg-primary"], ["In progress", p.current, "bg-primary/40"], ["Pending", p.pending, "bg-muted"]].map(([l, n, c]) => (
              <li key={String(l)} className="rounded-xl bg-muted/50 py-2">
                <span className={cn("mx-auto mb-1 block h-2 w-2 rounded-full", String(c))} aria-hidden />
                <span className="block text-[15px] font-semibold leading-none">{n}</span>
                <span className="text-muted-foreground">{l}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Widget>
  )
}

// ---- schedule ---------------------------------------------------------------
function Schedule({ sch, today, s }: { sch: D["schedule"]; today: string; s: S }) {
  const days = Number(s.days ?? 7)
  const until = new Date(`${today}T00:00:00Z`); until.setUTCDate(until.getUTCDate() + days)
  const due = sch.due.filter((t) => t.due_date <= until.toISOString().slice(0, 10))
  return (
    <Widget title="Schedule" sub={`next ${days} days`} action={<Link to="/my-work" className={pill}>My work</Link>}>
      <ul className="divide-y divide-border text-[13px]">
        {due.slice(0, 6).map((t) => {
          const late = lateBy(t.due_date, today)
          return (
            <li key={t.id} className="flex items-center gap-3 py-2">
              <span className={cn("w-14 shrink-0 whitespace-nowrap rounded-lg px-1 py-1 text-center text-[10.5px] leading-tight", late > 0 ? "bg-bad-soft text-bad" : "bg-muted text-muted-foreground")}>
                <span className="block text-[13px] font-semibold text-foreground">{t.due_date.slice(8, 10)}</span>{late > 0 ? `${late} d late` : dayLabel(t.due_date)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{t.title}</span>
                <span className="block truncate text-[12px] text-muted-foreground">{t.project}{t.who ? ` · ${t.who}` : ""}</span>
              </span>
              <Link to={`/board?rollout=${t.project_id}`} className={pill}>Open</Link>
            </li>
          )
        })}
        {due.length === 0 && <li><Empty>Nothing falls due in the next {days} days.</Empty></li>}
        {due.length > 6 && <li className="py-1.5 text-[12px]"><Link to="/my-work" className="text-muted-foreground hover:text-foreground">{due.length - 6} more due</Link></li>}
      </ul>
      {sch.approvals.length > 0 && (
        <>
          <h4 className="mt-3 mb-1 text-[12px] font-semibold text-nav-fg">Waiting on the customer</h4>
          <ul className="divide-y divide-border text-[13px]">
            {sch.approvals.slice(0, 4).map((a) => (
              <li key={`${a.project_id}-${a.stage}`} className="flex items-center gap-3 py-2">
                <ShieldCheck className="h-4 w-4 shrink-0 text-warn" aria-hidden />
                <span className="min-w-0 flex-1"><span className="block truncate font-medium">{a.project}</span><span className="block text-[12px] text-muted-foreground">{a.stage} · asked <Ago iso={a.requested_at} /></span></span>
                <Link to={`/board?rollout=${a.project_id}`} className={pill}>Open</Link>
              </li>
            ))}
            {sch.approvals.length > 4 && <li className="py-1.5 text-[12px]"><Link to="/board?filter=customer" className="text-muted-foreground hover:text-foreground">{sch.approvals.length - 4} more waiting</Link></li>}
          </ul>
        </>
      )}
    </Widget>
  )
}

// ---- tasks completed --------------------------------------------------------
function Completion({ series, s }: { series: D["completion"]; s: S }) {
  const n = Number(s.days ?? 7)
  const { now, before } = splitWindow(series, n)
  const sum = (xs: typeof series) => xs.reduce((a, x) => a + x.count, 0)
  const total = sum(now), prev = sum(before), peak = Math.max(0, ...now.map((x) => x.count))
  const change = pctChange(total, prev)
  const data = now.map((x) => ({ ...x, label: n <= 7 ? dayLabel(x.day).slice(0, 1) : x.day.slice(8, 10) }))
  return (
    <Widget title="Tasks completed" sub={`last ${n} days`}>
      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-[26px] font-semibold leading-none tracking-tight">{total}</span>
        {change && <span className={cn("rounded-full px-1.5 py-0.5 text-[11px] font-medium", change.startsWith("+") ? "bg-ok-soft text-ok" : change.startsWith("-") ? "bg-warn-soft text-warn" : "bg-muted text-muted-foreground")}>{change}</span>}
        <span className="text-[11.5px] text-muted-foreground">vs the {n} days before ({prev})</span>
      </div>
      <div className="h-36">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 18, right: 0, bottom: 0, left: 0 }} barCategoryGap={n <= 7 ? "28%" : "18%"}>
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} interval={n <= 7 ? 0 : "preserveStartEnd"} />
            <ChartTip {...tip} formatter={(v) => [`${v} task${v === 1 ? "" : "s"}`, ""]} labelFormatter={(_, p) => (p?.[0]?.payload ? fmtDate(p[0].payload.day) : "")} />
            <Bar dataKey="count" radius={[6, 6, 0, 0]} isAnimationActive={false}>
              {data.map((x) => <Cell key={x.day} fill="var(--primary)" fillOpacity={peak > 0 && x.count === peak ? 1 : 0.45} />)}
              <LabelList dataKey="count" position="top" content={(p) => (peak > 0 && p.value === peak && typeof p.x === "number" && typeof p.y === "number"
                ? <text x={p.x + Number(p.width ?? 0) / 2} y={p.y - 6} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--foreground)">{String(p.value)}</text> : null)} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="sr-only">{data.map((x) => `${fmtDate(x.day)}: ${x.count}`).join(", ")}</p>
    </Widget>
  )
}

// ---- team -------------------------------------------------------------------
function Team({ t, s }: { t: D["team"]; s: S }) {
  const limit = Number(s.limit ?? 6)
  return (
    <Widget title="Team" sub="rollouts and open work per person" action={<Link to="/users" className={pill}>People</Link>}>
      <ul className="divide-y divide-border text-[13px]">
        {t.people.slice(0, limit).map((m) => (
          <li key={m.id} className="flex items-center gap-3 py-2">
            <UserAvatar name={m.name} url={m.avatar_url} className="h-8 w-8" />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{m.name}</span>
              <span className="block truncate text-[12px] text-muted-foreground">{m.projects} rollout{m.projects === 1 ? "" : "s"} · {m.open} open{m.late > 0 && <> · <span className="font-medium text-bad">{m.late} late</span></>}</span>
            </span>
            <span className={chip}>{m.role}</span>
          </li>
        ))}
        {t.people.length === 0 && <li><Empty>No open tasks are assigned.</Empty></li>}
      </ul>
      {t.unassigned > 0 && <p className="mt-2 text-[12px] text-muted-foreground">{t.unassigned} open task{t.unassigned === 1 ? "" : "s"} unassigned</p>}
    </Widget>
  )
}

// ---- rollouts per stage -----------------------------------------------------
function Stages({ rows }: { rows: D["stages"] }) {
  const total = rows.reduce((a, r) => a + r.count, 0)
  return (
    <Widget title="Rollouts per stage" sub={`${total} active`}>
      {total === 0 ? <Empty>No active rollouts.</Empty> : (
        <div className="flex items-center gap-4">
          <div className="relative h-36 w-36 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={rows} dataKey="count" nameKey="stage" innerRadius={44} outerRadius={66} paddingAngle={2} stroke="var(--card)" strokeWidth={2} isAnimationActive={false}>
                  {rows.map((r, i) => <Cell key={r.stage} fill="var(--primary)" fillOpacity={0.25 + (0.75 * (i + 1)) / rows.length} />)}
                </Pie>
                <ChartTip {...tip} formatter={(v, name) => [`${v} rollout${v === 1 ? "" : "s"}`, String(name)]} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[22px] font-semibold leading-none">{total}</span><span className="text-[10.5px] text-muted-foreground">active</span>
            </div>
          </div>
          <ul className="min-w-0 flex-1 text-[12.5px]">
            {rows.map((r, i) => (
              <li key={r.stage} className="flex items-center gap-2 py-1">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-primary" style={{ opacity: 0.25 + (0.75 * (i + 1)) / rows.length }} aria-hidden />
                <Link to={`/board?stage=${encodeURIComponent(r.stage)}`} className="min-w-0 flex-1 truncate hover:underline">{r.stage}</Link>
                <span className="tabular-nums font-medium">{r.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Widget>
  )
}

// ---- recent activity --------------------------------------------------------
const KIND = { move: { icon: ArrowRight, verb: "moved" }, note: { icon: MessageSquare, verb: "noted on" }, approval: { icon: ShieldCheck, verb: "decided on" }, task: { icon: CheckSquare, verb: "ticked off on" }, document: { icon: FileText, verb: "added to" } }
function ActivityFeed({ rows, s }: { rows: D["activity"]; s: S }) {
  const limit = Number(s.limit ?? 10)
  return (
    <Widget title="Recent activity" sub="across the portfolio">
      <ul className="grid gap-2.5 text-[12.5px]">
        {rows.slice(0, limit).map((a, i) => {
          const k = KIND[a.kind]
          return (
            <li key={i} className="flex gap-2.5">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"><k.icon className="h-3.5 w-3.5" aria-hidden /></span>
              <span className="min-w-0">
                <span className="block leading-snug"><span className="font-medium">{a.who ?? "Someone"}</span> {k.verb} <Link to={`/board?rollout=${a.project_id}`} className="font-medium hover:underline">{a.project}</Link></span>
                <span className="block truncate text-muted-foreground">{a.text}</span>
                <span className="block text-[11px] text-muted-foreground"><Ago iso={a.at} /></span>
              </span>
            </li>
          )
        })}
        {rows.length === 0 && <li><Empty>Nothing has happened yet.</Empty></li>}
      </ul>
    </Widget>
  )
}

// ---- open alerts ------------------------------------------------------------
function Alerts({ rows, s }: { rows: D["alerts"]; s: S }) {
  const limit = Number(s.limit ?? 8)
  const dot = (sev: string) => (sev === "critical" ? "bg-bad-line" : sev === "warning" ? "bg-warn-line" : "bg-input")
  return (
    <Widget title="Open alerts" sub={String(rows.length)} action={<Link to="/alerts" className={pill}>All alerts</Link>}>
      <ul className="divide-y divide-border text-[13px]">
        {rows.slice(0, limit).map((a) => (
          <li key={a.id} className="flex items-center gap-3 py-2">
            <span className={cn("h-2 w-2 shrink-0 rounded-full", dot(a.severity))} aria-hidden /><span className="sr-only">{a.severity}: </span>
            <span className="min-w-0 flex-1"><span className="block truncate font-medium">{a.title}</span><Link to={`/board?rollout=${a.project_id}`} className="block truncate text-[12px] text-muted-foreground hover:underline">{a.project}</Link></span>
            <span className="shrink-0 text-[11px] text-muted-foreground"><Ago iso={a.created_at} /></span>
          </li>
        ))}
        {rows.length === 0 && <li><Empty>No open alerts.</Empty></li>}
      </ul>
    </Widget>
  )
}

// ---- my work ----------------------------------------------------------------
function MyWork({ m, today }: { m: D["mywork"]; today: string }) {
  return (
    <Widget title="My work" sub={`${m.tasks.length} open task${m.tasks.length === 1 ? "" : "s"} · ${m.owned} rollout${m.owned === 1 ? "" : "s"} you own`} action={<Link to="/my-work" className={pill}>Open</Link>}>
      <ul className="grid gap-x-6 text-[13px] md:grid-cols-2">
        {m.tasks.map((t) => {
          const late = t.due_date ? lateBy(t.due_date, today) : 0
          return (
            <li key={t.id} className="flex items-center gap-3 border-b border-border py-2">
              <span className={cn("w-16 shrink-0 text-[12px]", late > 0 ? "font-medium text-bad" : "text-muted-foreground")}>{t.due_date ? (late > 0 ? `${late} d late` : fmtDate(t.due_date)) : "no date"}</span>
              <span className="min-w-0 flex-1"><Link to={`/board?rollout=${t.project_id}`} className="block truncate font-medium hover:underline">{t.title}</Link><span className="block truncate text-[12px] text-muted-foreground">{t.project} · {t.stage}</span></span>
            </li>
          )
        })}
        {m.tasks.length === 0 && <li><Empty>Nothing is assigned to you.</Empty></li>}
      </ul>
    </Widget>
  )
}

// ---- cycle time -------------------------------------------------------------
function Cycle({ c }: { c: D["cycle"] }) {
  const d1 = (n: number | null) => (n == null ? "—" : n.toFixed(1))
  return (
    <Widget title="Cycle time" sub={c?.template} action={<Link to="/analytics" className={pill}>Detail</Link>}>
      {!c ? <Empty>No stage template yet.</Empty> : (
        <>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[["Lead time avg", d1(c.lead_avg), "days"], ["Median", d1(c.lead_median), "days"], ["Closed", String(c.completed_count), "rollouts"]].map(([l, v, u]) => (
              <div key={l} className="rounded-xl bg-muted/50 py-2"><span className="block text-[18px] font-semibold leading-none">{v}</span><span className="text-[11px] text-muted-foreground">{u}</span><span className="block text-[11px] text-muted-foreground">{l}</span></div>
            ))}
          </div>
          {c.slowest && <p className="mt-2 text-[12px] text-muted-foreground">Slowest stage <span className="font-medium text-foreground">{c.slowest.stage}</span>, {d1(c.slowest.avg_days)} days on average</p>}
          {c.throughput.length > 0 && (
            <div className="mt-2 h-20">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={c.throughput.map(([m, n]) => ({ m: m.slice(5), n }))} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                  <XAxis dataKey="m" tickLine={false} axisLine={false} tick={{ fontSize: 10.5, fill: "var(--muted-foreground)" }} />
                  <ChartTip {...tip} formatter={(v) => [`${v} closed`, ""]} />
                  <Bar dataKey="n" fill="var(--primary)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </Widget>
  )
}

function renderWidget(item: LayoutItem, d: D, today: string) {
  const s = item.settings
  switch (item.id) {
    case "kpis": return <Kpis k={d.kpis} s={s} />
    case "timeline": return <Timeline rows={d.timeline} today={today} s={s} />
    case "progress": return <Progress p={d.progress} />
    case "schedule": return <Schedule sch={d.schedule} today={today} s={s} />
    case "completion": return <Completion series={d.completion} s={s} />
    case "team": return <Team t={d.team} s={s} />
    case "stages": return <Stages rows={d.stages} />
    case "activity": return <ActivityFeed rows={d.activity} s={s} />
    case "alerts": return <Alerts rows={d.alerts} s={s} />
    case "mywork": return <MyWork m={d.mywork} today={today} />
    case "cycle": return <Cycle c={d.cycle} />
    default: return null
  }
}

export default function Dashboard({ user }: { user: User }) {
  const [d, setD] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { document.title = "Dashboard · Odin"; dashboard().then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")) }, [])
  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!d) return <PageSkeleton />
  const hour = new Date().getHours()
  return (
    <div className="px-5 pb-6 pt-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">{hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"}, {user.name.split(" ")[0]}</h1>
        <p className="text-[13px] text-muted-foreground">the portfolio this week · {fmtDate(d.today)}</p>
      </div>
      <div className="mt-3 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(d.layout as LayoutItem[]).map((item) => (
          <div key={item.id} className={cn("min-w-0", WIDTH_CLASS[item.w])}>{renderWidget(item, d.data, d.today)}</div>
        ))}
        {d.layout.length === 0 && <p className="text-[13px] text-muted-foreground md:col-span-2 xl:col-span-3">Every widget is hidden.</p>}
      </div>
    </div>
  )
}
