import { useEffect, useState } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { ApiError, myWork, type MyWorkData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"

const fmtDate = (iso: string | null) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" }) : "—")
const SCHEDULE = { overdue: { label: "Overdue", cls: "bg-bad-soft text-bad" }, at_risk: { label: "Due soon", cls: "bg-warn-soft text-warn" }, on_track: { label: "On track", cls: "text-muted-foreground" } } as const

export default function MyWork(_props: { user: User }) {
  const [d, setD] = useState<MyWorkData | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { document.title = "My work · Odin"; myWork().then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")) }, [])
  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!d) return <div className="p-5 text-[13px] text-muted-foreground">Loading…</div>
  const overdue = d.projects.filter((p) => p.schedule === "overdue").length
  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">My work</h1>
        <p className="text-[13px] text-muted-foreground">{d.tasks.length} open task{d.tasks.length === 1 ? "" : "s"} · {d.projects.length} active project{d.projects.length === 1 ? "" : "s"}{overdue ? <> · <span className="font-medium text-bad">{overdue} overdue</span></> : null}</p>
      </div>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-border p-4">
          <h3 className="mb-2 text-[12px] font-semibold text-nav-fg">My tasks <span className="font-normal text-muted-foreground">assigned to me, open</span></h3>
          <ul className="divide-y divide-border text-[13px]">
            {d.tasks.map((t) => (
              <li key={t.id} className="flex items-center gap-3 py-1.5">
                <span className="min-w-0 flex-1 truncate font-medium">{t.title}</span>
                <a href={`/board?rollout=${t.project_id}`} className="truncate text-muted-foreground hover:text-foreground hover:underline">{t.project_name}{t.stage ? ` · ${t.stage}` : ""}</a>
                <span className={cn("whitespace-nowrap text-[12px]", t.overdue ? "rounded-md bg-bad-soft px-1.5 py-0.5 font-medium text-bad" : "text-muted-foreground")}>{fmtDate(t.due_date)}</span>
              </li>
            ))}
            {d.tasks.length === 0 && <li className="py-2 text-muted-foreground">No open tasks assigned to you.</li>}
          </ul>
        </section>
        <section className="rounded-lg border border-border p-4">
          <h3 className="mb-2 text-[12px] font-semibold text-nav-fg">My projects <span className="font-normal text-muted-foreground">owned by me, active</span></h3>
          <ul className="divide-y divide-border text-[13px]">
            {d.projects.map((p) => (
              <li key={p.id} className="flex items-center gap-3 py-1.5">
                <a href={`/projects/${p.id}`} className="min-w-0 flex-1 truncate font-medium hover:underline">{p.name} <span className="font-normal text-muted-foreground">{p.client}</span></a>
                <span className="truncate text-[12.5px]">{p.stage}</span>
                {p.schedule && <span className={cn("whitespace-nowrap rounded-md px-1.5 py-0.5 text-[12px] font-medium", SCHEDULE[p.schedule].cls)}>{SCHEDULE[p.schedule].label}</span>}
                <span className="hidden whitespace-nowrap text-[12px] text-muted-foreground sm:inline">{fmtDate(p.target_end_date)}</span>
              </li>
            ))}
            {d.projects.length === 0 && <li className="py-2 text-muted-foreground">You do not own any active projects.</li>}
          </ul>
        </section>
      </div>
    </div>
  )
}
