import { Plus, X } from "lucide-react"
import { Input } from "@/components/ui/input"
import { fieldArea, fieldAuto, checkbox } from "@/lib/ui"
import { cn } from "@/lib/utils"
import type { AskQuestion, AskQuestionKind } from "@/lib/api"

// The questions of a form ask (services/asks.py), as the task form edits them:
// words, the kind of answer, the choices for a choice, and whether it must be
// answered. A question keeps its key through an edit, so earlier answers still
// match; the server checks the lot and caps the count (policy ask_form_max_questions).

const KINDS: [AskQuestionKind, string][] = [["text", "Text"], ["number", "Number"], ["date", "Date"], ["choice", "Choice"], ["yesno", "Yes or no"]]

export function AskFormEditor({ value, onChange }: { value: AskQuestion[]; onChange: (v: AskQuestion[]) => void }) {
  const set = (i: number, patch: Partial<AskQuestion>) => onChange(value.map((q, j) => (j === i ? { ...q, ...patch } : q)))
  return (
    <fieldset className="grid grid-cols-1 gap-2 rounded-lg bg-muted/50 p-2">
      <legend className="sr-only">Questions</legend>
      {value.map((q, i) => (
        <div key={q.key ?? `new-${i}`} className="grid grid-cols-1 gap-1">
          <div className="flex items-center gap-1">
            <Input value={q.label} onChange={(e) => set(i, { label: e.target.value })} placeholder={`Question ${i + 1}`} aria-label={`Question ${i + 1}`} maxLength={200} className="h-7 min-w-0 flex-1 px-2 text-[12px]" />
            <button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label={`Remove question ${i + 1}`}
              className="relative shrink-0 text-muted-foreground before:absolute before:-inset-[5px] before:content-[''] hover:text-destructive"><X className="h-3.5 w-3.5" /></button>
          </div>
          <div className="flex items-center gap-2">
            <select value={q.kind} onChange={(e) => set(i, { kind: e.target.value as AskQuestionKind })} aria-label={`Answer to question ${i + 1}`} className={cn(fieldAuto, "h-7 min-w-0 text-[12px]")}>
              {KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
            <label className="flex items-center gap-1 text-[12px] text-muted-foreground">
              <input type="checkbox" className={checkbox} checked={q.required !== false} onChange={(e) => set(i, { required: e.target.checked })} /> Required
            </label>
          </div>
          {q.kind === "choice" && (
            <textarea rows={2} value={(q.choices ?? []).join("\n")} onChange={(e) => set(i, { choices: e.target.value.split("\n") })}
              placeholder="One choice per line" aria-label={`Choices for question ${i + 1}`} className={cn(fieldArea, "text-[12px]")} />
          )}
        </div>
      ))}
      <button type="button" onClick={() => onChange([...value, { label: "", kind: "text", required: true }])} className="flex items-center gap-1 text-[12px] text-muted-foreground hover:text-primary-text">
        <Plus className="h-3 w-3" /> Question
      </button>
    </fieldset>
  )
}
