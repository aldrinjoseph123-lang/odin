// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { Calendar } from "./Calendar"
import { calendarData } from "./fixtures"
import * as api from "@/lib/api"

vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), calendar: vi.fn(async () => calendarData), moveTaskDue: vi.fn(async () => ({ ok: true })) }))

const Where = () => <output data-testid="where">{useLocation().search}</output>
const mount = (wide = true) => render(<MemoryRouter initialEntries={["/board?view=calendar&month=2026-09"]}><Calendar wide={wide} /><Where /></MemoryRouter>)

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

  it("Enter on a movable task opens its rollout; Move picks a new due date from the keyboard", async () => {
    const user = userEvent.setup()
    mount()
    const chip = (await screen.findAllByRole("button", { name: /^Late: ?Task 1$/ }))[0]
    chip.focus(); await user.keyboard("{Enter}")
    expect(screen.getByTestId("where")).toHaveTextContent("rollout=1")
    await user.click(screen.getAllByRole("button", { name: "Move Task 1 to another day" })[0])
    expect(await screen.findByRole("dialog")).toHaveTextContent("Due 10 Sep")
    expect(screen.getByRole("button", { name: "Move task" })).toBeDisabled()   // same day: nothing to save
    await user.click(screen.getByRole("button", { name: /New due date/ }))
    await screen.findByRole("grid", { name: /September 2026/ })   // the popover's month; the rail has one too, so take the last
    await user.click(screen.getAllByRole("button", { name: /September 11th, 2026/ }).at(-1)!)
    await user.click(screen.getByRole("button", { name: "Move task" }))
    expect(api.moveTaskDue).toHaveBeenCalledWith(1, 1, "2026-09-11")
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })
})
