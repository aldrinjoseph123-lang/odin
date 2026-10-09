import { useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { slaProposals, type SettingsData, type SlaProposal } from "@/lib/api"

type Send = (path: string, fields?: Record<string, string>, confirmText?: string) => Promise<unknown>

// The SLA check under Stage templates: where a stage's SLA disagrees with how
// long it really took on this template's rollouts. The numbers are Odin's;
// the one-line reason is the AI's when it has written one. Apply saves the
// template's SLAs through the normal (audited) route with this one changed.
export function SlaCheck({ templates, busy, send }: { templates: SettingsData["templates"]; busy: boolean; send: Send }) {
  const [rows, setRows] = useState<SlaProposal[] | null>(null)
  const key = JSON.stringify(templates.map((t) => t.stages.map((s) => s.sla_days)))
  useEffect(() => { slaProposals().then((x) => setRows(x.proposals)).catch(() => setRows([])) }, [key])
  if (!rows || rows.length === 0) return null
  function apply(p: SlaProposal) {
    const t = templates.find((x) => x.id === p.template_id)
    if (!t) return
    const fields = Object.fromEntries(t.stages.map((s) => [`sla::${s.id}`, s.id === p.stage_id ? String(p.proposed) : s.sla_days == null ? "" : String(s.sla_days)]))
    void send(`/settings/templates/${p.template_id}/sla`, fields)
  }
  return (
    <div className="mt-4 border-t border-border pt-3">
      <h3 className="text-[13px] font-semibold text-nav-fg">SLA check <span className="font-normal text-muted-foreground">stages whose SLA disagrees with how long they really took (80% of finished rollouts within the proposal)</span></h3>
      <div className="mt-2 overflow-x-auto"><table className="w-full min-w-[680px] text-[13px]">
        <thead><tr className="text-left text-[12px] text-muted-foreground">{["Template", "Stage", "Today", "Proposed", "History", ""].map((h) => <th key={h} className="pb-2 pr-3 font-normal">{h}</th>)}</tr></thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.key} className="border-t border-border align-top">
              <td className="py-2 pr-3">{p.template}</td>
              <td className="py-2 pr-3 font-medium">{p.stage}</td>
              <td className="whitespace-nowrap py-2 pr-3 tabular-nums">{p.current == null ? "none" : `${p.current} d`}</td>
              <td className="whitespace-nowrap py-2 pr-3 font-medium tabular-nums">{p.proposed} d</td>
              <td className="py-2 pr-3 text-[13px] text-muted-foreground">
                {p.visits} rollouts, median {p.median}, 80% within {p.p80} {p.unit}
                {p.reason && <span className="mt-1 flex items-start gap-1 text-foreground"><Sparkles className="mt-1 h-3 w-3 shrink-0 text-primary-text" aria-label="Written by AI" />{p.reason}</span>}
              </td>
              <td className="py-2 text-right"><Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => apply(p)}>Apply</Button></td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </div>
  )
}
