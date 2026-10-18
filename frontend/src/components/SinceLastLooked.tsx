import { Link } from "react-router-dom"
import { ArrowRight, CheckSquare, Flag, ShieldCheck, TriangleAlert } from "lucide-react"
import { Ago } from "@/components/Ago"
import type { SinceData, SinceItem } from "@/lib/api"
import { sinceLine } from "@/lib/format"

// The dashboard's "Since you last looked" body (the Widget frame is the dashboard's):
// what moved on my rollouts since my previous visit, newest first.
const ICON = { move: ArrowRight, raid: TriangleAlert, decided: Flag, approval: ShieldCheck, ask: CheckSquare }
const iconOf = (kind: string) => ICON[(kind.startsWith("raid_") ? "raid" : kind) as keyof typeof ICON] ?? ArrowRight

export function SinceRows({ since, limit }: { since: SinceData; limit: number }) {
  if (since.items.length === 0) return <p className="py-4 text-center text-[13px] text-muted-foreground">Nothing new on your rollouts since you last looked.</p>
  return (
    <ul className="grid grid-cols-1 gap-3 text-[13px]">
      {since.items.slice(0, limit).map((a: SinceItem, i) => {
        const Icon = iconOf(a.kind)
        return (
          <li key={i} className="flex gap-3">
            <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"><Icon className="h-3.5 w-3.5" aria-hidden /></span>
            <span className="min-w-0">
              <Link to={`/board?rollout=${a.project_id}`} className="block truncate font-medium hover:underline">{a.project}</Link>
              <span className="block truncate text-muted-foreground">{sinceLine(a)}</span>
              <span className="block text-[11px] text-muted-foreground"><Ago iso={a.at} /></span>
            </span>
          </li>
        )
      })}
    </ul>
  )
}
