import { useState, type FormEvent } from "react"
import { Segmented } from "@/components/Segmented"
import { checkbox, field, danger, fieldArea } from "@/lib/ui"
import { Field } from "@/components/ui/field"
import { Badge } from "@/components/ui/badge"
import { Notice } from "@/components/Notice"
import { EmptyState } from "@/components/EmptyState"
import { LoadFailed } from "@/components/LoadFailed"
import { useLoad } from "@/lib/useLoad"
import { askConfirm } from "@/lib/confirm"
import { AlertOctagon, Eye, Gavel, Plus, ShieldAlert, TriangleAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ApiError, decideAIProposal, deleteRaid, raid, saveRaid, type RaidItem, type RaidKind } from "@/lib/api"
import { toast } from "@/lib/toast"
import { AIRaidProposals } from "@/components/AIRaidProposals"
import { cn } from "@/lib/utils"
import { DatePicker } from "@/components/DatePicker"
import { fmtDate, lateBy, localToday } from "@/lib/format"

// The rollout's risks, issues, decisions and blockers: a filterable list, and
// one dialog to add or edit an item. Open blockers and high-impact risks
// count against the rollout's health; items marked for the customer appear
// in the customer's version of the report.
export const RAID_KIND: Record<RaidKind, { label: string; icon: typeof ShieldAlert }> = {
  risk: { label: "Risk", icon: ShieldAlert }, issue: { label: "Issue", icon: TriangleAlert }, blocker: { label: "Blocker", icon: AlertOctagon }, decision: { label: "Decision", icon: Gavel },
}
// amber for high impact, not red: red in Odin means overdue (test report UX-20); the word carries the level
const IMPACT: Record<string, string> = { high: "bg-warn-soft text-warn", medium: "bg-muted text-foreground", low: "bg-muted text-muted-foreground" }
type Draft = Partial<RaidItem> & { kind: RaidKind; title: string }

export function RaidPanel({ projectId, onChanged }: { projectId: number; onChanged?: () => void }) {
  const { data: d, error: failed, reload: load } = useLoad(`raid:${projectId}`, () => raid(projectId))
  const [show, setShow] = useState<"open" | "all">("open")
  const [edit, setEdit] = useState<Draft | null>(null)
  const [opened, setOpened] = useState("")   // an existing item as opened: Save wakes when it differs (review P3-41)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fromAI, setFromAI] = useState<{ suggestion: number; index: number } | null>(null)   // the proposal this new item came from
  const [aiRefresh, setAiRefresh] = useState(0)
  if (!d) return failed ? <LoadFailed what="the register" onRetry={() => void load()} /> : <p className="text-[13px] text-muted-foreground">Loading…</p>
  const today = localToday()
  const list = d.items.filter((i) => show === "all" || i.open)
  const counts = (["blocker", "issue", "risk", "decision"] as RaidKind[]).map((k) => [k, d.items.filter((i) => i.kind === k && i.open).length] as const)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!edit) return
    setBusy(true); setError(null)
    try {
      const r = await saveRaid(projectId, edit, edit.id)
      const newId = (r as { id?: number }).id
      // the item is saved: a failed mark on the AI proposal must not leave the dialog open for a second save (review P3-38)
      if (fromAI && !edit.id && newId) await decideAIProposal(projectId, fromAI.suggestion, fromAI.index, "accepted", newId)
        .then(() => setAiRefresh((n) => n + 1), () => toast("Logged. The AI proposal could not be marked used: dismiss it there.", { tone: "bad" }))
      toast(edit.id ? "Saved to the log" : `${RAID_KIND[edit.kind]?.label ?? "Item"} logged`)
      setEdit(null); setFromAI(null); await load(); onChanged?.()
    } catch (err) { setError(err instanceof ApiError ? err.message : "That did not save") } finally { setBusy(false) }
  }
  async function remove() {
    if (!edit?.id || !(await askConfirm("Delete this item? The log keeps a line that it existed."))) return
    setBusy(true)
    try { await deleteRaid(projectId, edit.id); toast("Deleted from the log"); setEdit(null); await load(); onChanged?.() } catch (err) { setError(err instanceof ApiError ? err.message : "That did not delete") } finally { setBusy(false) }
  }
  const set = (patch: Partial<Draft>) => setEdit((x) => (x ? { ...x, ...patch } : x))
  const open = (x: Draft) => { setOpened(x.id ? JSON.stringify(x) : ""); setEdit(x) }
  const changed = !!edit && (!edit.id || JSON.stringify(edit) !== opened)
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {counts.map(([k, n]) => {
          const K = RAID_KIND[k]
          return <Badge key={k} variant="secondary" className={n ? (k === "blocker" ? "bg-bad-soft text-bad" : k === "issue" ? "bg-warn-soft text-warn" : "bg-muted") : "bg-transparent text-muted-foreground"}><K.icon aria-hidden />{n} {K.label.toLowerCase()}{n === 1 ? "" : "s"}</Badge>
        })}
        <Segmented label="Show" className="ml-auto" value={show} onChange={setShow} options={[{ value: "open", label: "Open" }, { value: "all", label: "All" }]} />
        {d.can_edit && <Button size="sm" onClick={() => { setError(null); setFromAI(null); open({ kind: "risk", title: "", impact: "medium", likelihood: "medium" }) }}><Plus className="h-3.5 w-3.5" /> Add</Button>}
      </div>
      {d.can_edit && (
        <AIRaidProposals projectId={projectId} refresh={aiRefresh} onAdd={(p, suggestion, index) => {
          setError(null); setFromAI({ suggestion, index })
          open({ kind: p.kind, title: p.title, detail: `${p.detail}\n\nFrom the notes: "${p.evidence}"`, impact: p.impact, likelihood: p.likelihood ?? (p.kind === "risk" ? "medium" : null), status: d.statuses[p.kind][0] })
        }} />
      )}
      <ul className="mt-2 divide-y divide-border text-[13px]">
        {list.map((i) => {
          const K = RAID_KIND[i.kind]
          const late = i.open && i.due_date ? lateBy(i.due_date, today) : 0
          return (
            <li key={i.id}>
              <button type="button" disabled={!d.can_edit} onClick={() => { setError(null); setFromAI(null); open({ ...i }) }} className="flex w-full items-start gap-3 py-2 text-left enabled:hover:bg-muted/40">
                <K.icon className={cn("mt-1 h-4 w-4 shrink-0", i.kind === "blocker" && i.open ? "text-bad" : "text-muted-foreground")} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className={cn("block font-medium", !i.open && "text-muted-foreground line-through")}>{i.title}</span>
                  <span className="block text-[12px] text-muted-foreground">{K.label} · {i.status}{i.owner_name && ` · ${i.owner_name}`}{i.stage && ` · ${i.stage}`}{i.resolution && ` · ${i.resolution}`}</span>
                </span>
                {i.customer_visible && <Eye className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="Shown to the customer" />}
                {i.kind !== "decision" && <Badge variant="secondary" className={IMPACT[i.impact]}>{i.impact}</Badge>}
                {i.due_date && <span className={cn("shrink-0 whitespace-nowrap text-[12px]", late > 0 ? "font-medium text-bad" : "text-muted-foreground")}>{late > 0 ? `${late} d late` : fmtDate(i.due_date)}</span>}
              </button>
            </li>
          )
        })}
        {list.length === 0 && <EmptyState as="li">{show === "open" ? (d.can_edit ? "Nothing open. Add a risk before it becomes an issue." : "Nothing open.") : "Nothing recorded yet."}</EmptyState>}
      </ul>

      <Dialog open={edit !== null} onOpenChange={(o) => { if (!o) { setEdit(null); setFromAI(null) } }}>
        <DialogContent className="sm:max-w-lg">
          {edit && (
            <form onSubmit={submit} className="grid grid-cols-1 gap-3">
              <DialogHeader><DialogTitle>{edit.id ? `Edit ${RAID_KIND[edit.kind].label.toLowerCase()}` : "Add to the register"}</DialogTitle><DialogDescription>Risks and issues with high impact, and every open blocker, count against the rollout's health.</DialogDescription></DialogHeader>
              <Segmented label="Kind" full value={edit.kind} onChange={(k) => set({ kind: k, status: d.statuses[k][0] })}
                options={(Object.keys(RAID_KIND) as RaidKind[]).map((k) => ({ value: k, label: RAID_KIND[k].label }))} />
              <Field label="Title"><input className={field} required maxLength={200} value={edit.title} onChange={(e) => set({ title: e.target.value })} autoFocus /></Field>
              <Field label="Detail"><textarea rows={3} maxLength={4000} className={fieldArea} value={edit.detail ?? ""} onChange={(e) => set({ detail: e.target.value })} /></Field>
              <div className="grid grid-cols-2 gap-3">
                {edit.kind !== "decision" && <Field label="Impact"><select className={field} value={edit.impact ?? "medium"} onChange={(e) => set({ impact: e.target.value as RaidItem["impact"] })}>{["low", "medium", "high"].map((x) => <option key={x}>{x}</option>)}</select></Field>}
                {edit.kind === "risk" && <Field label="Likelihood"><select className={field} value={edit.likelihood ?? "medium"} onChange={(e) => set({ likelihood: e.target.value as RaidItem["likelihood"] })}>{["low", "medium", "high"].map((x) => <option key={x}>{x}</option>)}</select></Field>}
                <Field label="Status"><select className={field} value={edit.status ?? d.statuses[edit.kind][0]} onChange={(e) => set({ status: e.target.value })}>{d.statuses[edit.kind].map((x) => <option key={x}>{x}</option>)}</select></Field>
                <Field label="Owner"><select className={field} value={edit.owner_id ?? ""} onChange={(e) => set({ owner_id: e.target.value ? Number(e.target.value) : null })}><option value="">Nobody yet</option>{d.owners.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>
                <Field label="Due"><DatePicker value={edit.due_date ?? ""} onChange={(v) => set({ due_date: v || null })} label="Due" placeholder="No date" className="w-full" /></Field>
                <Field label="Stage"><select className={field} value={edit.stage ?? ""} onChange={(e) => set({ stage: e.target.value || null })}><option value="">Any</option>{d.stages.map((s) => <option key={s}>{s}</option>)}</select></Field>
              </div>
              <Field label={edit.kind === "decision" ? "Decision and rationale" : "Mitigation or resolution"}><input className={field} maxLength={2000} value={edit.resolution ?? ""} onChange={(e) => set({ resolution: e.target.value })} /></Field>
              <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" className={checkbox} checked={!!edit.customer_visible} onChange={(e) => set({ customer_visible: e.target.checked })} /> Show in the customer's report</label>
              {error && <Notice bad>{error}</Notice>}
              <div className="flex gap-2">
                {edit.id && <Button type="button" size="sm" variant="ghost" className={danger} disabled={busy} onClick={remove}>Delete</Button>}
                <span className="ml-auto flex gap-2"><Button type="button" size="sm" variant="ghost" onClick={() => setEdit(null)}>Cancel</Button><Button type="submit" size="sm" loading={busy} disabled={!edit.title.trim() || !changed}>Save</Button></span>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
