import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/EmptyState"
import { Segmented } from "@/components/Segmented"
import { UserAvatar } from "@/components/UserAvatar"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { workload as fetchWorkload, type User, type WorkloadCell } from "@/lib/api"
import { useLoad } from "@/lib/useLoad"
import { cn } from "@/lib/utils"
import { cellTitle, hrs, LEVEL_BAR, LEVEL_TEXT, levelWord, weekLabel } from "@/lib/workload"

// People › Workload: the next four weeks per person, hours against capacity.
// A week is amber from the workspace's "heavy" share and red over capacity; the
// word is printed beside the colour. A row opens the person's tasks.
function Cell({ c, capacity, to }: { c: WorkloadCell; capacity: number; to: string }) {
  const word = levelWord(c.level)
  return (
    <Link to={to} title={cellTitle(c, capacity)} aria-label={`${weekLabel(c.week, 1)}: ${cellTitle(c, capacity)}${word ? `. ${word}` : ""}`}
      className="block rounded-lg px-2 py-1.5 outline-none hover:bg-muted/50 focus-visible:ring-[3px] focus-visible:ring-ring/50">
      <span className="flex items-baseline justify-between gap-2 text-[13px]">
        <span className="font-medium tabular-nums">{hrs(c.hours)}</span>
        <span className={cn("text-[12px] tabular-nums text-muted-foreground", LEVEL_TEXT[c.level] && "font-medium", LEVEL_TEXT[c.level])}>{word ? `${word} · ${c.pct} %` : `${c.pct} %`}</span>
      </span>
      <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
        <span className={cn("block h-full rounded-full", LEVEL_BAR[c.level])} style={{ width: `${Math.min(100, c.pct)}%` }} />
      </span>
    </Link>
  )
}

export default function Workload(_props: { user: User }) {
  const { data: d, error } = useLoad("workload", fetchWorkload)
  const [q, setQ] = useState("")
  const [show, setShow] = useState<"all" | "heavy">("all")
  useEffect(() => { document.title = "Workload · Odin" }, [])
  if (error) return <LoadError message={error.message} />
  if (!d) return <PageSkeleton />
  const list = d.people.filter((p) => (!q || p.name.toLowerCase().includes(q.toLowerCase())) && (show === "all" || p.weeks.some((w) => w.level !== "ok")))
  return (
    <div className="px-5 pb-8 pt-4">
      <PageHeader title="Workload"
        lede={`Hours per week against capacity (${d.capacity_default} h by default): open tasks due that week, plus an allowance for each rollout a person manages. Late work counts in this week.`}
        actions={<Link to="/people" className={buttonVariants({ variant: "outline", size: "sm" })}>People</Link>} />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Segmented label="Show" value={show} onChange={setShow} options={[{ value: "all", label: "Everyone" }, { value: "heavy", label: `Heavy or over${d.over + d.heavy ? ` (${d.over + d.heavy})` : ""}` }]} />
        <p className="text-[13px] text-muted-foreground">{d.over ? `${d.over} over capacity` : "Nobody over capacity"}{d.heavy > 0 && ` · ${d.heavy} heavy`}</p>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a person" aria-label="Find a person" className="ml-auto w-52" />
      </div>
      <section className="panel mt-3 overflow-x-auto" aria-label="Workload by person">
        <table className="w-full min-w-[720px] text-left">
          <thead>
            <tr className="text-[12px] text-muted-foreground">
              <th scope="col" className="px-4 py-2 font-medium">Person</th>
              {d.weeks.map((w, i) => <th key={w} scope="col" className="px-2 py-2 font-medium">{weekLabel(w, i)}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {list.map((p) => (
              <tr key={p.id}>
                <th scope="row" className="px-4 py-2 text-left font-normal">
                  <Link to={`/people/${p.id}`} className="flex items-center gap-3 outline-none focus-visible:underline">
                    <UserAvatar name={p.name} url={p.avatar_url} className="h-8 w-8" />
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium hover:underline">{p.name}</span>
                      <span className="block truncate text-[12px] text-muted-foreground">{p.role} · {hrs(p.capacity)} a week{p.custom_capacity ? " (own)" : ""}{p.rollouts > 0 && ` · manages ${p.rollouts}`}</span>
                    </span>
                  </Link>
                </th>
                {p.weeks.map((c) => <td key={c.week} className="px-1 py-1 align-middle"><Cell c={c} capacity={p.capacity} to={`/people/${p.id}`} /></td>)}
              </tr>
            ))}
          </tbody>
        </table>
        {list.length === 0 && <EmptyState className="m-3">{q ? `Nobody matches “${q}”.` : show === "heavy" ? "Nobody is heavy or over capacity in the next four weeks." : "Nobody to plan yet."}</EmptyState>}
      </section>
    </div>
  )
}
