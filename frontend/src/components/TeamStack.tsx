import type React from "react"
import { UserAvatar } from "@/components/UserAvatar"
import { cn } from "@/lib/utils"

// Who is on it, at a glance: PM first, then up to two more, then "+n".
// Faces overlap by a quarter, ringed in the card's colour so each edge reads;
// "+n" is a quiet count beside them, not another avatar.
export function TeamStack({ people, className, style, avatarClass }: { people: { id: number; name: string; avatar_url: string | null }[]; className?: string; style?: React.CSSProperties; avatarClass?: string }) {
  const shown = people.slice(0, 3)
  return (
    <span className={cn("items-center", className)} style={style} title={people.map((p) => p.name).join(", ")}>
      {shown.map((p, i) => <UserAvatar key={p.id} name={p.name} url={p.avatar_url} className={cn("ring-2 ring-card", i > 0 && "-ml-1", avatarClass)} />)}
      {people.length > 3 && <span className="ml-1 shrink-0 whitespace-nowrap text-[11px] tabular-nums text-muted-foreground">+{people.length - 3}</span>}
    </span>
  )
}
