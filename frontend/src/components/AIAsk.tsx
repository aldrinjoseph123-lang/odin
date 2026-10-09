import { useCallback, useEffect, useState, type FormEvent } from "react"
import { Link } from "react-router-dom"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Ago } from "@/components/Ago"
import { ApiError, cancelAIJob, projectAI, requestProjectAI, type AskAnswer, type ProjectAI } from "@/lib/api"
import { usePoll } from "@/lib/usePoll"

// Ask this rollout: a question answered only from the rollout's own records,
// each sentence pointing at the passage it came from. Odin finds the
// passages; the AI answers from them or says the records do not say.
export function AIAsk({ projectId }: { projectId: number }) {
  const [s, setS] = useState<ProjectAI<AskAnswer> | null>(null)
  const [q, setQ] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try { setS(await projectAI<AskAnswer>(projectId, "ask_rollout")) } catch { setS(null) }
  }, [projectId])
  useEffect(() => { void load() }, [load])
  const working = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  usePoll(working, load)
  if (!s || (!s.available && !s.suggestion)) return null
  const a = s.suggestion
  async function ask(e: FormEvent) {
    e.preventDefault()
    if (q.trim().length < 5) return
    setBusy(true); setError(null)
    try { await requestProjectAI(projectId, "ask_rollout", { question: q.trim() }); await load() } catch (x) { setError(x instanceof ApiError ? x.message : "Could not ask") } finally { setBusy(false) }
  }
  const lastJob = s.job && !working && s.job.created_at > (a?.created_at ?? "") ? s.job : null
  return (
    <section className="panel p-4" aria-labelledby="ask-h">
      <h2 id="ask-h" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-semibold text-nav-fg">
        <Sparkles className="h-3.5 w-3.5 text-primary-text" aria-hidden />Ask this rollout<span className="sr-only">, </span>
        <span className="font-normal text-muted-foreground">answered from its notes, risks, scope, tasks, plan changes and documents</span>
      </h2>
      {s.available && (
        <form onSubmit={(e) => void ask(e)} className="mt-2 flex flex-wrap gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} maxLength={300} placeholder="e.g. Why did Design slip? What did the customer decide about phase 2?"
            aria-label="Question about this rollout" disabled={working} className="h-8 min-w-0 flex-1 text-[13px]" />
          {working && s.job ? <Button type="button" size="sm" variant="ghost" className="h-8" onClick={() => void cancelAIJob(projectId, s.job!.id).then(load).catch((e: unknown) => setError(e instanceof ApiError ? e.message : "That did not work"))}>Cancel</Button>
            : <Button type="submit" size="sm" className="h-8" loading={busy} disabled={q.trim().length < 5}>Ask</Button>}
        </form>
      )}
      <div aria-live="polite" className="text-[13px]">
        {working && <p className="mt-2 text-muted-foreground">Reading the rollout's records… about a minute or two.</p>}
        {lastJob?.status === "failed" && <p className="mt-2 text-bad">That question did not finish: {lastJob.error}</p>}
        {lastJob?.result?.skipped && <p className="mt-2 text-muted-foreground">{lastJob.result.skipped}</p>}
        {error && <p className="mt-2 text-bad" role="alert">{error}</p>}
        {a && !working && (
          <div className="mt-3 rounded-lg bg-muted/50 px-3 py-2">
            <p className="text-[12px] text-muted-foreground">“{a.payload.question}”, <Ago iso={a.created_at} /></p>
            <p className="mt-1 leading-relaxed">{a.payload.answer}</p>
            {a.payload.sources.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-2 text-[12px]">
                {a.payload.sources.map((src) => <li key={src.n}><Link to={src.href} className="rounded-full border border-border px-2 py-1 hover:bg-muted">[{src.n}] {src.from}</Link></li>)}
              </ul>
            )}
            {!a.payload.found && <p className="mt-1 text-[12px] text-muted-foreground">The records do not answer this; nothing was guessed.</p>}
          </div>
        )}
      </div>
    </section>
  )
}
