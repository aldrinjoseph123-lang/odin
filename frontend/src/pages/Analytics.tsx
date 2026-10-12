import { useEffect, useState } from "react"
import { PanelTitle } from "@/components/PanelTitle"
import { EmptyState } from "@/components/EmptyState"
import { chip } from "@/lib/ui"
import { useSearchParams } from "react-router-dom"
import { analytics, ApiError, type AnalyticsData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { StatTile } from "@/components/StatTile"

const d1 = (n: number | null | undefined) => (n == null ? "—" : n > 0 && n < 0.05 ? "<0.1" : n.toFixed(1))   // a same-day close is not "0.0 days" (UX-23)

export default function Analytics(_props: { user: User }) {
  const [params, setParams] = useSearchParams()
  const [d, setD] = useState<AnalyticsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const tid = Number(params.get("template")) || null
  useEffect(() => {
    document.title = "Cycle time · Odin"
    let live = true   // only the latest template's answer is shown
    analytics(tid).then((x) => { if (live) setD(x) }).catch((e) => { if (live) setError(e instanceof ApiError ? e.message : "Could not load") })
    return () => { live = false }
  }, [tid])
  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  const s = d.stats
  const scale = s ? Math.max(0, ...s.stages.map((r) => r.avg_days ?? 0)) : 0
  const peak = s ? Math.max(0, ...s.throughput.map(([, n]) => n)) : 0
  const tname = d.templates.find((t) => t.id === d.template_id)?.name
  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Cycle time</h1>
        <p className="max-w-prose text-[13px] text-muted-foreground">where rollouts get stuck, per stage template</p>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {d.templates.map((t) => <button key={t.id} type="button" onClick={() => setParams({ template: String(t.id) })} aria-pressed={t.id === d.template_id} className={chip(t.id === d.template_id)}>{t.name}</button>)}
        {d.custom_count > 0 && <span className="text-[12px] text-muted-foreground">{d.custom_count} rollout{d.custom_count === 1 ? "" : "s"} on a custom stage list (not compared)</span>}
      </div>
      {!s ? <EmptyState className="mt-4">No stage template yet — create one in Settings.</EmptyState> : (
        <>
          <p className="mt-3 max-w-3xl text-[13px] text-muted-foreground">Timings compare only rollouts that share a stage list, so this is <span className="font-medium text-foreground">{tname}</span> across {s.measured_projects} project{s.measured_projects === 1 ? "" : "s"}. Averages count stages a project has already left; the stage it sits in now is under Aging.</p>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Slowest stage" value={s.slowest?.stage ?? "—"} sub={s.slowest ? `${d1(s.slowest.avg_days)} days avg` : undefined} tone="warn" />
            <StatTile label="Lead time (avg)" value={d1(s.lead_avg)} sub={`${s.completed_count} completed rollout${s.completed_count === 1 ? "" : "s"}`} />
            <StatTile label="Lead time (median)" value={d1(s.lead_median)} sub="days, start to closed" />
            <StatTile label="Oldest open stage" value={s.aging[0] ? String(Math.round(s.aging[0].days)) : "—"} sub={s.aging[0]?.project_name ?? "nothing ageing"} tone="bad" />
          </div>
          <div className="mt-4 overflow-auto panel" tabIndex={0} role="region" aria-label="Time per stage">
            <table className="w-full border-collapse text-[13px]">
              <thead><tr className="border-b border-border text-left text-[12px] font-normal text-muted-foreground">{["Stage", "SLA", "Completed visits", "Avg days", "Median", "Longest", "In stage now"].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr></thead>
              <tbody>
                {s.stages.map((r) => {
                  const target = d.slas[r.stage]
                  return (
                    <tr key={r.stage} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 font-medium">{r.stage}</td>
                      <td className="px-3 py-2">{target ? <span className={cn("whitespace-nowrap", r.avg_days != null && r.avg_days > target && "rounded-md bg-bad-soft px-2 py-1 font-medium text-bad")}>{target} d{r.avg_days != null && r.avg_days > target && " · over"}</span> : "—"}</td>
                      <td className="px-3 py-2 text-muted-foreground">{r.visits || "—"}</td>
                      <td className="px-3 py-2">{r.avg_days == null ? "—" : (
                        <span className="flex items-center gap-2"><span className="h-1.5 w-32 rounded-full bg-muted"><span className="block h-1.5 rounded-full bg-foreground" style={{ width: `${scale ? (r.avg_days / scale) * 100 : 0}%` }} /></span>{d1(r.avg_days)}</span>
                      )}</td>
                      <td className="px-3 py-2 text-muted-foreground">{d1(r.median_days)}</td>
                      <td className="px-3 py-2 text-muted-foreground">{d1(r.max_days)}</td>
                      <td className="px-3 py-2 text-muted-foreground">{r.in_stage_now || "—"}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section className="panel p-4">
              <PanelTitle n={false} className="mb-2" hint="days in current stage">Aging</PanelTitle>
              <ul className="divide-y divide-border text-[13px]">
                {s.aging.map((a) => (
                  <li key={`${a.project_id}-${a.stage}`} className="flex items-center gap-3 py-2">
                    <a href={`/board?rollout=${a.project_id}`} className="min-w-0 flex-1 truncate font-medium hover:underline">{a.project_name}</a>
                    <span className="truncate text-[13px] text-muted-foreground">{a.stage}</span>
                    <span className={cn("whitespace-nowrap text-right tabular-nums", a.days >= 30 ? "font-medium text-bad" : a.days >= 14 ? "font-medium text-warn" : "")}>{Math.round(a.days)} d{a.days >= 30 ? " · over 30" : a.days >= 14 ? " · over 14" : ""}</span>
                  </li>
                ))}
                {s.aging.length === 0 && <li className="py-2 text-muted-foreground">Nothing in progress.</li>}
              </ul>
            </section>
            <section className="panel p-4">
              <PanelTitle n={false} className="mb-2" hint="rollouts closed per month">Throughput</PanelTitle>
              <ul className="grid grid-cols-1 gap-2 text-[13px]">
                {s.throughput.map(([month, n]) => (
                  <li key={month} className="flex items-center gap-3"><span className="w-16 text-[12px] text-muted-foreground">{month}</span><span className="h-2 flex-1 rounded-full bg-muted"><span className="block h-2 rounded-full bg-ok-line" style={{ width: `${peak ? (n / peak) * 100 : 0}%` }} /></span><span className="w-6 text-right">{n}</span></li>
                ))}
                {s.throughput.length === 0 && <EmptyState as="li">No rollouts have reached the final stage yet.</EmptyState>}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  )
}
