import { useState, type FormEvent } from "react"
import { ArrowDown, ArrowUp, Trash2 } from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

// One editor for any stage list — a project's own list or a template in
// Settings. The caller supplies the form routes; the rows and the rules
// (last stage is closed, the current stage cannot go) are the same.
export type StageRow = { id: number; name: string; sla_days: number | null }
export type StagePaths = { add: string; rename: (id: number) => string; move: (id: number) => string; remove: (id: number) => string; sla: string }
// The key a parent should give the editor: any change to the rows remounts it.
export const stageRowsKey = (rows: StageRow[]) => rows.map((s) => `${s.id}:${s.name}:${s.sla_days ?? ""}`).join("|")
type Send = (path: string, fields?: Record<string, string>, confirmText?: string) => Promise<unknown>

export function StageListEditor({ rows, current, busy, send, paths, label = "this project" }: { rows: StageRow[]; current?: string; busy: boolean; send: Send; paths: StagePaths; label?: string }) {
  // Edit state is seeded once; the parent remounts this editor (key) when the
  // rows change, so a save never fights a half-typed rename.
  const [names, setNames] = useState<Record<number, string>>(() => Object.fromEntries(rows.map((s) => [s.id, s.name])))
  const [slas, setSlas] = useState<Record<number, string>>(() => Object.fromEntries(rows.map((s) => [s.id, s.sla_days == null ? "" : String(s.sla_days)])))
  const [newName, setNewName] = useState("")
  function saveSlas(e: FormEvent) {
    e.preventDefault()
    void send(paths.sla, Object.fromEntries(rows.map((s) => [`sla::${s.id}`, slas[s.id] ?? ""])))
  }
  return (
    <div className="grid grid-cols-1 gap-2 text-[13px]">
      {rows.map((s, i) => (
        <div key={s.id} className="flex flex-wrap items-center gap-2">
          <button type="button" disabled={busy || i === 0} onClick={() => send(paths.move(s.id), { direction: "up" })} aria-label={`Move ${s.name} up`} className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "h-7 w-7 px-0")}><ArrowUp className="h-3.5 w-3.5" /></button>
          <button type="button" disabled={busy || i === rows.length - 1} onClick={() => send(paths.move(s.id), { direction: "down" })} aria-label={`Move ${s.name} down`} className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "h-7 w-7 px-0")}><ArrowDown className="h-3.5 w-3.5" /></button>
          <form onSubmit={(e) => { e.preventDefault(); if ((names[s.id] ?? "").trim() && names[s.id] !== s.name) void send(paths.rename(s.id), { name: names[s.id] }) }} className="flex min-w-0 flex-1 items-center gap-2">
            <Input value={names[s.id] ?? ""} onChange={(e) => setNames({ ...names, [s.id]: e.target.value })} aria-label={`Rename stage ${s.name}`} maxLength={80} className={cn("h-7 min-w-32 flex-1 text-[13px]", s.name === current && "font-medium")} />
            {names[s.id] !== undefined && names[s.id] !== s.name && <Button type="submit" size="sm" variant="outline" className="h-7" loading={busy}>Rename</Button>}
          </form>
          <span className="w-16 text-right text-[12px] text-muted-foreground">{s.name === current ? "current" : i === rows.length - 1 ? "closed" : ""}</span>
          <button type="button" disabled={busy || s.name === current || rows.length <= 1} onClick={() => send(paths.remove(s.id), {}, `Delete stage ${s.name} from ${label}?`)} aria-label={`Delete ${s.name}`} className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "ml-1 h-7 w-7 px-0 text-muted-foreground hover:text-bad")}><Trash2 className="h-3.5 w-3.5" /></button>
        </div>
      ))}
      <form onSubmit={(e) => { e.preventDefault(); if (newName.trim()) void send(paths.add, { name: newName.trim() }).then((r) => { if (r) setNewName("") }) }} className="mt-1 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="New stage name" aria-label={`New stage for ${label}`} maxLength={80} className="h-8 w-full text-[13px] sm:w-56" />
        <Button type="submit" size="sm" variant="outline" loading={busy} disabled={!newName.trim()}>Add stage</Button>
        <span className="text-[12px] text-muted-foreground">Added before the last stage.</span>
      </form>
      <form onSubmit={saveSlas} className="mt-1 border-t border-border pt-3">
        <div className="mb-2 text-[12px] font-semibold text-nav-fg">SLA days per stage</div>
        <div className="flex flex-wrap gap-2">
          {rows.map((s) => (
            <label key={s.id} className="flex items-center gap-2 text-[13px]">
              <span className="max-w-32 truncate text-muted-foreground" title={s.name}>{s.name}</span>
              <Input type="number" min={1} value={slas[s.id] ?? ""} onChange={(e) => setSlas({ ...slas, [s.id]: e.target.value })} aria-label={`SLA days for ${s.name} in ${label}`} placeholder="—" className="h-7 w-16 text-[13px]" />
            </label>
          ))}
        </div>
        <Button type="submit" size="sm" variant="outline" className="mt-2" loading={busy}>Save SLAs</Button>
      </form>
    </div>
  )
}
