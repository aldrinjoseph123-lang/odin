import { useEffect } from "react"
import { pingActivity } from "@/lib/api"
import { shouldPing } from "@/lib/format"

// Counts active minutes: once a minute, while this tab is visible and was used
// within the idle limit (Settings → Sign-up & activity; 0 = tracking off). The server ignores pings under 50 s apart, so
// several open tabs still count one minute.
export function useActivityPing(idleMinutes = 5) {
  useEffect(() => {
    if (!idleMinutes) return
    let last = Date.now()
    const touch = () => { last = Date.now() }
    const events = ["pointerdown", "keydown", "wheel", "touchstart", "mousemove"] as const
    events.forEach((e) => window.addEventListener(e, touch, { passive: true }))
    const tick = () => { if (shouldPing(Date.now(), last, document.visibilityState === "visible", idleMinutes)) void pingActivity().catch(() => {}) }
    tick()
    const timer = window.setInterval(tick, 60_000)
    return () => { window.clearInterval(timer); events.forEach((e) => window.removeEventListener(e, touch)) }
  }, [idleMinutes])
}
