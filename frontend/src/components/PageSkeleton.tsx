import { CircleAlert } from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { SIGNED_OUT } from "@/lib/api"
import { Skeleton } from "@/components/ui/skeleton"

// Placeholder while a page's data loads: the page's rough shape in muted
// bars, so the layout does not jump when content arrives.
export function PageSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="px-5 pt-4" role="status" aria-label="Loading">
      <Skeleton className="h-5 w-40" />
      <div className="mt-4 grid grid-cols-1 gap-2">
        {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-9 rounded-lg" style={{ opacity: 1 - i * 0.12 }} />)}
      </div>
    </div>
  )
}

// A page whose data did not load: what happened, and a way on — try again, or
// sign in when the session ended (test report UX-6, UX-7). Plain ink, not red:
// red in Odin means overdue.
// A missing record passes `back` (test report UX-18): a way out, not a retry.
export function LoadError({ message, back }: { message: string; back?: { href: string; label: string } }) {
  const signedOut = message === SIGNED_OUT
  return (
    <div className="p-5">
      <div className="flex max-w-xl flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 text-[13px]" role="alert">
        <CircleAlert className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1">{message}</span>
        {signedOut
          ? <a href={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} className={buttonVariants({ size: "sm" })}>Sign in</a>
          : back ? <a href={back.href} className={buttonVariants({ size: "sm", variant: "outline" })}>{back.label}</a>
          : <Button size="sm" variant="outline" onClick={() => location.reload()}>Try again</Button>}
      </div>
    </div>
  )
}
