// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { Calendar } from "./Calendar"
import { calendarData } from "./fixtures"

vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), calendar: vi.fn(async () => calendarData) }))

const mount = (wide = true) => render(<MemoryRouter initialEntries={["/board?view=calendar&month=2026-09"]}><Calendar wide={wide} /></MemoryRouter>)

describe("Calendar", () => {
  it("draws the month with bars, chips, a cap per day and the day panel", async () => {
    const user = userEvent.setup()
    mount()
    expect(await screen.findByRole("heading", { level: 2 })).toHaveTextContent("September 2026")
    expect(screen.getAllByRole("link", { name: /EDR Rollout - Globex/ }).length).toBeGreaterThan(0)   // the span's bars
    expect(screen.getByText("PO Received to Scoping")).toBeInTheDocument()                          // the move
    expect(screen.getByRole("button", { name: "+1 more" })).toBeInTheDocument()                    // 4 tasks, 3 shown
    await user.click(screen.getByRole("button", { name: "+1 more" }))
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("10 Sep · 4 items")
    await user.click(screen.getByRole("button", { name: "Tasks" }))
    expect(screen.queryByText("Task 1")).toBeNull()
  })

  it("below md the month is an agenda", async () => {
    mount(false)
    expect(await screen.findByRole("heading", { level: 2 })).toHaveTextContent("September 2026")
    expect(screen.getByRole("heading", { level: 3, name: /10 Sep/ })).toBeInTheDocument()
    expect(screen.getByText("Task 4")).toBeInTheDocument()                                          // no cap in the agenda
  })
})
