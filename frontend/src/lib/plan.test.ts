import { describe, expect, it } from "vitest"
import { addDays, daysBetween, fillSuggested, setDate, type PlanRow } from "./plan"

const rows: PlanRow[] = [
  { id: 1, plan_start: "2026-10-01", plan_end: "2026-10-06", suggested_start: "2026-10-01", suggested_end: "2026-10-08" },
  { id: 2, plan_start: "2026-10-06", plan_end: "2026-10-16", suggested_start: "2026-10-08", suggested_end: "2026-10-15" },
  { id: 3, plan_start: null, plan_end: null, suggested_start: "2026-10-15", suggested_end: "2026-10-22" },
]

describe("plan editing", () => {
  it("counts and adds days across a month end", () => {
    expect(addDays("2026-10-30", 3)).toBe("2026-11-02")
    expect(daysBetween("2026-10-30", "2026-11-02")).toBe(3)
  })
  it("moving an end carries the later planned stages by the same amount", () => {
    const out = setDate(rows, 0, "plan_end", "2026-10-09", true)
    expect([out[0].plan_end, out[1].plan_start, out[1].plan_end]).toEqual(["2026-10-09", "2026-10-09", "2026-10-19"])
    expect(out[2].plan_start).toBeNull()                          // an unplanned stage is left alone
    expect(setDate(rows, 0, "plan_end", "2026-10-09", false)[1].plan_start).toBe("2026-10-06")
    expect(rows[0].plan_end).toBe("2026-10-06")                   // the input is not mutated
  })
  it("moving a start keeps the length; an end before the start is pulled up to it", () => {
    expect(setDate(rows, 1, "plan_start", "2026-10-10", false)[1]).toMatchObject({ plan_start: "2026-10-10", plan_end: "2026-10-20" })
    expect(setDate(rows, 1, "plan_end", "2026-10-01", false)[1]).toMatchObject({ plan_start: "2026-10-06", plan_end: "2026-10-06" })
    expect(setDate(rows, 2, "plan_start", "2026-10-20", false)[2]).toMatchObject({ plan_start: "2026-10-20", plan_end: "2026-10-27" })
  })
  it("fills unplanned stages from the suggestion", () => {
    const out = fillSuggested(rows)
    expect(out[2]).toMatchObject({ plan_start: "2026-10-15", plan_end: "2026-10-22" }); expect(out[0]).toBe(rows[0])
  })
})
