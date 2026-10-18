import { Link2, X } from "lucide-react"
import { fieldAuto } from "@/lib/ui"
import { cn } from "@/lib/utils"

export type WaitOption = { id: number; title: string }

// What a task waits on, under its title: the link glyph, the open predecessors
// and how late each is (late is overdue: the bad state).
export function WaitsOn({ waits }: { waits: { id: number; title: string; late_by: number }[] }) {
  return <span className="flex items-start gap-1 text-[11px] font-normal text-muted-foreground">
    <Link2 className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
    <span>waits on {waits.map((w, i) => <span key={w.id}>{i ? ", " : ""}{w.title}{w.late_by > 0 && <span className="font-medium text-bad"> · {w.late_by} d late</span>}</span>)}</span>
  </span>
}

// "Waits on": the tasks of the same rollout this one cannot finish before
// (finish-to-start). The chosen ones are chips with a remove button; the
// select adds one more. The caller passes only the rollout's other tasks;
// the server refuses a loop and says why.
export function WaitsOnPicker({ options, value, onChange, label = "Waits on", className }: {
  options: WaitOption[]; value: number[]; onChange: (ids: number[]) => void; label?: string; className?: string
}) {
  const chosen = value.map((id) => options.find((o) => o.id === id)).filter((o): o is WaitOption => !!o)
  const left = options.filter((o) => !value.includes(o.id))
  if (!options.length) return null
  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      {chosen.map((o) => (
        <span key={o.id} className="flex h-6 max-w-full items-center gap-1 rounded-full bg-muted pl-2 pr-1 text-[12px]">
          <Link2 className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
          <span className="truncate" title={o.title}>{o.title}</span>
          <button type="button" onClick={() => onChange(value.filter((id) => id !== o.id))} aria-label={`No longer waits on ${o.title}`}
            className="rounded-full p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"><X className="h-3 w-3" /></button>
        </span>
      ))}
      {left.length > 0 && (
        <select value="" onChange={(e) => { if (e.target.value) onChange([...value, Number(e.target.value)]) }} aria-label={label}
          className={cn(fieldAuto, "h-7 min-w-0 flex-1 text-[12px]")}>
          <option value="">{chosen.length ? "And waits on…" : "Waits on…"}</option>
          {left.map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}
        </select>
      )}
    </div>
  )
}
