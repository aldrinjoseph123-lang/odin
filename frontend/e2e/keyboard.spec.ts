import { expect, test } from "@playwright/test"
import { signIn } from "./helpers"

// @keys: the journeys without a mouse.

test("@keys flow: j/k move, Enter opens, Esc closes, Home/End jump", async ({ page }) => {
  await signIn(page, "admin", "/board")
  await page.getByRole("button", { name: /Show \d+ on-track rollouts/ }).click()
  const rows = page.locator("button[data-row]")
  await rows.first().focus()
  await page.keyboard.press("j")
  await expect(rows.nth(1)).toBeFocused()
  await page.keyboard.press("k")
  await expect(rows.first()).toBeFocused()
  await page.keyboard.press("End")
  await expect(rows.last()).toBeFocused()
  await page.keyboard.press("Home")
  await expect(rows.first()).toBeFocused()
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/rollout=\d+/)
  await expect(page.getByRole("list", { name: "Stages" })).toBeVisible()   // the rollout is open before Esc is asked to close it
  await page.keyboard.press("Escape")
  await expect(page).not.toHaveURL(/rollout=/)
  await expect(rows.first()).toBeFocused()   // focus comes back to the row it opened, a frame later
  // the whole list is one tab stop: Tab from a row leaves the list
  await rows.first().focus()
  await page.keyboard.press("Tab")
  await expect(rows.first()).not.toBeFocused()
})

test("@keys dashboard: a widget's menu entirely from the keyboard", async ({ page }) => {
  await signIn(page, "admin", "/dashboard")
  await page.getByRole("button", { name: "Customise Portfolio progress" }).focus()
  await page.keyboard.press("Enter")
  await expect(page.getByRole("button", { name: "Move Portfolio progress earlier" })).toBeVisible()
  await page.getByRole("button", { name: "Move Portfolio progress earlier" }).focus()
  await page.keyboard.press("Enter")
  await expect(page.getByText(/Saved to your dashboard/).first()).toBeVisible()   // a toast
  await page.keyboard.press("Escape")
  await page.getByRole("button", { name: "Undo" }).last().focus()
  await page.keyboard.press("Enter")
  await expect(page.getByText(/Change undone/)).toBeVisible()
  // every control on the page has a name
  const nameless = await page.locator("main button").evaluateAll((els) => els.filter((b) => !b.textContent?.trim() && !b.getAttribute("aria-label")).length)
  expect(nameless).toBe(0)
})

test("@keys calendar: months, toggles and a day, by Tab and Enter", async ({ page }) => {
  await signIn(page, "admin", "/board?view=calendar")
  await expect(page.getByRole("button", { name: "Next month" })).toBeVisible()   // the calendar loads on first use
  const title = page.locator("h2")
  const start = await title.textContent()
  await page.getByRole("button", { name: "Next month" }).focus()
  await page.keyboard.press("Enter")
  await expect(title).not.toHaveText(start!)
  await page.getByRole("button", { name: "Today", exact: true }).focus()
  await page.keyboard.press("Enter")
  await expect(title).toHaveText(start!)
  const day = page.getByRole("button", { name: /\d+ items?$/ }).nth(8)
  await day.focus()
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/day=/)
  // focus is visible on the pills and the chips
  await page.getByRole("button", { name: "Tasks", exact: true }).focus()
  const ring = await page.getByRole("button", { name: "Tasks", exact: true }).evaluate((el) => getComputedStyle(el).outlineStyle !== "none" || getComputedStyle(el).boxShadow !== "none")
  expect(ring).toBe(true)
})

test("@keys the skip link reaches the content", async ({ page }) => {
  await signIn(page, "admin", "/dashboard")
  await expect(page.getByRole("link", { name: "Odin, home" })).toBeVisible()   // the shell is up: Tab before it lands in the loading skeleton
  await page.keyboard.press("Tab")
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused()
  await page.keyboard.press("Enter")
  await expect(page.locator("#main")).toBeFocused()
})

test("@keys a dialog gives focus back to the button that opened it", async ({ page }) => {
  // test report UX-10: focus fell to the page body, so the next Tab started from the top
  await signIn(page, "admin", "/projects/2")
  const add = page.locator("#raid").getByRole("button", { name: "Add" })
  await add.focus()
  await page.keyboard.press("Enter")
  await expect(page.getByRole("dialog")).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page.getByRole("dialog")).toBeHidden()
  await expect(add).toBeFocused()
})
