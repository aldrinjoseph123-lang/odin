import { useCallback, useEffect, useState } from "react"

// An element's width, kept current: hand `ref` to the element.
export function useWidth<T extends HTMLElement>() {
  const [width, setWidth] = useState(0)
  const ref = useCallback((el: T | null) => {
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [width, ref] as const
}

// Whether a media query matches, following changes (true without matchMedia, as on the server).
export function useMedia(query: string) {
  const get = () => typeof window === "undefined" || typeof window.matchMedia !== "function" || window.matchMedia(query).matches
  const [on, setOn] = useState(get)
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const m = window.matchMedia(query)
    const change = () => setOn(m.matches)
    m.addEventListener("change", change)
    return () => m.removeEventListener("change", change)
  }, [query])
  return on
}
