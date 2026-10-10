import { useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AIProgress } from "@/components/AIProgress"
import { Ago } from "@/components/Ago"
import { requestProjectAI } from "@/lib/api"
import { useProjectAI } from "@/lib/usePoll"

type Why = { why: string; first_move: string }

// Why is this amber? Under the health line, for an amber or red rollout: the
// reasons Odin computed, phrased by the AI with a first move. Hidden when the
// rollout is green or done, or when the AI cannot run here and has nothing
// to show; the reasons list above it is always the source of truth.
export function AIHealthWhy({ projectId, rag }: { projectId: number; rag: string }) {
  const show = rag === "amber" || rag === "red"
  const { s, load, working } = useProjectAI<Why>(projectId, "health_explained", { enabled: show })
  const [busy, setBusy] = useState(false)
  if (!show || !s || (!s.available && !s.suggestion)) return null
  const sug = s.suggestion
  async function explain() {
    setBusy(true)
    try { await requestProjectAI(projectId, "health_explained"); await load() } finally { setBusy(false) }
  }
  return (
    <div className="mt-2 flex flex-wrap items-start gap-x-3 gap-y-1 rounded-lg bg-muted/50 px-3 py-2 text-[13px]">
      <Sparkles className="mt-1 h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
      <div className="min-w-0 flex-1 basis-56" aria-live="polite">
        {working && s.job ? <AIProgress job={s.job} doing="Explaining" />
          : sug ? <>
              <p>{sug.payload.why}</p>
              <p className="mt-1"><span className="font-medium">First move:</span> {sug.payload.first_move}</p>
              <p className="mt-1 text-[12px] text-muted-foreground">AI, <Ago iso={sug.created_at} />{sug.model ? ` · ${sug.model}` : ""}. The reasons above are Odin's own count.</p>
            </>
            : <span className="text-muted-foreground">Have the AI explain this in plain words, with a first move.</span>}
      </div>
      {s.available && !working && <Button size="sm" variant="outline" className="h-7" loading={busy} onClick={() => void explain()}>{sug ? "Explain again" : "Explain"}</Button>}
    </div>
  )
}
