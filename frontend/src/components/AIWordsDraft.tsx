import { useCallback, useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ApiError, dismissAISuggestion, projectAI, requestProjectAI, type ProjectAI, type WeeklyWordsDraft } from "@/lib/api"
import { fmtWhen } from "@/lib/format"

type Words = { summary: string; next_steps: string; asks: string }

// The weekly-words AI draft on the report page. Shown only to whoever may
// save the report, and only when the AI can run here or a draft is waiting;
// otherwise the page is exactly as before. The draft fills the three boxes;
// nothing is saved until the project manager saves a version.
export function AIWordsDraft({ projectId, onUse }: { projectId: number; onUse: (w: Words, suggestion: number) => void }) {
  const [s, setS] = useState<ProjectAI<WeeklyWordsDraft> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { setS(await projectAI<WeeklyWordsDraft>(projectId, "weekly_words")) } catch { setS(null) }
  }, [projectId])
  useEffect(() => { void load() }, [load])
  const drafting = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  useEffect(() => {
    if (!drafting) return
    const t = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(t)
  }, [drafting, load])
  if (!s || (!s.available && !s.suggestion)) return null

  async function draft() {
    setBusy(true); setError(null)
    try { await requestProjectAI(projectId, "weekly_words"); await load() } catch (e) { setError(e instanceof ApiError ? e.message : "Could not ask for a draft") } finally { setBusy(false) }
  }
  async function dismiss(id: number) {
    setBusy(true)
    try { await dismissAISuggestion(projectId, id); await load() } finally { setBusy(false) }
  }
  const sug = s.suggestion
  const lastJob = s.job && !drafting && s.job.created_at > (sug?.created_at ?? "") ? s.job : null
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-[12.5px] print:hidden">
      <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
      <span className="min-w-0 flex-1" aria-live="polite">
        {drafting ? "Drafting from this week's notes, plan and risks… about a minute."
          : sug ? <>AI draft, {fmtWhen(sug.created_at)}{sug.model ? ` · ${sug.model}` : ""}. It fills the three boxes for you to edit; the customer copy uses the same words.</>
            : "Draft the summary, next steps and asks with AI from this week's notes, plan and risks."}
        {lastJob?.status === "failed" && <span className="block text-bad">The last draft did not finish: {lastJob.error}</span>}
        {lastJob?.result?.skipped && <span className="block text-muted-foreground">{lastJob.result.skipped}</span>}
        {error && <span className="block text-bad">{error}</span>}
      </span>
      {sug && !drafting && (
        <>
          <Button size="sm" className="h-7" disabled={busy} onClick={() => onUse({ summary: sug.payload.summary, next_steps: sug.payload.next_steps.join("\n"), asks: sug.payload.asks.join("\n") }, sug.id)}>Use AI draft</Button>
          <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void dismiss(sug.id)}>Dismiss</Button>
        </>
      )}
      {s.available && !drafting && <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => void draft()}>{sug ? "Draft again" : "Draft with AI"}</Button>}
    </div>
  )
}
