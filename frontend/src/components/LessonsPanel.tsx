import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Sparkles, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ApiError, cancelAIJob, deleteLesson, dismissAISuggestion, lessonsOf, projectAI, requestProjectAI, saveLessons, saveRaid,
  type Lesson, type LessonsData, type ProjectAI } from "@/lib/api"

const KIND = { avoid: "Avoid", repeat: "Repeat" } as const

// Lessons: what this rollout taught (saved to the library, drafted by the AI
// from its history with evidence, ticked by the project manager), and what
// the most similar past rollouts taught, with the risks that hit them, so
// they can be logged here on day one. Similarity is plain matching (product,
// template, vendor, client), not the AI.
export function LessonsPanel({ projectId }: { projectId: number }) {
  const [d, setD] = useState<LessonsData | null>(null)
  const [s, setS] = useState<ProjectAI<{ lessons: Lesson[] }> | null>(null)
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const load = useCallback(async () => {
    try { setD(await lessonsOf(projectId)) } catch { setD(null) }
    try {
      const x = await projectAI<{ lessons: Lesson[] }>(projectId, "lessons")
      setS(x)
      if (x.suggestion) setPicked(new Set(x.suggestion.payload.lessons.map((_, i) => i)))
    } catch { setS(null) }
  }, [projectId])
  useEffect(() => { void load() }, [load])
  const drafting = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  useEffect(() => {
    if (!drafting) return
    const t = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(t)
  }, [drafting, load])
  if (!d) return null
  const sug = s?.suggestion
  const showAI = !!s && (s.available || !!sug)
  if (d.lessons.length === 0 && d.similar.length === 0 && !showAI) return null
  async function act(fn: () => Promise<unknown>, done?: string) {
    setBusy(true); setNote(null)
    try { await fn(); if (done) setNote(done); await load() } catch (e) { setNote(e instanceof ApiError ? e.message : "That did not work") } finally { setBusy(false) }
  }
  return (
    <section className="panel p-4" aria-labelledby="lessons-h">
      <h2 id="lessons-h" className="text-[13px] font-semibold text-nav-fg">Lessons<span className="sr-only">, </span><span className="ml-2 font-normal text-muted-foreground">what this rollout taught, and what similar ones did</span></h2>
      {note && <p className="mt-2 text-[13px] text-muted-foreground" role="status">{note}</p>}
      {d.lessons.length > 0 && (
        <ul className="mt-2 divide-y divide-border text-[13px]">
          {d.lessons.map((l) => (
            <li key={l.id} className="flex items-start gap-2 py-2">
              <span className={l.kind === "avoid" ? "w-14 shrink-0 text-[12px] font-medium text-warn" : "w-14 shrink-0 text-[12px] font-medium text-ok"}>{KIND[l.kind]}</span>
              <span className="min-w-0 flex-1">{l.text}</span>
              {d.can_edit && <button type="button" disabled={busy} onClick={() => void act(() => deleteLesson(projectId, l.id))} aria-label={`Delete lesson: ${l.text}`} className="text-muted-foreground hover:text-bad"><Trash2 className="h-3.5 w-3.5" /></button>}
            </li>
          ))}
        </ul>
      )}
      {showAI && d.can_edit && s && (
        <div className="mt-3 rounded-lg bg-muted/60 px-3 py-2 text-[13px]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
            <span className="min-w-0 flex-1" aria-live="polite">{drafting ? "Reading the rollout's history… about a minute." : sug ? "AI draft: tick the lessons worth keeping, then save them to the library." : "Draft this rollout's lessons with AI from its plan changes, overruns, risks, scope and notes."}</span>
            {s.available && !drafting && <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => void act(() => requestProjectAI(projectId, "lessons"))}>{sug ? "Draft again" : "Draft lessons"}</Button>}
            {drafting && s.job && <Button size="sm" variant="ghost" className="h-7" onClick={() => void act(() => cancelAIJob(projectId, s.job!.id))}>Cancel</Button>}
          </div>
          {sug && !drafting && (
            <div className="mt-2 border-t border-border pt-2">
              <ul className="grid grid-cols-1 gap-2">
                {sug.payload.lessons.map((l, i) => (
                  <li key={i}><label className="flex items-start gap-2">
                    <input type="checkbox" className="mt-1 h-3.5 w-3.5 accent-primary" checked={picked.has(i)} onChange={() => setPicked((p) => { const n = new Set(p); if (n.has(i)) n.delete(i); else n.add(i); return n })} />
                    <span><span className="font-medium">{KIND[l.kind]}:</span> {l.text}{l.evidence && <q className="block text-[12px] italic text-muted-foreground">{l.evidence}</q>}</span>
                  </label></li>
                ))}
              </ul>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button size="sm" className="h-7" disabled={busy || picked.size === 0} onClick={() => void act(() => saveLessons(projectId, sug.payload.lessons.filter((_, i) => picked.has(i)), sug.id), "Saved to the lessons library.")}>Save {picked.size} to the library</Button>
                <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void act(() => dismissAISuggestion(projectId, sug.id))}>Dismiss</Button>
              </div>
            </div>
          )}
        </div>
      )}
      {d.similar.length > 0 && (
        <div className="mt-3 border-t border-border pt-3">
          <h3 className="text-[12px] font-semibold text-nav-fg">From similar rollouts</h3>
          <ul className="mt-1 grid grid-cols-1 gap-3 text-[13px]">
            {d.similar.map((r) => (
              <li key={r.id}>
                <Link to={`/projects/${r.id}`} className="font-medium hover:underline">{r.name}</Link>
                <span className="text-[12px] text-muted-foreground"> · {r.why.join(", ")} · {r.stage}</span>
                <ul className="mt-1 grid grid-cols-1 gap-1">
                  {[...r.lessons.map((l) => ({ label: `${KIND[l.kind]}: ${l.text}`, title: l.text, detail: `Lesson from ${r.name}: ${l.text}` })),
                    ...r.risks.map((x) => ({ label: `Hit them: ${x.title} (${x.kind}${x.resolution ? `; ${x.resolution}` : ""})`, title: x.title, detail: `Hit ${r.name}: ${x.title}${x.resolution ? `. Resolved: ${x.resolution}` : ""}` }))].map((x) => (
                    <li key={x.label} className="flex items-start gap-2">
                      <span className="min-w-0 flex-1 text-[13px]">{x.label}</span>
                      {d.can_add_risk && <Button size="sm" variant="ghost" className="h-6 px-2 text-[12px]" disabled={busy}
                        onClick={() => void act(() => saveRaid(projectId, { kind: "risk", title: x.title.slice(0, 200), detail: x.detail, impact: "medium", likelihood: "medium" }), "Added to this rollout's RAID register.")}>Add as a risk here</Button>}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
