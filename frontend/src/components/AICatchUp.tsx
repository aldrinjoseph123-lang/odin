import { useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AIProgress } from "@/components/AIProgress"
import { Ago } from "@/components/Ago"
import { ApiError, cancelAIJob, requestProjectAI, type CatchUp } from "@/lib/api"
import { useProjectAI } from "@/lib/usePoll"

// Catch me up: a one-page brief on this rollout for whoever takes it over or
// joins. Who waits on whom is Odin's own list; the rest is written by the AI
// from the rollout's facts. Hidden when the AI cannot run and no brief exists.
export function AICatchUp({ projectId }: { projectId: number }) {
  const { s, load, working } = useProjectAI<CatchUp>(projectId, "catch_up", { every: 5000 })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  if (!s || (!s.available && !s.suggestion)) return null
  const sug = s.suggestion
  async function ask() {
    setBusy(true); setOpen(true); setError(null)
    try { await requestProjectAI(projectId, "catch_up"); await load() } catch (e) { setError(e instanceof ApiError ? e.message : "Could not ask") } finally { setBusy(false) }
  }
  const list = (title: string, items: string[]) => items.length > 0 && (
    <section><h3 className="text-[12px] font-semibold text-nav-fg">{title}</h3><ul className="mt-1 list-disc pl-5">{items.map((x) => <li key={x}>{x}</li>)}</ul></section>
  )
  return (
    <section className="panel p-4" aria-labelledby="catchup-h">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
        <h2 id="catchup-h" className="min-w-0 flex-1 basis-56 text-[12px] font-semibold text-nav-fg">
          Catch me up<span className="sr-only">, </span>
          <span className="ml-2 font-normal text-muted-foreground" aria-live="polite">
            {working ? "Reading the rollout…" : sug ? <>AI brief, <Ago iso={sug.created_at} /></> : "a one-page brief on this rollout, for whoever takes it over or joins"}
          </span>
        </h2>
        {sug && !working && <Button size="sm" variant="ghost" className="h-7" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</Button>}
        {s.available && !working && <Button size="sm" variant="outline" className="h-7" loading={busy} onClick={() => void ask()}>{sug ? "Brief me again" : "Brief me"}</Button>}
        {working && s.job && <Button size="sm" variant="ghost" className="h-7" onClick={() => void cancelAIJob(projectId, s.job!.id).then(load).catch((e: unknown) => setError(e instanceof ApiError ? e.message : "That did not work"))}>Cancel</Button>}
      </div>
      {working && s.job && <AIProgress job={s.job} />}
      {error && <p className="mt-2 text-[13px] text-destructive" role="alert">{error}</p>}
      {sug && open && !working && (
        <div className="mt-3 grid grid-cols-1 gap-3 text-[13px] leading-relaxed lg:grid-cols-2 [&>*]:min-w-0">
          <div className="grid grid-cols-1 content-start gap-2">
            <p>{sug.payload.where_it_stands}</p>
            <p className="text-muted-foreground">{sug.payload.who_is_who}</p>
            <p>{sug.payload.what_changed}</p>
          </div>
          <div className="grid grid-cols-1 content-start gap-3">
            {list("Waiting", sug.payload.waiting)}
            {list("Watch out", sug.payload.watch_out)}
          </div>
          <p className="text-[12px] text-muted-foreground lg:col-span-2">Written by AI from this rollout's facts{sug.model ? ` (${sug.model})` : ""}; the waiting list is Odin's own. Check anything you act on.</p>
        </div>
      )}
    </section>
  )
}
