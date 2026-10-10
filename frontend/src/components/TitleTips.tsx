import { useEffect, useState } from "react"
import { CUT, tipText } from "@/lib/tips"

// Tooltips for the whole app, from what the markup already says: an element's
// `title` (truncated names, icon hints) or, for an icon-only control, its
// aria-label. One styled bubble replaces the browser's slow native tooltip:
// after a short hover, at once on keyboard focus; gone on leave, scroll or Esc.
// Elements that use the Tooltip component (data-slot="tooltip-trigger") keep theirs.
type Tip = { text: string; x: number; y: number; below: boolean }

export function TitleTips() {
  const [tip, setTip] = useState<Tip | null>(null)
  useEffect(() => {
    let timer: number | undefined
    let current: HTMLElement | null = null
    const hide = () => { window.clearTimeout(timer); current = null; setTip(null) }
    const show = (el: HTMLElement, delay: number) => {
      const text = tipText(el)
      if (!text) return
      window.clearTimeout(timer)
      current = el
      timer = window.setTimeout(() => {
        if (current !== el || !el.isConnected) return
        const r = el.getBoundingClientRect()
        const below = r.top < 48
        setTip({ text, x: Math.min(Math.max(r.left + r.width / 2, 128), window.innerWidth - 128), y: below ? r.bottom + 8 : r.top - 8, below })
      }, delay)
    }
    const target = (e: Event) => (e.target instanceof Element ? e.target.closest<HTMLElement>(`[title], [data-tip], button[aria-label], a[aria-label], [role='button'][aria-label], ${CUT}`) : null)
    const over = (e: PointerEvent) => {
      const el = target(e)
      if (!el || el.closest("[data-slot='tooltip-trigger']")) return
      if (el !== current) show(el, 450)
    }
    const out = (e: PointerEvent) => { if (current && !(e.relatedTarget instanceof Node && current.contains(e.relatedTarget))) hide() }
    const focus = (e: FocusEvent) => {
      const el = target(e)
      if (el && !el.closest("[data-slot='tooltip-trigger']") && el.matches(":focus-visible")) show(el, 0)
    }
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") hide() }
    document.addEventListener("pointerover", over)
    document.addEventListener("pointerout", out)
    document.addEventListener("focusin", focus)
    document.addEventListener("focusout", hide)
    document.addEventListener("pointerdown", hide, true)
    document.addEventListener("keydown", key)
    window.addEventListener("scroll", hide, true)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener("pointerover", over)
      document.removeEventListener("pointerout", out)
      document.removeEventListener("focusin", focus)
      document.removeEventListener("focusout", hide)
      document.removeEventListener("pointerdown", hide, true)
      document.removeEventListener("keydown", key)
      window.removeEventListener("scroll", hide, true)
    }
  }, [])
  if (!tip) return null
  return (
    <div role="tooltip" className="pointer-events-none fixed z-[110] max-w-60 rounded-md bg-foreground px-2 py-1 text-[12px] leading-snug text-background shadow-pop animate-in fade-in duration-100"
      style={{ left: tip.x, top: tip.y, transform: `translate(-50%, ${tip.below ? "0" : "-100%"})` }}>
      {tip.text}
    </div>
  )
}
