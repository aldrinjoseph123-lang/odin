import { useCallback, useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { addTask, ApiError, cancelAIJob, closeAISuggestion, dismissAISuggestion, projectAI, requestProjectAI, type MinutesTask, type ProjectAI } from "@/lib/api"
import { fmtDate } from "@/lib/format"

// Meeting notes to tasks: paste the minutes; the AI lists the actions agreed
// in them, each with the words that say so. Owners come only from this
// project's team, stages only from its list, due dates are read by Odin.
// Ticked ones are added through the normal task route.
export function AINotesTasks({ projectId }: { projectId: number }) {
  const [s, setS] = useState<ProjectAI<{ tasks: MinutesTask[] }> | null>(null)
  const [text, setText] = useState("")
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const load = useCallback(async () => {
    try {
      const x = await projectAI<{ tasks: MinutesTask[] }>(projectId, "notes_to_tasks")
      setS(x)
      if (x.suggestion) setPicked(new Set(x.suggestion.payload.tasks.map((_, i) => i)))
    } catch { setS(null) }
  }, [projectId])
  useEffect(() => { void load() }, [load])
  const working = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  useEffect(() => {
    if (!working) return
    const t = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(t)
  }, [working, load])
  if (!s || (!s.available && !s.suggestion)) return null
  const sug = s.suggestion
  const lastJob = s.job && !working && s.job.created_at > (sug?.created_at ?? "") ? s.job : null
  async function find() {
    setBusy(true); setNote(null)
    try { await requestProjectAI(projectId, "notes_to_tasks", { text }); setText(""); await load() } catch (e) { setNote(e instanceof ApiError ? e.message : "Could not ask") } finally { setBusy(false) }
  }
  async function add() {
    if (!sug) return
    setBusy(true); setNote(null)
    let taken = 0
    try {
      for (const [i, t] of sug.payload.tasks.entries()) {
        if (!picked.has(i)) continue
        await addTask(projectId, { title: t.title, stage: t.stage ?? "", assignee_id: t.assignee_id, due_date: t.due_date })
        taken += 1
      }
      await closeAISuggestion(projectId, sug.id, taken)
      setNote(`${taken} task${taken === 1 ? "" : "s"} added.`)
      await load()
    } catch (e) {
      setNote(`${taken} added, then: ${e instanceof ApiError ? e.message : "that did not save"}`)
      if (taken) await closeAISuggestion(projectId, sug.id, taken).catch(() => undefined)
      await load()
    } finally { setBusy(false) }
  }
  return (
    <section className="panel p-4" aria-labelledby="minutes-h">
      <h2 id="minutes-h" className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12.5px] font-semibold text-nav-fg">
        <Sparkles className="h-3.5 w-3.5 text-primary-text" aria-hidden />Tasks from meeting notes<span className="sr-only">, </span>
        <span className="font-normal text-muted-foreground">paste the minutes; the AI lists the actions agreed in them</span>
      </h2>
      {!sug && !working && s.available && (
        <div className="mt-2 grid grid-cols-1 gap-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={3500} aria-label="Meeting minutes"
            placeholder={"e.g. Omar to cable the Site B racks by 13 Oct.\nAnn will send the log samples by Friday."}
            className="w-full rounded-md border border-input bg-background p-2 text-[13px] leading-relaxed" />
          <div><Button size="sm" variant="outline" className="h-7" disabled={busy || text.trim().length < 20} onClick={() => void find()}>Find the actions</Button></div>
        </div>
      )}
      <div aria-live="polite" className="text-[13px]">
        {working && <div className="mt-2 flex items-center gap-3 text-muted-foreground">Reading the minutes… about a minute.
          {s.job && <Button size="sm" variant="ghost" className="h-7" onClick={() => void cancelAIJob(projectId, s.job!.id).then(load)}>Cancel</Button>}</div>}
        {lastJob?.status === "failed" && <p className="mt-2 text-bad">That did not finish: {lastJob.error}</p>}
        {lastJob?.result?.skipped && <p className="mt-2 text-muted-foreground">{lastJob.result.skipped}</p>}
        {note && <p className="mt-2 text-muted-foreground" role="status">{note}</p>}
      </div>
      {sug && !working && (
        <div className="mt-2">
          {sug.payload.tasks.length === 0 ? <p className="text-[13px] text-muted-foreground">No actions found in those minutes.</p> : (
            <ul className="divide-y divide-border text-[13px]">
              {sug.payload.tasks.map((t, i) => (
                <li key={i} className="flex items-start gap-2 py-1.5">
                  <input type="checkbox" className="mt-1 h-3.5 w-3.5 accent-primary" checked={picked.has(i)} aria-label={`Add ${t.title}`}
                    onChange={() => setPicked((p) => { const n = new Set(p); if (n.has(i)) n.delete(i); else n.add(i); return n })} />
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{t.title}</span>
                    <span className="block text-[12px] text-muted-foreground">{t.owner ?? "nobody yet"} · {t.stage ?? "current stage"}{t.due_date ? ` · due ${fmtDate(t.due_date)}` : t.due_text ? ` · "${t.due_text}" (not a date Odin could read)` : ""}</span>
                    <q className="block text-[12px] italic text-muted-foreground">{t.quote}</q>
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {sug.payload.tasks.length > 0 && <Button size="sm" className="h-7" disabled={busy || picked.size === 0} onClick={() => void add()}>Add {picked.size} task{picked.size === 1 ? "" : "s"}</Button>}
            <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void dismissAISuggestion(projectId, sug.id).then(load)}>{sug.payload.tasks.length ? "Dismiss" : "Clear"}</Button>
          </div>
        </div>
      )}
    </section>
  )
}
