import { Fragment, useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { alerts, ApiError, type AlertsData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Pager } from "@/components/Pager"
import { fmtWhen } from "@/lib/format"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"

const fmt = (iso: string) => fmtWhen(iso, true)
const chip = (on: boolean) => cn("h-7 rounded-full border px-3 text-[13px] font-medium transition-colors", on ? "border-foreground bg-foreground text-background" : "border-border text-nav-fg hover:bg-muted")

export default function Alerts(_props: { user: User }) {
  const [params, setParams] = useSearchParams()
  const [d, setD] = useState<AlertsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const query = params.toString()
  useEffect(() => {
    document.title = "Alerts · Odin"
    let live = true   // only the latest filter's answer is shown
    alerts(query).then((x) => { if (live) setD(x) }).catch((e) => { if (live) setError(e instanceof ApiError ? e.message : "Could not load alerts") })
    return () => { live = false }
  }, [query])
  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params); next.delete("page")
    for (const [k, v] of Object.entries(changes)) { if (v) next.set(k, v); else next.delete(k) }
    setParams(next)
  }
  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  return (
    <div className="flex h-full flex-col px-5 pb-4 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Alerts</h1>
        <p className="text-[13px] text-muted-foreground">{d.total} {d.show_resolved ? "in total" : "active"}</p>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => update({ resolved: null })} aria-pressed={!d.show_resolved} className={chip(!d.show_resolved)}>Active</button>
        <button type="button" onClick={() => update({ resolved: "1" })} aria-pressed={d.show_resolved} className={chip(d.show_resolved)}>All</button>
        <span className="mx-1 h-4 w-px bg-border" />
        <button type="button" onClick={() => update({ type: null })} aria-pressed={!d.alert_type} className={chip(!d.alert_type)}>All types</button>
        {Object.entries(d.types).map(([k, title]) => <button key={k} type="button" onClick={() => update({ type: k })} aria-pressed={d.alert_type === k} className={chip(d.alert_type === k)}>{title}</button>)}
      </div>
      <div className="mt-3 min-h-0 flex-1 overflow-auto panel">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-card"><tr className="border-b border-border text-left text-[12px] font-normal text-muted-foreground">{["Alert", "Project", "Raised", "Status"].map((h, i) => <th key={h} className={cn("px-3 py-2 font-normal", i > 1 && "text-right", i > 0 && "hidden sm:table-cell")}>{h}</th>)}</tr></thead>
          <tbody>
            {d.rows.map((a, i) => {
              // chunked the way the list is sorted: open alerts by severity, then the resolved ones
              const group = (x: typeof a) => (x.resolved ? "resolved" : x.severity)
              const age = group(a), head = i === 0 || group(d.rows[i - 1]) !== age
              return (<Fragment key={a.id}>
              {head && <tr className="bg-muted/50"><th scope="rowgroup" colSpan={4} className="px-3 py-1 text-left text-[12px] font-semibold capitalize text-nav-fg">
                <span className={cn("mr-2 inline-block h-2 w-2 rounded-full", age === "critical" ? "bg-bad-line" : age === "warning" ? "bg-warn-line" : "bg-input")} aria-hidden />{age}</th></tr>}
              <tr className={cn("border-b border-border last:border-0 hover:bg-muted", a.resolved && "text-muted-foreground")}>
                {/* the receipt: what happened on the left, its weight, age and state on the right */}
                <td className="px-3 py-2 wrap-anywhere"><div className="font-medium">{a.title}</div>{a.description && <div className="text-[12px] text-muted-foreground">{a.description}</div>}
                  {/* phones: one stacked receipt */}
                  <div className="mt-1 text-[12px] text-muted-foreground sm:hidden">
                    {a.project_id && a.project_name && <><a href={`/board?rollout=${a.project_id}`} className="text-foreground hover:underline">{a.project_name}</a> · </>}
                    {fmt(a.created_at)} · {a.resolved ? "Resolved" : "Open"}
                  </div></td>
                <td className="hidden px-3 py-2 wrap-anywhere sm:table-cell">{a.project_id && a.project_name ? <a href={`/board?rollout=${a.project_id}`} className="hover:underline">{a.project_name}</a> : "—"}</td>
                <td className="hidden whitespace-nowrap px-3 py-2 text-right text-[12px] text-muted-foreground sm:table-cell">{fmt(a.created_at)}</td>
                <td className="hidden whitespace-nowrap px-3 py-2 text-right text-[12px] text-muted-foreground sm:table-cell">{a.resolved ? `Resolved ${a.resolved_at ? fmt(a.resolved_at) : ""}` : "Open"}</td>
              </tr>
              </Fragment>)
            })}
            {d.rows.length === 0 && <tr><td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">No alerts — every rollout is inside its dates and SLAs.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex items-center gap-3 text-[13px] text-muted-foreground">
        {d.total_pages > 1 && <>
          <Pager page={d.page} pages={d.total_pages} href={(n) => { const q = new URLSearchParams(params); q.set("page", String(n)); return `?${q}` }}
            onPage={(n) => { const q = new URLSearchParams(params); q.set("page", String(n)); setParams(q) }} />
          <span>·</span>
        </>}
        <span>{d.total} alert{d.total === 1 ? "" : "s"}</span>
      </div>
    </div>
  )
}
