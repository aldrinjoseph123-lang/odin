import { useCallback, useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Ago } from "@/components/Ago"
import { cancelAIJob, projectAI, requestProjectAI, type CatchUp, type ProjectAI } from "@/lib/api"

// Catch me up: a one-page brief on this rollout for whoever takes it over or
// joins. Who waits on whom is Odin's own list; the rest is written by the AI
// from the rollout's facts. Hidden when the AI cannot run and no brief exists.
export function AICatchUp({ projectId }: { projectId: number }) {
  const [s, setS] = useState<ProjectAI<CatchUp> | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const load = useCallback(async () => {
    try { setS(await projectAI<CatchUp>(projectId, "catch_up")) } catch { setS(null) }
  }, [projectId])
  useEffect(() => { void load() }, [load])
  const working = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  useEffect(() => {
    if (!working) return
    const t = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(t)
  }, [working, load])
  if (!s || (!s.available && !s.suggestion)) return null
  const sug = s.suggestion
  async function ask() {
    setBusy(true); setOpen(true)
    try { await requestProjectAI(projectId, "catch_up"); await load() } finally { setBusy(false) }
  }
  const list = (title: string, items: string[]) => items.length > 0 && (
    <section><h3 className="text-[12px] font-semibold text-nav-fg">{title}</h3><ul className="mt-0.5 list-disc pl-5">{items.map((x) => <li key={x}>{x}</li>)}</ul></section>
  )
  return (
    <section className="panel p-4" aria-labelledby="catchup-h">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
        <h2 id="catchup-h" className="min-w-0 flex-1 basis-56 text-[13px] font-semibold text-nav-fg">
          Catch me up<span className="sr-only">, </span>
          <span className="ml-2 font-normal text-muted-foreground" aria-live="polite">
            {working ? "Reading the rollout… about two minutes." : sug ? <>AI brief, <Ago iso={sug.created_at} /></> : "a one-page brief on this rollout, for whoever takes it over or joins"}
          </span>
        </h2>
        {sug && !working && <Button size="sm" variant="ghost" className="h-7" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</Button>}
        {s.available && !working && <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => void ask()}>{sug ? "Brief me again" : "Brief me"}</Button>}
        {working && s.job && <Button size="sm" variant="ghost" className="h-7" onClick={() => void cancelAIJob(projectId, s.job!.id).then(load)}>Cancel</Button>}
      </div>
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
