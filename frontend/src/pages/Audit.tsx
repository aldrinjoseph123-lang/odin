import { Fragment, useEffect, useState } from "react"
import { PageHeader } from "@/components/PageHeader"
import { filterSelect, th, td } from "@/lib/ui"
import { EmptyState } from "@/components/EmptyState"
import { useSearchParams } from "react-router-dom"
import { buttonVariants } from "@/components/ui/button"
import { ApiError, audit, type AuditData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Pager } from "@/components/Pager"
import { DatePicker } from "@/components/DatePicker"
import { actionText, dayBucket, fmtWhen } from "@/lib/format"
import { UserAvatar } from "@/components/UserAvatar"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"


export default function Audit(_props: { user: User }) {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<AuditData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const query = params.toString()
  useEffect(() => {
    document.title = "Audit log · Odin"
    let live = true   // only the latest filter's answer is shown
    audit(query).then((d) => { if (live) { setData(d); setError(null) } }).catch((e) => { if (live) setError(e instanceof ApiError ? e.message : "Could not load the audit log") })
    return () => { live = false }
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
      <PageHeader title="Audit log" lede={`${data.total} ${filtered ? "matching " : ""}entr${data.total === 1 ? "y" : "ies"} · append-only`}
        actions={<a href={`/audit-logs/export.csv${query ? `?${query}` : ""}`} className={buttonVariants({ variant: "outline", size: "sm" })}>Export CSV</a>} />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select value={params.get("user") ?? ""} onChange={(e) => update({ user: e.target.value || null })} aria-label="Filter by user" className={cn(filterSelect, "max-w-48")}>
          <option value="">All users</option>{data.usernames.map((u) => <option key={u} value={u}>{u}</option>)}
        </select>
        <select value={params.get("action") ?? ""} onChange={(e) => update({ action: e.target.value || null })} aria-label="Filter by action" className={cn(filterSelect, "max-w-48")}>
          <option value="">All actions</option>{data.actions.map((a) => <option key={a} value={a}>{actionText(a)}</option>)}
        </select>
        <select value={params.get("project_id") ?? ""} onChange={(e) => update({ project_id: e.target.value || null })} aria-label="Filter by rollout" className={cn(filterSelect, "max-w-48")}>
          <option value="">All rollouts</option>{data.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <DatePicker value={params.get("from") ?? ""} onChange={(v) => update({ from: v || null })} label="From date" placeholder="From" className="h-8 w-40" />
        <DatePicker value={params.get("to") ?? ""} onChange={(v) => update({ to: v || null })} label="To date" placeholder="To" className="h-8 w-40" />
        {filtered && <button type="button" onClick={() => setParams({})} className="text-[12px] text-muted-foreground hover:text-foreground">Clear</button>}
      </div>

      <div className="mt-3 min-h-0 flex-1 overflow-auto panel">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b border-border">
              {["When", "User", "Action", "Resource", "Details", "IP"].map((h, i) => <th key={h} className={cn(th, i === 5 && "hidden lg:table-cell")}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r, i) => {
              // one header per day, so a long log reads in chunks (Today, Yesterday, 6 Oct 2026…)
              const day = dayBucket(r.timestamp), head = i === 0 || dayBucket(data.rows[i - 1].timestamp) !== day
              return (<Fragment key={r.id}>
              {head && <tr className="bg-muted/50"><th scope="rowgroup" colSpan={6} className="px-3 py-1 text-left text-[12px] font-semibold text-nav-fg">{day}</th></tr>}
              <tr className="border-b border-border align-top last:border-0 hover:bg-muted">
                <td className={cn(td, "whitespace-nowrap text-[12px] text-muted-foreground")}>{fmtWhen(r.timestamp, true)}</td>
                <td className={td}><span className="inline-flex items-center gap-2 whitespace-nowrap"><UserAvatar name={r.user_name || r.username || "?"} className="h-5 w-5 shrink-0" />{r.user_name || r.username}</span></td>
                <td className={td} title={r.action}>{actionText(r.action)}</td>
                <td className={td}>
                  {/* the name when there is one; "Rollout 40" only when the record has none */}
                  {r.resource_type && !r.resource_name && <span className="text-muted-foreground">{actionText(r.resource_type)} </span>}
                  {r.resource_type === "project" && r.resource_id ? <a href={`/projects/${r.resource_id}`} className="font-medium wrap-anywhere hover:underline">{r.resource_name ?? `Rollout #${r.resource_id}`}</a>
                    : r.resource_name ? <span className="wrap-anywhere">{r.resource_name}</span> : r.resource_id ? <span className="text-muted-foreground">{r.resource_id}</span> : null}
                </td>
                <td className={cn(td, "max-w-md wrap-anywhere")}>{r.details}</td>
                <td className={cn(td, "hidden whitespace-nowrap text-[12px] text-muted-foreground lg:table-cell")}>{r.ip_address}</td>
              </tr>
              </Fragment>)
            })}
            {data.rows.length === 0 && <tr><td colSpan={6} className="p-3"><EmptyState>Nothing matches this filter.</EmptyState></td></tr>}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex items-center gap-3 text-[13px] text-muted-foreground">
        {data.total_pages > 1 && <>
          <Pager page={data.page} pages={data.total_pages} href={(n) => { const q = new URLSearchParams(params); q.set("page", String(n)); return `?${q}` }}
            onPage={goto} />
          <span>·</span>
        </>}
        <span>{data.total} entr{data.total === 1 ? "y" : "ies"}</span>
      </div>
    </div>
  )
}
