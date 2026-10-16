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

// A JSON call from inside the page, in its own session and with the CSRF token,
// as the app's fetch does. For setting up and putting back what a journey changed.
export async function api<T = unknown>(page: Page, method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<{ status: number; body: T }> {
  return page.evaluate(async ({ method, path, body }) => {
    const s = await (await fetch("/api/session")).json()
    const r = await fetch(path, {
      method, headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": s.csrf },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    return { status: r.status, body: (await r.json().catch(() => null)) as never }
  }, { method, path, body })
}

// Invite an outside party to a rollout as the admin who is signed in on this page, and
// return the one-time sign-in link the server hands back when no mail is configured.
// A fresh address each time: the link is only shown for a brand-new account.
export async function inviteExternal(page: Page, projectId: number, role: "Customer" | "Contractor" | "Reseller"): Promise<{ email: string; link: string }> {
  const email = `e2e-${role.toLowerCase()}-${Date.now()}@partner.example`
  const messages = await page.evaluate(async ({ projectId, role, email }) => {
    const s = await (await fetch("/api/session")).json()
    const r = await fetch(`/projects/${projectId}/participants/invite`, {
      method: "POST", headers: { Accept: "application/json", "X-CSRF-Token": s.csrf, "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ email, name: `E2E ${role}`, role }).toString(),
    })
    return ((await r.json()) as { messages: string[] }).messages
  }, { projectId, role, email })
  const found = messages.join(" ").match(/https?:\/\/[^\s]+(\/auth\/link\/[^\s]+)/)
  if (!found) throw new Error(`no sign-in link in: ${messages.join(" | ")}`)
  return { email, link: found[1] }
}

// What an invited person does: open the emailed link and press Continue (the page
// only shows the button on GET, so a mail scanner opening it cannot spend the link).
export async function signInWithLink(page: Page, link: string) {
  await page.context().clearCookies()
  await page.goto(link)
  await page.getByRole("button", { name: "Continue to Odin" }).click()
  await expect(page).not.toHaveURL(/\/auth\/link/)
}

// A card dragged to a target (a Kanban column, a calendar day): press on the card, move off it a
// little so the drag starts, wait for the page to draw the drag, then let go inside the target.
// dnd-kit needs the in-between moves; two animation frames stand in for the old fixed waits.
export async function dragCard(page: Page, from: Locator, to: Locator) {
  await from.scrollIntoViewIfNeeded()
  const a = (await from.boundingBox())!
  const b = (await to.boundingBox())!
  const frames = () => page.evaluate(() => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))))
  await page.mouse.move(a.x + 6, a.y + 6)
  await page.mouse.down()
  await page.mouse.move(a.x + 30, a.y + 30, { steps: 4 }); await frames()
  await page.mouse.move(b.x + b.width / 2, b.y + Math.min(80, b.height / 2), { steps: 12 }); await frames()
  await page.mouse.up()
}
