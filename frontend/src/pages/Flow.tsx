import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react"
import { Segmented } from "@/components/Segmented"
import { MoveConfirm } from "@/components/MoveConfirm"
import { chip, fieldAuto, filterSelect } from "@/lib/ui"
import { askConfirm } from "@/lib/confirm"
import { Inbox, ArrowRight, CalendarDays, GanttChart, Kanban as KanbanIcon, Check, ChevronLeft, ChevronRight, LayoutList, Clock, ExternalLink, FileSignature, Plus, Trash2, UserRound, X } from "lucide-react"
import { Link, useSearchParams } from "react-router-dom"
import { UserAvatar } from "@/components/UserAvatar"
import { TeamStack } from "@/components/TeamStack"
import { Ago } from "@/components/Ago"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { ApiError, addTask, postForm, decideApproval, deleteTask, editTask, flow, flowDetail, toggleTask, type ApprovalStatus, type FlowData, type FlowDetail, type FlowRow, type FlowTask, type User } from "@/lib/api"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/ui/empty"
import { DatePicker } from "@/components/DatePicker"
import { STATE } from "@/lib/state"
import { StateChip } from "@/components/StateChip"
import { days, fitStages, fmtDate, groupRows, parseStamp, signoffText, stateText, lateBy, nextUp, stageColumns, timelineSummary, type FlowGroupBy } from "@/lib/format"
import { Stepper } from "@/components/Stepper"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { useMedia, useWidth } from "@/lib/useMeasure"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"

// the heavier views load when first opened, so the list stays fast
const FlowKanban = lazy(() => import("@/pages/FlowKanban"))
const FlowGantt = lazy(() => import("@/pages/FlowGantt"))
const Calendar = lazy(() => import("@/pages/Calendar").then((m) => ({ default: m.Calendar })))
type View = "list" | "kanban" | "gantt" | "calendar"
const VIEWS: View[] = ["list", "kanban", "gantt", "calendar"]


// Customer approval of the current stage: amber while open, green/red once decided.
const APPROVAL: Record<ApprovalStatus, { label: string; chip: string } | null> = {
  pending:    { label: "Awaiting approval", chip: "bg-warn-soft text-warn" },
  approved:   { label: "Approved",          chip: "bg-ok-soft text-ok" },
  declined:   { label: "Declined",          chip: "bg-bad-soft text-bad" },
  superseded: null,
}

// one width for every view's title, so the view switcher after it stays put
const TITLE = "w-36 shrink-0 text-[17px] font-semibold tracking-tight"

function ApprovalChip({ status, className }: { status: ApprovalStatus | null; className?: string }) {
  const a = status && APPROVAL[status]
  return a ? <span className={cn("whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium", a.chip, className)}>{a.label}</span> : null
}



// A task's due date, in the bad state once it has passed.
function DueDate({ due, today, className }: { due: string; today: string; className?: string }) {
  const late = lateBy(due, today)
  return <span className={cn("block text-[11px]", late > 0 ? "font-medium text-bad" : "text-muted-foreground", className)}>
    {late > 0 ? `${late} d late · due ${fmtDate(due)}` : `due ${fmtDate(due)}`}</span>
}

// A task's fields, for adding one or correcting one in place. What was typed
// stays when the save fails; `save` says whether it worked.
type TaskValues = { title: string; assignee: string; due: string }
function TaskForm({ d, label, init, busy, onSave, onCancel, submitLabel }: {
  d: FlowDetail; label: string; init: TaskValues; busy: boolean; submitLabel: string
  onSave: (v: TaskValues) => Promise<boolean>; onCancel: () => void
}) {
  const [v, setV] = useState(init)
  const set = (k: keyof TaskValues) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value })
  return (
    <form className="mt-2 grid grid-cols-1 gap-1" onSubmit={async (e) => { e.preventDefault(); if (v.title.trim() && await onSave(v) && !init.title) setV({ ...v, title: "" }) }}
      onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onCancel() } }}>
      <Input autoFocus value={v.title} onChange={set("title")} placeholder="Task" aria-label={label} maxLength={200} className="h-7 px-2 text-[13px]" />
      <select value={v.assignee} onChange={set("assignee")} aria-label="Assign to" className={cn(fieldAuto, "h-7 min-w-0 text-[12px]")}>
        <option value="">Unassigned</option>
        {d.assignable.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
      </select>
      <DatePicker value={v.due} onChange={(due) => setV({ ...v, due })} label="Due date" placeholder="Due" className="h-7 px-2 text-[12px]" />
      <div className="flex items-center gap-1">
        <Button type="submit" size="sm" className="h-7 flex-1 px-2" loading={busy} disabled={!v.title.trim()} aria-label={submitLabel}>{init.title ? "Save" : <Plus className="h-3.5 w-3.5" />}</Button>
        <Button type="button" size="sm" variant="ghost" className="h-7 px-2" onClick={onCancel} aria-label="Cancel"><X className="h-3.5 w-3.5" /></Button>
      </div>
    </form>
  )
}

// ---- tasks under a stage box: tick, add, correct, remove — no page change ------
// `quiet` (stages other than the current one): finished tasks fold to "n done" and
// "+ Task" shows on hover or focus, so the chart is not a wall of links (critique 10 Oct)
function StageTasks({ d, stage, done, reload, onError, quiet = false }: { d: FlowDetail; stage: string; done: boolean; reload: () => Promise<void>; onError: (m: string | null) => void; quiet?: boolean }) {
  const all = d.tasks.filter((t) => t.stage === stage)
  const finished = all.filter((t) => t.done).length
  const [showDone, setShowDone] = useState(false)
  const tasks = quiet && !showDone ? all.filter((t) => !t.done) : all
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const canTick = (t: FlowTask) => d.can_edit || t.assignee_id === d.me
  async function run(fn: () => Promise<unknown>, done?: string): Promise<boolean> {
    setBusy(true); onError(null)
    try { await fn(); await reload(); if (done) toast(done); return true }
    catch (e) { onError(e instanceof ApiError ? e.message : "That did not save"); return false }
    finally { setBusy(false) }
  }
  const fields = (v: TaskValues) => ({ title: v.title.trim(), assignee_id: v.assignee ? Number(v.assignee) : null, due_date: v.due || null })
  return (
    <div className="mt-2 text-[13px]">
      {tasks.length > 0 && (
        <ul className="divide-y divide-border border-t border-border">
          {tasks.map((t) => editing === t.id ? (
            <li key={t.id} className="py-1">
              <TaskForm d={d} label={`Task title`} submitLabel={`Save ${t.title}`} busy={busy} init={{ title: t.title, assignee: t.assignee_id ? String(t.assignee_id) : "", due: t.due_date ?? "" }}
                onCancel={() => setEditing(null)}
                onSave={async (v) => { const ok = await run(() => editTask(d.id, t.id, fields(v)), "Task saved"); if (ok) setEditing(null); return ok }} />
            </li>
          ) : (
            <li key={t.id} className={cn("group flex items-center gap-2 py-2", t.done && "text-muted-foreground")}>
              <button type="button" disabled={!canTick(t) || busy} onClick={() => run(() => toggleTask(d.id, t.id), t.done ? `Reopened ${t.title}` : `Done: ${t.title}`)}
                aria-label={t.done ? `Reopen ${t.title}` : `Complete ${t.title}`}
                className={cn("relative flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border before:absolute before:-inset-[5px] before:content-['']", t.done ? "border-ok-line bg-ok-line text-background" : "border-input bg-background", canTick(t) ? "hover:border-foreground" : "cursor-default opacity-60")}>
                {t.done && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
              </button>
              <span className="min-w-0 flex-1">
                {/* the title opens the task for correcting: title, who, when */}
                {d.can_edit && !t.done
                  ? <button type="button" onClick={() => setEditing(t.id)} title={`${t.title} — edit`} aria-label={`Edit ${t.title}`} className="line-clamp-3 text-left decoration-dotted underline-offset-2 hover:underline">{t.title}</button>
                  : <span title={t.title} className={cn("line-clamp-3", t.done && "line-through")}>{t.title}</span>}
                {/* the person the task is on may move its date, nothing else (the server allows the same) */}
                {!d.can_edit && t.assignee_id === d.me && !t.done
                  ? <DatePicker value={t.due_date ?? ""} label={`Due date of ${t.title}`} placeholder="Set a due date" disabled={busy} className="mt-1 h-7 px-2 text-[12px]"
                      onChange={(due) => void run(() => editTask(d.id, t.id, { title: t.title, assignee_id: t.assignee_id, due_date: due || null }), due ? `${t.title}: due ${fmtDate(due)}` : `${t.title}: no date`)} />
                  : t.due_date && !t.done && <DueDate due={t.due_date} today={d.today} />}
              </span>
              {t.assignee && <UserAvatar name={t.assignee} url={t.assignee_avatar_url} className="h-5 w-5" textClass="text-[11px]" />}
              {d.can_edit && (
                <button type="button" disabled={busy} onClick={async () => {
                  // a deleted task comes back with Undo: the same title, person, date and stage
                  if (await run(() => deleteTask(d.id, t.id))) toast(`Deleted ${t.title}`, { action: { label: "Undo", run: () => void run(() => addTask(d.id, { title: t.title, stage: t.stage, assignee_id: t.assignee_id, due_date: t.due_date }), `${t.title} is back`) } })
                }} aria-label={`Delete ${t.title}`}
                  className="relative hidden shrink-0 text-muted-foreground before:absolute before:-inset-[5px] before:content-[''] hover:text-destructive group-hover:block group-focus-within:block [@media(hover:none)]:block"><Trash2 className="h-3.5 w-3.5" /></button>
              )}
            </li>
          ))}
        </ul>
      )}
      {quiet && finished > 0 && <button type="button" onClick={() => setShowDone(!showDone)} className="mt-1 text-[12px] text-muted-foreground hover:text-foreground">{showDone ? "Hide finished" : `${finished} done`}</button>}
      {/* a finished stage keeps its tasks but takes no new ones */}
      {d.can_edit && !done && (adding ? (
        <TaskForm d={d} label={`New task in ${stage}`} submitLabel="Add task" busy={busy} init={{ title: "", assignee: "", due: "" }} onCancel={() => setAdding(false)}
          onSave={(v) => run(() => addTask(d.id, { stage, ...fields(v) }), `Task added to ${stage}`)} />
      ) : (
        <button type="button" onClick={() => setAdding(true)} aria-label={`Add a task to ${stage}`} className={cn("mt-1 flex items-center gap-1 text-[12px] text-muted-foreground hover:text-primary-text", quiet && "opacity-0 transition-opacity focus:opacity-100 group-hover/node:opacity-100")}>
          <Plus className="h-3 w-3" /> Task
        </button>
      ))}
    </div>
  )
}

// ---- top pane: every active rollout, stuck first -------------------------------
const needsAttention = (r: FlowRow) => r.state !== "on_track" || r.late_tasks > 0
type Filter = "all" | "attention" | "customer" | "mine"

// What happens next on this rollout, in one quiet line.
function NextLine({ r, today }: { r: FlowRow; today: string }) {
  const t = r.next_task
  const late = t?.due_date ? lateBy(t.due_date, today) : 0
  return (
    <span className="flex min-w-0 items-center gap-2 text-[12px] text-muted-foreground">
      {t ? (
        <>
          {/* the title keeps ~16 characters; the extras give way before it does */}
          <span className="min-w-[min(10rem,100%)] shrink truncate" title={t.title}><span className="text-nav-fg">Next:</span> {t.title}</span>
          {t.assignee && <span className="hidden min-w-0 shrink-[4] truncate sm:inline" title={t.assignee}>· {t.assignee}</span>}
          {t.due_date && <span className={cn("shrink-0", late > 0 && "font-medium text-bad")}>· {late > 0 ? `${late} d late` : `due ${fmtDate(t.due_date)}`}</span>}
        </>
      ) : <span className="truncate">No open task</span>}
      {/* the task name comes first: the tally only where there is room for both */}
      {r.total_tasks > 0 && <span className="hidden shrink-0 tabular-nums lg:inline">· {r.total_tasks - r.open_tasks} of {r.total_tasks} done</span>}
      {r.stale && <span className="shrink-0">· idle {Math.round(r.idle_days ?? 0)} d</span>}
    </span>
  )
}

function RolloutRow({ r, selected, tabStop, onSelect, today, me }: {
  r: FlowRow; selected: boolean; tabStop: boolean; onSelect: (id: number) => void; today: string; me: number
}) {
  const chip = r.state === "on_track" ? <span className="whitespace-nowrap text-[12px] text-muted-foreground"><span className="sr-only">On track: </span>{stateText(r)}</span>
    : <StateChip state={r.state} text={stateText(r)} />
  // The viewer is on most of their own rows: show who else is.
  const others = r.team.filter((p) => p.id !== me)
  const t = r.next_task
  return (
    <li>
      <button type="button" data-row data-id={r.id} onClick={() => onSelect(r.id)} aria-current={selected || undefined} tabIndex={tabStop ? 0 : -1}
        aria-label={`${r.name}${r.name.includes(r.client) ? "" : `, ${r.client}`}. ${r.stage}, stage ${r.stage_index + 1} of ${r.stages.length}. ${r.state === "on_track" ? `On track, ${stateText(r)} in stage` : `${STATE[r.state].label}, ${stateText(r)}`}${r.approval === "pending" ? ". Waiting on the customer's approval" : r.approval === "declined" ? ". Customer declined" : r.approval === "approved" ? ". Approved" : ""}. ${t ? `Next: ${t.title}${t.assignee ? `, ${t.assignee}` : ""}` : "No open task"}${r.stale ? `. Idle ${Math.round(r.idle_days ?? 0)} days` : ""}`}
        className={cn("grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2 text-left outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50",
          "md:grid-cols-[minmax(240px,1.6fr)_minmax(120px,1fr)_210px_76px] md:gap-x-4 md:gap-y-1",
          selected ? "border-transparent bg-muted shadow-[inset_3px_0_0_var(--ring)]" : "border-transparent hover:bg-muted focus-visible:bg-muted")}>
        <span className="flex min-w-0 items-center gap-2 md:col-start-1 md:row-start-1">
          <span className={cn("h-2 w-2 shrink-0 rounded-full md:hidden", r.state === "on_track" ? "bg-transparent" : STATE[r.state].dot)} aria-hidden />
          <span className="truncate text-[14px] font-medium" title={r.name}>{r.name}</span>
          {!r.name.includes(r.client) && <span className="hidden truncate text-[12px] text-muted-foreground sm:inline" title={r.client}>{r.client}</span>}
        </span>
        <span className="justify-self-end md:hidden">{chip}</span>
        {/* the row's own stages, so the bar reads on its own (shared columns left unlabelled gaps: critique 10 Oct) */}
        <span className="hidden md:col-start-2 md:row-span-2 md:row-start-1 md:grid md:gap-1">
          <Stepper stages={r.stages} index={r.stage_index} state={r.state} selected={selected} />
          <span className="text-[11px] text-muted-foreground" aria-hidden>stage {r.stage_index + 1} of {r.stages.length}</span>
        </span>
        {/* phones: the stage and a progress bar in place of the dots */}
        <span className="col-span-2 flex min-w-0 items-center gap-2 pl-4 md:col-span-1 md:col-start-3 md:row-span-2 md:row-start-1 md:grid md:gap-1 md:pl-0">
          <span className="truncate text-[13px] font-medium" title={r.stage}>{r.stage}</span>
          <span className="h-1 w-12 shrink-0 overflow-hidden rounded-full bg-muted md:hidden" aria-hidden>
            <span className="block h-full bg-ok-line" style={{ width: `${((r.stage_index + 1) / Math.max(1, r.stages.length)) * 100}%` }} />
          </span>
          <span className="flex min-w-0 flex-wrap items-center gap-2 gap-y-1">
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

// attention: off track, or on track with a task past its date (critique 10 Oct; the state stays On track)
const match = (r: FlowRow, f: Filter) =>
  f === "attention" ? needsAttention(r) : f === "customer" ? r.approval === "pending" : f === "mine" ? r.mine : true

// One header for every view of the flow: the title, the view switcher, the
// counts and the filters, in the same place, so switching views moves nothing.
function FlowHeader({ data, title, views, filter, setFilter, group, setGroup, stage, setStage }: {
  data: FlowData; title: string; views: ReactNode; filter?: Filter; setFilter?: (f: Filter) => void
  group?: FlowGroupBy | null; setGroup?: (g: FlowGroupBy | null) => void
  stage?: string | null; setStage?: (s: string | null) => void   // shown as a removable chip where the view has no stage pills
}) {
  const count = (f: Filter) => data.rows.filter((r) => match(r, f)).length
  const chips = ([
    { key: "all", label: "All", n: data.rows.length },
    { key: "attention", label: "Needs attention", n: data.rows.filter(needsAttention).length },
    { key: "customer", label: "Waiting on customer", n: count("customer") },
    { key: "mine", label: "Mine", n: count("mine") },
  ] as { key: Filter; label: string; n: number }[])
    // a filter that changes nothing is noise: "Mine" for someone on every rollout, "Waiting" with none waiting
    .filter((c) => c.key === filter || c.key === "all" || (c.n > 0 && c.n < data.rows.length) || (c.key === "attention" && c.n > 0))
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 pb-2 pt-4">
      <h1 className={TITLE}>{title}</h1>
      {views}
      {filter && (
        <p className="text-[13px] text-muted-foreground">
          {data.rows.length} active
          {data.counts.overdue ? <> · <span className="font-medium text-bad">{data.counts.overdue} overdue</span></> : null}
          {data.counts.over_sla ? <> · <span className="font-medium text-warn">{data.counts.over_sla} over SLA</span></> : null}
          {data.counts.due_soon ? <> · <span className="font-medium text-warn">{data.counts.due_soon} due soon</span></> : null}
          {data.counts.late_tasks ? <> · <span className="font-medium text-bad">{data.counts.late_tasks} on track with late tasks</span></> : null}
        </p>
      )}
      {filter && setFilter && (
        <div className="flex flex-wrap items-center gap-2 md:ml-auto">
          {stage && setStage && (
            <button type="button" onClick={() => setStage(null)} aria-label={`Stage ${stage}: show every stage`} className={cn(chip(true), "flex items-center gap-1")}>{stage} <X className="h-3 w-3" aria-hidden /></button>
          )}
          {chips.map((c) => (
            <button key={c.key} type="button" onClick={() => setFilter(c.key)} aria-pressed={filter === c.key} aria-label={`${c.label}, ${c.n}`}
              className={cn(chip(filter === c.key), "flex items-center gap-1")}>
              {c.label}{c.n ? <span className={filter === c.key ? "text-background/70" : "text-muted-foreground"}>{c.n}</span> : null}
            </button>
          ))}
          {setGroup && (
            <label className="flex items-center gap-2 pl-1 text-[13px] text-muted-foreground">
              Group
              <select aria-label="Group rollouts by" value={group ?? ""} onChange={(e) => setGroup((e.target.value || null) as FlowGroupBy | null)}
                className={cn(filterSelect, "pointer-coarse:h-10")}>
                <option value="">None</option><option value="stage">Stage</option><option value="client">Client</option><option value="owner">Owner</option>
              </select>
            </label>
          )}
        </div>
      )}
    </div>
  )
}

function RolloutList({ data, me, partner, selectedId, onSelect, filter, setFilter, stage, setStage, group, header }: {
  data: FlowData; me: number; partner?: boolean; selectedId: number | null; onSelect: (id: number) => void; header: ReactNode
  filter: Filter; setFilter: (f: Filter) => void; stage: string | null; setStage: (s: string | null) => void; group: FlowGroupBy | null
}) {
  const rows = useMemo(() => data.rows.filter((r) => match(r, filter) && (!stage || r.stage === stage)), [data.rows, filter, stage])
  // Every row's stages in one column order, so a stage lines up down the list.
  const columns = useMemo(() => stageColumns(data.rows.map((r) => r.stages)), [data.rows])
  const inStage = useMemo(() => {
    const n = new Map<string, number>()
    for (const r of data.rows) if (match(r, filter)) n.set(r.stage, (n.get(r.stage) ?? 0) + 1)
    return n
  }, [data.rows, filter])
  // On track needs no attention: folded into one line while anything else does.
  const calm = group ? [] : rows.filter((r) => !needsAttention(r))
  const [showCalm, setShowCalm] = useState(false)
  const fold = calm.length > 0 && calm.length < rows.length && !showCalm && !calm.some((r) => r.id === selectedId)
  const shown = fold ? rows.filter(needsAttention) : rows
  // One tab stop for the whole list; ↑/↓ or j/k move between rows, Enter opens.
  function onKeys(e: KeyboardEvent<HTMLUListElement>) {
    // → or l: from the list into the open rollout's actions (the rail), without a Tab marathon
    if ((e.key === "ArrowRight" || e.key === "l") && selectedId != null) {
      const first = document.querySelector<HTMLElement>("[data-rail] button:not(:disabled), [data-rail] a, [data-rail] input")
      if (first) { e.preventDefault(); first.focus() }
      return
    }
    const step = e.key === "ArrowDown" || e.key === "j" ? 1 : e.key === "ArrowUp" || e.key === "k" ? -1 : 0
    const buttons = [...e.currentTarget.querySelectorAll<HTMLButtonElement>("button[data-row]")]
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement)
    const to = e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : step && at >= 0 ? at + step : -1
    if (to < 0 || to >= buttons.length) return
    e.preventDefault()
    buttons[to].focus()
  }
  const tabStop = shown.some((r) => r.id === selectedId) ? selectedId : shown[0]?.id
  const row = (r: FlowRow) => <RolloutRow key={r.id} r={r} selected={r.id === selectedId} tabStop={r.id === tabStop} onSelect={onSelect} today={data.today} me={me} />
  return (
    <div className="flex h-full flex-col">
      {header}
      {/* how many sit in each stage, named; a tap shows only that stage */}
      <nav aria-label="Rollouts in each stage" className="fade-x flex gap-2 overflow-x-auto px-5 pb-2 [scrollbar-width:none]">
        {columns.filter((c) => inStage.get(c) || stage === c).map((c) => {
          const on = stage === c
          return (
            <button key={c} type="button" onClick={() => setStage(on ? null : c)} aria-pressed={on}
              aria-label={`${c}: ${inStage.get(c) ?? 0}. ${on ? "Show every stage" : "Show only this stage"}`}
              className={cn(chip(on), "flex items-center gap-1 font-normal")}>
              {c} <span className={cn("font-medium tabular-nums", on ? "text-background" : "text-foreground")}>{inStage.get(c) ?? 0}</span>
              {on && <X className="h-3 w-3" aria-hidden />}
            </button>
          )
        })}
      </nav>
      <ScrollArea className="min-h-0 flex-1">
        <div className="sticky top-0 z-10 mx-3 hidden grid-cols-[minmax(240px,1.6fr)_minmax(120px,1fr)_210px_76px] gap-4 border-y border-transparent bg-card px-3 py-2 text-[12px] text-muted-foreground md:grid">
          <span>Rollout · next step <span className="ml-1">(↑↓ or j/k, Enter opens, right arrow to its actions)</span></span><span>Progress</span><span>Stage · status</span><span>Team</span>
        </div>
        <ul className="grid grid-cols-1 gap-1 px-3 pb-3" onKeyDown={onKeys} aria-label="Active rollouts, stuck first">
          {group ? groupRows(shown, group).map((g) => (
            <li key={g.key} className="mt-2 first:mt-0">
              <p className="flex items-baseline gap-2 border-b border-border px-3 pb-1 text-[13px] font-semibold">
                {g.key}<span className="font-normal text-muted-foreground">{g.rows.length}
                  {(() => { const bad = g.rows.filter(needsAttention).length; return bad ? ` · ${bad} ${bad === 1 ? "needs" : "need"} attention` : "" })()}</span>
              </p>
              <ul className="mt-1 grid grid-cols-1 gap-1">{g.rows.map(row)}</ul>
            </li>
          )) : shown.map(row)}
          {(fold || (showCalm && calm.length > 0 && calm.length < rows.length)) && (
            <li>
              <button type="button" onClick={() => setShowCalm(fold)} aria-expanded={!fold} aria-label={fold ? `Show ${calm.length} on-track rollouts` : "Hide the on-track rollouts"}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-3 text-left text-[13px] text-muted-foreground outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50">
                <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", !fold && "rotate-90")} aria-hidden />
                {fold ? <><span className="font-medium text-foreground">{calm.length} on track</span> · show</> : "Hide the on-track rollouts"}
              </button>
            </li>
          )}
          {rows.length === 0 && (
            <li><Empty className="rounded-lg bg-muted/40 py-12"><EmptyHeader><EmptyMedia variant="icon"><Inbox /></EmptyMedia><EmptyDescription>
              {data.rows.length === 0 ? (partner ? "No rollout is shared with you yet. It appears here once a project manager adds you." : "No active rollouts yet. Create one from a client PO and it appears here.")
                : stage ? <>No rollout in {stage} matches this filter. <button type="button" onClick={() => { setStage(null); setFilter("all") }} className="font-medium text-foreground underline underline-offset-2">Show every rollout</button></>
                : filter === "customer" ? "No rollout is waiting on a customer's approval."
                : "Nothing needs attention — every rollout is inside its stage SLA, on schedule, and no task is late."}
            </EmptyDescription></EmptyHeader></Empty></li>
          )}
        </ul>
      </ScrollArea>
    </div>
  )
}

// ---- bottom pane: the selected rollout as a flowchart ------------------------
const NODE = 148   // px per flowchart column before stages fold
// The rollout's timeline (9 Oct 2026: the bare strip read as noise): a titled
// line in words, then — once there is a span worth drawing — a bar from the
// start to the target (or to today when there is none), each visited stage a
// segment, today an ink line, and a legend for the colours.
function TimeStrip({ d }: { d: FlowDetail }) {
  const start = new Date(`${d.start_date}T00:00:00`).getTime()
  const today = new Date(`${d.today}T00:00:00`).getTime()
  const end = d.target_end_date ? new Date(`${d.target_end_date}T00:00:00`).getTime() : today
  // The domain covers everything worth seeing — a target already in the past
  // sits to the left of today, which is exactly the shape of "overdue".
  const firstEntry = Math.min(...d.stages.filter((s) => s.entered_at).map((s) => parseStamp(s.entered_at!).getTime()), start)
  const t0 = Math.min(end, firstEntry)
  const t1 = Math.max(today, end)
  const drawn = t1 - t0 >= 2 * 864e5   // under two days there is nothing to see but a dot
  const span = t1 - t0
  const frac = (t: number) => Math.min(1, Math.max(0, (t - t0) / span))
  const pct = (t: number) => `${frac(t) * 100}%`
  const ticks = [{ t: start, l: fmtDate(d.start_date) }, { t: today, l: "today" }, ...(d.target_end_date ? [{ t: end, l: `target ${fmtDate(d.target_end_date)}` }] : [])]
    .sort((a, b) => a.t - b.t)
    .map((tk, i, all) => ({ ...tk, row: i > 0 && frac(tk.t) - frac(all[i - 1].t) < 0.12 ? 1 : 0 }))
  const visited = d.stages.filter((s) => s.entered_at)
  const late = d.state === "over_sla" || d.state === "overdue"
  const lateBar = d.state === "overdue" ? "bg-bad-line" : "bg-warn-line"   // overdue is red here as everywhere else
  return (
    <section className="mt-4 border-t border-border pt-3" aria-label="Timeline">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-[13px]"><span className="font-semibold">Timeline</span><span className="text-muted-foreground"> · {timelineSummary(d.start_date, d.today, d.target_end_date, d.stage_index === d.stages.length - 1)}</span></p>
        {drawn && (
          <p className="flex items-center gap-3 text-[11px] text-muted-foreground" aria-hidden>
            {[["h-1.5 w-3 rounded-full bg-ok-line", "stage done"], [cn("h-1.5 w-3 rounded-full", late ? lateBar : "bg-foreground"), "current stage"], ["h-3 border-l-[1.5px] border-dashed border-nav-fg", "target"], ["h-3 w-[1.5px] bg-foreground", "today"]].map(([swatch, label]) => (
              <span key={label} className="flex items-center gap-1"><span className={swatch} />{label}</span>
            ))}
          </p>
        )}
      </div>
      {drawn && (
        <div className="relative mt-1 h-[52px]">
          {ticks.map((tk) => (
            <span key={tk.l} className={cn("absolute whitespace-nowrap text-[11px]", tk.row ? "top-4" : "top-0", tk.l === "today" ? "font-semibold text-foreground" : "text-muted-foreground")}
              style={{ left: pct(tk.t), transform: frac(tk.t) > 0.85 ? "translateX(-100%)" : frac(tk.t) < 0.1 ? "none" : "translateX(-50%)" }}>{tk.l}</span>
          ))}
          <span className="absolute top-9 h-1.5 rounded-full bg-foreground/10" style={{ left: pct(t0), width: `calc(${pct(t1)} - ${pct(t0)})` }} aria-hidden />
          {visited.map((s, i) => {
            const from = parseStamp(s.entered_at!).getTime()
            const to = i + 1 < visited.length ? parseStamp(visited[i + 1].entered_at!).getTime() : today
            return (
              <Tooltip key={s.name}>
                <TooltipTrigger render={<span />} className={cn("absolute top-9 h-1.5 rounded-full", s.status === "current" && late ? lateBar : s.status === "done" ? "bg-ok-line" : "bg-foreground")}
                  style={{ left: pct(from), width: `max(6px, calc(${pct(to)} - ${pct(from)}))` }} />
                <TooltipContent>{s.name} · {days(s.days)}</TooltipContent>
              </Tooltip>
            )
          })}
          {d.target_end_date && <span className={cn("absolute top-7 h-6 border-l-[1.5px] border-dashed", end < today ? "border-bad-line" : "border-nav-fg")} style={{ left: pct(end) }} aria-hidden />}
          {d.target_end_date && end < today && <span className="absolute top-9 h-1.5" aria-hidden
            style={{ left: pct(end), width: `calc(${pct(today)} - ${pct(end)})`, background: "repeating-linear-gradient(135deg, var(--bad-line) 0 3px, transparent 3px 6px)" }} />}
          <span className="absolute top-7 h-6 w-[1.5px] bg-foreground" style={{ left: pct(today) }} aria-hidden />
        </div>
      )}
    </section>
  )
}

export function Detail({ d, reload, onMoved, onClose, standalone = false }: { d: FlowDetail; reload: () => Promise<void>; onMoved: (msg: string, undo?: string) => void; onClose?: () => void; standalone?: boolean }) {
  // on the project page the name is the h1, so the rail's headings are h2s there
  const H = standalone ? "h2" : "h3"
  // The flowchart fits its width: measure it, and fold stages that don't fit
  // (finished ones first) until someone asks to see them all.
  const [flowWidth, measure] = useWidth<HTMLOListElement>()
  const [showAll, setShowAll] = useState(false)
  useEffect(() => { setShowAll(false) }, [d.id])
  const [comment, setComment] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function decide(decision: "approved" | "declined") {
    if (!d.approval) return
    // a decline cannot be taken back: ask, and say what it does (sim roles-9)
    if (decision === "declined" && !(await askConfirm(`Decline ${d.approval.stage}? The project manager is told; your comment goes with it. This cannot be undone.`))) return
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
  // the terminal stage is the end: the project is closed, nothing is "next"
  const closed = !d.next_stage && d.stage_index === d.stages.length - 1
  const closedOn = closed ? d.stages[d.stage_index]?.entered_at ?? null : null
  const workFirst = openHere > 0 && !!next && next.stage === d.stage
  // with no open task, "next" is the move itself: ready to advance, or the sign-off, or nothing to do here
  const nextMove = d.can_move && d.next_stage
    ? d.signoff?.needed ? `Sign-off: ${signoffText(d.signoff.status)}` : `Ready to move to ${d.next_stage}`
    : `No open task in ${d.stage}`
  // Next up, as a panel: first in the rail while work is open in the stage, after the move otherwise
  // (with no task left and the sign-off panel showing, it would only repeat that panel)
  const nextUpPanel = closed || (!next && d.can_move && d.next_stage && d.signoff?.needed) ? null : (
<section className="panel p-3">
          <H className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-nav-fg"><ChevronRight className="h-3.5 w-3.5" /> Next up</H>
          {next ? (
            <>
              <div className="flex items-start gap-2">
                {(d.can_edit || next.assignee_id === d.me) && (
                  <button type="button" disabled={busy} onClick={() => void tickNext()} aria-label={`Complete ${next.title}`} title="Mark done"
                    className="relative mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border border-input bg-background before:absolute before:-inset-[5px] before:content-[''] hover:border-foreground" />
                )}
                <p className="font-medium">{next.title}</p>
              </div>
              <p className="mt-1 flex items-center gap-3 text-muted-foreground">
                <span className="flex items-center gap-1">{next.assignee ? <UserAvatar name={next.assignee} url={next.assignee_avatar_url} className="h-5 w-5" /> : <UserRound className="h-3.5 w-3.5" />}{next.assignee ?? "Unassigned"}</span>
                {next.due_date && <span className="flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" /><DueDate due={next.due_date} today={d.today} className="inline text-[13px]" /></span>}
              </p>
            </>
          ) : <p className="text-muted-foreground">{nextMove}</p>}
        </section>
  )
  async function tickNext() {
    if (!next) return
    setBusy(true); setErr(null)
    try { await toggleTask(d.id, next.id); toast(`Done: ${next.title}`); await reload() } catch (e) { setErr(e instanceof ApiError ? e.message : "That did not save") } finally { setBusy(false) }
  }
  return (
    <div className="grid grid-cols-1 gap-5 px-5 py-4 xl:grid-cols-[minmax(0,1fr)_280px]">
      <div className="min-w-0 xl:col-start-1 xl:row-start-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {standalone
              ? <h1 className="truncate text-[17px] font-semibold tracking-tight" title={d.name}>{d.name}</h1>
              : <h2 className="truncate text-[17px] font-semibold tracking-tight" title={d.name}>{d.name}</h2>}
            <p className="text-[13px] text-muted-foreground">
              {d.client}{d.vendor_name ? ` · ${d.vendor_name}` : ""}{d.product_name ? ` · ${d.product_name}` : ""}{d.outsourcer_name ? ` · via ${d.outsourcer_name}` : ""} · owner {d.owner_name}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {d.approval && d.approval.stage === d.stage && <ApprovalChip status={d.approval.status} className="px-2 py-1 text-[12px]" />}
            {closed && <span className="rounded-md bg-ok-soft px-2 py-1 text-[12px] font-medium text-ok">Closed{closedOn ? ` on ${fmtDate(closedOn)}` : ""}</span>}
            {/* the project page shows the plan's verdict in its title row instead (one health, not two) */}
            {!closed && !standalone && <StateChip state={d.state} text={stateText({ state: d.state, days_in_stage: d.stages[d.stage_index]?.days ?? null, over_by: d.over_by, target_end_date: d.target_end_date })} />}
            {!standalone && <a href={`/projects/${d.id}/report`} className={buttonVariants({ variant: "ghost", size: "sm" })}>Report</a>}
            {!standalone && <a href={`/projects/${d.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>Open rollout <ExternalLink className="h-3.5 w-3.5" /></a>}
            {onClose && <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close this rollout (Esc)" title="Close (Esc)"><X className="h-4 w-4" /></Button>}
          </div>
        </div>

        {/* the flowchart: one column per stage while they fit (148 px each, so a
            stage name wraps at words, never mid-word); below md it is a plain
            stacked list and nothing folds */}
        {(() => {
          const stacked = typeof window !== "undefined" && !window.matchMedia("(min-width: 768px)").matches
          const capacity = showAll || stacked ? Infinity : !flowWidth ? 6 : Math.max(4, Math.floor((flowWidth + 12) / NODE))   // unmeasured: a safe guess, never an overflow
          const items = fitStages(d.stages.map((st) => st.status), capacity)
          const itemDone = (it: (typeof items)[number]) => it.kind === "done" || (it.kind === "stage" && d.stages[it.index].status === "done")
          return (
            <ol ref={measure} className="mt-4 grid grid-cols-1 items-start gap-2 md:gap-0 md:overflow-x-auto md:pb-2 md:[grid-template-columns:var(--cols)]" style={{ "--cols": `repeat(${items.length}, minmax(${NODE - 12}px, 1fr))` } as CSSProperties} aria-label="Stages">
              {items.map((it, k) => {
                const arrow = k > 0 && (
                  <span className="absolute -left-2 top-[26px] hidden w-4 items-center md:flex" aria-hidden>
                    <span className={cn("h-[1.5px] flex-1", itemDone(items[k - 1]) ? "bg-ok-line" : "bg-input")} />
                    <ArrowRight className={cn("-ml-2 h-3 w-3", itemDone(items[k - 1]) ? "text-ok-line" : "text-input")} />
                  </span>
                )
                if (it.kind !== "stage") {
                  const names = d.stages.slice(it.from, it.to + 1).map((st) => st.name)
                  const open = d.tasks.filter((t) => !t.done && names.includes(t.stage)).length
                  return (
                    <li key={`${it.kind}-${it.from}`} className="relative min-w-0 md:px-2 md:first:pl-0 md:last:pr-0">
                      {arrow}
                      <button type="button" onClick={() => setShowAll(true)} aria-expanded={false}
                        aria-label={`${it.kind === "done" ? "Finished" : "Later"} stages: ${names.join(", ")}. Show every stage`}
                        title={names.join(" › ")}
                        className={cn("block min-h-[58px] w-full rounded-lg border-[1.5px] px-3 py-2 text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                          it.kind === "done" ? "border-ok-line bg-ok-soft hover:bg-ok-soft/70" : "border-dashed border-input bg-card hover:bg-muted")}>
                        <span className={cn("flex items-start gap-1 text-[13px] font-semibold leading-tight", it.kind === "later" && "text-nav-fg")}>
                          {it.kind === "done" && <Check className="mt-px h-3.5 w-3.5 shrink-0 text-ok" />}
                          {it.kind === "done" ? `${names.length} done` : `+${names.length} later`}
                        </span>
                        <span className="mt-1 block truncate text-[12px] text-muted-foreground">{names.join(", ")}</span>
                      </button>
                      {it.kind === "later" && open > 0 && <p className="mt-2 text-[12px] text-muted-foreground">{open} open task{open === 1 ? "" : "s"}</p>}
                    </li>
                  )
                }
                const i = it.index, st = d.stages[i]
                return (
                  <li key={st.name} className="group/node relative min-w-0 md:px-2 md:first:pl-0 md:last:pr-0">
                    {arrow}
                    <div className={cn("min-h-[58px] rounded-lg border-[1.5px] bg-card px-3 py-2",
                      st.status === "done" && "border-ok-line bg-ok-soft",
                      st.status === "current" && cn("ring-[3px]", STATE[d.state].ring),
                      st.status === "next" && "border-dashed border-input")}>
                      <div className={cn("flex items-start gap-1 text-[13px] font-semibold leading-tight", st.status === "next" && "text-nav-fg")}>
                        {st.status === "done" && <Check className="mt-px h-3.5 w-3.5 shrink-0 text-ok" />}<span className="line-clamp-2 [overflow-wrap:normal] hyphens-auto" title={st.name}>{st.name}</span>
                      </div>
                      <div className="mt-1 truncate text-[12px] text-muted-foreground">
                        {st.status === "next" ? (st.sla_days ? `SLA ${st.sla_days} d` : "") : st.status === "done" ? days(st.days) : `${days(st.days)}${st.sla_days ? ` · SLA ${st.sla_days}` : ""}`}
                      </div>
                    </div>
                    {/* every stage carries its own tasks — work happens here, not on the project page; the
                        current stage's list sits full width under the chart, and the last stage takes none */}
                    {st.status !== "current" && <StageTasks d={d} stage={st.name} done={st.status === "done" || closed || i === d.stages.length - 1} reload={reload} onError={setErr} quiet />}
                  </li>
                )
              })}
            </ol>
          )
        })()}
        {!closed && (
          <section className="mt-3 max-w-2xl" aria-label={`Tasks in ${d.stage}`}>
            <H className="text-[12px] font-semibold text-nav-fg">In {d.stage} <span className="font-normal text-muted-foreground">· {openHere ? `${openHere} open` : "nothing open"}</span></H>
            <StageTasks d={d} stage={d.stage} done={d.stage_index === d.stages.length - 1} reload={reload} onError={setErr} />
          </section>
        )}
        {showAll && flowWidth > 0 && d.stages.length * NODE > flowWidth + 12 && (
          <button type="button" onClick={() => setShowAll(false)} className="mt-1 text-[12px] text-muted-foreground hover:text-foreground">Fold stages to fit</button>
        )}
        {/* one place for errors: the Advance section shows its own when it is on screen */}
        {err && !(d.can_move && d.next_stage) && <p className="mt-2 text-[12px] text-destructive" role="alert">{err}</p>}

        {/* the project page draws the full plan chart below; the strip is the flow pane's short version */}
        {!standalone && <TimeStrip d={d} />}
      </div>

      {/* right rail: what to do next, when it's due, how we got here */}
      <aside data-rail className="grid grid-cols-1 content-start gap-4 text-[13px] md:grid-cols-2 xl:col-start-2 xl:row-span-2 xl:row-start-1 xl:grid-cols-1">
        {/* the rail leads with what someone must do now: decide, sign, then the work open in this stage
            (with a tick), and only then the move, which turns secondary while work is open (critique 10 Oct) */}
        {d.approval && d.approval.stage === d.stage && d.approval.status === "pending" && d.can_approve && (
          <section className="rounded-lg bg-warn-soft p-3">
            <H className="mb-1 text-[12px] font-semibold text-nav-fg">Your approval</H>
            <p className="mb-2 text-[13px] text-muted-foreground">The rollout moved to <span className="font-medium text-foreground">{d.stage}</span>. Do you agree with this step?</p>
            <Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment (optional)" aria-label="Approval comment" maxLength={2000} className="h-8 text-[13px]" />
            <div className="mt-2 flex gap-2">
              <Button size="sm" className="flex-1" disabled={busy} onClick={() => decide("approved")}>Approve</Button>
              <Button size="sm" variant="outline" className="flex-1" disabled={busy} onClick={() => decide("declined")}>Decline</Button>
            </div>
          </section>
        )}
        {d.approval && d.approval.stage === d.stage && d.approval.status !== "pending" && d.approval.status !== "superseded" && (
          <p className="text-[13px] text-muted-foreground">{d.stage} {d.approval.status} by {d.approval.decided_by}{d.approval.comment ? ` · ${d.approval.comment}` : ""}</p>
        )}
        {d.signoff?.awaiting_me && (
          <section className="rounded-lg bg-warn-soft p-3">
            <H className="mb-1 flex items-center gap-2 text-[12px] font-semibold text-nav-fg"><FileSignature className="h-3.5 w-3.5" /> Your signature</H>
            <p className="mb-2 text-[13px] text-muted-foreground">The sign-off for {d.name} is waiting for you: review what was delivered, then sign.</p>
            <Link to={`/projects/${d.id}/signoff`} className={cn(buttonVariants({ size: "sm" }), "w-full")}>Review and sign</Link>
          </section>
        )}
        {workFirst && nextUpPanel}
        {d.can_move && d.next_stage && d.signoff?.needed && !d.signoff.awaiting_me && (
          <section className="panel p-3">
            <H className="mb-1 flex items-center gap-2 text-[12px] font-semibold text-nav-fg"><FileSignature className="h-3.5 w-3.5" /> Sign-off before {d.next_stage}</H>
            <p className="mb-2 text-[13px] text-muted-foreground">{signoffText(d.signoff.status)}. The rollout closes once the customer has signed and we have countersigned.</p>
            <Link to={`/projects/${d.id}/signoff`} className={cn(buttonVariants({ size: "sm" }), "w-full")}>{d.signoff.status ? "Open the sign-off" : "Prepare the sign-off"}</Link>
          </section>
        )}
        {d.can_move && d.next_stage && !d.signoff?.needed && (
          <MoveConfirm d={d} quiet={workFirst} heading={H} onMoved={async (text, undo) => { onMoved(text, undo); await reload() }} />
        )}
        {!workFirst && nextUpPanel}
        <section className="panel p-3">
          {/* the target the customer was given (the plan's forecast lives on the project page) */}
          <H className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-nav-fg"><Clock className="h-3.5 w-3.5" /> {closed ? "Closed" : "Target"}</H>
          {closed ? (
            <p><span className="font-medium">{closedOn ? fmtDate(closedOn) : "—"}</span>
              {d.target_end_date && <span className="ml-2 text-muted-foreground">target {fmtDate(d.target_end_date)}</span>}</p>
          ) : d.target_end_date ? (
            <p><span className="font-medium">{fmtDate(d.target_end_date)}</span>
              <span className={cn("ml-2", d.days_left != null && d.days_left < 0 ? "text-bad" : "text-muted-foreground")}>{d.days_left == null ? "" : d.days_left < 0 ? `${-d.days_left} d late` : `${d.days_left} d left`}</span></p>
          ) : <p className="text-muted-foreground">No target date set.</p>}
          <p className="mt-1 text-muted-foreground">{d.documents} document{d.documents === 1 ? "" : "s"} · {d.tasks.filter((t) => t.done).length}/{d.tasks.length} tasks done</p>
        </section>
      </aside>

      {/* who and what happened: under the flowchart on wide screens, after the rail otherwise;
          the project page has its own Team and Notes panels, so it leaves this out */}
      {!standalone && <div className="grid grid-cols-1 content-start gap-4 text-[13px] md:grid-cols-2 xl:col-start-1 xl:row-start-2">
        <section>
          <H className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-nav-fg"><UserRound className="h-3.5 w-3.5" /> Team</H>
          <ul className="grid grid-cols-1 gap-2">
            {d.participants.map((m) => (
              <li key={m.id} className="flex items-center gap-2 text-[13px]">
                <UserAvatar name={m.name} url={m.avatar_url} />
                <span className="min-w-0 flex-1 truncate font-medium">{m.name}</span>
                <span className="text-muted-foreground">{m.role}</span>
              </li>
            ))}
          </ul>
          {!standalone && <a href={`/projects/${d.id}#team`} className="mt-2 inline-block text-[12px] text-primary-text hover:underline">Manage team</a>}
        </section>
        {d.recent_notes.length > 0 && (
          <section className="min-w-0">
            {/* min-w-0 all the way down: a truncated note must not widen the column */}
            <H className="mb-2 text-[12px] font-semibold text-nav-fg">Recent</H>
            <ul className="grid grid-cols-1 min-w-0 gap-2">
              {d.recent_notes.map((n, i) => (
                <li key={i} className="min-w-0 text-[13px]"><span className="font-medium">{n.author}</span> <span className="text-muted-foreground">· {n.stage} · <Ago iso={n.created_at} /></span><div className="truncate text-nav-fg">{n.note}</div></li>
              ))}
            </ul>
          </section>
        )}
      </div>}
    </div>
  )
}

// Phones get the rollout as its own screen with a back button, not a split.

export default function Flow({ user }: { user: User }) {
  const wide = useMedia("(min-width: 768px)")
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
  const [detailError, setDetailError] = useState<string | null>(null)
  // the rollout the pane is for: a slower answer for the previous one is dropped
  const wanted = useRef(selectedId)
  wanted.current = selectedId
  // Ways to look at the portfolio, kept in the URL: the list, a Kanban by stage, or a month.
  const vw = params.get("view")
  // the Gantt reads plans, which are staff-only (the customer cut is the rollout report's)
  const view: View = VIEWS.includes(vw as View) && !(vw === "gantt" && user.kind === "external") ? vw as View : "list"
  useEffect(() => { document.title = `${{ list: "Flow", kanban: "Kanban", gantt: "Gantt", calendar: "Calendar" }[view]} · Odin` }, [view])   // test report UX-17
  const setView = useCallback((v: View) => {
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
    try {
      const x = await flowDetail(id)
      if (wanted.current === id) { setDetail(x); setDetailError(null) }
    } catch (e) {
      if (wanted.current !== id) return
      setDetailError(e instanceof ApiError && (e.status === 404 || e.status === 403) ? "This rollout does not exist, or you are not on it."
        : e instanceof ApiError ? e.message : "Could not load the rollout")
    }
  }, [])
  useEffect(() => { void load() }, [load])
  // the list keeps itself current: a minute's poll while the tab is visible, and on coming back to it
  // (a colleague's move shows without a reload; the open rollout's own pane is left alone)
  useEffect(() => {
    const t = window.setInterval(() => { if (document.visibilityState === "visible") void load() }, 60_000)
    const back = () => void load()
    window.addEventListener("focus", back)
    return () => { window.clearInterval(t); window.removeEventListener("focus", back) }
  }, [load])
  useEffect(() => { setDetailError(null); if (selectedId != null) void loadDetail(selectedId) }, [selectedId, loadDetail])
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
      const was = selectedId
      setSelectedId(null)
      // focus goes back to the row it came from, not to the page
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`button[data-row][data-id="${was}"]`)?.focus())
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [selectedId, setSelectedId])

  async function undoMove(path: string, say: (text: string, bad: boolean) => void = (text, bad) => setNotice({ text, bad })) {
    try {
      const r = await postForm(path)
      const back = r.messages.join(" ")
      say(back || "Move undone", !back.startsWith("Moved back"))
      await Promise.all([load(), selectedId != null ? loadDetail(selectedId) : Promise.resolve()])
    } catch (e) { say(e instanceof ApiError ? e.message : "Could not undo the move", true) }
  }
  // a Kanban drop: the rollout's own detail feeds the same confirm the rail shows
  const [moving, setMoving] = useState<FlowDetail | null>(null)
  async function askMove(r: FlowRow) {
    try { setMoving(await flowDetail(r.id)) } catch (e) { toast(e instanceof ApiError ? e.message : "Could not load the rollout", { tone: "bad" }) }
  }

  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />

  const views = (
    <Segmented label="View" value={view} onChange={setView}
      options={([["list", LayoutList, "List"], ["kanban", KanbanIcon, "Kanban"], ...(user.kind === "external" ? [] : [["gantt", GanttChart, "Gantt"] as const]), ["calendar", CalendarDays, "Calendar"]] as const)
        .map(([v, Icon, label]) => ({ value: v, label, icon: <Icon className="h-3.5 w-3.5" aria-hidden /> }))} />
  )
  const shownRows = data.rows.filter((r) => match(r, filter) && (!stage || r.stage === stage))
  // the same header row, in the same card at the same place, on every view, so the switcher never moves (critique 10 Oct)
  const list = view === "calendar" ? (
    <div className="flex min-h-0 flex-1 flex-col"><FlowHeader data={data} title="Calendar" views={views} /><Suspense fallback={<PageSkeleton />}><Calendar wide={wide} /></Suspense></div>
  ) : view === "gantt" ? (
    <div className="flex min-h-0 flex-1 flex-col">
      <FlowHeader data={data} title="Active rollouts" views={views} filter={filter} setFilter={setFilter} stage={stage} setStage={setStage} />
      <Suspense fallback={<PageSkeleton />}><FlowGantt ids={shownRows.map((r) => r.id)} selectedId={selectedId} onSelect={setSelectedId} /></Suspense>
    </div>
  ) : view === "kanban" ? (
    <div className="flex min-h-0 flex-1 flex-col">
      <FlowHeader data={data} title="Active rollouts" views={views} filter={filter} setFilter={setFilter} stage={stage} setStage={setStage} />
      <Suspense fallback={<PageSkeleton />}>
        <FlowKanban rows={shownRows} columns={stageColumns(data.rows.map((r) => r.stages))} selectedId={selectedId} onSelect={setSelectedId} onMove={(r) => void askMove(r)} onOnly={setStage} />
      </Suspense>
      <Dialog open={moving != null} onOpenChange={(o) => { if (!o) setMoving(null) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Move {moving?.name} to {moving?.next_stage}</DialogTitle><DialogDescription>From {moving?.stage} to {moving?.next_stage}.</DialogDescription></DialogHeader>
          {moving && <MoveConfirm d={moving} confirmNow bare onCancel={() => setMoving(null)} onMoved={async (text, undo) => {
            setMoving(null)
            toast(text, undo ? { action: { label: "Undo", run: () => void undoMove(undo, (t, bad) => toast(t, { tone: bad ? "bad" : "ok" })) } } : {})
            await Promise.all([load(), selectedId != null ? loadDetail(selectedId) : Promise.resolve()])
          }} />}
        </DialogContent>
      </Dialog>
    </div>
  ) : (
    <RolloutList data={data} me={user.id} partner={user.kind === "external"} selectedId={selectedId} onSelect={setSelectedId} filter={filter} setFilter={setFilter} stage={stage} setStage={setStage} group={group}
      header={<FlowHeader data={data} title="Active rollouts" views={views} filter={filter} setFilter={setFilter} group={group} setGroup={setGroup} />} />
  )
  const pane = selectedId != null && (
    <>
              {!wide && (
                <button type="button" onClick={() => setSelectedId(null)} className="flex h-11 items-center gap-1 px-4 text-[14px] font-medium text-primary-text">
                  <ChevronLeft className="h-4 w-4" aria-hidden /> All rollouts
                </button>
              )}
              {notice && (
                <div className={cn("mx-5 mt-3 flex items-center justify-between gap-3 rounded-md px-3 py-2 text-[13px]", notice.bad ? "bg-destructive/10 text-destructive" : "bg-ok-soft text-ok")} role="status">
                  <span>{notice.text}
                    {/* the mover can put it back for five minutes; the server decides */}
                    {notice.undo && <button type="button" onClick={() => void undoMove(notice.undo!)} className="ml-2 font-semibold underline-offset-2 hover:underline">Undo</button>}
                  </span>
                  <button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
                </div>
              )}
              {/* always present, so a screen reader hears which rollout opened; the list keeps the focus */}
              <p className="sr-only" aria-live="polite">{detail && detail.id === selectedId ? `${detail.name} open below: ${detail.stage}${detail.state !== "on_track" ? `, ${STATE[detail.state].label}` : ""}` : ""}</p>
              {detailError ? (
                <div className="flex flex-wrap items-center gap-3 px-5 py-4 text-[13px]" role="alert">
                  <span className="min-w-0 flex-1">{detailError}</span>
                  <Button size="sm" variant="outline" onClick={() => setSelectedId(null)}>Back to all rollouts</Button>
                </div>
              ) : detail && detail.id === selectedId ? (
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
