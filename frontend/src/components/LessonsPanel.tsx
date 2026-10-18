import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Sparkles, Trash2 } from "lucide-react"
import { checkbox } from "@/lib/ui"
import { Button } from "@/components/ui/button"
import { Tag } from "@/components/ui/tag"
import { AIProgress } from "@/components/AIProgress"
import { cancelAIJob, deleteLesson, dismissAISuggestion, lessonsOf, requestProjectAI, saveLessons, saveRaid, type Lesson } from "@/lib/api"
import { useProjectAI } from "@/lib/usePoll"
import { useLoad } from "@/lib/useLoad"
import { useAction } from "@/lib/useAction"
import { askConfirm } from "@/lib/confirm"
import { Notice } from "@/components/Notice"

const KIND = { avoid: "Avoid", repeat: "Repeat" } as const

// Lessons: what this rollout taught (saved to the library, drafted by the AI
// from its history with evidence, ticked by the project manager), and what
// the most similar past rollouts taught, with the risks that hit them, so
// they can be logged here on day one. Similarity is plain matching (product,
// template, vendor, client), not the AI.
export function LessonsPanel({ projectId }: { projectId: number }) {
  const { data: d, reload } = useLoad(`lessons:${projectId}`, () => lessonsOf(projectId))
  const { s, load, working: drafting, poll } = useProjectAI<{ lessons: Lesson[] }>(projectId, "lessons")
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const { busy, note, act } = useAction(useCallback(() => Promise.all([reload(), load()]), [reload, load]))
  const sug = s?.suggestion
  // a new draft starts with every lesson ticked
  useEffect(() => { if (sug) setPicked(new Set(sug.payload.lessons.map((_, i) => i))) }, [sug?.id])   // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return null
  const showAI = !!s && (s.available || !!sug)
  if (d.lessons.length === 0 && d.similar.length === 0 && !showAI) return null
  return (
    <section className="panel scroll-mt-16 p-4" id="lessons" aria-labelledby="lessons-h">
      {/* folded to one line: worth reaching for, not worth a screen every visit (critique 10 Oct) */}
      <details>
      <summary className="cursor-pointer list-none rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden">
        <h2 id="lessons-h" className="inline text-[12px] font-semibold text-nav-fg">Lessons<span className="sr-only">, </span><span className="ml-2 font-normal text-muted-foreground">{d.lessons.length} kept · {d.similar.length} similar rollout{d.similar.length === 1 ? "" : "s"} · show</span></h2>
      </summary>
      {note && <Notice bad={note.bad} className="mt-2">{note.text}</Notice>}
      {d.lessons.length > 0 && (
        <ul className="mt-2 divide-y divide-border text-[13px]">
          {d.lessons.map((l) => (
            <li key={l.id} className="flex items-start gap-2 py-2">
              <Tag kind="kind">{KIND[l.kind]}</Tag>
              <span className="min-w-0 flex-1">{l.text}</span>
              {d.can_edit && <Button type="button" variant="ghost" size="icon-sm" disabled={busy} onClick={async () => { if (await askConfirm("Delete this lesson? It leaves this rollout and the library that similar rollouts read.", "Delete")) void act(() => deleteLesson(projectId, l.id)) }} aria-label={`Delete lesson: ${l.text}`} className="-my-1 text-muted-foreground hover:text-destructive"><Trash2 className="size-3.5" /></Button>}
            </li>
          ))}
        </ul>
      )}
      {showAI && d.can_edit && s && (
        <div className="mt-3 rounded-lg bg-muted/60 px-3 py-2 text-[13px]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Sparkles className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <span className="min-w-0 flex-1 basis-56" aria-live="polite">{drafting ? "Reading the rollout's history…" : sug ? "AI draft: tick the lessons worth keeping, then save them to the library." : "Draft this rollout's lessons with AI from its plan changes, overruns, risks, scope and notes."}</span>
            {s.available && !drafting && <Button size="sm" variant="outline" loading={busy} onClick={() => void act(() => requestProjectAI(projectId, "lessons"))}>{sug ? "Draft again" : "Draft lessons"}</Button>}
            {drafting && s.job && <Button size="sm" variant="ghost" onClick={() => void act(() => cancelAIJob(projectId, s.job!.id))}>Cancel</Button>}
          </div>
          {drafting && s.job && <AIProgress job={s.job} poll={poll} />}
          {sug && !drafting && (
            <div className="mt-2 border-t border-border pt-2">
              <ul className="grid grid-cols-1 gap-2">
                {sug.payload.lessons.map((l, i) => (
                  <li key={i}><label className="flex items-start gap-2">
                    <input type="checkbox" className={`mt-1 ${checkbox}`} checked={picked.has(i)} onChange={() => setPicked((p) => { const n = new Set(p); if (n.has(i)) n.delete(i); else n.add(i); return n })} />
                    <span><span className="font-medium">{KIND[l.kind]}:</span> {l.text}{l.evidence && <q className="block text-[12px] italic text-muted-foreground">{l.evidence}</q>}</span>
                  </label></li>
                ))}
              </ul>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button size="sm" loading={busy} disabled={picked.size === 0} onClick={() => void act(() => saveLessons(projectId, sug.payload.lessons.filter((_, i) => picked.has(i)), sug.id), "Saved to the lessons library.")}>Save {picked.size} to the library</Button>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => dismissAISuggestion(projectId, sug.id))}>Dismiss</Button>
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
                    ...r.risks.map((x) => ({ label: `They hit: ${x.title} (${x.kind}${x.resolution ? `; ${x.resolution}` : ""})`, title: x.title, detail: `Hit ${r.name}: ${x.title}${x.resolution ? `. Resolved: ${x.resolution}` : ""}` }))].map((x) => (
                    <li key={x.label} className="flex items-start gap-2">
                      <span className="min-w-0 flex-1 text-[13px]">{x.label}</span>
                      {d.can_add_risk && <Button size="xs" variant="ghost" disabled={busy} aria-label={`Add “${x.title}” as a risk here`}
                        onClick={() => void act(() => saveRaid(projectId, { kind: "risk", title: x.title.slice(0, 200), detail: x.detail, impact: "medium", likelihood: "medium" }), "Added to this rollout's RAID register.")}>Add as a risk here</Button>}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}
      </details>
    </section>
  )
}
