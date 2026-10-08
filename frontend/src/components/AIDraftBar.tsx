import { useCallback, useEffect, useState, type ReactNode } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ApiError, cancelAIJob, dismissAISuggestion, projectAI, requestProjectAI, type AISuggestion, type ProjectAI } from "@/lib/api"
import { fmtWhen } from "@/lib/format"

// An AI draft for one rollout, above the boxes it fills: ask for one, use it
// (the boxes fill; nothing is saved until the person saves), dismiss it, or
// ask again. Shown only to whoever may save, and only when the AI can run
// here or a draft is waiting; otherwise the page is exactly as before.
export function AIDraftBar<T>({ projectId, feature, idle, working, note, onUse, ask = "Draft with AI", again = "Draft again", input }: {
  projectId: number; feature: string; idle: string; working: string; note: ReactNode; onUse: (s: AISuggestion<T>) => void
  ask?: string; again?: string; input?: () => unknown   // input: what the person typed, for a feature that works on it
}) {
  const [s, setS] = useState<ProjectAI<T> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { setS(await projectAI<T>(projectId, feature)) } catch { setS(null) }
  }, [projectId, feature])
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
    try { await requestProjectAI(projectId, feature, input?.()); await load() } catch (e) { setError(e instanceof ApiError ? e.message : "Could not ask for a draft") } finally { setBusy(false) }
  }
  async function dismiss(id: number) {
    setBusy(true)
    try { await dismissAISuggestion(projectId, id); await load() } finally { setBusy(false) }
  }
  const sug = s.suggestion
  const lastJob = s.job && !drafting && s.job.created_at > (sug?.created_at ?? "") ? s.job : null
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-[13px] print:hidden">
      <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
      <span className="min-w-0 flex-1" aria-live="polite">
        {drafting ? working : sug ? <>AI draft, {fmtWhen(sug.created_at)}{sug.model ? ` · ${sug.model}` : ""}. {note}</> : idle}
        {lastJob?.status === "failed" && <span className="block text-bad">The last draft did not finish: {lastJob.error}</span>}
        {lastJob?.result?.skipped && <span className="block text-muted-foreground">{lastJob.result.skipped}</span>}
        {error && <span className="block text-bad">{error}</span>}
      </span>
      {sug && !drafting && (
        <>
          <Button size="sm" className="h-7" disabled={busy} onClick={() => onUse(sug)}>Use AI draft</Button>
          <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void dismiss(sug.id)}>Dismiss</Button>
        </>
      )}
      {s.available && !drafting && <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => void draft()}>{sug ? again : ask}</Button>}
      {drafting && s.job && <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void cancelAIJob(projectId, s.job!.id).then(load)}>Cancel</Button>}
    </div>
  )
}
