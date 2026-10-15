import { lazy, type ComponentType } from "react"

// A deploy replaces the chunk files, so a tab opened before it asks for a
// file that is gone. Reload once to fetch the new build; the flag stops a loop
// and is cleared once a chunk loads again.
const flag = "odin.chunk-reload"
const store = {
  get: () => { try { return sessionStorage.getItem(flag) } catch { return "1" } },
  set: (v: string | null) => { try { if (v) sessionStorage.setItem(flag, v); else sessionStorage.removeItem(flag) } catch { /* private mode */ } },
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyPage<T extends ComponentType<any>>(load: () => Promise<{ default: T }>) {
  return lazy(() => load().then((m) => { store.set(null); return m }, (e) => {
    if (store.get()) throw e
    store.set("1"); window.location.reload()
    return new Promise<{ default: T }>(() => {})
  }))
}
