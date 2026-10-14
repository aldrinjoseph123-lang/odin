import { describe, expect, it } from "vitest"
import { boardColumns, canDrag, columnOf, dropRefusal } from "./board"
import { flowRow } from "@/pages/fixtures"

describe("the Kanban's rules", () => {
  const r = flowRow({ id: 7, name: "EDR", stage: "Scoping", next_stage: "Sensor pilot" })
  it("puts each card in its stage's column, keeping empty columns", () => {
    const v = boardColumns([r], ["PO Received", "Scoping", "Sensor pilot"])
    expect(Object.keys(v)).toEqual(["PO Received", "Scoping", "Sensor pilot"])
    expect(v.Scoping.map((x) => x.id)).toEqual([7]); expect(v["PO Received"]).toEqual([])
    expect(columnOf(v, 7)).toBe("Scoping")
  })
  it("lets a card go only to its next stage, when the person may move it and no sign-off waits", () => {
    expect(dropRefusal(r, "Scoping")).toBeNull()
    expect(dropRefusal(r, "Sensor pilot")).toBeNull()
    expect(dropRefusal(r, "Deployment")).toMatch(/only move to Sensor pilot/)
    expect(dropRefusal(r, "PO Received")).toMatch(/only move to Sensor pilot/)   // never backwards
    expect(dropRefusal({ ...r, can_move: false }, "Sensor pilot")).toMatch(/cannot move/)
    expect(dropRefusal({ ...r, signoff_needed: true }, "Sensor pilot")).toMatch(/signed sign-off/)
    expect(dropRefusal({ ...r, next_stage: null }, "Sensor pilot")).toMatch(/last stage/)
    expect(canDrag(r)).toBe(true); expect(canDrag({ ...r, can_move: false })).toBe(false)
  })
})
