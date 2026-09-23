import { useEffect, useState, type FormEvent } from "react"
import { useSearchParams } from "react-router-dom"
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ExternalLink, Search } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Stepper } from "@/components/Stepper"
import { ApiError, projects, type ProjectsData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"

// Every filter lives in the URL: shareable, back-button friendly, and the
// same query string the CSV export and Flask's nav memory understand.
const VIEWS: { key: string; label: string; params: Record<string, string> }[] = [
  { key: "active", label: "Active", params: {} },
  { key: "closed", label: "All", params: { closed: "1" } },
  { key: "overdue", label: "Overdue", params: { view: "overdue" } },
  { key: "at_risk", label: "Due soon", params: { view: "at_risk" } },
  { key: "stale", label: "Stale", params: { view: "stale" } },
]
const COLUMNS: { key: string; label: string; className?: string }[] = [
  { key: "name", label: "Project" }, { key: "client", label: "Client", className: "hidden sm:table-cell" },
  { key: "po_number", label: "PO #", className: "hidden lg:table-cell" }, { key: "stage", label: "Stage" },
  { key: "owner", label: "Owner", className: "hidden md:table-cell" }, { key: "mode", label: "Mode", className: "hidden xl:table-cell" },
  { key: "vendor", label: "Vendor", className: "hidden xl:table-cell" }, { key: "product", label: "Product", className: "hidden xl:table-cell" },
  { key: "updated", label: "Updated", className: "hidden md:table-cell" },
]
const fmtDate = (iso: string | null) => (iso ? new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" }) : "—")
const selectClass = "h-7 rounded-md border border-border bg-background px-2 text-[12.5px] font-medium text-nav-fg hover:bg-muted"

export default function Projects({ user }: { user: User }) {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<ProjectsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState(params.get("q") ?? "")
  const query = params.toString()
  useEffect(() => {
    projects(query).then((d) => { setData(d); setError(null) }).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load projects"))
  }, [query])
  useEffect(() => { setQ(params.get("q") ?? "") }, [params])

  // change some keys, drop the page (a new filter starts at the top)
  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    next.delete("page")
    for (const [k, v] of Object.entries(changes)) { if (v) next.set(k, v); else next.delete(k) }
    setParams(next)
  }
  const activeView = params.get("view") ? params.get("view")! : params.get("closed") === "1" ? "closed" : params.get("stage") || params.get("delivery_mode") ? "" : "active"
  function pickView(v: typeof VIEWS[number]) { update({ view: null, closed: null, stage: null, delivery_mode: null, ...v.params }) }
  function sortBy(key: string) {
    const flip = data?.sort === key && data.dir === "desc"
    update({ sort: key, dir: flip ? "asc" : "desc" })
  }
  function search(e: FormEvent) { e.preventDefault(); update({ q: q.trim() || null }) }
  const filtered = Boolean(params.get("q") || params.get("view") || params.get("stage") || params.get("delivery_mode"))

  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!data) return <div className="p-5 text-[13px] text-muted-foreground">Loading projects…</div>

  return (
    <div className="flex h-full flex-col px-5 pb-4 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Projects</h1>
        <p className="text-[13px] text-muted-foreground">{data.total} {filtered ? "matching" : activeView === "closed" ? "in total" : "active"}</p>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <a href={`/projects/export.csv${query ? `?${query}` : ""}`} className={buttonVariants({ variant: "outline", size: "sm" })}>Export CSV</a>
          <a href="/reports/all" target="_blank" rel="noreferrer" className={buttonVariants({ variant: "outline", size: "sm" })}>All-projects report <ExternalLink className="h-3.5 w-3.5" /></a>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {VIEWS.map((v) => (
          <button key={v.key} type="button" onClick={() => pickView(v)} aria-pressed={activeView === v.key}
            className={cn("h-7 rounded-full border px-3 text-[12.5px] font-medium transition-colors", activeView === v.key ? "border-foreground bg-foreground text-background" : "border-border text-nav-fg hover:bg-muted")}>
            {v.label}
          </button>
        ))}
        <select value={params.get("stage") ?? ""} onChange={(e) => update({ stage: e.target.value || null, view: null, closed: null })} aria-label="Stage" className={selectClass}>
          <option value="">Any stage</option>
          {data.stages.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={params.get("delivery_mode") ?? ""} onChange={(e) => update({ delivery_mode: e.target.value || null, view: null, stage: null })} aria-label="Delivery mode" className={selectClass}>
          <option value="">Any mode</option>
          {data.delivery_modes.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <form onSubmit={search} className="ml-auto flex items-center gap-1.5">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, client, PO #" aria-label="Search projects" className="h-7 w-52 text-[12.5px]" />
          <button type="submit" aria-label="Search" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7 px-2")}><Search className="h-3.5 w-3.5" /></button>
          {params.get("q") && <button type="button" onClick={() => update({ q: null })} className="text-[12px] text-muted-foreground hover:text-foreground">Clear</button>}
        </form>
      </div>

      <div className="mt-3 min-h-0 flex-1 overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-background">
            <tr className="border-b border-border text-left text-[11.5px] font-normal text-muted-foreground">
              {COLUMNS.map((c) => (
                <th key={c.key} className={cn("px-3 py-2 font-normal", c.className)}>
                  <button type="button" onClick={() => sortBy(c.key)} className={cn("inline-flex items-center gap-1 hover:text-foreground", data.sort === c.key && "font-medium text-foreground")}
                    aria-sort={data.sort === c.key ? (data.dir === "asc" ? "ascending" : "descending") : undefined}>
                    {c.label}{data.sort === c.key && (data.dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.id} className="border-b border-border last:border-0 hover:bg-muted">
                <td className="px-3 py-2">
                  <a href={`/projects/${r.id}`} className="font-medium hover:underline">{r.name}</a>
                  <span className="block text-[12px] text-muted-foreground sm:hidden">{r.client}</span>
                </td>
                <td className="hidden px-3 py-2 sm:table-cell">{r.client}</td>
                <td className="hidden px-3 py-2 text-muted-foreground lg:table-cell">{r.po_number ?? "—"}</td>
                <td className="px-3 py-2">
                  <a href={`/board?rollout=${r.id}`} className="flex items-center gap-3" title="Open on the flow">
                    <span className="w-24 shrink-0"><Stepper stages={r.stages} index={r.stage_index} state="on_track" selected={false} /></span>
                    <span className={cn("truncate text-[12.5px] font-medium", r.closed && "text-muted-foreground")}>{r.stage}</span>
                  </a>
                </td>
                <td className="hidden px-3 py-2 md:table-cell">{r.owner_name}</td>
                <td className="hidden px-3 py-2 text-muted-foreground xl:table-cell">{r.delivery_mode}</td>
                <td className="hidden px-3 py-2 text-muted-foreground xl:table-cell">{r.vendor_name ?? "—"}</td>
                <td className="hidden px-3 py-2 text-muted-foreground xl:table-cell">{r.product_name ?? "—"}</td>
                <td className="hidden whitespace-nowrap px-3 py-2 text-muted-foreground md:table-cell">{fmtDate(r.updated_at)}</td>
              </tr>
            ))}
            {data.rows.length === 0 && (
              <tr><td colSpan={COLUMNS.length} className="px-4 py-10 text-center text-[13px] text-muted-foreground">
                {filtered ? <>No projects match this filter. <button type="button" className="text-primary-text hover:underline" onClick={() => setParams({})}>Clear filters</button></>
                  : <>No projects yet.{data.can_create && user.role !== "Viewer" && <> <a href="/projects/new" className="text-primary-text hover:underline">Create the first one</a></>}</>}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-2 flex items-center gap-3 text-[12.5px] text-muted-foreground">
        {data.total_pages > 1 && (
          <>
            <button type="button" disabled={data.page <= 1} onClick={() => { const n = new URLSearchParams(params); n.set("page", String(data.page - 1)); setParams(n) }} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7")} aria-label="Previous page"><ChevronLeft className="h-3.5 w-3.5" /></button>
            <span>Page {data.page} of {data.total_pages}</span>
            <button type="button" disabled={data.page >= data.total_pages} onClick={() => { const n = new URLSearchParams(params); n.set("page", String(data.page + 1)); setParams(n) }} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7")} aria-label="Next page"><ChevronRight className="h-3.5 w-3.5" /></button>
            <span>·</span>
          </>
        )}
        <span>{data.total} project{data.total === 1 ? "" : "s"}</span>
      </div>
    </div>
  )
}
