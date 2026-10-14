import { describe, expect, it } from "vitest"
import { addDays, changedStages, daysBetween, dragPlan, fillSuggested, setDate, workDays, type PlanRow } from "./plan"

const rows: PlanRow[] = [
  { id: 1, plan_start: "2026-10-01", plan_end: "2026-10-06", suggested_start: "2026-10-01", suggested_end: "2026-10-08" },
  { id: 2, plan_start: "2026-10-06", plan_end: "2026-10-16", suggested_start: "2026-10-08", suggested_end: "2026-10-15" },
  { id: 3, plan_start: null, plan_end: null, suggested_start: "2026-10-15", suggested_end: "2026-10-22" },
]

describe("plan editing", () => {
  it("counts working days without weekends and holidays", () => {
    const cal = { working: true, week: [0, 1, 2, 3, 4], off: ["2026-12-02"] }
    expect(workDays("2026-11-27", "2026-12-04", cal)).toBe(4)          // Fri to Fri: Mon, Tue, Thu, Fri
    expect(workDays("2026-11-27", "2026-12-04", { ...cal, working: false })).toBe(7)
    expect(workDays("2026-11-27", "2026-12-04")).toBe(7)
  })
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

describe("dragging a planned bar on the Gantt", () => {
  const r = (id: number, s: string | null, e: string | null): PlanRow => ({ id, plan_start: s, plan_end: e, suggested_start: "2026-10-01", suggested_end: "2026-10-05" })
  const rows = [r(1, "2026-10-01", "2026-10-10"), r(2, "2026-10-10", "2026-10-20"), r(3, null, null)]
  it("moves a bar whole, and the later stages with it when asked", () => {
    const moved = dragPlan(rows, 0, "move", 3, true)
    expect([moved[0].plan_start, moved[0].plan_end, moved[1].plan_start, moved[1].plan_end]).toEqual(["2026-10-04", "2026-10-13", "2026-10-13", "2026-10-23"])
    expect(moved[2].plan_start).toBeNull()   // an unplanned stage stays unplanned
    expect(dragPlan(rows, 0, "move", 3, false)[1].plan_start).toBe("2026-10-10")
    expect(changedStages(rows, moved).map((x) => x.id)).toEqual([1, 2])
  })
  it("resizes one edge and never past the other", () => {
    expect(dragPlan(rows, 1, "end", -20, true)[1].plan_end).toBe("2026-10-10")
    expect(dragPlan(rows, 1, "start", 30, true)[1].plan_start).toBe("2026-10-20")
    const later = dragPlan(rows, 0, "start", 2, true)
    expect([later[0].plan_start, later[0].plan_end, later[1].plan_start]).toEqual(["2026-10-03", "2026-10-10", "2026-10-10"])   // a new start moves nothing else
  })
  it("plans an unplanned stage from its suggestion", () => {
    expect(dragPlan(rows, 2, "move", 1, false)[2]).toMatchObject({ plan_start: "2026-10-02", plan_end: "2026-10-06" })
  })
})
