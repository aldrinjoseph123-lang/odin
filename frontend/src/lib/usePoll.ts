import { useCallback, useEffect, useState } from "react"
import { projectAI, type ProjectAI } from "@/lib/api"

// Ask again every `ms` while `on` (an AI job is queued or running). A hidden
// tab does not ask, and after `max` asks (5 min at 4 s) it stops: a job the
// scheduler never picks up must not poll the server forever.
export function usePoll(on: boolean, fn: () => unknown, ms = 4000, max = 75) {
  useEffect(() => {
    if (!on) return
    let asked = 0
    const t = window.setInterval(() => {
      if (document.hidden) return
      if (++asked > max) { window.clearInterval(t); return }
      void fn()
    }, ms)
    return () => window.clearInterval(t)
  }, [on, fn, ms, max])
}

// One AI feature's state for a project (the latest suggestion, a running
// job, whether it can run): loaded on mount (and when `refresh` changes),
// polled while a job is queued or running.
export function useProjectAI<T>(projectId: number, feature: string, { enabled = true, every, refresh }: { enabled?: boolean; every?: number; refresh?: unknown } = {}) {
  const [s, setS] = useState<ProjectAI<T> | null>(null)
  const load = useCallback(async () => {
    try { setS(await projectAI<T>(projectId, feature)) } catch { setS(null) }
  }, [projectId, feature])
  useEffect(() => { if (enabled) void load() }, [load, enabled, refresh])
  const working = !!s?.job && (s.job.status === "queued" || s.job.status === "running")
  usePoll(working, load, every)
  return { s, load, working }
}
