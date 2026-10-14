import { useCallback, useEffect, useMemo, useState } from "react"
import { EmptyState } from "@/components/EmptyState"
import { StatTile } from "@/components/StatTile"
import { pill, filterSelect } from "@/lib/ui"
import { Link } from "react-router-dom"
import { AlertTriangle, CalendarClock, Check, CheckSquare, Layers } from "lucide-react"
import { Stepper } from "@/components/Stepper"
import { StateChip } from "@/components/StateChip"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { ApiError, editTask, myWork, toggleTask, type MyWorkData, type User, type WorkTask } from "@/lib/api"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { DatePicker } from "@/components/DatePicker"
import { fmtDate, lateBy, stateText, weekday } from "@/lib/format"
import { addDays } from "@/lib/plan"

// My work: what needs doing, in the order it needs doing. Headline numbers,
// the fortnight of what got done, tasks grouped by urgency with a tick that
// finishes them in place, and the rollouts this person is on with their state.
type Group = { key: string; title: string; hint: string; tone?: "bad" | "warn"; tasks: WorkTask[] }

function groupTasks(tasks: WorkTask[], today: string): Group[] {
  const w = addDays(today, 7)
  const g: Record<string, WorkTask[]> = { overdue: [], today: [], week: [], later: [], undated: [] }
  for (const t of tasks) {
    if (!t.due_date) g.undated.push(t)
    else if (t.due_date < today) g.overdue.push(t)
    else if (t.due_date === today) g.today.push(t)
    else if (t.due_date <= w) g.week.push(t)
    else g.later.push(t)
  }
  const groups: Group[] = [
    { key: "overdue", title: "Overdue", hint: "past their date", tone: "bad", tasks: g.overdue },
    { key: "today", title: "Today", hint: fmtDate(today), tone: "warn", tasks: g.today },
    { key: "week", title: "This week", hint: "the next 7 days", tasks: g.week },
    { key: "later", title: "Later", hint: "beyond this week", tasks: g.later },
    { key: "undated", title: "No date", hint: "whenever", tasks: g.undated },
  ]
  return groups.filter((x) => x.tasks.length > 0)
}

// The due date as a button; a click turns it into a date field that saves on change.
function DueButton({ t, late, busy, onChange }: { t: WorkTask; late: number; busy: boolean; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  if (open) return (
    <DatePicker autoOpen value={t.due_date ?? ""} label={`Due date for ${t.title}`} disabled={busy} onClose={() => setOpen(false)}
      onChange={(v) => { setOpen(false); if (v !== (t.due_date ?? "")) onChange(v) }} className="h-7 shrink-0 px-2 text-[12px]" />
  )
  return (
    <button type="button" onClick={() => setOpen(true)} aria-label={`${t.due_date ? `Due ${fmtDate(t.due_date)}` : "No date"}. Change the due date of ${t.title}`}
      className={cn("h-7 shrink-0 whitespace-nowrap rounded-md px-2 text-[12px] hover:bg-muted", late > 0 ? "bg-bad-soft font-medium text-bad hover:bg-bad-soft" : "text-muted-foreground")}>
      {t.due_date ? (late > 0 ? `${late} d late` : fmtDate(t.due_date)) : "Set a date"}
    </button>
  )
}

export default function MyWork({ user }: { user: User }) {
  const [d, setD] = useState<MyWorkData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [project, setProject] = useState<number | null>(null)
  const load = useCallback(() => myWork().then((x) => { setD(x); setError(null) }).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")), [])
  useEffect(() => { document.title = "My work · Odin"; void load() }, [load])
  const groups = useMemo(() => (d ? groupTasks(project ? d.tasks.filter((t) => t.project_id === project) : d.tasks, d.today) : []), [d, project])
  if (error) return <LoadError message={error} />
  if (!d) return <PageSkeleton />
  const c = d.counts
  const peak = Math.max(1, ...d.done_by_day.map((x) => x.count))
  // a tick leaves the list; the toast's Undo brings the task back
  async function tick(t: WorkTask) {
    setBusy(t.id)
    try {
      await toggleTask(t.project_id, t.id)
      toast(`Done: ${t.title}`, { action: { label: "Undo", run: () => void toggleTask(t.project_id, t.id).then(load).catch(() => toast("Could not reopen it", { tone: "bad" })) } })
      await load()
    } catch (e) { toast(e instanceof ApiError ? e.message : "That did not save", { tone: "bad" }) } finally { setBusy(null) }
  }
  // set or move a task's date (the task is the person's own, so it stays assigned to them)
  async function redate(t: WorkTask, due: string) {
    setBusy(t.id)
    try { await editTask(t.project_id, t.id, { title: t.title, assignee_id: user.id, due_date: due || null }); toast(due ? `${t.title}: due ${fmtDate(due)}` : `${t.title}: no date`); await load() }
    catch (e) { toast(e instanceof ApiError && e.status === 403 ? "Only someone who manages this rollout's tasks can move its date." : e instanceof ApiError ? e.message : "That did not save", { tone: "bad" }) } finally { setBusy(null) }
  }
  const tiles: { label: string; value: number; sub: string; icon: typeof Layers; tone?: "bad" | "warn" }[] = [
    { label: "Open tasks", value: c.open, sub: `${c.due_week} due this week`, icon: CheckSquare },
    { label: "Overdue", value: c.overdue, sub: c.overdue ? "need a date or a tick" : "nothing late", icon: AlertTriangle, tone: c.overdue ? "bad" : undefined },
    { label: "Done this week", value: c.done_week, sub: "tasks ticked in 7 days", icon: Check },
    { label: "My rollouts", value: c.rollouts, sub: c.stuck ? `${c.stuck} need attention` : "all on track", icon: Layers, tone: c.stuck ? "warn" : undefined },
  ]
  return (
    <div className="px-5 pb-8 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">My work</h1>
        <p className="text-[13px] text-muted-foreground">{user.name.split(" ")[0]}, here is what is on you · {fmtDate(d.today)}</p>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-4 xl:grid-cols-4">
        {tiles.map((t) => (
          <StatTile key={t.label} label={t.label} value={t.value} sub={t.sub} tone={t.tone || undefined} icon={<t.icon className="h-3.5 w-3.5" aria-hidden />} />
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section className="panel p-4" aria-label="My tasks">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h2 className="text-[14px] font-semibold">Tasks <span className="font-normal text-muted-foreground">{d.tasks.length} open, most urgent first</span></h2>
            {d.projects.length > 1 && (
              <select value={project ?? ""} onChange={(e) => setProject(e.target.value ? Number(e.target.value) : null)} aria-label="Only this rollout" className={cn(filterSelect, "ml-auto")}>
                <option value="">Every rollout</option>
                {d.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            )}
          </div>
          {groups.length === 0 && <EmptyState>Nothing open{project ? " on this rollout" : ""}. Enjoy it.</EmptyState>}
          {groups.map((g) => (
            <div key={g.key} className="mb-3 last:mb-0">
              <h3 className={cn("mb-1 flex items-baseline gap-2 text-[12px] font-semibold", g.tone === "bad" ? "text-bad" : g.tone === "warn" ? "text-warn" : "text-nav-fg")}>{g.title}<span className="font-normal text-muted-foreground">{g.tasks.length} · {g.hint}</span></h3>
              <ul className="divide-y divide-border text-[13px]">
                {g.tasks.map((t) => {
                  const late = t.due_date ? lateBy(t.due_date, d.today) : 0
                  return (
                    <li key={t.id} className="flex items-center gap-3 py-2">
                      <button type="button" disabled={busy === t.id} onClick={() => tick(t)} aria-label={`Complete ${t.title}`}
                        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-input bg-background hover:border-foreground disabled:opacity-50">
                        {busy === t.id && <Check className="h-3 w-3 text-muted-foreground" />}
                      </button>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium" title={t.title}>{t.title}</span>
                        <Link to={`/board?rollout=${t.project_id}`} title={t.project} className="block truncate text-[12px] text-muted-foreground hover:underline">{t.project} · {t.stage || t.project_stage}</Link>
                      </span>
                      <DueButton t={t} late={late} busy={busy === t.id} onChange={(v) => void redate(t, v)} />
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </section>

        <div className="grid grid-cols-1 content-start gap-4">
          <section className="panel p-4" aria-label="Done, the last 14 days">
            <h2 className="mb-2 text-[14px] font-semibold">Done <span className="font-normal text-muted-foreground">the last 14 days</span></h2>
            <ul className="flex h-20 items-end gap-1" aria-label="Tasks done per day">
              {d.done_by_day.map((x) => (
                <li key={x.day} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1 text-[11px] text-muted-foreground" title={`${fmtDate(x.day)}: ${x.count}`}>
                  <span className={cn("block w-full rounded-t-[3px]", x.count ? "bg-nav-fg/60" : "bg-muted")} style={{ height: `${Math.max(x.count ? 8 : 3, (x.count / peak) * 100)}%` }} aria-hidden />
                  <span aria-hidden>{weekday(x.day)[0]}</span>
                  <span className="sr-only">{fmtDate(x.day)}: {x.count}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel p-4" aria-label="My rollouts">
            <h2 className="mb-2 text-[14px] font-semibold">My rollouts <span className="font-normal text-muted-foreground">{d.projects.length} active</span></h2>
            <ul className="divide-y divide-border text-[13px]">
              {d.projects.map((p) => (
                <li key={p.id} className="py-2">
                  <div className="flex items-center gap-2">
                    <Link to={`/board?rollout=${p.id}`} title={`${p.name} · ${p.client}`} className="min-w-0 flex-1 truncate font-medium hover:underline">{p.name} <span className="font-normal text-muted-foreground">{p.client}</span></Link>
                    <span className="shrink-0 text-[12px] text-muted-foreground">{p.role}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-3 pl-4">
                    <span className="w-24 shrink-0"><Stepper compact stages={p.stages} index={p.stage_index} state={p.state} selected={false} /></span>
                    <span className="truncate text-[13px]">{p.stage}</span>
                    <StateChip state={p.state} className="ml-auto" quiet={p.target_end_date ? `target ${fmtDate(p.target_end_date)}` : "no target"}
                      text={stateText({ state: p.state, days_in_stage: p.days_in_stage ?? null, over_by: p.over_by ?? null, target_end_date: p.target_end_date })} />
                  </div>
                </li>
              ))}
              {d.projects.length === 0 && <li className="py-2 text-muted-foreground">You are not on any active rollout.</li>}
            </ul>
            <div className="mt-2 flex gap-2"><Link to="/board?filter=mine" className={pill}>Mine on the flow</Link><Link to="/board?view=calendar" className={pill}><CalendarClock className="h-3.5 w-3.5" /> Calendar</Link></div>
          </section>
        </div>
      </div>
    </div>
  )
}
