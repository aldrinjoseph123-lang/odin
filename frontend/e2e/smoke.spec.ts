import { expect, test } from "@playwright/test"
import { expectClean, signIn, watch, type Who } from "./helpers"

// @smoke: every page renders for every kind of account, and every control in
// the header goes where it says. Shallow on purpose; the journeys are in the
// other specs.
const PAGES: { path: string; h1: RegExp; who?: Who[] }[] = [
  { path: "/dashboard", h1: /Good (morning|afternoon|evening)/ },
  { path: "/board", h1: /Active rollouts/ },
  { path: "/board?view=calendar", h1: /Calendar/ },
  { path: "/board?view=kanban", h1: /Active rollouts/ },
  { path: "/board?view=gantt", h1: /Active rollouts/ },
  { path: "/my-work", h1: /My work/ },
  { path: "/people", h1: /People/ },
  { path: "/people/2", h1: /./ },
  { path: "/people/workload", h1: /Workload/ },
  { path: "/projects", h1: /Rollouts/ },
  { path: "/projects/1", h1: /EDR Rollout - Globex/ },
  { path: "/projects/new", h1: /New project/, who: ["admin", "member"] },
  { path: "/projects/1/edit", h1: /Edit/, who: ["admin"] },   // editing needs a role on the project
  { path: "/projects/1/report", h1: /EDR Rollout - Globex/ },
  { path: "/projects/1/signoff", h1: /Sign-off/ },
  { path: "/reports/all", h1: /report/i },
  { path: "/analytics", h1: /Cycle time/ },
  { path: "/alerts", h1: /Alerts/ },
  { path: "/account", h1: /^Account$/ },
  { path: "/settings/general", h1: /General/, who: ["admin"] },
  { path: "/settings/security", h1: /Sign-in/, who: ["admin"] },
  { path: "/settings/workflow", h1: /workflow/i, who: ["admin"] },
  { path: "/settings/notifications", h1: /Notifications/, who: ["admin"] },
  { path: "/settings/integrations", h1: /Integrations/, who: ["admin"] },
  { path: "/settings/ai", h1: /^AI$/, who: ["admin"] },
  { path: "/settings/reports", h1: /Reports/, who: ["admin"] },
  { path: "/settings/backups", h1: /Backups/, who: ["admin"] },
  { path: "/settings/documents", h1: /Documents/, who: ["admin"] },
  { path: "/settings/people", h1: /Sign-up & activity/, who: ["admin"] },
  { path: "/settings/map", h1: /System map/, who: ["admin"] },
  { path: "/settings/api", h1: /API/, who: ["admin"] },
  { path: "/settings/audit", h1: /Retention/, who: ["admin"] },
  { path: "/settings/rbac", h1: /Role permissions/, who: ["admin"] },
  { path: "/settings/contacts", h1: /Contacts/, who: ["admin"] },
  { path: "/settings/automations", h1: /Automations/, who: ["admin"] },
  { path: "/users", h1: /Users/, who: ["admin"] },
  { path: "/audit-logs", h1: /Audit log/, who: ["admin"] },
]

for (const who of ["admin", "member", "viewer"] as Who[]) {
  // desktop and phone: every page also fits its window (test report UX-2 to UX-4)
  test(`@smoke @phone every page renders and fits for ${who}`, async ({ page }) => {
    const errors = watch(page)
    await signIn(page, who)
    for (const p of PAGES) {
      if (p.who && !p.who.includes(who)) continue
      await page.goto(p.path)
      await expect(page.locator("h1").first(), p.path).toHaveText(p.h1)
      await expect(page.locator("main"), p.path).toBeVisible()
      const [scroll, inner] = await page.evaluate(() => [document.scrollingElement!.scrollWidth, document.documentElement.clientWidth])
      expect(scroll, `${p.path} scrolls sideways`).toBeLessThanOrEqual(inner + 1)
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

test("@smoke the rollout page shows what its customer was asked, and what came back", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  await expect(page.getByRole("region", { name: "Asked of the customer and partners" })).toContainText("Tell us about your environment")
  expectClean(errors)
})

test("@smoke the rollout page lists its milestones, with the missed one in words", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  const panel = page.getByRole("region", { name: "Milestones" })
  await expect(panel).toContainText("Pilot go-live")
  await expect(panel).toContainText("Security review signed off")   // the internal one, already missed
  await expect(page.getByRole("link", { name: "Milestones" })).toHaveAttribute("href", "#milestones")   // the section row
  expectClean(errors)
})

test("@smoke the account page offers each kind at once, daily or off, and a calendar feed; a rollout offers mute or follow", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "member", "/account")
  await expect(page.getByRole("radiogroup", { name: "Tasks assigned to me" }).getByRole("radio", { name: "Daily summary" })).toBeVisible()
  await expect(page.getByRole("button", { name: /^(Make a feed|Make a new address)$/ })).toBeVisible()
  await page.goto("/board?rollout=1")
  await expect(page.getByRole("button", { name: /^(Mute|Unmute|Follow|Unfollow)$/ })).toBeVisible()
  expectClean(errors)
})

test("@smoke the header: every link lands, every button does something", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin")
  // the logo and the nav pills
  for (const [label, path] of [["Dashboard", "/dashboard"], ["Flow", "/board"], ["My work", "/my-work"], ["Rollouts", "/projects"], ["People", "/people"], ["Cycle time", "/analytics"], ["Alerts", "/alerts"], ["Settings", "/settings/general"]]) {
    await page.getByRole("navigation").getByRole("link", { name: new RegExp(`^${label}`) }).click()
    await expect(page, label).toHaveURL(new RegExp(path.replace("?", "\\?")))
  }
  await page.getByRole("link", { name: "Odin, home" }).click()
  await expect(page).toHaveURL(/\/dashboard/)
  // the current pill is filled
  await expect(page.getByRole("navigation").getByRole("link", { name: /^Dashboard/ })).toHaveAttribute("aria-current", "page")
  // search opens the palette and Esc closes it
  await page.getByRole("button", { name: "Search rollouts and tasks" }).click()
  const palette = page.getByRole("dialog").or(page.getByPlaceholder(/Search|Jump/))
  await expect(palette.first()).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(palette.first()).toBeHidden()
  // "?" opens the shortcut sheet, and so does the account menu
  await page.keyboard.press("?")
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeHidden()
  await page.getByRole("button", { name: "Your account" }).click()
  await page.getByRole("button", { name: /Keyboard shortcuts/ }).click()
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible()
  await page.keyboard.press("Escape")
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
  await page.getByRole("button", { name: "Your account" }).click()
  await page.getByRole("link", { name: "Account settings" }).click()
  await expect(page).toHaveURL(/\/account/)
  await page.getByRole("button", { name: "Your account" }).click()
  await page.getByRole("button", { name: "Log out" }).first().click()
  await expect(page).toHaveURL(/\/login/)
  expectClean(errors)
})

test("@smoke the admin's header fits laptop widths without sideways scrolling", async ({ page }) => {
  // test report UX-1: at 1280-1366 px Log out, the avatar and the theme switch sat off-screen
  await signIn(page, "admin")
  for (const width of [1024, 1280, 1366, 1440, 1536]) {
    await page.setViewportSize({ width, height: 800 })
    const [scroll, inner] = await page.evaluate(() => [document.scrollingElement!.scrollWidth, window.innerWidth])
    expect(scroll, `page width at ${width} px`).toBeLessThanOrEqual(inner)
    await expect(page.getByRole("button", { name: "Your account" })).toBeInViewport()
  }
})

test("@smoke @phoneonly the header folds into a menu that reaches every page", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin")
  const menu = page.getByRole("button", { name: "Menu" })
  // keyboard: focus moves into the menu, Escape closes it and returns (test report UX-12)
  await menu.click()
  await expect(page.getByRole("navigation").getByRole("link").first()).toBeFocused()
  await page.keyboard.press("Escape")
  await expect(menu).toHaveAttribute("aria-expanded", "false")
  await expect(menu).toBeFocused()
  // a tap outside closes it (V16)
  await menu.click()
  await page.mouse.click(8, page.viewportSize()!.height - 8)
  await expect(menu).toHaveAttribute("aria-expanded", "false")
  // the notifications list stays inside the window (V1)
  await page.getByRole("button", { name: /^Notifications/ }).click()
  const box = (await page.getByRole("dialog", { name: "Notifications" }).boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.keyboard.press("Escape")
  await menu.click()
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

test("@smoke the single-key shortcuts (/, ?, 1-4) can be switched off on the Account page (WCAG 2.1.4)", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "member", "/account")
  const slash = page.getByRole("switch", { name: "Single-key shortcuts" })
  await slash.click()
  await expect(slash).toHaveAttribute("aria-checked", "false")
  await page.locator("main").click({ position: { x: 4, y: 4 } })
  await page.keyboard.press("/")
  await expect(page.getByRole("dialog", { name: "Search and jump" })).toHaveCount(0)
  await slash.click()   // back on: / opens search again
  await page.locator("main").click({ position: { x: 4, y: 4 } })
  await page.keyboard.press("/")
  await expect(page.getByRole("dialog", { name: "Search and jump" })).toBeVisible()
  expectClean(errors)
})

test("@smoke custom fields: the settings panel, a rollout's values and the list's column", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/settings/workflow")
  await expect(page.getByRole("region", { name: "Custom fields" }).getByText("Region", { exact: true })).toBeVisible()   // seeded
  await page.goto("/projects/1")
  await expect(page.locator("#details").getByRole("button", { name: "Edit fields" })).toBeVisible()
  await page.goto("/projects")
  await expect(page.getByRole("columnheader", { name: "Region" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "Region" })).toBeVisible()
  expectClean(errors)
})

test("@smoke stage gates: the stage-list editors say what each stage asks before it is left", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  await page.locator("#stages").getByRole("button", { name: "Edit stages" }).click()
  await expect(page.getByRole("checkbox", { name: /^All tasks done before leaving / }).first()).toBeVisible()
  await expect(page.getByRole("button", { name: "Save what each stage asks" })).toBeVisible()
  await page.goto("/settings/workflow")
  await expect(page.getByRole("checkbox", { name: /^All tasks done before leaving / }).first()).toBeVisible()
  expectClean(errors)
})

test("@smoke task links: a waiting task says so, the task form picks what it waits on, templates bring tasks", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?rollout=2")
  // seeded: the firewall logs wait on the syslog forwarder, which is late
  await expect(page.locator("li", { has: page.getByRole("button", { name: "Edit Onboard firewall logs" }) }).first()).toContainText("waits on Stand up the syslog forwarder")
  await page.getByRole("region", { name: /^Tasks in / }).getByRole("button", { name: /^Add a task to / }).click()
  await expect(page.getByRole("combobox", { name: "Waits on" })).toBeVisible()
  await expect(page.getByRole("spinbutton", { name: "Estimate hours" })).toBeVisible()
  await page.goto("/settings/workflow")
  await expect(page.getByRole("heading", { name: /^Tasks that come with / }).first()).toBeVisible()
  await expect(page.getByRole("textbox", { name: /^Task title in / }).first()).toHaveValue("Confirm the PO and the scope with the customer")
  expectClean(errors)
})

test("@smoke crm intake: the seeded deal waits in the flow and its own list view, and Settings shows the endpoint's token panel and calls", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board")
  const lane = page.getByRole("region", { name: "Pending intake" })
  await expect(lane.getByText("Branch SD-WAN refresh")).toBeVisible()   // seeded through POST /api/v1/intake
  await expect(page.locator("main").getByRole("button", { name: /^Branch SD-WAN refresh, / })).toHaveCount(0)   // a holding lane, not a rollout row
  await page.goto("/projects")
  await page.getByRole("button", { name: /^Pending intake/ }).click()
  await expect(page.getByRole("region", { name: "Pending intake" }).getByRole("button", { name: "Confirm Branch SD-WAN refresh" })).toBeVisible()
  // its own page says it waits, with Confirm
  const pending = await (await page.request.get("/api/intake/pending")).json() as { rows: { id: number; name: string }[] }
  await page.goto(`/projects/${pending.rows.find((r) => r.name === "Branch SD-WAN refresh")!.id}`)
  await expect(page.getByRole("status").filter({ hasText: "waiting for a project manager" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Confirm…" })).toBeVisible()
  await page.goto("/settings/integrations")
  await expect(page.getByRole("region", { name: "CRM intake" })).toBeVisible()
  await expect(page.getByRole("table", { name: "Recent intake calls" }).getByText("201 Created").first()).toBeVisible()
  await expect(page.getByRole("region", { name: "Intake defaults" })).toBeVisible()
  expectClean(errors)
})
