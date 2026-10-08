import { useCallback, useEffect, useMemo, useState } from "react"
import { CalendarRange, History, Wand2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { PlanGantt, RagPill } from "@/components/PlanGantt"
import { Ago } from "@/components/Ago"
import { AIHealthWhy } from "@/components/AIHealthWhy"
import { ApiError, plan as loadPlan, rebaseline, savePlan, type PlanData } from "@/lib/api"
import { fillSuggested, setDate, workDays, type PlanRow } from "@/lib/plan"
import { cn } from "@/lib/utils"
import { fmtDate } from "@/lib/format"

// The rollout's plan on its project page: health up top, the Gantt, then the
// dates per stage (editable for the project manager), the baseline controls
// and the log of what moved. Saving the first plan freezes it as the baseline.
const input = "h-8 w-[8.5rem] rounded-md border border-input bg-background px-2 text-[13px] tabular-nums disabled:opacity-60"
const slipText = (n: number | null) => (n == null ? "—" : n === 0 ? "on plan" : n > 0 ? `${n} d late` : `${-n} d early`)

export function PlanPanel({ projectId, onSaved }: { projectId: number; onSaved?: () => void }) {
  const [d, setD] = useState<PlanData | null>(null)
  const [rows, setRows] = useState<(PlanRow & { name: string })[]>([])
  const [cascade, setCascade] = useState(true)
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ text: string; bad?: boolean } | null>(null)
  const [rebase, setRebase] = useState<string | null>(null)
  const [log, setLog] = useState(false)
  const load = useCallback(async () => {
    const x = await loadPlan(projectId)
    setD(x)
    setRows(x.stages.map((s) => ({ id: s.id, name: s.name, plan_start: s.plan_start, plan_end: s.plan_end, suggested_start: s.suggested_start, suggested_end: s.suggested_end })))
  }, [projectId])
  useEffect(() => { load().catch(() => setNotice({ text: "Could not load the plan", bad: true })) }, [load])
  const dirty = useMemo(() => !!d && rows.some((r, i) => r.plan_start !== d.stages[i].plan_start || r.plan_end !== d.stages[i].plan_end), [d, rows])
  if (!d) return <p className="text-[13px] text-muted-foreground">Loading the plan…</p>

  async function run(fn: () => Promise<string>) {
    setBusy(true); setNotice(null)
    try { const text = await fn(); await load(); setNotice({ text }); onSaved?.() } catch (e) { setNotice({ text: e instanceof ApiError ? e.message : "That did not save", bad: true }) } finally { setBusy(false) }
  }
  const save = () => run(async () => {
    const r = await savePlan(projectId, rows.map(({ id, plan_start, plan_end }) => ({ id, plan_start, plan_end })), reason.trim())
    setReason("")
    return r.baselined ? "Plan saved and frozen as the baseline." : `Plan saved: ${r.changed} date${r.changed === 1 ? "" : "s"} moved.`
  })
  const f = d.finish
  const tiles: { label: string; value: string; sub?: string; tone?: "bad" | "warn" | "ok" }[] = [
    { label: "Forecast finish", value: f.forecast ? fmtDate(f.forecast) : "—", sub: f.vs_target_days == null ? "no target date" : f.vs_target_days > 0 ? `${f.vs_target_days} d after target` : `${-f.vs_target_days} d before target`, tone: f.vs_target_days != null && f.vs_target_days > 0 ? "bad" : "ok" },
    { label: "Target", value: f.target ? fmtDate(f.target) : "—", sub: f.days_to_target == null ? "" : f.days_to_target < 0 ? `${-f.days_to_target} d ago` : `${f.days_to_target} d to go` },
    { label: "Against baseline", value: f.vs_baseline_days == null ? "—" : slipText(f.vs_baseline_days), sub: d.baseline_at ? `baseline of ${fmtDate(d.baseline_at)}` : "no baseline yet", tone: f.vs_baseline_days && f.vs_baseline_days > 0 ? "warn" : undefined },
    { label: "Complete", value: `${d.pct_complete}%`, sub: `confidence ${d.health.confidence}` },
  ]
  return (
    <div>
      <div className="flex flex-wrap items-start gap-3">
        <RagPill rag={d.health.rag} />
        <ul className="min-w-0 flex-1 text-[13px] text-muted-foreground">{d.health.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      </div>
      <AIHealthWhy projectId={projectId} rag={d.health.rag} />
      <div className="mt-3 grid grid-cols-2 gap-3 xl:grid-cols-4">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-xl bg-muted/50 p-3">
            <div className="text-[12px] text-muted-foreground">{t.label}</div>
            <div className={cn("mt-1 text-[17px] font-semibold leading-none", t.tone === "bad" && "text-bad", t.tone === "warn" && "text-warn")}>{t.value}</div>
            {t.sub && <div className="mt-1 text-[12px] text-muted-foreground">{t.sub}</div>}
          </div>
        ))}
      </div>

      <div className="mt-4"><PlanGantt stages={d.stages} today={d.today} target={f.target} /></div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-[13px]">
          <thead><tr className="border-b border-border text-left text-[12px] text-muted-foreground">
            {["Stage", "Planned start", "Planned end", d.calendar?.working ? "Work days" : "Days", "SLA", "Actual", "Forecast end", "Slip"].map((h) => <th key={h} className="px-2 py-2 font-normal">{h}</th>)}
          </tr></thead>
          <tbody>
            {d.stages.map((s, i) => {
              const r = rows[i]
              const days = r.plan_start && r.plan_end ? workDays(r.plan_start, r.plan_end, d.calendar) : null
              return (
                <tr key={s.id} className={cn("border-b border-border last:border-0", s.status === "current" && "bg-accent/40")}>
                  <td className="px-2 py-2 font-medium">{s.name}{s.status === "current" && <span className="ml-2 text-[11px] font-normal text-primary-text">now</span>}</td>
                  <td className="px-2 py-1"><input type="date" aria-label={`${s.name} planned start`} className={input} disabled={!d.can_edit || busy} value={r.plan_start ?? ""} placeholder={s.suggested_start}
                    onChange={(e) => e.target.value && setRows(setDate(rows, i, "plan_start", e.target.value, cascade))} /></td>
                  <td className="px-2 py-1"><input type="date" aria-label={`${s.name} planned end`} className={input} disabled={!d.can_edit || busy} value={r.plan_end ?? ""}
                    onChange={(e) => e.target.value && setRows(setDate(rows, i, "plan_end", e.target.value, cascade))} /></td>
                  <td className="px-2 py-2 tabular-nums text-muted-foreground">{days ?? "—"}</td>
                  <td className="px-2 py-2 tabular-nums text-muted-foreground">{s.sla_days ? `${s.sla_days} d` : "—"}</td>
                  <td className="px-2 py-2 text-muted-foreground">{s.actual_start ? `${fmtDate(s.actual_start)}${s.actual_end ? ` → ${fmtDate(s.actual_end)}` : " → now"}` : s.status === "skipped" ? "skipped" : "—"}</td>
                  <td className="px-2 py-2">{s.forecast_end ? fmtDate(s.forecast_end) : "—"}</td>
                  <td className={cn("px-2 py-2 whitespace-nowrap", s.slip_days && s.slip_days > 0 ? "font-medium text-bad" : "text-muted-foreground")}>{slipText(s.slip_days)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {d.can_edit && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" className="rounded-full" disabled={busy} onClick={() => setRows(fillSuggested(rows))}><Wand2 className="h-3.5 w-3.5" /> Fill the gaps from SLAs</Button>
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground"><input type="checkbox" checked={cascade} onChange={(e) => setCascade(e.target.checked)} className="accent-primary" /> Move later stages with it</label>
          {d.baseline_at && dirty && <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why the dates move (goes in the log)" aria-label="Why the dates move" maxLength={300} className="h-8 min-w-60 flex-1 rounded-md border border-input bg-background px-2 text-[13px]" />}
          <span className="ml-auto flex gap-2">
            {dirty && <Button size="sm" variant="ghost" className="rounded-full" disabled={busy} onClick={() => load()}>Discard</Button>}
            <Button size="sm" className="rounded-full" loading={busy} disabled={!dirty} onClick={save}><CalendarRange className="h-3.5 w-3.5" /> {d.baseline_at ? "Save plan" : "Save plan and set baseline"}</Button>
            {d.baseline_at && <Button size="sm" variant="outline" className="rounded-full" disabled={busy || dirty} onClick={() => setRebase("")}>Re-baseline</Button>}
          </span>
        </div>
      )}
      {notice && <p className={cn("mt-2 text-[13px]", notice.bad ? "text-bad" : "text-muted-foreground")} role="status">{notice.text}</p>}

      {d.changes.length > 0 && (
        <div className="mt-3">
          <button type="button" onClick={() => setLog(!log)} aria-expanded={log} className="flex items-center gap-2 text-[13px] text-muted-foreground hover:text-foreground"><History className="h-3.5 w-3.5" />{log ? "Hide" : "Show"} what moved ({d.changes.length})</button>
          {log && (
            <ul className="mt-2 divide-y divide-border text-[13px]">
              {d.changes.map((c, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-x-2 py-2">
                  {c.field === "baseline" ? <span className="font-medium">Re-baselined</span> : <span><span className="font-medium">{c.stage}</span> {c.field} {c.old ? fmtDate(c.old) : "unset"} → {c.new ? fmtDate(c.new) : "unset"}</span>}
                  {c.reason && <span className="text-muted-foreground">— {c.reason}</span>}
                  <span className="ml-auto text-[12px] text-muted-foreground">{c.author} · <Ago iso={c.created_at} /></span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <Dialog open={rebase !== null} onOpenChange={(o) => { if (!o) setRebase(null) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Re-baseline the plan</DialogTitle><DialogDescription>The current plan becomes what the rollout is measured against from now on. The old baseline stays in the log.</DialogDescription></DialogHeader>
          <label htmlFor="rebase-reason" className="text-[13px] font-medium">Why</label>
          <input id="rebase-reason" autoFocus value={rebase ?? ""} onChange={(e) => setRebase(e.target.value)} maxLength={300} placeholder="Scope change agreed with the customer on 3 Oct" className="h-8 rounded-md border border-input bg-background px-2 text-[13px]" />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" className="rounded-full" onClick={() => setRebase(null)}>Cancel</Button>
            <Button size="sm" className="rounded-full" disabled={busy || !rebase?.trim()} onClick={() => { const why = rebase!.trim(); setRebase(null); void run(async () => { await rebaseline(projectId, why); return "The current plan is the new baseline." }) }}>Re-baseline</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
