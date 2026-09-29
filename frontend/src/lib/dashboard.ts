// The dashboard layout: an ordered list of widgets with a width in thirds.
// Pure helpers, tested in dashboard.test.ts; the page only renders them.
export type Width = 1 | 2 | 3
export type LayoutItem = { id: string; w: Width; settings: Record<string, unknown> }

// Tailwind needs whole class names: one per width, on the md (2-col) and xl (3-col) grids.
export const WIDTH_CLASS: Record<Width, string> = { 1: "", 2: "md:col-span-2 xl:col-span-2", 3: "md:col-span-2 xl:col-span-3" }

export function move(layout: LayoutItem[], id: string, by: -1 | 1): LayoutItem[] {
  const i = layout.findIndex((x) => x.id === id)
  const j = i + by
  if (i < 0 || j < 0 || j >= layout.length) return layout
  const out = [...layout]
  ;[out[i], out[j]] = [out[j], out[i]]
  return out
}

// Drop the dragged widget before the one it was dropped on (or at the end).
export function reorder(layout: LayoutItem[], draggedId: string, beforeId: string | null): LayoutItem[] {
  const item = layout.find((x) => x.id === draggedId)
  if (!item || draggedId === beforeId) return layout
  const rest = layout.filter((x) => x.id !== draggedId)
  const at = beforeId ? rest.findIndex((x) => x.id === beforeId) : -1
  return at < 0 ? [...rest, item] : [...rest.slice(0, at), item, ...rest.slice(at)]
}

export const resize = (layout: LayoutItem[], id: string, w: Width) => layout.map((x) => (x.id === id ? { ...x, w } : x))
export const remove = (layout: LayoutItem[], id: string) => layout.filter((x) => x.id !== id)
export const configure = (layout: LayoutItem[], id: string, settings: Record<string, unknown>) =>
  layout.map((x) => (x.id === id ? { ...x, settings: { ...x.settings, ...settings } } : x))
export const same = (a: LayoutItem[], b: LayoutItem[]) => JSON.stringify(a) === JSON.stringify(b)

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
