export type Theme = "system" | "light" | "dark"
export type Accent = "blue" | "indigo" | "violet" | "teal" | "green" | "sky" | "plum" | "ink"
export const THEMES: Theme[] = ["system", "light", "dark"]
export const ACCENTS: { key: Accent; label: string; swatch: string }[] = [
  { key: "blue", label: "Blue", swatch: "#3D5AFE" }, { key: "indigo", label: "Indigo", swatch: "#4F46E5" },
  { key: "violet", label: "Violet", swatch: "#7C3AED" }, { key: "teal", label: "Teal", swatch: "#0F766E" },
  { key: "green", label: "Green", swatch: "#15803D" }, { key: "sky", label: "Sky", swatch: "#0369A1" },
  { key: "plum", label: "Plum", swatch: "#A21CAF" }, { key: "ink", label: "Ink", swatch: "#101114" },
]

const media = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null
let current: Theme = "system"

function paint(theme: Theme, accent: Accent) {
  const dark = theme === "dark" || (theme === "system" && !!media?.matches)
  const root = document.documentElement
  root.dataset.theme = dark ? "dark" : "light"
  root.dataset.accent = accent
  root.classList.toggle("dark", dark)
}

// Apply now and remember for the next first paint. With "system", follow the OS as it changes.
export function applyTheme(theme: Theme, accent: Accent) {
  current = theme
  paint(theme, accent)
  try { localStorage.setItem("odin.theme", theme); localStorage.setItem("odin.accent", accent) } catch { /* private mode */ }
}
media?.addEventListener("change", () => { if (current === "system") paint("system", (document.documentElement.dataset.accent as Accent) || "blue") })

export const isDark = () => document.documentElement.dataset.theme === "dark"
