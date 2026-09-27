import { useEffect } from "react"

// While a form holds unsaved typing, closing the tab or following a link off
// the app asks first. (In-app route changes are rare on these pages.)
export function useUnsavedGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = "" }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [dirty])
}
