// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import FlowGantt from "./FlowGantt"
import * as api from "@/lib/api"
import type { GanttData, GanttRow, GanttStage } from "@/lib/api"

// The Gantt's drag and the dialog that saves it (P2-57): a bar dragged two days opens
// the dialog, a baselined plan will not save without a reason, and what is sent is
// exactly the stages that changed. FlowGantt.tsx draws in a browser; here the pointer
// events carry the coordinates (jsdom has no layout, so every bar starts at 0).

const stage = (id: number, name: string, status: GanttStage["status"], start: string, end: string): GanttStage => ({
  id, name, status, sla_days: null, plan_start: start, plan_end: end, base_start: start, base_end: end, actual_start: null, actual_end: null,
  forecast_start: start, forecast_end: end, suggested_start: start, suggested_end: end, slip_days: null,
})
const row = (over: Partial<GanttRow> = {}): GanttRow => ({
  id: 7, name: "EDR Rollout - Globex", client: "Globex", stage: "Scoping", owner_name: "Admin", start_date: "2026-09-01", target_end_date: "2026-10-31",
  forecast: "2026-10-20", pct_complete: 20, rag: "green", has_plan: true, baselined: true, can_edit: true,
  stages: [stage(1, "Scoping", "next", "2026-09-07", "2026-09-11"), stage(2, "Kickoff", "next", "2026-09-14", "2026-09-18"), stage(3, "Closed", "next", "2026-09-21", "2026-09-21")], ...over,
})
const data = (rows: GanttRow[]): GanttData => ({ today: "2026-09-04", calendar: { working: false, week: [], off: [] }, rows })

vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), flowPlan: vi.fn(), savePlan: vi.fn(async () => ({ ok: true, changed: 2, baselined: false })) }))

beforeEach(() => {
  localStorage.clear()
  Element.prototype.setPointerCapture = () => {}
  localStorage.setItem("odin.pref.0.gantt.open", JSON.stringify([7]))   // the rollout's stages are showing
})
const mount = (rows: GanttRow[]) => {
  vi.mocked(api.flowPlan).mockResolvedValue(data(rows))
  return render(<FlowGantt ids={rows.map((r) => r.id)} selectedId={null} onSelect={() => {}} />)
}
// month zoom is 18 px a day: 36 px is two days. The bar is given a body (80 px wide) and grabbed in its
// middle: a press within 8 px of an edge resizes instead of moving.
const dragBy = (bar: HTMLElement, px: number) => {
  vi.spyOn(bar, "getBoundingClientRect").mockReturnValue({ left: 0, right: 80, width: 80, top: 0, bottom: 20, height: 20, x: 0, y: 0, toJSON() {} })
  fireEvent.pointerDown(bar, { clientX: 40, button: 0, pointerId: 1 })
  fireEvent.pointerMove(bar, { clientX: 40 + px, pointerId: 1 })
  fireEvent.pointerUp(bar, { pointerId: 1 })
}

describe("FlowGantt: drag a planned bar and save it", () => {
  it("a baselined plan needs a reason; the save sends the moved stage and the ones after it, and reloads", async () => {
    const user = userEvent.setup()
    mount([row()])
    const bar = await screen.findByRole("button", { name: /^Scoping plan .* Drag to move/ })
    dragBy(bar, 36)
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent("Scoping · EDR Rollout - Globex")
    expect(dialog).toHaveTextContent("3 stages change")   // the later stages follow by default
    await user.click(screen.getByRole("button", { name: "Save plan" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Say why the dates move")
    expect(api.savePlan).not.toHaveBeenCalled()
    await user.type(screen.getByRole("textbox"), "Customer asked")
    await user.click(screen.getByRole("button", { name: "Save plan" }))
    await waitFor(() => expect(api.savePlan).toHaveBeenCalledTimes(1))
    expect(api.savePlan).toHaveBeenCalledWith(7, [
      { id: 1, plan_start: "2026-09-09", plan_end: "2026-09-13" },
      { id: 2, plan_start: "2026-09-16", plan_end: "2026-09-20" },
      { id: 3, plan_start: "2026-09-23", plan_end: "2026-09-23" },
    ], "Customer asked")
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    expect(api.flowPlan).toHaveBeenCalledTimes(2)   // the page reloads the plans it just changed
  })

  it("an unbaselined plan saves without a reason, and Cancel changes nothing", async () => {
    const user = userEvent.setup()
    mount([row({ baselined: false })])
    dragBy(await screen.findByRole("button", { name: /^Kickoff plan .* Drag to move/ }), 18)
    await user.click(await screen.findByRole("button", { name: "Cancel" }))
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(api.savePlan).not.toHaveBeenCalled()
    dragBy(screen.getByRole("button", { name: /^Kickoff plan .* Drag to move/ }), 18)
    await user.click(await screen.findByRole("button", { name: "Save plan" }))
    await waitFor(() => expect(api.savePlan).toHaveBeenCalledWith(7, expect.arrayContaining([{ id: 2, plan_start: "2026-09-15", plan_end: "2026-09-19" }]), ""))
  })

  it("a server refusal stays in the dialog and the dates are not reloaded", async () => {
    const user = userEvent.setup()
    vi.mocked(api.savePlan).mockRejectedValueOnce(new api.ApiError(400, "That stage is already done"))
    mount([row({ baselined: false })])
    dragBy(await screen.findByRole("button", { name: /^Scoping plan .* Drag to move/ }), 18)
    await user.click(await screen.findByRole("button", { name: "Save plan" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("That stage is already done")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(api.flowPlan).toHaveBeenCalledTimes(1)
  })

  it("someone who may not edit the plan gets no draggable bar", async () => {
    mount([row({ can_edit: false })])
    expect(await screen.findByRole("button", { name: /EDR Rollout - Globex: .* to /i })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Drag to move/ })).toBeNull()
  })
})
