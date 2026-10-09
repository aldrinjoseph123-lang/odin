export type Theme = "system" | "light" | "dark"
export type Accent = "red" | "blue" | "indigo" | "violet" | "teal" | "green" | "sky" | "plum" | "ink"
export const THEMES: Theme[] = ["system", "light", "dark"]
export const ACCENTS: { key: Accent; label: string; swatch: string }[] = [
  // pastel fills (the swatch is the fill the buttons and selection use)
  { key: "red", label: "Red", swatch: "#FFD3DA" }, { key: "blue", label: "Blue", swatch: "#CCDAFF" },
  { key: "indigo", label: "Indigo", swatch: "#D6D8FF" }, { key: "violet", label: "Violet", swatch: "#E2D5FF" },
  { key: "teal", label: "Teal", swatch: "#C4EEE6" }, { key: "green", label: "Green", swatch: "#CFF0D9" },
  { key: "sky", label: "Sky", swatch: "#C9E8FB" }, { key: "plum", label: "Plum", swatch: "#F4D5F8" },
  { key: "ink", label: "Ink", swatch: "#E3E5EA" },
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
media?.addEventListener("change", () => { if (current === "system") paint("system", (document.documentElement.dataset.accent as Accent) || "red") })

export const isDark = () => document.documentElement.dataset.theme === "dark"
