import { useSyncExternalStore } from "react"

export type Theme = "system" | "light" | "dark"
export type Accent = "red" | "blue" | "indigo" | "violet" | "teal" | "green" | "sky" | "plum" | "ink"
export const THEMES: Theme[] = ["system", "light", "dark"]
export const ACCENTS: { key: Accent; label: string; swatch: string }[] = [
  // pastel fills (the swatch is the fill the buttons and selection use)
  { key: "blue", label: "Blue", swatch: "#CCDAFF" }, { key: "red", label: "Red", swatch: "#FFD3DA" },
  { key: "indigo", label: "Indigo", swatch: "#D6D8FF" }, { key: "violet", label: "Violet", swatch: "#E2D5FF" },
  { key: "teal", label: "Teal", swatch: "#C4EEE6" }, { key: "green", label: "Green", swatch: "#CFF0D9" },
  { key: "sky", label: "Sky", swatch: "#C9E8FB" }, { key: "plum", label: "Plum", swatch: "#F4D5F8" },
  { key: "ink", label: "Ink", swatch: "#E3E5EA" },
]

const media = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null
// One source of truth for the client (review P2-33): the header button and the
// Account page both read and write it, so neither keeps a stale copy.
const stored = (k: string) => { try { return localStorage.getItem(k) } catch { return null } }
let current: { theme: Theme; accent: Accent } = { theme: (stored("odin.theme") as Theme) || "system", accent: (stored("odin.accent") as Accent) || "blue" }
const subs = new Set<() => void>()

function paint(theme: Theme, accent: Accent) {
  const dark = theme === "dark" || (theme === "system" && !!media?.matches)
  const root = document.documentElement
  root.dataset.theme = dark ? "dark" : "light"
  root.dataset.accent = accent
  root.classList.toggle("dark", dark)
}

// Apply now and remember for the next first paint. With "system", follow the OS as it changes.
export function applyTheme(theme: Theme, accent: Accent) {
  current = { theme, accent }
  paint(theme, accent)
  try { localStorage.setItem("odin.theme", theme); localStorage.setItem("odin.accent", accent) } catch { /* private mode */ }
  subs.forEach((f) => f())
}
media?.addEventListener("change", () => { if (current.theme === "system") paint("system", current.accent) })

export function useAppearance() {
  return useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => current, () => current)
}

// The saved choice from the server (the session's user): applied unless the
// header button has a newer one still waiting to be saved.
let saving: number | undefined
export function syncAppearance(theme: Theme, accent: Accent) { if (saving === undefined) applyTheme(theme, accent) }

// The header button: paint at once, save once the clicking stops, so three
// clicks are one POST and one audit row, not three.
type Save = (theme: Theme, accent: Accent, keepalive?: boolean) => Promise<unknown>
let pending: Save | null = null
export function cycleTheme(save: Save, ms = 800) {
  applyTheme(current.theme === "system" ? "light" : current.theme === "light" ? "dark" : "system", current.accent)
  pending = save
  window.clearTimeout(saving)
  saving = window.setTimeout(() => void flushAppearance(), ms)
}
// Save a click still waiting now: before logging out, and as the page goes
// (a reload, a closed tab: `keepalive` lets the request outlive the page).
export function flushAppearance(keepalive = false) {
  const save = pending
  if (saving === undefined || !save) return Promise.resolve()
  window.clearTimeout(saving); saving = undefined; pending = null
  return save(current.theme, current.accent, keepalive).catch(() => undefined)   // unsaved: stays local until the next save
}
if (typeof window !== "undefined") {
  window.addEventListener("pagehide", () => void flushAppearance(true))
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") void flushAppearance(true) })
}

export const isDark = () => document.documentElement.dataset.theme === "dark"
