import { useEffect } from "react"

export const LEAVE_UNSAVED = "Leave this page? What you typed is not saved."

// While a form holds unsaved typing, closing the tab, following a link off
// the app, or clicking an in-app link (the nav, the logo) asks first (test
// report UX-9: in-app links dropped a half-filled form without a word).
export function useUnsavedGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = "" }
    const click = (e: MouseEvent) => {
      const a = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null
      if (!a || a.target === "_blank" || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return
      const to = new URL(a.href, location.href)
      if (to.origin !== location.origin || to.pathname + to.search === location.pathname + location.search) return
      if (!window.confirm(LEAVE_UNSAVED)) { e.preventDefault(); e.stopPropagation() }
    }
    window.addEventListener("beforeunload", warn)
    document.addEventListener("click", click, true)   // capture: before the router's own link handler
    return () => { window.removeEventListener("beforeunload", warn); document.removeEventListener("click", click, true) }
  }, [dirty])
}
