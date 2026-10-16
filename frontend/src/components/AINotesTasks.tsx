import { useEffect, useState } from "react"
import { checkbox, fieldArea } from "@/lib/ui"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { PanelTitle } from "@/components/PanelTitle"
import { AIProgress } from "@/components/AIProgress"
import { addTask, ApiError, cancelAIJob, closeAISuggestion, dismissAISuggestion, requestProjectAI, type MinutesTask } from "@/lib/api"
import { fmtDate } from "@/lib/format"
import { Notice } from "@/components/Notice"
import { useProjectAI } from "@/lib/usePoll"
import { useAction } from "@/lib/useAction"

// Meeting notes to tasks: paste the minutes; the AI lists the actions agreed
// in them, each with the words that say so. Owners come only from this
// project's team, stages only from its list, due dates are read by Odin.
// Ticked ones are added through the normal task route.
export function AINotesTasks({ projectId }: { projectId: number }) {
  const { s, load, working, poll } = useProjectAI<{ tasks: MinutesTask[] }>(projectId, "notes_to_tasks")
  const [text, setText] = useState("")
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const { busy, note, setNote, act } = useAction(load)
  const sug = s?.suggestion
  // a new suggestion starts with every action ticked
  useEffect(() => { if (sug) setPicked(new Set(sug.payload.tasks.map((_, i) => i))) }, [sug?.id])   // eslint-disable-line react-hooks/exhaustive-deps
  if (!s || (!s.available && !sug)) return null
  const lastJob = s.job && !working && s.job.created_at > (sug?.created_at ?? "") ? s.job : null
  const find = () => act(async () => { await requestProjectAI(projectId, "notes_to_tasks", { text }); setText("") })
  // one by one through the task route; a failure part-way says how many went in
  const add = (from: NonNullable<typeof sug>) => act(async () => {
    let taken = 0
    try {
      for (const [i, t] of from.payload.tasks.entries()) {
        if (!picked.has(i)) continue
        await addTask(projectId, { title: t.title, stage: t.stage ?? "", assignee_id: t.assignee_id, due_date: t.due_date })
        taken += 1
      }
    } catch (e) {
      if (taken) await closeAISuggestion(projectId, from.id, taken).catch(() => undefined)
      throw new ApiError(0, `${taken} added, then: ${e instanceof ApiError ? e.message : "that did not save"}`)
    }
    await closeAISuggestion(projectId, from.id, taken)
    setNote({ text: `${taken} task${taken === 1 ? "" : "s"} added.` })
  })
  return (
    <section className="panel p-4" aria-labelledby="minutes-h">
      <PanelTitle n={false} id="minutes-h" className="mb-0" icon={<Sparkles className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />} hint="paste the minutes; the AI lists the actions agreed in them">Tasks from meeting notes</PanelTitle>
      {!sug && !working && s.available && (
        <div className="mt-2 grid grid-cols-1 gap-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={3500} aria-label="Meeting minutes"
            placeholder={"e.g. Omar to cable the Site B racks by 13 Oct.\nAnn will send the log samples by Friday."}
            className={fieldArea} />
          <div><Button size="sm" variant="outline" loading={busy} disabled={text.trim().length < 20} onClick={() => void find()}>Find the actions</Button></div>
        </div>
      )}
      <div aria-live="polite" className="text-[13px]">
        {working && s.job && <AIProgress job={s.job} poll={poll} doing="Reading the minutes" />}
        {working && <div className="mt-2 flex items-center gap-3 text-muted-foreground">
          {s.job && <Button size="sm" variant="ghost" onClick={() => void act(() => cancelAIJob(projectId, s.job!.id))}>Cancel</Button>}</div>}
        {lastJob?.status === "failed" && <Notice bad className="mt-2">That did not finish: {lastJob.error}</Notice>}
        {lastJob?.result?.skipped && <Notice className="mt-2">{lastJob.result.skipped}</Notice>}
        {note && <Notice bad={note.bad} className="mt-2">{note.text}</Notice>}
      </div>
      {sug && !working && (
        <div className="mt-2">
          {sug.payload.tasks.length === 0 ? <Notice>No actions found in those minutes.</Notice> : (
            <ul className="divide-y divide-border text-[13px]">
              {sug.payload.tasks.map((t, i) => (
                <li key={i} className="flex items-start gap-2 py-2">
                  <input type="checkbox" className={`mt-1 ${checkbox}`} checked={picked.has(i)} aria-label={`Add ${t.title}`}
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
            {sug.payload.tasks.length > 0 && <Button size="sm" loading={busy} disabled={picked.size === 0} onClick={() => void add(sug)}>Add {picked.size} task{picked.size === 1 ? "" : "s"}</Button>}
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => dismissAISuggestion(projectId, sug.id))}>{sug.payload.tasks.length ? "Dismiss" : "Clear"}</Button>
          </div>
        </div>
      )}
    </section>
  )
}
