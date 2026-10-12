import { useEffect, useState } from "react"
import { chip } from "@/lib/ui"
import { Link } from "react-router-dom"
import { ExternalLink } from "lucide-react"
import { buttonVariants } from "@/components/ui/button"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { ApiError, kibana, type KibanaData } from "@/lib/api"
import { cn } from "@/lib/utils"

// The Kibana view of the flow: the Elastic dashboards an admin listed under
// Settings → Integrations, framed inside Odin — for one rollout at a time
// when an address carries {project}, {client} or {po}. The rollout is the
// flow's own ?rollout=, so a dashboard opened from a rollout shows it.
export function Kibana({ rollout, onRollout }: { rollout: number | null; onRollout: (id: number | null) => void }) {
  const [d, setD] = useState<KibanaData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [at, setAt] = useState(0)
  useEffect(() => { kibana(rollout).then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")) }, [rollout])
  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  const current = d.dashboards[at] ?? d.dashboards[0]
  if (!current) {
    return (
      <div className="px-6 py-12 text-center text-[13px] text-muted-foreground">
        <p className="font-medium text-foreground">No Kibana dashboards yet.</p>
        <p className="mt-1">{d.can_manage ? "List them under Settings › Integrations, one per line as “Name | address”, using each dashboard's share link with embed=true. Put {project}, {client} or {po} in an address and the view shows one rollout at a time." : "Ask an Odin admin to list them under Settings › Integrations."}</p>
        {d.can_manage && <Link to="/settings/integrations" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-4 rounded-full")}>Open Integrations</Link>}
      </div>
    )
  }
  const perRollout = d.dashboards.some((x) => x.per_rollout)
  const chosen = d.rollouts.find((r) => r.id === d.rollout)
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 px-4 pb-3 pt-3">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Kibana dashboards">
          {d.dashboards.map((x, i) => (
            <button key={x.name} type="button" role="tab" aria-selected={i === at} onClick={() => setAt(i)}
              className={chip(i === at)}>{x.name}</button>
          ))}
        </div>
        {perRollout && (
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
            Rollout
            <select value={d.rollout ?? ""} onChange={(e) => onRollout(e.target.value ? Number(e.target.value) : null)} aria-label="Rollout shown in Kibana" className="h-7 max-w-64 rounded-md border border-input bg-background px-2 text-[13px] text-foreground">
              <option value="">Pick a rollout</option>
              {d.rollouts.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </label>
        )}
        <a href={current.url} target="_blank" rel="noreferrer" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "ml-auto h-7 rounded-full px-3 text-[12px]")}>Open in Kibana <ExternalLink className="h-3.5 w-3.5" /></a>
      </div>
      {current.per_rollout && !chosen ? (
        <div className="flex flex-1 items-center justify-center px-6 py-12 text-center text-[13px] text-muted-foreground">This dashboard is drawn for one rollout at a time — pick one above, or open it from a rollout on the flow.</div>
      ) : (
        <>
          {chosen && current.per_rollout && <p className="px-4 pb-2 text-[12px] text-muted-foreground">Showing <span className="font-medium text-foreground">{chosen.name}</span>{chosen.client && ` · ${chosen.client}`}{chosen.po_number && ` · ${chosen.po_number}`}</p>}
          {/* Kibana needs scripts and its own origin; nothing here grants it more than a normal tab would have */}
          <iframe key={current.url} src={current.url} title={`Kibana: ${current.name}${chosen ? ` for ${chosen.name}` : ""}`} className="min-h-[560px] w-full flex-1 border-t border-border bg-card"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads" referrerPolicy="no-referrer" />
        </>
      )}
    </div>
  )
}
