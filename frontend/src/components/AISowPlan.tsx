import { useCallback, useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { addTask, ApiError, cancelAIJob, closeAISuggestion, dismissAISuggestion, projectAI, requestProjectAI, saveScope, type ProjectAI, type SowItem, type SowPlan } from "@/lib/api"
import { fmtWhen } from "@/lib/format"

type Pick = { kind: "scope" | "task" | "customer"; item: SowItem; key: string }

// Plan from the scope of work: pick the PO and scope documents, the AI reads
// them in parts and suggests scope items, tasks per stage and what the
// customer must provide, each with the document words behind it. Ticked ones
// are added through the normal scope and task routes (audited there); key
// dates and exclusions are shown to read, not added.
export function AISowPlan({ projectId, onAdded }: { projectId: number; onAdded: () => void }) {
  const [s, setS] = useState<ProjectAI<SowPlan> | null>(null)
  const [docs, setDocs] = useState<number[] | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try {
      const x = await projectAI<SowPlan>(projectId, "sow_plan")
      setS(x)
      setDocs((d) => d ?? (x.options?.documents ?? []).filter((doc) => doc.likely).map((doc) => doc.id))
      if (x.suggestion) {
        const p = x.suggestion.payload
        setPicked(new Set([...p.scope_items.map((_, i) => `scope:${i}`), ...p.tasks.map((_, i) => `task:${i}`), ...p.customer_obligations.map((_, i) => `customer:${i}`)]))
      }
    } catch { setS(null) }
  }, [projectId])
  useEffect(() => { void load() }, [load])
  const reading = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  useEffect(() => {
    if (!reading) return
    const t = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(t)
  }, [reading, load])
  if (!s || (!s.available && !s.suggestion)) return null
  const sug = s.suggestion
  const all = s.options?.documents ?? []
  const lastJob = s.job && !reading && s.job.created_at > (sug?.created_at ?? "") ? s.job : null

  async function ask() {
    setBusy(true); setError(null)
    try { await requestProjectAI(projectId, "sow_plan", { document_ids: docs ?? [] }); await load() } catch (e) { setError(e instanceof ApiError ? e.message : "Could not ask") } finally { setBusy(false) }
  }
  async function take() {
    if (!sug) return
    const p = sug.payload
    const chosen: Pick[] = [
      ...p.scope_items.map((item, i) => ({ kind: "scope" as const, item, key: `scope:${i}` })),
      ...p.tasks.map((item, i) => ({ kind: "task" as const, item, key: `task:${i}` })),
      ...p.customer_obligations.map((item, i) => ({ kind: "customer" as const, item, key: `customer:${i}` })),
    ].filter((x) => picked.has(x.key))
    setBusy(true); setError(null)
    let taken = 0
    try {
      for (const c of chosen) {
        if (c.kind === "scope") await saveScope(projectId, { title: c.item.title.slice(0, 300), detail: c.item.detail ?? "", status: "agreed", note: "" })
        else await addTask(projectId, { title: (c.kind === "customer" ? `Customer: ${c.item.title}` : c.item.title).slice(0, 200), stage: c.item.stage ?? "" })
        taken += 1
      }
      await closeAISuggestion(projectId, sug.id, taken)
      onAdded(); await load()
    } catch (e) {
      setError(`${taken} added, then: ${e instanceof ApiError ? e.message : "that did not save"}`)
      if (taken) { await closeAISuggestion(projectId, sug.id, taken).catch(() => undefined); onAdded(); await load() }
    } finally { setBusy(false) }
  }
  const toggle = (key: string) => setPicked((p) => { const n = new Set(p); if (n.has(key)) n.delete(key); else n.add(key); return n })
  const row = (kind: string, item: SowItem, i: number, extra?: string) => {
    const key = `${kind}:${i}`
    return (
      <li key={key} className="flex items-start gap-2 py-1.5">
        <input type="checkbox" className="mt-1 h-3.5 w-3.5 accent-primary" checked={picked.has(key)} onChange={() => toggle(key)} aria-label={`Add ${item.title}`} />
        <span className="min-w-0 flex-1">
          <span className="font-medium">{item.title}</span>{extra && <span className="text-muted-foreground"> · {extra}</span>}
          {item.detail && <span className="block text-[12px] text-muted-foreground">{item.detail}</span>}
          {item.quote && <q className="block text-[12px] italic text-muted-foreground">{item.quote}</q>}
        </span>
      </li>
    )
  }
  return (
    <div className="mt-3 rounded-lg border border-border bg-muted/50 px-3 py-2 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
        <span className="min-w-0 flex-1" aria-live="polite">
          {reading ? "Reading the documents in parts and drafting a plan… a few minutes for a long scope of work."
            : sug ? <>AI suggested plan from the documents, {fmtWhen(sug.created_at)}{sug.model ? ` · ${sug.model}` : ""}. Untick what you do not want, then add the rest.</>
              : "Suggest the scope items and tasks from the PO and scope of work with AI. Pick the documents to read:"}
          {lastJob?.status === "failed" && <span className="block text-bad">The last reading did not finish: {lastJob.error}</span>}
          {lastJob?.result?.skipped && <span className="block text-bad">{lastJob.result.skipped}</span>}
          {error && <span className="block text-bad" role="alert">{error}</span>}
        </span>
        {reading && s.job && <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void cancelAIJob(projectId, s.job!.id).then(load)}>Cancel</Button>}
      </div>
      {!sug && !reading && (
        <div className="mt-2">
          {all.length === 0 ? <p className="text-muted-foreground">No readable documents yet: upload the PO or scope of work (PDF, Word, Excel or text) under Documents.</p> : (
            <ul className="grid grid-cols-1 gap-1">
              {all.map((d) => (
                <li key={d.id}><label className="flex items-center gap-2">
                  <input type="checkbox" className="h-3.5 w-3.5 accent-primary" checked={!!docs?.includes(d.id)} onChange={() => setDocs((x) => (x ?? []).includes(d.id) ? (x ?? []).filter((i) => i !== d.id) : [...(x ?? []), d.id])} />
                  <span className="font-medium">{d.filename}</span><span className="text-muted-foreground">{d.category}</span>
                </label></li>
              ))}
            </ul>
          )}
          {s.available && <Button size="sm" variant="outline" className="mt-2 h-7" disabled={busy || !docs?.length} onClick={() => void ask()}>Suggest a plan with AI</Button>}
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
            <Button size="sm" className="h-7" disabled={busy || picked.size === 0} onClick={() => void take()}>Add {picked.size} selected</Button>
            <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void dismissAISuggestion(projectId, sug.id).then(load)}>Dismiss</Button>
          </div>
        </div>
      )}
    </div>
  )
}
