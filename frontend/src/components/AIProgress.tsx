import { useEffect, useState } from "react"
import { Progress } from "@/components/ui/progress"
import { Spinner } from "@/components/ui/spinner"
import { aiProgress } from "@/lib/format"
import type { ProjectAI } from "@/lib/api"
import type { Poll } from "@/lib/usePoll"

// Where an AI draft stands (9 Oct 2026, the user's call: "we are blind"): a
// spinner, a bar and a line. Queued: a sliding bar and how many jobs are ahead.
// Running: the bar fills towards the feature's usual time, ticking each second,
// and never claims 100% before the answer lands.
export function AIProgress({ job, doing, poll }: { job: NonNullable<ProjectAI<unknown>["job"]>; doing?: string; poll: Poll }) {
  const [now, setNow] = useState(() => Date.now())
  const [since, setSince] = useState(() => Date.now())   // when the page began watching; polling gives up after poll.window
  useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(t) }, [])
  const { pct, text } = aiProgress(job, now)
  return (
    <div className="mt-3 grid grid-cols-1 gap-2" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-[13px]">
        <Spinner className="size-4 text-muted-foreground" />
        {doing && <span className="font-medium">{doing}</span>}
        <span className="text-muted-foreground">{text}</span>
      </div>
      {now - since > poll.window && (
        <p className="text-[13px] text-muted-foreground">Still waiting after {Math.round(poll.window / 60_000)} minutes. The AI server may be busy or switched off.{" "}
          <button type="button" className="font-medium text-primary-text hover:underline" onClick={() => { setSince(Date.now()); poll.recheck() }}>Check again</button></p>
      )}
      {pct === null ? (
        <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden>
          <span className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-nav-fg/60 motion-safe:animate-[odin-indeterminate_1.4s_ease-in-out_infinite]" />
        </div>
      ) : (
        <Progress value={pct} aria-label={`${doing ?? "AI draft"}: ${Math.round(pct)}%`} className="[&_[data-slot=progress-indicator]]:bg-nav-fg/70 [&_[data-slot=progress-track]]:h-1.5" />
      )}
    </div>
  )
}
