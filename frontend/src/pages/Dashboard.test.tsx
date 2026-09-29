// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Dashboard from "./Dashboard"
import { admin, dashboard } from "./fixtures"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  dashboard: vi.fn(async () => dashboard),
  saveLayout: vi.fn(async (layout: unknown) => ({ ok: true, layout, is_custom: true })),
  resetLayout: vi.fn(async () => ({ ok: true, layout: dashboard.layout, is_custom: false })),
}))
import { resetLayout, saveLayout } from "@/lib/api"

const mount = () => render(<MemoryRouter><Dashboard user={admin} /></MemoryRouter>)
const titles = () => screen.getAllByRole("region").map((r) => r.getAttribute("aria-label"))

describe("Dashboard", () => {
  it("draws the widgets in the layout's order, honouring their settings", async () => {
    mount()
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(/Good (morning|afternoon|evening), Admin/)
    expect(titles()).toEqual(["Timeline", "Portfolio progress", "Open alerts"])   // kpis is a tile row, not a region
    expect(screen.getByText("Active rollouts")).toBeInTheDocument()
    expect(screen.queryByText("Over stage SLA")).toBeNull()                        // tiles setting hid it
    expect(screen.getByText("+1")).toBeInTheDocument()                             // active: 4 vs 3
    expect(screen.getByText("−1")).toBeInTheDocument()                             // overdue: 1 vs 2
  })

  it("customise: moves, resizes, removes, adds and saves a draft", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Customise" }))
    expect(screen.getByText("No changes yet")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Move Portfolio progress up" }))
    expect(titles()).toEqual(["Portfolio progress", "Timeline", "Open alerts"])
    await user.click(within(screen.getByRole("group", { name: "Width of Timeline" })).getByRole("button", { name: "Full" }))
    await user.click(screen.getByRole("button", { name: "Remove Open alerts" }))
    expect(titles()).toEqual(["Portfolio progress", "Timeline"])
    await user.click(screen.getByRole("button", { name: /Team/ }))                 // from the picker
    expect(titles()).toEqual(["Portfolio progress", "Timeline", "Team"])
    await user.click(screen.getByRole("button", { name: "Settings for Timeline" }))
    await user.selectOptions(screen.getByLabelText("Show"), "attention")
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Save my dashboard" }))
    expect(saveLayout).toHaveBeenCalledWith([
      { id: "kpis", w: 3, settings: { tiles: ["active", "overdue"] } },
      { id: "progress", w: 1, settings: {} },
      { id: "timeline", w: 3, settings: { show: "attention", limit: 12 } },
      { id: "team", w: 1, settings: {} },
    ])
    expect(await screen.findByRole("status")).toHaveTextContent("Your dashboard is saved")
    expect(screen.getByText(/your arrangement/)).toBeInTheDocument()
  })

  it("cancel drops the draft; reset asks the server for the default", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Customise" }))
    await user.click(screen.getByRole("button", { name: "Remove Timeline" }))
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(titles()).toEqual(["Timeline", "Portfolio progress", "Open alerts"])
    expect(screen.queryByRole("button", { name: "Reset to default" })).toBeNull()  // nothing custom yet
    await user.click(screen.getByRole("button", { name: "Customise" }))
    await user.click(screen.getByRole("button", { name: "Remove Timeline" }))
    await user.click(screen.getByRole("button", { name: "Save my dashboard" }))
    await screen.findByRole("status")
    await user.click(screen.getByRole("button", { name: "Customise" }))
    await user.click(screen.getByRole("button", { name: "Reset to default" }))
    expect(resetLayout).toHaveBeenCalled()
    expect(await screen.findByText("Back to the workspace default.")).toBeInTheDocument()
  })
})
