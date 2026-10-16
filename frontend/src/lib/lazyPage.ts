import { createElement, lazy, type ComponentProps, type ComponentType } from "react"

// A deploy replaces the chunk files, so a tab opened before it asks for a
// file that is gone. Reload once to fetch the new build. The flag is the time
// of that reload: a chunk that fails again soon after is a real failure (the
// error screen, no loop), while one failing hours later reloads again.
// A failed chunk is not remembered: at a new address (where the error
// boundary clears too) it is asked for afresh.
const flag = "odin.chunk-reload"
const SOON = 30_000
const reloadedAt = () => { try { return Number(sessionStorage.getItem(flag) ?? 0) } catch { return Date.now() } }   // storage off: never reload
const here = () => location.pathname + location.search
const markReload = () => { try { sessionStorage.setItem(flag, String(Date.now())) } catch { /* private mode */ } }

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyPage<T extends ComponentType<any>>(load: () => Promise<{ default: T }>) {
  const make = () => lazy(() => load().catch((e: unknown) => {
    if (Date.now() - reloadedAt() < SOON) { failedAt = here(); throw e }
    markReload(); window.location.reload()
    return new Promise<{ default: T }>(() => {})
  }))
  let Page = make()
  let failedAt: string | null = null   // the address it failed at: React's own retry there still lands on the error
  return (props: ComponentProps<T>) => {
    if (failedAt !== null && failedAt !== here()) { failedAt = null; Page = make() }
    return createElement(Page, props)
  }
}
