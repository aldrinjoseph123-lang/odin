import { Fragment, useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, audit, type AuditData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { dayBucket, fmtWhen } from "@/lib/format"
import { UserAvatar } from "@/components/UserAvatar"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"

const fmt = (iso: string) => fmtWhen(iso, true)
const selectClass = "h-7 max-w-48 rounded-md border border-border bg-background px-2 text-[13px] font-medium text-nav-fg hover:bg-muted"

export default function Audit(_props: { user: User }) {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<AuditData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const query = params.toString()
  useEffect(() => {
    document.title = "Audit log · Odin"
    audit(query).then((d) => { setData(d); setError(null) }).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load the audit log"))
  }, [query])
  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    next.delete("page")
    for (const [k, v] of Object.entries(changes)) { if (v) next.set(k, v); else next.delete(k) }
    setParams(next)
  }
  function goto(page: number) { const n = new URLSearchParams(params); n.set("page", String(page)); setParams(n) }
  const filtered = ["user", "action", "project_id", "from", "to"].some((k) => params.get(k))

  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />

  return (
    <div className="flex h-full flex-col px-5 pb-4 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Audit log</h1>
        <p className="text-[13px] text-muted-foreground">{data.total} {filtered ? "matching" : ""} entr{data.total === 1 ? "y" : "ies"} · append-only</p>
        <div className="ml-auto flex items-center gap-2">
          <a href={`/audit-logs/export.csv${query ? `?${query}` : ""}`} className={buttonVariants({ variant: "outline", size: "sm" })}>Export CSV</a>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select value={params.get("user") ?? ""} onChange={(e) => update({ user: e.target.value || null })} aria-label="Filter by user" className={selectClass}>
          <option value="">All users</option>{data.usernames.map((u) => <option key={u} value={u}>{u}</option>)}
        </select>
        <select value={params.get("action") ?? ""} onChange={(e) => update({ action: e.target.value || null })} aria-label="Filter by action" className={selectClass}>
          <option value="">All actions</option>{data.actions.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={params.get("project_id") ?? ""} onChange={(e) => update({ project_id: e.target.value || null })} aria-label="Filter by project" className={selectClass}>
          <option value="">All projects</option>{data.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <Input type="date" value={params.get("from") ?? ""} onChange={(e) => update({ from: e.target.value || null })} aria-label="From date" className="h-7 w-36 text-[13px]" />
        <Input type="date" value={params.get("to") ?? ""} onChange={(e) => update({ to: e.target.value || null })} aria-label="To date" className="h-7 w-36 text-[13px]" />
        {filtered && <button type="button" onClick={() => setParams({})} className="text-[12px] text-muted-foreground hover:text-foreground">Clear</button>}
      </div>

      <div className="mt-3 min-h-0 flex-1 overflow-auto panel">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b border-border text-left text-[12px] font-normal text-muted-foreground">
              {["When", "User", "Action", "Resource", "Details", "IP"].map((h, i) => <th key={h} className={cn("px-3 py-2 font-normal", i === 5 && "hidden lg:table-cell")}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r, i) => {
              // one header per day, so a long log reads in chunks (Today, Yesterday, 6 Oct 2026…)
              const day = dayBucket(r.timestamp), head = i === 0 || dayBucket(data.rows[i - 1].timestamp) !== day
              return (<Fragment key={r.id}>
              {head && <tr className="bg-muted/50"><th scope="rowgroup" colSpan={6} className="px-3 py-1 text-left text-[12px] font-semibold text-nav-fg">{day}</th></tr>}
              <tr className="border-b border-border align-top last:border-0 hover:bg-muted">
                <td className="whitespace-nowrap px-3 py-2 text-[12px] text-muted-foreground">{fmt(r.timestamp)}</td>
                <td className="px-3 py-2"><span className="inline-flex items-center gap-2"><UserAvatar name={r.username || "?"} className="h-5 w-5" />{r.username}</span></td>
                <td className="px-3 py-2"><span className="rounded-md bg-muted px-2 py-1 font-mono text-[12px]">{r.action}</span></td>
                <td className="px-3 py-2">
                  {r.resource_type && <span className="text-[12px] text-muted-foreground">{r.resource_type} </span>}
                  {r.resource_type === "project" && r.resource_id ? <a href={`/projects/${r.resource_id}`} className="font-medium hover:underline">{r.resource_name ?? `#${r.resource_id}`}</a>
                    : r.resource_name ? <span>{r.resource_name}</span> : r.resource_id ? <span className="text-muted-foreground">#{r.resource_id}</span> : null}
                </td>
                <td className="max-w-md break-words px-3 py-2 text-[13px]">{r.details}</td>
                <td className="hidden whitespace-nowrap px-3 py-2 text-[12px] text-muted-foreground lg:table-cell">{r.ip_address}</td>
              </tr>
              </Fragment>)
            })}
            {data.rows.length === 0 && <tr><td colSpan={6} className="px-4 py-10 text-center text-[13px] text-muted-foreground">Nothing matches this filter.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex items-center gap-3 text-[13px] text-muted-foreground">
        {data.total_pages > 1 && (
          <>
            <button type="button" disabled={data.page <= 1} onClick={() => goto(data.page - 1)} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7")} aria-label="Previous page"><ChevronLeft className="h-3.5 w-3.5" /></button>
            <span>Page {data.page} of {data.total_pages}</span>
            <button type="button" disabled={data.page >= data.total_pages} onClick={() => goto(data.page + 1)} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7")} aria-label="Next page"><ChevronRight className="h-3.5 w-3.5" /></button>
            <span>·</span>
          </>
        )}
        <span>{data.total} entr{data.total === 1 ? "y" : "ies"}</span>
      </div>
    </div>
  )
}
