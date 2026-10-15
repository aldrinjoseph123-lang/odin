import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

// The outcome of an action, left on the page by the control that caused it.
// A failure must not look like a success (review P2-37): `bad` takes the
// error tone and role=alert so it is announced; the rest is a quiet status.
export function Notice({ bad, className, children }: { bad?: boolean; className?: string; children: ReactNode }) {
  return <p role={bad ? "alert" : "status"} className={cn("text-[13px]", bad ? "text-destructive" : "text-muted-foreground", className)}>{children}</p>
}
