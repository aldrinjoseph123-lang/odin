import { Button } from "@/components/ui/button"

// A panel whose data did not load: one quiet line and the retry, in place of
// the panel (the page around it carries on). Plain ink: red means overdue.
export function LoadFailed({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <p className="flex items-center gap-2 text-[13px] text-muted-foreground" role="alert">
      Could not load {what}. <Button size="sm" variant="outline" onClick={onRetry}>Try again</Button>
    </p>
  )
}
