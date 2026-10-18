import { Lock } from "lucide-react"
import { cn } from "@/lib/utils"

// What holds a rollout in its stage (services/gates.py), in one line
// (lib/format gateText). Staff only: the server sends no gate to partners
// and customers.

export function GateBlock({ text, className }: { text: string; className?: string }) {
  if (!text) return null
  return (
    <span className={cn("flex min-w-0 items-center gap-1 text-[12px] font-medium text-warn", className)} title={`Before leaving this stage: ${text}`}>
      <Lock className="h-3 w-3 shrink-0" aria-hidden /><span className="truncate"><span className="sr-only">Before leaving this stage: </span>{text}</span>
    </span>
  )
}
