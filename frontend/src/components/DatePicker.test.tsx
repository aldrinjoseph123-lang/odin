// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { DatePicker } from "./DatePicker"

// Wednesday 14 Oct 2026, whatever day the suite runs
beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 9, 14, 13) }) })
afterEach(() => vi.useRealTimers())

describe("DatePicker quick picks (B4)", () => {
  it.each([["Today", "2026-10-14"], ["Tomorrow", "2026-10-15"], ["Next Monday", "2026-10-19"], ["+1 week", "2026-10-21"]])("%s sets %s", async (label, value) => {
    const user = userEvent.setup({ advanceTimers: () => {} }), change = vi.fn()
    render(<DatePicker value="" onChange={change} label="Due" />)
    await user.click(screen.getByRole("button", { name: /Due/ }))
    await user.click(await screen.findByRole("button", { name: label }))
    expect(change).toHaveBeenCalledWith(value)
  })
  it("leaves out a pick beyond the latest date allowed", async () => {
    const user = userEvent.setup({ advanceTimers: () => {} })
    render(<DatePicker value="" onChange={() => {}} label="Due" max="2026-10-16" />)
    await user.click(screen.getByRole("button", { name: /Due/ }))
    expect(await screen.findByRole("button", { name: "Tomorrow" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Next Monday" })).toBeNull()
    expect(screen.queryByRole("button", { name: "+1 week" })).toBeNull()
  })
})
