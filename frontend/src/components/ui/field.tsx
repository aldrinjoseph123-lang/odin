import { cloneElement, isValidElement, useId, type ReactNode } from "react"
import { cn } from "@/lib/utils"

// The one form field: a 12 px medium chrome-text label over its control, an optional
// 12 px muted hint and an inline error under it (DESIGN.md "Inputs / Fields"; review
// P2-52: four label looks had drifted apart). The label wraps the control, so a click
// on the text focuses it and the name needs no id; a single element child also gets
// `aria-describedby` (hint, error) and `aria-invalid` from here.
export function Field({ label, hint, error, children, className }: { label: ReactNode; hint?: ReactNode; error?: ReactNode; children: ReactNode; className?: string }) {
  const id = useId()
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ") || undefined
  const control = isValidElement<Record<string, unknown>>(children) && (describedBy || error)
    ? cloneElement(children, { "aria-describedby": [children.props["aria-describedby"], describedBy].filter(Boolean).join(" ") || undefined, "aria-invalid": error ? true : children.props["aria-invalid"] })
    : children
  return (
    <div className={cn("grid grid-cols-1 gap-1", className)}>
      <label className="grid grid-cols-1 gap-1 text-[12px] font-medium text-nav-fg">{label}{control}</label>
      {hint && <p id={`${id}-hint`} className="text-[12px] text-muted-foreground">{hint}</p>}
      {error && <p id={`${id}-error`} role="alert" className="text-[12px] text-destructive">{error}</p>}
    </div>
  )
}
