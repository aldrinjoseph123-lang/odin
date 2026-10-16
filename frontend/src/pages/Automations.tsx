import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Ago } from "@/components/Ago"
import { EmptyState } from "@/components/EmptyState"
import { LoadFailed } from "@/components/LoadFailed"
import { Notice } from "@/components/Notice"
import { PageHeader } from "@/components/PageHeader"
import { PageSkeleton } from "@/components/PageSkeleton"
import { Panel } from "@/components/PanelTitle"
import { RuleEditor } from "@/components/RuleEditor"
import { Button } from "@/components/ui/button"
import { Tag } from "@/components/ui/tag"
import { createRule, deleteRule, pauseRule, ruleRuns, rulesData, updateRule, type Rule, type User } from "@/lib/api"
import { askConfirm } from "@/lib/confirm"
import { BLANK_RULE, ruleSummary } from "@/lib/rules"
import { danger, td, th } from "@/lib/ui"
import { useAction } from "@/lib/useAction"
import { useLoad } from "@/lib/useLoad"
import { cn } from "@/lib/utils"

// Settings › Automations (services/rules.py, manage_rules): the rules, an editor
// in three columns, pause and resume, and each rule's run log. A rule tells
// staff, adds a task or a RAID item, sets a field or posts to Teams: it never
// reaches the customer and never moves a stage.
export default function Automations(_props: { user: User }) {
  const { data: d, reload, error } = useLoad("rules", rulesData)
  const { busy, note, act } = useAction(reload)
  const [editing, setEditing] = useState<number | "new" | null>(null)
  const [log, setLog] = useState<number | null>(null)
  const done = useCallback(() => setEditing(null), [])
  useEffect(() => { document.title = "Automations · Settings · Odin" }, [])
  if (!d) return error ? <LoadFailed what="the automations" onRetry={() => void reload()} /> : <PageSkeleton />
  const full = d.rules.length >= d.max
  const shown = d.rules.find((r) => r.id === log)
  return (
    <div className="grid gap-4 px-5 pb-6 pt-4">
      <PageHeader title="Automations"
        lede="When something happens on a rollout and every condition holds, Odin does the actions. Rules reach staff and Teams only, never the customer, and never move a stage."
        actions={<Button size="sm" disabled={full || editing === "new"} onClick={() => setEditing("new")}>New rule</Button>} />
      {editing === "new" && (
        <Panel title="New rule">
          <RuleEditor data={d} start={BLANK_RULE} busy={busy} onCancel={done}
            onSave={(r) => act(async () => { const made = await createRule(r); setLog(made.id) }, `Saved ${r.name}.`).then((ok) => { if (ok) done() })} />
        </Panel>
      )}
      <Panel title="Rules" hint={`${d.rules.length} of ${d.max}`}>
        {d.rules.length === 0 ? <EmptyState>No automations yet. A rule might tell the team when a rollout enters Deployment, or add a risk when the customer declines a stage.</EmptyState> : (
          <ul className="grid grid-cols-1 divide-y divide-border text-[13px]" aria-label="Rules">
            {d.rules.map((r) => (
              <li key={r.id} className="py-3">
                {editing === r.id ? (
                  <RuleEditor data={d} start={r} busy={busy} onCancel={done}
                    onSave={(x) => act(() => updateRule(r.id, x), `Saved ${x.name}.`).then((ok) => { if (ok) done() })} />
                ) : <RuleRow r={r} summary={ruleSummary(r, d)} busy={busy} logOpen={log === r.id}
                  onEdit={() => setEditing(r.id)} onLog={() => setLog(log === r.id ? null : r.id)}
                  onPause={() => void act(() => pauseRule(r.id, !r.paused), r.paused ? `${r.name} is on again.` : `${r.name} is paused.`)}
                  onDelete={async () => { if (await askConfirm(`Delete ${r.name}? Its run log goes with it; the audit log keeps every firing.`, "Delete")) void act(() => deleteRule(r.id), `Deleted ${r.name}.`) }} />}
              </li>
            ))}
          </ul>
        )}
        {full && <p className="mt-2 text-[12px] text-muted-foreground">That is the most this workspace allows (Settings › Rollouts & workflow › Most automations).</p>}
        {note && <Notice bad={note.bad} className="mt-2">{note.text}</Notice>}
      </Panel>
      {shown && <RunLog key={`${shown.id}:${shown.runs}`} rule={shown} keepDays={d.keep_days} />}
    </div>
  )
}

function RuleRow({ r, summary, busy, logOpen, onEdit, onLog, onPause, onDelete }: {
  r: Rule; summary: string; busy: boolean; logOpen: boolean; onEdit: () => void; onLog: () => void; onPause: () => void; onDelete: () => void
}) {
  return (
    <div className="grid gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("font-medium", r.paused && "text-muted-foreground")}>{r.name}</span>
        {r.paused ? <Tag kind="warn">Paused</Tag> : <Tag kind="role">Active</Tag>}
        <span className="text-[12px] text-muted-foreground">
          {r.last_run ? <>ran {r.runs} {r.runs === 1 ? "time" : "times"}, last <Ago iso={r.last_run.at} />{!r.last_run.ok && " (an action failed)"}</> : "not run yet"}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="outline" aria-pressed={logOpen} onClick={onLog}>Run log</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={onPause}>{r.paused ? "Resume" : "Pause"}</Button>
          <Button size="sm" variant="outline" aria-label={`Edit ${r.name}`} onClick={onEdit}>Edit</Button>
          <Button size="sm" variant="outline" className={danger} disabled={busy} aria-label={`Delete ${r.name}`} onClick={onDelete}>Delete</Button>
        </span>
      </div>
      <p className="text-muted-foreground">{summary}</p>
    </div>
  )
}

function RunLog({ rule, keepDays }: { rule: Rule; keepDays: number }) {
  const { data, error, reload } = useLoad(`rule-runs-${rule.id}`, () => ruleRuns(rule.id))
  return (
    <Panel title={`Run log: ${rule.name}`} hint={`kept ${keepDays} days; every firing is also in the audit log`}>
      {!data ? (error ? <LoadFailed what="the run log" onRetry={() => void reload()} /> : null) : data.runs.length === 0 ? <EmptyState>It has not fired yet.</EmptyState> : (
        <div className="overflow-x-auto"><table className="w-full text-[13px]" aria-label="Run log">
          <thead><tr>{["When", "Rollout", "What happened", "What it did"].map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
          <tbody>
            {data.runs.map((x) => (
              <tr key={x.id} className="border-t border-border align-top">
                <td className={cn(td, "whitespace-nowrap")}><Ago iso={x.at} /></td>
                <td className={td}>{x.project_id && x.project ? <Link to={`/projects/${x.project_id}`} className="hover:underline">{x.project}</Link> : "—"}</td>
                <td className={td}>{x.what}</td>
                <td className={td}>
                  <ul className="grid gap-0.5">
                    {x.actions.map((a, i) => <li key={i} className={cn(!a.ok && "text-destructive")}>{a.ok ? "" : "Failed: "}{a.said}</li>)}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </Panel>
  )
}
