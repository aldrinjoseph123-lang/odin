import { UserAvatar } from "@/components/UserAvatar"
import { cn } from "@/lib/utils"

// Who is on it, at a glance: PM first, then up to two more, then "+n".
export function TeamStack({ people, className }: { people: { id: number; name: string; avatar_url: string | null }[]; className?: string }) {
  const shown = people.slice(0, 3)
  return (
    <span className={cn("items-center -space-x-1.5", className)} title={people.map((p) => p.name).join(", ")}>
      {shown.map((p) => <UserAvatar key={p.id} name={p.name} url={p.avatar_url} className="ring-2 ring-background" />)}
      {people.length > 3 && <span className="ml-1 pl-1.5 text-[11px] text-muted-foreground">+{people.length - 3}</span>}
    </span>
  )
}
