import { useCallback, useEffect, useState, type FormEvent } from "react"
import { Segmented } from "@/components/Segmented"
import { field, danger, fieldArea } from "@/lib/ui"
import { askConfirm } from "@/lib/confirm"
import { Link } from "react-router-dom"
import { ArrowDown, ArrowUp, FileSignature, Plus } from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ApiError, deleteScope, saveScope, scopeItems, type ScopeData, type ScopeItem, type ScopeStatus, type SignoffState } from "@/lib/api"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { signoffText } from "@/lib/format"
import { AISowPlan } from "@/components/AISowPlan"

// The agreed scope: recorded while scoping, marked delivered / partial /
// descoped at the end. The sign-off document lists it item by item, so the
// customer signs against what they agreed. The sign-off's state sits on top.
export const SCOPE_WORD: Record<ScopeStatus, string> = { agreed: "Agreed", delivered: "Delivered", partial: "Partly delivered", descoped: "Descoped" }
export const SCOPE_TONE: Record<ScopeStatus, string> = { agreed: "bg-muted text-muted-foreground", delivered: "bg-ok-soft text-ok", partial: "bg-warn-soft text-warn", descoped: "bg-muted text-muted-foreground line-through" }
type Draft = Partial<ScopeItem> & { title: string; status: ScopeStatus }

export function ScopePanel({ projectId, signoff }: { projectId: number; signoff?: SignoffState }) {
  const [d, setD] = useState<ScopeData | null>(null)
  const [edit, setEdit] = useState<Draft | null>(null)
  const [opened, setOpened] = useState("")   // an existing item as opened: Save wakes when it differs (review P3-41)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const load = useCallback(() => scopeItems(projectId).then((x) => { setD(x); setFailed(false) }), [projectId])
  const first = useCallback(() => { setFailed(false); load().catch(() => setFailed(true)) }, [load])
  useEffect(first, [first])
  if (!d) return failed
    ? <p className="flex items-center gap-2 text-[13px] text-muted-foreground" role="alert">Could not load the scope. <Button size="sm" variant="outline" onClick={first}>Try again</Button></p>
    : <p className="text-[13px] text-muted-foreground">Loading…</p>
  const count = (s: ScopeStatus) => d.items.filter((i) => i.status === s).length
  const set = (patch: Partial<Draft>) => setEdit((x) => (x ? { ...x, ...patch } : x))
  const open = (x: Draft) => { setOpened(x.id ? JSON.stringify(x) : ""); setEdit(x) }
  const changed = !!edit && (!edit.id || JSON.stringify(edit) !== opened)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!edit) return
    setBusy(true); setError(null)
    try { await saveScope(projectId, { title: edit.title, detail: edit.detail ?? "", status: edit.status, note: edit.note ?? "" }, edit.id); toast(edit.id ? "Scope item saved" : "Added to the scope"); setEdit(null); await load() }
    catch (err) { setError(err instanceof ApiError ? err.message : "That did not save") } finally { setBusy(false) }
  }
  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    try { await fn(); await load() } catch (err) { setError(err instanceof ApiError ? err.message : "That did not save") } finally { setBusy(false) }
  }
  const signoffDone = signoff?.complete
  return (
    <div>
      {signoff && (
        <div className={cn("mb-3 flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 text-[13px]", signoffDone ? "bg-ok-soft" : signoff.in_stage ? "bg-warn-soft/60" : "bg-muted/60")}>
          <FileSignature className={cn("h-4 w-4", signoffDone ? "text-ok" : "text-muted-foreground")} aria-hidden />
          <span><span className="font-medium">Sign-off{signoff.version ? ` v${signoff.version}` : ""}:</span> {signoffText(signoff.status)}</span>
          {(signoff.status || d.can_edit) && <Link to={`/projects/${projectId}/signoff`} className={cn(buttonVariants({ variant: signoff.in_stage && !signoffDone ? "default" : "outline", size: "sm" }), "ml-auto h-7 rounded-full")}>
            {signoff.status ? "Open the sign-off" : "Prepare the sign-off"}
          </Link>}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        {d.items.length > 0 ? (["delivered", "partial", "descoped", "agreed"] as ScopeStatus[]).filter(count).map((s) =>
          <span key={s} className={cn("rounded-full px-2 py-1", SCOPE_TONE[s].replace("line-through", ""))}>{count(s)} {SCOPE_WORD[s].toLowerCase()}</span>)
          : <span className="text-muted-foreground">{d.can_edit ? "What the customer agreed to, item by item. The sign-off lists it." : "No scope recorded yet."}</span>}
        {d.can_edit && <Button size="sm" className="ml-auto" onClick={() => { setError(null); open({ title: "", status: "agreed" }) }}><Plus className="h-3.5 w-3.5" /> Add</Button>}
      </div>
      {d.can_edit && <AISowPlan projectId={projectId} onAdded={() => void load()} />}
      {error && !edit && <p className="mt-2 text-[13px] text-destructive" role="alert">{error}</p>}
      <ol className="mt-2 divide-y divide-border text-[13px]">
        {d.items.map((i, n) => (
          <li key={i.id} className="flex items-start gap-2 py-2">
            <span className="w-5 shrink-0 pt-1 text-right text-[12px] tabular-nums text-muted-foreground">{n + 1}</span>
            <button type="button" disabled={!d.can_edit} onClick={() => { setError(null); open({ ...i }) }} className="min-w-0 flex-1 text-left enabled:hover:underline">
              <span className={cn("block font-medium", i.status === "descoped" && "text-muted-foreground line-through")}>{i.title}</span>
              {(i.detail || i.note) && <span className="block text-[12px] text-muted-foreground">{[i.detail, i.note].filter(Boolean).join(" · ")}</span>}
            </button>
            <span className={cn("shrink-0 rounded-full px-2 py-1 text-[11px] font-medium", SCOPE_TONE[i.status].replace("line-through", ""))}>{SCOPE_WORD[i.status]}</span>
            {d.can_edit && (
              <span className="flex shrink-0">
                <button type="button" aria-label={`Move ${i.title} up`} disabled={busy || n === 0} onClick={() => act(() => saveScope(projectId, { move: -1 }, i.id))} className="rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowUp className="h-3.5 w-3.5" /></button>
                <button type="button" aria-label={`Move ${i.title} down`} disabled={busy || n === d.items.length - 1} onClick={() => act(() => saveScope(projectId, { move: 1 }, i.id))} className="rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowDown className="h-3.5 w-3.5" /></button>
              </span>
            )}
          </li>
        ))}
        {d.items.length === 0 && d.can_edit && <li className="py-3 text-[13px] text-muted-foreground">No scope recorded. Add the deliverables agreed at kickoff; without them the sign-off is drafted from the stages, tasks and deliverables.</li>}
      </ol>

      <Dialog open={edit !== null} onOpenChange={(o) => { if (!o) setEdit(null) }}>
        <DialogContent className="sm:max-w-lg">
          {edit && (
            <form onSubmit={submit} className="grid grid-cols-1 gap-3">
              <DialogHeader><DialogTitle>{edit.id ? "Scope item" : "Add to the scope"}</DialogTitle>
                <DialogDescription>Before sign-off, mark each item delivered, partly delivered or descoped; the last two need a reason.</DialogDescription></DialogHeader>
              <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Deliverable<input className={field} required maxLength={300} value={edit.title} onChange={(e) => set({ title: e.target.value })} autoFocus /></label>
              <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Detail<textarea rows={2} maxLength={2000} className={fieldArea} value={edit.detail ?? ""} onChange={(e) => set({ detail: e.target.value })} placeholder="Quantities, sites, acceptance criteria" /></label>
              <Segmented label="Status" full value={edit.status as ScopeStatus} onChange={(s) => set({ status: s })}
                options={(Object.keys(SCOPE_WORD) as ScopeStatus[]).map((s) => ({ value: s, label: SCOPE_WORD[s] }))} />
              <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">{edit.status === "descoped" ? "Why it was descoped" : edit.status === "partial" ? "What was left out, and why" : "Note"}
                <input className={field} maxLength={1000} required={edit.status === "partial" || edit.status === "descoped"} value={edit.note ?? ""} onChange={(e) => set({ note: e.target.value })} /></label>
              {error && <p className="text-[13px] text-destructive" role="alert">{error}</p>}
              <div className="flex gap-2">
                {edit.id && <Button type="button" size="sm" variant="ghost" className={danger} disabled={busy} onClick={async () => { if (await askConfirm("Delete this scope item? It leaves the agreed scope; the history keeps a line that it existed.")) void act(async () => { await deleteScope(projectId, edit.id!); setEdit(null); toast("Scope item deleted") }) }}>Delete</Button>}
                <span className="ml-auto flex gap-2"><Button type="button" size="sm" variant="ghost" onClick={() => setEdit(null)}>Cancel</Button><Button type="submit" size="sm" loading={busy} disabled={!edit.title.trim() || !changed}>Save</Button></span>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
