// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useSearchParams } from "react-router-dom"
import Flow from "./Flow"
import { admin, flow } from "./fixtures"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  flow: vi.fn(async () => flow),
  flowDetail: vi.fn(async () => { throw new Error("not in this test") }),
  flowPlan: vi.fn(async () => ({ today: "2026-09-29", calendar: null, rows: [] })),
  pendingIntake: vi.fn(async () => ({ rows: [], can_confirm: true, can_lead: true, leads: [], po_category: "Client PO" })),
}))
const View = () => <p data-testid="view">{useSearchParams()[0].get("view") ?? "list"}</p>
const mount = () => render(<MemoryRouter initialEntries={["/board"]}><Flow user={admin} /><View /></MemoryRouter>)

describe("1–4 switch the Flow views (B6)", () => {
  it("goes to Kanban, Gantt, Calendar and back to the list", async () => {
    const user = userEvent.setup()
    mount()
    await screen.findByText("Late one")
    for (const [key, view] of [["2", "kanban"], ["3", "gantt"], ["4", "calendar"], ["1", "list"]]) {
      await user.keyboard(key)
      await waitFor(() => expect(screen.getByTestId("view")).toHaveTextContent(view))
    }
  })
  it("ignores a digit with a modifier, typed in a field, or with the single-key shortcuts off", async () => {
    const user = userEvent.setup()
    localStorage.setItem("odin.pref.0.shortcut.slash", "false")
    mount()
    await screen.findByText("Late one")
    await user.keyboard("2")
    expect(screen.getByTestId("view")).toHaveTextContent("list")
    localStorage.clear()
    await user.keyboard("{Control>}2{/Control}")
    expect(screen.getByTestId("view")).toHaveTextContent("list")
    const box = document.createElement("input")
    document.body.append(box)
    await user.click(box)
    await user.keyboard("2")
    expect(screen.getByTestId("view")).toHaveTextContent("list")
    box.remove()
  })
})
