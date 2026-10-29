// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import Alerts from "./Alerts"
import { admin } from "./fixtures"
import * as api from "@/lib/api"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  alerts: vi.fn(async () => ({ rows: [], show_resolved: false, alert_type: "", types: { overdue: "Overdue" }, page: 1, total_pages: 1, total: 0 })),
}))

describe("Alerts: Mine chip (sim 28 Oct)", () => {
  it("asks the server for mine=1, keeps the other filters, and a second click clears it", async () => {
    render(<MemoryRouter initialEntries={["/alerts?type=overdue"]}><Alerts user={admin} /></MemoryRouter>)
    const chip = await screen.findByRole("button", { name: "Mine" })
    expect(chip).toHaveAttribute("aria-pressed", "false")
    fireEvent.click(chip)
    await waitFor(() => expect(api.alerts).toHaveBeenLastCalledWith(expect.stringMatching(/(?=.*mine=1)(?=.*type=overdue)/)))
    expect(screen.getByRole("button", { name: "Mine" })).toHaveAttribute("aria-pressed", "true")
    fireEvent.click(screen.getByRole("button", { name: "Mine" }))
    await waitFor(() => expect(api.alerts).toHaveBeenLastCalledWith("type=overdue"))
  })
})
