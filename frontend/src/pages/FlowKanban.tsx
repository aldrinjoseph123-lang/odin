import { useEffect, useMemo, useState } from "react"
import { CalendarClock, ChevronLeft, ChevronRight, CircleDashed, Clock, Columns3, GripVertical, ListChecks, MoreHorizontal, UserRound } from "lucide-react"
import { Kanban, KanbanBoard, KanbanColumn, KanbanColumnContent, KanbanItem, KanbanItemHandle, KanbanOverlay } from "@/components/reui/kanban"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { buttonVariants } from "@/components/ui/button"
import { StateChip } from "@/components/StateChip"
import { TeamStack } from "@/components/TeamStack"
import { UserAvatar } from "@/components/UserAvatar"
import { STATE } from "@/lib/state"
import { stateText, fmtDate } from "@/lib/format"
import { boardColumns, canDrag, columnOf, dropRefusal } from "@/lib/board"
import { toast } from "@/lib/toast"
import type { FlowRow } from "@/lib/api"
import { cn } from "@/lib/utils"

// The Flow as a Kanban (13 Oct 2026, the user's call, after the ReUI
// "kanban-board-2" reference): a column per stage in the shared order, a card
// per rollout. A card may be dragged only to its own next stage; the drop opens
// the same confirm as the detail's "Move to" (MoveConfirm), and the server
// decides. Which columns are hidden or folded is remembered per browser.

const HIDDEN = "odin.kanban.hidden", FOLDED = "odin.kanban.folded"
const load = (key: string): string[] | null => { try { const v = localStorage.getItem(key); return v ? JSON.parse(v) as string[] : null } catch { return null } }
const save = (key: string, v: string[]) => { try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* private mode */ } }

export default function FlowKanban({ rows, columns, selectedId, onSelect, onMove, onOnly }: {
  rows: FlowRow[]; columns: string[]; selectedId: number | null
  onSelect: (id: number) => void
  onMove: (r: FlowRow) => void          // a drop on the next stage: the page asks to confirm
  onOnly: (stage: string) => void       // "Show only this stage" (the Flow's stage filter)
}) {
  const [hidden, setHidden] = useState<string[]>(() => load(HIDDEN) ?? [])
  // the last stage holds closed rollouts: folded until opened
  const [folded, setFolded] = useState<string[]>(() => load(FOLDED) ?? columns.slice(-1))
  useEffect(() => save(HIDDEN, hidden), [hidden])
  useEffect(() => save(FOLDED, folded), [folded])
  const shown = useMemo(() => columns.filter((c) => !hidden.includes(c)), [columns, hidden])
  const byId = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows])
  const base = useMemo(() => boardColumns(rows, shown), [rows, shown])
  const [value, setValue] = useState(base)
  useEffect(() => setValue(base), [base])
  const [active, setActive] = useState<FlowRow | null>(null)

  // the board previews a card wherever it is dragged; keep only its own column and its next stage
  function preview(next: Record<string, FlowRow[]>) {
    if (!active) return
    const at = columnOf(next, active.id)
    if (at && (at === active.stage || !dropRefusal(active, at))) setValue(at === active.stage ? base : next)
  }
  function commit(next: Record<string, FlowRow[]>) {
    const r = active
    setActive(null); setValue(base)        // the card stays put until the server has moved it
    if (!r) return
    const at = columnOf(next, r.id)
    if (at && at !== r.stage) onMove(r)
  }
  const toggle = (list: string[], set: (v: string[]) => void, c: string) => set(list.includes(c) ? list.filter((x) => x !== c) : [...list, c])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 px-5 pb-3">
        <p className="text-[12px] text-muted-foreground">Drag a card by its handle to its next stage; Space lifts it from the keyboard, arrows move it, Space drops.</p>
        <Popover>
          <PopoverTrigger className={cn(buttonVariants({ variant: "outline", size: "sm" }), "ml-auto")}><Columns3 className="h-3.5 w-3.5" /> Columns{hidden.length ? ` · ${hidden.length} hidden` : ""}</PopoverTrigger>
          <PopoverContent align="end" className="w-60 p-3">
            <fieldset className="grid gap-1 text-[13px]">
              <legend className="mb-1 text-[12px] font-semibold text-nav-fg">Stages on the board</legend>
              {columns.map((c) => (
                <label key={c} className="flex items-center gap-2 rounded-md px-1 py-1 hover:bg-muted">
                  <input type="checkbox" checked={!hidden.includes(c)} onChange={() => toggle(hidden, setHidden, c)} className="h-3.5 w-3.5 accent-primary" />{c}
                </label>
              ))}
            </fieldset>
            {hidden.length > 0 && <button type="button" onClick={() => setHidden([])} className="mt-2 text-[12px] font-medium text-primary-text hover:underline">Show every stage</button>}
          </PopoverContent>
        </Popover>
      </div>
      <Kanban value={value} onValueChange={preview} onValueCommit={commit} getItemValue={(r: FlowRow) => String(r.id)} restoreOnCancel
        onDragStart={(e) => setActive(byId.get(Number(e.active.id)) ?? null)}
        onDragCancel={() => { setActive(null); setValue(base) }}
        onDragEnd={(e) => {
          // a refused drop says why (the preview never showed the card there)
          if (!active || !e.over) return
          const over = String(e.over.id)
          const at = shown.includes(over) ? over : columnOf(base, Number(over))
          const why = at && at !== active.stage ? dropRefusal(active, at) : null
          if (why) toast(why, { tone: "bad" })
        }}>
        <KanbanBoard className="flex min-h-0 flex-1 gap-3 overflow-x-auto px-5 pb-4" aria-label="Rollouts by stage">
          {shown.map((c) => {
            const items = value[c] ?? []
            const target = active ? (c === active.next_stage && !dropRefusal(active, c)) : false
            const blocked = !!active && c !== active.stage && !target
            const trouble = items.filter((r) => r.state !== "on_track").length
            if (folded.includes(c)) return (
              <KanbanColumn key={c} value={c} disabled
                className={cn("w-11 shrink-0 items-center gap-2 rounded-xl border border-border bg-muted/40 py-3 opacity-100", target && "border-primary-text ring-2 ring-primary/40")}>
                <button type="button" onClick={() => toggle(folded, setFolded, c)} aria-label={`Show the ${c} column, ${items.length} rollouts`} className="flex flex-col items-center gap-2 text-[12px] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 rounded-md">
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                  <span className="font-medium [writing-mode:vertical-rl]">{c}</span>
                  <span className="tabular-nums text-muted-foreground">{items.length}</span>
                </button>
                <KanbanColumnContent value={c} className="hidden" />
              </KanbanColumn>
            )
            return (
              <KanbanColumn key={c} value={c} disabled
                className={cn("w-[300px] shrink-0 rounded-xl border border-border bg-muted/40 transition-colors",
                  target && "border-primary-text bg-accent/40 ring-2 ring-primary/40", blocked ? "opacity-60" : "opacity-100")}>
                <div className="flex items-center gap-2 px-3 py-2">
                  <CircleDashed className={cn("h-3.5 w-3.5", trouble ? "text-warn" : "text-muted-foreground")} aria-hidden />
                  <h2 className="min-w-0 truncate text-[13px] font-semibold" title={c}>{c}</h2>
                  <span className="rounded-md bg-card px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">{items.length}</span>
                  {target && <span className="text-[11px] font-medium text-primary-text">Drop to move here</span>}
                  <button type="button" onClick={() => toggle(folded, setFolded, c)} aria-label={`Fold the ${c} column`} className="ml-auto rounded-md p-1 text-muted-foreground hover:bg-card hover:text-foreground"><ChevronLeft className="h-3.5 w-3.5" /></button>
                  <DropdownMenu>
                    <DropdownMenuTrigger aria-label={`${c} column menu`} className="rounded-md p-1 text-muted-foreground hover:bg-card hover:text-foreground"><MoreHorizontal className="h-3.5 w-3.5" /></DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => onOnly(c)}>Show only this stage</DropdownMenuItem>
                      <DropdownMenuItem onClick={() => toggle(folded, setFolded, c)}>Fold the column</DropdownMenuItem>
                      <DropdownMenuItem onClick={() => toggle(hidden, setHidden, c)}>Hide from the board</DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <KanbanColumnContent value={c} render={<ul />} className="min-h-24 gap-2 overflow-y-auto px-2 pb-2" aria-label={`${c}, ${items.length} rollouts`}>
                  {items.map((r) => <Card key={r.id} r={r} selected={r.id === selectedId} onSelect={onSelect} />)}
                  {items.length === 0 && <li className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-[12px] text-muted-foreground">{target ? "Drop here" : "No rollouts"}</li>}
                </KanbanColumnContent>
              </KanbanColumn>
            )
          })}
        </KanbanBoard>
        <KanbanOverlay>{({ value: id }) => { const r = byId.get(Number(id)); return r ? <Card r={r} selected={false} onSelect={() => {}} lifted /> : null }}</KanbanOverlay>
      </Kanban>
    </div>
  )
}

function Card({ r, selected, onSelect, lifted }: { r: FlowRow; selected: boolean; onSelect: (id: number) => void; lifted?: boolean }) {
  const movable = canDrag(r)
  const late = r.late_tasks > 0
  return (
    <KanbanItem value={String(r.id)} disabled={!movable} render={<li />} role="listitem" tabIndex={-1} aria-roledescription={undefined}
      className={cn("group/card rounded-lg border border-border bg-card p-3 text-[13px] shadow-card opacity-100 transition-shadow",
        selected && "border-primary-text ring-2 ring-primary/30", lifted && "rotate-1 shadow-pop")}>
      <div className="flex items-start gap-2">
        {movable ? (
          <KanbanItemHandle render={<button type="button" aria-label={`Move ${r.name} to ${r.next_stage}`} title={`Drag to ${r.next_stage}`} />}
            className="-ml-1 mt-0.5 rounded-md p-0.5 text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50">
            <GripVertical className="h-3.5 w-3.5" aria-hidden />
          </KanbanItemHandle>
        ) : <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", r.state === "on_track" ? "bg-transparent" : STATE[r.state].dot)} aria-hidden />}
        <button type="button" onClick={() => onSelect(r.id)} data-card={r.id} className="min-w-0 flex-1 text-left font-medium outline-none hover:underline focus-visible:underline" title={`${r.name} · ${r.client}`}>
          <span className="line-clamp-2">{r.name}</span>
        </button>
      </div>
      <ul className="mt-2 grid gap-1.5 text-[12px] text-muted-foreground">
        <li className="flex items-center gap-2"><UserRound className="h-3.5 w-3.5 shrink-0" aria-hidden /><span className="sr-only">Owner: </span>
          <UserAvatar name={r.owner_name} url={r.team[0]?.avatar_url} className="h-5 w-5" textClass="text-[9px]" /><span className="truncate text-foreground">{r.owner_name}</span></li>
        <li className="flex items-center gap-2"><CalendarClock className="h-3.5 w-3.5 shrink-0" aria-hidden /><span className="truncate">{r.client}{r.target_end_date && ` · target ${fmtDate(r.target_end_date)}`}</span></li>
        {r.next_task && <li className="flex items-center gap-2"><ListChecks className="h-3.5 w-3.5 shrink-0" aria-hidden /><span className="truncate">{r.next_task.title}</span></li>}
      </ul>
      {r.state !== "on_track" && <StateChip state={r.state} text={stateText(r)} className="mt-2 inline-block" />}
      <div className="mt-2 flex items-center gap-3 border-t border-border pt-2 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1" title={`${r.open_tasks} open of ${r.total_tasks} tasks`}><ListChecks className="h-3 w-3" aria-hidden />{r.open_tasks}/{r.total_tasks}</span>
        {late && <span className="font-medium text-bad">{r.late_tasks} late</span>}
        {r.approval === "pending" && <span className="font-medium text-warn">Awaiting approval</span>}
        <TeamStack people={r.team} className="ml-auto flex" avatarClass="h-5 w-5" />
        <span className="flex items-center gap-1 tabular-nums" title="Days in this stage"><Clock className="h-3 w-3" aria-hidden />{r.days_in_stage == null ? "—" : `${Math.round(r.days_in_stage)}d`}</span>
      </div>
    </KanbanItem>
  )
}
