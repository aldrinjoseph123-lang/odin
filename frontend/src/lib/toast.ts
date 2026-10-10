import { useSyncExternalStore } from "react"

// Affirmative feedback for an action that changed something: a short line
// that slides in at the bottom and leaves on its own (4 s; 8 s with an action).
// At most three show at once. Errors that need reading stay inline, by the field.
export type Toast = { id: number; text: string; tone: "ok" | "bad"; action?: { label: string; run: () => void } }

let items: Toast[] = []
let next = 0
const subs = new Set<() => void>()
const emit = () => subs.forEach((f) => f())

export function toast(text: string, opts: { tone?: "ok" | "bad"; action?: Toast["action"] } = {}) {
  const t: Toast = { id: ++next, text, tone: opts.tone ?? "ok", action: opts.action }
  items = [...items.slice(-2), t]
  emit()
  setTimeout(() => dismissToast(t.id), t.action ? 8000 : 4000)
  return t.id
}

export function dismissToast(id: number) {
  if (!items.some((t) => t.id === id)) return
  items = items.filter((t) => t.id !== id)
  emit()
}

export const currentToasts = () => items

// A save that ends in a full page load (the project form) hands its line to
// the next page, which shows it as soon as this module loads.
const CARRY = "odin.toast"
export function toastAfterLoad(text: string) {
  try { sessionStorage.setItem(CARRY, text) } catch { /* storage off: the page change is the receipt */ }
}
try {
  const carried = typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(CARRY)
  if (carried) { sessionStorage.removeItem(CARRY); toast(carried) }
} catch { /* storage off */ }

export function useToasts(): Toast[] {
  return useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => items, () => items)
}
