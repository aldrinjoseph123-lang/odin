import type { ReactNode } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AIProgress } from "@/components/AIProgress"
import { cancelAIJob, dismissAISuggestion, requestProjectAI, type AISuggestion } from "@/lib/api"
import { fmtWhen } from "@/lib/format"
import { useProjectAI } from "@/lib/usePoll"
import { useAction } from "@/lib/useAction"
import { Notice } from "@/components/Notice"

// An AI draft for one rollout, above the boxes it fills: ask for one, use it
// (the boxes fill; nothing is saved until the person saves), dismiss it, or
// ask again. Shown only to whoever may save, and only when the AI can run
// here or a draft is waiting; otherwise the page is exactly as before.
export function AIDraftBar<T>({ projectId, feature, idle, working, note, onUse, ask = "Draft with AI", again = "Draft again", input }: {
  projectId: number; feature: string; idle: string; working: string; note: ReactNode; onUse: (s: AISuggestion<T>) => void
  ask?: string; again?: string; input?: () => unknown   // input: what the person typed, for a feature that works on it
}) {
  const { s, load, working: drafting, poll } = useProjectAI<T>(projectId, feature)
  const { busy, note: said, act } = useAction(load)
  if (!s || (!s.available && !s.suggestion)) return null
  const sug = s.suggestion
  const lastJob = s.job && !drafting && s.job.created_at > (sug?.created_at ?? "") ? s.job : null
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg bg-muted/60 px-3 py-2 text-[13px] print:hidden">
      <Sparkles className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1 basis-56" aria-live="polite">
        {drafting ? working : sug ? <>AI draft, {fmtWhen(sug.created_at)}{sug.model ? ` · ${sug.model}` : ""}. {note}</> : idle}
        {lastJob?.status === "failed" && <Notice bad>The last draft did not finish: {lastJob.error}</Notice>}
        {lastJob?.result?.skipped && <Notice>{lastJob.result.skipped}</Notice>}
        {said && <Notice bad={said.bad}>{said.text}</Notice>}
      </div>
      {sug && !drafting && (
        <>
          <Button size="sm" disabled={busy} onClick={() => onUse(sug)}>Use AI draft</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => dismissAISuggestion(projectId, sug.id))}>Dismiss</Button>
        </>
      )}
      {s.available && !drafting && <Button size="sm" variant="outline" loading={busy} onClick={() => void act(() => requestProjectAI(projectId, feature, input?.()))}>{sug ? again : ask}</Button>}
      {drafting && s.job && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => cancelAIJob(projectId, s.job!.id))}>Cancel</Button>}
      {drafting && s.job && <div className="basis-full"><AIProgress job={s.job} poll={poll} /></div>}
    </div>
  )
}
