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
  dashboardVersion: vi.fn(async () => ({ version: dashboard.version })),
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

  it("a tile opens the rollouts behind its number; a widget expands with its data as a table", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Overdue: 1. Show them" }))
    const dialog = await screen.findByRole("dialog")
    expect(within(dialog).getByText("Overdue · 1")).toBeInTheDocument()
    expect(within(dialog).getByRole("link", { name: "EDR Rollout - Globex" })).toHaveAttribute("href", "/board?rollout=1")
    expect(within(dialog).getByText("12 d late")).toBeInTheDocument()
    await user.keyboard("{Escape}")
    await user.click(screen.getByRole("button", { name: "Expand Open alerts" }))
    const big = await screen.findByRole("dialog")
    expect(within(big).getByRole("columnheader", { name: "Severity" })).toBeInTheDocument()
    expect(within(big).getByRole("cell", { name: "Project overdue" })).toBeInTheDocument()
  })

  it("a custom metric can be added more than once, titled and charted", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Customise" }))
    await user.click(screen.getByRole("button", { name: "Custom metric" }))   // the picker's pill, exactly
    await user.click(screen.getByRole("button", { name: "Custom metric" }))
    expect(screen.getAllByRole("region", { name: "Custom metric" })).toHaveLength(2)
    await user.click(screen.getAllByRole("button", { name: "Settings for Custom metric" })[0])
    await user.clear(screen.getByLabelText("Title")); await user.type(screen.getByLabelText("Title"), "Owners")
    await user.selectOptions(screen.getByLabelText("Measure"), "rollouts_by_owner")
    await user.selectOptions(screen.getByLabelText("Chart"), "number")
    expect(screen.getByRole("region", { name: "Owners" })).toHaveTextContent("Admin User")
    await user.click(screen.getByRole("button", { name: "Save my dashboard" }))
    const saved = (saveLayout as unknown as { mock: { calls: unknown[][] } }).mock.calls.at(-1)![0] as { id: string; uid?: string; settings: Record<string, unknown> }[]
    expect(saved.filter((x) => x.id === "custom")).toHaveLength(2)
    expect(saved.find((x) => x.settings.title === "Owners")).toMatchObject({ id: "custom", settings: { measure: "rollouts_by_owner", chart: "number" } })
    expect(new Set(saved.filter((x) => x.id === "custom").map((x) => x.uid)).size).toBe(2)
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
