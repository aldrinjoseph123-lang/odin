import { useCallback, useEffect, useState } from "react"
import { projectAI, type ProjectAI } from "@/lib/api"

// Ask again every `ms` while `on` (an AI job is queued or running). A hidden
// tab does not ask, and after `max` asks it stops: a job the scheduler never
// picks up must not poll the server forever. The progress line then says it
// is still waiting (after `window`, which is ms × max) and offers "Check
// again": `recheck` asks once and starts the count again (review P3-40).
export type Poll = { recheck: () => void; window: number }
export function usePoll(on: boolean, fn: () => unknown, ms = 4000, max = 75): Poll {
  const [round, setRound] = useState(0)
  useEffect(() => {
    if (!on) return
    let asked = 0
    const t = window.setInterval(() => {
      if (document.hidden) return
      if (++asked > max) { window.clearInterval(t); return }
      void fn()
    }, ms)
    return () => window.clearInterval(t)
  }, [on, fn, ms, max, round])
  const recheck = useCallback(() => { void fn(); setRound((n) => n + 1) }, [fn])
  return { recheck, window: ms * max }
}

// One AI feature's state for a project (the latest suggestion, a running
// job, whether it can run): loaded on mount (and when `refresh` changes),
// polled while a job is queued or running.
export function useProjectAI<T>(projectId: number, feature: string, { enabled = true, every, refresh }: { enabled?: boolean; every?: number; refresh?: unknown } = {}) {
  const [s, setS] = useState<ProjectAI<T> | null>(null)
  const load = useCallback(async () => {
    try { setS(await projectAI<T>(projectId, feature)) } catch { /* a failed poll keeps the draft bar as it was (review P2-29) */ }
  }, [projectId, feature])
  useEffect(() => { if (enabled) void load() }, [load, enabled, refresh])
  const working = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  const poll = usePoll(working, load, every)
  return { s, load, working, poll }
}
