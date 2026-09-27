import { describe, expect, it } from "vitest"
import { days, fmtDate, initials, localDateTime, stateText } from "./format"

describe("initials", () => {
  it("takes the first letter of the first two words, upper-cased", () => {
    expect(initials("Ann Reyes")).toBe("AR")
    expect(initials("pm1")).toBe("P")
    expect(initials("Jane Okafor Smith")).toBe("JO")
    expect(initials(null)).toBe("?")
  })
})

describe("days", () => {
  it("rounds and marks unknown", () => {
    expect(days(8.6)).toBe("9 d")
    expect(days(0)).toBe("0 d")
    expect(days(null)).toBe("—")
  })
})

describe("fmtDate", () => {
  it("formats the date part only and dashes an empty value", () => {
    expect(fmtDate(null)).toBe("—")
    expect(fmtDate("2026-11-30T10:00:00")).toMatch(/30/)
  })
})

describe("stateText", () => {
  it("says the one thing each state needs", () => {
    expect(stateText({ state: "on_track", days_in_stage: 3.2, over_by: null, target_end_date: null })).toBe("3 d")
    expect(stateText({ state: "over_sla", days_in_stage: 9, over_by: 4, target_end_date: null })).toBe("9 d · 4 over SLA")
    expect(stateText({ state: "due_soon", days_in_stage: 1, over_by: null, target_end_date: "2026-11-30" })).toMatch(/^Due /)
    expect(stateText({ state: "overdue", days_in_stage: 1, over_by: null, target_end_date: "2020-01-01" })).toMatch(/^Overdue \d+ d$/)
  })
})

describe("localDateTime", () => {
  it("treats a naive stored timestamp as UTC and echoes junk unchanged", () => {
    expect(localDateTime("not a date")).toBe("not a date")
    expect(localDateTime("2026-09-25T03:32:31")).toMatch(/2026/)
  })
})
