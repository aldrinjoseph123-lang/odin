import { useState, type FormEvent } from "react"
import { PanelTitle } from "@/components/PanelTitle"
import { Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { MoveArrows } from "@/components/MoveArrows"
import { DragReorder, DragRow } from "@/components/DragReorder"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { TemplateTasksEditor } from "@/components/TemplateTasksEditor"
import { checkbox } from "@/lib/ui"

// One editor for any stage list — a project's own list or a template in
// Settings. The caller supplies the form routes; the rows and the rules
// (last stage is closed, the current stage cannot go) are the same.
// gate_tasks / required_docs: what the stage asks before a rollout leaves it (services/gates.py)
export type StageRow = { id: number; name: string; sla_days: number | null; gate_tasks?: boolean; required_docs?: string[] }
export type StagePaths = { add: string; rename: (id: number) => string; move: (id: number) => string; remove: (id: number) => string; sla: string; gates?: string }
// The key a parent should give the editor: a rename, an SLA or an added or
// removed stage remounts it. Order is left out, so a reorder keeps the rows and
// the keyboard focus on the arrow that was pressed (review P2-41).
export const stageRowsKey = (rows: StageRow[]) => [...rows].sort((a, b) => a.id - b.id).map((s) => `${s.id}:${s.name}:${s.sla_days ?? ""}:${s.gate_tasks ? 1 : 0}:${(s.required_docs ?? []).join(",")}`).join("|")
type Send = (path: string, fields?: Record<string, string>, confirmText?: string) => Promise<unknown>

// templateId: a template's list also edits the tasks its stages bring (TemplateTasksEditor)
export function StageListEditor({ rows, current, busy, send, paths, label = "this rollout", categories = [], templateId }: { rows: StageRow[]; current?: string; busy: boolean; send: Send; paths: StagePaths; label?: string; categories?: string[]; templateId?: number }) {
  // Edit state is seeded once; the parent remounts this editor (key) when the
  // rows change, so a save never fights a half-typed rename.
  const [names, setNames] = useState<Record<number, string>>(() => Object.fromEntries(rows.map((s) => [s.id, s.name])))
  const [slas, setSlas] = useState<Record<number, string>>(() => Object.fromEntries(rows.map((s) => [s.id, s.sla_days == null ? "" : String(s.sla_days)])))
  const [gates, setGates] = useState<Record<number, { tasks: boolean; docs: string[] }>>(() => Object.fromEntries(rows.map((s) => [s.id, { tasks: !!s.gate_tasks, docs: s.required_docs ?? [] }])))
  const [newName, setNewName] = useState("")
  // the last stage is the finish line: a rollout never leaves it forward, so it asks nothing
  const gated = rows.slice(0, -1)
  const gatesChanged = gated.some((s) => gates[s.id].tasks !== !!s.gate_tasks || gates[s.id].docs.join("\n") !== (s.required_docs ?? []).join("\n"))
  const toggleDoc = (id: number, c: string) => setGates({ ...gates, [id]: { ...gates[id], docs: gates[id].docs.includes(c) ? gates[id].docs.filter((x) => x !== c) : [...gates[id].docs, c] } })
  function saveGates(e: FormEvent) {
    e.preventDefault()
    if (paths.gates) void send(paths.gates, Object.fromEntries(gated.flatMap((s) => [[`gate::${s.id}`, gates[s.id].tasks ? "1" : ""], [`docs::${s.id}`, gates[s.id].docs.join("\n")]])))
  }
  const slasChanged = rows.some((s) => (slas[s.id] ?? "") !== (s.sla_days == null ? "" : String(s.sla_days)))
  function saveSlas(e: FormEvent) {
    e.preventDefault()
    void send(paths.sla, Object.fromEntries(rows.map((s) => [`sla::${s.id}`, slas[s.id] ?? ""])))
  }
  return (
    <div className="grid grid-cols-1 gap-2 text-[13px]">
      {/* a drop is saved as the one-step moves the arrows post; the first refusal stops the rest */}
      <DragReorder ids={rows.map((s) => s.id)} onReorder={async (id, steps) => { for (const direction of steps) if (!(await send(paths.move(id), { direction }))) break }}>
      {rows.map((s, i) => (
        <DragRow key={s.id} id={s.id} className="flex flex-wrap items-center gap-2">
          <MoveArrows name={s.name} first={i === 0} last={i === rows.length - 1} busy={busy} onMove={(direction) => send(paths.move(s.id), { direction })} />
          <form onSubmit={(e) => { e.preventDefault(); if ((names[s.id] ?? "").trim() && names[s.id] !== s.name) void send(paths.rename(s.id), { name: names[s.id] }) }} className="flex min-w-0 flex-1 items-center gap-2">
            <Input value={names[s.id] ?? ""} onChange={(e) => setNames({ ...names, [s.id]: e.target.value })} aria-label={`Rename stage ${s.name}`} maxLength={80} className={cn("h-7 min-w-32 flex-1 text-[13px]", s.name === current && "font-medium")} />
            {names[s.id] !== undefined && names[s.id] !== s.name && <Button type="submit" size="sm" variant="outline" className="h-7" loading={busy}>Rename</Button>}
          </form>
          <span className="w-16 text-right text-[12px] text-muted-foreground">{s.name === current ? "current" : i === rows.length - 1 ? "closed" : ""}</span>
          <Button type="button" variant="ghost" size="icon-sm" className="ml-1 text-muted-foreground hover:text-destructive" disabled={busy || s.name === current || rows.length <= 1} aria-label={`Delete ${s.name}`}
            onClick={() => send(paths.remove(s.id), {}, `Delete stage ${s.name} from ${label}? ${current !== undefined ? "Its tasks move to the current stage, and its planned dates and baseline are removed." : "Rollouts already started keep their own copy."}`)}><Trash2 className="size-3.5" /></Button>
        </DragRow>
      ))}
      </DragReorder>
      <form onSubmit={(e) => { e.preventDefault(); if (newName.trim()) void send(paths.add, { name: newName.trim() }).then((r) => { if (r) setNewName("") }) }} className="mt-1 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="New stage name" aria-label={`New stage for ${label}`} maxLength={80} className="h-8 w-full text-[13px] sm:w-56" />
        <Button type="submit" size="sm" variant="outline" loading={busy} disabled={!newName.trim()}>Add stage</Button>
        <span className="text-[12px] text-muted-foreground">Added before the last stage.</span>
      </form>
      <form onSubmit={saveSlas} className="mt-1 border-t border-border pt-3">
        <PanelTitle n={false} className="mb-2">SLA days per stage</PanelTitle>
        <div className="flex flex-wrap gap-2">
          {rows.map((s) => (
            <label key={s.id} className="flex items-center gap-2 text-[13px]">
              <span className="max-w-32 truncate text-muted-foreground" title={s.name}>{s.name}</span>
              <Input type="number" min={1} value={slas[s.id] ?? ""} onChange={(e) => setSlas({ ...slas, [s.id]: e.target.value })} aria-label={`SLA days for ${s.name} in ${label}`} placeholder="—" className="h-7 w-16 text-[13px]" />
            </label>
          ))}
        </div>
        <Button type="submit" size="sm" className="mt-2" loading={busy} disabled={!slasChanged}>Save SLAs</Button>
      </form>
      {paths.gates && gated.length > 0 && (
        <form onSubmit={saveGates} className="mt-1 border-t border-border pt-3">
          <PanelTitle n={false} className="mb-1">Before leaving this stage</PanelTitle>
          <p className="mb-2 text-[12px] text-muted-foreground">A rollout cannot move on until these are met. An admin, and the project manager while Settings › Workflow allows it, may move past with a reason.</p>
          <div className="grid grid-cols-1 gap-2">
            {gated.map((s) => (
              <fieldset key={s.id} className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <legend className="sr-only">Before leaving {s.name}</legend>
                <span className="w-32 truncate text-muted-foreground" title={s.name} aria-hidden>{s.name}</span>
                <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" className={checkbox} checked={gates[s.id].tasks} onChange={(e) => setGates({ ...gates, [s.id]: { ...gates[s.id], tasks: e.target.checked } })} aria-label={`All tasks done before leaving ${s.name}`} />All tasks done</label>
                {categories.map((c) => (
                  <label key={c} className="flex items-center gap-2 text-[13px]"><input type="checkbox" className={checkbox} checked={gates[s.id].docs.includes(c)} onChange={() => toggleDoc(s.id, c)} aria-label={`${c} on file before leaving ${s.name}`} />{c}</label>
                ))}
              </fieldset>
            ))}
          </div>
          <Button type="submit" size="sm" className="mt-2" loading={busy} disabled={!gatesChanged}>Save what each stage asks</Button>
        </form>
      )}
      {templateId !== undefined && <TemplateTasksEditor templateId={templateId} stages={rows} label={label} />}
    </div>
  )
}
