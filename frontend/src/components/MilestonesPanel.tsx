import { useState, type FormEvent } from "react"
import { Check, Diamond, Eye, Plus, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field } from "@/components/ui/field"
import { DatePicker } from "@/components/DatePicker"
import { EmptyState } from "@/components/EmptyState"
import { LoadFailed } from "@/components/LoadFailed"
import { Notice } from "@/components/Notice"
import { Segmented } from "@/components/Segmented"
import { ApiError, deleteMilestone, milestones, saveMilestone, type Milestone } from "@/lib/api"
import { askConfirm } from "@/lib/confirm"
import { fmtDate, lateBy, localToday } from "@/lib/format"
import { toast } from "@/lib/toast"
import { checkbox, danger, field } from "@/lib/ui"
import { useAction } from "@/lib/useAction"
import { useLoad } from "@/lib/useLoad"
import { cn } from "@/lib/utils"

// The rollout's milestones: dated commitments (go-live, UAT sign-off) that are
// reached or missed. Whoever manages the rollout's tasks adds, edits and marks
// one reached; the project manager deletes. A milestone marked for the customer
// shows on the customer's report and calendar; the rest stay with the team.
type Draft = { id?: number; name: string; date: string; stage: string | null; customer_visible: boolean }

export function MilestonesPanel({ projectId, onChanged }: { projectId: number; onChanged?: () => void }) {
  const { data: d, error: failed, reload } = useLoad(`milestones:${projectId}`, () => milestones(projectId))
  const [show, setShow] = useState<"open" | "all">("open")
  const [edit, setEdit] = useState<Draft | null>(null)
  const [opened, setOpened] = useState("")   // an existing milestone as opened: Save wakes when it differs
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const after = async () => { await reload(); onChanged?.() }
  const { busy, act } = useAction(after)
  if (!d) return failed ? <LoadFailed what="the milestones" onRetry={() => void reload()} /> : <p className="text-[13px] text-muted-foreground">Loading…</p>
  const today = localToday()
  const list = d.items.filter((m) => show === "all" || !m.done)
  const missed = d.items.filter((m) => m.missed).length
  const reached = d.items.filter((m) => m.done).length

  const open = (m: Draft) => { setError(null); setOpened(m.id ? JSON.stringify(m) : ""); setEdit(m) }
  const changed = !!edit && (!edit.id || JSON.stringify(edit) !== opened)
  const set = (patch: Partial<Draft>) => setEdit((x) => (x ? { ...x, ...patch } : x))
  const body = (m: Draft) => ({ name: m.name.trim(), date: m.date, stage: m.stage, customer_visible: m.customer_visible })

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!edit) return
    setError(null); setSaving(true)
    try {
      await saveMilestone(projectId, body(edit), edit.id)
      toast(edit.id ? "Milestone saved" : "Milestone added")
      setEdit(null); await after()
    } catch (err) { setError(err instanceof ApiError ? err.message : "That did not save") } finally { setSaving(false) }
  }
  async function remove() {
    if (!edit?.id || !(await askConfirm("Delete this milestone? The log keeps a line that it existed."))) return
    try { await deleteMilestone(projectId, edit.id); toast("Milestone deleted"); setEdit(null); await after() }
    catch (err) { setError(err instanceof ApiError ? err.message : "That did not delete") }
  }
  const reach = (m: Milestone) => void act(() => saveMilestone(projectId, { name: m.name, date: m.date, stage: m.stage, customer_visible: m.customer_visible, done: !m.done }, m.id),
    ).then((ok) => { if (ok) toast(m.done ? `${m.name}: open again` : `${m.name}: reached`) })

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className={missed ? "bg-warn-soft text-warn" : "bg-transparent text-muted-foreground"}>{missed} missed</Badge>
        <Badge variant="secondary" className="bg-transparent text-muted-foreground">{reached} of {d.items.length} reached</Badge>
        <Segmented label="Show milestones" className="ml-auto" value={show} onChange={setShow} options={[{ value: "open", label: "Open" }, { value: "all", label: "All" }]} />
        {d.can_edit && <Button size="sm" onClick={() => open({ name: "", date: "", stage: null, customer_visible: false })}><Plus className="h-3.5 w-3.5" /> Add</Button>}
      </div>
      <ul className="mt-2 divide-y divide-border text-[13px]">
        {list.map((m) => {
          const late = m.done ? 0 : lateBy(m.date, today)
          return (
            <li key={m.id} className="flex items-center gap-1">
              <button type="button" disabled={!d.can_edit} onClick={() => open({ id: m.id, name: m.name, date: m.date, stage: m.stage, customer_visible: m.customer_visible })}
                className="flex min-w-0 flex-1 items-start gap-3 py-2 text-left enabled:hover:bg-muted/40">
                <Diamond className={cn("mt-1 h-4 w-4 shrink-0", m.done ? "fill-current text-ok" : late > 0 ? "text-warn" : "text-muted-foreground")} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className={cn("block font-medium", m.done && "text-muted-foreground line-through")}>{m.name}</span>
                  <span className="block text-[12px] text-muted-foreground">{m.done ? `Reached ${fmtDate(m.done_at!.slice(0, 10))}` : late > 0 ? "Missed" : "Ahead"}{m.stage && ` · ${m.stage}`}</span>
                </span>
                {m.customer_visible && <Eye className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="Shown to the customer" />}
                <span className={cn("shrink-0 whitespace-nowrap text-[12px]", late > 0 ? "font-medium text-warn" : "text-muted-foreground")}>{late > 0 ? `${late} d late · ${fmtDate(m.date)}` : fmtDate(m.date)}</span>
              </button>
              {d.can_edit && (
                <Button type="button" size="sm" variant="ghost" className="h-7 shrink-0 px-2" aria-disabled={busy || undefined} onClick={() => { if (!busy) reach(m) }}
                  aria-label={m.done ? `Reopen ${m.name}` : `Mark ${m.name} reached`} title={m.done ? "Reopen" : "Mark reached"}>
                  {m.done ? <RotateCcw className="h-3.5 w-3.5" /> : <Check className="h-3.5 w-3.5" />}
                </Button>
              )}
            </li>
          )
        })}
        {list.length === 0 && <EmptyState as="li">{show === "open" ? (d.can_edit ? "Nothing open. Add the dates the customer was promised." : "Nothing open.") : "No milestones yet."}</EmptyState>}
      </ul>

      <Dialog open={edit !== null} onOpenChange={(o) => { if (!o) setEdit(null) }}>
        <DialogContent className="sm:max-w-md">
          {edit && (
            <form onSubmit={submit} className="grid grid-cols-1 gap-3">
              <DialogHeader><DialogTitle>{edit.id ? "Edit milestone" : "Add a milestone"}</DialogTitle><DialogDescription>A dated commitment. Odin raises an alert when its day passes and it is not marked reached.</DialogDescription></DialogHeader>
              <Field label="Name"><input className={field} required maxLength={200} value={edit.name} onChange={(e) => set({ name: e.target.value })} autoFocus /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Date"><DatePicker value={edit.date} onChange={(v) => set({ date: v })} label="Date" placeholder="Pick a day" clearable={false} className="w-full" /></Field>
                <Field label="Stage"><select className={field} value={edit.stage ?? ""} onChange={(e) => set({ stage: e.target.value || null })}><option value="">Any</option>{d.stages.map((s) => <option key={s}>{s}</option>)}</select></Field>
              </div>
              <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" className={checkbox} checked={edit.customer_visible} onChange={(e) => set({ customer_visible: e.target.checked })} /> Show to the customer (their report and calendar)</label>
              {error && <Notice bad>{error}</Notice>}
              <div className="flex gap-2">
                {edit.id && d.can_delete && <Button type="button" size="sm" variant="ghost" className={danger} onClick={() => void remove()}>Delete</Button>}
                <span className="ml-auto flex gap-2"><Button type="button" size="sm" variant="ghost" onClick={() => setEdit(null)}>Cancel</Button><Button type="submit" size="sm" loading={saving} disabled={!edit.name.trim() || !edit.date || !changed}>Save</Button></span>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
