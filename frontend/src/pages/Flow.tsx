import { useCallback, useEffect, useMemo, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react"
import { ArrowRight, BarChart3, CalendarDays, Check, ChevronLeft, ChevronRight, LayoutList, Clock, ExternalLink, FileSignature, Plus, Trash2, UserRound, X } from "lucide-react"
import { Link, useSearchParams } from "react-router-dom"
import { UserAvatar } from "@/components/UserAvatar"
import { TeamStack } from "@/components/TeamStack"
import { Ago } from "@/components/Ago"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { ApiError, addTask, changeStage, postForm, decideApproval, deleteTask, flow, flowDetail, toggleTask, type ApprovalStatus, type FlowData, type FlowDetail, type FlowRow, type FlowTask, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { STATE } from "@/lib/state"
import { days, fitStages, fmtDate, groupRows, signoffText, stateText, lateBy, nextUp, stageColumns, type FlowGroupBy } from "@/lib/format"
import { Stepper } from "@/components/Stepper"
import { Calendar } from "@/pages/Calendar"
import { Kibana } from "@/pages/Kibana"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"


// Customer approval of the current stage: amber while open, green/red once decided.
const APPROVAL: Record<ApprovalStatus, { label: string; chip: string } | null> = {
  pending:    { label: "Awaiting approval", chip: "bg-warn-soft text-warn" },
  approved:   { label: "Approved",          chip: "bg-ok-soft text-ok" },
  declined:   { label: "Declined",          chip: "bg-bad-soft text-bad" },
  superseded: null,
}
function ApprovalChip({ status, className }: { status: ApprovalStatus | null; className?: string }) {
  const a = status && APPROVAL[status]
  return a ? <span className={cn("whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-medium", a.chip, className)}>{a.label}</span> : null
}



// A task's due date, in the bad state once it has passed.
function DueDate({ due, today, className }: { due: string; today: string; className?: string }) {
  const late = lateBy(due, today)
  return <span className={cn("block text-[11px]", late > 0 ? "font-medium text-bad" : "text-muted-foreground", className)}>
    {late > 0 ? `${late} d late · due ${fmtDate(due)}` : `due ${fmtDate(due)}`}</span>
}

// ---- tasks under a stage box: tick, add, remove — no page change --------------
function StageTasks({ d, stage, done, reload, onError }: { d: FlowDetail; stage: string; done: boolean; reload: () => Promise<void>; onError: (m: string | null) => void }) {
  const tasks = d.tasks.filter((t) => t.stage === stage)
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState("")
  const [assignee, setAssignee] = useState<string>("")
  const [busy, setBusy] = useState(false)
  const canTick = (t: FlowTask) => d.can_edit || t.assignee_id === d.me
  async function run(fn: () => Promise<unknown>) {
    setBusy(true); onError(null)
    try { await fn(); await reload() } catch (e) { onError(e instanceof ApiError ? e.message : "That did not save") } finally { setBusy(false) }
  }
  async function submit() {
    const t = title.trim()
    if (!t) return
    await run(() => addTask(d.id, { title: t, stage, assignee_id: assignee ? Number(assignee) : null }))
    setTitle("")
  }
  return (
    <div className="mt-2 text-[12.5px]">
      {tasks.length > 0 && (
        <ul className="divide-y divide-border border-t border-border">
          {tasks.map((t) => (
            <li key={t.id} className={cn("group flex items-center gap-1.5 py-1.5", t.done && "text-muted-foreground")}>
              <button type="button" disabled={!canTick(t) || busy} onClick={() => run(() => toggleTask(d.id, t.id))}
                aria-label={t.done ? `Reopen ${t.title}` : `Complete ${t.title}`}
                className={cn("relative flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border before:absolute before:-inset-[5px] before:content-['']", t.done ? "border-ok-line bg-ok-line text-background" : "border-input bg-background", canTick(t) ? "hover:border-foreground" : "cursor-default opacity-60")}>
                {t.done && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
              </button>
              <span className="min-w-0 flex-1">
                <span className={cn("break-words line-clamp-2", t.done && "line-through")}>{t.title}</span>
                {t.due_date && !t.done && <DueDate due={t.due_date} today={d.today} />}
              </span>
              {t.assignee && <UserAvatar name={t.assignee} url={t.assignee_avatar_url} className="h-5 w-5" textClass="text-[10px]" />}
              {d.can_edit && (
                <button type="button" disabled={busy} onClick={() => run(() => deleteTask(d.id, t.id))} aria-label={`Delete ${t.title}`}
                  className="hidden shrink-0 text-muted-foreground hover:text-bad group-hover:block group-focus-within:block [@media(hover:none)]:block"><Trash2 className="h-3.5 w-3.5" /></button>
              )}
            </li>
          ))}
        </ul>
      )}
      {/* a finished stage keeps its tasks but takes no new ones */}
      {d.can_edit && !done && (adding ? (
        <form className="mt-1.5 grid grid-cols-1 gap-1" onSubmit={(e) => { e.preventDefault(); void submit() }}>
          <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task" aria-label={`New task in ${stage}`} maxLength={200} className="h-7 px-2 text-[12.5px]"
            onKeyDown={(e) => { if (e.key === "Escape") { setAdding(false); setTitle("") } }} />
          <div className="flex items-center gap-1">
            <select value={assignee} onChange={(e) => setAssignee(e.target.value)} aria-label="Assign to" className="h-7 min-w-0 flex-1 rounded-md border border-input bg-background px-1.5 text-[12px]">
              <option value="">Unassigned</option>
              {d.assignable.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
            <Button type="submit" size="sm" className="h-7 px-2" disabled={busy || !title.trim()} aria-label="Add task"><Plus className="h-3.5 w-3.5" /></Button>
            <Button type="button" size="sm" variant="ghost" className="h-7 px-1.5" onClick={() => { setAdding(false); setTitle("") }} aria-label="Cancel"><X className="h-3.5 w-3.5" /></Button>
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => setAdding(true)} aria-label={`Add a task to ${stage}`} className="mt-1 flex items-center gap-1 text-[12px] text-muted-foreground hover:text-primary-text">
          <Plus className="h-3 w-3" /> Task
        </button>
      ))}
    </div>
  )
}

// ---- top pane: every active rollout, stuck first -------------------------------
type Filter = "all" | "attention" | "customer" | "mine"
// Pills share one size: 32 px, 40 px under a finger.
const pill = "flex h-8 shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-3 text-[12.5px] font-medium outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 pointer-coarse:h-10"
const pillOn = "border-foreground bg-foreground text-background"
const pillOff = "border-border text-nav-fg hover:bg-muted"

// What happens next on this rollout, in one quiet line.
function NextLine({ r, today }: { r: FlowRow; today: string }) {
  const t = r.next_task
  const late = t?.due_date ? lateBy(t.due_date, today) : 0
  return (
    <span className="flex min-w-0 items-center gap-1.5 text-[12px] text-muted-foreground">
      {t ? (
        <>
          <span className="min-w-0 truncate"><span className="text-nav-fg">Next:</span> {t.title}</span>
          {t.assignee && <span className="shrink-0">· {t.assignee}</span>}
          {t.due_date && <span className={cn("shrink-0", late > 0 && "font-medium text-bad")}>· {late > 0 ? `${late} d late` : `due ${fmtDate(t.due_date)}`}</span>}
        </>
      ) : <span className="truncate">No open task</span>}
      {/* the task name comes first: the tally only where there is room for both */}
      {r.total_tasks > 0 && <span className="hidden shrink-0 tabular-nums lg:inline">· {r.total_tasks - r.open_tasks} of {r.total_tasks} done</span>}
      {r.stale && <span className="shrink-0">· idle {Math.round(r.idle_days ?? 0)} d</span>}
    </span>
  )
}

function RolloutRow({ r, selected, tabStop, onSelect, columns, today, me }: {
  r: FlowRow; selected: boolean; tabStop: boolean; onSelect: (id: number) => void; columns: string[]; today: string; me: number
}) {
  const chip = <span className={cn("whitespace-nowrap rounded-md px-2 py-0.5 text-[12px] font-medium", STATE[r.state].chip, r.state === "on_track" && "bg-transparent px-0 font-normal text-muted-foreground")}>
    <span className="sr-only">{STATE[r.state].label}: </span>{stateText(r)}</span>
  // The viewer is on most of their own rows: show who else is.
  const others = r.team.filter((p) => p.id !== me)
  const t = r.next_task
  return (
    <li>
      <button type="button" data-row onClick={() => onSelect(r.id)} aria-current={selected || undefined} tabIndex={tabStop ? 0 : -1}
        aria-label={`${r.name}, ${r.client}. ${r.stage}, stage ${r.stage_index + 1} of ${r.stages.length}. ${r.state === "on_track" ? `On track, ${stateText(r)} in stage` : stateText(r)}${r.approval === "pending" ? ". Waiting on the customer's approval" : r.approval === "declined" ? ". Customer declined" : r.approval === "approved" ? ". Approved" : ""}. ${t ? `Next: ${t.title}${t.assignee ? `, ${t.assignee}` : ""}` : "No open task"}${r.stale ? `. Idle ${Math.round(r.idle_days ?? 0)} days` : ""}`}
        className={cn("grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2 text-left outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50",
          "md:grid-cols-[minmax(240px,1.6fr)_minmax(120px,1fr)_210px_76px] md:gap-x-4 md:gap-y-0.5",
          selected ? "border-primary bg-accent" : "border-transparent hover:bg-muted focus-visible:bg-muted")}>
        <span className="flex min-w-0 items-center gap-2 md:col-start-1 md:row-start-1">
          <span className={cn("h-2 w-2 shrink-0 rounded-full", r.state === "on_track" ? "bg-transparent" : STATE[r.state].dot)} aria-hidden />
          <span className="truncate text-[13.5px] font-medium">{r.name}</span>
          <span className="hidden truncate text-[12px] text-muted-foreground sm:inline">{r.client}</span>
        </span>
        <span className="justify-self-end md:hidden">{chip}</span>
        <span className="hidden md:col-start-2 md:row-span-2 md:row-start-1 md:block">
          <Stepper stages={r.stages} index={r.stage_index} state={r.state} selected={selected} columns={columns} />
        </span>
        {/* phones: the stage and a progress bar in place of the dots */}
        <span className="col-span-2 flex min-w-0 items-center gap-2 pl-4 md:col-span-1 md:col-start-3 md:row-span-2 md:row-start-1 md:grid md:gap-0.5 md:pl-0">
          <span className="truncate text-[12.5px] font-medium">{r.stage}</span>
          <span className="h-1 w-12 shrink-0 overflow-hidden rounded-full bg-muted md:hidden" aria-hidden>
            <span className="block h-full bg-ok-line" style={{ width: `${((r.stage_index + 1) / Math.max(1, r.stages.length)) * 100}%` }} />
          </span>
          <span className="flex min-w-0 flex-wrap items-center gap-1.5 gap-y-1">
            <span className="hidden md:inline">{chip}</span>
            <ApprovalChip status={r.approval} />
          </span>
        </span>
        <TeamStack people={others} className="hidden md:col-start-4 md:row-span-2 md:row-start-1 md:flex" />
        <span className="col-span-2 min-w-0 pl-4 md:col-span-1 md:col-start-1 md:row-start-2"><NextLine r={r} today={today} /></span>
      </button>
    </li>
  )
}

function RolloutList({ data, me, partner, selectedId, onSelect, filter, setFilter, stage, setStage, group, setGroup, tools }: {
  data: FlowData; me: number; partner?: boolean; selectedId: number | null; onSelect: (id: number) => void; tools?: ReactNode
  filter: Filter; setFilter: (f: Filter) => void
  stage: string | null; setStage: (s: string | null) => void
  group: FlowGroupBy | null; setGroup: (g: FlowGroupBy | null) => void
}) {
  const match = useCallback((r: FlowRow, f: Filter) =>
    f === "attention" ? r.state !== "on_track" : f === "customer" ? r.approval === "pending" : f === "mine" ? r.mine : true, [])
  const rows = useMemo(() => data.rows.filter((r) => match(r, filter) && (!stage || r.stage === stage)), [data.rows, filter, stage, match])
  // Every row's stages in one column order, so a stage lines up down the list.
  const columns = useMemo(() => stageColumns(data.rows.map((r) => r.stages)), [data.rows])
  const inStage = useMemo(() => {
    const n = new Map<string, number>()
    for (const r of data.rows) if (match(r, filter)) n.set(r.stage, (n.get(r.stage) ?? 0) + 1)
    return n
  }, [data.rows, filter, match])
  const stuck = data.counts.overdue + data.counts.over_sla + data.counts.due_soon
  const count = (f: Filter) => data.rows.filter((r) => match(r, f)).length
  const chips = ([
    { key: "all", label: "All", n: data.rows.length },
    { key: "attention", label: "Needs attention", n: stuck },
    { key: "customer", label: "Waiting on customer", n: count("customer") },
    { key: "mine", label: "Mine", n: count("mine") },
  ] as { key: Filter; label: string; n: number }[])
    // a filter that changes nothing is noise: "Mine" for someone on every rollout, "Waiting" with none waiting
    .filter((c) => c.key === filter || c.key === "all" || (c.n > 0 && c.n < data.rows.length) || (c.key === "attention" && c.n > 0))
  // On track needs no attention: folded into one line while anything else does.
  const calm = group ? [] : rows.filter((r) => r.state === "on_track")
  const [showCalm, setShowCalm] = useState(false)
  const fold = calm.length > 0 && calm.length < rows.length && !showCalm && !calm.some((r) => r.id === selectedId)
  const shown = fold ? rows.filter((r) => r.state !== "on_track") : rows
  // One tab stop for the whole list; ↑/↓ or j/k move between rows, Enter opens.
  function onKeys(e: KeyboardEvent<HTMLUListElement>) {
    const step = e.key === "ArrowDown" || e.key === "j" ? 1 : e.key === "ArrowUp" || e.key === "k" ? -1 : 0
    const buttons = [...e.currentTarget.querySelectorAll<HTMLButtonElement>("button[data-row]")]
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement)
    const to = e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : step && at >= 0 ? at + step : -1
    if (to < 0 || to >= buttons.length) return
    e.preventDefault()
    buttons[to].focus()
  }
  const tabStop = shown.some((r) => r.id === selectedId) ? selectedId : shown[0]?.id
  const row = (r: FlowRow) => <RolloutRow key={r.id} r={r} selected={r.id === selectedId} tabStop={r.id === tabStop} onSelect={onSelect} columns={columns} today={data.today} me={me} />
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 pb-2 pt-4">
        <h1 className="text-[17px] font-semibold tracking-tight">Active rollouts</h1>
        {tools}
        <p className="text-[13px] text-muted-foreground">
          {data.rows.length} active
          {data.counts.overdue ? <> · <span className="font-medium text-bad">{data.counts.overdue} overdue</span></> : null}
          {data.counts.over_sla ? <> · <span className="font-medium text-warn">{data.counts.over_sla} over SLA</span></> : null}
          {data.counts.due_soon ? <> · <span className="font-medium text-warn">{data.counts.due_soon} due soon</span></> : null}
        </p>
        <div className="flex flex-wrap items-center gap-1.5 md:ml-auto">
          {chips.map((c) => (
            <button key={c.key} type="button" onClick={() => setFilter(c.key)} aria-pressed={filter === c.key} aria-label={`${c.label}, ${c.n}`}
              className={cn(pill, filter === c.key ? pillOn : pillOff)}>
              {c.label}{c.n ? <span className={filter === c.key ? "text-background/70" : "text-muted-foreground"}>{c.n}</span> : null}
            </button>
          ))}
          <label className="flex items-center gap-1.5 pl-1 text-[12.5px] text-muted-foreground">
            Group
            <select aria-label="Group rollouts by" value={group ?? ""} onChange={(e) => setGroup((e.target.value || null) as FlowGroupBy | null)}
              className="h-8 rounded-md border border-input bg-background px-2 text-[12.5px] text-foreground pointer-coarse:h-10">
              <option value="">None</option><option value="stage">Stage</option><option value="client">Client</option><option value="owner">Owner</option>
            </select>
          </label>
        </div>
      </div>
      {/* how many sit in each stage, named; a tap shows only that stage */}
      <nav aria-label="Rollouts in each stage" className="flex gap-1.5 overflow-x-auto px-5 pb-2 [scrollbar-width:none]">
        {columns.filter((c) => inStage.get(c) || stage === c).map((c) => {
          const on = stage === c
          return (
            <button key={c} type="button" onClick={() => setStage(on ? null : c)} aria-pressed={on}
              aria-label={`${c}: ${inStage.get(c) ?? 0}. ${on ? "Show every stage" : "Show only this stage"}`}
              className={cn(pill, "font-normal", on ? pillOn : pillOff)}>
              {c} <span className={cn("font-medium tabular-nums", on ? "text-background" : "text-foreground")}>{inStage.get(c) ?? 0}</span>
              {on && <X className="h-3 w-3" aria-hidden />}
            </button>
          )
        })}
      </nav>
      <ScrollArea className="min-h-0 flex-1">
        <div className="sticky top-0 z-10 mx-3 hidden grid-cols-[minmax(240px,1.6fr)_minmax(120px,1fr)_210px_76px] gap-4 border-y border-transparent bg-card px-3 py-1.5 text-[11.5px] text-muted-foreground md:grid">
          <span>Rollout · next step</span><span>Progress</span><span>Stage · status</span><span>Team</span>
        </div>
        <ul className="grid grid-cols-1 gap-0.5 px-3 pb-3" onKeyDown={onKeys} aria-label="Active rollouts, stuck first">
          {group ? groupRows(shown, group).map((g) => (
            <li key={g.key} className="mt-2 first:mt-0">
              <p className="flex items-baseline gap-2 border-b border-border px-3 pb-1 text-[12.5px] font-semibold">
                {g.key}<span className="font-normal text-muted-foreground">{g.rows.length}
                  {(() => { const bad = g.rows.filter((r) => r.state !== "on_track").length; return bad ? ` · ${bad} ${bad === 1 ? "needs" : "need"} attention` : "" })()}</span>
              </p>
              <ul className="mt-0.5 grid grid-cols-1 gap-0.5">{g.rows.map(row)}</ul>
            </li>
          )) : shown.map(row)}
          {(fold || (showCalm && calm.length > 0 && calm.length < rows.length)) && (
            <li>
              <button type="button" onClick={() => setShowCalm(fold)} aria-expanded={!fold} aria-label={fold ? `Show ${calm.length} on-track rollouts` : "Hide the on-track rollouts"}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-[13px] text-muted-foreground outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50">
                <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", !fold && "rotate-90")} aria-hidden />
                {fold ? <><span className="font-medium text-foreground">{calm.length} on track</span> · show</> : "Hide the on-track rollouts"}
              </button>
            </li>
          )}
          {rows.length === 0 && (
            <li className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-[13px] text-muted-foreground">
              {data.rows.length === 0 ? (partner ? "No rollout is shared with you yet. It appears here once a project manager adds you." : "No active rollouts yet. Create one from a client PO and it appears here.")
                : stage ? `No rollout in ${stage} matches this filter.`
                : filter === "customer" ? "No rollout is waiting on a customer's approval."
                : "Nothing needs attention — every rollout is inside its stage SLA and on schedule."}
            </li>
          )}
        </ul>
      </ScrollArea>
    </div>
  )
}

// ---- bottom pane: the selected rollout as a flowchart ------------------------
function TimeStrip({ d }: { d: FlowDetail }) {
  const start = new Date(`${d.start_date}T00:00:00`).getTime()
  const today = new Date(`${d.today}T00:00:00`).getTime()
  const end = d.target_end_date ? new Date(`${d.target_end_date}T00:00:00`).getTime() : Math.max(today, start + 14 * 864e5)
  // The domain covers everything worth seeing — a target already in the past
  // sits to the left of today, which is exactly the shape of "overdue".
  const firstEntry = Math.min(...d.stages.filter((s) => s.entered_at).map((s) => new Date(s.entered_at!).getTime()), start)
  const t0 = Math.min(start, end, firstEntry)
  const t1 = Math.max(today, end, start + 864e5)
  const span = t1 - t0 || 1
  const frac = (t: number) => Math.min(1, Math.max(0, (t - t0) / span))
  const pct = (t: number) => `${frac(t) * 100}%`
  const ticks = [{ t: start, l: fmtDate(d.start_date) }, { t: today, l: "today" }, ...(d.target_end_date ? [{ t: end, l: `target ${fmtDate(d.target_end_date)}` }] : [])]
    .sort((a, b) => a.t - b.t)
    .map((tk, i, all) => ({ ...tk, row: i > 0 && frac(tk.t) - frac(all[i - 1].t) < 0.12 ? 1 : 0 }))
  const visited = d.stages.filter((s) => s.entered_at)
  return (
    <div className="relative mt-4 h-[68px] border-t border-border">
      {ticks.map((tk) => (
        <span key={tk.l} className={cn("absolute whitespace-nowrap text-[11px]", tk.row ? "top-5" : "top-1", tk.l === "today" ? "font-semibold text-primary-text" : "text-muted-foreground")}
          style={{ left: pct(tk.t), transform: frac(tk.t) > 0.85 ? "translateX(-100%)" : frac(tk.t) < 0.1 ? "none" : "translateX(-50%)" }}>{tk.l}</span>
      ))}
      <span className="absolute top-10 h-1.5 rounded-full bg-muted" style={{ left: pct(Math.min(start, end)), width: `calc(${pct(Math.max(start, end))} - ${pct(Math.min(start, end))})` }} aria-hidden />
      {visited.map((s, i) => {
        const from = new Date(s.entered_at!).getTime()
        const to = i + 1 < visited.length ? new Date(visited[i + 1].entered_at!).getTime() : today
        const late = s.status === "current" && (d.state === "over_sla" || d.state === "overdue")
        return (
          <Tooltip key={s.name}>
            <TooltipTrigger render={<span />} className={cn("absolute top-10 h-1.5 rounded-full", late ? "bg-warn-line" : "bg-foreground")} style={{ left: pct(from), width: `calc(${pct(to)} - ${pct(from)})` }} />
            <TooltipContent>{s.name} · {days(s.days)}</TooltipContent>
          </Tooltip>
        )
      })}
      <span className="absolute top-8 h-6 w-[1.5px] bg-primary" style={{ left: pct(today) }} aria-hidden />
    </div>
  )
}

export function Detail({ d, reload, onMoved, onClose, standalone = false }: { d: FlowDetail; reload: () => Promise<void>; onMoved: (msg: string, undo?: string) => void; onClose?: () => void; standalone?: boolean }) {
  const [note, setNote] = useState("")
  const [confirming, setConfirming] = useState(false)
  // The flowchart fits its width: measure it, and fold stages that don't fit
  // (finished ones first) until someone asks to see them all.
  const [flowWidth, setFlowWidth] = useState(0)
  const [showAll, setShowAll] = useState(false)
  useEffect(() => { setShowAll(false) }, [d.id])
  const measure = useCallback((el: HTMLOListElement | null) => {
    if (!el) return
    const ro = new ResizeObserver(([e]) => setFlowWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const [comment, setComment] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function decide(decision: "approved" | "declined") {
    if (!d.approval) return
    setBusy(true); setErr(null)
    try {
      await decideApproval(d.id, d.approval.id, decision, comment)
      setComment("")
      onMoved(`${d.stage} ${decision}`)
      await reload()
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not record the decision") } finally { setBusy(false) }
  }
  const open = d.tasks.filter((t) => !t.done)
  const next = nextUp(open, d.stage)
  const openHere = open.filter((t) => t.stage === d.stage).length
  const approvalPending = d.approval?.stage === d.stage && d.approval.status === "pending"
  const told = d.participants.filter((p) => p.user_id !== d.me).length
  async function advance() {
    if (!d.next_stage) return
    setBusy(true); setErr(null)
    try {
      const r = await changeStage(d.id, d.next_stage, note)
      setNote(""); setConfirming(false)
      onMoved(`${d.name} moved to ${d.next_stage}.`, r.undo)
      await reload()
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not move the stage") } finally { setBusy(false) }
  }
  return (
    <div className="grid grid-cols-1 gap-5 px-5 py-4 xl:grid-cols-[minmax(0,1fr)_280px]">
      <div className="min-w-0 xl:col-start-1 xl:row-start-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {standalone
              ? <h1 className="truncate text-[17px] font-semibold tracking-tight">{d.name}</h1>
              : <h2 className="truncate text-[17px] font-semibold tracking-tight">{d.name}</h2>}
            <p className="text-[12.5px] text-muted-foreground">
              {d.client}{d.vendor_name ? ` · ${d.vendor_name}` : ""}{d.product_name ? ` · ${d.product_name}` : ""}{d.outsourcer_name ? ` · via ${d.outsourcer_name}` : ""} · owner {d.owner_name}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {d.approval && d.approval.stage === d.stage && <ApprovalChip status={d.approval.status} className="px-2 py-1 text-[12px]" />}
            {d.state !== "on_track" && <span className={cn("rounded-md px-2 py-1 text-[12px] font-medium", STATE[d.state].chip)}>{stateText({ state: d.state, days_in_stage: d.stages[d.stage_index]?.days ?? null, over_by: d.over_by, target_end_date: d.target_end_date })}</span>}
            {!standalone && <a href={`/projects/${d.id}/report`} className={buttonVariants({ variant: "ghost", size: "sm" })}>Report</a>}
            {!standalone && <a href={`/projects/${d.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>Open project <ExternalLink className="h-3.5 w-3.5" /></a>}
            {onClose && <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close this rollout (Esc)" title="Close (Esc)"><X className="h-4 w-4" /></Button>}
          </div>
        </div>

        {/* the flowchart: one column per stage while they fit (112 px each);
            below md it is a plain stacked list and nothing folds */}
        {(() => {
          const stacked = typeof window !== "undefined" && !window.matchMedia("(min-width: 768px)").matches
          const capacity = showAll || stacked || !flowWidth ? Infinity : Math.max(4, Math.floor((flowWidth + 12) / 112))
          const items = fitStages(d.stages.map((st) => st.status), capacity)
          const itemDone = (it: (typeof items)[number]) => it.kind === "done" || (it.kind === "stage" && d.stages[it.index].status === "done")
          return (
            <ol ref={measure} className="mt-4 grid grid-cols-1 items-start gap-2 md:gap-0 md:overflow-x-auto md:pb-2 md:[grid-template-columns:var(--cols)]" style={{ "--cols": `repeat(${items.length}, minmax(100px, 1fr))` } as CSSProperties} aria-label="Stages">
              {items.map((it, k) => {
                const arrow = k > 0 && (
                  <span className="absolute -left-2 top-[26px] hidden w-4 items-center md:flex" aria-hidden>
                    <span className={cn("h-[1.5px] flex-1", itemDone(items[k - 1]) ? "bg-ok-line" : "bg-input")} />
                    <ArrowRight className={cn("-ml-1.5 h-3 w-3", itemDone(items[k - 1]) ? "text-ok-line" : "text-input")} />
                  </span>
                )
                if (it.kind !== "stage") {
                  const names = d.stages.slice(it.from, it.to + 1).map((st) => st.name)
                  const open = d.tasks.filter((t) => !t.done && names.includes(t.stage)).length
                  return (
                    <li key={`${it.kind}-${it.from}`} className="relative min-w-0 md:px-1.5 md:first:pl-0 md:last:pr-0">
                      {arrow}
                      <button type="button" onClick={() => setShowAll(true)} aria-expanded={false}
                        aria-label={`${it.kind === "done" ? "Finished" : "Later"} stages: ${names.join(", ")}. Show every stage`}
                        title={names.join(" → ")}
                        className={cn("block min-h-[58px] w-full rounded-lg border-[1.5px] px-2.5 py-2 text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                          it.kind === "done" ? "border-ok-line bg-ok-soft hover:bg-ok-soft/70" : "border-dashed border-input bg-card hover:bg-muted")}>
                        <span className={cn("flex items-start gap-1 text-[12.5px] font-semibold leading-tight", it.kind === "later" && "text-nav-fg")}>
                          {it.kind === "done" && <Check className="mt-px h-3.5 w-3.5 shrink-0 text-ok" />}
                          {it.kind === "done" ? `${names.length} done` : `+${names.length} later`}
                        </span>
                        <span className="mt-0.5 block truncate text-[11.5px] text-muted-foreground">{names.join(", ")}</span>
                      </button>
                      {it.kind === "later" && open > 0 && <p className="mt-2 text-[11.5px] text-muted-foreground">{open} open task{open === 1 ? "" : "s"}</p>}
                    </li>
                  )
                }
                const i = it.index, st = d.stages[i]
                return (
                  <li key={st.name} className="relative min-w-0 md:px-1.5 md:first:pl-0 md:last:pr-0">
                    {arrow}
                    <div className={cn("min-h-[58px] rounded-lg border-[1.5px] bg-card px-2.5 py-2",
                      st.status === "done" && "border-ok-line bg-ok-soft",
                      st.status === "current" && cn("ring-[3px]", STATE[d.state].ring),
                      st.status === "next" && "border-dashed border-input")}>
                      <div className={cn("flex items-start gap-1 text-[12.5px] font-semibold leading-tight", st.status === "next" && "text-nav-fg")}>
                        {st.status === "done" && <Check className="mt-px h-3.5 w-3.5 shrink-0 text-ok" />}<span className="line-clamp-2">{st.name}</span>
                      </div>
                      <div className="mt-0.5 truncate text-[11.5px] text-muted-foreground">
                        {st.status === "next" ? (st.sla_days ? `SLA ${st.sla_days} d` : "—") : st.status === "done" ? days(st.days) : `${days(st.days)}${st.sla_days ? ` · SLA ${st.sla_days}` : ""}`}
                      </div>
                    </div>
                    {/* every stage carries its own tasks — work happens here, not on the project page */}
                    <StageTasks d={d} stage={st.name} done={st.status === "done"} reload={reload} onError={setErr} />
                    {st.status === "current" && openHere > 0 && <p className="mt-1 text-[11.5px] text-muted-foreground">{openHere} open before moving on</p>}
                  </li>
                )
              })}
            </ol>
          )
        })()}
        {showAll && flowWidth > 0 && d.stages.length * 112 > flowWidth + 12 && (
          <button type="button" onClick={() => setShowAll(false)} className="mt-1 text-[12px] text-muted-foreground hover:text-foreground">Fold stages to fit</button>
        )}
        {/* one place for errors: the Advance section shows its own when it is on screen */}
        {err && !(d.can_move && d.next_stage) && <p className="mt-2 text-[12px] text-bad" role="alert">{err}</p>}

        <TimeStrip d={d} />
      </div>

      {/* right rail: what to do next, when it's due, how we got here */}
      <aside className="grid grid-cols-1 content-start gap-4 text-[13px] md:grid-cols-2 xl:col-start-2 xl:row-span-2 xl:row-start-1 xl:grid-cols-1">
        <section className="panel p-3">
          <h3 className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-nav-fg"><ChevronRight className="h-3.5 w-3.5" /> Next up</h3>
          {next ? (
            <>
              <p className="font-medium">{next.title}</p>
              <p className="mt-1 flex items-center gap-3 text-muted-foreground">
                <span className="flex items-center gap-1"><UserRound className="h-3.5 w-3.5" />{next.assignee ?? "Unassigned"}</span>
                {next.due_date && <span className="flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" /><DueDate due={next.due_date} today={d.today} className="inline text-[13px]" /></span>}
              </p>
            </>
          ) : <p className="text-muted-foreground">Nothing queued — add a task under a stage.</p>}
        </section>
        <section className="panel p-3">
          <h3 className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-nav-fg"><Clock className="h-3.5 w-3.5" /> ETA</h3>
          {d.target_end_date ? (
            <p><span className="font-medium">{fmtDate(d.target_end_date)}</span>
              <span className={cn("ml-2", d.days_left != null && d.days_left < 0 ? "text-bad" : "text-muted-foreground")}>{d.days_left == null ? "" : d.days_left < 0 ? `${-d.days_left} d late` : `${d.days_left} d left`}</span></p>
          ) : <p className="text-muted-foreground">No target date set.</p>}
          <p className="mt-1 text-muted-foreground">{d.documents} document{d.documents === 1 ? "" : "s"} · {d.tasks.filter((t) => t.done).length}/{d.tasks.length} tasks done</p>
        </section>
        {d.approval && d.approval.stage === d.stage && d.approval.status === "pending" && d.can_approve && (
          <section className="rounded-lg border border-warn-line bg-warn-soft/40 p-3">
            <h3 className="mb-1 text-[12px] font-semibold text-nav-fg">Your approval</h3>
            <p className="mb-2 text-[12.5px] text-muted-foreground">The project moved to <span className="font-medium text-foreground">{d.stage}</span>. Do you agree with this step?</p>
            <Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment (optional)" aria-label="Approval comment" maxLength={2000} className="h-8 text-[13px]" />
            <div className="mt-2 flex gap-2">
              <Button size="sm" className="flex-1" disabled={busy} onClick={() => decide("approved")}>Approve</Button>
              <Button size="sm" variant="outline" className="flex-1" disabled={busy} onClick={() => decide("declined")}>Decline</Button>
            </div>
          </section>
        )}
        {d.approval && d.approval.stage === d.stage && d.approval.status !== "pending" && d.approval.status !== "superseded" && (
          <p className="text-[12.5px] text-muted-foreground">{d.stage} {d.approval.status} by {d.approval.decided_by}{d.approval.comment ? ` · ${d.approval.comment}` : ""}</p>
        )}
        {d.signoff?.awaiting_me && (
          <section className="rounded-lg border border-warn-line bg-warn-soft/40 p-3">
            <h3 className="mb-1 flex items-center gap-1.5 text-[12px] font-semibold text-nav-fg"><FileSignature className="h-3.5 w-3.5" /> Your signature</h3>
            <p className="mb-2 text-[12.5px] text-muted-foreground">The sign-off for {d.name} is waiting for you: review what was delivered, then sign.</p>
            <Link to={`/projects/${d.id}/signoff`} className={cn(buttonVariants({ size: "sm" }), "w-full")}>Review and sign</Link>
          </section>
        )}
        {d.can_move && d.next_stage && d.signoff?.needed && (
          <section className="panel p-3">
            <h3 className="mb-1 flex items-center gap-1.5 text-[12px] font-semibold text-nav-fg"><FileSignature className="h-3.5 w-3.5" /> Sign-off before {d.next_stage}</h3>
            <p className="mb-2 text-[12.5px] text-muted-foreground">{signoffText(d.signoff.status)}. The project closes once the customer has signed and we have countersigned.</p>
            <Link to={`/projects/${d.id}/signoff`} className={cn(buttonVariants({ size: "sm" }), "w-full")}>{d.signoff.status ? "Open the sign-off" : "Prepare the sign-off"}</Link>
          </section>
        )}
        {d.can_move && d.next_stage && !d.signoff?.needed && (
          <section className="panel p-3" onKeyDown={(e) => { if (e.key === "Escape" && confirming) { e.stopPropagation(); setConfirming(false) } }}>
            {/* what the move will do, next to the button that does it */}
            <ul className="mb-2 grid grid-cols-1 gap-1 text-[12.5px] text-muted-foreground">
              {openHere > 0 && <li className="font-medium text-warn">{openHere} open task{openHere === 1 ? "" : "s"} still in {d.stage}</li>}
              {approvalPending && <li className="font-medium text-warn">The customer has not approved {d.stage} yet</li>}
              <li>Tells {told} {told === 1 ? "person" : "people"} on the team</li>
            </ul>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note for the history (optional)" aria-label="Stage change note" maxLength={5000} className="h-8 text-[13px]" />
            {confirming ? (
              <div className="mt-2 grid grid-cols-1 gap-1.5" role="group" aria-label={`Confirm the move to ${d.next_stage}`}>
                <Button size="sm" onClick={advance} disabled={busy} autoFocus>{busy ? "Moving…" : `Move to ${d.next_stage} now`}</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>Cancel</Button>
              </div>
            ) : (
              <Button className="mt-2 w-full" size="sm" onClick={() => setConfirming(true)} disabled={busy}>Advance to {d.next_stage} <ArrowRight className="h-3.5 w-3.5" /></Button>
            )}
            {err && <p className="mt-2 text-[12px] text-bad" role="alert">{err}</p>}
          </section>
        )}
      </aside>

      {/* who and what happened: under the flowchart on wide screens, after the rail otherwise */}
      <div className="grid grid-cols-1 content-start gap-4 text-[13px] md:grid-cols-2 xl:col-start-1 xl:row-start-2">
        <section>
          <h3 className="mb-1.5 flex items-center gap-1.5 text-[12px] font-semibold text-nav-fg"><UserRound className="h-3.5 w-3.5" /> Team</h3>
          <ul className="grid grid-cols-1 gap-1.5">
            {d.participants.map((m) => (
              <li key={m.id} className="flex items-center gap-2 text-[12.5px]">
                <UserAvatar name={m.name} url={m.avatar_url} />
                <span className="min-w-0 flex-1 truncate font-medium">{m.name}</span>
                <span className="text-muted-foreground">{m.role}</span>
              </li>
            ))}
          </ul>
          {!standalone && <a href={`/projects/${d.id}#team`} className="mt-1.5 inline-block text-[12px] text-primary-text hover:underline">Manage team</a>}
        </section>
        {d.recent_notes.length > 0 && (
          <section className="min-w-0">
            {/* min-w-0 all the way down: a truncated note must not widen the column */}
            <h3 className="mb-1.5 text-[12px] font-semibold text-nav-fg">Recent</h3>
            <ul className="grid grid-cols-1 min-w-0 gap-1.5">
              {d.recent_notes.map((n, i) => (
                <li key={i} className="min-w-0 text-[12.5px]"><span className="font-medium">{n.author}</span> <span className="text-muted-foreground">· {n.stage} · <Ago iso={n.created_at} /></span><div className="truncate text-nav-fg">{n.note}</div></li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  )
}

// Phones get the rollout as its own screen with a back button, not a split.
function useWide() {
  const q = "(min-width: 768px)"
  const [wide, setWide] = useState(() => typeof window === "undefined" || window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q)
    const on = () => setWide(m.matches)
    m.addEventListener("change", on)
    return () => m.removeEventListener("change", on)
  }, [])
  return wide
}

export default function Flow({ user }: { user: User }) {
  const wide = useWide()
  const [data, setData] = useState<FlowData | null>(null)
  // The selection is the URL (?rollout=): shareable, and it follows any
  // navigation to it — a palette jump or a link — even while this page is open.
  const [params, setParams] = useSearchParams()
  const q = Number(params.get("rollout"))
  const selectedId = Number.isInteger(q) && q > 0 ? q : null
  const setSelectedId = useCallback((id: number | null) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (id == null) next.delete("rollout"); else next.set("rollout", String(id))
      return next
    // opening a rollout is a step Back can undo (a phone's back gesture returns to the list); moving between rollouts is not
    }, { replace: selectedId != null || id == null })
  }, [setParams, selectedId])
  const [detail, setDetail] = useState<FlowDetail | null>(null)
  // Three ways to look at the portfolio, kept in the URL: the list, a month, or Kibana.
  const vw = params.get("view")
  const view: "list" | "calendar" | "kibana" = vw === "calendar" || (vw === "kibana" && user.kind !== "external") ? vw : "list"
  useEffect(() => { document.title = `${view === "calendar" ? "Calendar" : view === "kibana" ? "Kibana" : "Flow"} · Odin` }, [view])   // test report UX-17
  const setView = useCallback((v: "list" | "calendar" | "kibana") => {
    setParams((prev) => { const next = new URLSearchParams(prev); if (v === "list") next.delete("view"); else next.set("view", v); next.delete("month"); next.delete("day"); return next }, { replace: true })
  }, [setParams])
  // The filter lives in the URL too, so a reload keeps it.
  const f = params.get("filter")
  const filter: Filter = f === "attention" || f === "mine" || f === "customer" ? f : "all"
  const stage = params.get("stage")
  const g = params.get("group")
  const group: FlowGroupBy | null = g === "stage" || g === "client" || g === "owner" ? g : null
  const setGroup = useCallback((v: FlowGroupBy | null) => {
    setParams((prev) => { const next = new URLSearchParams(prev); if (!v) next.delete("group"); else next.set("group", v); return next }, { replace: true })
  }, [setParams])
  const setStage = useCallback((v: string | null) => {
    setParams((prev) => { const next = new URLSearchParams(prev); if (!v) next.delete("stage"); else next.set("stage", v); return next }, { replace: true })
  }, [setParams])
  const setFilter = useCallback((v: Filter) => {
    setParams((prev) => { const next = new URLSearchParams(prev); if (v === "all") next.delete("filter"); else next.set("filter", v); return next }, { replace: true })
  }, [setParams])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ text: string; undo?: string; bad?: boolean } | null>(null)

  const load = useCallback(async () => {
    try { setData(await flow()); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load rollouts") }
  }, [])
  const loadDetail = useCallback(async (id: number) => {
    try { setDetail(await flowDetail(id)) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load the rollout") }
  }, [])
  useEffect(() => { void load() }, [load])
  useEffect(() => { if (selectedId != null) void loadDetail(selectedId) }, [selectedId, loadDetail])
  // Only after a click. On load the list must open at the top, where the
  // stuck rows are — scrolling to a deep-linked row would hide them.
  useEffect(() => {
    // after the split opens, so the row lands inside the shrunken list (phones especially)
    const t = setTimeout(() => document.querySelector('main [aria-current="true"]')?.scrollIntoView({ block: "nearest" }), 60)
    return () => clearTimeout(t)
  }, [selectedId])
  // Esc closes the rollout, unless it is cancelling something inside a field or dialog.
  useEffect(() => {
    if (selectedId == null) return
    const onKey = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.key !== "Escape" || e.defaultPrevented || t.closest("input, textarea, select, dialog, [role=dialog]")) return
      setSelectedId(null)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [selectedId, setSelectedId])

  async function undoMove(path: string) {
    try {
      const r = await postForm(path)
      const back = r.messages.join(" ")
      setNotice({ text: back || "Move undone", bad: !back.startsWith("Moved back") })
      await Promise.all([load(), selectedId != null ? loadDetail(selectedId) : Promise.resolve()])
    } catch (e) { setNotice({ text: e instanceof ApiError ? e.message : "Could not undo the move", bad: true }) }
  }

  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />

  const views = (
    <span className="flex rounded-full bg-muted p-0.5" role="group" aria-label="View">
      {([["list", LayoutList, "Rollouts"], ["calendar", CalendarDays, "Calendar"], ...(user.kind === "external" ? [] : [["kibana", BarChart3, "Kibana"] as const])] as const).map(([v, Icon, label]) => (
        <button key={v} type="button" onClick={() => setView(v)} aria-pressed={view === v}
          className={cn("flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium", view === v ? "bg-card text-foreground shadow-card" : "text-muted-foreground hover:text-foreground")}>
          <Icon className="h-3.5 w-3.5" aria-hidden />{label}
        </button>
      ))}
    </span>
  )
  if (view !== "list") return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 pb-2 pt-4">
        <h1 className="text-[17px] font-semibold tracking-tight">{view === "calendar" ? "Calendar" : "Kibana"}</h1>
        {views}
      </div>
      <div className="panel mx-4 mb-4 flex min-h-0 flex-1 flex-col overflow-hidden">{view === "calendar" ? <Calendar wide={wide} /> : <Kibana rollout={selectedId} onRollout={setSelectedId} />}</div>
    </div>
  )
  const list = <RolloutList data={data} me={user.id} partner={user.kind === "external"} selectedId={selectedId} onSelect={setSelectedId} filter={filter} setFilter={setFilter} stage={stage} setStage={setStage} group={group} setGroup={setGroup} tools={views} />
  const pane = selectedId != null && (
    <>
              {!wide && (
                <button type="button" onClick={() => setSelectedId(null)} className="flex h-11 items-center gap-1 px-4 text-[13.5px] font-medium text-primary-text">
                  <ChevronLeft className="h-4 w-4" aria-hidden /> All rollouts
                </button>
              )}
              {notice && (
                <div className={cn("mx-5 mt-3 flex items-center justify-between gap-3 rounded-md px-3 py-1.5 text-[12.5px]", notice.bad ? "bg-bad-soft text-bad" : "bg-ok-soft text-ok")} role="status">
                  <span>{notice.text}
                    {/* the mover can put it back for five minutes; the server decides */}
                    {notice.undo && <button type="button" onClick={() => void undoMove(notice.undo!)} className="ml-2 font-semibold underline-offset-2 hover:underline">Undo</button>}
                  </span>
                  <button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
                </div>
              )}
              {detail && detail.id === selectedId ? (
                <Detail d={detail} reload={async () => { await Promise.all([load(), loadDetail(selectedId)]) }} onMoved={(text, undo) => setNotice({ text, undo })} onClose={wide ? () => setSelectedId(null) : undefined} />
              ) : <PageSkeleton />}
    </>
  )
  // each pane is a card on the ground
  if (!wide) return selectedId != null ? <ScrollArea className="panel mx-3 mb-3 min-h-0 flex-1">{pane}</ScrollArea> : <div className="panel mx-3 mb-3 flex min-h-0 flex-1 flex-col overflow-hidden">{list}</div>

  return (
    // the margins sit on a wrapper: the group sets an inline width of 100%, which plus mx-4 ran 32 px past the window (test report UX-2)
    <div className="mx-4 mb-4 flex min-h-0 min-w-0 flex-1 flex-col">
    <ResizablePanelGroup orientation="vertical" className="min-h-0 flex-1">
      <ResizablePanel defaultSize={selectedId == null ? 100 : 48} minSize={20}><div className="panel flex h-full min-h-0 flex-col overflow-hidden">{list}</div></ResizablePanel>
      {selectedId != null && (
        <>
          <ResizableHandle withHandle aria-label="Resize the rollout list and the flowchart" />
          <ResizablePanel defaultSize={52} minSize={25}>
            <ScrollArea className="panel h-full">{pane}</ScrollArea>
          </ResizablePanel>
        </>
      )}
    </ResizablePanelGroup>
    </div>
  )
}
