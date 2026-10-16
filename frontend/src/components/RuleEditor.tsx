import { useState, type FormEvent, type ReactNode } from "react"
import { Trash2 } from "lucide-react"
import { EmptyState } from "@/components/EmptyState"
import { Notice } from "@/components/Notice"
import { PanelTitle } from "@/components/PanelTitle"
import { SubmitForm } from "@/components/SubmitForm"
import { Button } from "@/components/ui/button"
import { Field } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { dryRunRule, type DryRun, type RuleAction, type RuleActionKind, type RuleCondition, type RuleConditionKind, type RuleDraft, type RuleOptions, type RulesData } from "@/lib/api"
import { plural } from "@/lib/format"
import { blankAction, blankCondition, firstValue } from "@/lib/rules"
import { checkbox, field as fieldLook, fieldArea } from "@/lib/ui"
import { useAction } from "@/lib/useAction"

// Settings › Automations: one rule in three columns — When (the trigger), If (the
// conditions, all of which must hold) and Then (the actions). Dry run asks the
// server which rollouts the rule as written would have matched in the last 30
// days, and says what it could replay; it sends nothing and changes nothing.

type Field = RuleOptions["fields"][number]

function Column({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="grid content-start gap-3 rounded-lg bg-muted/50 p-3">
      <PanelTitle n={false} hint={hint} className="mb-0">{title}</PanelTitle>
      {children}
    </section>
  )
}

// a field's value as its kind takes it, stored as Odin keeps it
function FieldValue({ f, value, onChange, label, any }: { f: Field | undefined; value: string | null | undefined; onChange: (v: string | null) => void; label: string; any?: boolean }) {
  const v = value ?? ""
  if (f?.kind === "choice" || f?.kind === "yesno") {
    const opts = f.kind === "choice" ? f.choices.map((c) => [c, c]) : [["1", "Yes"], ["0", "No"]]
    return (
      <select aria-label={label} value={v} onChange={(e) => onChange(e.target.value || null)} className={fieldLook}>
        {any && <option value="">Any value</option>}
        {opts.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
    )
  }
  return <Input aria-label={label} type={f?.kind === "date" ? "date" : "text"} inputMode={f?.kind === "number" ? "decimal" : undefined} value={v}
    placeholder={any ? "Any value" : undefined} onChange={(e) => onChange(e.target.value || null)} className="h-8 text-[13px]" />
}

function FieldPick({ o, id, onChange, label }: { o: RuleOptions; id: number | undefined; onChange: (id: number) => void; label: string }) {
  return (
    <select aria-label={label} value={id ?? ""} onChange={(e) => onChange(Number(e.target.value))} className={fieldLook}>
      {o.fields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
    </select>
  )
}

const Remove = ({ label, onClick }: { label: string; onClick: () => void }) => (
  <Button type="button" variant="ghost" size="icon-sm" aria-label={label} className="text-muted-foreground hover:text-destructive" onClick={onClick}><Trash2 className="size-3.5" /></Button>
)

export function RuleEditor({ data, start, busy, onSave, onCancel }: {
  data: RulesData; start: RuleDraft; busy: boolean; onSave: (r: RuleDraft) => unknown; onCancel: () => void
}) {
  const o = data.options
  const [r, setR] = useState<RuleDraft>(() => structuredClone(start))
  const [dry, setDry] = useState<DryRun | null>(null)
  const { busy: trying, note: dryNote, act } = useAction()
  const fieldOf = (id?: number) => o.fields.find((f) => f.id === id)
  const setCond = (i: number, c: RuleCondition) => setR({ ...r, conditions: r.conditions.map((x, j) => j === i ? c : x) })
  const setAct = (i: number, a: RuleAction) => setR({ ...r, actions: r.actions.map((x, j) => j === i ? a : x) })

  function submit(e: FormEvent) { e.preventDefault(); void onSave(r) }
  async function tryIt() {
    if (!(await act(async () => setDry(await dryRunRule(r))))) setDry(null)
  }

  const condKinds = (Object.keys(data.conditions) as RuleConditionKind[]).filter((k) => k !== "field" || o.fields.length > 0)
  const actKinds = (Object.keys(data.actions) as RuleActionKind[]).filter((k) => (k !== "set_field" || o.fields.length > 0) && (k !== "add_task" || o.template_tasks.length > 0))
  return (
    <SubmitForm onSubmit={submit} aria-label="Rule" className="grid grid-cols-1 gap-3">
      <Field label="Name" className="max-w-md">
        <Input value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} required maxLength={100} placeholder="e.g. Deployment starts: tell the team" className="h-8 text-[13px]" />
      </Field>
      <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-3">
        <Column title="When" hint="what starts it">
          <Field label="Trigger">
            <select value={r.event} onChange={(e) => { const event = e.target.value as RuleDraft["event"]; setR({ ...r, event, event_config: event === "field_set" ? { field_id: o.fields[0]?.id, value: null } : {} }) }} className={fieldLook}>
              {Object.entries(data.events).map(([k, l]) => <option key={k} value={k} disabled={k === "field_set" && o.fields.length === 0}>{l}</option>)}
            </select>
          </Field>
          {r.event === "document_uploaded" && (
            <Field label="Category">
              <select value={r.event_config.category ?? ""} onChange={(e) => setR({ ...r, event_config: e.target.value ? { category: e.target.value } : {} })} className={fieldLook}>
                <option value="">Any category</option>
                {o.categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
          )}
          {r.event === "field_set" && (
            <>
              <FieldPick o={o} id={r.event_config.field_id} label="Trigger field" onChange={(id) => setR({ ...r, event_config: { field_id: id, value: null } })} />
              <FieldValue f={fieldOf(r.event_config.field_id)} value={r.event_config.value} any label="Trigger value"
                onChange={(value) => setR({ ...r, event_config: { ...r.event_config, value } })} />
            </>
          )}
          {["stage_sla_breached", "task_overdue", "milestone_missed"].includes(r.event) && (
            <p className="text-[12px] text-muted-foreground">Checked every quarter hour. Fires once for each, and only for what happens after the rule is saved or resumed.</p>
          )}
        </Column>

        <Column title="If" hint="all must hold">
          {r.conditions.length === 0 && <p className="text-[12px] text-muted-foreground">Every rollout.</p>}
          {r.conditions.map((c, i) => (
            <div key={i} className="grid grid-cols-1 gap-2 rounded-lg bg-card p-2">
              <div className="flex items-center gap-2">
                <span className="text-[12px] font-medium text-nav-fg">{data.conditions[c.kind]}</span>
                <span className="ml-auto"><Remove label={`Remove condition ${i + 1}`} onClick={() => setR({ ...r, conditions: r.conditions.filter((_, j) => j !== i) })} /></span>
              </div>
              {c.kind === "stage" && (
                <select aria-label={`Condition ${i + 1} stage`} value={c.value ?? ""} onChange={(e) => setCond(i, { ...c, value: e.target.value })} className={fieldLook}>
                  {o.stages.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              )}
              {c.kind === "delivery_mode" && (
                <select aria-label={`Condition ${i + 1} delivery mode`} value={c.value ?? ""} onChange={(e) => setCond(i, { ...c, value: e.target.value })} className={fieldLook}>
                  {o.delivery_modes.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              )}
              {c.kind === "client" && <Input aria-label={`Condition ${i + 1} client`} value={c.value ?? ""} maxLength={200} onChange={(e) => setCond(i, { ...c, value: e.target.value })} className="h-8 text-[13px]" />}
              {c.kind === "field" && (
                <>
                  <FieldPick o={o} id={c.field_id} label={`Condition ${i + 1} field`} onChange={(id) => setCond(i, { ...c, field_id: id, value: firstValue(fieldOf(id)) })} />
                  <FieldValue f={fieldOf(c.field_id)} value={c.value} label={`Condition ${i + 1} value`} onChange={(value) => setCond(i, { ...c, value })} />
                </>
              )}
            </div>
          ))}
          <AddMenu label="Add a condition" options={condKinds.map((k) => [k, data.conditions[k]])} onPick={(k) => setR({ ...r, conditions: [...r.conditions, blankCondition(k as RuleConditionKind, o)] })} />
        </Column>

        <Column title="Then" hint="staff and Teams only">
          {r.actions.length === 0 && <p className="text-[12px] text-muted-foreground">Add at least one action.</p>}
          {r.actions.map((a, i) => (
            <div key={i} className="grid grid-cols-1 gap-2 rounded-lg bg-card p-2">
              <div className="flex items-center gap-2">
                <span className="text-[12px] font-medium text-nav-fg">{data.actions[a.kind]}</span>
                <span className="ml-auto"><Remove label={`Remove action ${i + 1}`} onClick={() => setR({ ...r, actions: r.actions.filter((_, j) => j !== i) })} /></span>
              </div>
              <ActionFields a={a} i={i} o={o} fieldOf={fieldOf} onChange={(x) => setAct(i, x)} />
            </div>
          ))}
          <AddMenu label="Add an action" options={actKinds.map((k) => [k, data.actions[k]])} onPick={(k) => setR({ ...r, actions: [...r.actions, blankAction(k as RuleActionKind, o)] })} />
        </Column>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" loading={busy}>Save rule</Button>
        <Button type="button" size="sm" variant="outline" loading={trying} disabled={busy} onClick={() => void tryIt()}>Dry run</Button>
        <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={onCancel}>Cancel</Button>
      </div>
      {dryNote?.bad && <Notice bad>{dryNote.text}</Notice>}
      {dry && <DryRunResult d={dry} />}
    </SubmitForm>
  )
}

function AddMenu({ label, options, onPick }: { label: string; options: [string, string][]; onPick: (k: string) => void }) {
  return (
    <select aria-label={label} value="" onChange={(e) => { if (e.target.value) onPick(e.target.value) }} className={fieldLook}>
      <option value="">{label}…</option>
      {options.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
    </select>
  )
}

function ActionFields({ a, i, o, fieldOf, onChange }: { a: RuleAction; i: number; o: RuleOptions; fieldOf: (id?: number) => Field | undefined; onChange: (a: RuleAction) => void }) {
  const n = `Action ${i + 1}`
  switch (a.kind) {
    case "notify": {
      const flip = <T,>(list: T[], x: T, on: boolean) => on ? [...list, x] : list.filter((y) => y !== x)
      return (
        <>
          <fieldset className="grid gap-1 text-[13px]">
            <legend className="mb-1 text-[12px] text-muted-foreground">Who, on the rollout</legend>
            {o.roles.map((role) => (
              <label key={role} className="flex items-center gap-2"><input type="checkbox" className={checkbox} checked={a.roles.includes(role)} onChange={(e) => onChange({ ...a, roles: flip(a.roles, role, e.target.checked) })} />{role}</label>
            ))}
          </fieldset>
          <fieldset className="grid gap-1 text-[13px]">
            <legend className="mb-1 text-[12px] text-muted-foreground">And these people</legend>
            <div className="grid max-h-40 gap-1 overflow-y-auto">
              {o.users.map((u) => (
                <label key={u.id} className="flex items-center gap-2"><input type="checkbox" className={checkbox} checked={a.user_ids.includes(u.id)} onChange={(e) => onChange({ ...a, user_ids: flip(a.user_ids, u.id, e.target.checked) })} />{u.name}</label>
              ))}
            </div>
          </fieldset>
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" className={checkbox} checked={a.email} onChange={(e) => onChange({ ...a, email: e.target.checked })} />Email too (the bell always)</label>
          <Field label="Message" hint="optional"><textarea aria-label={`${n} message`} rows={2} maxLength={500} value={a.message} onChange={(e) => onChange({ ...a, message: e.target.value })} className={fieldArea} /></Field>
        </>
      )
    }
    case "add_task":
      return (
        <select aria-label={`${n} template task`} value={a.template_task_id} onChange={(e) => onChange({ ...a, template_task_id: Number(e.target.value) })} className={fieldLook}>
          {o.template_tasks.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select>
      )
    case "add_raid":
      return (
        <>
          <div className="grid grid-cols-2 gap-2">
            <select aria-label={`${n} kind`} value={a.raid_kind} onChange={(e) => onChange({ ...a, raid_kind: e.target.value })} className={fieldLook}>
              {o.raid_kinds.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
            <select aria-label={`${n} impact`} value={a.impact} onChange={(e) => onChange({ ...a, impact: e.target.value })} className={fieldLook}>
              {o.raid_levels.map((k) => <option key={k} value={k}>{k} impact</option>)}
            </select>
          </div>
          <Input aria-label={`${n} title`} value={a.title} maxLength={200} placeholder="Title" onChange={(e) => onChange({ ...a, title: e.target.value })} className="h-8 text-[13px]" />
        </>
      )
    case "set_field":
      return (
        <>
          <FieldPick o={o} id={a.field_id} label={`${n} field`} onChange={(id) => onChange({ ...a, field_id: id, value: firstValue(fieldOf(id)) })} />
          <FieldValue f={fieldOf(a.field_id)} value={a.value} label={`${n} value`} onChange={(value) => onChange({ ...a, value: value ?? "" })} />
        </>
      )
    case "teams":
      return <Field label="Message" hint="the channel and the webhook under Settings › Notifications"><textarea aria-label={`${n} message`} rows={2} maxLength={500} value={a.message} onChange={(e) => onChange({ ...a, message: e.target.value })} className={fieldArea} /></Field>
  }
}

function DryRunResult({ d }: { d: DryRun }) {
  return (
    <section aria-label="Dry run" className="grid gap-2 rounded-lg bg-muted/50 p-3 text-[13px]">
      <PanelTitle n={false} hint={`${plural(d.total, "rollout")} in the last 30 days`} className="mb-0">Dry run</PanelTitle>
      {d.matches.length === 0 ? <EmptyState className="py-4">No rollout would have matched.</EmptyState> : (
        <ul className="grid gap-1">
          {d.matches.map((m) => (
            <li key={m.project_id} className="flex flex-wrap gap-x-2">
              <a href={`/projects/${m.project_id}`} className="font-medium hover:underline">{m.name}</a>
              <span className="text-muted-foreground">{m.client} · {plural(m.times, "time")} · latest: {m.last}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-[12px] text-muted-foreground">Replayed: {d.replayed} {d.caveat}</p>
    </section>
  )
}
