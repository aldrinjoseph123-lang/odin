import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react"
import { ApiError, failureText } from "@/lib/api"
import { toast } from "@/lib/toast"

// One way for a page to load its data (review P2-29, advisor A5). The latest
// request wins: an answer that lands after a newer one was asked for is
// dropped. A refresh that fails keeps what is on screen and says so once,
// quietly, instead of swapping the page for an error; the error screen is only
// for a first load that failed. A new `key` starts afresh (no last record shown
// against a new id), or with `keep` holds the old rows until the new arrive (a
// filter change); if the new key fails, its error shows, not the old rows.
type State<T> = { key: string; data: T | null; error: ApiError | null; stale: boolean }

export function useLoad<T>(key: string, fn: () => Promise<T>, { keep = false } = {}) {
  const [s, setS] = useState<State<T>>({ key, data: null, error: null, stale: false })
  const shown = useRef(s)
  const latest = useRef(fn)
  const asked = useRef(0)
  useEffect(() => { latest.current = fn })
  const put = useCallback((next: State<T>) => { shown.current = next; setS(next) }, [])
  const reload = useCallback(async () => {
    const n = ++asked.current
    try {
      const data = await latest.current()
      if (n === asked.current) put({ key, data, error: null, stale: false })
    } catch (e) {
      if (n !== asked.current) return
      const error = e instanceof ApiError ? e : new ApiError(500, failureText(500))
      const was = shown.current
      // a new key that failed is the error, never the old key's rows passed off as its answer
      if (was.data === null || was.key !== key) return put({ key, data: null, error, stale: false })
      if (!was.stale) toast(error.status === 401 ? error.message : "Could not refresh just now: showing what was loaded before.", { tone: "bad" })
      put({ ...was, stale: true })
    }
  }, [key, put])
  useEffect(() => { void reload() }, [reload])   // a new key asks again, and so drops the old key's late answer
  // for a change made in place (an optimistic edit); the next load replaces it
  const setData = useCallback((v: SetStateAction<T | null>) => {
    const was = shown.current
    put({ ...was, data: typeof v === "function" ? (v as (x: T | null) => T | null)(was.data) : v })
  }, [put])
  const view: State<T> = s.key === key ? s : keep ? { ...s, error: null, stale: false } : { key, data: null, error: null, stale: false }
  return { data: view.data, error: view.error, stale: view.stale, reload, setData }
}
