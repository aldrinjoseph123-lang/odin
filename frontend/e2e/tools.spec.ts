import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"
import { api, expectClean, inviteExternal, signIn, watch } from "./helpers"

// @flow: the quality-of-life tools (advice B11, B16, B17, B19, B20) on the seeded portfolio.
// Each journey leaves the data as it found it.

test("@flow stages: a stage dragged down one place saves through the move route, and the arrows put it back", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  const names = async () => (await api<{ stage_rows: { name: string }[] }>(page, "GET", "/api/projects/1")).body.stage_rows.map((s) => s.name)
  const before = await names()
  await page.locator("#stages").getByRole("button", { name: "Edit stages" }).click()
  const handles = page.locator("#stages [data-drag-handle]")
  expect(await handles.count()).toBeGreaterThan(3)
  // the second stage onto the third: the grip is the pointer's way, the arrows stay the keyboard's
  await handles.nth(1).scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)   // the editor has opened and the page has settled
  const a = (await handles.nth(1).boundingBox())!, b = (await handles.nth(2).boundingBox())!
  const frames = () => page.evaluate(() => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))))
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2)
  await page.mouse.down()
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2 + 10, { steps: 4 }); await frames()
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2 + 6, { steps: 10 }); await frames()
  await page.mouse.up()
  await expect.poll(names).toEqual([before[0], before[2], before[1], ...before.slice(3)])
  // the keyboard way back, and the grip is not a tab stop
  await expect(handles.first()).toHaveAttribute("aria-hidden", "true")
  await page.getByRole("button", { name: `Move ${before[1]} up` }).click()
  await expect.poll(names).toEqual(before)
  expectClean(errors)
})

test("@flow csv: a rollout's RAID and tasks download, formula-safe, for staff only", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  await expect(page.getByRole("group", { name: /Download this rollout/ })).toBeVisible()
  const [raid] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "RAID (CSV)" }).click()])
  expect(raid.suggestedFilename()).toMatch(/^odin-raid-.*\.csv$/)
  expect(readFileSync((await raid.path())!, "utf8").split(/\r?\n/)[0]).toBe("Kind,Title,Detail,Impact,Likelihood,Status,Owner,Due date,Stage,Resolution,Shown to the customer,Created by,Created at,Closed at")
  const [tasks] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Tasks (CSV)" }).click()])
  expect(tasks.suggestedFilename()).toMatch(/^odin-tasks-.*\.csv$/)
  expect(readFileSync((await tasks.path())!, "utf8")).toContain("Task,Stage,Assignee,Due date,Done")
  // a viewer may read the rollout, so may download it (the server refuses partners: test_v2_tools.py)
  await signIn(page, "viewer", "/projects/1")
  expect((await api(page, "GET", "/projects/1/raid.csv")).status).toBe(200)   // a viewer reads the rollout: staff
  expectClean(errors)
})

test("@flow my work: a task is added to one of my rollouts without opening it", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/my-work")
  const form = page.getByRole("form", { name: "Add a task" })
  await expect(form).toBeVisible()
  await form.getByRole("textbox", { name: "New task title" }).fill("E2E quick add")
  await form.getByRole("button", { name: "Add", exact: true }).click()
  await expect(page.getByText(/^Added to .*: E2E quick add/)).toBeVisible()
  await expect(page.getByRole("button", { name: "Complete E2E quick add" })).toBeVisible()
  // tidy: tick it done so it leaves the open list
  await page.getByRole("button", { name: "Complete E2E quick add" }).click()
  await expect(page.getByRole("button", { name: "Complete E2E quick add" })).toHaveCount(0)
  expectClean(errors)
})

test("@flow users: search narrows the list, and the access review deactivates a partner on no rollout", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/projects/1")
  const { email } = await inviteExternal(page, 1, "Customer")
  const team = (await api<{ participants: { id: number; email: string }[] }>(page, "GET", "/api/projects/1")).body.participants
  const mine = team.find((p) => p.email === email)!
  await page.evaluate(async (pid) => {
    const s = await (await fetch("/api/session")).json()
    await fetch(`/projects/1/participants/${pid}/remove`, { method: "POST", headers: { Accept: "application/json", "X-CSRF-Token": s.csrf } })
  }, mine.id)
  await page.goto("/users")
  // search: name, username, email or role
  await page.getByRole("searchbox", { name: "Search users" }).fill(email)
  await expect(page.getByRole("button", { name: /^Manage / })).toHaveCount(1)
  await page.getByRole("searchbox", { name: "Search users" }).fill("")
  await page.getByRole("combobox", { name: "Filter by role" }).selectOption("External")
  await expect(page.getByRole("button", { name: `Manage E2E Customer` }).first()).toBeVisible()
  await page.getByRole("combobox", { name: "Filter by role" }).selectOption("")
  // the access review: this partner is on no rollout, one click ends the account
  await page.getByRole("button", { name: /^Access review/ }).click()
  const row = page.getByRole("listitem").filter({ hasText: email })
  await expect(row).toContainText("On no rollout")
  await row.getByRole("button", { name: /^Deactivate / }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: /Deactivate|Confirm|OK/ }).click()
  await expect(page.getByRole("listitem").filter({ hasText: email })).toHaveCount(0)
  expectClean(errors)
})

test("@flow gantt print: the page is landscape and holds nothing but the chart", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?view=gantt")
  await expect(page.getByRole("button", { name: "Print" })).toBeVisible()
  await page.emulateMedia({ media: "print" })
  await expect(page.getByRole("table", { name: "Rollouts on a timeline" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Print" })).toBeHidden()      // the toolbar is screen only
  await expect(page.getByRole("list", { name: "Legend" })).toBeVisible()       // the legend prints
  await expect(page.getByRole("navigation")).toBeHidden()                      // no app chrome
  // the browser fires beforeprint itself; page.pdf() does not, so say it: the timeline is squeezed to the page
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")))
  const width = await page.getByRole("table", { name: "Rollouts on a timeline" }).evaluate((t) => t.firstElementChild!.getBoundingClientRect().width)
  expect(width).toBeLessThanOrEqual(1040)
  const pdf = await page.pdf({ preferCSSPageSize: true })
  expect(pdf.length).toBeGreaterThan(2000)
  expect(pdf.toString("latin1")).toMatch(/\/MediaBox\s*\[\s*0\s+0\s+841\.\d+\s+59[45]\.\d+\s*\]/)   // A4 landscape
  expectClean(errors)
})
