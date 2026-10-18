import { useState, type FormEvent } from "react"
import { Pencil, Trash2 } from "lucide-react"
import { Panel } from "@/components/PanelTitle"
import { MoveArrows } from "@/components/MoveArrows"
import { LoadFailed } from "@/components/LoadFailed"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Field } from "@/components/ui/field"
import { Tag } from "@/components/ui/tag"
import { askConfirm } from "@/lib/confirm"
import { checkbox, field as fieldLook, fieldArea } from "@/lib/ui"
import { createField, customFields, deleteField, moveField, updateField, type CustomField, type FieldDraft, type FieldKind } from "@/lib/api"
import { useLoad } from "@/lib/useLoad"
import { useAction } from "@/lib/useAction"

// Settings › Rollouts & workflow › Custom fields: the extra fields every
// rollout carries. Renaming keeps the values; deleting takes them, so it asks
// first and says so (the server wants the field's name with the request and
// keeps the first few values in the audit row).
const BLANK: FieldDraft = { name: "", kind: "text", choices: [], required: false, customer_visible: false, show_in_list: false }
const FLAGS: [keyof Pick<FieldDraft, "required" | "customer_visible" | "show_in_list">, string, string][] = [
  ["required", "Required when a rollout is created", "required"],
  ["customer_visible", "Partners and customers see it (their project page, the customer report, the sign-off)", "customers see it"],
  ["show_in_list", "A column on the rollouts list", "in the list"],
]

export function FieldsEditor() {
  const { data: d, error, reload } = useLoad("custom-fields", customFields)
  const { busy, note, act } = useAction(reload)
  const [editing, setEditing] = useState<number | "new" | null>(null)
  const done = () => setEditing(null)
  if (!d) return error ? <LoadFailed what="the custom fields" onRetry={() => void reload()} /> : null
  const full = d.fields.length >= d.max
  async function remove(f: CustomField) {
    if (!(await askConfirm(`Delete ${f.name}? Every rollout's ${f.name} value is deleted with it and cannot be brought back; the audit log keeps only the first few.`, "Delete field"))) return
    done()
    void act(() => deleteField(f.id, f.name), `Deleted ${f.name}.`)   // the server wants the name with the request
  }

  return (
    <Panel title="Custom fields" hint={`${d.fields.length} of ${d.max}: extra details every rollout carries`} id="fields">
      <ul className="grid grid-cols-1 divide-y divide-border text-[13px]" aria-label="Custom fields">
        {d.fields.map((f, i) => (
          <li key={f.id} className="py-2">
            {editing === f.id ? (
              <FieldForm start={f} kinds={d.kinds} busy={busy} onCancel={done}
                onSave={(x) => act(() => updateField(f.id, x), `Saved ${x.name}.`).then((ok) => { if (ok) done() })} />
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 font-medium">{f.name}</span>
                <Tag kind="role">{d.kinds[f.kind]}{f.kind === "choice" ? `: ${f.choices.join(", ")}` : ""}</Tag>
                {FLAGS.filter(([k]) => f[k]).map(([k, , short]) => <Tag key={k}>{short}</Tag>)}
                <span className="ml-auto flex items-center gap-1">
                  <MoveArrows name={f.name} first={i === 0} last={i === d.fields.length - 1} busy={busy} onMove={(dir) => act(() => moveField(f.id, dir === "up" ? -1 : 1))} />
                  <Button type="button" variant="ghost" size="icon-sm" aria-label={`Edit ${f.name}`} onClick={() => { done(); setEditing(f.id) }}><Pencil className="size-3.5" /></Button>
                  <Button type="button" variant="ghost" size="icon-sm" aria-label={`Delete ${f.name}`} className="text-muted-foreground hover:text-destructive" onClick={() => void remove(f)}><Trash2 className="size-3.5" /></Button>
                </span>
              </div>
            )}
          </li>
        ))}
        {d.fields.length === 0 && <li className="py-2 text-muted-foreground">No custom fields yet. Add one for anything a rollout should record that Odin does not already ask for, such as a region or the number of endpoints.</li>}
      </ul>
      {editing === "new" ? (
        <div className="mt-3 border-t border-border pt-3">
          <FieldForm start={BLANK} kinds={d.kinds} busy={busy} onCancel={done}
            onSave={(x) => act(() => createField(x), `Added ${x.name}.`).then((ok) => { if (ok) done() })} />
        </div>
      ) : (
        <Button type="button" size="sm" variant="outline" className="mt-3" disabled={full} onClick={() => { done(); setEditing("new") }}>Add field</Button>
      )}
      {full && <p className="mt-2 text-[12px] text-muted-foreground">That is the most this workspace allows (Most custom fields, above).</p>}
      {note && <Notice bad={note.bad} className="mt-2">{note.text}</Notice>}
      <p className="mt-2 text-[12px] text-muted-foreground">In a document template, <code className="rounded bg-muted px-1">{"{field:Name}"}</code> prints a field partners and customers see.</p>
    </Panel>
  )
}

function FieldForm({ start, kinds, busy, onSave, onCancel }: {
  start: FieldDraft | CustomField; kinds: Record<FieldKind, string>; busy: boolean; onSave: (f: FieldDraft) => unknown; onCancel: () => void
}) {
  const [f, setF] = useState<FieldDraft>({ ...start })
  const [choices, setChoices] = useState(start.choices.join("\n"))
  function submit(e: FormEvent) {
    e.preventDefault()
    onSave({ ...f, choices: f.kind === "choice" ? choices.split("\n").map((c) => c.trim()).filter(Boolean) : [] })
  }
  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required maxLength={60} className="h-8 text-[13px]" /></Field>
      <Field label="Kind">
        <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as FieldKind })} className={fieldLook}>
          {Object.entries(kinds).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </Field>
      {f.kind === "choice" && (
        <Field label="Choices" hint="one per line" className="sm:col-span-2">
          <textarea value={choices} onChange={(e) => setChoices(e.target.value)} rows={3} className={fieldArea} />
        </Field>
      )}
      <div className="grid grid-cols-1 gap-1 sm:col-span-2">
        {FLAGS.map(([k, label]) => (
          <label key={k} className="flex items-center gap-2 text-[13px]"><input type="checkbox" className={checkbox} checked={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />{label}</label>
        ))}
      </div>
      <div className="flex items-center gap-2 sm:col-span-2">
        <Button type="submit" size="sm" loading={busy}>Save field</Button>
        <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}
