import { expect, type Locator, type Page, type ConsoleMessage } from "@playwright/test"

// The seeded accounts (scripts/seed_uat.py). Test values on a throw-away database.
export const USERS = {
  admin: { username: "admin", password: "Glacier-Harbour-4471", name: "Admin" },
  member: { username: "pm1", password: "Correct-Horse-Battery-9", name: "Priya Menon" },
  contributor: { username: "eng1", password: "Correct-Horse-Battery-9", name: "Omar Haddad" },
  viewer: { username: "vw1", password: "Correct-Horse-Battery-9", name: "Viewer One" },
} as const
export type Who = keyof typeof USERS

// Sign in through the JSON door the React page uses, then land somewhere.
export async function signIn(page: Page, who: Who = "admin", landing = "/dashboard") {
  await page.goto("/login")
  const u = USERS[who]
  await page.evaluate(async ({ username, password }) => {
    const s = await (await fetch("/api/session")).json()
    const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": s.csrf }, body: JSON.stringify({ username, password }) })
    if (!r.ok) throw new Error(`sign-in failed: ${r.status}`)
  }, { username: u.username, password: u.password })
  await page.goto(landing)
}

// Every page must stay free of console errors and failed requests; call this
// before navigating and assert with `expectClean` at the end of the test.
export function watch(page: Page) {
  const errors: string[] = []
  page.on("console", (m: ConsoleMessage) => { if (m.type() === "error") errors.push(`console: ${m.text()}`) })
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`))
  page.on("response", (r) => { if (r.status() >= 400 && !r.url().includes("/api/login")) errors.push(`${r.status()} ${r.url()}`) })
  return errors
}
export function expectClean(errors: string[]) {
  expect(errors, "no console errors, page errors or failed requests").toEqual([])
}

// Dark on demand: the app reads the theme from the root attribute (index.html sets it before paint).
// Transitions are switched off first: a colour sampled mid-fade is neither theme.
export async function setTheme(page: Page, theme: "light" | "dark") {
  await page.addStyleTag({ content: "*, *::before, *::after { transition: none !important; animation: none !important }" })
  await page.evaluate((t) => { document.documentElement.dataset.theme = t; document.documentElement.classList.toggle("dark", t === "dark") }, theme)
  await page.waitForTimeout(50)
}

// The date picker (shadcn Calendar in a popover): open it unless it is open,
// choose month and year in the caption, then click the day.
export async function pickDate(page: Page, trigger: Locator, iso: string) {
  const [y, m, d] = iso.split("-").map(Number)
  const pop = page.locator("[data-slot='popover-content']").last()
  if (!(await pop.isVisible().catch(() => false))) await trigger.click()
  await expect(pop).toBeVisible()
  const selects = pop.locator("select")
  await selects.nth(1).selectOption(String(y))
  await selects.nth(0).selectOption(String(m - 1))
  const month = new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "long" })
  await pop.getByRole("button", { name: new RegExp(`${month} ${d}(st|nd|rd|th)?, ${y}`) }).click()
  await expect(pop).toBeHidden()
}
