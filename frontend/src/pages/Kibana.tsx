import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { ExternalLink } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { buttonVariants } from "@/components/ui/button"
import { PageSkeleton } from "@/components/PageSkeleton"
import { ApiError, kibana, type KibanaData } from "@/lib/api"
import { cn } from "@/lib/utils"

// The Kibana view: the Elastic dashboards an admin listed under Settings →
// Integrations, framed inside Odin one at a time. Kibana draws its own
// interface in the frame; Odin only names the dashboard and links out.
export function Kibana() {
  const [d, setD] = useState<KibanaData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [at, setAt] = useState(0)
  useEffect(() => { kibana().then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")) }, [])
  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!d) return <PageSkeleton />
  const current = d.dashboards[at] ?? d.dashboards[0]
  if (!current) {
    return (
      <div className="px-6 py-12 text-center text-[13px] text-muted-foreground">
        <p className="font-medium text-foreground">No Kibana dashboards yet.</p>
        <p className="mt-1">{d.can_manage ? "List them under Settings → Integrations, one per line as “Name | address”, using each dashboard's share link with embed=true." : "Ask an Odin admin to list them under Settings → Integrations."}</p>
        {d.can_manage && <Link to="/settings/integrations" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-4 rounded-full")}>Open Integrations</Link>}
      </div>
    )
  }
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 px-4 pb-3 pt-3">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Kibana dashboards">
          {d.dashboards.map((x, i) => (
            <button key={x.url} type="button" role="tab" aria-selected={i === at} onClick={() => setAt(i)}
              className={cn("h-7 rounded-full border px-3 text-[12px] font-medium", i === at ? "border-foreground bg-foreground text-background" : "border-border text-nav-fg hover:bg-muted")}>{x.name}</button>
          ))}
        </div>
        <a href={current.url} target="_blank" rel="noreferrer" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "ml-auto h-7 rounded-full px-3 text-[12px]")}>Open in Kibana <ExternalLink className="h-3.5 w-3.5" /></a>
      </div>
      {/* Kibana needs scripts and its own origin; nothing here grants it more than a normal tab would have */}
      <iframe key={current.url} src={current.url} title={`Kibana: ${current.name}`} className="min-h-[560px] w-full flex-1 border-t border-border bg-card"
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads" referrerPolicy="no-referrer" />
    </div>
  )
}
