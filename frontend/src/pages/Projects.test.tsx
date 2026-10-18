// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Projects from "./Projects"
import { admin, projects } from "./fixtures"
import * as api from "@/lib/api"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()), projects: vi.fn(async () => projects),
  pendingIntake: vi.fn(async () => ({ rows: [{ id: 9, name: "Branch SD-WAN", client: "Hooli", source: "crm", deal_id: "D-1", delivery_mode: "Outsourced", vendor_name: null, product_name: null,
    po_number: null, target_end_date: null, contacts: [], owner_name: "Admin User", created_at: "2026-10-01T08:00:00" }], can_confirm: true, can_lead: true, leads: [], po_category: "Client PO" })),
}))

describe("Projects", () => {
  it("switches between the table and cards, and remembers it", async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Projects user={admin} /></MemoryRouter>)
    expect(await screen.findByRole("table")).toBeInTheDocument()
    await user.click(screen.getByRole("radio", { name: "Cards" }))
    expect(screen.getByRole("list", { name: "Rollouts" })).toBeInTheDocument()
    expect(screen.getByText("1 of 2 tasks done")).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "Sort by" })).toBeInTheDocument()   // cards have no column heads
    expect(localStorage.getItem("odin.pref.0.projects.layout")).toBe(JSON.stringify("cards"))
    await user.click(screen.getByRole("radio", { name: "Table" }))
    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.queryByRole("combobox", { name: "Sort by" })).toBeNull()
  })

  it("offers the Pending intake filter only while a deal waits, and lists the deals there", async () => {
    const user = userEvent.setup()
    const { unmount } = render(<MemoryRouter><Projects user={admin} /></MemoryRouter>)
    await screen.findByRole("table")
    expect(screen.queryByRole("button", { name: /Pending intake/ })).toBeNull()
    unmount()
    vi.mocked(api.projects).mockResolvedValueOnce({ ...projects, pending: 2 })
    render(<MemoryRouter><Projects user={admin} /></MemoryRouter>)
    await user.click(await screen.findByRole("button", { name: /Pending intake/ }))
    expect(await screen.findByText("Branch SD-WAN")).toBeInTheDocument()
    expect(screen.queryByRole("table")).toBeNull()
  })
})
