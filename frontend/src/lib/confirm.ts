import { useSyncExternalStore } from "react"

// One confirm for the whole app, in Odin's own dialog (critique 10 Oct: three
// idioms became one). Write the question, then what it does: "Remove Ann? They
// lose access…". The dialog titles the question, describes the rest, and puts
// the first word on the button ("Remove"), red when it destroys.
type Ask = { text: string; action?: string; resolve: (ok: boolean) => void }
let current: Ask | null = null
const subs = new Set<() => void>()
const emit = () => subs.forEach((f) => f())

export function askConfirm(text: string, action?: string): Promise<boolean> {
  current?.resolve(false)   // a second question replaces an unanswered first
  return new Promise((resolve) => { current = { text, action, resolve }; emit() })
}

export function answerConfirm(ok: boolean) {
  const ask = current
  current = null
  emit()
  ask?.resolve(ok)
}

export const useConfirmAsk = () => useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => current, () => current)

// "Delete this note? It leaves the history." → title, description, verb
export function confirmParts(text: string): { title: string; detail: string; verb: string; danger: boolean } {
  const cut = text.indexOf("? ")
  const title = cut > 0 ? text.slice(0, cut + 1) : text
  const verb = title.split(" ")[0].replace(/[^A-Za-z-]/g, "") || "Confirm"
  return { title, detail: cut > 0 ? text.slice(cut + 2) : "", verb, danger: /^(Delete|Remove|Decline|Revoke|Withdraw|Rotate)$/.test(verb) }
}
