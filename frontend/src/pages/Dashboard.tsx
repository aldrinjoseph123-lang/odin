import { createContext, Fragment, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { Activity, AlertTriangle, ArrowRight, CalendarClock, CheckSquare, ChevronDown, ChevronUp, FileText, GripHorizontal, Layers, Maximize2, MessageSquare, MoreHorizontal, PauseCircle, Plus, ShieldCheck, Timer, Trash2, UserCheck } from "lucide-react"
import { Area, AreaChart, Bar, BarChart, Cell, LabelList, Line, LineChart, Pie, PieChart, PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer, Tooltip as ChartTip, XAxis } from "recharts"
import { buttonVariants } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { UserAvatar } from "@/components/UserAvatar"
import { TeamStack } from "@/components/TeamStack"
import { Ago } from "@/components/Ago"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { ApiError, dashboard, dashboardVersion, resetLayout, saveLayout, type Aggregate, type DashboardData, type DashKey, type DetailRow, type User, type WidgetInfo } from "@/lib/api"
import { cn } from "@/lib/utils"
import { STATE } from "@/lib/state"
import { dayOf, deltaText, fmtDate, lateBy, monthTicks, timelineDomain } from "@/lib/format"
import { configure, GRID_CLASS, keyOf, move, newUid, pack, pctChange, remove, reorder, resize, SPAN_CLASS, splitWindow, type LayoutItem, type Width } from "@/lib/dashboard"
import { useMedia, useWidth } from "@/lib/useMeasure"

// The dashboard: widgets on a three-column grid, in the order and widths of
// the layout the server hands over (the workspace default, or this user's
// own). Each widget draws one slice of `data`; the settings it honours are
// its own, validated server-side. The page polls a version number and
// reloads the data when anything in the portfolio changes.
type D = DashboardData["data"]
type S = Record<string, unknown>
type Table = { columns: string[]; rows: (string | number)[][] }
const POLL_MS = 15_000

const tip = {
  contentStyle: { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "var(--elevation-pop)", fontSize: 12, padding: "6px 10px" },
  labelStyle: { color: "var(--muted-foreground)" }, itemStyle: { color: "var(--foreground)" }, cursor: { fill: "var(--muted)" },
}
const axis = { tickLine: false, axisLine: false, tick: { fontSize: 11, fill: "var(--muted-foreground)" } }
const pill = cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7 rounded-full px-3 text-[12px]")
const chip = "rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground"
const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
const dayLabel = (iso: string) => WEEKDAY[new Date(`${iso}T00:00:00`).getDay()]

// Each grid cell hands its widget the ⋯ menu to show in the header.
const MenuSlot = createContext<ReactNode>(null)

function Widget({ title, sub, action, onExpand, children }: { title: string; sub?: ReactNode; action?: ReactNode; onExpand?: () => void; children: ReactNode }) {
  const menu = useContext(MenuSlot)
  return (
    <section className="panel flex h-full min-w-0 flex-col p-4" aria-label={title}>
      <header className="mb-3 flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <h2 className="min-w-0 text-[14px] font-semibold">{title}{sub && <span className="sr-only">, </span>}{sub && <span className="ml-2 font-normal text-muted-foreground">{sub}</span>}</h2>
        <span className="ml-auto flex shrink-0 items-center gap-1">
          {action}
          {onExpand && <button type="button" onClick={onExpand} aria-label={`Expand ${title}`} className="inline-flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"><Maximize2 className="h-3.5 w-3.5" /></button>}
          {menu}
        </span>
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  )
}
const Empty = ({ children }: { children: ReactNode }) => <p className="py-2 text-[13px] text-muted-foreground">{children}</p>

// Thin horizontal bars for a ranked list: label, bar, count.
function Bars({ rows, link }: { rows: Aggregate; link?: (key: string) => string }) {
  const peak = Math.max(0, ...rows.map((r) => r.count))
  return (
    <ul className="grid grid-cols-1 gap-2 text-[13px]">
      {rows.map((r) => (
        <li key={r.key} className="flex items-center gap-3">
          {link ? <Link to={link(r.key)} className="w-32 truncate text-[13px] hover:underline">{r.key}</Link> : <span className="w-32 truncate text-[13px]">{r.key}</span>}
          <span className="h-2 flex-1 rounded-full bg-muted"><span className="block h-2 rounded-full bg-primary" style={{ width: `${peak ? (r.count / peak) * 100 : 0}%` }} /></span>
          <span className="w-6 text-right tabular-nums">{r.count}</span>
        </li>
      ))}
    </ul>
  )
}
// An accent donut whose slices darken in order, the total in the middle, a legend beside.
function Donut({ rows, total, unit, link, large }: { rows: Aggregate; total: number; unit: string; link?: (key: string) => string; large?: boolean }) {
  return (
    <div className="flex items-center gap-4">
      <div className={cn("relative shrink-0", large ? "h-56 w-56" : "h-36 w-36")}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={rows} dataKey="count" nameKey="key" innerRadius={large ? 70 : 44} outerRadius={large ? 105 : 66} paddingAngle={2} stroke="var(--card)" strokeWidth={2} isAnimationActive={false}>
              {rows.map((r, i) => <Cell key={r.key} fill="var(--primary)" fillOpacity={0.25 + (0.75 * (i + 1)) / rows.length} />)}
            </Pie>
            <ChartTip {...tip} formatter={(v, name) => [`${v} ${unit}`, String(name)]} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[17px] font-semibold leading-none">{total}</span><span className="text-[11px] text-muted-foreground">{unit}</span>
        </div>
      </div>
      <ul className="min-w-0 flex-1 text-[13px]">
        {rows.map((r, i) => (
          <li key={r.key} className="flex items-center gap-2 py-1">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-primary" style={{ opacity: 0.25 + (0.75 * (i + 1)) / rows.length }} aria-hidden />
            {link ? <Link to={link(r.key)} className="min-w-0 flex-1 truncate hover:underline">{r.key}</Link> : <span className="min-w-0 flex-1 truncate">{r.key}</span>}
            <span className="tabular-nums font-medium">{r.count}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---- headline numbers -------------------------------------------------------
const TILES: { key: DashKey; label: string; icon: typeof Activity; tone?: "warn" | "bad"; worseUp: boolean }[] = [
  { key: "active", label: "Active rollouts", icon: Layers, worseUp: false },
  { key: "overdue", label: "Overdue", icon: AlertTriangle, tone: "bad", worseUp: true },
  { key: "over_sla", label: "Over stage SLA", icon: Timer, tone: "warn", worseUp: true },
  { key: "due_soon", label: "Due soon", icon: CalendarClock, tone: "warn", worseUp: true },
  { key: "awaiting", label: "Waiting on customer", icon: UserCheck, worseUp: true },
  { key: "idle", label: "Idle", icon: PauseCircle, worseUp: true },
]
function Kpis({ k, s, onTile }: { k: D["kpis"]; s: S; onTile: (key: DashKey) => void }) {
  const tiles = TILES.filter((t) => (s.tiles as string[] | undefined)?.includes(t.key) ?? true)
  const trend = (s.trend as string) ?? "area"
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
      {tiles.map((t) => {
        const n = k.counts[t.key], before = k.before?.[t.key] ?? null
        const d = before == null ? 0 : n - before
        // red only when the tile is lateness itself (DESIGN.md; test report UX-20); a worse SLA or waiting count is amber
        const tone = d === 0 || !t.worseUp ? "bg-muted text-muted-foreground" : d > 0 ? (t.tone === "bad" ? "bg-bad-soft text-bad" : "bg-warn-soft text-warn") : "bg-ok-soft text-ok"
        const series = k.series[t.key]
        return (
          <button key={t.key} type="button" onClick={() => onTile(t.key)} aria-label={`${t.label}: ${n}. Show them`}
            className="panel flex min-w-0 flex-col p-4 text-left outline-none transition-colors hover:bg-muted/40 focus-visible:ring-[3px] focus-visible:ring-ring/50">
            <span className="flex items-center gap-2 text-[12px] text-muted-foreground"><t.icon className="h-3.5 w-3.5" aria-hidden />{t.label}</span>
            <span className="mt-2 flex items-baseline gap-2">
              <span className={cn("text-[24px] font-semibold leading-none tracking-tight", n > 0 && t.tone === "bad" && "text-bad", n > 0 && t.tone === "warn" && "text-warn")}>{n}</span>
              {before != null && <span className={cn("rounded-full px-2 py-1 text-[11px] font-medium", tone)}>{deltaText(n, before)}</span>}
            </span>
            <span className="mt-1 text-[12px] text-muted-foreground">
              {t.key === "active" ? `${k.moved_this_week} stage move${k.moved_this_week === 1 ? "" : "s"} this week` : before != null ? `since ${fmtDate(k.since)}` : "no history yet"}
            </span>
            {trend !== "none" && series.length > 1 && (
              <span className="mt-2 block h-9" aria-hidden>
                <ResponsiveContainer width="100%" height="100%">
                  {trend === "bars" ? (
                    <BarChart data={series} margin={{ top: 2, right: 0, bottom: 0, left: 0 }} accessibilityLayer={false}><Bar dataKey="v" fill="var(--primary)" fillOpacity={0.6} radius={[2, 2, 0, 0]} isAnimationActive={false} /></BarChart>
                  ) : (
                    <AreaChart data={series} margin={{ top: 2, right: 0, bottom: 0, left: 0 }} accessibilityLayer={false}>
                      <Area type="monotone" dataKey="v" stroke="var(--primary)" strokeWidth={1.5} fill="var(--primary)" fillOpacity={0.12} isAnimationActive={false} />
                    </AreaChart>
                  )}
                </ResponsiveContainer>
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ---- timeline ---------------------------------------------------------------
function Timeline({ rows, today, s, onExpand, large }: { rows: D["timeline"]; today: string; s: S; onExpand?: () => void; large?: boolean }) {
  const [all, setAll] = useState(false)
  const shown = (s.show === "attention" ? rows.filter((r) => r.state !== "on_track") : rows)
  const limit = large ? 200 : Number(s.limit ?? 12)
  const list = all ? shown : shown.slice(0, limit)
  const { t0, t1 } = timelineDomain(shown, today)
  const pct = (t: number) => `${((t - t0) / (t1 - t0)) * 100}%`
  const now = dayOf(today)
  const [width, measure] = useWidth<HTMLDivElement>()
  const months = monthTicks(t0, t1, width ? Math.max(2, Math.floor(width / 64)) : 8)
  const crowded = months.some((tk) => Math.abs(tk.t - now) / (t1 - t0) * (width || 800) < 44)
  return (
    <Widget title="Timeline" sub="every active rollout, start to target" action={<Link to="/board" className={pill}>Open the flow</Link>} onExpand={onExpand}>
      {shown.length === 0 ? <Empty>No active rollouts{s.show === "attention" ? " need attention" : ""}.</Empty> : (
        <div className="grid grid-cols-[minmax(96px,176px)_minmax(0,1fr)] gap-x-3 overflow-x-clip text-[13px]">
          <span />
          <div ref={measure} className={cn("relative text-[11px] text-muted-foreground", crowded ? "h-9" : "h-5")}>
            {months.map((tk) => <span key={tk.t} className="absolute top-0 -translate-x-1/2" style={{ left: pct(tk.t) }}>{tk.label}</span>)}
            <span className={cn("absolute -translate-x-1/2 font-semibold text-foreground", crowded ? "top-4" : "top-0")} style={{ left: pct(now) }}>today</span>
          </div>
          {list.map((r) => {
            const a = dayOf(r.start_date), b = r.target_end_date ? dayOf(r.target_end_date) : now
            const from = Math.min(a, b), to = Math.max(a, b)
            const fill = r.state === "on_track" ? "bg-muted-foreground/45" : STATE[r.state].dot   // on track is neutral grey; colour is for trouble
            return (
              <Fragment key={r.id}>
                <Link to={`/board?rollout=${r.id}`} title={`${r.name} · ${r.client}`} className="flex min-w-0 items-baseline gap-2 py-2 font-medium hover:underline">
                  <span className="truncate">{r.name}</span>{r.state === "overdue" && <span className="shrink-0 text-[11px] font-semibold text-bad">late</span>}<span className="hidden min-w-0 truncate font-normal text-muted-foreground sm:inline">{r.client}</span></Link>
                <div className="relative py-2">
                  <span className="absolute inset-y-0 w-[1.5px] bg-foreground/60" style={{ left: pct(now) }} aria-hidden />
                  <Tooltip>
                    <TooltipTrigger render={<span />} tabIndex={0} role="img"
                      aria-label={`${r.name}: ${fmtDate(r.start_date)} to ${r.target_end_date ? fmtDate(r.target_end_date) : "no target"}, ${Math.round(r.progress * 100)} percent of stages done, ${STATE[r.state].label}`}
                      className="absolute top-1/2 block h-2.5 min-w-2 -translate-y-1/2 overflow-hidden rounded-full bg-muted"
                      style={{ left: pct(from), width: `calc(${pct(to)} - ${pct(from)})` }}>
                      <span className={cn("block h-full rounded-full", fill)} style={{ width: `${Math.max(4, r.progress * 100)}%` }} />
                    </TooltipTrigger>
                    <TooltipContent>{r.name} · {r.stage} · {fmtDate(r.start_date)} → {r.target_end_date ? fmtDate(r.target_end_date) : "no target"} · {Math.round(r.progress * 100)}% of stages{r.state !== "on_track" && ` · ${STATE[r.state].label}`}</TooltipContent>
                  </Tooltip>
                  {r.team.length > 0 && <TeamStack people={r.team} avatarClass="h-5 w-5" className="absolute top-1/2 flex -translate-y-1/2 pl-2" style={{ left: pct(to) }} />}
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
function Progress({ p, s, onExpand }: { p: D["progress"]; s: S; onExpand?: () => void }) {
  const total = p.done + p.current + p.pending
  const legend = (
    <ul className="mt-2 grid grid-cols-3 gap-2 text-center text-[12px]">
      {[["Completed", p.done, "bg-ok-line"], ["In progress", p.current, "bg-primary/40"], ["Pending", p.pending, "bg-input"]].map(([l, n, c]) => (
        <li key={String(l)} className="rounded-xl bg-muted/50 py-2">
          <span className={cn("mx-auto mb-1 block h-2 w-2 rounded-full", String(c))} aria-hidden />
          <span className="block text-[14px] font-semibold leading-none">{n}</span>
          <span className="text-muted-foreground">{l}</span>
        </li>
      ))}
    </ul>
  )
  return (
    <Widget title="Portfolio progress" sub="stage steps across active rollouts" onExpand={onExpand}>
      {total === 0 ? <Empty>No active rollouts.</Empty> : s.chart === "bar" ? (
        <>
          <div className="flex items-baseline gap-2"><span className="text-[24px] font-semibold leading-none tracking-tight">{p.pct}%</span><span className="text-[12px] text-muted-foreground">of stages done</span></div>
          <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-muted" role="img" aria-label={`${p.done} done, ${p.current} in progress, ${p.pending} pending`}>
            <span className="bg-ok-line" style={{ width: `${(p.done / total) * 100}%` }} /><span className="bg-primary/40" style={{ width: `${(p.current / total) * 100}%` }} />
          </div>
          {legend}
        </>
      ) : (
        <>
          <div className="relative mx-auto h-40 max-w-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart innerRadius="72%" outerRadius="100%" startAngle={210} endAngle={-30} data={[{ v: p.pct }]} barSize={14}>
                <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
                <RadialBar dataKey="v" fill="var(--ok-line)" cornerRadius={8} background={{ fill: "var(--muted)" }} isAnimationActive={false} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pt-4">
              <span className="text-[24px] font-semibold leading-none tracking-tight">{p.pct}%</span>
              <span className="mt-1 text-[12px] text-muted-foreground">of stages done</span>
            </div>
          </div>
          {legend}
        </>
      )}
    </Widget>
  )
}

// ---- schedule ---------------------------------------------------------------
function Schedule({ sch, today, s, onExpand, large }: { sch: D["schedule"]; today: string; s: S; onExpand?: () => void; large?: boolean }) {
  const days = Number(s.days ?? 7)
  const until = new Date(`${today}T00:00:00Z`); until.setUTCDate(until.getUTCDate() + days)
  const due = sch.due.filter((t) => t.due_date <= until.toISOString().slice(0, 10))
  const cap = large ? 100 : 6
  const lateCount = due.filter((t) => lateBy(t.due_date, today) > 0).length
  const group = "border-0 bg-muted/60 px-2 py-1 text-[12px] font-semibold text-nav-fg"
  return (
    <Widget title="Schedule" sub={lateCount ? `${lateCount} late · next ${days} days` : `next ${days} days`} action={<Link to="/my-work" className={pill}>My work</Link>} onExpand={onExpand}>
      <ul className="divide-y divide-border text-[13px]">
        {due.slice(0, cap).map((t, i) => {
          const late = lateBy(t.due_date, today)
          // due is sorted by date: late items first, then the window, each under its own heading
          const head = i === 0 && late > 0 ? "Late" : (i === 0 || lateBy(due[i - 1].due_date, today) > 0) && late <= 0 ? `Next ${days} days` : null
          return (
            <Fragment key={t.id}>
            {head && <li className={group}>{head}</li>}
            <li className="flex items-center gap-3 py-2">
              <span className={cn("w-14 shrink-0 whitespace-nowrap rounded-lg px-1 py-1 text-center text-[11px] leading-tight", late > 0 ? "bg-bad-soft text-bad" : "bg-muted text-muted-foreground")}>
                <span className="block text-[13px] font-semibold text-foreground">{t.due_date.slice(8, 10)}</span>{late > 0 ? `${late} d late` : dayLabel(t.due_date)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{t.title}</span>
                <span className="block truncate text-[12px] text-muted-foreground">{[t.project, t.stage, t.who].filter(Boolean).join(" · ")}</span>
              </span>
              <Link to={`/board?rollout=${t.project_id}`} className={pill}>Open</Link>
            </li>
            </Fragment>
          )
        })}
        {due.length === 0 && <li><Empty>Nothing falls due in the next {days} days.</Empty></li>}
        {due.length > cap && <li className="py-2 text-[12px]"><Link to="/my-work" className="text-muted-foreground hover:text-foreground">{due.length - cap} more due</Link></li>}
      </ul>
      {sch.approvals.length > 0 && (
        <>
          <h3 className="mt-3 mb-1 text-[12px] font-semibold text-nav-fg">Waiting on the customer</h3>
          <ul className="divide-y divide-border text-[13px]">
            {sch.approvals.slice(0, large ? 100 : 4).map((a) => (
              <li key={`${a.project_id}-${a.stage}`} className="flex items-center gap-3 py-2">
                <ShieldCheck className="h-4 w-4 shrink-0 text-warn" aria-hidden />
                <span className="min-w-0 flex-1"><span className="block truncate font-medium">{a.project}</span><span className="block text-[12px] text-muted-foreground">{a.stage} · asked <Ago iso={a.requested_at} /></span></span>
                <Link to={`/board?rollout=${a.project_id}`} className={pill}>Open</Link>
              </li>
            ))}
            {!large && sch.approvals.length > 4 && <li className="py-2 text-[12px]"><Link to="/board?filter=customer" className="text-muted-foreground hover:text-foreground">{sch.approvals.length - 4} more waiting</Link></li>}
          </ul>
        </>
      )}
    </Widget>
  )
}

// ---- tasks completed --------------------------------------------------------
function Completion({ series, s, onExpand, large }: { series: D["completion"]; s: S; onExpand?: () => void; large?: boolean }) {
  const n = Number(s.days ?? 7)
  const { now, before } = splitWindow(series, n)
  const sum = (xs: typeof series) => xs.reduce((a, x) => a + x.count, 0)
  const total = sum(now), prev = sum(before), peak = Math.max(0, ...now.map((x) => x.count))
  const change = pctChange(total, prev)
  const data = now.map((x) => ({ ...x, label: n <= 7 ? dayLabel(x.day).slice(0, 1) : x.day.slice(8, 10) }))
  return (
    <Widget title="Tasks completed" sub={`last ${n} days`} onExpand={onExpand}>
      {total === 0 ? <Empty>No tasks completed in the last {n} days{prev ? ` (${prev} in the ${n} days before)` : ""}.</Empty> : <>
      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-[24px] font-semibold leading-none tracking-tight">{total}</span>
        {change && <span className={cn("rounded-full px-2 py-1 text-[11px] font-medium", change.startsWith("+") ? "bg-ok-soft text-ok" : change.startsWith("-") ? "bg-warn-soft text-warn" : "bg-muted text-muted-foreground")}>{change}</span>}
        <span className="text-[12px] text-muted-foreground">vs the {n} days before ({prev})</span>
      </div>
      <div className={large ? "h-72" : "h-36"}>
        <ResponsiveContainer width="100%" height="100%">
          {s.chart === "line" ? (
            <LineChart data={data} margin={{ top: 18, right: 8, bottom: 0, left: 8 }}>
              <XAxis dataKey="label" {...axis} interval={n <= 7 ? 0 : "preserveStartEnd"} />
              <ChartTip {...tip} formatter={(v) => [`${v} task${v === 1 ? "" : "s"}`, ""]} labelFormatter={(_, p) => (p?.[0]?.payload ? fmtDate(p[0].payload.day) : "")} />
              <Line type="monotone" dataKey="count" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3, fill: "var(--primary)", strokeWidth: 2, stroke: "var(--card)" }} isAnimationActive={false} />
            </LineChart>
          ) : (
            <BarChart data={data} margin={{ top: 18, right: 0, bottom: 0, left: 0 }} barCategoryGap={n <= 7 ? "28%" : "18%"}>
              <XAxis dataKey="label" {...axis} interval={n <= 7 ? 0 : "preserveStartEnd"} />
              <ChartTip {...tip} formatter={(v) => [`${v} task${v === 1 ? "" : "s"}`, ""]} labelFormatter={(_, p) => (p?.[0]?.payload ? fmtDate(p[0].payload.day) : "")} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]} isAnimationActive={false}>
                {data.map((x) => <Cell key={x.day} fill="var(--primary)" fillOpacity={peak > 0 && x.count === peak ? 1 : 0.45} />)}
                <LabelList dataKey="count" position="top" content={(p) => (peak > 0 && p.value === peak && typeof p.x === "number" && typeof p.y === "number"
                  ? <text x={p.x + Number(p.width ?? 0) / 2} y={p.y - 6} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--foreground)">{String(p.value)}</text> : null)} />
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
      <p className="sr-only">{data.map((x) => `${fmtDate(x.day)}: ${x.count}`).join(", ")}</p>
      </>}
    </Widget>
  )
}

// ---- team -------------------------------------------------------------------
function Team({ t, s, onExpand, large }: { t: D["team"]; s: S; onExpand?: () => void; large?: boolean }) {
  const limit = large ? 100 : Number(s.limit ?? 6)
  const people = t.people.slice(0, limit)
  return (
    <Widget title="Team" sub="rollouts and open work per person" action={<Link to="/people" className={pill}>People</Link>} onExpand={onExpand}>
      {s.chart === "bar" ? (
        people.length === 0 ? <Empty>No open tasks are assigned.</Empty> : <Bars rows={people.map((m) => ({ key: m.name, count: m.open }))} link={(k) => `/people/${t.people.find((m) => m.name === k)?.id ?? ""}`} />
      ) : (
        <ul className="divide-y divide-border text-[13px]">
          {people.map((m) => (
            <li key={m.id} className="flex items-center gap-3 py-2">
              <UserAvatar name={m.name} url={m.avatar_url} className="h-8 w-8" />
              <span className="min-w-0 flex-1">
                <Link to={`/people/${m.id}`} className="block truncate font-medium hover:underline">{m.name}</Link>
                <span className="block truncate text-[12px] text-muted-foreground">{m.projects} rollout{m.projects === 1 ? "" : "s"} · {m.open} open{m.late > 0 && <> · <span className="font-medium text-bad">{m.late} late</span></>}</span>
              </span>
              <span className={chip}>{m.role}</span>
            </li>
          ))}
          {t.people.length === 0 && <li><Empty>No open tasks are assigned.</Empty></li>}
        </ul>
      )}
      {t.unassigned > 0 && <p className="mt-2 text-[12px] text-muted-foreground">{t.unassigned} open task{t.unassigned === 1 ? "" : "s"} unassigned</p>}
    </Widget>
  )
}

// ---- rollouts per stage -----------------------------------------------------
function Stages({ rows, s, onExpand, large }: { rows: D["stages"]; s: S; onExpand?: () => void; large?: boolean }) {
  const total = rows.reduce((a, r) => a + r.count, 0)
  const link = (k: string) => `/board?stage=${encodeURIComponent(k)}`
  const agg = rows.map((r) => ({ key: r.stage, count: r.count }))
  return (
    <Widget title="Rollouts per stage" sub={`${total} active`} onExpand={onExpand}>
      {total === 0 ? <Empty>No active rollouts.</Empty> : s.chart === "bar" ? <Bars rows={agg} link={link} /> : <Donut rows={agg} total={total} unit="active" link={link} large={large} />}
    </Widget>
  )
}

// ---- recent activity --------------------------------------------------------
const KIND = { move: { icon: ArrowRight, verb: "moved" }, note: { icon: MessageSquare, verb: "noted on" }, approval: { icon: ShieldCheck, verb: "decided on" }, task: { icon: CheckSquare, verb: "ticked off on" }, document: { icon: FileText, verb: "added to" } }
function ActivityFeed({ rows, s, onExpand, large }: { rows: D["activity"]; s: S; onExpand?: () => void; large?: boolean }) {
  const limit = large ? 100 : Number(s.limit ?? 10)
  return (
    <Widget title="Recent activity" sub="across the portfolio" onExpand={onExpand}>
      <ul className="grid grid-cols-1 gap-3 text-[13px]">
        {rows.slice(0, limit).map((a, i) => {
          const k = KIND[a.kind]
          return (
            <li key={i} className="flex gap-3">
              <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"><k.icon className="h-3.5 w-3.5" aria-hidden /></span>
              <span className="min-w-0">
                <span className="block leading-snug">{a.who ? <><span className="font-medium">{a.who}</span> {k.verb} </> : a.kind === "task" ? "Task done on " : "On "}<Link to={`/board?rollout=${a.project_id}`} className="font-medium hover:underline">{a.project}</Link></span>
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
function Alerts({ rows, s, onExpand, large }: { rows: D["alerts"]; s: S; onExpand?: () => void; large?: boolean }) {
  const limit = large ? 100 : Number(s.limit ?? 8)
  const dot = (sev: string) => (sev === "critical" ? "bg-bad-line" : sev === "warning" ? "bg-warn-line" : "bg-input")
  return (
    <Widget title="Open alerts" sub={String(rows.length)} action={<Link to="/alerts" className={pill}>All alerts</Link>} onExpand={onExpand}>
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
function MyWork({ m, today, onExpand }: { m: D["mywork"]; today: string; onExpand?: () => void }) {
  return (
    <Widget title="My work" sub={`${m.tasks.length} open task${m.tasks.length === 1 ? "" : "s"} · ${m.owned} rollout${m.owned === 1 ? "" : "s"} you own`} action={<Link to="/my-work" className={pill}>Open</Link>} onExpand={onExpand}>
      <ul className="grid grid-cols-1 gap-x-6 text-[13px] md:grid-cols-2">
        {m.tasks.map((t) => {
          const late = t.due_date ? lateBy(t.due_date, today) : 0
          return (
            <li key={t.id} className="flex items-center gap-3 border-b border-border py-2">
              <span className={cn("w-16 shrink-0 text-[12px]", late > 0 ? "font-medium text-bad" : "text-muted-foreground")}>{t.due_date ? (late > 0 ? `${late} d late` : fmtDate(t.due_date)) : "no date"}</span>
              <span className="min-w-0 flex-1"><Link to={`/board?rollout=${t.project_id}`} className="block truncate font-medium hover:underline">{t.title}</Link><span className="block truncate text-[12px] text-muted-foreground">{[t.project, t.stage].filter(Boolean).join(" · ")}</span></span>
            </li>
          )
        })}
        {m.tasks.length === 0 && <li><Empty>Nothing is assigned to you.</Empty></li>}
      </ul>
    </Widget>
  )
}

// ---- cycle time -------------------------------------------------------------
function Cycle({ c, s, onExpand, large }: { c: D["cycle"]; s: S; onExpand?: () => void; large?: boolean }) {
  const d1 = (n: number | null) => (n == null ? "—" : n > 0 && n < 0.05 ? "<0.1" : n.toFixed(1))   // a same-day close is not "0.0 days" (UX-23)
  const data = c?.throughput.map(([m, n]) => ({ m: m.slice(5), n })) ?? []
  return (
    <Widget title="Cycle time" sub={c?.template} action={<Link to="/analytics" className={pill}>Detail</Link>} onExpand={onExpand}>
      {!c ? <Empty>No stage template yet.</Empty> : (
        <>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[["Lead time avg", d1(c.lead_avg), "days"], ["Median", d1(c.lead_median), "days"], ["Closed", String(c.completed_count), "rollouts"]].map(([l, v, u]) => (
              <div key={l} className="rounded-xl bg-muted/50 py-2"><span className="block text-[17px] font-semibold leading-none">{v}</span><span className="text-[11px] text-muted-foreground">{u}</span><span className="block text-[11px] text-muted-foreground">{l}</span></div>
            ))}
          </div>
          {c.slowest && <p className="mt-2 text-[12px] text-muted-foreground">Slowest stage <span className="font-medium text-foreground">{c.slowest.stage}</span>, {d1(c.slowest.avg_days)} days on average</p>}
          {data.length > 0 && (
            <div className={cn("mt-2", large ? "h-56" : "h-20")}>
              <ResponsiveContainer width="100%" height="100%">
                {s.chart === "line" ? (
                  <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 8 }}><XAxis dataKey="m" {...axis} /><ChartTip {...tip} formatter={(v) => [`${v} closed`, ""]} /><Line type="monotone" dataKey="n" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3, fill: "var(--primary)" }} isAnimationActive={false} /></LineChart>
                ) : (
                  <BarChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}><XAxis dataKey="m" {...axis} /><ChartTip {...tip} formatter={(v) => [`${v} closed`, ""]} /><Bar dataKey="n" fill="var(--primary)" radius={[4, 4, 0, 0]} isAnimationActive={false} /></BarChart>
                )}
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </Widget>
  )
}

// ---- a custom metric: any aggregate as a number, bars, a pie or a list ------
const MEASURE_LABEL: Record<string, string> = {
  rollouts_by_stage: "Rollouts by stage", rollouts_by_client: "Rollouts by client", rollouts_by_state: "Rollouts by state", rollouts_by_owner: "Rollouts by owner",
  rollouts_by_mode: "Rollouts by delivery mode", open_tasks_by_person: "Open tasks by person", done_tasks_by_person: "Tasks finished by person, 30 days", tasks_done_per_day: "Tasks finished per day, 14 days",
}
function Custom({ agg, s, onExpand, large }: { agg: D["aggregates"]; s: S; onExpand?: () => void; large?: boolean }) {
  const measure = String(s.measure ?? "rollouts_by_stage")
  const rows = (agg[measure] ?? []).slice(0, large ? 100 : Number(s.top ?? 6))
  const total = (agg[measure] ?? []).reduce((a, r) => a + r.count, 0)
  const unit = measure.startsWith("rollouts") ? "rollouts" : "tasks"
  const chart = String(s.chart ?? "bar")
  const link = measure === "rollouts_by_stage" ? (k: string) => `/board?stage=${encodeURIComponent(k)}` : undefined
  return (
    <Widget title={String(s.title || "Custom metric")} sub={MEASURE_LABEL[measure]} onExpand={onExpand}>
      {rows.length === 0 ? <Empty>Nothing to count yet.</Empty>
        : chart === "number" ? (
          <div>
            <div className="flex items-baseline gap-2"><span className="text-[24px] font-semibold leading-none tracking-tight">{total}</span><span className="text-[12px] text-muted-foreground">{unit}</span></div>
            <p className="mt-2 text-[13px] text-muted-foreground">Most: <span className="font-medium text-foreground">{rows[0].key}</span> with {rows[0].count}</p>
          </div>
        ) : chart === "pie" ? <Donut rows={rows} total={total} unit={unit} link={link} large={large} />
        : chart === "list" ? (
          <ul className="divide-y divide-border text-[13px]">{rows.map((r) => <li key={r.key} className="flex items-center justify-between gap-3 py-2"><span className="truncate">{r.key}</span><span className="tabular-nums font-medium">{r.count}</span></li>)}</ul>
        ) : <Bars rows={rows} link={link} />}
    </Widget>
  )
}

// ---- the data behind a widget, as a table (the expand pop-up) ---------------
function tableFor(item: LayoutItem, d: D): Table | null {
  switch (item.id) {
    case "timeline": return { columns: ["Rollout", "Client", "Stage", "Start", "Target", "State", "Team"], rows: d.timeline.map((r) => [r.name, r.client, r.stage, fmtDate(r.start_date), r.target_end_date ? fmtDate(r.target_end_date) : "—", STATE[r.state].label, r.team.map((p) => p.name).join(", ")]) }
    case "progress": return { columns: ["Steps", "Count"], rows: [["Completed", d.progress.done], ["In progress", d.progress.current], ["Pending", d.progress.pending]] }
    case "schedule": return { columns: ["Due", "Task", "Rollout", "Who"], rows: d.schedule.due.map((t) => [fmtDate(t.due_date), t.title, t.project, t.who ?? "—"]) }
    case "completion": return { columns: ["Day", "Tasks completed"], rows: d.completion.slice(-28).map((x) => [fmtDate(x.day), x.count]) }
    case "team": return { columns: ["Person", "Role", "Rollouts", "Open", "Late"], rows: d.team.people.map((m) => [m.name, m.role, m.projects, m.open, m.late]) }
    case "stages": return { columns: ["Stage", "Rollouts"], rows: d.stages.map((s) => [s.stage, s.count]) }
    case "activity": return { columns: ["When", "Who", "Rollout", "What"], rows: d.activity.map((a) => [a.at.slice(0, 16).replace("T", " "), a.who ?? "—", a.project, a.text]) }
    case "alerts": return { columns: ["Severity", "Alert", "Rollout", "Raised"], rows: d.alerts.map((a) => [a.severity, a.title, a.project, a.created_at.slice(0, 10)]) }
    case "mywork": return { columns: ["Due", "Task", "Rollout", "Stage"], rows: d.mywork.tasks.map((t) => [t.due_date ? fmtDate(t.due_date) : "—", t.title, t.project, t.stage ?? "—"]) }
    case "cycle": return d.cycle ? { columns: ["Month", "Closed"], rows: d.cycle.throughput.map(([m, n]) => [m, n]) } : null
    case "custom": { const rows = d.aggregates[String(item.settings.measure ?? "rollouts_by_stage")] ?? []; return { columns: ["Key", "Count"], rows: rows.map((r) => [r.key, r.count]) } }
    default: return null
  }
}

function renderWidget(item: LayoutItem, d: D, today: string, on: { tile: (k: DashKey) => void; expand?: () => void }, large = false) {
  const s = item.settings
  switch (item.id) {
    case "kpis": return <Kpis k={d.kpis} s={s} onTile={on.tile} />
    case "timeline": return <Timeline rows={d.timeline} today={today} s={s} onExpand={on.expand} large={large} />
    case "progress": return <Progress p={d.progress} s={s} onExpand={on.expand} />
    case "schedule": return <Schedule sch={d.schedule} today={today} s={s} onExpand={on.expand} large={large} />
    case "completion": return <Completion series={d.completion} s={s} onExpand={on.expand} large={large} />
    case "team": return <Team t={d.team} s={s} onExpand={on.expand} large={large} />
    case "stages": return <Stages rows={d.stages} s={s} onExpand={on.expand} large={large} />
    case "activity": return <ActivityFeed rows={d.activity} s={s} onExpand={on.expand} large={large} />
    case "alerts": return <Alerts rows={d.alerts} s={s} onExpand={on.expand} large={large} />
    case "mywork": return <MyWork m={d.mywork} today={today} onExpand={on.expand} />
    case "cycle": return <Cycle c={d.cycle} s={s} onExpand={on.expand} large={large} />
    case "custom": return <Custom agg={d.aggregates} s={s} onExpand={on.expand} large={large} />
    default: return null
  }
}

// ---- customising: each widget's own ⋯ menu -------------------------------------
// Every change saves at once to this person's arrangement (with an Undo);
// text and number settings save a moment after typing stops.
const WIDTHS: { w: Width; label: string }[] = [{ w: 1, label: "⅓" }, { w: 2, label: "⅔" }, { w: 3, label: "Full" }]
const tool = "inline-flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40"
function WidgetMenu({ item, info, title, first, last, onMove, onResize, onRemove, onSettings }: {
  item: LayoutItem; info: WidgetInfo; title: string; first: boolean; last: boolean
  onMove: (by: -1 | 1) => void; onResize: (w: Width) => void; onRemove: () => void; onSettings: (s: Record<string, unknown>) => void
}) {
  return (
    <Popover>
      <PopoverTrigger render={<button type="button" />} aria-label={`Customise ${title}`} className={tool}><MoreHorizontal className="h-4 w-4" /></PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-3 text-[13px]">
        <div className="mb-2 font-semibold">{title}</div>
        {info.settings.length > 0 && (
          <div className="grid grid-cols-1 gap-2 border-b border-border pb-3">
            {info.settings.map((s) => {
              const v = item.settings[s.key] ?? s.default
              const id = `${keyOf(item)}-${s.key}`
              if (s.kind === "multi") return (
                <fieldset key={s.key}><legend className="mb-1 text-muted-foreground">{s.label}</legend>
                  <div className="flex flex-wrap gap-2">
                    {s.choices?.map((c) => {
                      const on = (v as string[]).includes(c)
                      return <button key={c} type="button" aria-pressed={on} onClick={() => onSettings({ [s.key]: on ? (v as string[]).filter((x) => x !== c) : [...(v as string[]), c] })}
                        className={cn("h-7 rounded-full border px-3 text-[12px]", on ? "border-foreground bg-foreground text-background" : "border-border text-nav-fg hover:bg-muted")}>{TILES.find((t) => t.key === c)?.label ?? c}</button>
                    })}
                  </div>
                </fieldset>
              )
              return (
                <label key={s.key} htmlFor={id} className="flex items-center justify-between gap-3"><span className="text-muted-foreground">{s.label}</span>
                  {s.kind === "choice" ? (
                    <select id={id} value={String(v)} onChange={(e) => onSettings({ [s.key]: e.target.value })} className="h-7 max-w-[60%] rounded-md border border-input bg-background px-2 text-[13px]">
                      {s.choices?.map((c) => <option key={c} value={c}>{MEASURE_LABEL[c] ?? c}</option>)}
                    </select>
                  ) : s.kind === "text" ? <input id={id} type="text" maxLength={s.max} value={String(v)} onChange={(e) => onSettings({ [s.key]: e.target.value })} className="h-7 w-40 rounded-md border border-input bg-background px-2 text-[13px]" />
                  : <input id={id} type="number" min={s.min} max={s.max} value={Number(v)} onChange={(e) => onSettings({ [s.key]: Math.max(s.min ?? 0, Math.min(s.max ?? 999, Number(e.target.value) || 0)) })} className="h-7 w-20 rounded-md border border-input bg-background px-2 text-[13px]" />}
                </label>
              )
            })}
          </div>
        )}
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="text-muted-foreground">Width</span>
          <span className="flex rounded-full bg-muted p-1" role="group" aria-label={`Width of ${title}`}>
            {WIDTHS.map((x) => (
              <button key={x.w} type="button" onClick={() => onResize(x.w)} aria-pressed={item.w === x.w}
                className={cn("h-6 rounded-full px-3 text-[12px] font-medium", item.w === x.w ? "bg-card shadow-card" : "text-muted-foreground hover:text-foreground")}>{x.label}</button>
            ))}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-1">
          <span className="mr-auto text-muted-foreground">Position</span>
          <button type="button" onClick={() => onMove(-1)} disabled={first} className={cn(tool, "w-auto px-3 text-[12px]")} aria-label={`Move ${title} earlier`}><ChevronUp className="h-3.5 w-3.5" /> Earlier</button>
          <button type="button" onClick={() => onMove(1)} disabled={last} className={cn(tool, "w-auto px-3 text-[12px]")} aria-label={`Move ${title} later`}><ChevronDown className="h-3.5 w-3.5" /> Later</button>
        </div>
        <button type="button" onClick={onRemove} className="mt-3 flex w-full items-center justify-center gap-2 rounded-full border border-border py-2 text-[12px] text-bad hover:bg-bad-soft" aria-label={`Remove ${title}`}><Trash2 className="h-3.5 w-3.5" /> Remove from my dashboard</button>
      </PopoverContent>
    </Popover>
  )
}

// Three columns on wide screens, two on tablets, one on phones: the packer needs to know which.
function useColumns() {
  const xl = useMedia("(min-width: 1280px)"), md = useMedia("(min-width: 768px)")
  return xl ? 3 : md ? 2 : 1
}

export default function Dashboard({ user }: { user: User }) {
  const [d, setD] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<string>(() => new Date().toISOString())
  // customising: every change saves at once (typing settles first), with an Undo
  const [dragging, setDragging] = useState<string | null>(null)
  const [grip, setGrip] = useState<string | null>(null)
  const [undo, setUndo] = useState<LayoutItem[] | null>(null)
  const saveTimer = useRef<number | undefined>(undefined)
  const cols = useColumns()
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [tile, setTile] = useState<DashKey | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const version = useRef<number | null>(null)
  const saved = useRef<{ layout: DashboardData["layout"]; is_custom: boolean } | null>(null)   // the arrangement the server holds
  const pending = useRef(false)

  const load = useCallback(async () => {
    try {
      const next = await dashboard()
      setD(next); version.current = next.version; saved.current = { layout: next.layout, is_custom: next.is_custom }; setUpdatedAt(new Date().toISOString()); setError(null)
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load") }
  }, [])
  useEffect(() => { document.title = "Dashboard · Odin"; void load() }, [load])
  // live: ask for the version every few seconds and whenever the tab comes back; reload the data when it moved
  useEffect(() => {
    let stop = false
    const check = async () => {
      if (stop || document.hidden || pending.current) return
      try {
        const { version: v } = await dashboardVersion()
        if (version.current != null && v !== version.current) await load()
      } catch { /* the next tick tries again */ }
    }
    const timer = setInterval(check, POLL_MS)
    document.addEventListener("visibilitychange", check)
    window.addEventListener("focus", check)
    return () => { stop = true; clearInterval(timer); document.removeEventListener("visibilitychange", check); window.removeEventListener("focus", check) }
  }, [load])

  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  const hour = new Date().getHours()
  const layout = d.layout as LayoutItem[]
  const info = (id: string) => d.catalogue.find((w) => w.id === id)!
  const hidden = d.catalogue.filter((w) => !w.multiple && !layout.some((x) => x.id === w.id))
  const repeatable = d.catalogue.filter((w) => w.multiple)
  const admin = user.permissions.includes("manage_settings")
  // one door for every change: show it now, save it (debounced for typing), offer Undo
  const commit = (fn: (l: LayoutItem[]) => LayoutItem[], label = "Saved to your dashboard.", settle = 0) => {
    const before = layout
    const next = fn(layout)
    setD({ ...d, layout: next, is_custom: true })
    setUndo(before)
    window.clearTimeout(saveTimer.current)
    pending.current = true
    saveTimer.current = window.setTimeout(() => {
      saveLayout(next).then(() => { saved.current = { layout: next, is_custom: true }; setNotice(label) })
        .catch((e) => {
          const back = saved.current
          if (back) setD((cur) => (cur ? { ...cur, ...back } : cur))
          setUndo(null)
          setNotice(`${e instanceof ApiError ? e.message : "That did not save"} The dashboard is back as it was saved.`)
        })
        .finally(() => { pending.current = false })
    }, settle)
  }
  const add = (w: WidgetInfo) => commit((l) => [...l, { id: w.id, w: w.w, settings: Object.fromEntries(w.settings.map((s) => [s.key, s.default])), ...(w.multiple ? { uid: newUid() } : {}) }], `${w.title} added.`)
  async function run(label: string, fn: () => Promise<{ layout: DashboardData["layout"]; is_custom?: boolean }>, after: (r: { layout: DashboardData["layout"]; is_custom?: boolean }) => void) {
    setBusy(true); setNotice(null)
    try { const r = await fn(); after(r); setNotice(label); setUndo(null) } catch (e) { setNotice(e instanceof ApiError ? e.message : "That did not save") } finally { setBusy(false) }
  }
  const saveDefault = () => run("Saved as the workspace default.", () => saveLayout(layout, "default"), () => {})
  const reset = () => run("Back to the workspace default.", () => resetLayout(), (r) => setD({ ...d, layout: r.layout, is_custom: false }))
  const packed = pack(layout, cols)
  const expandedItem = expanded ? layout.find((x) => keyOf(x) === expanded) : null
  const tileInfo = tile ? TILES.find((t) => t.key === tile)! : null
  const tileRows: DetailRow[] = tile ? d.data.kpis.detail[tile] ?? [] : []
  const table = expandedItem ? tableFor(expandedItem, d.data) : null
  const titleOf = (item: LayoutItem) => (item.id === "custom" ? String(item.settings.title || "Custom metric") : info(item.id).title)

  return (
    <div className="px-5 pb-24 pt-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">{hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"}, {user.name.split(" ")[0]}</h1>
        <p className="text-[13px] text-muted-foreground">the portfolio this week · {fmtDate(d.today)}{d.is_custom && " · your arrangement"}</p>
        <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-ok-line" aria-hidden />live · updated <Ago iso={updatedAt} />
        </p>
        <span className="ml-auto flex items-center gap-2">
          <Popover>
            <PopoverTrigger render={<button type="button" />} className={pill}><Plus className="h-3.5 w-3.5" /> Add widget</PopoverTrigger>
            <PopoverContent align="end" className="w-80 p-2 text-[13px]">
              <ul className="grid grid-cols-1 gap-1">
                {[...hidden, ...repeatable].map((w) => (
                  <li key={w.id}><button type="button" onClick={() => add(w)} className="grid grid-cols-1 w-full gap-1 rounded-lg px-3 py-2 text-left hover:bg-muted">
                    <span className="font-medium">{w.title}{w.multiple && <span className="ml-2 font-normal text-muted-foreground">add another</span>}</span>
                    <span className="text-[12px] text-muted-foreground">{w.blurb}</span></button></li>
                ))}
              </ul>
            </PopoverContent>
          </Popover>
          {(admin || d.is_custom) && (
            <Popover>
              <PopoverTrigger render={<button type="button" />} aria-label="Dashboard layout" className={cn(pill, "px-2")}><MoreHorizontal className="h-4 w-4" /></PopoverTrigger>
              <PopoverContent align="end" className="w-72 p-2 text-[13px]">
                {admin && <button type="button" disabled={busy} onClick={saveDefault} className="grid grid-cols-1 w-full gap-1 rounded-lg px-3 py-2 text-left hover:bg-muted">
                  <span className="font-medium">Save as workspace default</span><span className="text-[12px] text-muted-foreground">Everyone without their own arrangement sees this one</span></button>}
                {d.is_custom && <button type="button" disabled={busy} onClick={reset} className="grid grid-cols-1 w-full gap-1 rounded-lg px-3 py-2 text-left hover:bg-muted">
                  <span className="font-medium">Reset to default</span><span className="text-[12px] text-muted-foreground">Drop your arrangement and use the workspace's</span></button>}
              </PopoverContent>
            </Popover>
          )}
        </span>
      </div>
      {notice && (
        <p className="mt-2 text-[13px] text-muted-foreground" role="status">{notice}
          {undo && <button type="button" onClick={() => { const back = undo; commit(() => back, "Change undone."); setUndo(null) }} className="ml-2 font-medium text-primary-text hover:underline">Undo</button>}
        </p>
      )}

      <div className={cn("mt-3 grid gap-4", GRID_CLASS[cols])}>
        {packed.map(({ item, span }) => {
          const key = keyOf(item)
          const i = layout.findIndex((x) => keyOf(x) === key)
          const menu = (
            <WidgetMenu item={item} info={info(item.id)} title={titleOf(item)} first={i === 0} last={i === layout.length - 1}
              onMove={(by) => commit((l) => move(l, key, by))} onResize={(w) => commit((l) => resize(l, key, w))}
              onRemove={() => commit((l) => remove(l, key), `${titleOf(item)} removed.`)}
              onSettings={(st) => commit((l) => configure(l, key, st), "Saved to your dashboard.", 600)} />
          )
          return (
            <div key={key} className={cn("group/cell relative min-w-0", SPAN_CLASS[span], dragging === key && "opacity-50")}
              draggable={grip === key} onDragStart={() => setDragging(key)} onDragEnd={() => { setDragging(null); setGrip(null) }}
              onDragOver={(e) => { if (dragging) e.preventDefault() }} onDrop={(e) => { e.preventDefault(); if (dragging && dragging !== key) commit((l) => reorder(l, dragging, key)); setDragging(null); setGrip(null) }}>
              {/* drag by the grip (mouse); the menu's Earlier / Later does the same from the keyboard */}
              {/* a small handle centred in the card's top margin, never over its title */}
              <span onPointerDown={() => setGrip(key)} onPointerUp={() => setGrip(null)} aria-hidden title="Drag to move"
                className="absolute left-1/2 top-0 z-10 hidden h-4 w-10 -translate-x-1/2 cursor-grab items-center justify-center rounded-b-md text-muted-foreground/70 opacity-0 transition-opacity hover:text-foreground group-hover/cell:opacity-100 md:flex">
                <GripHorizontal className="h-4 w-4" /></span>
              {item.id === "kpis" && <div className="absolute -top-2 right-0 z-10 rounded-full bg-card opacity-0 shadow-card transition-opacity focus-within:opacity-100 group-hover/cell:opacity-100">{menu}</div>}
              <MenuSlot.Provider value={item.id === "kpis" ? null : menu}>
                {renderWidget(item, d.data, d.today, { tile: setTile, expand: item.id === "kpis" ? undefined : () => setExpanded(key) })}
              </MenuSlot.Provider>
            </div>
          )
        })}
        {layout.length === 0 && <p className={cn("text-[13px] text-muted-foreground", SPAN_CLASS[cols])}>Every widget is hidden. Add one with Add widget.</p>}
      </div>

      {/* a tile's pop-up: the rollouts behind the number */}
      <Dialog open={tile != null} onOpenChange={(o) => { if (!o) setTile(null) }}>
        <DialogContent className="sm:max-w-lg">
          {tileInfo && (
            <>
              <DialogHeader>
                <DialogTitle>{tileInfo.label} · {tileRows.length}</DialogTitle>
                <DialogDescription>{tile === "active" ? "Every active rollout and its state." : tile === "awaiting" ? "Rollouts whose current stage waits on the customer's approval." : "Click a rollout to open it on the flow."}</DialogDescription>
              </DialogHeader>
              <ul className="max-h-[60vh] divide-y divide-border overflow-auto text-[13px]">
                {tileRows.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 py-2">
                    <span className="min-w-0 flex-1"><Link to={`/board?rollout=${r.id}`} className="block truncate font-medium hover:underline">{r.name}</Link><span className="block truncate text-[12px] text-muted-foreground">{[r.client, r.stage].filter(Boolean).join(" · ")}</span></span>
                    <span className={cn("shrink-0 text-[12px]", tile === "overdue" ? "font-medium text-bad" : tile === "over_sla" || tile === "due_soon" ? "font-medium text-warn" : "text-muted-foreground")}>{r.text}</span>
                  </li>
                ))}
                {tileRows.length === 0 && <li className="py-3 text-muted-foreground">Nothing here.</li>}
              </ul>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* a widget's pop-up: the widget at full size, then its data as a table */}
      <Dialog open={expandedItem != null} onOpenChange={(o) => { if (!o) setExpanded(null) }}>
        <DialogContent className="sm:max-w-4xl">
          {expandedItem && (
            <>
              <DialogHeader><DialogTitle>{titleOf(expandedItem)}</DialogTitle><DialogDescription>{expandedItem.id === "custom" ? MEASURE_LABEL[String(expandedItem.settings.measure)] : info(expandedItem.id).blurb}</DialogDescription></DialogHeader>
              <div className="max-h-[75vh] overflow-auto">
                <div className="[&_section]:border-0 [&_section]:p-0 [&_section]:shadow-none [&_section>header_button]:hidden">{renderWidget(expandedItem, d.data, d.today, { tile: setTile }, true)}</div>
                {table && table.rows.length > 0 && (
                  <table className="mt-4 w-full border-collapse text-[13px]">
                    <thead><tr className="border-b border-border text-left text-[12px] text-muted-foreground">{table.columns.map((c) => <th key={c} className="px-2 py-2 font-normal">{c}</th>)}</tr></thead>
                    <tbody>{table.rows.map((r, i) => <tr key={i} className="border-b border-border last:border-0">{r.map((c, j) => <td key={j} className={cn("px-2 py-2", typeof c === "number" && "tabular-nums")}>{c}</td>)}</tr>)}</tbody>
                  </table>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

    </div>
  )
}
