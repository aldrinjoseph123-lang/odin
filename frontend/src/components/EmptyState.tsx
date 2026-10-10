import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

// An empty list says so in one place, the same way everywhere (DESIGN.md: a
// dashed hairline box, 16 px corners, 40 px tall padding, centred 13 px muted
// text). Small in-line lists (a day in the calendar, a menu) keep a quiet line.
export function EmptyState({ children, className, as: As = "p" }: { children: ReactNode; className?: string; as?: "p" | "li" }) {
  return <As className={cn("rounded-lg border border-dashed border-border px-4 py-10 text-center text-[13px] text-muted-foreground", className)}>{children}</As>
}
