import { describe, expect, it } from "vitest"
import { activeProjectsView, days, fmtDate, groupBlocks, initials, localDateTime, stateText, timeAgo } from "./format"

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

describe("groupBlocks", () => {
  it("runs consecutive items into one list and keeps the rest in order", () => {
    expect(groupBlocks([["h", "Timeline"], ["li", "a"], ["li", "b"], ["p", "text"], ["li", "c"]])).toEqual([
      { kind: "h", text: "Timeline" }, { kind: "ul", items: ["a", "b"] }, { kind: "p", text: "text" }, { kind: "ul", items: ["c"] },
    ])
    expect(groupBlocks([])).toEqual([])
  })
})

describe("activeProjectsView", () => {
  const from = (o: Record<string, string>) => (k: string) => o[k] ?? null
  it("lights the chip the URL means", () => {
    expect(activeProjectsView(from({}))).toBe("active")
    expect(activeProjectsView(from({ view: "overdue" }))).toBe("overdue")
    expect(activeProjectsView(from({ closed: "1" }))).toBe("closed")
    expect(activeProjectsView(from({ stage: "Scoping" }))).toBe("")
    expect(activeProjectsView(from({ view: "stale", closed: "1" }))).toBe("stale")
  })
})

describe("timeAgo", () => {
  const now = Date.parse("2026-09-27T12:00:00Z")
  it("counts up through minutes, hours and days, then gives a date", () => {
    expect(timeAgo("2026-09-27T11:59:40", now)).toBe("just now")
    expect(timeAgo("2026-09-27T11:40:00", now)).toBe("20 min ago")
    expect(timeAgo("2026-09-27T09:00:00", now)).toBe("3 h ago")
    expect(timeAgo("2026-09-26T09:00:00", now)).toBe("yesterday")
    expect(timeAgo("2026-09-23T12:00:00", now)).toBe("4 d ago")
    expect(timeAgo("2026-08-01T12:00:00", now)).toMatch(/Aug|1/)
    expect(timeAgo("2025-08-01T12:00:00", now)).toMatch(/2025/)
    expect(timeAgo("junk", now)).toBe("junk")
  })
})
