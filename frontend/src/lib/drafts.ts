// Save their work before they are signed out (UI states, 2 Nov 2026): when a
// request comes back 401 the words typed on the page are stashed in
// sessionStorage under its address; after the sign-in lands back there, the
// fields that render get their words back and a toast says so. Same tab only
// (sessionStorage), one hour, text fields and textareas, never passwords.
// Values go in through the prototype setter so React's controlled inputs see
// the change as typing.
import { toast } from "@/lib/toast"

const KEY = "odin.drafts"
const HOUR = 60 * 60 * 1000
type Field = HTMLTextAreaElement | HTMLInputElement
type Stash = { at: number; path: string; values: Record<string, string> }

const fieldKey = (el: Field, i: number) => el.name || el.id || el.getAttribute("aria-label") || el.placeholder || `#${i}`

function fields(doc: Document): Field[] {
  return [...doc.querySelectorAll<Field>("textarea, input[type=text], input:not([type])")].filter((el) => !el.readOnly && !el.disabled)
}

function read(): Stash | null {
  try { return JSON.parse(sessionStorage.getItem(KEY) || "null") as Stash | null } catch { return null }
}

function write(stash: Stash | null) {
  try { stash ? sessionStorage.setItem(KEY, JSON.stringify(stash)) : sessionStorage.removeItem(KEY) } catch { /* private window: nothing kept */ }
}

export function stashDrafts(doc: Document | undefined = globalThis.document) {
  if (!doc) return   // no page (a unit test in node)
  const values: Record<string, string> = {}
  fields(doc).forEach((el, i) => { if (el.value.trim()) values[fieldKey(el, i)] = el.value })
  if (Object.keys(values).length) write({ at: Date.now(), path: doc.location.pathname, values })
}

function setValue(el: Field, v: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, v)
  el.dispatchEvent(new Event("input", { bubbles: true }))
}

// Puts back what matches the fields on the page now; true when nothing is left to restore.
export function restoreDrafts(doc: Document = document): boolean {
  const stash = read()
  if (!stash) return true
  if (Date.now() - stash.at > HOUR) { write(null); return true }
  if (stash.path !== doc.location.pathname) return true   // another page (the sign-in page on the way back): leave it for its own
  let n = 0
  fields(doc).forEach((el, i) => {
    const k = fieldKey(el, i)
    const v = stash.values[k]
    if (v !== undefined && !el.value) { setValue(el, v); delete stash.values[k]; n++ }
  })
  if (n) toast("What you typed before the sign-out is back.")
  const done = Object.keys(stash.values).length === 0
  write(done ? null : stash)
  return done
}

// At boot: fields render after the page's data, so watch the page until the stash is used up (or a minute passes).
export function installDrafts(doc: Document = document) {
  if (restoreDrafts(doc)) return
  const mo = new MutationObserver(() => { if (restoreDrafts(doc)) mo.disconnect() })
  mo.observe(doc.body, { childList: true, subtree: true })
  setTimeout(() => mo.disconnect(), 60_000)
}
