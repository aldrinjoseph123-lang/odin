import { describe, expect, it } from "vitest"
import { flowChips, flowFilterParams, matchFlow, parseFlowFilter } from "./flowFilter"

const row = (id: number, o: { state?: "on_track" | "overdue"; late_tasks?: number; approval?: "pending" | null; mine?: boolean }) =>
  ({ id, state: "on_track" as const, late_tasks: 0, approval: null, mine: false, ...o })
const rows = [
  row(1, { state: "overdue", mine: true }),
  row(2, { state: "overdue" }),
  row(3, { late_tasks: 2, mine: true }),
  row(4, { mine: true }),
  row(5, { approval: "pending" }),
]
const ids = (f: Parameters<typeof matchFlow>[1]) => rows.filter((r) => matchFlow(r, f)).map((r) => r.id)

describe("Flow filters combine (sim 28 Oct)", () => {
  it("Mine and Needs attention together are the late things on my rollouts", () => {
    expect(ids({ reading: "attention", mine: false })).toEqual([1, 2, 3])
    expect(ids({ reading: "all", mine: true })).toEqual([1, 3, 4])
    expect(ids({ reading: "attention", mine: true })).toEqual([1, 3])
    expect(ids({ reading: "customer", mine: true })).toEqual([])
    expect(ids({ reading: "all", mine: false })).toEqual([1, 2, 3, 4, 5])
  })

  it("each chip counts within the other filter, and only one reading is on at a time", () => {
    const chips = flowChips(rows, { reading: "attention", mine: true })
    expect(Object.fromEntries(chips.map((c) => [c.key, c.n]))).toEqual({ all: 5, attention: 2, customer: 0, mine: 2 })
    expect(chips.filter((c) => c.on).map((c) => c.key)).toEqual(["attention", "mine"])
    expect(flowChips(rows, { reading: "all", mine: false }).filter((c) => c.on).map((c) => c.key)).toEqual(["all"])
  })

  it("the address: ?filter=mine still works, the new form is filter + mine=1, nothing falls back to the kept choice", () => {
    expect(parseFlowFilter("mine", null)).toEqual({ reading: "all", mine: true })             // the old single value
    expect(parseFlowFilter("attention", "1")).toEqual({ reading: "attention", mine: true })
    expect(parseFlowFilter(null, "1")).toEqual({ reading: "all", mine: true })
    expect(parseFlowFilter("attention", null, { reading: "all", mine: true })).toEqual({ reading: "attention", mine: false })   // the address wins whole
    expect(parseFlowFilter(null, null, { reading: "customer", mine: true })).toEqual({ reading: "customer", mine: true })
    expect(parseFlowFilter("nonsense", null)).toEqual({ reading: "all", mine: false })
    expect(flowFilterParams({ reading: "attention", mine: true })).toEqual({ filter: "attention", mine: "1" })
    expect(flowFilterParams({ reading: "all", mine: false })).toEqual({ filter: null, mine: null })
  })
})
