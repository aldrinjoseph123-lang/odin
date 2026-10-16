import { DatePicker } from "@/components/DatePicker"
import type { Repeat } from "@/lib/repeat"
import { fieldAuto } from "@/lib/ui"
import { cn } from "@/lib/utils"

// A task's "Repeats" choice (services/milestones.py): never, weekly, fortnightly or
// monthly, and until when. The next occurrence is made when this one is ticked or
// its day passes, never twice.
const select = cn(fieldAuto, "h-7 min-w-0 text-[12px]")

export function RepeatPicker({ value, due, onChange }: { value: Repeat; due: string; onChange: (v: Repeat) => void }) {
  const repeat = value.repeat ?? "", until = value.until ?? ""
  const mode = !until ? "none" : until === "stage" ? "stage" : "date"
  return (
    <div className="grid grid-cols-1 gap-1">
      <select value={repeat} onChange={(e) => onChange({ repeat: e.target.value as Repeat["repeat"], until: e.target.value ? until : "" })} aria-label="Repeats" className={select}>
        <option value="">Does not repeat</option>
        <option value="weekly">Repeats every week</option>
        <option value="fortnightly">Repeats every two weeks</option>
        <option value="monthly">Repeats every month</option>
      </select>
      {repeat && (
        <div className="flex items-center gap-1">
          <select value={mode} aria-label="Repeat until" className={cn(select, "flex-1")}
            onChange={(e) => onChange({ repeat, until: e.target.value === "stage" ? "stage" : e.target.value === "date" ? due : "" })}>
            <option value="none">With no end date</option>
            <option value="stage">Until the stage is done</option>
            <option value="date">Until a date</option>
          </select>
          {mode === "date" && <DatePicker value={until} onChange={(v) => onChange({ repeat, until: v })} label="Repeat until" placeholder="Last day" className="h-7 min-w-0 flex-1 px-2 text-[12px]" />}
        </div>
      )}
      {repeat && !due && <p className="px-1 text-[11px] text-muted-foreground">Pick a due date: the next one is counted from it.</p>}
    </div>
  )
}
