import { useCallback, useState } from "react"
import { ApiError } from "@/lib/api"
import { toast } from "@/lib/toast"

// One button's worth of work: busy while it runs, then reload what it may
// have changed (`after`, whatever the outcome), and a line by the control:
// `done` on success, the server's words (as an error) on failure. `act`
// answers whether it went through. `quiet` is for a control with no room for a
// line (a header button, a quick add): the failure shows as a toast instead.
export type ActNote = { text: string; bad?: boolean }
export function useAction(after?: () => unknown, { quiet = false } = {}) {
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<ActNote | null>(null)
  const act = useCallback(async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true); setNote(null)
    try { await fn(); if (done) setNote({ text: done }); return true }
    catch (e) {
      const text = e instanceof ApiError ? e.message : "That did not work"
      if (quiet) toast(text, { tone: "bad" }); else setNote({ text, bad: true })
      return false
    }
    finally { await after?.(); setBusy(false) }   // a failure part-way may have changed things too
  }, [after, quiet])
  return { busy, note, setNote, act }
}
