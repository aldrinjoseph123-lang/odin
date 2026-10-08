import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

// A headline number: label over value over one quiet line. Tone is a state
// (warn / bad) and is passed only when the value is in that state.
export function StatTile({ label, value, sub, tone, className }: { label: string; value: string; sub?: ReactNode; tone?: "warn" | "bad"; className?: string }) {
  return (
    <div className={cn("panel p-3", className)}>
      <div className="text-[12px] text-muted-foreground">{label}</div>
      <div className={cn("mt-1 text-[24px] font-semibold tracking-tight", tone === "warn" && "text-warn", tone === "bad" && "text-bad")}>{value}</div>
      {sub && <div className="text-[12px] text-muted-foreground">{sub}</div>}
    </div>
  )
}
