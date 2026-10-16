import { createHmac } from "node:crypto"
import { expect, test } from "@playwright/test"
import { dragCard, expectClean, pickDate, signIn, USERS, watch } from "./helpers"

// @flow: the journeys, end to end, on the seeded portfolio. Each test leaves
// the data as it found it where it can (undo, reset, restore), so the order
// does not matter.

test("@flow dashboard: each widget's menu saves at once, rows stay full, reset, and the workspace default", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/dashboard")
  const titles = () => page.locator("main section[aria-label]").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")))
  await expect(page.locator("main section[aria-label='Timeline']")).toBeVisible()
  // a widget's own menu: move, width, a setting — each saved at once
  await page.getByRole("button", { name: "Customise Portfolio progress" }).click()
  await page.getByRole("button", { name: "Move Portfolio progress earlier" }).click()
  await expect(page.getByText(/Saved to your dashboard/).first()).toBeVisible()   // a toast
  await page.keyboard.press("Escape")
  await page.getByRole("button", { name: "Customise Timeline" }).click()
  await page.getByRole("radiogroup", { name: "Width of Timeline" }).getByRole("radio", { name: "Full" }).click()
  await page.locator("#timeline-show").selectOption("attention")
  await page.keyboard.press("Escape")
  await page.getByRole("button", { name: "Customise Open alerts" }).click()
  await page.getByRole("button", { name: "Remove Open alerts" }).click()
  await expect(page.locator("main section[aria-label='Open alerts']")).toHaveCount(0)
  await expect(page.getByText("Open alerts removed.")).toBeVisible()
  await page.getByRole("button", { name: "Undo" }).last().click()   // the newest toast's Undo
  await expect(page.locator("main section[aria-label='Open alerts']")).toHaveCount(1)
  // no gaps: every row of the three-column grid is full
  const rowsFull = await page.locator("main .grid.grid-cols-3 > div").evaluateAll((cells) => {
    let used = 0
    for (const c of cells) { const span = Number((c.className.match(/col-span-(\d)/) || [])[1] || 1); used += span; if (used > 3) return false; if (used === 3) used = 0 }
    return used === 0
  })
  expect(rowsFull).toBe(true)
  await expect(page.getByText("Change undone.").first()).toBeVisible()   // the toast follows the save: the PUT has landed
  await page.reload()
  await expect(page.locator("main section[aria-label='Timeline']")).toBeVisible()
  expect((await titles()).indexOf("Portfolio progress")).toBeLessThan((await titles()).indexOf("Timeline"))
  await expect(page.getByText("your arrangement")).toBeVisible()
  // add a widget from the picker
  await page.getByRole("button", { name: "Add widget" }).click()
  await page.getByRole("button", { name: /^Custom metric/ }).click()
  await page.keyboard.press("Escape")
  await expect(page.locator("main section[aria-label='Custom metric']")).toHaveCount(1)
  // reset returns to the workspace default
  await page.getByRole("button", { name: "Dashboard layout" }).click()
  await page.getByRole("button", { name: /Reset to default/ }).click()
  await expect(page.getByText(/Back to the workspace default/).first()).toBeVisible()   // a toast
  await expect(page.locator("main section[aria-label='Custom metric']")).toHaveCount(0)
  // an admin sets the default; a member without their own arrangement sees it
  await page.getByRole("button", { name: "Customise Cycle time" }).click()
  await page.getByRole("button", { name: "Remove Cycle time" }).click()
  await page.getByRole("button", { name: "Dashboard layout" }).click()
  await page.getByRole("button", { name: /Save as workspace default/ }).click()
  await page.locator("[data-confirm-yes]").click()   // it changes what everyone sees: asked first
  await expect(page.getByText(/Saved as the workspace default/).first()).toBeVisible()   // a toast
  await signIn(page, "member", "/dashboard")
  await expect(page.locator("main section[aria-label='Timeline']")).toBeVisible()
  await expect(page.locator("main section[aria-label='Cycle time']")).toHaveCount(0)
  // put it back
  await signIn(page, "admin", "/dashboard")
  await page.getByRole("button", { name: "Dashboard layout" }).click()
  await page.getByRole("button", { name: /Reset to default/ }).click()
  await page.getByRole("button", { name: "Add widget" }).click()
  await page.getByRole("button", { name: /^Cycle time/ }).click()
  await page.keyboard.press("Escape")
  await page.getByRole("button", { name: "Dashboard layout" }).click()
  await page.getByRole("button", { name: /Save as workspace default/ }).click()
  await page.locator("[data-confirm-yes]").click()   // it changes what everyone sees: asked first
  await expect(page.getByText(/Saved as the workspace default/).first()).toBeVisible()   // a toast
  expectClean(errors)
})

test("@flow dashboard: every widget's link goes where it says", async ({ page }) => {
  await signIn(page, "admin", "/dashboard")
  for (const [widget, link, url] of [["Timeline", "Open the flow", /\/board$/], ["Schedule", "My work", /\/my-work/], ["Team", "People", /\/people/], ["Open alerts", "All alerts", /\/alerts/], ["My work", "Open", /\/my-work/], ["Cycle time", "Detail", /\/analytics/]] as const) {
    await page.goto("/dashboard")
    await page.locator(`main section[aria-label='${widget}']`).getByRole("link", { name: link, exact: true }).click()
    await expect(page, `${widget} → ${link}`).toHaveURL(url)
  }
  await page.goto("/dashboard")
  await page.locator("main section[aria-label='Timeline'] a[href^='/board?rollout=']").first().click()
  await expect(page).toHaveURL(/\/board\?rollout=\d+/)
})

test("@flow flow list: filters, stage pills, grouping, the fold, opening a rollout", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board")
  const rows = page.locator("button[data-row]")
  const total = Number((await page.getByRole("button", { name: /^All, / }).getAttribute("aria-label"))!.match(/\d+/)![0])
  // on-track rows are folded behind one line; showing them lists everything
  await expect(page.getByRole("button", { name: /Show \d+ on-track rollouts/ })).toBeVisible()
  await page.getByRole("button", { name: /Show \d+ on-track rollouts/ }).click()
  await expect(rows).toHaveCount(total)
  await page.getByRole("button", { name: "Hide the on-track rollouts" }).click()
  // needs attention = the count on its chip
  const attention = page.getByRole("button", { name: /^Needs attention, / })
  const n = Number((await attention.getAttribute("aria-label"))!.match(/\d+/)![0])
  await attention.click()
  await expect(rows).toHaveCount(n)
  await expect(page).toHaveURL(/filter=attention/)
  // a stage pill narrows further and shows in the URL
  const pills = page.getByRole("navigation", { name: "Rollouts in each stage" })
  await pills.getByRole("button").first().click()
  const pill = pills.getByRole("button", { pressed: true })   // read the stage and count from the pill that is now lit
  const [, stage, count] = (await pill.getAttribute("aria-label"))!.match(/^(.+): (\d+)\./)!
  await expect(page).toHaveURL(/stage=/)
  await expect(rows).toHaveCount(Number(count))
  for (const r of await rows.all()) expect(await r.getAttribute("aria-label")).toContain(`. ${stage}, stage`)
  await pill.click()
  await page.getByRole("button", { name: /^All, / }).click()
  // grouping draws headers
  await page.getByRole("combobox", { name: "Group rollouts by" }).selectOption("client")
  await expect(page.locator("ul[aria-label] > li > p").first()).toBeVisible()
  await page.getByRole("combobox", { name: "Group rollouts by" }).selectOption("")
  // opening a rollout shows its flowchart; Esc closes it
  await rows.first().click()
  await expect(page).toHaveURL(/rollout=\d+/)
  await expect(page.getByRole("list", { name: "Stages" })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page).not.toHaveURL(/rollout=/)
  expectClean(errors)
})

test("@flow flow detail: advance with the confirm step, then undo", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?rollout=1")
  const advance = page.getByRole("button", { name: /^Move to (?!.* now$)/ })
  const next = (await advance.textContent())!.replace("Move to", "").trim()
  await advance.click()
  // the confirm names the risk (open tasks, no approval yet) and ignores a click within 400 ms of the first
  const move = page.getByRole("group", { name: `Confirm the move to ${next}` }).getByRole("button", { name: /^Move / })
  // press until it takes (a click within 400 ms of the first is ignored)
  await expect(async () => {
    await move.click()
    // the pane's live region (the shell keeps its own, empty, for server messages)
    await expect(page.getByRole("status").filter({ hasText: new RegExp(`moved to ${next}`) })).toBeVisible({ timeout: 1000 })
  }).toPass()
  await expect(page.locator("button[data-row][aria-current='true']")).toHaveAttribute("aria-label", new RegExp(next))
  await page.getByRole("button", { name: "Undo" }).click()
  await expect(page.getByRole("status").filter({ hasText: /Moved back/ })).toBeVisible()
  await expect(page.locator("button[data-row][aria-current='true']")).not.toHaveAttribute("aria-label", new RegExp(`\\. ${next},`))
  // a task can be added, ticked and removed in the current stage's list under the flowchart
  await page.getByRole("region", { name: /^Tasks in / }).getByRole("button", { name: /^Add a task to / }).click()
  await page.getByRole("textbox", { name: /^New task in / }).fill("E2E task")
  await page.getByRole("button", { name: "Add task" }).click()
  await page.getByRole("button", { name: "Complete E2E task" }).click()
  await expect(page.getByRole("button", { name: "Reopen E2E task" })).toBeVisible()
  await page.getByRole("button", { name: "Reopen E2E task" }).hover()   // the bin shows when the row is hovered
  await page.getByRole("button", { name: "Delete E2E task" }).click()
  await expect(page.getByRole("button", { name: /E2E task/ })).toHaveCount(0)
  expectClean(errors)
})

test("@flow calendar: months, toggles, a day, and a chip into the flow", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?view=calendar")
  await expect(page.getByRole("button", { name: "Next month" })).toBeVisible()   // the calendar loads on first use
  const title = page.locator("h2")
  const start = await title.textContent()
  await page.getByRole("button", { name: "Next month" }).click()
  await expect(title).not.toHaveText(start!)
  await expect(page).toHaveURL(/month=\d{4}-\d{2}/)
  await page.getByRole("button", { name: "Today" }).click()
  await expect(title).toHaveText(start!)
  // hiding tasks removes their chips
  const chips = page.locator(".grid-cols-7 :is(a, button)[title]")
  await page.waitForLoadState("networkidle")               // the month's data has landed before counting
  const before = await chips.count()
  await page.getByRole("button", { name: "Tasks", exact: true }).click()
  await expect.poll(() => chips.count()).toBeLessThan(before)
  await page.getByRole("button", { name: "Tasks", exact: true }).click()
  // a day with more than three items opens as a list
  await page.getByRole("button", { name: /\+\d+ more/ }).first().click()
  await expect(page.locator("h3", { hasText: /item/ })).toBeVisible()
  await expect(page).toHaveURL(/day=\d{4}-\d{2}-\d{2}/)
  await page.getByRole("button", { name: "Close" }).click()
  // a chip opens the rollout under the calendar
  await chips.first().click()
  await expect(page).toHaveURL(/view=calendar.*rollout=\d+/)
  expectClean(errors)
})

test("@flow projects: table or cards, remembered; sort and search", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects")
  await expect(page.getByRole("table")).toBeVisible()
  await page.getByRole("radio", { name: "Cards" }).click()
  await expect(page.getByRole("list", { name: "Rollouts" })).toBeVisible()
  await page.reload()
  await expect(page.getByRole("list", { name: "Rollouts" })).toBeVisible()
  await page.getByRole("combobox", { name: "Sort by" }).selectOption("name")
  await expect(page).toHaveURL(/sort=name/)
  await page.getByRole("radio", { name: "Table" }).click()
  await page.getByRole("textbox", { name: "Search rollouts" }).fill("Globex")
  await page.getByRole("button", { name: "Search", exact: true }).click()
  await expect(page).toHaveURL(/q=Globex/)
  await expect(page.getByText(/\d+ matching/)).toBeVisible()
  await expect.poll(async () => (await page.locator("tbody tr").allTextContents()).every((t) => /Globex/.test(t))).toBe(true)
  expectClean(errors)
})

test("@flow settings: a policy saves and takes effect", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/settings/general")
  const name = page.locator("#pol-company_name")
  const original = await name.inputValue()
  await name.fill("E2E Co")
  await page.getByRole("button", { name: "Save" }).first().click()
  await expect(page.getByText("Saved").first()).toBeVisible()
  await page.reload()
  await expect(page.locator("#pol-company_name")).toHaveValue("E2E Co")
  await page.locator("#pol-company_name").fill(original)
  await page.getByRole("button", { name: "Save" }).first().click()
  await expect(page.getByText("Saved").first()).toBeVisible()
  expectClean(errors)
})

test("@flow account: the home page is a choice", async ({ page }) => {
  await signIn(page, "member", "/account")
  const group = page.getByRole("radiogroup", { name: "Home page" })
  await group.getByRole("radio", { name: "Flow" }).click()
  await expect(group.getByRole("radio", { name: "Flow" })).toHaveAttribute("aria-checked", "true")
  await page.goto("/")
  await expect(page).toHaveURL(/\/board$/)
  await page.goto("/account")
  await group.getByRole("radio", { name: "Dashboard" }).click()
  await expect(group.getByRole("radio", { name: "Dashboard" })).toHaveAttribute("aria-checked", "true")
  await page.goto("/")
  await expect(page).toHaveURL(/\/dashboard$/)
})

test("@flow plan, RAID and the rollout report: move a date, log a risk, save a version, both PDFs", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  const plan = page.locator("#plan")
  await plan.getByRole("button", { name: "Edit dates" }).click()   // the dates are read until asked to edit
  const end = plan.locator("button[aria-label*='planned end']").last()
  await expect(end).toBeEnabled()
  const was = await end.getAttribute("data-value")
  const later = new Date(Date.parse(was || "2026-12-01") + 3 * 864e5).toISOString().slice(0, 10)
  await pickDate(page, end, later)
  await plan.getByRole("textbox", { name: "Why the dates move" }).fill("E2E slip")
  await plan.getByRole("button", { name: /^Save plan/ }).click()
  await expect(plan.getByRole("status").filter({ hasText: /Plan saved/ })).toBeVisible()
  await plan.getByRole("button", { name: /Show what moved/ }).click()
  await expect(plan.getByText("— E2E slip").first()).toBeVisible()

  // a risk: add, see it counted, then delete it
  const raid = page.locator("#raid")
  await raid.getByRole("button", { name: "Add" }).click()
  await page.getByRole("textbox", { name: "Title" }).fill("E2E risk")
  await page.getByRole("checkbox", { name: "Show in the customer's report" }).check()
  await page.getByRole("button", { name: "Save" }).click()
  await raid.getByRole("button", { name: /E2E risk/ }).click()
  await page.getByRole("button", { name: "Delete" }).click()
  await page.locator("[data-confirm-yes]").click()   // Odin's own confirm
  await expect(raid.getByRole("button", { name: /E2E risk/ })).toHaveCount(0)

  // the report: the customer copy hides the baseline; a saved version is listed; both PDFs render
  await page.goto("/projects/1/report")
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/EDR Rollout - Globex/)
  await page.getByRole("radio", { name: "Customer copy" }).click()
  await expect(page).toHaveURL(/audience=customer/)
  await expect(page.locator("main")).not.toContainText(/baseline/i)
  await page.getByRole("radio", { name: "Internal" }).click()
  await page.getByRole("textbox", { name: "What we need from the customer" }).fill("E2E: confirm the change window.")
  await page.getByRole("button", { name: "Save as version" }).click()
  await expect(page.getByRole("alertdialog")).toContainText(/Partners and customers/)
  await page.locator("[data-confirm-yes]").click()   // Odin's own confirm
  await expect(page.getByRole("status").filter({ hasText: /Version \d+ saved/ })).toBeVisible()
  for (const audience of ["internal", "customer"]) {
    const r = await page.request.get(`/projects/1/report.pdf?audience=${audience}`)
    expect(r.status()).toBe(200)
    expect(r.headers()["content-type"]).toContain("application/pdf")
  }
  expectClean(errors)
})

test("@flow portfolio report: health, roadmap into a rollout's report, the PDF", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/reports/all")
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Portfolio report")
  await expect(page.locator("section[aria-label='Health']")).toContainText(/off track|at risk|on track/)
  const roadmap = page.locator("section[aria-label='Roadmap']")
  const first = roadmap.getByRole("link").first()
  const name = (await first.locator("span.font-medium").textContent())!.trim()   // the name, not the health word said before it
  const r = await page.request.get("/reports/all.pdf")
  expect(r.status()).toBe(200)
  expect(r.headers()["content-type"]).toContain("application/pdf")
  await first.click()
  await expect(page).toHaveURL(/\/projects\/\d+\/report$/)
  await expect(page.getByRole("heading", { level: 1 })).toContainText(name.slice(0, 12))
  expectClean(errors)
})

test("@flow scope and sign-off: mark the last item, send, see it waiting, withdraw; the gate holds", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  // a sign-off goes out from the Sign-off stage (the stage before the finish): take the rollout there, and back at the end
  const move = (stage: string) => page.evaluate(async (stage) => {
    const s = await (await fetch("/api/session")).json()
    return (await fetch("/api/projects/1/stage", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": s.csrf }, body: JSON.stringify({ stage, note: "e2e: sign-off journey" }) })).status
  }, stage)
  const before = await page.evaluate(async () => (await (await fetch("/api/projects/1/flow")).json()).stage as string)
  expect(await move("Sign-off")).toBe(200)
  await page.reload()
  const scope = page.locator("#scope")
  await expect(scope).toContainText("1 agreed")
  await scope.getByRole("button", { name: /^Alerts forwarded/ }).click()
  await page.getByRole("radio", { name: "Delivered", exact: true }).click()
  await page.getByRole("button", { name: "Save" }).click()
  await expect(scope).toContainText("4 delivered")
  await scope.getByRole("link", { name: "Prepare the sign-off" }).click()
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Sign-off")
  await expect(page.getByRole("textbox", { name: "Summary" })).toHaveValue(/4 of 4 agreed scope items were delivered in full/)
  await page.getByRole("button", { name: "Send for signature" }).click()
  await page.getByRole("button", { name: /^Send to Ann Reyes now$/ }).click()
  await expect(page.getByText(/Version \d+ sent to Ann Reyes/)).toBeVisible()   // a toast
  await expect(page.getByText("Sent, waiting for the customer's signature").first()).toBeVisible()
  await expect(page.getByText(/SHA-256 [0-9a-f]{64}/)).toBeVisible()
  const pdf = await page.request.get("/projects/1/signoff.pdf")
  expect(pdf.headers()["content-type"]).toContain("application/pdf")
  // the admin is not the signatory: no signing form, and the stage move to the end is refused
  await expect(page.getByRole("button", { name: "Sign", exact: true })).toHaveCount(0)
  const refused = await page.evaluate(async () => {
    const s = await (await fetch("/api/session")).json()
    const stages = (await (await fetch("/api/projects/1/flow")).json()).stages as { name: string }[]
    const r = await fetch("/api/projects/1/stage", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": s.csrf }, body: JSON.stringify({ stage: stages[stages.length - 1].name }) })
    return r.status
  })
  expect(refused).toBe(400)
  // no mail on day one: the PM hands the signatory a one-time link
  await page.getByRole("button", { name: "Get a sign-in link" }).click()
  await expect(page.getByRole("textbox", { name: "Sign-in link for the signatory" })).toHaveValue(/\/auth\/link\/[^?]+\?next=%2Fprojects%2F1%2Fsignoff|\/auth\/link\/.+next=\/projects\/1\/signoff/)
  await page.getByRole("button", { name: "Withdraw and revise" }).click()
  await page.locator("[data-confirm-yes]").click()   // Odin's own confirm
  await expect(page.getByText(/withdrawn/).first()).toBeVisible()   // a toast
  await expect(page.getByRole("button", { name: "Send for signature" })).toBeVisible()
  expect(await move(before)).toBe(200)
  expectClean(errors.filter((e) => !/\/api\/projects\/1\/stage|400 \(BAD REQUEST\)/.test(e)))   // the refused move is the point
})

test("@flow people: active minutes are counted while the page is in use", async ({ page }) => {
  const errors = watch(page)
  const ping = page.waitForRequest((r) => r.url().endsWith("/api/activity") && r.method() === "POST")
  await signIn(page, "admin", "/people/2")
  await ping                                                    // the first minute is sent on arrival
  await expect(page.getByRole("region", { name: "Time on Odin" })).toContainText("Last 30 days")
  await page.goto("/account")
  await expect(page.getByRole("region", { name: "Time on Odin" })).toContainText("Admins and Members can also see")
  expectClean(errors)
})

test("@flow settings: an admin switches time on Odin and sign-up links off, then on again", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/settings/people")
  // each card saves on its own and leaves the other card's switch alone
  const time = page.getByRole("region", { name: "Time on Odin" })
  const signup = page.getByRole("region", { name: "Sign-up links" })
  await time.getByRole("switch", { name: "Record time on Odin" }).uncheck()
  await Promise.all([page.waitForResponse((r) => r.request().method() === "POST" && r.url().includes("/settings/") && r.ok()), time.getByRole("button", { name: "Save", exact: true }).click()])
  await expect(signup.getByRole("switch", { name: "Sign-up links work" })).toBeChecked()
  await signup.getByRole("switch", { name: "Sign-up links work" }).uncheck()
  await Promise.all([page.waitForResponse((r) => r.request().method() === "POST" && r.url().includes("/settings/") && r.ok()), signup.getByRole("button", { name: "Save", exact: true }).click()])
  await expect(time.getByRole("switch", { name: "Record time on Odin" })).not.toBeChecked()
  await page.goto("/account")
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  await expect(page.getByRole("region", { name: "Time on Odin" })).toHaveCount(0)
  await page.goto("/users")
  await expect(page.getByRole("region", { name: "Sign-up links" })).toContainText("switched off")
  await expect(page.getByRole("button", { name: "Create link" })).toHaveCount(0)
  // back on, so later journeys see the defaults
  await page.goto("/settings/people")
  await time.getByRole("switch", { name: "Record time on Odin" }).check()
  await Promise.all([page.waitForResponse((r) => r.request().method() === "POST" && r.url().includes("/settings/") && r.ok()), time.getByRole("button", { name: "Save", exact: true }).click()])
  await signup.getByRole("switch", { name: "Sign-up links work" }).check()
  await Promise.all([page.waitForResponse((r) => r.request().method() === "POST" && r.url().includes("/settings/") && r.ok()), signup.getByRole("button", { name: "Save", exact: true }).click()])
  // the longer explanation is one tap away
  await time.getByRole("button", { name: "What is Record time on Odin?" }).click()
  await expect(page.getByText(/visible and in use/)).toBeVisible()
  await page.keyboard.press("Escape")
  await page.goto("/account")
  await expect(page.getByRole("region", { name: "Time on Odin" })).toBeVisible()
  expectClean(errors)
})

test("@flow contacts: tabs, a product under its vendor, rename carries into projects, usage listed", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/settings/contacts")
  await page.getByRole("tab", { name: /Vendors/ }).click()
  await expect(page).toHaveURL(/tab=vendors/)
  await page.getByRole("button", { name: "Add vendor" }).click()
  await page.getByRole("dialog").getByRole("textbox", { name: "Name" }).fill("E2E Vendor")
  await page.getByRole("dialog").getByRole("button", { name: "Add", exact: true }).click()
  await expect(page.getByRole("dialog")).toHaveCount(0)
  await expect(page.getByRole("cell", { name: "E2E Vendor", exact: true })).toBeVisible()
  // a product added under that vendor
  await page.getByRole("tab", { name: /Products/ }).click()
  await page.getByRole("button", { name: "Add a product under E2E Vendor" }).click()
  await page.getByRole("dialog").getByRole("textbox", { name: "Name" }).fill("E2E Box")
  await expect(page.getByRole("dialog").getByRole("combobox", { name: "Vendor" })).toHaveValue(/\d+/)
  await page.getByRole("dialog").getByRole("button", { name: "Add", exact: true }).click()
  await expect(page.getByRole("cell", { name: "E2E Box", exact: true })).toBeVisible()
  // a duplicate name is refused inside the dialog
  await page.getByRole("button", { name: "Actions for E2E Box" }).click()
  await page.getByRole("menuitem", { name: "Edit" }).click()
  await page.getByRole("dialog").getByRole("textbox", { name: "Name" }).fill("FortiGate")
  await page.getByRole("dialog").getByRole("button", { name: "Save", exact: true }).click()
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("already exists")
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click()
  // the project form offers it only with its vendor
  await page.goto("/projects/new")
  await page.getByRole("combobox", { name: "Delivery mode" }).selectOption("Distribution/MSSP")
  const product = page.getByRole("combobox", { name: "Product" })
  await page.getByRole("combobox", { name: "Vendor" }).selectOption("Fortinet")
  await expect(product.locator("option", { hasText: "E2E Box" })).toHaveCount(0)
  await expect(product.locator("option", { hasText: "FortiGate" })).toHaveCount(1)
  await page.getByRole("combobox", { name: "Vendor" }).selectOption("E2E Vendor")
  await expect(product.locator("option", { hasText: "E2E Box" })).toHaveCount(1)
  await page.getByRole("combobox", { name: "Vendor" }).selectOption("")   // back to untouched, so leaving asks nothing
  // usage: a seeded vendor names its projects
  await page.goto("/settings/contacts?tab=partners")
  await expect(page.getByRole("tab", { name: /Partners/ })).toHaveAttribute("aria-selected", "true")
  await page.getByRole("button", { name: "Redington", exact: true }).click()
  await expect(page.getByText("meera@redington.example")).toBeVisible()
  // tidy up
  await page.goto("/settings/contacts?tab=products")
  await page.getByRole("button", { name: "Actions for E2E Box" }).click()
  await page.getByRole("menuitem", { name: "Delete" }).click()
  await page.locator("[data-confirm-yes]").click()   // Odin's own confirm
  await expect(page.getByRole("cell", { name: "E2E Box", exact: true })).toHaveCount(0)
  await page.goto("/settings/contacts?tab=vendors")
  await page.getByRole("button", { name: "Actions for E2E Vendor" }).click()
  await page.getByRole("menuitem", { name: "Delete" }).click()
  await page.locator("[data-confirm-yes]").click()   // Odin's own confirm
  await expect(page.getByRole("cell", { name: "E2E Vendor", exact: true })).toHaveCount(0)
  // the refused duplicate answers 400: expected
  expectClean(errors.filter((e) => !/400 \(BAD REQUEST\)|\/settings\/contacts\/products/.test(e)))
})

// RFC 6238 in a few lines, to play the authenticator app
function totp(secret: string, step = Math.floor(Date.now() / 30000)) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
  const bits = secret.replace(/\s/g, "").split("").map((c) => alphabet.indexOf(c).toString(2).padStart(5, "0")).join("")
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)))
  const msg = Buffer.alloc(8); msg.writeBigUInt64BE(BigInt(step))
  const h = createHmac("sha1", key).update(msg).digest()
  const o = h[h.length - 1] & 15
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000).padStart(6, "0")
}

// The current 30 s step, unless fewer than 3 s of it are left: then the next one (waited for), so
// the code is still good when the server checks it.
async function stepWithRoom() {
  const left = 30000 - (Date.now() % 30000)
  if (left < 3000) await new Promise((r) => setTimeout(r, left + 50))
  return Math.floor(Date.now() / 30000)
}

test("@flow two-step sign-in: set up with the app, sign in with a code, turn it off with a recovery code", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "viewer", "/account")
  const panel = page.getByRole("region", { name: "Two-step sign-in" })
  await panel.getByRole("button", { name: "Set up two-step sign-in" }).click()
  await panel.getByLabel("Your password").fill(USERS.viewer.password)   // setting it up asks for the password first
  await panel.getByRole("button", { name: "Continue" }).click()
  await expect(panel.getByRole("img", { name: "QR code for your authenticator app" })).toBeVisible()
  const secret = (await panel.locator("code").innerText()).replace(/\s/g, "")
  const step = await stepWithRoom()   // the code is made now, not a step boundary away
  await panel.getByLabel("Code", { exact: true }).fill(totp(secret, step))
  await panel.getByRole("button", { name: "Turn on" }).click()
  await expect(panel.getByRole("list", { name: "Recovery codes" }).getByRole("listitem")).toHaveCount(10)
  const codes = await panel.getByRole("list", { name: "Recovery codes" }).getByRole("listitem").allInnerTexts()
  expect(codes).toHaveLength(10)
  await panel.getByRole("button", { name: "I have saved them" }).click()
  await expect(panel).toContainText("on since")
  // sign in again: password, then the code
  await page.evaluate(async () => { const s = await (await fetch("/api/session")).json(); await fetch("/api/logout", { method: "POST", headers: { "X-CSRF-Token": s.csrf } }) })
  await page.goto("/login")
  await page.getByLabel("Username").fill(USERS.viewer.username)
  await page.getByLabel("Password", { exact: true }).fill(USERS.viewer.password)
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Two-step sign-in")
  await page.getByLabel("Code", { exact: true }).fill(totp(secret, step + 1))   // the enrolment used this step's code; the server accepts the next one
  await page.getByRole("button", { name: "Continue" }).click()
  await expect(page).toHaveURL(/\/dashboard|\/board/)
  // and off again, proven with the password and a recovery code
  await page.goto("/account")
  await panel.getByRole("button", { name: "Turn off" }).click()
  await panel.getByLabel("Password").fill(USERS.viewer.password)
  await panel.getByLabel("Authenticator or recovery code").fill(codes[0])
  await panel.getByRole("button", { name: "Turn off" }).click()
  await expect(panel).toContainText("off")
  await expect(panel.getByRole("button", { name: "Set up two-step sign-in" })).toBeVisible()
  expectClean(errors)
})

test("@flow sign-up link: an admin makes it, a colleague asks, the admin approves, they sign in", async ({ page, browser }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/users")
  const panel = page.getByRole("region", { name: "Sign-up links" })
  await panel.getByPlaceholder("e.g. Omar, field engineer").fill("E2E joiner")
  await panel.getByRole("button", { name: "Create link" }).click()
  const link = await panel.getByRole("textbox", { name: "New sign-up link" }).inputValue()
  expect(link).toMatch(/\/join\//)
  // a stranger's browser: the public page, no session
  const other = await browser.newContext()
  const guest = await other.newPage()
  await guest.goto(link.replace(/^https?:\/\/[^/]+/, ""))
  await expect(guest.getByRole("heading", { level: 1 })).toHaveText(/Join .* on Odin/)
  await guest.getByLabel("Full name").fill("E2E Joiner")
  await guest.getByLabel("Work email").fill("e2e.joiner@corp.example")
  await guest.getByLabel("Username").fill("e2ejoiner")
  await guest.getByLabel("Password", { exact: true }).fill("Correct-Horse-Battery-9")
  await guest.getByLabel("Again").fill("Correct-Horse-Battery-9")
  await guest.getByRole("button", { name: "Ask to join" }).click()
  await expect(guest.getByRole("heading", { level: 1 })).toHaveText("Request sent")
  // the admin approves it
  await page.reload()
  const waiting = page.getByRole("region", { name: "Waiting for approval" })
  await expect(waiting).toContainText("E2E Joiner")
  await expect(waiting).toContainText('via sign-up link "E2E joiner"')
  await waiting.getByRole("button", { name: "Approve" }).click()
  await expect(page.getByText(/can now sign in/)).toBeVisible()   // a toast
  // and they are in
  await guest.goto("/login")
  await guest.getByLabel("Username").fill("e2ejoiner")
  await guest.getByLabel("Password", { exact: true }).fill("Correct-Horse-Battery-9")
  await guest.getByRole("button", { name: "Sign in", exact: true }).click()
  await expect(guest).toHaveURL(/\/dashboard|\/board/)
  await other.close()
  expectClean(errors)
})

test("@flow document templates: brand, sections and wording; previewed, saved, picked for a sign-off", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/settings/documents")
  await page.getByRole("region", { name: "Sign-off" }).getByRole("button", { name: "New template" }).click()
  await page.getByLabel("Template name").fill("E2E certificate")
  await page.getByLabel("Document title").fill("Acceptance certificate")
  await page.getByRole("button", { name: "teal" }).click()
  await page.getByLabel("Show Summary").uncheck()
  await page.getByRole("button", { name: "Move Outstanding items up" }).click()
  await page.getByLabel(/Opening text/).fill("Prepared for {client}.")
  await page.getByRole("button", { name: "Preview" }).click()
  await expect(page.frameLocator("iframe[title='Template preview']").locator("body")).toBeAttached()
  await page.getByRole("button", { name: "Save template" }).click()
  await expect(page.getByRole("status").filter({ hasText: /Template saved/ })).toBeVisible()
  await expect(page.getByRole("region", { name: "Sign-off" })).toContainText("E2E certificate")
  await expect(page.getByRole("region", { name: "Sign-off" })).toContainText("Default")   // the first of its kind
  // a sign-off composer offers it
  await page.goto("/projects/1/signoff")
  await expect(page.getByRole("combobox", { name: "Document template" })).toContainText("E2E certificate (default)")
  // clean up: delete it
  await page.goto("/settings/documents")
  await page.getByRole("button", { name: "Delete E2E certificate" }).click()
  await page.locator("[data-confirm-yes]").click()   // Odin's own confirm
  await expect(page.getByRole("status").filter({ hasText: /Template deleted/ })).toBeVisible()
  expectClean(errors)
})

test("@flow feedback: a missing field is named under it, a finished task says so", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/new")
  await page.getByRole("button", { name: "Create project" }).click()
  const name = page.getByRole("textbox", { name: "Project name" })
  await expect(name).toHaveAttribute("aria-invalid", "true")
  await expect(name).toBeFocused()
  await expect(page.getByRole("alert")).toHaveText(/./)              // the browser's own words, under the field
  await name.fill("x")
  await expect(page.getByRole("alert")).toHaveCount(0)
  await expect(name).not.toHaveAttribute("aria-invalid", "true")
  // a state change answers with a toast, and putting it back answers too
  await page.goto("/board?rollout=1")
  // the current stage's list: Next up repeats its first task's tick under the same name
  const tasks = page.getByRole("region", { name: /^Tasks in / })
  const toggles = tasks.locator('button[aria-label^="Complete "], button[aria-label^="Reopen "]')
  await expect(toggles.first()).toBeVisible()   // the rollout's detail has loaded
  const labels = await toggles.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? ""))
  const bare = (l: string) => l.replace(/^(Complete|Reopen) /, "")
  const title = bare(labels.find((l) => l.startsWith("Complete ") && labels.filter((x) => bare(x) === bare(l)).length === 1)!)   // a task named once
  await tasks.getByRole("button", { name: `Complete ${title}` }).click()
  await expect(page.getByText(`Done: ${title}`)).toBeVisible()
  await tasks.getByRole("button", { name: `Reopen ${title}` }).click()
  await expect(page.getByText(`Reopened ${title}`)).toBeVisible()
  expectClean(errors)
})

test("@flow tasks: a new task takes a due date and is corrected in place", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?rollout=1")
  await page.getByRole("button", { name: /^Add a task to / }).first().click()
  await page.getByRole("textbox", { name: /^New task in / }).fill("E2E dated task")
  await pickDate(page, page.getByRole("button", { name: /^Due date:/ }), "2030-01-15")
  await page.getByRole("button", { name: "Add task" }).click()
  await expect(page.getByRole("button", { name: "Edit E2E dated task" })).toBeVisible()
  await expect(page.locator("li", { has: page.getByRole("button", { name: "Edit E2E dated task" }) }).first()).toContainText(/due /)
  // the title opens it: title, who and when, saved in place
  await page.getByRole("button", { name: "Edit E2E dated task" }).click()
  await page.getByRole("textbox", { name: "Task title" }).fill("E2E renamed task")
  await page.getByRole("button", { name: "Save E2E dated task" }).click()
  await expect(page.getByText("Task saved")).toBeVisible()
  await expect(page.getByRole("button", { name: "Edit E2E renamed task" })).toBeVisible()
  await page.getByRole("button", { name: "Complete E2E renamed task" }).hover()
  await page.getByRole("button", { name: "Delete E2E renamed task" }).click()
  await expect(page.getByRole("button", { name: /E2E renamed task/ })).toHaveCount(0)
  expectClean(errors)
})

test("@flow my work: a due date is set in place, and a tick can be undone", async ({ page }) => {
  const errors = watch(page)
  // a task of the admin's own, so the date is theirs to move
  await signIn(page, "admin", "/board?rollout=1")
  await page.getByRole("button", { name: /^Add a task to / }).first().click()
  await page.getByRole("textbox", { name: /^New task in / }).fill("E2E my task")
  await page.getByRole("combobox", { name: "Assign to" }).selectOption({ label: "Admin" })
  await page.getByRole("button", { name: "Add task" }).click()
  await expect(page.getByRole("button", { name: "Edit E2E my task" })).toBeVisible()
  await page.goto("/my-work")
  await page.getByRole("button", { name: "No date. Change the due date of E2E my task" }).click()
  await pickDate(page, page.getByRole("button", { name: /^Due date for E2E my task/ }), "2030-02-01")   // the picker opens by itself
  await expect(page.getByText("E2E my task: due")).toBeVisible()
  await page.getByRole("button", { name: "Complete E2E my task" }).click()
  await expect(page.getByText("Done: E2E my task")).toBeVisible()
  await expect(page.getByRole("button", { name: "Complete E2E my task" })).toHaveCount(0)
  await page.getByRole("button", { name: "Undo" }).click()
  await expect(page.getByRole("button", { name: "Complete E2E my task" })).toBeVisible()
  expectClean(errors)
})

test("@flow notes: an @mention is picked by keyboard, and a note can be shared", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  const box = page.getByRole("combobox", { name: "Add a note" })
  await box.fill("Thanks @")
  await expect(page.getByRole("listbox", { name: "Mention someone" })).toBeVisible()
  await box.press("ArrowDown")
  await box.press("Enter")
  await expect(page.getByRole("listbox", { name: "Mention someone" })).toHaveCount(0)
  await expect(box).toBeFocused()
  await expect(box).toHaveValue(/^Thanks @\S.* $/)
  // internal unless shared, and the form says so
  await expect(page.getByText("internal to the team")).toBeVisible()
  await page.getByRole("checkbox", { name: /Share with the customer/ }).check()
  await expect(page.getByText("Visible to the customer and partners")).toBeVisible()
  expectClean(errors)
})

test("@flow users: each person is one row; Manage opens their settings and Esc closes it", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/users")
  const list = page.getByRole("region", { name: "Team members" })
  await expect(list.getByRole("listitem").filter({ hasText: "Omar Haddad" })).toContainText(/Signed in|Never signed in/)
  await list.getByRole("button", { name: "Manage Omar Haddad" }).click()
  const dialog = page.getByRole("dialog", { name: "Omar Haddad" })
  await expect(dialog.getByRole("textbox", { name: "Email for Omar Haddad" })).toBeVisible()
  await expect(dialog.getByRole("button", { name: "Deactivate" })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(dialog).toHaveCount(0)
  expectClean(errors)
})

test("@flow project page: health in the title row, a section index, rare settings folded, a styled confirm", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  await expect(page.getByText(/^(On track|At risk|Off track|Complete)$/).first()).toBeVisible()
  const index = page.getByRole("navigation", { name: "Sections of this rollout" })
  await index.getByRole("link", { name: "Documents" }).click()
  await expect(page).toHaveURL(/#documents$/)
  // rotate and delete live behind ⋯
  await page.getByRole("button", { name: "More actions" }).click()
  await expect(page.getByRole("menuitem", { name: "Delete project" })).toBeVisible()
  await page.keyboard.press("Escape")
  // the stage editor and the invite forms are folded until asked for
  await expect(page.getByRole("button", { name: /^Delete PO Received/ })).toHaveCount(0)
  await page.getByRole("button", { name: "Edit stages" }).click()
  await expect(page.getByRole("button", { name: "Done editing" })).toBeVisible()
  await page.getByRole("button", { name: "Add people" }).click()
  await expect(page.getByRole("textbox", { name: "Invite by email" })).toBeVisible()
  // removing someone asks in the app's own dialog, with what it does; Cancel keeps them
  const remove = page.locator("#team").getByRole("button", { name: /^Remove / }).first()
  await remove.click()
  const ask = page.getByRole("alertdialog")
  await expect(ask).toContainText("They lose access")
  await ask.getByRole("button", { name: "Cancel" }).click()
  await expect(ask).toHaveCount(0)
  await expect(remove).toBeVisible()
  expectClean(errors)
})

test("@flow kanban: a card moves to its next stage from the keyboard and by dragging, through the confirm, and back with Undo", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?view=kanban")
  await expect(page.locator('[data-slot="kanban-column"]').first()).toBeVisible()   // the board loads on first use
  const columns = await page.locator('[data-slot="kanban-column"]').evaluateAll((els) => els.map((e) => e.getAttribute("data-value")))
  const rows: { name: string; stage: string; next_stage: string | null; can_move: boolean; signoff_needed: boolean }[] = await page.evaluate(async () => (await (await fetch("/api/flow")).json()).rows)
  // a rollout whose next stage is the very next column
  // (and early on the board, so its next column is on screen for the drag)
  const r = rows.find((x) => x.can_move && !x.signoff_needed && x.next_stage && columns.indexOf(x.stage) <= 1 && columns[columns.indexOf(x.stage) + 1] === x.next_stage)!
  const handle = page.getByRole("button", { name: `Move ${r.name} to ${r.next_stage}` })
  await handle.focus()
  await page.keyboard.press("Enter")   // the handle asks for the move from the keyboard
  const dialog = page.getByRole("dialog", { name: `Move ${r.name} to ${r.next_stage}` })
  await expect(dialog).toBeVisible()
  // the confirm ignores a click within 400 ms of the drop: press until it takes
  await expect(async () => {
    await dialog.getByRole("group", { name: `Confirm the move to ${r.next_stage}` }).getByRole("button", { name: /^Move / }).click()
    await expect(page.getByText(`${r.name} moved to ${r.next_stage}.`)).toBeVisible({ timeout: 1000 })
  }).toPass()
  await page.getByRole("button", { name: "Undo" }).click()
  await expect(page.getByText(/Moved back/)).toBeVisible()
  // the same move by dragging the handle into the next column opens the same confirm
  await dragCard(page, handle, page.locator(`[data-slot="kanban-column"][data-value="${r.next_stage}"]`))
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "Cancel" }).click()
  await expect(dialog).toHaveCount(0)
  // a card that may not move has no handle
  await signIn(page, "viewer", "/board?view=kanban")
  await expect(page.locator('[data-slot="kanban-column"]').first()).toBeVisible()
  await expect(page.getByRole("button", { name: /^Move .* to / })).toHaveCount(0)
  expectClean(errors)
})

test("@flow gantt: zoom, a rollout's stages, and a planned bar opened by keyboard", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?view=gantt")
  await page.getByRole("radio", { name: "Week" }).click()
  await expect(page.getByRole("radio", { name: "Week" })).toHaveAttribute("aria-checked", "true")
  await page.getByRole("button", { name: "Open every rollout" }).click()   // some rollouts have nothing left to plan
  const bar = page.getByRole("button", { name: /plan .* press Enter to pick dates/ }).first()
  await bar.focus()
  await page.keyboard.press("Enter")
  const dialog = page.getByRole("dialog")
  await expect(dialog.getByRole("button", { name: "Save plan" })).toBeDisabled()   // nothing changed yet
  await expect(dialog.getByText(/plan's log/)).toBeVisible()
  await dialog.getByRole("button", { name: "Cancel" }).click()
  await expect(dialog).toHaveCount(0)
  // clicking a rollout opens it under the timeline
  await page.getByRole("button", { name: /\d+% done/ }).first().click()
  await expect(page).toHaveURL(/view=gantt.*rollout=\d+/)
  expectClean(errors)
})

test("@flow calendar week: a task dragged to another day, and back with Undo", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?view=calendar")
  await page.getByRole("radio", { name: "Week" }).click()
  await expect(page).toHaveURL(/cal=week/)
  await expect(page.locator("h2")).toHaveText(/–/)
  // a task this admin may move, within six weeks (P3-50: it said nothing and crashed on null when there was none)
  let chip = page.locator("[data-drop-day] button[data-task]").first()
  for (let i = 0; i < 6 && !(await chip.count()); i++) {
    await page.getByRole("button", { name: "Next week" }).click()
    chip = page.locator("[data-drop-day] button[data-task]").first()
  }
  expect(await chip.count(), "a movable task in the next six weeks").toBeGreaterThan(0)
  const id = (await chip.getAttribute("data-task"))!
  const fromDay = (await chip.locator("xpath=ancestor::*[@data-drop-day][1]").getAttribute("data-drop-day"))!
  const days = await page.locator("[data-drop-day]").evaluateAll((els) => els.map((e) => e.getAttribute("data-drop-day")!))
  const toDay = days[days.indexOf(fromDay) >= 3 ? 0 : 6]
  await dragCard(page, chip, page.locator(`[data-drop-day="${toDay}"]`))
  await expect(page.getByText(/: due /).first()).toBeVisible()
  await expect(page.locator(`[data-drop-day="${toDay}"] button[data-task="${id}"]`)).toBeVisible()   // it moved
  await page.getByRole("button", { name: "Undo" }).click()
  await expect(page.getByText(/ again$/)).toBeVisible()
  await expect(page.locator(`[data-drop-day="${fromDay}"] button[data-task="${id}"]`)).toBeVisible()   // and Undo put it back
  await expect(page.locator(`[data-drop-day="${toDay}"] button[data-task="${id}"]`)).toHaveCount(0)
  expectClean(errors)
})

test("@flow delete a rollout, then Undo from the flow brings it back", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/2")
  const name = (await page.getByRole("heading", { level: 1 }).first().textContent())!.trim()
  await page.getByRole("button", { name: "More actions" }).click()
  await page.getByRole("menuitem", { name: "Delete project" }).click()
  await page.locator("[data-confirm-yes]").click()   // Odin's own confirm
  await expect(page).toHaveURL(/\/board/)
  await expect(page.getByText(/Project deleted/)).toBeVisible()
  await page.getByRole("button", { name: "Undo" }).click()
  await expect(page).toHaveURL(/\/projects\/2$/)
  await expect(page.getByRole("heading", { level: 1 }).first()).toHaveText(name)
  await expect(page.getByText(/restored/).first()).toBeVisible()
  expectClean(errors)
})

test("@flow a new API token stays on screen with Copy until it is put away", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/settings/api")
  await page.getByLabel("What uses it").fill("E2E token")
  await page.getByRole("button", { name: "Create token" }).click()
  const box = page.getByRole("textbox", { name: "New API token" })
  await expect(box).toHaveValue(/^odin_/)
  // longer than any toast: once the toasts are gone the token is still there
  await expect(page.locator("[aria-live=polite]").getByRole("button", { name: "Dismiss" })).toHaveCount(0, { timeout: 8000 })
  await expect(box).toBeVisible()
  await expect(page.getByRole("button", { name: /Copy the token|Copied/ })).toBeVisible()
  await page.getByRole("button", { name: "I have saved it" }).click()
  await expect(box).toHaveCount(0)
  // tidy: revoke it
  await page.getByRole("row", { name: /E2E token/ }).getByRole("button", { name: "Revoke" }).click()
  await page.locator("[data-confirm-yes]").click()
  expectClean(errors)
})

test("@flow kanban: a rollout waiting on its sign-off has no grip, only the way to the sign-off", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?view=kanban")
  await expect(page.locator('[data-slot="kanban-column"]').first()).toBeVisible()
  const rows: { id: number; name: string; next_stage: string | null; can_move: boolean; signoff_needed: boolean }[] = await page.evaluate(async () => (await (await fetch("/api/flow")).json()).rows)
  const r = rows.find((x) => x.can_move && x.signoff_needed)
  expect(r, "the seed has a rollout waiting on its sign-off").toBeTruthy()
  await expect(page.getByRole("button", { name: `Move ${r!.name} to ${r!.next_stage}` })).toHaveCount(0)
  const card = page.locator("li", { has: page.locator(`[data-card="${r!.id}"]`) })
  await card.getByRole("link", { name: `Sign-off before ${r!.next_stage}` }).click()
  await expect(page).toHaveURL(new RegExp(`/projects/${r!.id}/signoff`))
  expectClean(errors)
})

test("@flow calendar keyboard: Enter on a task opens its rollout; Move changes its due date, and Undo puts it back", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?view=calendar&cal=agenda")
  await expect(page.getByRole("button", { name: "Next month" })).toBeVisible()
  // a task this admin may move (its chip has a Move button beside it)
  let chip = page.locator("main button[data-task]").first()
  for (let i = 0; i < 6 && !(await chip.count()); i++) {
    const before = await page.getByRole("heading", { level: 2 }).first().textContent()
    await page.getByRole("button", { name: "Next month" }).click()
    await expect(page.getByRole("heading", { level: 2 }).first()).not.toHaveText(before ?? "")
    chip = page.locator("main button[data-task]").first()
  }
  const label = (await chip.locator("xpath=following-sibling::button[1]").getAttribute("aria-label"))!   // "Move <task> to another day"
  await chip.focus()
  await page.keyboard.press("Enter")   // Enter opens, it no longer starts a silent drag
  await expect(page).toHaveURL(/view=calendar.*rollout=\d+/)
  const move = page.getByRole("button", { name: label }).first()
  const dialog = page.getByRole("dialog")
  await expect(async () => {   // opening the rollout refreshes the calendar: a key pressed mid-redraw can miss the button
    await move.focus()
    await page.keyboard.press("Enter")
    await expect(dialog).toBeVisible({ timeout: 1000 })
  }).toPass()
  await expect(dialog.getByRole("button", { name: "Move task" })).toBeDisabled()   // the same day: nothing to save
  const trigger = dialog.getByRole("button", { name: /^New due date:/ })
  const due = (await trigger.getAttribute("data-value"))!
  await pickDate(page, trigger, new Date(Date.parse(`${due}T00:00:00Z`) + 86400000).toISOString().slice(0, 10))
  await dialog.getByRole("button", { name: "Move task" }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByText(/: due /)).toBeVisible()
  await page.getByRole("button", { name: "Undo" }).click()
  expectClean(errors)
})

test("@flow a view's chunk gone after a release: one reload; still gone, the error stays under the nav and clears on the way out", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board")
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  // the old build's Kanban file is gone: the first failure reloads the tab once
  let refused = 0
  await page.route(/\/assets\/FlowKanban-[\w-]+\.js$/, (route) => { refused++; return route.abort() })
  await page.getByRole("radio", { name: "Kanban" }).click()
  await expect.poll(() => refused).toBeGreaterThanOrEqual(2)   // the first try, then once more after the reload
  await expect(page.getByRole("heading", { name: "This page hit an error" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Flow", exact: true }).first()).toBeVisible()   // the nav stays
  await page.unroute(/\/assets\/FlowKanban-[\w-]+\.js$/)
  await page.getByRole("link", { name: "Flow", exact: true }).first().click()   // ?view= goes: the boundary clears
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Active rollouts")
  expectClean(errors.filter((e) => !/FlowKanban|Odin page error|dynamically imported module|Failed to load resource.*ERR_FAILED/.test(e)))
})

test("@flow account feedback: Save wakes on a change, Upload with no file says so, Remove picture and the error toast", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "member", "/account")
  const tell = page.locator("form", { hasText: "Tell me about" })
  await expect(tell.getByRole("button", { name: "Save" })).toBeDisabled()
  await tell.getByRole("switch").first().click()
  await expect(tell.getByRole("button", { name: "Save" })).toBeEnabled()
  await tell.getByRole("switch").first().click()
  await expect(tell.getByRole("button", { name: "Save" })).toBeDisabled()
  await page.getByRole("button", { name: "Upload" }).click()
  await expect(page.getByRole("alert").filter({ hasText: "Choose a picture first" })).toBeVisible()
  // a wrong current password is refused beside the form, and stays until it is fixed
  await page.getByLabel("Current password").fill("not-the-password-1")
  await page.getByLabel("New password").fill("Another-Long-Phrase-77")
  await page.getByRole("button", { name: "Update password" }).click()
  await expect(page.locator("form", { hasText: "Change password" }).getByRole("alert")).toBeVisible()
  expectClean(errors.filter((e) => !/^400 \S*\/account$|status of 400/.test(e)))   // the refusal is the point
})
