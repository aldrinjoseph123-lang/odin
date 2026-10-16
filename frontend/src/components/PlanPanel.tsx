import { useEffect, useMemo, useRef, useState } from "react"
import { checkbox, td, th } from "@/lib/ui"
import { Input } from "@/components/ui/input"
import { Field } from "@/components/ui/field"
import { CalendarRange, History, Link2, Wand2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { PlanGantt } from "@/components/PlanGantt"
import { Ago } from "@/components/Ago"
import { AIHealthWhy } from "@/components/AIHealthWhy"
import { ApiError, plan as loadPlan, rebaseline, savePlan } from "@/lib/api"
import { fillSuggested, setDate, workDays, type PlanRow } from "@/lib/plan"
import { cn } from "@/lib/utils"
import { DatePicker } from "@/components/DatePicker"
import { fmtDate, forecastTone } from "@/lib/format"
import { Notice } from "@/components/Notice"
import { LoadFailed } from "@/components/LoadFailed"
import { useLoad } from "@/lib/useLoad"

// The rollout's plan on its project page: health up top, the Gantt, then the
// dates per stage (editable for the project manager), the baseline controls
// and the log of what moved. Saving the first plan freezes it as the baseline.
const slipText = (n: number | null) => (n == null ? "—" : n === 0 ? "on plan" : n > 0 ? `${n} d late` : `${-n} d early`)

// `refresh` changes when something else on the page moves the health (a RAID item).
export function PlanPanel({ projectId, onSaved, refresh = 0 }: { projectId: number; onSaved?: () => void; refresh?: number }) {
  const { data: d, error: failed, reload } = useLoad(`plan:${projectId}`, () => loadPlan(projectId))
  const [rows, setRows] = useState<(PlanRow & { name: string })[]>([])
  const [cascade, setCascade] = useState(true)
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ text: string; bad?: boolean } | null>(null)
  const [rebase, setRebase] = useState<string | null>(null)
  const [log, setLog] = useState(false)
  const [editing, setEditing] = useState(false)   // dates are read until someone asks to edit them (critique 10 Oct)
  const typing = useRef(false)   // dates changed and not saved yet
  // `fresh` after a save; a refresh from elsewhere (a RAID item, a stage move)
  // keeps the dates being typed, on the same stages (review P3-38)
  const fresh = useRef(false)
  useEffect(() => {
    if (!d) return
    const next = d.stages.map((s) => ({ id: s.id, name: s.name, plan_start: s.plan_start, plan_end: s.plan_end, suggested_start: s.suggested_start, suggested_end: s.suggested_end }))
    setRows((cur) => !fresh.current && typing.current && cur.length === next.length && cur.every((r, i) => r.id === next[i].id)
      ? next.map((r, i) => ({ ...r, plan_start: cur[i].plan_start, plan_end: cur[i].plan_end })) : next)
    fresh.current = false
  }, [d])
  useEffect(() => { if (refresh) void reload() }, [refresh, reload])
  const dirty = useMemo(() => !!d && rows.some((r, i) => r.plan_start !== d.stages[i]?.plan_start || r.plan_end !== d.stages[i]?.plan_end), [d, rows])
  useEffect(() => { typing.current = dirty }, [dirty])
  if (!d) return failed ? <LoadFailed what="the plan" onRetry={() => void reload()} /> : <p className="text-[13px] text-muted-foreground">Loading the plan…</p>
  // a closed rollout's plan is history: shown, not edited
  const editable = d.can_edit && !d.closed
  const open = editable && (editing || !d.has_plan)   // with no plan yet, the table opens ready to fill

  async function run(fn: () => Promise<string>) {
    setBusy(true); setNotice(null)
    try { const text = await fn(); fresh.current = true; await reload(); setNotice({ text }); setEditing(false); onSaved?.() } catch (e) { setNotice({ text: e instanceof ApiError ? e.message : "That did not save", bad: true }) } finally { setBusy(false) }
  }
  // a click that finds nothing to do says so (review P3-40)
  function suggest() {
    const next = fillSuggested(rows)
    if (next.every((r, i) => r.plan_start === rows[i].plan_start && r.plan_end === rows[i].plan_end)) {
      setNotice({ text: rows.every((r) => r.plan_start && r.plan_end) ? "Every stage already has dates. Change one to move it." : "There is nothing to suggest yet: give the stages SLA days first." })
      return
    }
    setNotice(null); setRows(next)
  }
  const save = () => run(async () => {
    const r = await savePlan(projectId, rows.map(({ id, plan_start, plan_end }) => ({ id, plan_start, plan_end })), reason.trim())
    setReason("")
    const said = r.baselined ? "Plan saved and frozen as the baseline." : `Plan saved: ${r.changed} date${r.changed === 1 ? "" : "s"} moved.`
    return r.warning ? `${said} ${r.warning}` : said
  })
  const f = d.finish
  const tiles: { label: string; value: string; sub?: string; tone?: "bad" | "warn" | "ok" }[] = [
    { label: "Forecast finish", value: f.forecast ? fmtDate(f.forecast) : "—", sub: f.vs_target_days == null ? "no target date" : f.vs_target_days > 0 ? `${f.vs_target_days} d after target` : `${-f.vs_target_days} d before target`, tone: forecastTone(f.vs_target_days, f.target, d.today) },
    { label: "Target", value: f.target ? fmtDate(f.target) : "—", sub: f.days_to_target == null ? "" : f.days_to_target < 0 ? `${-f.days_to_target} d ago` : `${f.days_to_target} d to go` },
    { label: "Against baseline", value: f.vs_baseline_days == null ? "—" : slipText(f.vs_baseline_days), sub: d.baseline_at ? `baseline of ${fmtDate(d.baseline_at)}` : "no baseline yet", tone: f.vs_baseline_days && f.vs_baseline_days > 0 ? "warn" : undefined },
    { label: "Complete", value: `${d.pct_complete}%`, sub: `confidence ${d.health.confidence}` },
  ]
  return (
    <div>
      {/* the verdict and its first reason sit in the page's title row; here only the full list, when there is more */}
      {d.health.reasons.length > 1 && <ul className="min-w-0 text-[13px] text-muted-foreground">{d.health.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
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

      <div className="mt-4 overflow-x-auto" tabIndex={0} role="region" aria-label="Dates per stage">
        <table className="w-full min-w-[720px] border-collapse text-[13px]">
          <thead><tr className="border-b border-border text-left text-[12px] text-muted-foreground">
            {["Stage", "Planned start", "Planned end", d.calendar?.working ? "Work days" : "Days", "SLA", "Actual", "Forecast end", "Slip"].map((h) => <th key={h} className={th}>{h}</th>)}
          </tr></thead>
          <tbody>
            {d.stages.map((s, i) => {
              const r = rows[i] ?? s   // the rows catch up with a fresh plan one render later
              const days = r.plan_start && r.plan_end ? workDays(r.plan_start, r.plan_end, d.calendar) : null
              return (
                <tr key={s.id} className={cn("border-b border-border last:border-0", s.status === "current" && "bg-accent/40")}>
                  <td className={cn(td, "font-medium")}>{s.name}{s.status === "current" && <span className="ml-2 text-[12px] font-semibold text-foreground">now</span>}</td>
                  {open ? <>
                    <td className="px-3 py-1"><DatePicker label={`${s.name} planned start`} disabled={busy} value={r.plan_start ?? ""} placeholder={s.suggested_start ? fmtDate(s.suggested_start) : "—"} clearable={false}
                      onChange={(v) => v && setRows(setDate(rows, i, "plan_start", v, cascade))} className="h-8 w-40" /></td>
                    <td className="px-3 py-1"><DatePicker label={`${s.name} planned end`} disabled={busy} value={r.plan_end ?? ""} placeholder="—" clearable={false} min={r.plan_start ?? undefined}
                      onChange={(v) => v && setRows(setDate(rows, i, "plan_end", v, cascade))} className="h-8 w-40" /></td>
                  </> : <>
                    <td className={cn(td, "tabular-nums")}>{r.plan_start ? fmtDate(r.plan_start) : "—"}</td>
                    <td className={cn(td, "tabular-nums")}>{r.plan_end ? fmtDate(r.plan_end) : "—"}</td>
                  </>}
                  <td className={cn(td, "tabular-nums text-muted-foreground")}>{days ?? "—"}</td>
                  <td className={cn(td, "tabular-nums text-muted-foreground")}>{s.sla_days ? `${s.sla_days} d` : "—"}</td>
                  <td className={cn(td, "text-muted-foreground")}>{s.actual_start ? `${fmtDate(s.actual_start)}${s.actual_end ? ` – ${fmtDate(s.actual_end)}` : " – now"}` : s.status === "skipped" ? "skipped" : "—"}</td>
                  {/* a late predecessor moved it (services/task_links.py): the glyph, and the reason under the table */}
                  <td className={cn(td, "whitespace-nowrap")} title={s.forecast_reason ?? undefined}>{s.forecast_end ? fmtDate(s.forecast_end) : "—"}{s.forecast_reason && <><Link2 className="ml-1 inline h-3 w-3 text-warn" aria-hidden /><span className="sr-only"> (moved by a task it waits on)</span></>}</td>
                  {/* a finished stage's slip is history (muted); a running or coming stage that slips is amber;
                      red only once the target date itself has passed: red means overdue (critique 10 Oct) */}
                  <td className={cn(td, "whitespace-nowrap", s.slip_days && s.slip_days > 0 && s.status !== "done" ? (forecastTone(s.slip_days, f.target, d.today) === "bad" ? "font-medium text-bad" : "text-warn") : "text-muted-foreground")}>{slipText(s.slip_days)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {d.stages.filter((s) => s.forecast_reason).map((s) => (
        <p key={s.id} className="mt-2 flex items-start gap-1 text-[12px] text-muted-foreground"><Link2 className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />{s.forecast_reason}</p>
      ))}

      {editable && !open && <Button size="sm" variant="outline" className="mt-3" onClick={() => setEditing(true)}><CalendarRange className="h-3.5 w-3.5" /> Edit dates</Button>}
      {open && (
        <form className="mt-3 flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); void save() }}>
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={suggest}><Wand2 className="h-3.5 w-3.5" /> Suggest dates from the SLAs</Button>
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground"><input type="checkbox" checked={cascade} onChange={(e) => setCascade(e.target.checked)} className={checkbox} /> Move later stages with it</label>
          {/* once there is a baseline, every move says why (the log and the customer read it) */}
          {d.baseline_at && dirty && <Input value={reason} onChange={(e) => setReason(e.target.value)} required placeholder="Why the dates move (goes in the log)" aria-label="Why the dates move" maxLength={300} className="min-w-0 flex-1 basis-60" />}
          <span className="ml-auto flex gap-2">
            {(dirty || editing) && <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => { fresh.current = true; void reload(); setEditing(false) }}>{dirty ? "Discard" : "Done"}</Button>}
            <Button type="submit" size="sm" loading={busy} disabled={!dirty}><CalendarRange className="h-3.5 w-3.5" /> {d.baseline_at ? "Save plan" : "Save plan and set baseline"}</Button>
            {d.baseline_at && <Button type="button" size="sm" variant="outline" disabled={busy || dirty} onClick={() => setRebase("")}>Re-baseline</Button>}
          </span>
        </form>
      )}
      {notice && <Notice bad={notice.bad} className="mt-2">{notice.text}</Notice>}

      {d.changes.length > 0 && (
        <div className="mt-3">
          <button type="button" onClick={() => setLog(!log)} aria-expanded={log} className="flex items-center gap-2 text-[13px] text-muted-foreground hover:text-foreground"><History className="h-3.5 w-3.5" />{log ? "Hide" : "Show"} what moved ({d.changes.length})</button>
          {log && (
            <ul className="mt-2 divide-y divide-border text-[13px]">
              {d.changes.map((c, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-x-2 py-2">
                  {c.field === "baseline" ? <span className="font-medium">Re-baselined</span> : <span><span className="font-medium">{c.stage}</span> {c.field} {c.old ? fmtDate(c.old) : "unset"} to {c.new ? fmtDate(c.new) : "unset"}</span>}
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
          <Field label="Why"><Input autoFocus value={rebase ?? ""} onChange={(e) => setRebase(e.target.value)} maxLength={300} placeholder="Scope change agreed with the customer on 3 Oct" /></Field>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setRebase(null)}>Cancel</Button>
            <Button size="sm" loading={busy} disabled={!rebase?.trim()} onClick={() => { const why = rebase!.trim(); void run(async () => { await rebaseline(projectId, why); setRebase(null); return "The current plan is the new baseline." }) }}>Re-baseline</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
