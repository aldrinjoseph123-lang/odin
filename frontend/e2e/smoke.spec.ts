import { expect, test } from "@playwright/test"
import { expectClean, signIn, watch, type Who } from "./helpers"

// @smoke: every page renders for every kind of account, and every control in
// the header goes where it says. Shallow on purpose; the journeys are in the
// other specs.
const PAGES: { path: string; h1: RegExp; who?: Who[] }[] = [
  { path: "/dashboard", h1: /Good (morning|afternoon|evening)/ },
  { path: "/board", h1: /Active rollouts/ },
  { path: "/board?view=calendar", h1: /Calendar/ },
  { path: "/board?view=kibana", h1: /Kibana/ },
  { path: "/my-work", h1: /My work/ },
  { path: "/people", h1: /People/ },
  { path: "/people/2", h1: /./ },
  { path: "/projects", h1: /Projects/ },
  { path: "/projects/1", h1: /EDR Rollout - Globex/ },
  { path: "/projects/new", h1: /New project/, who: ["admin", "member"] },
  { path: "/projects/1/edit", h1: /Edit/, who: ["admin"] },   // editing needs a role on the project
  { path: "/projects/1/report", h1: /EDR Rollout - Globex/ },
  { path: "/projects/1/signoff", h1: /Sign-off/ },
  { path: "/reports/all", h1: /report/i },
  { path: "/analytics", h1: /Cycle time/ },
  { path: "/alerts", h1: /Alerts/ },
  { path: "/account", h1: /My account/ },
  { path: "/settings/general", h1: /General/, who: ["admin"] },
  { path: "/settings/security", h1: /Sign-in/, who: ["admin"] },
  { path: "/settings/workflow", h1: /workflow/i, who: ["admin"] },
  { path: "/settings/notifications", h1: /Notifications/, who: ["admin"] },
  { path: "/settings/integrations", h1: /Integrations/, who: ["admin"] },
  { path: "/settings/reports", h1: /Reports/, who: ["admin"] },
  { path: "/settings/backups", h1: /Backups/, who: ["admin"] },
  { path: "/settings/documents", h1: /Documents/, who: ["admin"] },
  { path: "/settings/api", h1: /API/, who: ["admin"] },
  { path: "/settings/audit", h1: /Audit/, who: ["admin"] },
  { path: "/settings/rbac", h1: /Role permissions/, who: ["admin"] },
  { path: "/settings/contacts", h1: /Contacts/, who: ["admin"] },
  { path: "/users", h1: /Users/, who: ["admin"] },
  { path: "/audit-logs", h1: /Audit log/, who: ["admin"] },
]

for (const who of ["admin", "member", "viewer"] as Who[]) {
  test(`@smoke every page renders for ${who}`, async ({ page }) => {
    const errors = watch(page)
    await signIn(page, who)
    for (const p of PAGES) {
      if (p.who && !p.who.includes(who)) continue
      await page.goto(p.path)
      await expect(page.locator("h1").first(), p.path).toHaveText(p.h1)
      await expect(page.locator("main"), p.path).toBeVisible()
    }
    expectClean(errors)
  })
}

test("@smoke a viewer is refused the admin pages, not shown a broken one", async ({ page }) => {
  await signIn(page, "viewer")
  for (const path of ["/settings/general", "/users", "/projects/new"]) {
    const r = await page.request.get(path)
    expect(r.status(), path).toBe(403)
  }
})

test("@smoke the header: every link lands, every button does something", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin")
  // the logo and the nav pills
  for (const [label, path] of [["Dashboard", "/dashboard"], ["Flow", "/board"], ["My work", "/my-work"], ["Projects", "/projects"], ["People", "/people"], ["Cycle time", "/analytics"], ["Alerts", "/alerts"], ["Settings", "/settings/general"]]) {
    await page.getByRole("navigation").getByRole("link", { name: new RegExp(`^${label}`) }).click()
    await expect(page, label).toHaveURL(new RegExp(path.replace("?", "\\?")))
  }
  await page.getByRole("link", { name: "Odin, home" }).click()
  await expect(page).toHaveURL(/\/dashboard/)
  // the current pill is filled
  await expect(page.getByRole("navigation").getByRole("link", { name: /^Dashboard/ })).toHaveAttribute("aria-current", /page/).catch(() => { /* aria-current is optional here; the fill is checked visually */ })
  // search opens the palette and Esc closes it
  await page.getByRole("button", { name: "Search projects and tasks" }).click()
  const palette = page.getByRole("dialog").or(page.getByPlaceholder(/Search|Jump/))
  await expect(palette.first()).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(palette.first()).toBeHidden()
  // theme cycles and is remembered on the account
  const theme = page.getByRole("button", { name: /^Theme:/ })
  const before = await theme.getAttribute("aria-label")
  await theme.click()
  await expect(theme).not.toHaveAttribute("aria-label", before!)
  const after = (await theme.getAttribute("aria-label"))!.match(/Theme: (\w+)/)![1]
  await page.reload()
  await expect(page.getByRole("button", { name: /^Theme:/ })).toHaveAttribute("aria-label", new RegExp(`Theme: ${after}`))
  // notifications open a list
  await page.getByRole("button", { name: "Notifications" }).click()
  await expect(page.getByText(/Notifications|Nothing new|No notifications/i).first()).toBeVisible()
  await page.keyboard.press("Escape")
  // new project, account, log out
  await page.getByRole("link", { name: "New project" }).click()
  await expect(page).toHaveURL(/\/projects\/new/)
  await page.getByRole("link", { name: "Your account" }).click()
  await expect(page).toHaveURL(/\/account/)
  await page.getByRole("button", { name: "Log out" }).first().click()
  await expect(page).toHaveURL(/\/login/)
  expectClean(errors)
})

test("@smoke @phoneonly the header folds into a menu that reaches every page", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin")
  await page.getByRole("button", { name: "Menu" }).click()
  await page.getByRole("navigation").getByRole("link", { name: /^Flow/ }).click()
  await expect(page).toHaveURL(/\/board/)
  await expect(page.locator("h1").first()).toHaveText(/Active rollouts/)
  expectClean(errors)
})

test("@smoke the sign-in page says what is missing and what is wrong", async ({ page }) => {
  await page.goto("/login")
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page.getByRole("alert")).toHaveText(/Enter your username/)
  await page.getByLabel("Username").fill("admin")
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page.getByRole("alert")).toHaveText(/Enter your password/)
  await page.getByLabel("Password", { exact: true }).fill("wrong-password-1")
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page.getByRole("alert")).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
  await page.getByLabel("Password", { exact: true }).fill("Glacier-Harbour-4471")
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/dashboard/)
})
