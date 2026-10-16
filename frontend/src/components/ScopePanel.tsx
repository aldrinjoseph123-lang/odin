import { useState, type FormEvent } from "react"
import { Segmented } from "@/components/Segmented"
import { field, danger, fieldArea } from "@/lib/ui"
import { Field } from "@/components/ui/field"
import { Tag } from "@/components/ui/tag"
import { MoveArrows } from "@/components/MoveArrows"
import { DragReorder, DragRow } from "@/components/DragReorder"
import { askConfirm } from "@/lib/confirm"
import { Link } from "react-router-dom"
import { FileSignature, Plus } from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { deleteScope, saveScope, scopeItems, type ScopeItem, type ScopeStatus, type SignoffState } from "@/lib/api"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { signoffText } from "@/lib/format"
import { AISowPlan } from "@/components/AISowPlan"
import { Notice } from "@/components/Notice"
import { EmptyState } from "@/components/EmptyState"
import { LoadFailed } from "@/components/LoadFailed"
import { PanelLoading } from "@/components/PanelLoading"
import { useLoad } from "@/lib/useLoad"
import { useAction } from "@/lib/useAction"

// The agreed scope: recorded while scoping, marked delivered / partial /
// descoped at the end. The sign-off document lists it item by item, so the
// customer signs against what they agreed. The sign-off's state sits on top.
export const SCOPE_WORD: Record<ScopeStatus, string> = { agreed: "Agreed", delivered: "Delivered", partial: "Partly delivered", descoped: "Descoped" }
type Draft = Partial<ScopeItem> & { title: string; status: ScopeStatus }

export function ScopePanel({ projectId, signoff }: { projectId: number; signoff?: SignoffState }) {
  const { data: d, error: failed, reload: load } = useLoad(`scope:${projectId}`, () => scopeItems(projectId))
  const [edit, setEdit] = useState<Draft | null>(null)
  const [opened, setOpened] = useState("")   // an existing item as opened: Save wakes when it differs (review P3-41)
  const { busy, note, setNote, act } = useAction(load)
  const error = note?.text
  if (!d) return failed ? <LoadFailed what="the scope" onRetry={() => void load()} /> : <PanelLoading />
  const count = (s: ScopeStatus) => d.items.filter((i) => i.status === s).length
  const set = (patch: Partial<Draft>) => setEdit((x) => (x ? { ...x, ...patch } : x))
  const open = (x: Draft) => { setOpened(x.id ? JSON.stringify(x) : ""); setEdit(x) }
  const changed = !!edit && (!edit.id || JSON.stringify(edit) !== opened)

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!edit) return
    void act(async () => { await saveScope(projectId, { title: edit.title, detail: edit.detail ?? "", status: edit.status, note: edit.note ?? "" }, edit.id); toast(edit.id ? "Scope item saved" : "Added to the scope"); setEdit(null) })
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
          <Tag key={s} kind="scope" level={s}>{count(s)} {SCOPE_WORD[s].toLowerCase()}</Tag>)
          : <span className="text-muted-foreground">{d.can_edit ? "What the customer agreed to, item by item. The sign-off lists it." : "No scope recorded yet."}</span>}
        {d.can_edit && <Button size="sm" className="ml-auto" onClick={() => { setNote(null); open({ title: "", status: "agreed" }) }}><Plus className="h-3.5 w-3.5" /> Add</Button>}
      </div>
      {d.can_edit && <AISowPlan projectId={projectId} onAdded={() => void load()} />}
      {error && !edit && <Notice bad className="mt-2">{error}</Notice>}
      {/* the list sits inside the drag context: dnd-kit draws its hidden help and live region beside it, and an <ol> may hold only <li> */}
      <DragReorder ids={d.items.map((i) => i.id)} onReorder={(id, steps) => act(async () => { for (const s of steps) await saveScope(projectId, { move: s === "up" ? -1 : 1 }, id) })}>
      <ol className="mt-2 divide-y divide-border text-[13px]">
        {d.items.map((i, n) => (
          <DragRow as="li" key={i.id} id={i.id} disabled={!d.can_edit} className="flex items-start gap-2 py-2">
            <span className="w-5 shrink-0 pt-1 text-right text-[12px] tabular-nums text-muted-foreground">{n + 1}</span>
            <button type="button" disabled={!d.can_edit} onClick={() => { setNote(null); open({ ...i }) }} className="min-w-0 flex-1 rounded-md text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 enabled:hover:underline">
              <span className={cn("block font-medium", i.status === "descoped" && "text-muted-foreground line-through")}>{i.title}</span>
              {(i.detail || i.note) && <span className="block text-[12px] text-muted-foreground">{[i.detail, i.note].filter(Boolean).join(" · ")}</span>}
            </button>
            <Tag kind="scope" level={i.status}>{SCOPE_WORD[i.status]}</Tag>
            {d.can_edit && <MoveArrows name={i.title} first={n === 0} last={n === d.items.length - 1} busy={busy} onMove={(dir) => act(() => saveScope(projectId, { move: dir === "up" ? -1 : 1 }, i.id))} />}
          </DragRow>
        ))}
        {d.items.length === 0 && d.can_edit && <EmptyState as="li">No scope recorded. Add the deliverables agreed at kickoff; without them the sign-off is drafted from the stages, tasks and deliverables.</EmptyState>}
      </ol>
      </DragReorder>

      <Dialog open={edit !== null} onOpenChange={(o) => { if (!o) setEdit(null) }}>
        <DialogContent className="sm:max-w-lg">
          {edit && (
            <form onSubmit={submit} className="grid grid-cols-1 gap-3">
              <DialogHeader><DialogTitle>{edit.id ? "Scope item" : "Add to the scope"}</DialogTitle>
                <DialogDescription>Before sign-off, mark each item delivered, partly delivered or descoped; the last two need a reason.</DialogDescription></DialogHeader>
              <Field label="Deliverable"><input className={field} required maxLength={300} value={edit.title} onChange={(e) => set({ title: e.target.value })} autoFocus /></Field>
              <Field label="Detail"><textarea rows={2} maxLength={2000} className={fieldArea} value={edit.detail ?? ""} onChange={(e) => set({ detail: e.target.value })} placeholder="Quantities, sites, acceptance criteria" /></Field>
              <Segmented label="Status" full value={edit.status as ScopeStatus} onChange={(s) => set({ status: s })}
                options={(Object.keys(SCOPE_WORD) as ScopeStatus[]).map((s) => ({ value: s, label: SCOPE_WORD[s] }))} />
              <Field label={edit.status === "descoped" ? "Why it was descoped" : edit.status === "partial" ? "What was left out, and why" : "Note"}>
                <input className={field} maxLength={1000} required={edit.status === "partial" || edit.status === "descoped"} value={edit.note ?? ""} onChange={(e) => set({ note: e.target.value })} /></Field>
              {error && <Notice bad>{error}</Notice>}
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
