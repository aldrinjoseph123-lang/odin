import { useEffect } from "react"

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
