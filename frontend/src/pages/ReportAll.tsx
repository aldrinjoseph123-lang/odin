import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Download, Printer } from "lucide-react"
import { buttonVariants } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { PrintBrand } from "@/components/Brand"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { RagPill } from "@/components/PlanGantt"
import { RAID_KIND } from "@/components/RaidPanel"
import { Section, Table } from "@/components/ReportParts"
import { ApiError, reportAll, type PortfolioRow, type Rag, type ReportAllData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { TemplatePicker } from "@/components/TemplatePicker"
import { dayOf, fmtDate, fmtWhen, monthTicks } from "@/lib/format"

// The portfolio report: every open rollout's health, when each lands against
// its target and baseline, what is blocking, and a way into each rollout's own
// report. Partners and customers get the cut the server makes for them (no
// reasons, no baseline, only the RAID items marked for them) and no PDF.
const pill = cn(buttonVariants({ variant: "outline", size: "sm" }), "h-8 rounded-full px-3 text-[13px]")
const RAGS: Rag[] = ["red", "amber", "green", "done"]
const WORD: Record<Rag, string> = { red: "Off track", amber: "At risk", green: "On track", done: "Complete" }
const SOLID: Record<Rag, string> = { red: "bg-bad-line", amber: "bg-warn-line", green: "bg-ok-line", done: "bg-muted-foreground" }   // marks wear the -line tokens; text wears the state colour
const SOFT: Record<Rag, string> = { red: "bg-bad-soft border-bad-line", amber: "bg-warn-soft border-warn-line", green: "bg-ok-soft border-ok-line", done: "bg-muted border-border" }
const days = (n: number | null | undefined, late = "late", early = "early") => (n == null ? "—" : n === 0 ? "on plan" : n > 0 ? `${n} d ${late}` : `${-n} d ${early}`)

function Roadmap({ rows, today, external = false }: { rows: PortfolioRow[]; today: string; external?: boolean }) {
  const all = rows.flatMap((r) => [r.start, r.forecast, r.baseline ?? null, r.target_end_date]).concat(today).filter((x): x is string => !!x).map(dayOf)
  const t0 = Math.min(...all) - 5 * 864e5, t1 = Math.max(...all) + 5 * 864e5
  const pct = (iso: string) => ((dayOf(iso) - t0) / (t1 - t0)) * 100
  const span = (a: string, b: string) => ({ left: `${pct(a)}%`, width: `max(3px, ${Math.max(0, pct(b) - pct(a))}%)` })
  return (
    <div className="overflow-x-clip text-[12px]">
      <div className="grid grid-cols-[minmax(120px,220px)_minmax(0,1fr)] gap-x-3">
        <span />
        <div className="relative h-5 text-[11px] text-muted-foreground">
          {monthTicks(t0, t1, 8).map((m) => <span key={m.t} className="absolute top-0 -translate-x-1/2" style={{ left: `${((m.t - t0) / (t1 - t0)) * 100}%` }}>{m.label}</span>)}
        </div>
        {rows.map((r) => {
          const end = r.forecast ?? today
          const now = today < r.start ? r.start : today > end ? end : today
          const label = `${r.name} (${WORD[r.rag]}): started ${fmtDate(r.start)}, forecast to finish ${fmtDate(r.forecast)}`
            + (r.target_end_date ? `, target ${fmtDate(r.target_end_date)} (${days(r.vs_target_days, "after", "before")})` : ", no target")
            + (r.baseline ? `, baseline finish ${fmtDate(r.baseline)} (${days(r.vs_baseline_days)})` : "")
          return (
            <div key={r.id} className="contents">
              <Link to={external && !r.report ? `/projects/${r.id}` : `/projects/${r.id}/report`} title={`${r.name} · ${r.client} · ${WORD[r.rag]}`} className="flex h-9 min-w-0 items-center gap-2 hover:underline">
                {/* the health is a word for everyone, the dot only repeats it */}
                <span className={cn("h-2 w-2 shrink-0 rounded-full", SOLID[r.rag])} aria-hidden /><span className="sr-only">{WORD[r.rag]}: </span>
                <span className="truncate font-medium">{r.name}</span>
                <span className="hidden truncate text-muted-foreground xl:inline">{r.client}</span>
              </Link>
              <Tooltip>
                <TooltipTrigger render={<div />} tabIndex={0} role="img" aria-label={label} className="relative h-9 border-b border-border/60 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
                  <span className="absolute inset-y-0 w-[1.5px] bg-primary/60" style={{ left: `${pct(today)}%` }} aria-hidden />
                  <span className={cn("absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full", SOLID[r.rag])} style={span(r.start, now)} aria-hidden />
                  {end > now && <span className={cn("absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full border", SOFT[r.rag])} style={span(now, end)} aria-hidden />}
                  {r.baseline && <span className="absolute top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-foreground/50" style={{ left: `${pct(r.baseline)}%` }} aria-hidden />}
                  {r.target_end_date && <span className="absolute top-1/2 h-5 w-0 -translate-y-1/2 border-l-[1.5px] border-dashed border-bad-line" style={{ left: `${pct(r.target_end_date)}%` }} aria-hidden />}
                </TooltipTrigger>
                <TooltipContent>{label}</TooltipContent>
              </Tooltip>
            </div>
          )
        })}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground" aria-label="Legend">
        <li className="flex items-center gap-2"><span className="h-2.5 w-5 rounded-full bg-foreground/60" />Done so far</li>
        <li className="flex items-center gap-2"><span className="h-2.5 w-5 rounded-full border border-border bg-muted" />Forecast</li>
        {rows.some((r) => r.baseline) && <li className="flex items-center gap-2"><span className="h-3 w-[2px] rounded-full bg-foreground/50" />Baseline finish</li>}
        <li className="flex items-center gap-2"><span className="h-3 w-0 border-l-[1.5px] border-dashed border-bad-line" />Target</li>
        <li className="flex items-center gap-2"><span className="h-3 w-[1.5px] bg-primary/60" />Today</li>
        <li>Bar colour is the rollout's health</li>
      </ul>
    </div>
  )
}

export default function ReportAll({ user }: { user: User }) {
  const external = user.kind === "external"
  const [d, setD] = useState<ReportAllData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [template, setTemplate] = useState<number | null>(null)
  useEffect(() => { document.title = "Portfolio report · Odin"; reportAll(template).then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")) }, [template])
  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  const s = d.summary
  const internal = d.audience === "internal"
  const hide = (key: string) => (!d.template || d.template.sections.some((x) => x.key === key && x.on) ? undefined : "hidden")   // the document template's sections
  const league = internal ? d.rows.filter((r) => r.vs_baseline_days).sort((a, b) => (b.vs_baseline_days ?? 0) - (a.vs_baseline_days ?? 0)).slice(0, 10) : []
  const tiles: { label: string; value: string; sub: string; bad?: boolean }[] = [
    { label: "Late against target", value: String(s.late_vs_target), sub: `of ${s.count} rollouts, by forecast`, bad: s.late_vs_target > 0 },
    ...(internal ? [{ label: "Behind baseline", value: String(s.behind_baseline ?? 0), sub: s.avg_slip == null ? "no baselines yet" : `average ${s.avg_slip > 0 ? "+" : ""}${s.avg_slip} d` }] : []),
    { label: "Open blockers", value: String(s.blockers), sub: "across the portfolio", bad: s.blockers > 0 },
    { label: "Finishing in 30 days", value: String(s.finishing_30d), sub: "by forecast" },
  ]
  return (
    <div className="mx-auto w-full max-w-6xl px-5 pb-10 pt-4 print:max-w-none print:px-0">
      <PrintBrand />
      <header className="flex flex-wrap items-end gap-x-4 gap-y-2">
        <div>
          <h1 className="text-[24px] font-semibold tracking-tight">Portfolio report</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">{s.count} active rollout{s.count === 1 ? "" : "s"} · as of {fmtDate(d.today)} · generated {fmtWhen(d.generated_at, true)}</p>
        </div>
        <span className="ml-auto flex gap-2 print:hidden">
          {internal && <TemplatePicker kind="portfolio" value={template} onChange={setTemplate} />}
          {internal && <a href={`/reports/all.pdf${template ? `?template=${template}` : ""}`} target="_blank" rel="noreferrer" className={pill}><Download className="h-3.5 w-3.5" /> PDF</a>}
          <button type="button" onClick={() => window.print()} className={pill}><Printer className="h-3.5 w-3.5" /> Print</button>
        </span>
      </header>

      <div className={cn("mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,2fr)]", hide("health"))}>
        <section className="panel p-4 print:shadow-none" aria-label="Health">
          <div className="text-[12px] text-muted-foreground">Health</div>
          <div className="mt-2 flex h-3 gap-1 overflow-hidden rounded-full bg-muted" role="img" aria-label={RAGS.filter((g) => s.health[g]).map((g) => `${s.health[g]} ${WORD[g].toLowerCase()}`).join(", ") || "no rollouts"}>
            {RAGS.map((g) => s.health[g] ? <span key={g} className={SOLID[g]} style={{ flexGrow: s.health[g] }} /> : null)}
          </div>
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
            {RAGS.map((g) => <li key={g} className={cn("flex items-center gap-2", !s.health[g] && "text-muted-foreground")}><span className={cn("h-2 w-2 rounded-full", SOLID[g])} aria-hidden /><span className="font-semibold tabular-nums">{s.health[g] ?? 0}</span> {WORD[g].toLowerCase()}</li>)}
          </ul>
          {internal && s.no_plan > 0 && <p className="mt-2 text-[12px] text-muted-foreground">{s.no_plan} without a plan: their forecast runs on stage SLAs.</p>}
        </section>
        <div className={cn("grid grid-cols-2 gap-3", internal ? "sm:grid-cols-4" : "sm:grid-cols-3")}>
          {tiles.map((t) => (
            <div key={t.label} className="panel p-4 print:shadow-none">
              <div className="text-[12px] text-muted-foreground">{t.label}</div>
              <div className={cn("mt-2 text-[24px] font-semibold leading-none tracking-tight tabular-nums", t.bad && "text-bad")}>{t.value}</div>
              <div className="mt-1 text-[12px] text-muted-foreground">{t.sub}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4">
        {d.rows.length > 0 && <Section n title="Roadmap" sub="start to forecast finish, worst health first; open a rollout for its report" className={hide("roadmap")}><Roadmap rows={d.rows} today={d.today} external={external} /></Section>}

        <div className={cn("grid gap-4", league.length > 0 && "lg:grid-cols-2")}>
          {league.length > 0 && (
            <Section n title="Slippage" sub="against each rollout's baseline" className={hide("slippage")}>
              <Table head={["Rollout", "Stage", "Baseline", "Target", "Confidence"]}
                rows={league.map((r) => [<Link key="n" to={`/projects/${r.id}/report`} className="font-medium hover:underline">{r.name}</Link>, r.stage, days(r.vs_baseline_days), days(r.vs_target_days, "after", "before"), r.confidence ?? "—"])}
                tone={(i, c) => (c === 2 && (league[i].vs_baseline_days ?? 0) > 0 ? "font-medium text-bad" : c === 3 && (league[i].vs_target_days ?? 0) > 0 ? "text-bad" : undefined)} />
            </Section>
          )}
          <Section n title={internal ? "Blockers and high-impact risks" : "Open points"} sub={`${d.risks.length} open`} className={hide("risks")}>
            <ul className="divide-y divide-border text-[13px]">
              {d.risks.map((x, i) => {
                const K = RAID_KIND[x.kind]
                return (
                  <li key={i} className="flex items-start gap-3 py-2">
                    <K.icon className={cn("mt-1 h-4 w-4 shrink-0", x.kind === "blocker" ? "text-bad" : "text-muted-foreground")} aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium">{x.title}</span>
                      <span className="block text-[12px] text-muted-foreground"><Link to={`/projects/${x.project_id}`} className="hover:underline">{x.project}</Link> · {K.label}{x.owner_name && ` · ${x.owner_name}`}{x.due_date && ` · due ${fmtDate(x.due_date)}`}</span>
                    </span>
                  </li>
                )
              })}
              {d.risks.length === 0 && <li className="py-3 text-muted-foreground">Nothing blocking, no high-impact risk open.</li>}
            </ul>
          </Section>
        </div>

        <Section n title="Every rollout" className={hide("table")}>
          <Table head={["Rollout", "Health", "Stage", "Done", "Forecast", "Target", "PM", "Report"]}
            rows={d.rows.map((r) => [
              <span key="n"><Link to={`/projects/${r.id}`} className="font-medium hover:underline">{r.name}</Link><span className="block text-[12px] text-muted-foreground">{r.client}</span></span>,
              <RagPill key="h" rag={r.rag} className="whitespace-nowrap" />,
              <span key="s" className="whitespace-nowrap">{r.stage_number}/{r.stage_count} · {r.stage}</span>,
              <span key="p" className="flex items-center gap-2"><span className="h-1.5 w-12 overflow-hidden rounded-full bg-muted"><span className="block h-full rounded-full bg-primary" style={{ width: `${r.pct_complete}%` }} /></span><span className="tabular-nums">{r.pct_complete}%</span></span>,
              <span key="f" className="whitespace-nowrap">{fmtDate(r.forecast)}{r.vs_target_days != null && r.vs_target_days > 0 && <span className="block text-[12px] text-bad">{r.vs_target_days} d after target</span>}</span>,
              <span key="t" className="whitespace-nowrap">{fmtDate(r.target_end_date)}</span>,
              r.owner_name,
              external && !r.report ? <span key="r" className="whitespace-nowrap text-muted-foreground">Not published yet</span>
                : <Link key="r" to={`/projects/${r.id}/report`} className="whitespace-nowrap text-primary-text hover:underline">{r.report ? `v${r.report.version} · ${fmtDate(r.report.created_at)}` : "Live"}</Link>,
            ])} />
          {d.rows.length === 0 && <p className="py-4 text-center text-[13px] text-muted-foreground">No active rollouts.</p>}
        </Section>
      </div>
    </div>
  )
}
