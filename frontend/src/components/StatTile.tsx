import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

// A headline number: label over value over one quiet line. Tone is a state
// (warn / bad) and is passed only when the value is in that state.
export function StatTile({ label, value, sub, tone, icon, className }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "warn" | "bad"; icon?: ReactNode; className?: string }) {
  return (
    <div className={cn("panel p-4", className)}>
      <div className="flex items-center gap-2 text-[12px] text-muted-foreground">{icon}{label}</div>
      <div className={cn("mt-2 text-[24px] font-semibold leading-none tracking-tight tabular-nums", tone === "warn" && "text-warn", tone === "bad" && "text-bad")}>{value}</div>
      {sub && <div className="mt-1 text-[12px] text-muted-foreground">{sub}</div>}
    </div>
  )
}
