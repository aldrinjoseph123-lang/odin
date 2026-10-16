import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"

// Contrast of the tokens in index.css, for every accent in light and dark (review
// P2-46): the focus ring and a tick box's edge at 3:1 against what they sit on,
// error text at 4.5:1 on the grounds and its own wash, a toast's glyph at 3:1.
const raw = (readFileSync(new URL("../index.css", import.meta.url), "utf8") as string).replace(/\/\*[\s\S]*?\*\//g, "")
// paper re-declares the light values (P2-48): screens never see the print block
const css = raw.replace(/@media print\s*\{/g, "\u0000").split("\u0000").map((part, i) => {
  if (i === 0) return part
  let depth = 1, j = 0
  for (; j < part.length && depth; j++) depth += part[j] === "{" ? 1 : part[j] === "}" ? -1 : 0
  return part.slice(j)
}).join("")
const blocks = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, sel, body]) => ({ sels: sel.split(",").map((x: string) => x.trim()), vars: Object.fromEntries([...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map(([, k, v]) => [k, v.trim()])) }))
type RGB = number[]
const hex = (h: string): RGB => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
const lin = (c: number) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }
const lum = (c: RGB) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])
const ratio = (a: RGB, b: RGB) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
const mix = (a: RGB, b: RGB, t: number) => a.map((v, i) => v * t + b[i] * (1 - t))
function tokens(theme: "light" | "dark", accent: string) {
  const ok = [":root", `:root[data-accent="${accent}"]`, ...(theme === "dark" ? [':root[data-theme="dark"]', `:root[data-theme="dark"][data-accent="${accent}"]`] : [])]
  const t: Record<string, string> = {}
  for (const b of blocks) if (b.sels.some((x) => ok.includes(x))) Object.assign(t, b.vars)
  const get = (k: string): RGB => { let v = t[k]; while (v?.startsWith("var(")) v = t[v.slice(6, -1)]; return hex(v) }
  return get
}

describe("token contrast", () => {
  for (const theme of ["light", "dark"] as const) for (const accent of ["red", "blue", "indigo", "violet", "teal", "green", "sky", "plum", "ink"]) {
    it(`${theme} ${accent}`, () => {
      const c = tokens(theme, accent)
      const card = c("card")
      const ground = theme === "light" ? mix(c("primary"), hex("#F6F6F9"), 0.07) : c("background")
      const min = (fg: RGB, backs: RGB[]) => Math.min(...backs.map((b) => ratio(fg, b)))
      expect(min(c("ring"), [card, ground, c("muted"), mix(c("accent"), card, 0.4)])).toBeGreaterThanOrEqual(3)
      expect(min(c("control"), [card, ground])).toBeGreaterThanOrEqual(3)
      expect(min(c("destructive"), [card, ground, mix(c("destructive"), card, 0.1), mix(c("destructive"), ground, 0.1)])).toBeGreaterThanOrEqual(4.5)
      // the primary button's label on its fill, and on the fill at hover (primary/80 over the card or the ground)
      const fill = c("primary")
      expect(min(c("primary-foreground"), [fill, mix(fill, card, 0.8), mix(fill, ground, 0.8)])).toBeGreaterThanOrEqual(4.5)
      expect(min(c("toast-ok"), [c("foreground")])).toBeGreaterThanOrEqual(3)
      expect(min(c("toast-bad"), [c("foreground")])).toBeGreaterThanOrEqual(3)
    })
  }
})
