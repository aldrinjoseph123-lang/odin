import { useState, type FormEvent } from "react"
import { Link } from "react-router-dom"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { PanelTitle } from "@/components/PanelTitle"
import { Badge } from "@/components/ui/badge"
import { Notice } from "@/components/Notice"
import { AIProgress } from "@/components/AIProgress"
import { Input } from "@/components/ui/input"
import { Ago } from "@/components/Ago"
import { ApiError, cancelAIJob, requestProjectAI, type AskAnswer } from "@/lib/api"
import { useProjectAI } from "@/lib/usePoll"

// Ask this rollout: a question answered only from the rollout's own records,
// each sentence pointing at the passage it came from. Odin finds the
// passages; the AI answers from them or says the records do not say.
export function AIAsk({ projectId }: { projectId: number }) {
  const { s, load, working, poll } = useProjectAI<AskAnswer>(projectId, "ask_rollout")
  const [q, setQ] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
      <PanelTitle n={false} id="ask-h" className="mb-0" icon={<Sparkles className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />} hint="answered from its notes, risks, scope, tasks, plan changes and documents">Ask this rollout</PanelTitle>
      {s.available && (
        <form onSubmit={(e) => void ask(e)} className="mt-2 flex flex-wrap gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} maxLength={300} placeholder="e.g. Why did Design slip? What did the customer decide about phase 2?"
            aria-label="Question about this rollout" disabled={working} className="h-8 min-w-0 flex-1 text-[13px]" />
          {working && s.job ? <Button type="button" size="sm" variant="ghost" onClick={() => void cancelAIJob(projectId, s.job!.id).then(load).catch((e: unknown) => setError(e instanceof ApiError ? e.message : "That did not work"))}>Cancel</Button>
            : <Button type="submit" size="sm" loading={busy} disabled={q.trim().length < 5}>Ask</Button>}
        </form>
      )}
      <div aria-live="polite" className="text-[13px]">
        {working && s.job && <AIProgress job={s.job} poll={poll} doing="Reading the rollout's records" />}
        {lastJob?.status === "failed" && <Notice bad className="mt-2">That question did not finish: {lastJob.error}</Notice>}
        {lastJob?.result?.skipped && <Notice className="mt-2">{lastJob.result.skipped}</Notice>}
        {error && <Notice bad className="mt-2">{error}</Notice>}
        {a && !working && (
          <div className="mt-3 rounded-lg bg-muted/50 px-3 py-2">
            <p className="text-[12px] text-muted-foreground">“{a.payload.question}”, <Ago iso={a.created_at} /></p>
            <p className="mt-1 leading-relaxed">{a.payload.answer}</p>
            {a.payload.sources.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-2 text-[12px]">
                {a.payload.sources.map((src) => <li key={src.n}><Badge variant="outline" render={<Link to={src.href} />}>[{src.n}] {src.from}</Badge></li>)}
              </ul>
            )}
            {!a.payload.found && <p className="mt-1 text-[12px] text-muted-foreground">The records do not answer this; nothing was guessed.</p>}
          </div>
        )}
      </div>
    </section>
  )
}
