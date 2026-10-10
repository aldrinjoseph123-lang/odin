import { useEffect, useState, type FormEvent } from "react"
import { StatTile } from "@/components/StatTile"
import { pill } from "@/lib/ui"
import { Link, useParams } from "react-router-dom"
import { ArrowRight, CheckSquare, ChevronLeft, MessageSquare, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { UserAvatar } from "@/components/UserAvatar"
import { Stepper } from "@/components/Stepper"
import { Ago } from "@/components/Ago"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { ApiError, notifyPerson, person, type PersonData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { ActivityPanel } from "@/components/ActivityPanel"
import { STATE } from "@/lib/state"
import { fmtDate, lateBy } from "@/lib/format"

// One person: what they carry, how it is going, what they did, and a way to
// reach them that lands in their bell and their inbox.
const KIND = { move: { icon: ArrowRight, verb: "moved" }, note: { icon: MessageSquare, verb: "noted on" }, task: { icon: CheckSquare, verb: "finished on" } }

export default function Person(_props: { user: User }) {
  const { id } = useParams()
  const [d, setD] = useState<PersonData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState("")
  const [about, setAbout] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  useEffect(() => {
    person(Number(id)).then((x) => { setD(x); document.title = `${x.user.name} · People · Odin` })
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? "No such person." : e instanceof ApiError ? e.message : "Could not load"))
  }, [id])
  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  const k = d.kpis
  const peak = Math.max(1, ...d.contribution.weeks.map((w) => w.done))
  async function send(e: FormEvent) {
    e.preventDefault()
    if (!message.trim()) return
    setBusy(true); setNotice(null)
    try { await notifyPerson(d!.user.id, message.trim(), about); setOpen(false); setMessage(""); setNotice(`Sent to ${d!.user.name.split(" ")[0]}: they have it in their bell${d!.user.email ? " and their inbox" : ""}.`) }
    catch (err) { setNotice(err instanceof ApiError ? err.message : "That did not send") } finally { setBusy(false) }
  }
  const tiles: { label: string; value: string; sub: string; tone?: "bad" | "warn" }[] = [
    { label: "Rollouts", value: String(k.rollouts), sub: k.stuck ? `${k.stuck} need attention` : "all on track", tone: k.stuck ? "warn" : undefined },
    { label: "Open tasks", value: String(k.open), sub: `${d.upcoming.length} due in 14 days` },
    { label: "Late", value: String(k.late), sub: k.late ? "past their date" : "nothing late", tone: k.late ? "bad" : undefined },
    { label: "Done, 30 days", value: String(k.done_30d), sub: k.on_time_pct == null ? "no dated tasks yet" : `${k.on_time_pct}% on time` },
  ]
  return (
    <div className="px-5 pb-8 pt-2">
      <Link to="/people" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"><ChevronLeft className="h-3.5 w-3.5" /> People</Link>
      <div className="mt-2 flex flex-wrap items-center gap-4">
        <UserAvatar name={d.user.name} url={d.user.avatar_url} className="h-14 w-14" textClass="text-[17px]" />
        <div className="min-w-0 flex-1">
          <h1 className="text-[17px] font-semibold tracking-tight">{d.user.name}</h1>
          <p className="text-[13px] text-muted-foreground">{d.user.role}{d.user.email && ` · ${d.user.email}`}{(d.activity?.last_seen_at ?? d.user.last_login_at) && <> · seen <Ago iso={(d.activity?.last_seen_at ?? d.user.last_login_at)!} /></>}</p>
        </div>
        {d.can_notify && <Button size="sm" className="rounded-full" onClick={() => setOpen(true)}><Send className="h-3.5 w-3.5" /> Notify {d.user.name.split(" ")[0]}</Button>}
      </div>
      {notice && <p className="mt-2 text-[13px] text-muted-foreground" role="status">{notice}</p>}

      <div className="mt-4 grid grid-cols-2 gap-4 xl:grid-cols-4">
        {tiles.map((t) => (
          <StatTile key={t.label} label={t.label} value={t.value} sub={t.sub} tone={t.tone || undefined} />
        ))}
      </div>

      {d.activity && <div className="mt-4"><ActivityPanel a={d.activity} /></div>}

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <section className="panel p-4" aria-label="Contribution">
          <h2 className="mb-2 text-[14px] font-semibold">Contribution <span className="font-normal text-muted-foreground">tasks finished per week, 8 weeks</span></h2>
          <ul className="flex h-24 items-end gap-2" aria-label="Tasks finished per week">
            {d.contribution.weeks.map((w) => (
              <li key={w.week} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1 text-[11px] text-muted-foreground" title={`week of ${fmtDate(w.week)}: ${w.done}`}>
                {w.done > 0 && w.done === peak && <span className="text-foreground">{w.done}</span>}
                <span className={cn("block w-full rounded-t-[3px]", w.done ? "bg-nav-fg/60" : "bg-muted")} style={{ height: `${Math.max(w.done ? 8 : 3, (w.done / peak) * 100)}%` }} aria-hidden />
                <span aria-hidden>{w.week.slice(8, 10)}/{w.week.slice(5, 7)}</span>
                <span className="sr-only">week of {fmtDate(w.week)}: {w.done}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[13px] text-muted-foreground">In the last 30 days: <span className="font-medium text-foreground">{k.done_30d}</span> task{k.done_30d === 1 ? "" : "s"} finished, <span className="font-medium text-foreground">{d.contribution.notes_30d}</span> note{d.contribution.notes_30d === 1 ? "" : "s"}, <span className="font-medium text-foreground">{d.contribution.moves_30d}</span> stage move{d.contribution.moves_30d === 1 ? "" : "s"}.</p>
        </section>

        <section className="panel p-4" aria-label="Active rollouts">
          <h2 className="mb-2 text-[14px] font-semibold">Active rollouts <span className="font-normal text-muted-foreground">{d.projects.length}</span></h2>
          <ul className="divide-y divide-border text-[13px]">
            {d.projects.map((p) => (
              <li key={p.id} className="py-2">
                <div className="flex items-center gap-2">
                  <span className={cn("h-2 w-2 shrink-0 rounded-full", p.state === "on_track" ? "bg-transparent" : STATE[p.state].dot)} aria-hidden />
                  <Link to={`/board?rollout=${p.id}`} title={`${p.name} · ${p.client}`} className="min-w-0 flex-1 truncate font-medium hover:underline">{p.name} <span className="font-normal text-muted-foreground">{p.client}</span></Link>
                  <span className="rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground">{p.role}</span>
                </div>
                <div className="mt-1 flex items-center gap-3 pl-4">
                  <span className="w-20 shrink-0"><Stepper stages={Array.from({ length: p.stages }, (_, i) => String(i))} index={p.stage_index} state={p.state} selected={false} /></span>
                  <span className="truncate text-[13px]" title={p.stage}>{p.stage}</span>
                  <span className={cn("ml-auto whitespace-nowrap text-[12px]", p.state === "on_track" ? "text-muted-foreground" : STATE[p.state].chip.split(" ")[1])}>{STATE[p.state].label}</span>
                </div>
              </li>
            ))}
            {d.projects.length === 0 && <li className="py-2 text-muted-foreground">Not on any active rollout.</li>}
          </ul>
        </section>

        <section className="panel p-4" aria-label="Pending tasks">
          <h2 className="mb-2 text-[14px] font-semibold">Pending <span className="font-normal text-muted-foreground">{d.pending.length} open, soonest first</span></h2>
          <ul className="divide-y divide-border text-[13px]">
            {d.pending.slice(0, 12).map((t) => {
              const late = t.due_date ? lateBy(t.due_date, d.today) : 0
              return (
                <li key={t.id} className="flex items-center gap-3 py-2">
                  <span className="min-w-0 flex-1"><span className="block truncate font-medium">{t.title}</span><Link to={`/board?rollout=${t.project_id}`} className="block truncate text-[12px] text-muted-foreground hover:underline">{t.project}</Link></span>
                  <span className={cn("shrink-0 text-[12px]", late > 0 ? "font-medium text-bad" : "text-muted-foreground")}>{t.due_date ? (late > 0 ? `${late} d late` : fmtDate(t.due_date)) : "no date"}</span>
                </li>
              )
            })}
            {d.pending.length === 0 && <li className="py-2 text-muted-foreground">Nothing pending.</li>}
            {d.pending.length > 12 && <li className="py-2 text-[12px] text-muted-foreground">{d.pending.length - 12} more</li>}
          </ul>
        </section>

        <section className="panel p-4" aria-label="Upcoming tasks">
          <h2 className="mb-2 text-[14px] font-semibold">Upcoming <span className="font-normal text-muted-foreground">due in the next 14 days</span></h2>
          <ul className="divide-y divide-border text-[13px]">
            {d.upcoming.map((t) => (
              <li key={t.id} className="flex items-center gap-3 py-2">
                <span className="w-14 shrink-0 rounded-lg bg-muted px-1 py-1 text-center text-[11px] leading-tight text-muted-foreground"><span className="block text-[13px] font-semibold text-foreground">{t.due_date!.slice(8, 10)}</span>{fmtDate(t.due_date).replace(/\d+ /, "")}</span>
                <span className="min-w-0 flex-1"><span className="block truncate font-medium">{t.title}</span><Link to={`/board?rollout=${t.project_id}`} className="block truncate text-[12px] text-muted-foreground hover:underline">{t.project}</Link></span>
              </li>
            ))}
            {d.upcoming.length === 0 && <li className="py-2 text-muted-foreground">Nothing falls due in the next two weeks.</li>}
          </ul>
        </section>

        <section className="panel p-4 xl:col-span-2" aria-label="Recent activity">
          <h2 className="mb-2 text-[14px] font-semibold">Recently <span className="font-normal text-muted-foreground">what {d.user.name.split(" ")[0]} did</span></h2>
          <ul className="grid grid-cols-1 gap-3 text-[13px] md:grid-cols-2">
            {d.recent.map((a, i) => {
              const K = KIND[a.kind]
              return (
                <li key={i} className="flex gap-3">
                  <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"><K.icon className="h-3.5 w-3.5" aria-hidden /></span>
                  <span className="min-w-0">
                    <span className="block leading-snug">{K.verb} <Link to={`/board?rollout=${a.project_id}`} className="font-medium hover:underline">{a.project}</Link></span>
                    <span className="block truncate text-muted-foreground" title={a.text}>{a.text}</span>
                    <span className="block text-[11px] text-muted-foreground"><Ago iso={a.at} /></span>
                  </span>
                </li>
              )
            })}
            {d.recent.length === 0 && <li className="text-muted-foreground">Nothing yet.</li>}
          </ul>
        </section>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={send}>
            <DialogHeader>
              <DialogTitle>Notify {d.user.name}</DialogTitle>
              <DialogDescription>A note that lands in their bell{d.user.email ? " and their inbox" : ""}, with a link back to the rollout you pick.</DialogDescription>
            </DialogHeader>
            <label htmlFor="notify-message" className="mt-3 block text-[13px] font-medium">Message</label>
            <textarea id="notify-message" value={message} onChange={(e) => setMessage(e.target.value)} rows={4} maxLength={1000} required autoFocus
              className="mt-1 w-full rounded-md border border-input bg-background p-2 text-[13px]" placeholder="Could you look at the pilot sign-off today?" />
            {d.projects.length > 0 && (
              <>
                <label htmlFor="notify-about" className="mt-3 block text-[13px] font-medium">About <span className="font-normal text-muted-foreground">(optional)</span></label>
                <select id="notify-about" value={about ?? ""} onChange={(e) => setAbout(e.target.value ? Number(e.target.value) : null)} className="mt-1 h-8 w-full rounded-md border border-input bg-background px-2 text-[13px]">
                  <option value="">No particular rollout</option>
                  {d.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" className="rounded-full" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
              <Button type="submit" size="sm" className="rounded-full" loading={busy} disabled={!message.trim()}><Send className="h-3.5 w-3.5" /> Send</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
      <Link to="/people" className={cn(pill, "mt-4 inline-flex")}>All people</Link>
    </div>
  )
}
