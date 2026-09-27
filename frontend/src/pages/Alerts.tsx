import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { buttonVariants } from "@/components/ui/button"
import { alerts, ApiError, type AlertsData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { PageSkeleton } from "@/components/PageSkeleton"

const fmt = (iso: string) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
const SEV = { critical: "bg-bad-soft text-bad", warning: "bg-warn-soft text-warn", info: "bg-muted text-muted-foreground" }
const chip = (on: boolean) => cn("h-7 rounded-full border px-3 text-[12.5px] font-medium transition-colors", on ? "border-foreground bg-foreground text-background" : "border-border text-nav-fg hover:bg-muted")

export default function Alerts(_props: { user: User }) {
  const [params, setParams] = useSearchParams()
  const [d, setD] = useState<AlertsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const query = params.toString()
  useEffect(() => { document.title = "Alerts · Odin"; alerts(query).then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load alerts")) }, [query])
  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params); next.delete("page")
    for (const [k, v] of Object.entries(changes)) { if (v) next.set(k, v); else next.delete(k) }
    setParams(next)
  }
  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
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
      <div className="mt-3 min-h-0 flex-1 overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-background"><tr className="border-b border-border text-left text-[11.5px] font-normal text-muted-foreground">{["Severity", "Alert", "Project", "Raised", "Status"].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr></thead>
          <tbody>
            {d.rows.map((a) => (
              <tr key={a.id} className={cn("border-b border-border last:border-0 hover:bg-muted", a.resolved && "text-muted-foreground")}>
                <td className="px-3 py-1.5"><span className={cn("rounded-md px-1.5 py-0.5 text-[11.5px] font-medium capitalize", SEV[a.severity])}>{a.severity}</span></td>
                <td className="px-3 py-1.5"><div className="font-medium">{a.title}</div>{a.description && <div className="text-[12px] text-muted-foreground">{a.description}</div>}</td>
                <td className="px-3 py-1.5">{a.project_id && a.project_name ? <a href={`/board?rollout=${a.project_id}`} className="hover:underline">{a.project_name}</a> : "—"}</td>
                <td className="whitespace-nowrap px-3 py-1.5 text-[12px] text-muted-foreground">{fmt(a.created_at)}</td>
                <td className="whitespace-nowrap px-3 py-1.5 text-[12px]">{a.resolved ? `Resolved ${a.resolved_at ? fmt(a.resolved_at) : ""}` : <span className="font-medium text-warn">Active</span>}</td>
              </tr>
            ))}
            {d.rows.length === 0 && <tr><td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">No alerts — every rollout is inside its dates and SLAs.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex items-center gap-3 text-[12.5px] text-muted-foreground">
        {d.total_pages > 1 && (<>
          <button type="button" disabled={d.page <= 1} onClick={() => { const n = new URLSearchParams(params); n.set("page", String(d.page - 1)); setParams(n) }} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7")} aria-label="Previous page"><ChevronLeft className="h-3.5 w-3.5" /></button>
          <span>Page {d.page} of {d.total_pages}</span>
          <button type="button" disabled={d.page >= d.total_pages} onClick={() => { const n = new URLSearchParams(params); n.set("page", String(d.page + 1)); setParams(n) }} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7")} aria-label="Next page"><ChevronRight className="h-3.5 w-3.5" /></button>
          <span>·</span>
        </>)}
        <span>{d.total} alert{d.total === 1 ? "" : "s"}</span>
      </div>
    </div>
  )
}
