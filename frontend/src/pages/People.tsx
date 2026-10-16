import { useEffect, useState } from "react"
import { EmptyState } from "@/components/EmptyState"
import { Link } from "react-router-dom"
import { Input } from "@/components/ui/input"
import { UserAvatar } from "@/components/UserAvatar"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { Ago } from "@/components/Ago"
import { ApiError, people, type PeopleData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"

// People: a card for everyone internal who is on active work — how much,
// how much of it is late, and what they finished lately. A card opens the
// person's page.
export default function People(_props: { user: User }) {
  const [d, setD] = useState<PeopleData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState("")
  useEffect(() => { document.title = "People · Odin"; people().then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")) }, [])
  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  const list = d.people.filter((p) => !q || p.name.toLowerCase().includes(q.toLowerCase()) || p.role.toLowerCase().includes(q.toLowerCase()))
  return (
    <div className="px-5 pb-8 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">People</h1>
        <p className="text-[13px] text-muted-foreground">{d.people.length} on active rollouts</p>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a person" aria-label="Find a person" className="ml-auto w-52" />
      </div>
      <ul className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4" aria-label="People">
        {list.map((p) => (
          <li key={p.id}>
            <Link to={`/people/${p.id}`} className="panel block p-4 outline-none transition-colors hover:bg-muted/40 focus-visible:ring-[3px] focus-visible:ring-ring/50">
              <div className="flex items-center gap-3">
                <UserAvatar name={p.name} url={p.avatar_url} className="h-11 w-11" textClass="text-[14px]" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[14px] font-semibold" title={p.name}>{p.name}{p.id === d.me && <span className="ml-2 font-normal text-muted-foreground">you</span>}</div>
                  <div className="truncate text-[12px] text-muted-foreground">{p.role}{p.last_seen_at && <> · seen <Ago iso={p.last_seen_at} /></>}</div>
                </div>
              </div>
              <dl className="mt-3 grid grid-cols-4 gap-2 text-center">
                {[["Rollouts", p.projects, ""], ["Open", p.open, ""], ["Late", p.late, p.late ? "text-bad" : ""], ["Done 30 d", p.done_30d, ""]].map(([l, v, cls]) => (
                  <div key={String(l)} className="rounded-xl bg-muted/50 py-2">
                    <dd className={cn("text-[17px] font-semibold leading-none", String(cls))}>{v}</dd>
                    <dt className="mt-1 text-[11px] text-muted-foreground">{l}</dt>
                  </div>
                ))}
              </dl>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted" role="img" aria-label={`${p.open - p.late} open on time, ${p.late} late`}>
                <div className="flex h-full"><span className="bg-nav-fg/60" style={{ width: `${p.open ? ((p.open - p.late) / p.open) * 100 : 0}%` }} /><span className="bg-bad-line" style={{ width: `${p.open ? (p.late / p.open) * 100 : 0}%` }} /></div>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground" aria-hidden>{p.open ? <>{p.open - p.late} open on time{p.late > 0 && <> · <span className="text-bad">{p.late} late</span></>}</> : "Nothing open"}</p>
            </Link>
          </li>
        ))}
        {list.length === 0 && <EmptyState as="li" className="col-span-full">{q ? `Nobody matches “${q}”.` : "Nobody is on active work yet."}</EmptyState>}
      </ul>
    </div>
  )
}
