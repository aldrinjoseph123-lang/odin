import { useCallback, useEffect, useState } from "react"
import { Copy, Mail, Sparkles } from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { ApiError, cancelAIJob, closeAISuggestion, dismissAISuggestion, projectAI, requestProjectAI, type ChaseDraft, type ProjectAI } from "@/lib/api"
import { fmtWhen, reminderText } from "@/lib/format"
import { cn } from "@/lib/utils"
import { usePoll } from "@/lib/usePoll"

// Waiting on the customer: what is waiting (Odin's own count), shown whenever
// something is, AI or not. A plain reminder can always be copied; when the AI
// can run, it drafts a chase email instead. Odin sends nothing.
export function AIChase({ projectId }: { projectId: number }) {
  const [s, setS] = useState<ProjectAI<ChaseDraft> | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const load = useCallback(async () => {
    try { setS(await projectAI<ChaseDraft>(projectId, "chase_draft")) } catch { setS(null) }
  }, [projectId])
  useEffect(() => { void load() }, [load])
  const drafting = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  usePoll(drafting, load)
  const waiting = s?.options?.waiting ?? []
  if (!s || waiting.length === 0) return null
  const ai = s.available || !!s.suggestion
  const sug = s.suggestion
  const contact = s.options?.contact
  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setNote(null)
    try { await fn(); await load() } catch (e) { setNote(e instanceof ApiError ? e.message : "That did not work") } finally { setBusy(false) }
  }
  async function copy() {
    if (!sug) return
    try { await navigator.clipboard.writeText(`${sug.payload.subject}\n\n${sug.payload.body}`); setNote("Copied: subject and body.") } catch { setNote("Select the text and copy it.") }
    void closeAISuggestion(projectId, sug.id, 1).catch(() => undefined)
  }
  async function copyReminder() {
    try { await navigator.clipboard.writeText(reminderText(waiting, contact?.name)); setNote("Copied a reminder. Paste it into your mail.") } catch { setNote("Could not copy: your browser blocked it.") }
  }
  const mailto = sug && contact?.email ? `mailto:${contact.email}?subject=${encodeURIComponent(sug.payload.subject)}&body=${encodeURIComponent(sug.payload.body)}` : null
  return (
    <section className="panel p-4" aria-labelledby="waiting-h">
      <h2 data-n id="waiting-h" className="mb-3 text-[12px] font-semibold text-nav-fg">Waiting on the customer<span className="sr-only">, </span><span className="ml-2 font-normal text-muted-foreground">{contact ? contact.name : "no customer contact on the team yet"}</span></h2>
      <ul className="grid grid-cols-1 gap-1 text-[13px]">
        {waiting.map((w) => (
          <li key={w.what} className="flex flex-wrap justify-between gap-x-3">
            <span className="font-medium">{w.what}</span>
            <span className="text-warn">{w.days_waiting != null ? `asked ${w.since}, ${w.days_waiting} d waiting` : `due ${w.due}, ${w.days_overdue} d overdue`}</span>
          </li>
        ))}
      </ul>
      {!ai && (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
          <Button size="sm" variant="outline" className="h-7" onClick={() => void copyReminder()}><Copy className="h-3.5 w-3.5" /> Copy a reminder</Button>
          {note && <span className="text-muted-foreground" role="status">{note}</span>}
        </div>
      )}
      {ai && <div className="mt-3 rounded-lg bg-muted/60 px-3 py-2 text-[13px]">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
          <span className="min-w-0 flex-1 basis-56" aria-live="polite">
            {drafting ? "Drafting a chase… about a minute."
              : sug ? <>AI draft, {fmtWhen(sug.created_at)}{sug.model ? ` · ${sug.model}` : ""}. Read it, then copy it or open it in your mail. Odin does not send it.</>
                : "Draft a short, polite chase email about these with AI."}
            {note && <span className="block text-muted-foreground" role="status">{note}</span>}
          </span>
          {s.available && !drafting && <Button size="sm" variant="outline" className="h-7" loading={busy} onClick={() => void act(() => requestProjectAI(projectId, "chase_draft"))}>{sug ? "Draft again" : "Draft a chase"}</Button>}
          {drafting && s.job && <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void act(() => cancelAIJob(projectId, s.job!.id))}>Cancel</Button>}
        </div>
        {sug && !drafting && (
          <div className="mt-2 border-t border-border pt-2">
            <p className="font-medium">{sug.payload.subject}</p>
            <p className="mt-1 whitespace-pre-line leading-relaxed">{sug.payload.body}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" className="h-7" onClick={() => void copy()}><Copy className="h-3.5 w-3.5" /> Copy</Button>
              {mailto && <a href={mailto} onClick={() => void closeAISuggestion(projectId, sug.id, 1).catch(() => undefined)} className={cn(buttonVariants({ size: "sm", variant: "outline" }), "h-7")}><Mail className="h-3.5 w-3.5" /> Open in mail</a>}
              <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void act(() => dismissAISuggestion(projectId, sug.id))}>Dismiss</Button>
            </div>
          </div>
        )}
      </div>}
    </section>
  )
}
