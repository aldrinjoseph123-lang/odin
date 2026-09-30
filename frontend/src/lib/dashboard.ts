// The dashboard layout: an ordered list of widgets with a width in thirds.
// A repeatable widget (a custom metric) carries a handle, `uid`; the key that
// tells items apart is that handle, or the widget id for the rest.
// Pure helpers, tested in dashboard.test.ts; the page only renders them.
export type Width = 1 | 2 | 3
export type LayoutItem = { id: string; uid?: string; w: Width; settings: Record<string, unknown> }
export const keyOf = (x: { id: string; uid?: string }) => x.uid ?? x.id

// Tailwind needs whole class names: one per width, on the md (2-col) and xl (3-col) grids.
export const WIDTH_CLASS: Record<Width, string> = { 1: "", 2: "md:col-span-2 xl:col-span-2", 3: "md:col-span-2 xl:col-span-3" }

export function move(layout: LayoutItem[], key: string, by: -1 | 1): LayoutItem[] {
  const i = layout.findIndex((x) => keyOf(x) === key)
  const j = i + by
  if (i < 0 || j < 0 || j >= layout.length) return layout
  const out = [...layout]
  ;[out[i], out[j]] = [out[j], out[i]]
  return out
}

// Drop the dragged widget before the one it was dropped on (or at the end).
export function reorder(layout: LayoutItem[], draggedKey: string, beforeKey: string | null): LayoutItem[] {
  const item = layout.find((x) => keyOf(x) === draggedKey)
  if (!item || draggedKey === beforeKey) return layout
  const rest = layout.filter((x) => keyOf(x) !== draggedKey)
  const at = beforeKey ? rest.findIndex((x) => keyOf(x) === beforeKey) : -1
  return at < 0 ? [...rest, item] : [...rest.slice(0, at), item, ...rest.slice(at)]
}

export const resize = (layout: LayoutItem[], key: string, w: Width) => layout.map((x) => (keyOf(x) === key ? { ...x, w } : x))
export const remove = (layout: LayoutItem[], key: string) => layout.filter((x) => keyOf(x) !== key)
export const configure = (layout: LayoutItem[], key: string, settings: Record<string, unknown>) =>
  layout.map((x) => (keyOf(x) === key ? { ...x, settings: { ...x.settings, ...settings } } : x))
export const same = (a: LayoutItem[], b: LayoutItem[]) => JSON.stringify(a) === JSON.stringify(b)

// A handle for a new repeatable widget: short, unique enough, safe in a URL.
export const newUid = () => `c${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`

// "+12%" against the week before; null when there was nothing before.
export function pctChange(now: number, before: number): string | null {
  if (!before) return now ? null : "0%"
  const d = Math.round(((now - before) / before) * 100)
  return d === 0 ? "0%" : d > 0 ? `+${d}%` : `${d}%`
}

// The last n of a day series, and the n before them, for a "vs previous" line.
export function splitWindow<T>(series: T[], n: number): { now: T[]; before: T[] } {
  return { now: series.slice(-n), before: series.slice(-2 * n, -n) }
}
