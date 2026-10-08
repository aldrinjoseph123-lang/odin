import { useCallback, useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ApiError, cancelAIJob, decideAIProposal, projectAI, requestProjectAI, type ProjectAI, type RaidProposal, type RaidProposals } from "@/lib/api"
import { fmtWhen } from "@/lib/format"
import { RAID_KIND } from "@/components/RaidPanel"

// Risks proposed: what the notes imply but nobody logged. Each proposal shows
// the note words behind it; Add opens the register's own dialog filled in, so
// the item is saved (and audited) exactly like one typed by hand. Shown only
// when the AI can run here or proposals are waiting.
export function AIRaidProposals({ projectId, refresh, onAdd }: { projectId: number; refresh: number; onAdd: (p: RaidProposal, suggestion: number, index: number) => void }) {
  const [s, setS] = useState<ProjectAI<RaidProposals> | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try { setS(await projectAI<RaidProposals>(projectId, "raid_proposals")) } catch { setS(null) }
  }, [projectId])
  useEffect(() => { void load() }, [load, refresh])
  const looking = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  useEffect(() => {
    if (!looking) return
    const t = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(t)
  }, [looking, load])
  if (!s || (!s.available && !s.suggestion)) return null
  const sug = s.suggestion
  const open = sug ? sug.payload.proposals.map((p, i) => [p, i] as const).filter(([, i]) => !sug.payload.decisions?.[String(i)]) : []
  const lastJob = s.job && !looking && s.job.created_at > (sug?.created_at ?? "") ? s.job : null

  async function look() {
    setBusy(true); setError(null)
    try { await requestProjectAI(projectId, "raid_proposals"); await load() } catch (e) { setError(e instanceof ApiError ? e.message : "Could not ask") } finally { setBusy(false) }
  }
  async function dismiss(i: number) {
    if (!sug) return
    setBusy(true)
    try { await decideAIProposal(projectId, sug.id, i, "dismissed"); await load() } finally { setBusy(false) }
  }
  return (
    <div className="mt-2 rounded-lg bg-muted/60 px-3 py-2 text-[13px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary-text" aria-hidden />
        <span className="min-w-0 flex-1" aria-live="polite">
          {looking ? "Reading the last two weeks of notes for anything not yet logged… about a minute."
            : sug && open.length ? <>AI found {open.length} thing{open.length === 1 ? "" : "s"} the notes mention that the register does not ({fmtWhen(sug.created_at)}{sug.model ? ` · ${sug.model}` : ""}).</>
              : sug ? "Nothing new in the notes that the register does not already hold."
                : "Look through the last two weeks of notes with AI for risks, issues and decisions nobody has logged."}
          {lastJob?.status === "failed" && <span className="block text-bad">The last look did not finish: {lastJob.error}</span>}
          {error && <span className="block text-bad">{error}</span>}
        </span>
        {s.available && !looking && <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => void look()}>{sug ? "Look again" : "Look with AI"}</Button>}
        {looking && s.job && <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void cancelAIJob(projectId, s.job!.id).then(load)}>Cancel</Button>}
      </div>
      {sug && open.length > 0 && !looking && (
        <ul className="mt-2 divide-y divide-border border-t border-border">
          {open.map(([p, i]) => {
            const K = RAID_KIND[p.kind]
            return (
              <li key={i} className="flex items-start gap-3 py-2">
                <K.icon className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{p.title}</span>
                  <span className="block text-[12px] text-muted-foreground">{K.label} · {p.impact} impact{p.likelihood ? ` · ${p.likelihood} likelihood` : ""}. {p.detail}</span>
                  <q className="mt-1 block text-[12px] italic text-muted-foreground">{p.evidence}</q>
                </span>
                <span className="flex shrink-0 gap-1">
                  <Button size="sm" className="h-7" disabled={busy} onClick={() => onAdd(p, sug.id, i)}>Add</Button>
                  <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => void dismiss(i)} aria-label={`Dismiss ${p.title}`}>Dismiss</Button>
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
