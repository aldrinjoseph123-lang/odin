import { useEffect, useState } from "react"
import { docTemplateChoices, type DocKind } from "@/lib/api"

// Which document template a report or sign-off is drawn with (Settings →
// Documents). Hidden when the workspace has none: the built-in layout applies.
export function TemplatePicker({ kind, value, onChange }: { kind: DocKind; value: number | null; onChange: (id: number | null) => void }) {
  const [choices, setChoices] = useState<{ id: number; name: string; is_default: boolean }[]>([])
  useEffect(() => { docTemplateChoices(kind).then((r) => setChoices(r.choices)).catch(() => setChoices([])) }, [kind])
  if (choices.length === 0) return null
  const def = choices.find((c) => c.is_default)
  return (
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)} aria-label="Document template"
      className="h-8 rounded-full border border-input bg-card px-3 text-[12.5px]">
      <option value="">{def ? `${def.name} (default)` : "Built-in layout"}</option>
      {choices.filter((c) => !c.is_default).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
  )
}
