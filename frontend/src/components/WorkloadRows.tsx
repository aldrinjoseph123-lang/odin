import { Link } from "react-router-dom"
import { UserAvatar } from "@/components/UserAvatar"
import type { WorkloadData } from "@/lib/api"
import { cn } from "@/lib/utils"
import { cellTitle, hrs, LEVEL_BAR, LEVEL_TEXT, levelWord, weekLabel } from "@/lib/workload"

// The dashboard's Workload widget body (the Widget frame is the dashboard's):
// the busiest people first, a bar per week of the next four, each as tall as
// its share of capacity. The same numbers as People › Workload.
export function WorkloadRows({ w, limit }: { w: WorkloadData; limit: number }) {
  const people = w.people.slice(0, limit)
  if (people.length === 0) return <p className="py-4 text-center text-[13px] text-muted-foreground">Nobody to plan yet.</p>
  return (
    <ul className="divide-y divide-border text-[13px]">
      {people.map((p) => {
        const now = p.weeks[0], worst = p.weeks.reduce((a, c) => (c.pct > a.pct ? c : a)).level, word = levelWord(worst)
        return (
          <li key={p.id} className="flex items-center gap-3 py-2">
            <UserAvatar name={p.name} url={p.avatar_url} className="h-8 w-8" />
            <span className="min-w-0 flex-1">
              <Link to={`/people/${p.id}`} className="block truncate font-medium hover:underline">{p.name}</Link>
              <span className="block truncate text-[12px] text-muted-foreground">{hrs(now.hours)} of {hrs(p.capacity)} this week{word && <> · <span className={cn("font-medium", LEVEL_TEXT[worst])}>{word}</span></>}</span>
            </span>
            <span className="flex h-8 items-end gap-1" role="img" aria-label={p.weeks.map((c, i) => `${weekLabel(c.week, i)}: ${cellTitle(c, p.capacity)}`).join(". ")}>
              {p.weeks.map((c) => (
                <span key={c.week} title={cellTitle(c, p.capacity)} className="flex h-full w-2 items-end overflow-hidden rounded-sm bg-muted">
                  <span className={cn("block w-full", LEVEL_BAR[c.level])} style={{ height: `${Math.max(8, Math.min(100, c.pct))}%` }} />
                </span>
              ))}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
