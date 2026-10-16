import { expect, test } from "@playwright/test"
import type { FlowData, GanttData } from "../src/lib/api"
import { api, dragCard, expectClean, signIn, watch } from "./helpers"

// @flow: the Flow's Kanban and Gantt, driven with the mouse the way a person does (P3-50, P2-57):
// a drop the board refuses, a drop it accepts and Undo, and a dragged plan bar that is saved
// through the plan's log and put back. flows.spec covers the keyboard routes and the dialogs.

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")

test("@flow kanban: a drop two stages ahead is refused with the reason, a drop on the next stage moves the rollout and Undo brings it back", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?view=kanban")
  const column = (name: string) => page.locator(`[data-slot="kanban-column"][data-value="${name}"]`)
  await expect(page.locator('[data-slot="kanban-column"]').first()).toBeVisible()
  const columns = await page.locator('[data-slot="kanban-column"]').evaluateAll((els) => els.map((e) => e.getAttribute("data-value")!))
  const { body } = await api<FlowData>(page, "GET", "/api/flow")
  const stageOf = async (id: number) => (await api<FlowData>(page, "GET", "/api/flow")).body.rows.find((r) => r.id === id)!.stage
  const early = body.rows.filter((r) => r.can_move && !r.signoff_needed && r.next_stage && columns.indexOf(r.stage) >= 0 && columns.indexOf(r.stage) <= 1)

  // refused: a column that is not its next stage. The card stays, no dialog opens, and the toast names the one stage it may go to.
  const far = early.find((r) => columns[columns.indexOf(r.stage) + 2] && columns[columns.indexOf(r.stage) + 2] !== r.next_stage)!   // the board's columns are every template's stages
  expect(far, "a rollout early on the board with two stages after it").toBeDefined()
  await dragCard(page, page.getByRole("button", { name: `Move ${far.name} to ${far.next_stage}` }), column(columns[columns.indexOf(far.stage) + 2]))
  await expect(page.getByText(`${far.name} can only move to ${far.next_stage}, its next stage`)).toBeVisible()
  await expect(page.getByRole("dialog")).toHaveCount(0)
  expect(await stageOf(far.id), "a refused drop changes nothing").toBe(far.stage)

  // accepted: another rollout dropped on its next column, confirmed
  const near = early.find((r) => r.id !== far.id && columns[columns.indexOf(r.stage) + 1] === r.next_stage)!
  expect(near, "a rollout whose next stage is the next column").toBeDefined()
  await dragCard(page, page.getByRole("button", { name: `Move ${near.name} to ${near.next_stage}` }), column(near.next_stage!))
  const dialog = page.getByRole("dialog", { name: `Move ${near.name} to ${near.next_stage}` })
  await expect(dialog).toBeVisible()
  // the confirm ignores a click within 400 ms of the drop: press until it takes
  await expect(async () => {
    await dialog.getByRole("group", { name: `Confirm the move to ${near.next_stage}` }).getByRole("button", { name: /^Move / }).click({ timeout: 1000 })
    await expect(dialog).toHaveCount(0, { timeout: 500 })
  }).toPass({ intervals: [300, 500, 700] })
  await expect(page.getByText(`${near.name} moved to ${near.next_stage}.`)).toBeVisible()
  expect(await stageOf(near.id), "the server moved it").toBe(near.next_stage)
  await page.getByRole("button", { name: "Undo" }).click()
  await expect(page.getByText(/Moved back/)).toBeVisible()
  expect(await stageOf(near.id), "Undo put it back").toBe(near.stage)
  expectClean(errors)
})

type Stage = GanttData["rows"][number]["stages"][number]
const dates = (s: Stage[]) => s.map((x) => ({ id: x.id, plan_start: x.plan_start, plan_end: x.plan_end }))

test("@flow gantt: dragging a planned bar saves the new dates with a reason in the plan's log, and the dates go back", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "admin", "/board?view=gantt")
  const plans = async () => (await api<GanttData>(page, "GET", "/api/flow/plan")).body.rows
  // a rollout whose plan was baselined (so the log wants a reason) with a stage still ahead that has planned dates
  const before = (await plans()).find((r) => r.can_edit && r.baselined && r.stages.some((s) => s.status === "next" && s.plan_start && s.plan_end))!
  expect(before, "a baselined rollout with a planned stage ahead").toBeDefined()
  const index = before.stages.map((s) => s.status === "next" && !!s.plan_start && !!s.plan_end).lastIndexOf(true)   // the last: nothing after it to cascade into
  const original = dates(before.stages)
  try {
    await page.getByRole("radio", { name: "Week" }).click()   // 44 px a day
    const openAll = page.getByRole("button", { name: "Open every rollout" })
    if (await openAll.isVisible()) await openAll.click()
    // the stage rows follow their rollout's row, in order
    const bar = page.locator(`[data-gantt-row="${before.id}"]`).locator("xpath=ancestor::*[@role='row'][1]/following-sibling::*[@role='row']").nth(index)
      .getByRole("button", { name: /plan .* Drag to move/ })
    await bar.scrollIntoViewIfNeeded()
    const box = (await bar.boundingBox())!
    const room = page.viewportSize()!.width - (box.x + box.width / 2) > 160
    const px = room ? 88 : -88   // two days, towards the side with room
    const y = box.y + box.height / 2
    await page.mouse.move(box.x + box.width / 2, y)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width / 2 + px / 2, y, { steps: 4 })
    await page.mouse.move(box.x + box.width / 2 + px, y, { steps: 6 })
    await page.mouse.up()
    // the dialog says where the bar landed; a baselined plan needs the reason
    const dialog = page.getByRole("dialog", { name: new RegExp(`${escape(before.stages[index].name)} · ${escape(before.name)}`) })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole("button", { name: "Save plan" })).toBeEnabled()
    await dialog.getByRole("button", { name: "Save plan" }).click()
    await expect(dialog.getByRole("alert")).toHaveText(/Say why the dates move/)   // refused up front, nothing sent
    expect(dates((await plans()).find((r) => r.id === before.id)!.stages)).toEqual(original)
    await dialog.getByRole("textbox").fill("E2E drag")
    await dialog.getByRole("button", { name: "Save plan" }).click()
    await expect(page.getByText(`Plan saved for ${before.name}`)).toBeVisible()
    await expect(dialog).toHaveCount(0)
    // the server holds the move, the log holds the reason, and the bar moved
    const after = (await plans()).find((r) => r.id === before.id)!
    expect(after.stages[index].plan_start, "the stage moved").not.toBe(before.stages[index].plan_start)
    const log = await api<{ changes: { reason: string | null }[] }>(page, "GET", `/api/projects/${before.id}/plan`)
    expect(log.body.changes.some((c) => c.reason === "E2E drag")).toBe(true)
  } finally {
    // put the dates back (through the same door, with its own reason)
    const now = (await plans()).find((r) => r.id === before.id)!
    const moved = dates(now.stages).filter((d, i) => d.plan_start !== original[i].plan_start || d.plan_end !== original[i].plan_end)
    if (moved.length) await api(page, "PUT", `/api/projects/${before.id}/plan`, { stages: original.filter((o) => moved.some((m) => m.id === o.id)), reason: "E2E restore" })
  }
  expect(dates((await plans()).find((r) => r.id === before.id)!.stages)).toEqual(original)
  expectClean(errors)
})
