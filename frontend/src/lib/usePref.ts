import { useCallback, useState } from "react"

// A choice the person makes again and again (a view, a filter, a mode), kept
// in this browser per person (advice B1). Storage may be off (a private
// window): then the choice lasts the visit and nothing breaks.
let who = 0
export function setPrefUser(id: number) { who = id }
const slot = (key: string) => `odin.pref.${who}.${key}`

export function readPref<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(slot(key)); return v == null ? fallback : (JSON.parse(v) as T) } catch { return fallback }
}

export function usePref<T>(key: string, fallback: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => readPref(key, fallback))
  const set = useCallback((next: T) => {
    setV(next)
    try { localStorage.setItem(slot(key), JSON.stringify(next)) } catch { /* private mode: forgotten on reload */ }
  }, [key])
  return [v, set]
}
