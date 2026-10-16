import { useSyncExternalStore } from "react"

// Feedback for an action: a short line that slides in at the bottom. A plain
// confirmation leaves on its own after 4 s; one that must be read (an error)
// or acted on (an Undo) stays until it is used or dismissed (review P2-36),
// and any toast waits while the pointer or the keyboard is on it (WCAG 2.2.1).
// At most three show at once. Results that need studying (a connection test, a
// password refusal) belong inline, by their control, not here.
export type Toast = { id: number; text: string; tone: "ok" | "bad"; action?: { label: string; run: () => void } }

let items: Toast[] = []
let next = 0
const subs = new Set<() => void>()
const emit = () => subs.forEach((f) => f())

const timers = new Map<number, { handle?: ReturnType<typeof setTimeout>; left: number; since: number }>()
function arm(id: number, ms: number) {
  const t = timers.get(id)!
  t.left = ms; t.since = Date.now()
  t.handle = setTimeout(() => dismissToast(id), ms)
}

export function toast(text: string, opts: { tone?: "ok" | "bad"; action?: Toast["action"] } = {}) {
  const t: Toast = { id: ++next, text, tone: opts.tone ?? "ok", action: opts.action }
  items = [...items.slice(-2), t]
  emit()
  if (!t.action && t.tone !== "bad") { timers.set(t.id, { left: 4000, since: 0 }); arm(t.id, 4000) }
  return t.id
}

export function dismissToast(id: number) {
  const t = timers.get(id)
  if (t) { clearTimeout(t.handle); timers.delete(id) }
  if (!items.some((x) => x.id === id)) return
  items = items.filter((x) => x.id !== id)
  emit()
}

// Hold a toast's clock while it is hovered or focused; it gets at least 2 s once released.
export function holdToast(id: number) {
  const t = timers.get(id)
  if (!t || t.handle === undefined) return
  clearTimeout(t.handle); t.handle = undefined
  t.left -= Date.now() - t.since
}
export function releaseToast(id: number) {
  const t = timers.get(id)
  if (t && t.handle === undefined) arm(id, Math.max(t.left, 2000))
}

export const currentToasts = () => items

// A save that ends in a full page load (the project form) hands its line to
// the next page, which shows it as soon as this module loads.
// `undo`: a form route that puts it back (a deleted rollout, review P1-3); the
// toast's Undo posts it and follows the server to where the thing is again.
const CARRY = "odin.toast"
export function toastAfterLoad(text: string, undo?: string | null) {
  try { sessionStorage.setItem(CARRY, JSON.stringify({ text, undo: undo ?? null })) } catch { /* storage off: the page change is the receipt */ }
}
try {
  const carried = typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(CARRY)
  if (carried) {
    sessionStorage.removeItem(CARRY)
    const c = JSON.parse(carried) as { text: string; undo: string | null }
    toast(c.text, c.undo ? { action: { label: "Undo", run: () => void import("@/lib/api").then(({ postForm }) => postForm(c.undo!))
      .then((r) => { toastAfterLoad(r.messages.join(" ") || "Restored"); window.location.assign(r.location ?? "/board") })
      .catch((e: Error) => toast(e.message || "Could not undo", { tone: "bad" })), } } : {})   // stays until used; the window itself is the server's
  }
} catch { /* storage off */ }

export function useToasts(): Toast[] {
  return useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => items, () => items)
}
