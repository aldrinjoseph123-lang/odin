import { useCallback, useEffect, useState, type FormEvent } from "react"
import { AlertOctagon, Eye, Gavel, Plus, ShieldAlert, TriangleAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ApiError, decideAIProposal, deleteRaid, raid, saveRaid, type RaidData, type RaidItem, type RaidKind } from "@/lib/api"
import { AIRaidProposals } from "@/components/AIRaidProposals"
import { cn } from "@/lib/utils"
import { fmtDate, lateBy, localToday } from "@/lib/format"

// The rollout's risks, issues, decisions and blockers: a filterable list, and
// one dialog to add or edit an item. Open blockers and high-impact risks
// count against the rollout's health; items marked for the customer appear
// in the customer's version of the report.
export const RAID_KIND: Record<RaidKind, { label: string; icon: typeof ShieldAlert }> = {
  risk: { label: "Risk", icon: ShieldAlert }, issue: { label: "Issue", icon: TriangleAlert }, blocker: { label: "Blocker", icon: AlertOctagon }, decision: { label: "Decision", icon: Gavel },
}
// amber for high impact, not red: red in Odin means overdue (test report UX-20); the word carries the level
const IMPACT: Record<string, string> = { high: "bg-warn-soft font-semibold text-warn", medium: "bg-muted text-foreground", low: "bg-muted text-muted-foreground" }
const field = "h-8 w-full rounded-md border border-input bg-background px-2 text-[13px]"
type Draft = Partial<RaidItem> & { kind: RaidKind; title: string }

export function RaidPanel({ projectId, onChanged }: { projectId: number; onChanged?: () => void }) {
  const [d, setD] = useState<RaidData | null>(null)
  const [show, setShow] = useState<"open" | "all">("open")
  const [edit, setEdit] = useState<Draft | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fromAI, setFromAI] = useState<{ suggestion: number; index: number } | null>(null)   // the proposal this new item came from
  const [aiRefresh, setAiRefresh] = useState(0)
  const load = useCallback(() => raid(projectId).then(setD), [projectId])
  useEffect(() => { void load() }, [load])
  if (!d) return <p className="text-[13px] text-muted-foreground">Loading…</p>
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
      if (fromAI && !edit.id && newId) { await decideAIProposal(projectId, fromAI.suggestion, fromAI.index, "accepted", newId); setAiRefresh((n) => n + 1) }
      setEdit(null); setFromAI(null); await load(); onChanged?.()
    } catch (err) { setError(err instanceof ApiError ? err.message : "That did not save") } finally { setBusy(false) }
  }
  async function remove() {
    if (!edit?.id || !confirm("Delete this item? The log keeps a line that it existed.")) return
    setBusy(true)
    try { await deleteRaid(projectId, edit.id); setEdit(null); await load(); onChanged?.() } catch (err) { setError(err instanceof ApiError ? err.message : "That did not delete") } finally { setBusy(false) }
  }
  const set = (patch: Partial<Draft>) => setEdit((x) => (x ? { ...x, ...patch } : x))
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {counts.map(([k, n]) => {
          const K = RAID_KIND[k]
          return <span key={k} className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px]", n && (k === "blocker" ? "bg-bad-soft text-bad" : k === "issue" ? "bg-warn-soft text-warn" : "bg-muted"), !n && "text-muted-foreground")}><K.icon className="h-3 w-3" aria-hidden />{n} {K.label.toLowerCase()}{n === 1 ? "" : "s"}</span>
        })}
        <span className="ml-auto flex rounded-full bg-muted p-0.5" role="group" aria-label="Show">
          {(["open", "all"] as const).map((v) => <button key={v} type="button" aria-pressed={show === v} onClick={() => setShow(v)} className={cn("h-6 rounded-full px-2.5 text-[12px]", show === v ? "bg-card shadow-card" : "text-muted-foreground")}>{v === "open" ? "Open" : "All"}</button>)}
        </span>
        {d.can_edit && <Button size="sm" className="rounded-full" onClick={() => { setError(null); setFromAI(null); setEdit({ kind: "risk", title: "", impact: "medium", likelihood: "medium" }) }}><Plus className="h-3.5 w-3.5" /> Add</Button>}
      </div>
      {d.can_edit && (
        <AIRaidProposals projectId={projectId} refresh={aiRefresh} onAdd={(p, suggestion, index) => {
          setError(null); setFromAI({ suggestion, index })
          setEdit({ kind: p.kind, title: p.title, detail: `${p.detail}\n\nFrom the notes: "${p.evidence}"`, impact: p.impact, likelihood: p.likelihood ?? (p.kind === "risk" ? "medium" : null), status: d.statuses[p.kind][0] })
        }} />
      )}
      <ul className="mt-2 divide-y divide-border text-[13px]">
        {list.map((i) => {
          const K = RAID_KIND[i.kind]
          const late = i.open && i.due_date ? lateBy(i.due_date, today) : 0
          return (
            <li key={i.id}>
              <button type="button" disabled={!d.can_edit} onClick={() => { setError(null); setFromAI(null); setEdit({ ...i }) }} className="flex w-full items-start gap-2.5 py-2 text-left enabled:hover:bg-muted/40">
                <K.icon className={cn("mt-0.5 h-4 w-4 shrink-0", i.kind === "blocker" && i.open ? "text-bad" : "text-muted-foreground")} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className={cn("block font-medium", !i.open && "text-muted-foreground line-through")}>{i.title}</span>
                  <span className="block text-[12px] text-muted-foreground">{K.label} · {i.status}{i.owner_name && ` · ${i.owner_name}`}{i.stage && ` · ${i.stage}`}{i.resolution && ` · ${i.resolution}`}</span>
                </span>
                {i.customer_visible && <Eye className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="Shown to the customer" />}
                {i.kind !== "decision" && <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium", IMPACT[i.impact])}>{i.impact}</span>}
                {i.due_date && <span className={cn("shrink-0 whitespace-nowrap text-[12px]", late > 0 ? "font-medium text-bad" : "text-muted-foreground")}>{late > 0 ? `${late} d late` : fmtDate(i.due_date)}</span>}
              </button>
            </li>
          )
        })}
        {list.length === 0 && <li className="py-3 text-muted-foreground">{show === "open" ? "Nothing open. Add a risk before it becomes an issue." : "Nothing recorded yet."}</li>}
      </ul>

      <Dialog open={edit !== null} onOpenChange={(o) => { if (!o) { setEdit(null); setFromAI(null) } }}>
        <DialogContent className="sm:max-w-lg">
          {edit && (
            <form onSubmit={submit} className="grid grid-cols-1 gap-3">
              <DialogHeader><DialogTitle>{edit.id ? `Edit ${RAID_KIND[edit.kind].label.toLowerCase()}` : "Add to the register"}</DialogTitle><DialogDescription>Risks and issues with high impact, and every open blocker, count against the rollout's health.</DialogDescription></DialogHeader>
              <div className="flex rounded-full bg-muted p-0.5" role="radiogroup" aria-label="Kind">
                {(Object.keys(RAID_KIND) as RaidKind[]).map((k) => <button key={k} type="button" role="radio" aria-checked={edit.kind === k} onClick={() => set({ kind: k, status: d.statuses[k][0] })} className={cn("h-7 flex-1 rounded-full text-[12.5px]", edit.kind === k ? "bg-card font-medium shadow-card" : "text-muted-foreground")}>{RAID_KIND[k].label}</button>)}
              </div>
              <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Title<input className={field} required maxLength={200} value={edit.title} onChange={(e) => set({ title: e.target.value })} autoFocus /></label>
              <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Detail<textarea rows={3} maxLength={4000} className="w-full rounded-md border border-input bg-background p-2 text-[13px]" value={edit.detail ?? ""} onChange={(e) => set({ detail: e.target.value })} /></label>
              <div className="grid grid-cols-2 gap-3">
                {edit.kind !== "decision" && <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Impact<select className={field} value={edit.impact ?? "medium"} onChange={(e) => set({ impact: e.target.value as RaidItem["impact"] })}>{["low", "medium", "high"].map((x) => <option key={x}>{x}</option>)}</select></label>}
                {edit.kind === "risk" && <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Likelihood<select className={field} value={edit.likelihood ?? "medium"} onChange={(e) => set({ likelihood: e.target.value as RaidItem["likelihood"] })}>{["low", "medium", "high"].map((x) => <option key={x}>{x}</option>)}</select></label>}
                <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Status<select className={field} value={edit.status ?? d.statuses[edit.kind][0]} onChange={(e) => set({ status: e.target.value })}>{d.statuses[edit.kind].map((x) => <option key={x}>{x}</option>)}</select></label>
                <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Owner<select className={field} value={edit.owner_id ?? ""} onChange={(e) => set({ owner_id: e.target.value ? Number(e.target.value) : null })}><option value="">Nobody yet</option>{d.owners.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
                <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Due<input type="date" className={field} value={edit.due_date ?? ""} onChange={(e) => set({ due_date: e.target.value || null })} /></label>
                <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Stage<select className={field} value={edit.stage ?? ""} onChange={(e) => set({ stage: e.target.value || null })}><option value="">Any</option>{d.stages.map((s) => <option key={s}>{s}</option>)}</select></label>
              </div>
              <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">{edit.kind === "decision" ? "Decision and rationale" : "Mitigation or resolution"}<input className={field} maxLength={2000} value={edit.resolution ?? ""} onChange={(e) => set({ resolution: e.target.value })} /></label>
              <label className="flex items-center gap-2 text-[12.5px]"><input type="checkbox" className="accent-primary" checked={!!edit.customer_visible} onChange={(e) => set({ customer_visible: e.target.checked })} /> Show in the customer's report</label>
              {error && <p className="text-[12.5px] text-bad" role="alert">{error}</p>}
              <div className="flex gap-2">
                {edit.id && <Button type="button" size="sm" variant="ghost" className="rounded-full text-bad" disabled={busy} onClick={remove}>Delete</Button>}
                <span className="ml-auto flex gap-2"><Button type="button" size="sm" variant="ghost" className="rounded-full" onClick={() => setEdit(null)}>Cancel</Button><Button type="submit" size="sm" className="rounded-full" disabled={busy || !edit.title.trim()}>Save</Button></span>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
