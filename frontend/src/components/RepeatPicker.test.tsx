// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { RepeatPicker } from "./RepeatPicker"
import { repeatFields } from "@/lib/repeat"

describe("RepeatPicker", () => {
  it("turns into the task fields: nothing when it does not repeat, the choice and its end when it does", () => {
    expect(repeatFields({})).toEqual({ recurrence: null, recur_until: null })
    expect(repeatFields({ repeat: "", until: "stage" })).toEqual({ recurrence: null, recur_until: null })   // an end without a repeat is dropped
    expect(repeatFields({ repeat: "weekly", until: "" })).toEqual({ recurrence: "weekly", recur_until: null })
    expect(repeatFields({ repeat: "monthly", until: "stage" })).toEqual({ recurrence: "monthly", recur_until: "stage" })
  })

  it("asks how often first, and until when only once it repeats", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const { rerender } = render(<RepeatPicker value={{}} due="2026-10-20" onChange={onChange} />)
    expect(screen.queryByRole("combobox", { name: "Repeat until" })).toBeNull()
    await user.selectOptions(screen.getByRole("combobox", { name: "Repeats" }), "fortnightly")
    expect(onChange).toHaveBeenLastCalledWith({ repeat: "fortnightly", until: "" })
    rerender(<RepeatPicker value={{ repeat: "fortnightly", until: "" }} due="2026-10-20" onChange={onChange} />)
    await user.selectOptions(screen.getByRole("combobox", { name: "Repeat until" }), "stage")
    expect(onChange).toHaveBeenLastCalledWith({ repeat: "fortnightly", until: "stage" })
    await user.selectOptions(screen.getByRole("combobox", { name: "Repeat until" }), "date")
    expect(onChange).toHaveBeenLastCalledWith({ repeat: "fortnightly", until: "2026-10-20" })   // starts at the due date: never before it
    rerender(<RepeatPicker value={{ repeat: "fortnightly", until: "2026-12-01" }} due="2026-10-20" onChange={onChange} />)
    expect(screen.getByRole("button", { name: /^Repeat until: (?!not set)/ })).toBeInTheDocument()
    await user.selectOptions(screen.getByRole("combobox", { name: "Repeats" }), "")
    expect(onChange).toHaveBeenLastCalledWith({ repeat: "", until: "" })
  })

  it("says why a repeat wants a due date", () => {
    render(<RepeatPicker value={{ repeat: "weekly" }} due="" onChange={() => {}} />)
    expect(screen.getByText(/Pick a due date/)).toBeInTheDocument()
  })
})
