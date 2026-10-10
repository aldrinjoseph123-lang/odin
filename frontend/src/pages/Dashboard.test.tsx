// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Dashboard from "./Dashboard"
import { Toaster } from "@/components/Toaster"
import { admin, dashboard } from "./fixtures"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  dashboard: vi.fn(async () => dashboard),
  dashboardVersion: vi.fn(async () => ({ version: dashboard.version })),
  saveLayout: vi.fn(async (layout: unknown) => ({ ok: true, layout, is_custom: true })),
  resetLayout: vi.fn(async () => ({ ok: true, layout: dashboard.layout, is_custom: false })),
}))
import { resetLayout, saveLayout } from "@/lib/api"

const mount = () => render(<MemoryRouter><Dashboard user={admin} /><Toaster /></MemoryRouter>)   // saves answer in a toast
const titles = () => screen.getAllByRole("region").map((r) => r.getAttribute("aria-label"))

describe("Dashboard", () => {
  it("draws the widgets in the layout's order, honouring their settings", async () => {
    mount()
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(/Good (morning|afternoon|evening), Admin/)
    expect(titles()).toEqual(["Headline numbers", "Timeline", "Portfolio progress", "Open alerts"])
    expect(screen.getByText("Active rollouts")).toBeInTheDocument()
    expect(screen.queryByText("Over stage SLA")).toBeNull()                        // tiles setting hid it
    expect(screen.getByText("+1")).toBeInTheDocument()                             // active: 4 vs 3
    expect(screen.getByText("−1")).toBeInTheDocument()                             // overdue: 1 vs 2
  })

  it("a tile opens the rollouts behind its number; a widget expands with its data as a table", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: /^Overdue: 1, .* since .*\. Show them$/ }))
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

  it("a custom metric can be added more than once, titled and charted, saved on its own", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Add widget" }))
    await user.click(screen.getByRole("button", { name: /^Custom metric/ }))
    await user.click(screen.getByRole("button", { name: /^Custom metric/ }))
    expect(screen.getAllByRole("region", { name: "Custom metric" })).toHaveLength(2)
    await user.keyboard("{Escape}")
    await user.click(screen.getAllByRole("button", { name: "Customise Custom metric" })[0])
    await user.clear(screen.getByLabelText("Title")); await user.type(screen.getByLabelText("Title"), "Owners")
    await user.selectOptions(screen.getByLabelText("Measure"), "rollouts_by_owner")
    await user.selectOptions(screen.getByLabelText("Chart"), "number")
    expect(screen.getByRole("region", { name: "Owners" })).toHaveTextContent("Admin User")
    await waitFor(() => {
      const saved = (saveLayout as unknown as { mock: { calls: unknown[][] } }).mock.calls.at(-1)![0] as { id: string; uid?: string; settings: Record<string, unknown> }[]
      expect(saved.find((x) => x.settings.title === "Owners")).toMatchObject({ id: "custom", settings: { measure: "rollouts_by_owner", chart: "number" } })
      expect(new Set(saved.filter((x) => x.id === "custom").map((x) => x.uid)).size).toBe(2)
    })
  })

  it("each widget's menu moves, resizes, removes and configures it, saving at once, with Undo", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Customise Portfolio progress" }))
    await user.click(screen.getByRole("button", { name: "Move Portfolio progress earlier" }))
    await waitFor(() => expect(saveLayout).toHaveBeenLastCalledWith([
      { id: "kpis", w: 3, settings: { tiles: ["active", "overdue"] } }, { id: "progress", w: 1, settings: {} },
      { id: "timeline", w: 2, settings: { show: "all", limit: 12 } }, { id: "alerts", w: 1, settings: { limit: 8 } }]))
    expect((await screen.findAllByText("Saved to your dashboard.")).length).toBeGreaterThan(0)
    await user.keyboard("{Escape}")
    await user.click(screen.getByRole("button", { name: "Customise Timeline" }))
    await user.click(within(screen.getByRole("group", { name: "Width of Timeline" })).getByRole("button", { name: "Full" }))
    await user.selectOptions(screen.getByLabelText("Show"), "attention")
    await user.keyboard("{Escape}")
    await user.click(screen.getByRole("button", { name: "Customise Open alerts" }))
    await user.click(screen.getByRole("button", { name: "Remove Open alerts" }))
    expect(titles()).not.toContain("Open alerts")
    await screen.findByText("Open alerts removed.")
    const undos = screen.getAllByRole("button", { name: "Undo" })   // the newest toast's Undo is the last
    await user.click(undos[undos.length - 1])
    expect(titles()).toContain("Open alerts")
    await waitFor(() => expect(saveLayout).toHaveBeenLastCalledWith([
      { id: "kpis", w: 3, settings: { tiles: ["active", "overdue"] } }, { id: "progress", w: 1, settings: {} },
      { id: "timeline", w: 3, settings: { show: "attention", limit: 12 } }, { id: "alerts", w: 1, settings: { limit: 8 } }]))
    expect(screen.getByText(/your arrangement/)).toBeInTheDocument()
  })

  it("rows never leave a gap: the last widget of a row stretches", async () => {
    mount()
    await screen.findByRole("region", { name: "Timeline" })
    // 3 columns: kpis full; timeline ⅔ + progress ⅓; alerts alone, stretched to the full row
    const cell = (name: string) => screen.getByRole("region", { name }).parentElement!
    expect(cell("Timeline").className).toContain("col-span-2")
    expect(cell("Portfolio progress").className).toContain("col-span-1")
    expect(cell("Open alerts").className).toContain("col-span-3")
  })

  it("reset asks the server for the workspace default", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Customise Timeline" }))
    await user.click(screen.getByRole("button", { name: "Remove Timeline" }))
    await screen.findByText("Timeline removed.")
    await user.click(screen.getByRole("button", { name: "Dashboard layout" }))
    await user.click(screen.getByRole("button", { name: /Reset to default/ }))
    expect(resetLayout).toHaveBeenCalled()
    expect(await screen.findByText("Back to the workspace default.")).toBeInTheDocument()
  })
})
