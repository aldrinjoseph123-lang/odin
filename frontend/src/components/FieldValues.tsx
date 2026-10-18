import { useCallback, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Field } from "@/components/ui/field"
import { DatePicker } from "@/components/DatePicker"
import { LoadFailed } from "@/components/LoadFailed"
import { Notice } from "@/components/Notice"
import { field as fieldLook } from "@/lib/ui"
import { fieldInput, fieldText } from "@/lib/format"
import { projectFields, saveProjectFields, type CustomField } from "@/lib/api"
import { useLoad } from "@/lib/useLoad"
import { useAction } from "@/lib/useAction"

// Custom fields (Settings › Rollouts & workflow) on a rollout: the values in
// the Details panel, edited in place by whoever may edit the rollout. The
// server cuts what partners and customers see and checks every value.

// One field's control, by its kind; `value` is the input's string
export function FieldInput({ field, value, onChange, name }: { field: Pick<CustomField, "name" | "kind" | "choices">; value: string; onChange: (v: string) => void; name?: string }) {
  const label = field.name
  if (field.kind === "date") return <DatePicker value={value} onChange={onChange} label={label} name={name} className="w-full" />
  if (field.kind === "choice" || field.kind === "yesno") {
    const options = field.kind === "choice" ? field.choices.map((c) => [c, c]) : [["yes", "Yes"], ["no", "No"]]
    return (
      <select value={value} onChange={(e) => onChange(e.target.value)} name={name} aria-label={label} className={fieldLook}>
        <option value="">—</option>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    )
  }
  return <Input value={value} onChange={(e) => onChange(e.target.value)} name={name} aria-label={label} maxLength={200}
    type={field.kind === "number" ? "number" : "text"} step={field.kind === "number" ? "any" : undefined} className="h-8 text-[13px]" />
}

export function FieldValues({ projectId }: { projectId: number }) {
  const { data: d, error, reload } = useLoad(`fields:${projectId}`, () => projectFields(projectId))
  const { busy, note, act } = useAction(reload)
  const [draft, setDraft] = useState<Record<string, string> | null>(null)
  const edit = useCallback(() => d && setDraft(Object.fromEntries(d.fields.map((f) => [f.id, fieldInput(f.kind, f.value)]))), [d])
  if (!d) return error ? <div className="mt-3 border-t border-border pt-3"><LoadFailed what="the custom fields" onRetry={() => void reload()} /></div> : null
  if (d.fields.length === 0) return null
  const shown = d.fields.filter((f) => f.value !== null)

  async function save() {
    if (await act(() => saveProjectFields(projectId, draft!), "Saved.")) setDraft(null)
  }

  return (
    <div className="mt-3 border-t border-border pt-3">
      {draft ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {d.fields.map((f) => (
            <Field key={f.id} label={f.name}>
              <FieldInput field={f} value={draft[f.id] ?? ""} onChange={(v) => setDraft({ ...draft, [f.id]: v })} />
            </Field>
          ))}
          <div className="flex items-center gap-2 sm:col-span-2">
            <Button type="button" size="sm" loading={busy} onClick={save}>Save fields</Button>
            <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setDraft(null)}>Cancel</Button>
          </div>
        </div>
      ) : (
        <dl className="grid grid-cols-[minmax(96px,auto)_minmax(0,1fr)] gap-x-4 gap-y-2 text-[13px] [&_dd]:min-w-0 [&_dd]:break-words">
          {shown.map((f) => <div key={f.id} className="contents"><dt className="text-muted-foreground">{f.name}</dt><dd>{fieldText(f.kind, f.value)}</dd></div>)}
          {shown.length === 0 && <dd className="col-span-2 text-muted-foreground">No custom fields filled in yet.</dd>}
        </dl>
      )}
      {!draft && d.can_edit && <Button type="button" size="sm" variant="ghost" className="mt-2 -ml-2" onClick={edit}>Edit fields</Button>}
      {note && <Notice bad={note.bad} className="mt-2">{note.text}</Notice>}
    </div>
  )
}
