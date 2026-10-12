import type { KeyboardEvent, ReactNode } from "react"
import { cn } from "@/lib/utils"

// One of a few, side by side on a muted track (whole-app critique, 10 Oct 2026:
// eight hand-rolled copies in three heights and two roles). A radio group:
// Tab reaches the chosen one, arrows move the choice. `full` stretches the
// options across a form field's width.
export function Segmented<T extends string | number>({ value, options, onChange, label, full, disabled, className }: {
  value: T; options: { value: T; label: ReactNode; icon?: ReactNode }[]; onChange: (v: T) => void
  label: string; full?: boolean; disabled?: boolean; className?: string
}) {
  const move = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0
    if (!step) return
    e.preventDefault()
    const i = (options.findIndex((o) => o.value === value) + step + options.length) % options.length
    onChange(options[i].value)
    ;(e.currentTarget.children[i] as HTMLElement | undefined)?.focus()
  }
  return (
    <div role="radiogroup" aria-label={label} onKeyDown={move} className={cn("flex rounded-full bg-muted p-1", className)}>
      {options.map((o) => {
        const on = o.value === value
        return (
          <button key={String(o.value)} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1} disabled={disabled} onClick={() => onChange(o.value)}
            className={cn("inline-flex h-7 items-center justify-center gap-2 rounded-full px-3 text-[12px] font-medium outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-60",
              full && "flex-1", on ? "bg-card text-foreground shadow-card" : "text-muted-foreground hover:text-foreground")}>
            {o.icon}{o.label}
          </button>
        )
      })}
    </div>
  )
}
