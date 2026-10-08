import { useCallback, useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Ago } from "@/components/Ago"
import { projectAI, requestProjectAI, type ProjectAI } from "@/lib/api"

type Why = { why: string; first_move: string }

// Why is this amber? Under the health line, for an amber or red rollout: the
// reasons Odin computed, phrased by the AI with a first move. Hidden when the
// rollout is green or done, or when the AI cannot run here and has nothing
// to show; the reasons list above it is always the source of truth.
export function AIHealthWhy({ projectId, rag }: { projectId: number; rag: string }) {
  const [s, setS] = useState<ProjectAI<Why> | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { setS(await projectAI<Why>(projectId, "health_explained")) } catch { setS(null) }
  }, [projectId])
  const show = rag === "amber" || rag === "red"
  useEffect(() => { if (show) void load() }, [load, show])
  const working = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  useEffect(() => {
    if (!working) return
    const t = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(t)
  }, [working, load])
  if (!show || !s || (!s.available && !s.suggestion)) return null
  const sug = s.suggestion
  async function explain() {
    setBusy(true)
    try { await requestProjectAI(projectId, "health_explained"); await load() } finally { setBusy(false) }
  }
  return (
    <div className="mt-2 flex flex-wrap items-start gap-x-3 gap-y-1 rounded-lg bg-muted/50 px-3 py-2 text-[12.5px]">
      <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
      <div className="min-w-0 flex-1" aria-live="polite">
        {working ? <span className="text-muted-foreground">Explaining… about half a minute.</span>
          : sug ? <>
              <p>{sug.payload.why}</p>
              <p className="mt-0.5"><span className="font-medium">First move:</span> {sug.payload.first_move}</p>
              <p className="mt-0.5 text-[11.5px] text-muted-foreground">AI, <Ago iso={sug.created_at} />{sug.model ? ` · ${sug.model}` : ""}. The reasons above are Odin's own count.</p>
            </>
            : <span className="text-muted-foreground">Have the AI explain this in plain words, with a first move.</span>}
      </div>
      {s.available && !working && <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => void explain()}>{sug ? "Explain again" : "Explain"}</Button>}
    </div>
  )
}
