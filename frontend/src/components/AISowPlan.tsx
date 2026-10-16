import { useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { checkbox } from "@/lib/ui"
import { Button } from "@/components/ui/button"
import { AIProgress } from "@/components/AIProgress"
import { addTask, ApiError, cancelAIJob, closeAISuggestion, dismissAISuggestion, requestProjectAI, saveScope, type SowItem, type SowPlan } from "@/lib/api"
import { fmtWhen } from "@/lib/format"
import { useProjectAI } from "@/lib/usePoll"
import { useAction } from "@/lib/useAction"
import { Notice } from "@/components/Notice"

type Pick = { kind: "scope" | "task" | "customer"; item: SowItem; key: string }

// Plan from the scope of work: pick the PO and scope documents, the AI reads
// them in parts and suggests scope items, tasks per stage and what the
// customer must provide, each with the document words behind it. Ticked ones
// are added through the normal scope and task routes (audited there); key
// dates and exclusions are shown to read, not added.
export function AISowPlan({ projectId, onAdded }: { projectId: number; onAdded: () => void }) {
  const { s, load, working: reading, poll } = useProjectAI<SowPlan>(projectId, "sow_plan", { every: 5000 })
  const [docs, setDocs] = useState<number[] | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const { busy, note, act } = useAction(load)
  const sug = s?.suggestion
  // the likely documents start ticked; a new suggestion starts with everything ticked
  useEffect(() => { if (s) setDocs((d) => d ?? (s.options?.documents ?? []).filter((doc) => doc.likely).map((doc) => doc.id)) }, [s])
  useEffect(() => {
    if (!sug) return
    const p = sug.payload
    setPicked(new Set([...p.scope_items.map((_, i) => `scope:${i}`), ...p.tasks.map((_, i) => `task:${i}`), ...p.customer_obligations.map((_, i) => `customer:${i}`)]))
  }, [sug?.id])   // eslint-disable-line react-hooks/exhaustive-deps
  if (!s || (!s.available && !sug)) return null
  const all = s.options?.documents ?? []
  const lastJob = s.job && !reading && s.job.created_at > (sug?.created_at ?? "") ? s.job : null

  const ask = () => act(() => requestProjectAI(projectId, "sow_plan", { document_ids: docs ?? [] }))
  const take = (from: NonNullable<typeof sug>) => act(async () => {
    const p = from.payload
    const chosen: Pick[] = [
      ...p.scope_items.map((item, i) => ({ kind: "scope" as const, item, key: `scope:${i}` })),
      ...p.tasks.map((item, i) => ({ kind: "task" as const, item, key: `task:${i}` })),
      ...p.customer_obligations.map((item, i) => ({ kind: "customer" as const, item, key: `customer:${i}` })),
    ].filter((x) => picked.has(x.key))
    let taken = 0
    try {
      for (const c of chosen) {
        if (c.kind === "scope") await saveScope(projectId, { title: c.item.title.slice(0, 300), detail: c.item.detail ?? "", status: "agreed", note: "" })
        else await addTask(projectId, { title: (c.kind === "customer" ? `Customer: ${c.item.title}` : c.item.title).slice(0, 200), stage: c.item.stage ?? "" })
        taken += 1
      }
    } catch (e) {
      if (taken) { await closeAISuggestion(projectId, from.id, taken).catch(() => undefined); onAdded() }
      throw new ApiError(0, `${taken} added, then: ${e instanceof ApiError ? e.message : "that did not save"}`)
    }
    await closeAISuggestion(projectId, from.id, taken)
    onAdded()
  })
  const toggle = (key: string) => setPicked((p) => { const n = new Set(p); if (n.has(key)) n.delete(key); else n.add(key); return n })
  const row = (kind: string, item: SowItem, i: number, extra?: string) => {
    const key = `${kind}:${i}`
    return (
      <li key={key} className="flex items-start gap-2 py-2">
        <input type="checkbox" className={`mt-1 ${checkbox}`} checked={picked.has(key)} onChange={() => toggle(key)} aria-label={`Add ${item.title}`} />
        <span className="min-w-0 flex-1">
          <span className="font-medium">{item.title}</span>{extra && <span className="text-muted-foreground"> · {extra}</span>}
          {item.detail && <span className="block text-[12px] text-muted-foreground">{item.detail}</span>}
          {item.quote && <q className="block text-[12px] italic text-muted-foreground">{item.quote}</q>}
        </span>
      </li>
    )
  }
  return (
    <div className="mt-3 rounded-lg bg-muted/60 px-3 py-2 text-[13px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Sparkles className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1 basis-56" aria-live="polite">
          {reading ? "Reading the documents in parts and drafting a plan…"
            : sug ? <>AI suggested plan from the documents, {fmtWhen(sug.created_at)}{sug.model ? ` · ${sug.model}` : ""}. Untick what you do not want, then add the rest.</>
              : "Suggest the scope items and tasks from the PO and scope of work with AI. Pick the documents to read:"}
          {lastJob?.status === "failed" && <Notice bad>The last reading did not finish: {lastJob.error}</Notice>}
          {lastJob?.result?.skipped && <Notice bad>{lastJob.result.skipped}</Notice>}
          {note && <Notice bad={note.bad}>{note.text}</Notice>}
        </div>
        {reading && s.job && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => cancelAIJob(projectId, s.job!.id))}>Cancel</Button>}
      </div>
      {reading && s.job && <AIProgress job={s.job} poll={poll} />}
      {!sug && !reading && (
        <div className="mt-2">
          {all.length === 0 ? <p className="text-muted-foreground">No readable documents yet: upload the PO or scope of work (PDF, Word, Excel or text) under Documents.</p> : (
            <ul className="grid grid-cols-1 gap-1">
              {all.map((d) => (
                <li key={d.id}><label className="flex items-center gap-2">
                  <input type="checkbox" className={checkbox} checked={!!docs?.includes(d.id)} onChange={() => setDocs((x) => (x ?? []).includes(d.id) ? (x ?? []).filter((i) => i !== d.id) : [...(x ?? []), d.id])} />
                  <span className="font-medium">{d.filename}</span><span className="text-muted-foreground">{d.category}</span>
                </label></li>
              ))}
            </ul>
          )}
          {s.available && <Button size="sm" variant="outline" className="mt-2" loading={busy} disabled={!docs?.length} onClick={() => void ask()}>Suggest a plan with AI</Button>}
        </div>
      )}
      {sug && !reading && (
        <div className="mt-2 grid grid-cols-1 gap-3 border-t border-border pt-2">
          {sug.payload.scope_items.length > 0 && <section><h3 className="text-[12px] font-semibold text-nav-fg">Scope items ({sug.payload.scope_items.length})</h3><ul>{sug.payload.scope_items.map((x, i) => row("scope", x, i))}</ul></section>}
          {sug.payload.tasks.length > 0 && <section><h3 className="text-[12px] font-semibold text-nav-fg">Tasks ({sug.payload.tasks.length})</h3><ul>{sug.payload.tasks.map((x, i) => row("task", x, i, x.stage ?? "current stage"))}</ul></section>}
          {sug.payload.customer_obligations.length > 0 && <section><h3 className="text-[12px] font-semibold text-nav-fg">What the customer must provide ({sug.payload.customer_obligations.length}, added as tasks)</h3><ul>{sug.payload.customer_obligations.map((x, i) => row("customer", x, i))}</ul></section>}
          {(sug.payload.key_dates.length > 0 || sug.payload.exclusions.length > 0) && (
            <section className="grid grid-cols-1 gap-2 text-muted-foreground sm:grid-cols-2">
              {sug.payload.key_dates.length > 0 && <div><h3 className="text-[12px] font-semibold text-nav-fg">Key dates</h3><ul>{sug.payload.key_dates.map((d, i) => <li key={i}>{d.what}: {d.date}</li>)}</ul></div>}
              {sug.payload.exclusions.length > 0 && <div><h3 className="text-[12px] font-semibold text-nav-fg">Out of scope</h3><ul>{sug.payload.exclusions.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
            </section>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" loading={busy} disabled={picked.size === 0} onClick={() => void take(sug)}>Add {picked.size} selected</Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => dismissAISuggestion(projectId, sug.id))}>Dismiss</Button>
          </div>
        </div>
      )}
    </div>
  )
}
