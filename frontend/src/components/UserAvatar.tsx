import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { initials } from "@/lib/format"
import { cn } from "@/lib/utils"

// One avatar everywhere a person appears: the picture when they set one,
// their initials otherwise. Size and fallback tone come from the caller.
export function UserAvatar({ name, url, className, textClass = "text-[10px]", title }: { name: string; url?: string | null; className?: string; textClass?: string; title?: string }) {
  return (
    <Avatar className={cn("h-6 w-6", className)} title={title ?? name}>
      {url && <AvatarImage src={url} alt="" />}
      <AvatarFallback className={cn("bg-secondary font-semibold text-nav-fg", textClass)}>{initials(name)}</AvatarFallback>
    </Avatar>
  )
}
